"""Multi-Trip Journey model, validation, splitting, and continuity."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .candidates import validate_candidates
from .clock import Clock, isoformat_seconds
from .contracts import canonical_json
from .flyai_inventory import AMapLodgingBackend, FlyAIBackend
from .mobility import MobilityBackend
from .planning import (
    RailBackend,
    RouteSpec,
    _budget_ledger,
    _normalize_journey_request,
    _normalize_request,
    _no_stay_conflict,
    _route_specs,
    plan_trip,
)
from .validate_trip import (
    SchemaSubsetValidator,
    ValidationIssue,
    ValidationReport,
    load_schema,
    validate_trip,
)
from .variflight_enrichment import VariFlightBackend


JOURNEY_SCHEMA_VERSION = "1.0.0"
TRIP_SCHEMA_REFERENCE = "trip.schema.json"
TRIP_DEFINITION_PREFIX = TRIP_SCHEMA_REFERENCE + "#/$defs/"
SEGMENT_ONE_WAY_CONSTRAINT = "单程（Journey 分段不自动返程）"


@dataclass(frozen=True)
class JourneySegmentInput:
    request: Mapping[str, Any]
    candidates: Mapping[str, Any]


@dataclass(frozen=True)
class JourneyPlanResult:
    journey: Mapping[str, Any]
    business_calls: Tuple[str, ...]
    trip_stages: Tuple[Tuple[str, ...], ...]
    journey_sha256: str


def default_journey_schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "schema" / "journey.schema.json"


def load_journey_schema(path: Optional[Path] = None) -> Mapping[str, Any]:
    schema_path = path or default_journey_schema_path()
    with schema_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):
        raise ValueError("Journey schema must be a JSON object")
    return schema


def resolved_journey_schema(path: Optional[Path] = None) -> Mapping[str, Any]:
    """Resolve the one canonical Trip schema for the dependency-free validator."""

    schema = copy.deepcopy(dict(load_journey_schema(path)))
    trip_schema = copy.deepcopy(dict(load_schema()))
    trip_definitions = copy.deepcopy(dict(trip_schema.pop("$defs")))
    definitions = copy.deepcopy(dict(schema.get("$defs", {})))
    collisions = set(definitions).intersection(trip_definitions)
    if collisions:
        raise ValueError("Journey and Trip schema definition collision: %s" % ", ".join(sorted(collisions)))
    definitions.update(trip_definitions)
    definitions["tripDocument"] = trip_schema
    schema["$defs"] = definitions

    def resolve(value: Any) -> None:
        if isinstance(value, dict):
            reference = value.get("$ref")
            if reference == TRIP_SCHEMA_REFERENCE:
                value["$ref"] = "#/$defs/tripDocument"
            elif isinstance(reference, str) and reference.startswith(TRIP_DEFINITION_PREFIX):
                value["$ref"] = "#/$defs/" + reference[len(TRIP_DEFINITION_PREFIX):]
            for child in value.values():
                resolve(child)
        elif isinstance(value, list):
            for child in value:
                resolve(child)

    resolve(schema)
    return schema


def split_journey_inputs(
    request: Mapping[str, Any],
    candidates: Mapping[str, Any],
) -> Tuple[JourneySegmentInput, ...]:
    """Split a request at cross-city days first, then at the seven-day hard limit."""

    normalized_request = _normalize_journey_request(request)
    normalized_candidates = json.loads(canonical_json(candidates))
    candidate_report = validate_candidates(normalized_candidates)
    if not candidate_report.ok:
        raise ValueError(
            "candidates validation failed: "
            + "; ".join(item.render() for item in candidate_report.errors)
        )
    shared_routes = _shared_journey_routes(normalized_request)
    lodging_city_by_date = _lodging_city_by_date(
        normalized_request,
        normalized_candidates["lodgings"],
    )
    starts = _segment_start_dates(
        normalized_request,
        shared_routes,
        lodging_city_by_date,
    )
    overall_end = date.fromisoformat(normalized_request["end_date"])
    segments: List[JourneySegmentInput] = []
    current_place = _initial_shared_place(normalized_request)
    consumed_routes = 0
    for index, start in enumerate(starts):
        end = starts[index + 1] - timedelta(days=1) if index + 1 < len(starts) else overall_end
        if lodging_city_by_date:
            destination = _request_place_for_city(
                normalized_request,
                lodging_city_by_date[start.isoformat()],
            )
            destinations = [destination]
        else:
            while consumed_routes < len(shared_routes) and date.fromisoformat(shared_routes[consumed_routes].travel_date) < start:
                current_place = shared_routes[consumed_routes].to_place
                consumed_routes += 1
            segment_routes: List[RouteSpec] = []
            route_cursor = consumed_routes
            while route_cursor < len(shared_routes):
                route_date = date.fromisoformat(shared_routes[route_cursor].travel_date)
                if route_date > end:
                    break
                segment_routes.append(shared_routes[route_cursor])
                route_cursor += 1
            destinations = _segment_destinations(current_place, segment_routes)
        segment_request = _segment_request(
            normalized_request,
            current_place,
            destinations,
            start,
            end,
            first=index == 0,
        )
        normalized_segment = _normalize_request(segment_request)
        segment_candidates = _segment_candidates(
            normalized_candidates,
            normalized_segment,
        )
        segments.append(JourneySegmentInput(normalized_segment, segment_candidates))
        if lodging_city_by_date:
            current_place = destination
        else:
            for route in segment_routes:
                current_place = route.to_place
            consumed_routes = route_cursor
    return tuple(segments)


def plan_journey(
    request: Mapping[str, Any],
    candidates: Mapping[str, Any],
    clock: Clock,
    rail_backend: RailBackend,
    mobility_backend: Optional[MobilityBackend] = None,
    flyai_backend: Optional[FlyAIBackend] = None,
    variflight_backend: Optional[VariFlightBackend] = None,
    amap_lodging_backend: Optional[AMapLodgingBackend] = None,
) -> JourneyPlanResult:
    """Plan each compliant Trip independently, then assemble one Journey."""

    normalized_source = _normalize_journey_request(request)
    segment_inputs = split_journey_inputs(normalized_source, candidates)
    trip_documents: List[Dict[str, Any]] = []
    calls: List[str] = []
    stages: List[Tuple[str, ...]] = []
    for segment in segment_inputs:
        # This explicit call is the invariant: every child must pass the unchanged
        # one-to-seven-day Trip boundary before the planner sees it.
        _normalize_request(segment.request)
        result = plan_trip(
            segment.request,
            segment.candidates,
            clock,
            rail_backend,
            mobility_backend,
            flyai_backend,
            variflight_backend,
            amap_lodging_backend,
        )
        trip_documents.append(copy.deepcopy(dict(result.trip)))
        calls.extend(result.business_calls)
        stages.append(result.stages)

    lodging_links = _bridge_segment_lodgings(trip_documents, segment_inputs)
    connections = _segment_connections(trip_documents, lodging_links)
    journey = assemble_journey(trip_documents, normalized_source, connections, clock)
    digest = hashlib.sha256(canonical_json(journey).encode("utf-8")).hexdigest()
    return JourneyPlanResult(
        journey=journey,
        business_calls=tuple(calls),
        trip_stages=tuple(stages),
        journey_sha256=digest,
    )


def _shared_journey_routes(request: Mapping[str, Any]) -> Tuple[RouteSpec, ...]:
    routes = _route_specs(request)
    groups = request.get("traveler_groups")
    if not groups:
        return routes
    anchor_ref = request["meeting_anchor"]["location"]["ref_id"]
    arrivals = {
        (item["origin"]["ref_id"], anchor_ref, str(item["group_id"]))
        for item in groups
    }
    return tuple(
        route for route in routes
        if not (
            len(route.group_refs) == 1
            and (route.from_place["ref_id"], route.to_place["ref_id"], route.group_refs[0]) in arrivals
        )
    )


def _segment_start_dates(
    request: Mapping[str, Any],
    routes: Sequence[RouteSpec],
    lodging_city_by_date: Mapping[str, str],
) -> Tuple[date, ...]:
    overall_start = date.fromisoformat(request["start_date"])
    overall_end = date.fromisoformat(request["end_date"])
    if lodging_city_by_date:
        preferred: List[date] = []
        previous_city = lodging_city_by_date[overall_start.isoformat()]
        cursor = overall_start + timedelta(days=1)
        while cursor <= overall_end:
            city = lodging_city_by_date[cursor.isoformat()]
            if city != previous_city:
                preferred.append(cursor)
                previous_city = city
            cursor += timedelta(days=1)
    else:
        preferred = sorted({
            date.fromisoformat(route.travel_date)
            for route in routes
            if overall_start < date.fromisoformat(route.travel_date) <= overall_end
        })
    boundaries = [overall_start] + preferred
    starts: List[date] = []
    for index, interval_start in enumerate(boundaries):
        interval_end = (
            boundaries[index + 1] - timedelta(days=1)
            if index + 1 < len(boundaries)
            else overall_end
        )
        cursor = interval_start
        while cursor <= interval_end:
            starts.append(cursor)
            cursor += timedelta(days=7)
    return tuple(starts)


def _lodging_city_by_date(
    request: Mapping[str, Any],
    lodgings: Sequence[Mapping[str, Any]],
) -> Mapping[str, str]:
    """Project an explicit lodging chain into the city for every Journey day."""

    overall_start = date.fromisoformat(request["start_date"])
    overall_end = date.fromisoformat(request["end_date"])
    destination_cities = {item["city"] for item in request["destinations"]}
    relevant = [item for item in lodgings if item["city"] in destination_cities]
    covered: Dict[str, str] = {}
    cursor = overall_start
    while cursor < overall_end:
        night = cursor.isoformat()
        covering = [
            item for item in relevant
            if item["check_in"] <= night < item["check_out"]
        ]
        cities = sorted({str(item["city"]) for item in covering})
        if len(cities) > 1:
            raise ValueError("Journey lodging chain has conflicting cities: " + canonical_json({
                "code": "LODGING_CITY_CONFLICT",
                "date": night,
                "cities": cities,
                "lodging_ids": sorted(str(item["lodging_id"]) for item in covering),
            }))
        if cities:
            covered[night] = cities[0]
        cursor += timedelta(days=1)
    if not covered:
        return {}

    first_city = covered[min(covered)]
    current_city = first_city
    result: Dict[str, str] = {}
    cursor = overall_start
    while cursor <= overall_end:
        travel_date = cursor.isoformat()
        if travel_date in covered:
            current_city = covered[travel_date]
        result[travel_date] = current_city
        cursor += timedelta(days=1)
    missing_nights = sorted(
        travel_date for travel_date in result
        if travel_date < overall_end.isoformat() and travel_date not in covered
    )
    if missing_nights:
        night = missing_nights[0]
        raise ValueError(
            "Journey lodging chain has no feasible stay: "
            + canonical_json(_no_stay_conflict(night, result[night], relevant))
        )
    return result


def _request_place_for_city(
    request: Mapping[str, Any],
    city: str,
) -> Mapping[str, str]:
    for place in request["destinations"]:
        if place["city"] == city:
            return copy.deepcopy(dict(place))
    raise ValueError("Journey lodging city is not a request destination: %s" % city)


def _initial_shared_place(request: Mapping[str, Any]) -> Mapping[str, str]:
    if request.get("traveler_groups"):
        return request["meeting_anchor"]["location"]
    if request.get("origin") is not None:
        return request["origin"]
    return request["destinations"][0]


def _segment_destinations(
    current_place: Mapping[str, str],
    routes: Sequence[RouteSpec],
) -> List[Mapping[str, str]]:
    destinations: List[Mapping[str, str]] = []
    for route in routes:
        destination = copy.deepcopy(dict(route.to_place))
        if not destinations or destinations[-1]["ref_id"] != destination["ref_id"]:
            destinations.append(destination)
    return destinations or [copy.deepcopy(dict(current_place))]


def _segment_request(
    source: Mapping[str, Any],
    current_place: Mapping[str, str],
    destinations: Sequence[Mapping[str, str]],
    start: date,
    end: date,
    *,
    first: bool,
) -> Mapping[str, Any]:
    result = copy.deepcopy(dict(source))
    result["start_date"] = start.isoformat()
    result["end_date"] = end.isoformat()
    result["destinations"] = copy.deepcopy(list(destinations))
    constraints = list(result.get("constraints", ()))
    if SEGMENT_ONE_WAY_CONSTRAINT not in constraints:
        constraints.append(SEGMENT_ONE_WAY_CONSTRAINT)
    result["constraints"] = constraints
    if source.get("traveler_groups") and first:
        result.pop("origin", None)
        result.pop("travelers", None)
    else:
        traveler_count = (
            sum(int(item["travelers"]) for item in source["traveler_groups"])
            if source.get("traveler_groups")
            else int(source["travelers"])
        )
        result["origin"] = copy.deepcopy(dict(current_place))
        result["travelers"] = traveler_count
        result.pop("traveler_groups", None)
        result.pop("meeting_anchor", None)
    return result


def _segment_candidates(
    candidates: Mapping[str, Any],
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    cities = {item["city"] for item in request["destinations"]}
    kept_pois: List[Mapping[str, Any]] = []
    poi_indexes: Dict[int, int] = {}
    for old_index, item in enumerate(candidates["pois"]):
        if item["city"] in cities:
            poi_indexes[old_index] = len(kept_pois)
            kept_pois.append(copy.deepcopy(item))

    kept_lodgings: List[Mapping[str, Any]] = []
    lodging_indexes: Dict[int, int] = {}
    for old_index, item in enumerate(candidates["lodgings"]):
        if item["city"] in cities:
            lodging_indexes[old_index] = len(kept_lodgings)
            kept_lodgings.append(copy.deepcopy(item))

    entity_ids = {
        item["poi_id"] for item in kept_pois
    } | {
        item["lodging_id"] for item in kept_lodgings
    }
    claims = [
        copy.deepcopy(item) for item in candidates["claims"]
        if item["subject_ref"] in entity_ids
    ]
    unknowns: List[Mapping[str, Any]] = []
    for item in candidates["unknowns"]:
        rewritten = _rewrite_candidate_unknown(item, poi_indexes, lodging_indexes)
        if rewritten is not None:
            unknowns.append(rewritten)
    result = {
        "candidates_version": candidates["candidates_version"],
        "pois": kept_pois,
        "lodgings": kept_lodgings,
        "claims": claims,
        "unknowns": unknowns,
    }
    report = validate_candidates(result)
    if not report.ok:
        raise ValueError(
            "segment candidates validation failed: "
            + "; ".join(item.render() for item in report.errors)
        )
    return result


def _rewrite_candidate_unknown(
    unknown: Mapping[str, Any],
    poi_indexes: Mapping[int, int],
    lodging_indexes: Mapping[int, int],
) -> Optional[Mapping[str, Any]]:
    parts = str(unknown["field_path"]).split("/", 3)
    if len(parts) != 4 or parts[0] != "" or not parts[2].isdigit():
        return None
    indexes = poi_indexes if parts[1] == "pois" else lodging_indexes if parts[1] == "lodgings" else None
    if indexes is None or int(parts[2]) not in indexes:
        return None
    rewritten = copy.deepcopy(dict(unknown))
    rewritten["field_path"] = "/%s/%d/%s" % (
        parts[1], indexes[int(parts[2])], parts[3],
    )
    return rewritten


def _bridge_segment_lodgings(
    trips: Sequence[Dict[str, Any]],
    segments: Sequence[JourneySegmentInput],
) -> Tuple[Mapping[str, Any], ...]:
    for index in range(len(trips) - 1):
        _ensure_boundary_lodging(
            trips[index],
            segments[index],
            trips[index + 1]["request"]["start_date"],
        )

    links: List[Mapping[str, Any]] = []
    for index in range(len(trips) - 1):
        left = trips[index]
        right = trips[index + 1]
        overnight = left["request"]["end_date"]
        next_start = right["request"]["start_date"]
        final_city = left["days"][-1]["city"]
        source_candidates = {
            item["lodging_id"]: item
            for item in segments[index].candidates["lodgings"]
        }
        eligible = []
        for lodging_index, lodging in enumerate(left["lodgings"]):
            source = source_candidates.get(lodging.get("candidate_ref"))
            if (
                lodging["city"] == final_city
                and source is not None
                and source["check_in"] <= overnight < source["check_out"]
            ):
                eligible.append((lodging["check_out"], lodging_index))
        if not eligible:
            raise ValueError(
                "Journey continuity failed: "
                + canonical_json(_no_stay_conflict(
                    overnight,
                    final_city,
                    segments[index].candidates["lodgings"],
                ))
            )
        _, lodging_index = max(eligible)
        outgoing = left["lodgings"][lodging_index]
        selected_nights = list(outgoing["selected_nights"])
        if overnight not in selected_nights:
            selected_nights.append(overnight)
            selected_nights.sort()
        outgoing["selected_nights"] = selected_nights
        outgoing["check_out"] = next_start
        left["days"][-1]["stay_id"] = outgoing["lodging_id"]
        ledger, budget_unknowns = _budget_ledger(
            left["request"],
            left["days"],
            left["transport_legs"],
            left["lodgings"],
            left["pois"],
            left["claims"],
        )
        left["budget_ledger"] = ledger
        left["unknowns"] = [
            item for item in left["unknowns"]
            if not str(item["field_path"]).startswith("/budget_ledger/")
        ] + budget_unknowns
        report = validate_trip(left)
        if not report.ok:
            raise ValueError(
                "boundary lodging produced an invalid Trip: "
                + "; ".join(item.render() for item in report.errors)
            )

        incoming = min(
            (
                item for item in right["lodgings"]
                if item["check_in"] == next_start
            ),
            key=lambda item: (item["check_out"], item["lodging_id"]),
            default=None,
        )
        outgoing_ref = outgoing.get("candidate_ref") or outgoing["lodging_id"]
        incoming_ref = (
            incoming.get("candidate_ref") or incoming["lodging_id"]
            if incoming is not None
            else None
        )
        if incoming is None:
            status = "departing"
            reason = "the following Trip ends without another overnight stay"
        elif incoming_ref == outgoing_ref:
            status = "continued"
            reason = "the same selected lodging candidate continues across the Trip boundary"
        else:
            status = "changed"
            reason = "the preceding lodging covers the boundary night before the next stay begins"
        links.append({
            "status": status,
            "overnight_date": overnight,
            "from_lodging_id": outgoing["lodging_id"],
            "to_lodging_id": incoming["lodging_id"] if incoming is not None else None,
            "reason": reason,
        })
    return tuple(links)


def _ensure_boundary_lodging(
    trip: Dict[str, Any],
    segment: JourneySegmentInput,
    next_start: str,
) -> None:
    """Materialize a boundary-night stay when a one-day child selected none."""

    overnight = trip["request"]["end_date"]
    final_city = trip["days"][-1]["city"]
    source_list = list(segment.candidates["lodgings"])
    source_by_id = {item["lodging_id"]: item for item in source_list}
    if any(
        lodging["city"] == final_city
        and lodging.get("candidate_ref") in source_by_id
        and source_by_id[lodging["candidate_ref"]]["check_in"] <= overnight
        < source_by_id[lodging["candidate_ref"]]["check_out"]
        for lodging in trip["lodgings"]
    ):
        return

    eligible = [
        (not bool(item.get("locked")), index, item)
        for index, item in enumerate(source_list)
        if item["city"] == final_city and item["check_in"] <= overnight < item["check_out"]
    ]
    if not eligible:
        raise ValueError(
            "Journey continuity failed: "
            + canonical_json(_no_stay_conflict(overnight, final_city, source_list))
        )
    _, source_index, source = min(eligible)
    stay_index = len(trip["lodgings"])
    stay = copy.deepcopy(dict(source))
    stay["check_in"] = overnight
    stay["check_out"] = next_start
    stay["candidate_ref"] = source["lodging_id"]
    stay["selection_status"] = "selected"
    stay["selected_nights"] = [overnight]
    trip["lodgings"].append(stay)

    existing_claim_ids = {item["claim_id"] for item in trip["claims"]}
    trip["claims"].extend(
        copy.deepcopy(item) for item in segment.candidates["claims"]
        if item["subject_ref"] == source["lodging_id"]
        and item["claim_id"] not in existing_claim_ids
    )
    for unknown in segment.candidates["unknowns"]:
        rewritten = _rewrite_candidate_unknown(
            unknown,
            {},
            {source_index: stay_index},
        )
        if rewritten is not None:
            trip["unknowns"].append(rewritten)


def _segment_connections(
    trips: Sequence[Mapping[str, Any]],
    lodging_links: Sequence[Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], ...]:
    connections: List[Mapping[str, Any]] = []
    for index, lodging_link in enumerate(lodging_links):
        left = trips[index]
        right = trips[index + 1]
        left_city = left["days"][-1]["city"]
        right_city = right["days"][0]["city"]
        if left_city == right_city:
            transport = {
                "status": "not_required",
                "leg_id": None,
                "included_in_trip_id": None,
                "price_type": None,
                "amount_min_cny": 0,
                "amount_max_cny": 0,
                "reason": "adjacent Trip segments remain in the same city",
            }
        else:
            candidates = [
                item for item in right["transport_legs"]
                if isinstance(item.get("depart_at"), str)
                and item["depart_at"][:10] == right["request"]["start_date"]
                and item.get("travel_mode") != "flight"
            ]
            if not candidates:
                raise ValueError("Journey continuity failed: " + canonical_json({
                    "code": "J_TRANSPORT_GAP",
                    "from_trip_id": left["trip_id"],
                    "to_trip_id": right["trip_id"],
                }))
            leg = min(candidates, key=lambda item: (item["depart_at"], item["leg_id"]))
            budget_item = next(
                (
                    item for item in right["budget_ledger"]["items"]
                    if item["ref_id"] == leg["leg_id"]
                ),
                None,
            )
            transport = {
                "status": "included_in_next_trip",
                "leg_id": leg["leg_id"],
                "included_in_trip_id": right["trip_id"],
                "price_type": budget_item["price_type"] if budget_item is not None else None,
                "amount_min_cny": budget_item["amount_min_cny"] if budget_item is not None else None,
                "amount_max_cny": budget_item["amount_max_cny"] if budget_item is not None else None,
                "reason": (
                    budget_item["reason"] if budget_item is not None
                    else "the following Trip owns the boundary leg but its comparable cost is unavailable"
                ),
            }
        connection_id = "connection-" + hashlib.sha256(canonical_json({
            "from": left["trip_id"],
            "to": right["trip_id"],
        }).encode("utf-8")).hexdigest()[:16]
        connections.append({
            "connection_id": connection_id,
            "from_trip_id": left["trip_id"],
            "to_trip_id": right["trip_id"],
            "from_end_date": left["request"]["end_date"],
            "to_start_date": right["request"]["start_date"],
            "lodging_continuity": copy.deepcopy(dict(lodging_link)),
            "cross_segment_transport": transport,
        })
    return tuple(connections)


def assemble_journey(
    trips: Sequence[Mapping[str, Any]],
    source_request: Mapping[str, Any],
    segment_connections: Sequence[Mapping[str, Any]],
    clock: Clock,
) -> Mapping[str, Any]:
    """Wrap complete standalone Trip documents in one validated Journey."""

    if not trips:
        raise ValueError("Journey requires at least one complete Trip")
    trip_documents = copy.deepcopy(list(trips))
    connections = copy.deepcopy(list(segment_connections))
    start_date = str(trip_documents[0]["request"]["start_date"])
    end_date = str(trip_documents[-1]["request"]["end_date"])
    identity: Dict[str, Any]
    if source_request.get("traveler_groups"):
        identity = {
            "traveler_groups": copy.deepcopy(list(source_request["traveler_groups"])),
            "meeting_anchor": copy.deepcopy(dict(source_request["meeting_anchor"])),
        }
    else:
        identity = {
            "origin": copy.deepcopy(source_request.get("origin")),
            "travelers": int(source_request["travelers"]),
        }
    budget_cny = source_request.get("budget_cny")
    now = isoformat_seconds(clock)
    identity_digest = {
        key: value for key, value in identity.items()
        if key in ("origin", "travelers", "traveler_groups")
    }
    journey_id = "journey-" + hashlib.sha256(canonical_json({
        "start_date": start_date,
        "end_date": end_date,
        "identity": identity_digest,
        "trip_ids": [item["trip_id"] for item in trip_documents],
    }).encode("utf-8")).hexdigest()[:16]
    journey: Dict[str, Any] = {
        "schema_version": JOURNEY_SCHEMA_VERSION,
        "journey_id": journey_id,
        "revision": {
            "number": 1,
            "parent_revision": None,
            "created_at": now,
            "reason": "initial multi-Trip journey plan",
            "created_by": "system",
        },
        "start_date": start_date,
        "end_date": end_date,
        "budget_ledger": journey_budget_ledger(trip_documents, connections, budget_cny),
        "trips": trip_documents,
        "segment_connections": connections,
        "generated_at": now,
    }
    journey.update(identity)
    report = validate_journey(journey)
    if not report.ok:
        raise ValueError("Journey validation failed: " + "; ".join(item.render() for item in report.errors))
    return journey


def journey_budget_ledger(
    trips: Sequence[Mapping[str, Any]],
    segment_connections: Sequence[Mapping[str, Any]],
    budget_cny: Optional[float],
) -> Mapping[str, Any]:
    """Aggregate Trip ledgers plus only transport not already owned by a Trip."""

    items: List[Mapping[str, Any]] = []
    known_cost = 0.0
    for trip in trips:
        ledger = trip.get("budget_ledger")
        if isinstance(ledger, Mapping):
            total_range = ledger.get("total_range_cny")
            minimum = total_range.get("minimum") if isinstance(total_range, Mapping) else None
            maximum = total_range.get("maximum") if isinstance(total_range, Mapping) else None
            trip_known = ledger.get("known_cost_cny")
            if isinstance(trip_known, (int, float)) and not isinstance(trip_known, bool):
                known_cost += float(trip_known)
            reason = None if minimum is not None and maximum is not None else "Trip ledger contains an incomparable price bound"
        else:
            minimum = None
            maximum = None
            reason = "Trip does not contain a budget ledger"
        items.append({
            "ref_id": str(trip["trip_id"]),
            "category": "trip",
            "price_type": None,
            "amount_min_cny": minimum,
            "amount_max_cny": maximum,
            "basis": "standalone Trip budget ledger",
            "included_in_total": True,
            "reason": reason,
        })

    for connection in segment_connections:
        transport = connection["cross_segment_transport"]
        separate = transport["status"] == "separate"
        minimum = transport["amount_min_cny"] if separate else 0
        maximum = transport["amount_max_cny"] if separate else 0
        if separate and isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
            known_cost += float(maximum)
        if separate:
            reason = transport.get("reason")
        elif transport["status"] == "included_in_next_trip":
            reason = "cross-segment transport is already included in %s" % transport["included_in_trip_id"]
        else:
            reason = "no cross-segment transport is required"
        items.append({
            "ref_id": str(connection["connection_id"]),
            "category": "cross_segment_transport",
            "price_type": transport.get("price_type"),
            "amount_min_cny": minimum,
            "amount_max_cny": maximum,
            "basis": "additional cross-segment transport",
            "included_in_total": True,
            "reason": reason,
        })

    total_minimum = _sum_if_complete(item["amount_min_cny"] for item in items)
    total_maximum = _sum_if_complete(item["amount_max_cny"] for item in items)
    known = _money(known_cost)
    if budget_cny is None:
        status = "unbudgeted"
        remaining = None
    elif total_maximum is None:
        status = "incomplete"
        remaining = _money(float(budget_cny) - float(known))
    elif float(total_maximum) <= float(budget_cny):
        status = "within_budget"
        remaining = _money(float(budget_cny) - float(total_maximum))
    else:
        status = "over_budget"
        remaining = _money(float(budget_cny) - float(total_maximum))
    return {
        "currency": "CNY",
        "budget_cny": budget_cny,
        "known_cost_cny": known,
        "remaining_known_budget_cny": remaining,
        "total_range_cny": {
            "minimum": total_minimum,
            "maximum": total_maximum,
        },
        "status": status,
        "items": items,
    }


def journey_booking_checklist(
    journey: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], ...]:
    """Derive every time-ordered booking or verification action from a Journey."""

    items: List[Mapping[str, Any]] = []
    for trip_index, trip in enumerate(journey["trips"]):
        context = _journey_trace_context(trip)
        for leg_index, leg in enumerate(trip["transport_legs"]):
            trace = _journey_entity_trace(
                trip,
                context,
                "transport_legs",
                leg_index,
            )
            items.append(_journey_action_item(
                "checklist",
                "transport",
                trip_index,
                trip,
                trace,
                leg.get("depart_at") or trip["request"]["start_date"],
                None,
                None,
                leg.get("provider"),
            ))
        for lodging_index, lodging in enumerate(trip["lodgings"]):
            trace = _journey_entity_trace(
                trip,
                context,
                "lodgings",
                lodging_index,
            )
            items.append(_journey_action_item(
                "checklist",
                "lodging",
                trip_index,
                trip,
                trace,
                lodging["check_in"],
                None,
                None,
                None,
            ))
        for unknown_index, unknown in enumerate(trip["unknowns"]):
            trace = _journey_unknown_trace(trip, context, unknown)
            items.append(_journey_action_item(
                "checklist",
                "unknown",
                trip_index,
                trip,
                trace,
                _journey_trace_deadline(trip, trace),
                unknown.get("claim_id"),
                unknown["field_path"],
                unknown.get("provider"),
                reason=unknown["reason"],
                source_index=unknown_index,
            ))
    return tuple(sorted(items, key=_journey_checklist_sort_key))


def journey_risk_items(
    journey: Mapping[str, Any],
) -> Tuple[Mapping[str, Any], ...]:
    """Derive all required capability, conflict, and unresolved-unknown risks."""

    items: List[Mapping[str, Any]] = []
    for trip_index, trip in enumerate(journey["trips"]):
        context = _journey_trace_context(trip)
        for health_index, health in enumerate(trip["provider_health"]):
            if health["status"] not in ("degraded", "missing"):
                continue
            for capability_index, capability in enumerate(health["capabilities"]):
                trace = {
                    "source_kind": "provider_health",
                    "source_ref": health["provider"],
                    "source_name": health["provider"],
                    "source_value": health,
                }
                items.append(_journey_action_item(
                    "risk",
                    "provider_capability",
                    trip_index,
                    trip,
                    trace,
                    trip["request"]["start_date"],
                    None,
                    None,
                    health["provider"],
                    reason=health["reason"],
                    status=health["status"],
                    capability=capability,
                    source_index=health_index * 1000 + capability_index,
                ))
        for claim_index, claim in enumerate(trip["claims"]):
            if claim["status"] != "conflict":
                continue
            trace = _journey_reference_trace(trip, context, claim["subject_ref"])
            items.append(_journey_action_item(
                "risk",
                "claim_conflict",
                trip_index,
                trip,
                trace,
                _journey_trace_deadline(trip, trace),
                claim["claim_id"],
                claim["field_path"],
                claim["provider"],
                reason="conflicting source claims require review",
                status=claim["status"],
                source_index=claim_index,
            ))
        for unknown_index, unknown in enumerate(trip["unknowns"]):
            trace = _journey_unknown_trace(trip, context, unknown)
            items.append(_journey_action_item(
                "risk",
                "unresolved_unknown",
                trip_index,
                trip,
                trace,
                _journey_trace_deadline(trip, trace),
                unknown.get("claim_id"),
                unknown["field_path"],
                unknown.get("provider"),
                reason=unknown["reason"],
                source_index=unknown_index,
            ))
    priority = {"claim_conflict": 0, "provider_capability": 1, "unresolved_unknown": 2}
    return tuple(sorted(
        items,
        key=lambda item: (
            priority[item["kind"]],
            _journey_deadline_sort_key(item["deadline"]),
            item["trip_index"],
            item["item_id"],
        ),
    ))


def _journey_action_item(
    prefix: str,
    kind: str,
    trip_index: int,
    trip: Mapping[str, Any],
    trace: Mapping[str, Any],
    deadline: str,
    claim_id: Optional[str],
    field_path: Optional[str],
    provider: Optional[str],
    *,
    reason: Optional[str] = None,
    status: Optional[str] = None,
    capability: Optional[str] = None,
    source_index: int = 0,
) -> Mapping[str, Any]:
    identity = {
        "kind": kind,
        "trip_index": trip_index,
        "source_index": source_index,
        "source_kind": trace["source_kind"],
        "source_ref": trace["source_ref"],
        "claim_id": claim_id,
        "field_path": field_path,
        "capability": capability,
    }
    return {
        "item_id": "%s-%s" % (
            prefix,
            hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()[:16],
        ),
        "kind": kind,
        "trip_index": trip_index,
        "trip_id": trip["trip_id"],
        "source_kind": trace["source_kind"],
        "source_ref": trace["source_ref"],
        "source_name": trace["source_name"],
        "claim_id": claim_id,
        "field_path": field_path,
        "provider": provider,
        "deadline": deadline,
        "reason": reason,
        "status": status,
        "capability": capability,
    }


def _journey_checklist_sort_key(item: Mapping[str, Any]) -> Tuple[Any, ...]:
    priority = {"transport": 0, "lodging": 1, "unknown": 2}
    return (
        _journey_deadline_sort_key(item["deadline"]),
        priority[item["kind"]],
        item["trip_index"],
        item["item_id"],
    )


def _journey_deadline_sort_key(value: str) -> Tuple[str, int, str]:
    # Date-only deadlines sort first on that day because their exact time is unknown.
    return (value[:10], 0 if len(value) == 10 else 1, value)


def _journey_trace_context(trip: Mapping[str, Any]) -> Mapping[str, Any]:
    names: Dict[str, str] = {}
    request = trip["request"]
    places: List[Mapping[str, Any]] = []
    if request.get("origin"):
        places.append(request["origin"])
    places.extend(item["origin"] for item in (request.get("traveler_groups") or ()))
    if request.get("meeting_anchor"):
        places.append(request["meeting_anchor"]["location"])
    places.extend(request["destinations"])
    for place in places:
        names[place["ref_id"]] = place["name"]
    for lodging in trip["lodgings"]:
        names[lodging["lodging_id"]] = lodging["name"]
    for poi in trip["pois"]:
        names[poi["poi_id"]] = poi["name"]
    for leg in trip["transport_legs"]:
        names[leg["leg_id"]] = "%s → %s" % (
            names.get(leg["from_ref"], leg["from_ref"]),
            names.get(leg["to_ref"], leg["to_ref"]),
        )
    return {"names": names}


def _journey_entity_trace(
    trip: Mapping[str, Any],
    context: Mapping[str, Any],
    collection: str,
    index: int,
) -> Mapping[str, Any]:
    keys = {
        "transport_legs": ("transport_leg", "leg_id"),
        "lodgings": ("lodging", "lodging_id"),
        "pois": ("poi", "poi_id"),
        "days": ("day", "day_id"),
    }
    source_kind, key = keys[collection]
    value = trip[collection][index]
    reference = value[key]
    if source_kind == "day":
        name = "%s · %s" % (value["date"], value["city"])
    else:
        name = context["names"].get(reference, reference)
    return {
        "source_kind": source_kind,
        "source_ref": reference,
        "source_name": name,
        "source_value": value,
    }


def _journey_reference_trace(
    trip: Mapping[str, Any],
    context: Mapping[str, Any],
    reference: str,
) -> Mapping[str, Any]:
    for collection, key, source_kind in (
        ("transport_legs", "leg_id", "transport_leg"),
        ("lodgings", "lodging_id", "lodging"),
        ("pois", "poi_id", "poi"),
        ("days", "day_id", "day"),
    ):
        for index, item in enumerate(trip[collection]):
            if item[key] == reference:
                return _journey_entity_trace(trip, context, collection, index)
    return {
        "source_kind": "trip",
        "source_ref": trip["trip_id"],
        "source_name": " → ".join(
            item["name"] for item in trip["request"]["destinations"]
        ),
        "source_value": trip,
    }


def _journey_unknown_trace(
    trip: Mapping[str, Any],
    context: Mapping[str, Any],
    unknown: Mapping[str, Any],
) -> Mapping[str, Any]:
    parts = _journey_pointer_parts(unknown["field_path"])
    if len(parts) >= 2 and parts[1].isdigit():
        index = int(parts[1])
        if parts[0] in ("transport_legs", "lodgings", "pois", "days"):
            if index < len(trip[parts[0]]):
                return _journey_entity_trace(trip, context, parts[0], index)
    if len(parts) >= 3 and parts[0] == "budget_ledger" and parts[1] == "items" and parts[2].isdigit():
        index = int(parts[2])
        budget_items = trip["budget_ledger"]["items"]
        if index < len(budget_items):
            return _journey_reference_trace(
                trip,
                context,
                budget_items[index]["ref_id"],
            )
    claim_id = unknown.get("claim_id")
    if claim_id:
        claim = next(
            (item for item in trip["claims"] if item["claim_id"] == claim_id),
            None,
        )
        if claim is not None:
            return _journey_reference_trace(trip, context, claim["subject_ref"])
    return _journey_reference_trace(trip, context, trip["trip_id"])


def _journey_trace_deadline(
    trip: Mapping[str, Any],
    trace: Mapping[str, Any],
) -> str:
    value = trace["source_value"]
    if trace["source_kind"] == "transport_leg":
        return value.get("depart_at") or trip["request"]["start_date"]
    if trace["source_kind"] == "lodging":
        return value["check_in"]
    if trace["source_kind"] == "poi":
        windows = value.get("opening_windows") or ()
        dated = sorted(
            window["start_at"] for window in windows
            if isinstance(window.get("start_at"), str)
        )
        return dated[0] if dated else trip["request"]["end_date"]
    if trace["source_kind"] == "day":
        return value["date"]
    return trip["request"]["end_date"]


def _journey_pointer_parts(pointer: str) -> List[str]:
    return [
        part.replace("~1", "/").replace("~0", "~")
        for part in str(pointer).lstrip("/").split("/")
        if part
    ]


def validate_journey(
    journey: Mapping[str, Any],
    schema_path: Optional[Path] = None,
) -> ValidationReport:
    if not isinstance(journey, dict):
        return ValidationReport((ValidationIssue("J_OBJECT", "/", "Journey must be an object"),))
    schema_issues = SchemaSubsetValidator(resolved_journey_schema(schema_path)).validate(journey)
    if schema_issues:
        return ValidationReport(tuple(sorted(set(schema_issues))))

    issues: List[ValidationIssue] = []
    trips = journey["trips"]
    trip_ids = [str(item["trip_id"]) for item in trips]
    if len(trip_ids) != len(set(trip_ids)):
        issues.append(ValidationIssue("J_DUPLICATE_TRIP_ID", "/trips", "Trip ids must be unique within a Journey"))
    for index, trip in enumerate(trips):
        report = validate_trip(trip)
        issues.extend(
            ValidationIssue(
                "J_TRIP_" + item.code,
                _prefixed_path("/trips/%d" % index, item.path),
                item.message,
            )
            for item in report.errors
        )

    if journey["start_date"] != trips[0]["request"]["start_date"]:
        issues.append(ValidationIssue("J_START_DATE", "/start_date", "must equal the first Trip start_date"))
    if journey["end_date"] != trips[-1]["request"]["end_date"]:
        issues.append(ValidationIssue("J_END_DATE", "/end_date", "must equal the final Trip end_date"))

    connections = journey["segment_connections"]
    expected_connection_count = len(trips) - 1
    if len(connections) != expected_connection_count:
        issues.append(ValidationIssue(
            "J_CONNECTION_COUNT", "/segment_connections",
            "must contain exactly one record for every adjacent Trip pair",
        ))
    for index in range(len(trips) - 1):
        left = trips[index]
        right = trips[index + 1]
        left_end = date.fromisoformat(left["request"]["end_date"])
        right_start = date.fromisoformat(right["request"]["start_date"])
        expected_start = left_end + timedelta(days=1)
        if right_start > expected_start:
            issues.append(ValidationIssue(
                "J_DATE_GAP", "/trips/%d/request/start_date" % (index + 1),
                "adjacent Trips leave an uncovered calendar gap",
            ))
        elif right_start < expected_start:
            issues.append(ValidationIssue(
                "J_DATE_OVERLAP", "/trips/%d/request/start_date" % (index + 1),
                "adjacent Trips overlap calendar dates",
            ))
        if index >= len(connections):
            continue
        _validate_connection(connections[index], left, right, index, issues)

    budget_cny = journey["budget_ledger"]["budget_cny"]
    expected_budget = journey_budget_ledger(trips, connections, budget_cny)
    if canonical_json(expected_budget) != canonical_json(journey["budget_ledger"]):
        issues.append(ValidationIssue(
            "J_BUDGET_MISMATCH", "/budget_ledger",
            "must equal the sum of Trip ledgers plus additional cross-segment transport",
        ))
    return ValidationReport(tuple(sorted(set(issues))))


def validate_journey_file(
    path: Path,
    schema_path: Optional[Path] = None,
) -> ValidationReport:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return ValidationReport((ValidationIssue("J_INVALID", "/", str(exc)),))
    if not isinstance(value, dict):
        return ValidationReport((ValidationIssue("J_OBJECT", "/", "Journey must be an object"),))
    return validate_journey(value, schema_path=schema_path)


def _validate_connection(
    connection: Mapping[str, Any],
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    index: int,
    issues: List[ValidationIssue],
) -> None:
    path = "/segment_connections/%d" % index
    expected = {
        "from_trip_id": left["trip_id"],
        "to_trip_id": right["trip_id"],
        "from_end_date": left["request"]["end_date"],
        "to_start_date": right["request"]["start_date"],
    }
    for field, value in expected.items():
        if connection[field] != value:
            issues.append(ValidationIssue(
                "J_CONNECTION_REF", path + "/" + field,
                "does not match its adjacent Trip pair",
            ))
    lodging = connection["lodging_continuity"]
    left_lodgings = {item["lodging_id"]: item for item in left["lodgings"]}
    right_lodgings = {item["lodging_id"]: item for item in right["lodgings"]}
    outgoing = left_lodgings.get(lodging["from_lodging_id"])
    incoming = right_lodgings.get(lodging["to_lodging_id"])
    if outgoing is None:
        issues.append(ValidationIssue(
            "J_LODGING_REF", path + "/lodging_continuity/from_lodging_id",
            "must reference a lodging in the preceding Trip",
        ))
    if lodging["to_lodging_id"] is not None and incoming is None:
        issues.append(ValidationIssue(
            "J_LODGING_REF", path + "/lodging_continuity/to_lodging_id",
            "must reference a lodging in the following Trip",
        ))
    if lodging["overnight_date"] != left["request"]["end_date"]:
        issues.append(ValidationIssue(
            "J_LODGING_DATE", path + "/lodging_continuity/overnight_date",
            "must cover the preceding Trip final date",
        ))
    if outgoing is not None:
        if (
            lodging["overnight_date"] not in outgoing.get("selected_nights", ())
            or outgoing["check_out"] != right["request"]["start_date"]
            or left["days"][-1].get("stay_id") != outgoing["lodging_id"]
        ):
            issues.append(ValidationIssue(
                "J_LODGING_GAP", path + "/lodging_continuity",
                "the preceding stay must cover its final overnight through the next Trip start",
            ))
    next_trip_needs_stay = len(right["days"]) > 1
    if next_trip_needs_stay and (
        incoming is None or right["days"][0].get("stay_id") != incoming["lodging_id"]
    ):
        issues.append(ValidationIssue(
            "J_LODGING_HANDOFF", path + "/lodging_continuity/to_lodging_id",
            "the following multi-day Trip must name its first selected stay",
        ))
    outgoing_ref = (
        outgoing.get("candidate_ref") or outgoing["lodging_id"]
        if outgoing is not None
        else None
    )
    incoming_ref = (
        incoming.get("candidate_ref") or incoming["lodging_id"]
        if incoming is not None
        else None
    )
    if lodging["status"] == "continued" and (
        incoming_ref is None or outgoing_ref != incoming_ref
    ):
        issues.append(ValidationIssue(
            "J_LODGING_STATUS", path + "/lodging_continuity/status",
            "continued requires the same lodging candidate on both sides",
        ))
    if lodging["status"] == "changed" and (
        incoming_ref is None or outgoing_ref == incoming_ref
    ):
        issues.append(ValidationIssue(
            "J_LODGING_STATUS", path + "/lodging_continuity/status",
            "changed requires two different lodging candidates",
        ))
    if lodging["status"] == "departing" and incoming is not None:
        issues.append(ValidationIssue(
            "J_LODGING_STATUS", path + "/lodging_continuity/status",
            "departing is allowed only when the following Trip has no stay",
        ))
    transport = connection["cross_segment_transport"]
    if transport["status"] == "included_in_next_trip":
        if transport["included_in_trip_id"] != right["trip_id"]:
            issues.append(ValidationIssue(
                "J_TRANSPORT_OWNER", path + "/cross_segment_transport/included_in_trip_id",
                "included cross-segment transport must belong to the following Trip",
            ))
        right_leg_ids = {item["leg_id"] for item in right["transport_legs"]}
        if transport["leg_id"] not in right_leg_ids:
            issues.append(ValidationIssue(
                "J_TRANSPORT_REF", path + "/cross_segment_transport/leg_id",
                "must reference a transport leg in the following Trip",
            ))
        right_ledger = right.get("budget_ledger")
        right_items = right_ledger.get("items", ()) if isinstance(right_ledger, Mapping) else ()
        budget_item = next(
            (item for item in right_items if item["ref_id"] == transport["leg_id"]),
            None,
        )
        recorded = (
            transport["price_type"],
            transport["amount_min_cny"],
            transport["amount_max_cny"],
        )
        expected_price = (
            budget_item["price_type"],
            budget_item["amount_min_cny"],
            budget_item["amount_max_cny"],
        ) if budget_item is not None else (None, None, None)
        if recorded != expected_price:
            issues.append(ValidationIssue(
                "J_TRANSPORT_COST", path + "/cross_segment_transport",
                "must preserve the owned Trip ledger range without counting it twice",
            ))
    elif transport["status"] == "not_required" and (
        transport["leg_id"] is not None or transport["included_in_trip_id"] is not None
    ):
        issues.append(ValidationIssue(
            "J_TRANSPORT_NOT_REQUIRED", path + "/cross_segment_transport",
            "a no-transport connection cannot reference a leg or Trip",
        ))
    elif transport["status"] == "separate" and transport["included_in_trip_id"] is not None:
        issues.append(ValidationIssue(
            "J_TRANSPORT_OWNER", path + "/cross_segment_transport/included_in_trip_id",
            "separate transport cannot also be included in a Trip",
        ))


def _prefixed_path(prefix: str, path: str) -> str:
    return prefix if path == "/" else prefix + path


def _sum_if_complete(values: Sequence[Optional[float]]) -> Optional[float]:
    collected = list(values)
    if any(value is None for value in collected):
        return None
    return _money(sum(float(value) for value in collected if value is not None))


def _money(value: float) -> float:
    rounded = round(float(value) + 0.0, 2)
    return int(rounded) if rounded.is_integer() else rounded
