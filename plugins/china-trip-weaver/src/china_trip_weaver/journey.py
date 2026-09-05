"""Multi-Trip Journey model, validation, splitting, and continuity."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
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
    _transport_pricing,
    plan_trip,
)
from .validate_trip import (
    SchemaSubsetValidator,
    ValidationIssue,
    ValidationReport,
    load_schema,
    validate_trip,
)
from .providers.amap_http import (
    AMapBudgetedTransport,
    AMapCallBudget,
    AMapHTTPTransport,
    AMapRequestMemo,
    MAX_CALLS_PER_RUN,
)
from .variflight_enrichment import VariFlightBackend


JOURNEY_SCHEMA_VERSION = "1.0.0"
TRIP_SCHEMA_REFERENCE = "trip.schema.json"
TRIP_DEFINITION_PREFIX = TRIP_SCHEMA_REFERENCE + "#/$defs/"
SEGMENT_ONE_WAY_CONSTRAINT = "单程（Journey 分段不自动返程）"
MAX_TRIP_DAYS = 7


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
    expected_segment_days: Optional[int] = None,
) -> Tuple[JourneySegmentInput, ...]:
    """Split into the fewest Trips, or around an optional preferred length."""

    expected_days = _validate_expected_segment_days(expected_segment_days)
    normalized_request = _normalize_journey_request(request)
    normalized_candidates = _validated_journey_candidates(candidates)
    shared_routes = _shared_journey_routes(normalized_request)
    lodging_city_by_date = _lodging_city_by_date(
        normalized_request,
        normalized_candidates["lodgings"],
    )
    starts = _segment_start_dates(
        normalized_request,
        shared_routes,
        lodging_city_by_date,
        expected_days,
    )
    segment_lengths = _segment_lengths(
        starts,
        date.fromisoformat(normalized_request["end_date"]),
    )
    source_with_assumption = copy.deepcopy(normalized_request)
    assumption = _segmentation_assumption(expected_days, segment_lengths)
    if assumption not in source_with_assumption["assumptions"]:
        source_with_assumption["assumptions"].append(assumption)
    return _segment_inputs_from_starts(
        source_with_assumption,
        normalized_candidates,
        starts,
        lodging_city_by_date,
    )


def _segment_inputs_from_starts(
    normalized_request: Mapping[str, Any],
    normalized_candidates: Mapping[str, Any],
    starts: Sequence[date],
    lodging_city_by_date: Mapping[str, str],
) -> Tuple[JourneySegmentInput, ...]:
    shared_routes = _shared_journey_routes(normalized_request)
    overall_end = date.fromisoformat(normalized_request["end_date"])
    segments: List[JourneySegmentInput] = []
    current_place = _initial_shared_place(normalized_request)
    consumed_routes = 0
    for index, start in enumerate(starts):
        end = starts[index + 1] - timedelta(days=1) if index + 1 < len(starts) else overall_end
        if lodging_city_by_date:
            destinations = _lodging_destinations(
                normalized_request,
                lodging_city_by_date,
                start,
                end,
            )
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
            current_place = destinations[-1]
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
    expected_segment_days: Optional[int] = None,
    amap_total_max_calls: Optional[int] = None,
) -> JourneyPlanResult:
    """Plan lodging-aligned units, merge logical Trips, then assemble a Journey."""

    expected_days = _validate_expected_segment_days(expected_segment_days)
    normalized_source = _normalize_journey_request(request)
    segment_inputs = split_journey_inputs(
        normalized_source,
        candidates,
        expected_segment_days=expected_days,
    )
    amap_segment_limits = _amap_segment_call_limits(
        len(segment_inputs),
        amap_total_max_calls,
    )
    amap_budget_template = _amap_budget_template(
        mobility_backend,
        amap_lodging_backend,
    )
    mobility_memo = AMapRequestMemo()
    lodging_memo = AMapRequestMemo()
    trip_documents: List[Dict[str, Any]] = []
    calls: List[str] = []
    stages: List[Tuple[str, ...]] = []
    for segment_index, segment in enumerate(segment_inputs):
        segment_budget = amap_budget_template.fork(
            amap_segment_limits[segment_index],
        )
        segment_mobility = _scoped_mobility_backend(
            mobility_backend,
            segment_budget,
            mobility_memo,
        )
        segment_amap_lodging = _scoped_amap_lodging_backend(
            amap_lodging_backend,
            segment_budget,
            lodging_memo,
        )
        atomic_inputs = _planning_inputs_for_segment(segment)
        atomic_trips: List[Dict[str, Any]] = []
        segment_stages: List[str] = []
        for atomic in atomic_inputs:
            # This explicit call is the invariant: every planning unit passes the
            # unchanged one-to-seven-day Trip boundary before the planner sees it.
            _normalize_request(atomic.request)
            result = plan_trip(
                atomic.request,
                atomic.candidates,
                clock,
                rail_backend,
                segment_mobility,
                flyai_backend,
                variflight_backend,
                segment_amap_lodging,
            )
            atomic_trips.append(copy.deepcopy(dict(result.trip)))
            calls.extend(result.business_calls)
            segment_stages.extend(result.stages)
        if len(atomic_trips) > 1:
            _bridge_segment_lodgings(atomic_trips, atomic_inputs)
            trip_document = _merge_segment_trips(atomic_trips, segment)
        else:
            trip_document = atomic_trips[0]
        trip_documents.append(trip_document)
        stages.append(tuple(segment_stages))

    lodging_links = _bridge_segment_lodgings(trip_documents, segment_inputs)
    connections = _segment_connections(trip_documents, lodging_links)
    journey = assemble_journey(
        trip_documents,
        normalized_source,
        connections,
        clock,
        expected_segment_days=expected_days,
    )
    digest = hashlib.sha256(canonical_json(journey).encode("utf-8")).hexdigest()
    return JourneyPlanResult(
        journey=journey,
        business_calls=tuple(calls),
        trip_stages=tuple(stages),
        journey_sha256=digest,
    )


def _amap_segment_call_limits(
    segment_count: int,
    total_max_calls: Optional[int],
) -> Tuple[int, ...]:
    if segment_count <= 0:
        raise ValueError("Journey must contain at least one segment")
    if (
        total_max_calls is not None
        and (
            not isinstance(total_max_calls, int)
            or isinstance(total_max_calls, bool)
            or total_max_calls < 0
        )
    ):
        raise ValueError("Journey AMap total max calls must be a non-negative integer")
    journey_default = MAX_CALLS_PER_RUN * segment_count
    available = min(
        journey_default,
        journey_default if total_max_calls is None else total_max_calls,
    )
    base, remainder = divmod(available, segment_count)
    return tuple(
        base + (1 if index < remainder else 0)
        for index in range(segment_count)
    )


def _amap_budget_template(
    mobility_backend: Optional[MobilityBackend],
    lodging_backend: Optional[AMapLodgingBackend],
) -> AMapCallBudget:
    for backend in (mobility_backend, lodging_backend):
        transport = getattr(backend, "transport", None)
        budget = getattr(transport, "budget", None)
        if isinstance(budget, AMapCallBudget):
            return budget
    return AMapCallBudget()


def _scoped_amap_transport(
    transport: Any,
    budget: AMapCallBudget,
    memo: AMapRequestMemo,
) -> Any:
    if transport is None:
        return None
    if isinstance(transport, AMapHTTPTransport):
        return transport.with_budget(budget, memo)
    return AMapBudgetedTransport(transport, budget, memo)


def _scoped_mobility_backend(
    backend: Optional[MobilityBackend],
    budget: AMapCallBudget,
    memo: AMapRequestMemo,
) -> Optional[MobilityBackend]:
    if backend is None or backend.transport is None:
        return backend
    return MobilityBackend(
        backend.mode,
        backend.credentials,
        _scoped_amap_transport(backend.transport, budget, memo),
        deadline_seconds=backend.deadline_seconds,
    )


def _scoped_amap_lodging_backend(
    backend: Optional[AMapLodgingBackend],
    budget: AMapCallBudget,
    memo: AMapRequestMemo,
) -> Optional[AMapLodgingBackend]:
    if backend is None or backend.transport is None:
        return backend
    return AMapLodgingBackend(
        backend.mode,
        backend.credentials,
        _scoped_amap_transport(backend.transport, budget, memo),
        deadline_seconds=backend.deadline_seconds,
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
    expected_segment_days: Optional[int],
) -> Tuple[date, ...]:
    overall_start = date.fromisoformat(request["start_date"])
    overall_end = date.fromisoformat(request["end_date"])
    preferred = _preferred_segment_boundaries(
        overall_start,
        overall_end,
        routes,
        lodging_city_by_date,
    )
    if expected_segment_days is not None:
        return _expected_segment_starts(
            overall_start,
            overall_end,
            preferred,
            expected_segment_days,
        )
    return _minimum_segment_starts(overall_start, overall_end, preferred)


def _preferred_segment_boundaries(
    overall_start: date,
    overall_end: date,
    routes: Sequence[RouteSpec],
    lodging_city_by_date: Mapping[str, str],
) -> Tuple[date, ...]:
    if not lodging_city_by_date:
        return tuple(sorted({
            date.fromisoformat(route.travel_date)
            for route in routes
            if overall_start < date.fromisoformat(route.travel_date) <= overall_end
        }))
    preferred: List[date] = []
    previous_city = lodging_city_by_date[overall_start.isoformat()]
    cursor = overall_start + timedelta(days=1)
    while cursor <= overall_end:
        city = lodging_city_by_date[cursor.isoformat()]
        if city != previous_city:
            preferred.append(cursor)
            previous_city = city
        cursor += timedelta(days=1)
    return tuple(preferred)


def _minimum_segment_starts(
    overall_start: date,
    overall_end: date,
    preferred: Sequence[date],
) -> Tuple[date, ...]:
    """Greedily preserve ceil(days / 7), choosing a lodging change when feasible."""

    end_exclusive = overall_end + timedelta(days=1)
    preferred_set = set(preferred)
    starts = [overall_start]
    cursor = overall_start
    while (end_exclusive - cursor).days > MAX_TRIP_DAYS:
        remaining_days = (end_exclusive - cursor).days
        remaining_segments = (
            remaining_days + MAX_TRIP_DAYS - 1
        ) // MAX_TRIP_DAYS
        earliest = end_exclusive - timedelta(
            days=MAX_TRIP_DAYS * (remaining_segments - 1),
        )
        latest = cursor + timedelta(days=MAX_TRIP_DAYS)
        candidates = [
            boundary for boundary in preferred_set
            if earliest <= boundary <= latest
        ]
        cursor = max(candidates) if candidates else latest
        starts.append(cursor)
    return tuple(starts)


def _expected_segment_starts(
    overall_start: date,
    overall_end: date,
    preferred: Sequence[date],
    expected_segment_days: int,
) -> Tuple[date, ...]:
    """Choose the requested segment count, then favor lodging-aligned cuts."""

    total_days = (overall_end - overall_start).days + 1
    segment_count = (
        total_days + expected_segment_days - 1
    ) // expected_segment_days
    preferred_offsets = {
        (boundary - overall_start).days for boundary in preferred
    }

    @lru_cache(maxsize=None)
    def choose(position: int, remaining_segments: int) -> Tuple[int, Tuple[int, ...]]:
        if remaining_segments == 1:
            length = total_days - position
            if 1 <= length <= MAX_TRIP_DAYS:
                return (0, (length,))
            raise ValueError("expected Journey segmentation has no feasible final Trip")

        best: Optional[Tuple[Tuple[Any, ...], int, Tuple[int, ...]]] = None
        minimum_remaining = remaining_segments - 1
        maximum_remaining = MAX_TRIP_DAYS * minimum_remaining
        for length in range(1, MAX_TRIP_DAYS + 1):
            next_position = position + length
            days_after = total_days - next_position
            if not minimum_remaining <= days_after <= maximum_remaining:
                continue
            suffix_boundaries, suffix_lengths = choose(
                next_position,
                remaining_segments - 1,
            )
            boundary_count = suffix_boundaries + int(
                next_position in preferred_offsets
            )
            lengths = (length,) + suffix_lengths
            score = (
                -boundary_count,
                sum((item - expected_segment_days) ** 2 for item in lengths),
                tuple(abs(item - expected_segment_days) for item in lengths),
                tuple(-item for item in lengths),
            )
            candidate = (score, boundary_count, lengths)
            if best is None or candidate[0] < best[0]:
                best = candidate
        if best is None:
            raise ValueError("expected Journey segmentation has no feasible partition")
        return best[1], best[2]

    _, lengths = choose(0, segment_count)
    starts = [overall_start]
    cursor = overall_start
    for length in lengths[:-1]:
        cursor += timedelta(days=length)
        starts.append(cursor)
    return tuple(starts)


def _strict_segment_start_dates(
    request: Mapping[str, Any],
    routes: Sequence[RouteSpec],
    lodging_city_by_date: Mapping[str, str],
) -> Tuple[date, ...]:
    """Keep city changes hard only for internal lodging-aligned planning units."""

    overall_start = date.fromisoformat(request["start_date"])
    overall_end = date.fromisoformat(request["end_date"])
    preferred = _preferred_segment_boundaries(
        overall_start,
        overall_end,
        routes,
        lodging_city_by_date,
    )
    boundaries = [overall_start] + list(preferred)
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
            cursor += timedelta(days=MAX_TRIP_DAYS)
    return tuple(starts)


def _segment_lengths(
    starts: Sequence[date],
    overall_end: date,
) -> Tuple[int, ...]:
    return tuple(
        (
            (starts[index + 1] if index + 1 < len(starts) else overall_end + timedelta(days=1))
            - start
        ).days
        for index, start in enumerate(starts)
    )


def _validate_expected_segment_days(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_TRIP_DAYS:
        raise ValueError("expected_segment_days must be an integer between one and seven inclusive")
    return value


def _segmentation_assumption(
    expected_segment_days: Optional[int],
    actual_segment_days: Sequence[int],
) -> str:
    actual = ",".join(str(item) for item in actual_segment_days)
    if expected_segment_days is None:
        return (
            "JOURNEY_SEGMENTATION expected_days=none actual_days=%s; "
            "Trip count is minimized under maximum_days=7 and cuts prefer lodging-city changes"
        ) % actual
    return (
        "JOURNEY_SEGMENTATION expected_days=%d actual_days=%s; actual lengths may differ "
        "because whole days are distributed around lodging-city changes while maximum_days=7 remains hard"
    ) % (expected_segment_days, actual)


def _validated_journey_candidates(
    candidates: Mapping[str, Any],
) -> Mapping[str, Any]:
    normalized = json.loads(canonical_json(candidates))
    candidate_report = validate_candidates(normalized)
    if not candidate_report.ok:
        raise ValueError(
            "candidates validation failed: "
            + "; ".join(item.render() for item in candidate_report.errors)
        )
    return normalized


def _planning_inputs_for_segment(
    segment: JourneySegmentInput,
) -> Tuple[JourneySegmentInput, ...]:
    request = _normalize_journey_request(segment.request)
    candidates = _validated_journey_candidates(segment.candidates)
    routes = _shared_journey_routes(request)
    lodging_city_by_date = dict(
        _lodging_city_by_date(request, candidates["lodgings"]),
    )
    final_date = str(request["end_date"])
    final_cities = sorted({
        str(item["city"])
        for item in candidates["lodgings"]
        if item["check_in"] <= final_date < item["check_out"]
    })
    if len(final_cities) > 1:
        raise ValueError("Journey lodging chain has conflicting cities: " + canonical_json({
            "code": "LODGING_CITY_CONFLICT",
            "date": final_date,
            "cities": final_cities,
        }))
    if final_cities and lodging_city_by_date:
        lodging_city_by_date[final_date] = final_cities[0]
    starts = _strict_segment_start_dates(request, routes, lodging_city_by_date)
    return _segment_inputs_from_starts(
        request,
        candidates,
        starts,
        lodging_city_by_date,
    )


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


def _lodging_destinations(
    request: Mapping[str, Any],
    lodging_city_by_date: Mapping[str, str],
    start: date,
    end: date,
) -> List[Mapping[str, str]]:
    """Keep every ordered city run that fits inside one logical Trip."""

    destinations: List[Mapping[str, str]] = []
    previous_city: Optional[str] = None
    cursor = start
    while cursor <= end:
        city = lodging_city_by_date[cursor.isoformat()]
        if city != previous_city:
            destinations.append(_request_place_for_city(request, city))
            previous_city = city
        cursor += timedelta(days=1)
    return destinations


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


def _merge_segment_trips(
    trips: Sequence[Mapping[str, Any]],
    segment: JourneySegmentInput,
) -> Dict[str, Any]:
    """Merge lodging-aligned planning units into one complete logical Trip."""

    if len(trips) < 2:
        return copy.deepcopy(dict(trips[0]))
    parts = [copy.deepcopy(dict(item)) for item in trips]
    request = copy.deepcopy(dict(segment.request))
    for part in parts:
        for assumption in part["request"]["assumptions"]:
            if assumption not in request["assumptions"]:
                request["assumptions"].append(assumption)
    trip_id = "trip-" + hashlib.sha256(canonical_json({
        "request": request,
        "planning_units": [item["trip_id"] for item in parts],
    }).encode("utf-8")).hexdigest()[:16]
    ref_maps: List[Dict[str, str]] = [
        {str(part["trip_id"]): trip_id} for part in parts
    ]

    days: List[Mapping[str, Any]] = []
    day_sources: List[int] = []
    day_index_maps: List[Dict[int, int]] = [dict() for _ in parts]
    used_slot_ids = set()
    for part_index, part in enumerate(parts):
        for old_day_index, source_day in enumerate(part["days"]):
            day_item = copy.deepcopy(dict(source_day))
            new_day_index = len(days)
            day_index_maps[part_index][old_day_index] = new_day_index
            old_day_id = str(day_item["day_id"])
            day_item["day_id"] = "day-%d" % (new_day_index + 1)
            ref_maps[part_index][old_day_id] = day_item["day_id"]
            for slot_index, slot in enumerate(day_item["slots"]):
                old_slot_id = str(slot["slot_id"])
                new_slot_id = old_slot_id
                if new_slot_id in used_slot_ids:
                    new_slot_id = _merged_identifier(
                        "slot", old_slot_id, part_index, slot_index, trip_id,
                    )
                used_slot_ids.add(new_slot_id)
                slot["slot_id"] = new_slot_id
                ref_maps[part_index][old_slot_id] = new_slot_id
            days.append(day_item)
            day_sources.append(part_index)

    group_specs = (
        ("transport_legs", "leg_id", "leg"),
        ("lodgings", "lodging_id", "stay"),
        ("pois", "poi_id", "poi"),
    )
    entity_values: Dict[str, List[Mapping[str, Any]]] = {}
    entity_sources: Dict[str, List[int]] = {}
    entity_index_maps: Dict[str, List[Dict[int, int]]] = {}
    for group, id_key, prefix in group_specs:
        merged_items: List[Mapping[str, Any]] = []
        merged_sources: List[int] = []
        source_indexes: List[Dict[int, int]] = [dict() for _ in parts]
        by_id: Dict[str, int] = {}
        for part_index, part in enumerate(parts):
            for old_index, source_item in enumerate(part[group]):
                item = copy.deepcopy(dict(source_item))
                old_id = str(item[id_key])
                existing_index = by_id.get(old_id)
                if (
                    existing_index is not None
                    and canonical_json(merged_items[existing_index]) == canonical_json(item)
                ):
                    new_id = old_id
                    new_index = existing_index
                else:
                    new_id = old_id
                    if existing_index is not None:
                        new_id = _merged_identifier(
                            prefix, old_id, part_index, old_index, trip_id,
                        )
                        item[id_key] = new_id
                    new_index = len(merged_items)
                    by_id[new_id] = new_index
                    merged_items.append(item)
                    merged_sources.append(part_index)
                source_indexes[part_index][old_index] = new_index
                ref_maps[part_index][old_id] = new_id
        entity_values[group] = merged_items
        entity_sources[group] = merged_sources
        entity_index_maps[group] = source_indexes

    provider_health, provider_index_maps = _merge_provider_health(parts)
    claims: List[Mapping[str, Any]] = []
    claim_maps: List[Dict[str, str]] = [dict() for _ in parts]
    claim_index_maps: List[Dict[int, int]] = [dict() for _ in parts]
    claim_by_id: Dict[str, int] = {}
    for part_index, part in enumerate(parts):
        for old_index, source_claim in enumerate(part["claims"]):
            claim = copy.deepcopy(dict(source_claim))
            old_claim_id = str(claim["claim_id"])
            claim["subject_ref"] = ref_maps[part_index].get(
                str(claim["subject_ref"]),
                str(claim["subject_ref"]),
            )
            existing_index = claim_by_id.get(old_claim_id)
            if (
                existing_index is not None
                and canonical_json(claims[existing_index]) == canonical_json(claim)
            ):
                new_claim_id = old_claim_id
                new_index = existing_index
            else:
                new_claim_id = old_claim_id
                if existing_index is not None:
                    new_claim_id = _merged_identifier(
                        "claim", old_claim_id, part_index, old_index, trip_id,
                    )
                    claim["claim_id"] = new_claim_id
                new_index = len(claims)
                claim_by_id[new_claim_id] = new_index
                claims.append(claim)
            claim_maps[part_index][old_claim_id] = new_claim_id
            claim_index_maps[part_index][old_index] = new_index

    for group, _, _ in group_specs:
        for item, part_index in zip(entity_values[group], entity_sources[group]):
            _rewrite_claim_references(item, claim_maps[part_index])
    for day_item, part_index in zip(days, day_sources):
        lodging_ref = day_item.get("stay_id")
        if isinstance(lodging_ref, str):
            day_item["stay_id"] = ref_maps[part_index].get(lodging_ref, lodging_ref)
        for slot in day_item["slots"]:
            slot_ref = slot.get("ref_id")
            if isinstance(slot_ref, str):
                slot["ref_id"] = ref_maps[part_index].get(slot_ref, slot_ref)
            _rewrite_claim_references(slot, claim_maps[part_index])

    unknowns: List[Mapping[str, Any]] = []
    unknown_keys = set()
    all_index_maps: Dict[str, List[Dict[int, int]]] = dict(entity_index_maps)
    all_index_maps["days"] = day_index_maps
    all_index_maps["claims"] = claim_index_maps
    all_index_maps["provider_health"] = provider_index_maps
    for part_index, part in enumerate(parts):
        for source_unknown in part["unknowns"]:
            field_path = str(source_unknown["field_path"])
            if field_path.startswith(("/budget_ledger/", "/transport_pricing/")):
                continue
            unknown = copy.deepcopy(dict(source_unknown))
            unknown["field_path"] = _rewrite_merged_unknown_path(
                field_path,
                part_index,
                all_index_maps,
            )
            claim_id = unknown.get("claim_id")
            if isinstance(claim_id, str):
                unknown["claim_id"] = claim_maps[part_index].get(claim_id, claim_id)
            encoded = canonical_json(unknown)
            if encoded not in unknown_keys:
                unknowns.append(unknown)
                unknown_keys.add(encoded)

    mode_rank = {"live": 0, "cached": 1, "static": 2, "mock": 3}
    mode = max((str(item["mode"]) for item in parts), key=lambda item: mode_rank[item])
    merged: Dict[str, Any] = {
        "schema_version": str(parts[0]["schema_version"]),
        "trip_id": trip_id,
        "revision": {
            "number": 1,
            "parent_revision": None,
            "created_at": str(parts[0]["revision"]["created_at"]),
            "reason": "initial lodging-aligned Journey segment plan",
            "created_by": "system",
        },
        "mode": mode,
        "request": request,
        "days": days,
        "transport_legs": entity_values["transport_legs"],
        "lodgings": entity_values["lodgings"],
        "pois": entity_values["pois"],
        "claims": claims,
        "provider_health": provider_health,
        "unknowns": unknowns,
        "patches": [],
        "generated_at": max(str(item["generated_at"]) for item in parts),
    }
    if mode == "mock":
        notices = [str(item["mock_notice"]) for item in parts if item.get("mock_notice")]
        merged["mock_notice"] = "; ".join(dict.fromkeys(notices)) or "merged mock planning units"
    if request.get("traveler_groups"):
        group_refs = [str(item["group_id"]) for item in request["traveler_groups"]]
        for leg in merged["transport_legs"]:
            if not leg.get("group_refs"):
                leg["group_refs"] = list(group_refs)
        merged["transport_pricing"] = _transport_pricing(
            request,
            merged["days"],
            merged["transport_legs"],
        )
    ledger, budget_unknowns = _budget_ledger(
        request,
        merged["days"],
        merged["transport_legs"],
        merged["lodgings"],
        merged["pois"],
        merged["claims"],
    )
    merged["budget_ledger"] = ledger
    merged["unknowns"].extend(budget_unknowns)
    report = validate_trip(merged)
    if not report.ok:
        raise ValueError(
            "merged Journey segment produced an invalid Trip: "
            + "; ".join(item.render() for item in report.errors)
        )
    return merged


def _merged_identifier(
    prefix: str,
    original: str,
    part_index: int,
    item_index: int,
    trip_id: str,
) -> str:
    digest = hashlib.sha256(canonical_json({
        "original": original,
        "part_index": part_index,
        "item_index": item_index,
        "trip_id": trip_id,
    }).encode("utf-8")).hexdigest()[:16]
    return "%s-merged-%s" % (prefix, digest)


def _rewrite_claim_references(
    item: Dict[str, Any],
    claim_map: Mapping[str, str],
) -> None:
    if isinstance(item.get("claim_ids"), list):
        item["claim_ids"] = [
            claim_map.get(str(claim_id), str(claim_id))
            for claim_id in item["claim_ids"]
        ]
    price = item.get("price")
    if isinstance(price, dict) and isinstance(price.get("claim_id"), str):
        price["claim_id"] = claim_map.get(price["claim_id"], price["claim_id"])
    for window in item.get("opening_windows", ()):
        if isinstance(window, dict) and isinstance(window.get("claim_id"), str):
            window["claim_id"] = claim_map.get(window["claim_id"], window["claim_id"])


def _merge_provider_health(
    parts: Sequence[Mapping[str, Any]],
) -> Tuple[List[Mapping[str, Any]], List[Dict[int, int]]]:
    status_rank = {
        "ready": 0,
        "degraded": 1,
        "missing": 2,
        "expired": 3,
        "rate_limited": 4,
        "unavailable": 5,
        "forbidden": 6,
        "contract_mismatch": 7,
    }
    mode_rank = {"live": 0, "cached": 1, "static": 2, "mock": 3}
    merged: List[Mapping[str, Any]] = []
    by_provider: Dict[str, int] = {}
    reason_part_indexes: Dict[str, Dict[str, set]] = {}
    index_maps: List[Dict[int, int]] = [dict() for _ in parts]
    for part_index, part in enumerate(parts):
        for old_index, source in enumerate(part["provider_health"]):
            provider = str(source["provider"])
            reason = str(source["reason"])
            new_index = by_provider.get(provider)
            if new_index is None:
                new_index = len(merged)
                by_provider[provider] = new_index
                reason_part_indexes[provider] = {reason: {part_index}}
                merged.append(copy.deepcopy(dict(source)))
            else:
                current = merged[new_index]
                selected = max(
                    (current, source),
                    key=lambda item: status_rank[str(item["status"])],
                )
                combined = copy.deepcopy(dict(selected))
                combined["mode"] = max(
                    (str(current["mode"]), str(source["mode"])),
                    key=lambda item: mode_rank[item],
                )
                combined["checked_at"] = max(
                    str(current["checked_at"]),
                    str(source["checked_at"]),
                )
                combined["capabilities"] = list(dict.fromkeys(
                    list(current["capabilities"]) + list(source["capabilities"])
                ))
                provider_reason_parts = reason_part_indexes[provider]
                provider_reason_parts.setdefault(reason, set()).add(part_index)
                combined["reason"] = "; ".join(
                    "%s ×%d" % (value, len(part_indexes))
                    if len(part_indexes) > 1 else value
                    for value, part_indexes in provider_reason_parts.items()
                )
                merged[new_index] = combined
            index_maps[part_index][old_index] = new_index
    return merged, index_maps


def _rewrite_merged_unknown_path(
    field_path: str,
    part_index: int,
    index_maps: Mapping[str, Sequence[Mapping[int, int]]],
) -> str:
    parts = field_path.split("/")
    if len(parts) < 3 or parts[0] != "" or not parts[2].isdigit():
        return field_path
    group = parts[1]
    if group not in index_maps:
        return field_path
    old_index = int(parts[2])
    source_map = index_maps[group][part_index]
    if old_index not in source_map:
        raise ValueError("merged Journey unknown references a missing source index: %s" % field_path)
    parts[2] = str(source_map[old_index])
    return "/".join(parts)


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
    expected_segment_days: Optional[int] = None,
) -> Mapping[str, Any]:
    """Wrap complete standalone Trip documents in one validated Journey."""

    if not trips:
        raise ValueError("Journey requires at least one complete Trip")
    trip_documents = copy.deepcopy(list(trips))
    connections = copy.deepcopy(list(segment_connections))
    expected_days = _validate_expected_segment_days(expected_segment_days)
    start_date = str(trip_documents[0]["request"]["start_date"])
    end_date = str(trip_documents[-1]["request"]["end_date"])
    actual_segment_days = tuple(len(item["days"]) for item in trip_documents)
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
        "segmentation": {
            "expected_segment_days": expected_days,
            "actual_segment_days": list(actual_segment_days),
        },
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
        "segmentation": {
            "expected_segment_days": expected_days,
            "maximum_segment_days": MAX_TRIP_DAYS,
            "actual_segment_days": list(actual_segment_days),
            "strategy": "expected_length" if expected_days is not None else "minimum_segments",
            "assumptions": [
                _segmentation_assumption(expected_days, actual_segment_days),
            ],
        },
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

    segmentation = journey.get("segmentation")
    if isinstance(segmentation, Mapping):
        actual_segment_days = [len(item["days"]) for item in trips]
        if segmentation["actual_segment_days"] != actual_segment_days:
            issues.append(ValidationIssue(
                "J_SEGMENT_LENGTHS",
                "/segmentation/actual_segment_days",
                "must equal the actual number of days in every embedded Trip",
            ))
        expected_strategy = (
            "expected_length"
            if segmentation["expected_segment_days"] is not None
            else "minimum_segments"
        )
        if segmentation["strategy"] != expected_strategy:
            issues.append(ValidationIssue(
                "J_SEGMENT_STRATEGY",
                "/segmentation/strategy",
                "must match whether an expected segment length was supplied",
            ))

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
