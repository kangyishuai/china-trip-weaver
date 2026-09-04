"""Candidate-file driven P0-P6 planning with truthful rail degradation."""

from __future__ import annotations

import copy
import hashlib
import json
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .candidates import validate_candidates
from .clock import Clock, isoformat_seconds
from .contracts import AdapterResult, ProviderRequest, canonical_json
from .credentials import SUPPORTED_KEY_NAMES, resolve_credentials
from .evidence import make_claim
from .flyai_inventory import AMapLodgingBackend, FlyAIBackend
from .matrix import haversine_meters, static_estimate_cell
from .mobility import MobilityBackend, MobilityResult, apply_locations
from .pipeline import PipelineRun
from .providers.base import ProviderContext, ReplayTransport, stable_id
from .providers.mcp_stdio import RailMCPStdioTransport
from .providers.rail12306 import Rail12306Adapter
from .render import render_trip, validate_html
from .scheduler.light import LightScheduler
from .validate_trip import SchemaSubsetValidator, load_schema, validate_trip
from .variflight_enrichment import VariFlightBackend


@dataclass(frozen=True)
class PlanResult:
    trip: Mapping[str, Any]
    html: str
    business_calls: Tuple[str, ...]
    stages: Tuple[str, ...]
    trip_sha256: str
    html_sha256: str


@dataclass(frozen=True)
class RouteSpec:
    from_place: Mapping[str, str]
    to_place: Mapping[str, str]
    travel_date: str
    return_leg: bool = False


@dataclass(frozen=True)
class RailBackend:
    mode: str
    repo_root: Path
    fixture: Optional[Mapping[str, Any]] = None
    deadline_seconds: float = 90.0
    limit: int = 10

    @classmethod
    def from_spec(cls, spec: str, repo_root: Path, deadline_seconds: float = 90.0) -> "RailBackend":
        if spec == "live":
            return cls("live", Path(repo_root), deadline_seconds=deadline_seconds)
        if spec == "off":
            return cls("off", Path(repo_root), deadline_seconds=deadline_seconds)
        if spec.startswith("fixture:"):
            fixture_path = Path(spec[len("fixture:"):])
            with fixture_path.open("r", encoding="utf-8") as handle:
                fixture = json.load(handle)
            if not isinstance(fixture, dict) or fixture.get("provider") != "rail12306" or not isinstance(fixture.get("transport"), dict):
                raise ValueError("rail fixture must be a rail12306 provider fixture")
            return cls("fixture", Path(repo_root), fixture=fixture, deadline_seconds=deadline_seconds)
        raise ValueError("--rail must be live, off, or fixture:<file>")

    def query(self, route: RouteSpec, clock: Clock) -> Optional[AdapterResult]:
        if self.mode == "off":
            return None
        parameters = {
            "date": route.travel_date,
            "from_name": route.from_place["name"],
            "to_name": route.to_place["name"],
            "from_ref": route.from_place["ref_id"],
            "to_ref": route.to_place["ref_id"],
            "train_filter_flags": "GD",
            "limited_num": self.limit,
            "earliest_start_time": 15 if route.return_leg else 7,
            "latest_start_time": 21,
        }
        request = ProviderRequest(
            request_id=stable_id("plan-rail", route.travel_date, route.from_place["ref_id"], route.to_place["ref_id"]),
            capability="rail",
            parameters=parameters,
            deadline_ms=int(self.deadline_seconds * 1000),
            as_of=route.travel_date,
            cache_policy="bypass",
            trace={"stage": "plan-rail"},
        )
        if self.mode == "fixture":
            assert self.fixture is not None
            transport = ReplayTransport(self.fixture["transport"], raw_ref="plan-rail-fixture")
        else:
            credentials = resolve_credentials({}, self.repo_root / ".tmp" / "plan-no-credentials")
            transport = RailMCPStdioTransport(
                cache_dir=self.repo_root / ".npm-cache",
                credentials=credentials,
                cwd=self.repo_root,
            )
        context = ProviderContext(
            clock=clock,
            credentials=resolve_credentials({}, self.repo_root / ".tmp" / "plan-no-credentials"),
            transport=transport,
        )
        return Rail12306Adapter().query(request, context)


def plan_trip(
    request: Mapping[str, Any],
    candidates: Mapping[str, Any],
    clock: Clock,
    rail_backend: RailBackend,
    mobility_backend: Optional[MobilityBackend] = None,
    flyai_backend: Optional[FlyAIBackend] = None,
    variflight_backend: Optional[VariFlightBackend] = None,
    amap_lodging_backend: Optional[AMapLodgingBackend] = None,
) -> PlanResult:
    normalized_request = _normalize_request(request)
    normalized_candidates = _normalize_candidates(candidates, normalized_request)
    trip_id = "trip-" + hashlib.sha256(
        canonical_json({"request": normalized_request, "candidates": normalized_candidates}).encode("utf-8")
    ).hexdigest()[:16]
    run = PipelineRun({
        "request": normalized_request,
        "candidates_sha256": hashlib.sha256(canonical_json(normalized_candidates).encode("utf-8")).hexdigest(),
    })
    run.advance("INTAKE", {"request": normalized_request}, trip_id, 1)
    run.advance(
        "RESEARCHED",
        {
            "candidate_claims": len(normalized_candidates["claims"]),
            "source": "candidates-file",
        },
        trip_id,
        1,
        {"candidate-schema": "1.0.0"},
    )

    now = isoformat_seconds(clock)
    claims = copy.deepcopy(normalized_candidates["claims"])
    pois = copy.deepcopy(normalized_candidates["pois"])
    lodging_candidates = copy.deepcopy(normalized_candidates["lodgings"])
    routes = _route_specs(normalized_request)
    transport_legs, rail_claims, rail_unknowns, rail_health, business_calls = _resolve_rail(
        routes, clock, rail_backend
    )
    claims.extend(rail_claims)
    active_flyai = flyai_backend or FlyAIBackend.from_spec("off", rail_backend.repo_root)
    inventory = active_flyai.resolve(normalized_request, routes, clock)
    amap_lodging = None
    if not inventory.lodgings and active_flyai.mode == "live":
        active_amap_lodging = amap_lodging_backend or AMapLodgingBackend.from_spec(
            "off", rail_backend.repo_root,
        )
        amap_lodging = active_amap_lodging.resolve(normalized_request, clock)
    fallback_lodgings = amap_lodging.lodgings if amap_lodging is not None else ()
    lodging_candidates, lodging_unknowns = _merge_lodging_candidates(
        lodging_candidates,
        normalized_candidates["unknowns"],
        inventory.lodgings,
        inventory.unknowns,
        fallback_lodgings,
        amap_lodging.unknowns if amap_lodging is not None else (),
    )
    active_variflight = variflight_backend or VariFlightBackend.from_spec("off", rail_backend.repo_root)
    enrichment = active_variflight.enrich(inventory.flights, routes, clock)
    transport_legs.extend(copy.deepcopy(list(enrichment.flights)))
    claims.extend(copy.deepcopy(list(inventory.claims)))
    if amap_lodging is not None:
        claims.extend(copy.deepcopy(list(amap_lodging.claims)))
    claims.extend(copy.deepcopy(list(enrichment.claims)))
    run.advance(
        "CANDIDATES_READY",
        {
            "pois": len(pois),
            "lodgings": len(lodging_candidates),
            "rail_routes": len(routes),
            "rail_legs": len([item for item in transport_legs if item["travel_mode"] == "rail"]),
            "flight_comparisons": len(enrichment.flights),
        },
        trip_id,
        1,
        {"12306-mcp": "0.3.10", "candidate-schema": "1.0.0"},
    )

    active_mobility = mobility_backend or MobilityBackend.from_spec("off", rail_backend.repo_root)
    mobility = active_mobility.resolve(normalized_candidates, clock, ("transit",))
    pois, lodging_candidates = apply_locations(pois, lodging_candidates, mobility)
    current_location_refs = {
        item["poi_id"] for item in pois
    } | {
        item["lodging_id"] for item in lodging_candidates
    }
    location_claim_ids = {
        claim_id
        for location in mobility.locations if location.ref_id in current_location_refs
        for claim_id in location.claim_ids
    }
    claims.extend(copy.deepcopy([
        claim for claim in mobility.claims if claim["claim_id"] in location_claim_ids
    ]))
    lodgings, claims, stay_selections = _select_stays(
        normalized_request, transport_legs, lodging_candidates, claims,
    )
    problems, matrix_cells, live_matrix_cells = _schedule_problems(
        normalized_request, transport_legs, lodgings, pois, mobility,
    )
    matrix_stage = "MATRIX_READY" if active_mobility.mode == "live" and live_matrix_cells else "MATRIX_DEGRADED"
    run.advance(
        matrix_stage,
        {
            "cell_count": matrix_cells,
            "live_cell_count": live_matrix_cells,
            "mode": "live" if live_matrix_cells else "static",
            "reason": mobility.health["reason"],
        },
        trip_id,
        1,
        {"amap": "web-service-v5-v3-route", "matrix": "ctw-route-matrix/1"},
    )
    scheduled = LightScheduler().schedule_plan(problems)
    if scheduled["status"] != "SCHEDULED":
        conflict = scheduled.get("conflict") or {}
        raise ValueError("plan has no feasible schedule: %s" % conflict.get("code", "unknown"))
    run.advance(
        "SCHEDULED",
        {"slot_counts": [len(day["slots"]) for day in scheduled["days"]]},
        trip_id,
        1,
    )

    entities = {
        "transport_legs": transport_legs,
        "lodgings": lodgings,
        "pois": pois,
    }
    days = _trip_days(normalized_request, scheduled, entities)
    unknowns = _selected_candidate_unknowns(lodging_unknowns, stay_selections)
    unknowns.extend(rail_unknowns)
    trip = {
        "schema_version": "1.0.0",
        "trip_id": trip_id,
        "revision": {
            "number": 1,
            "parent_revision": None,
            "created_at": now,
            "reason": "initial candidate-file plan",
            "created_by": "system",
        },
        "mode": "static",
        "request": normalized_request,
        "days": days,
        "transport_legs": transport_legs,
        "lodgings": lodgings,
        "pois": pois,
        "claims": claims,
        "provider_health": _provider_health(
            now,
            rail_health,
            inventory.health,
            _combined_amap_health(
                mobility.health,
                amap_lodging.health if amap_lodging is not None else None,
            ),
            enrichment.health,
        ),
        "unknowns": unknowns,
        "patches": [],
        "generated_at": now,
    }
    report = validate_trip(trip)
    if not report.ok:
        raise ValueError("Trip validation failed: " + "; ".join(item.render() for item in report.errors))
    run.advance("VALIDATED", {"errors": 0, "schema_version": "1.0.0"}, trip_id, 1)

    html = render_trip(trip)
    html_report = validate_html(html, trip)
    if not html_report.ok:
        raise ValueError("HTML validation failed: " + "; ".join(item.render() for item in html_report.errors))
    html_digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    run.advance("RENDERED", {"errors": 0, "html_sha256": html_digest}, trip_id, 1)
    return PlanResult(
        trip=trip,
        html=html,
        business_calls=(
            tuple(business_calls) + mobility.business_calls
            + inventory.business_calls
            + (amap_lodging.business_calls if amap_lodging is not None else ())
            + enrichment.business_calls
        ),
        stages=tuple(item.stage for item in run.checkpoints()),
        trip_sha256=hashlib.sha256(canonical_json(trip).encode("utf-8")).hexdigest(),
        html_sha256=html_digest,
    )


def _normalize_request(value: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = json.loads(canonical_json(value))
    issues = SchemaSubsetValidator(load_schema()).validate_fragment("#/$defs/request", normalized)
    if issues:
        raise ValueError("request validation failed: " + "; ".join(item.render() for item in issues))
    start = date.fromisoformat(normalized["start_date"])
    end = date.fromisoformat(normalized["end_date"])
    day_count = (end - start).days + 1
    if day_count < 1 or day_count > 7:
        raise ValueError("request must cover between one and seven inclusive days")
    if len(normalized["destinations"]) > 1 and normalized["origin"] is None:
        raise ValueError("multi-city planning requires an origin")
    return normalized


def _normalize_candidates(value: Mapping[str, Any], request: Mapping[str, Any]) -> Dict[str, Any]:
    normalized = json.loads(canonical_json(value))
    report = validate_candidates(normalized)
    if not report.ok:
        raise ValueError("candidates validation failed: " + "; ".join(item.render() for item in report.errors))
    destination_cities = {item["city"] for item in request["destinations"]}
    for group in ("pois", "lodgings"):
        for item in normalized[group]:
            if item["city"] not in destination_cities:
                raise ValueError("candidate city is outside the request destination")
    return normalized


def _route_specs(request: Mapping[str, Any]) -> Tuple[RouteSpec, ...]:
    origin = request["origin"]
    destinations = list(request["destinations"])
    destination = destinations[0]
    if origin is None:
        return ()
    text = " ".join(request.get("constraints", ()) + request.get("assumptions", ())).lower()
    pasted_notes = request.get("pasted_notes")
    if isinstance(pasted_notes, str):
        text = "%s %s" % (text, pasted_notes.lower())
    one_way = "单程" in text or "one-way" in text or "one way" in text
    explicit_round_trip = "往返" in text or "round-trip" in text or "round trip" in text or "day trip" in text
    negated_round_trip = any(phrase in text for phrase in (
        "不往返", "不需要往返", "无需往返", "不要往返", "非往返",
        "no round trip", "not a round trip", "not round trip", "do not return",
    ))

    # Preserve the established single-destination behavior: a multi-day trip
    # returns on the final date unless the request explicitly says one-way.
    if len(destinations) == 1:
        if origin["ref_id"] == destination["ref_id"]:
            return ()
        routes = [RouteSpec(origin, destination, request["start_date"], False)]
        if not one_way and (request["end_date"] != request["start_date"] or explicit_round_trip):
            routes.append(RouteSpec(destination, origin, request["end_date"], True))
        return tuple(routes)

    places = [origin] + destinations
    transitions = [
        (from_place, to_place)
        for from_place, to_place in zip(places, places[1:])
        if from_place["ref_id"] != to_place["ref_id"]
    ]
    last_is_origin = destinations[-1]["ref_id"] == origin["ref_id"]
    add_return = explicit_round_trip and not negated_round_trip and not one_way and not last_is_origin
    travel_dates = _distributed_route_dates(
        request["start_date"], request["end_date"], len(transitions), add_return,
    )
    routes = [
        RouteSpec(
            from_place,
            to_place,
            travel_date,
            to_place["ref_id"] == origin["ref_id"],
        )
        for (from_place, to_place), travel_date in zip(transitions, travel_dates)
    ]
    if add_return:
        routes.append(RouteSpec(destinations[-1], origin, request["end_date"], True))
    return tuple(routes)


def _distributed_route_dates(
    start_value: str,
    end_value: str,
    route_count: int,
    reserve_final_day_for_return: bool,
) -> Tuple[str, ...]:
    if route_count == 0:
        return ()
    start = date.fromisoformat(start_value)
    end = date.fromisoformat(end_value)
    day_count = (end - start).days + 1
    usable_days = day_count - (1 if reserve_final_day_for_return and day_count > 1 else 0)
    usable_days = max(1, usable_days)
    return tuple(
        (start + timedelta(days=min(usable_days - 1, (index * usable_days) // route_count))).isoformat()
        for index in range(route_count)
    )


def _trip_dates(request: Mapping[str, Any]) -> Tuple[str, ...]:
    start = date.fromisoformat(request["start_date"])
    end = date.fromisoformat(request["end_date"])
    return tuple(
        (start + timedelta(days=index)).isoformat()
        for index in range((end - start).days + 1)
    )


def _day_city_by_date(
    request: Mapping[str, Any],
    legs: Sequence[Mapping[str, Any]],
) -> Mapping[str, str]:
    dates = _trip_dates(request)
    destinations = list(request["destinations"])
    # A compatibility exception keeps established single-destination Trip output
    # stable even when its legacy implicit return leg occurs on the final day.
    if len(destinations) == 1:
        return {travel_date: destinations[0]["city"] for travel_date in dates}

    places = list(destinations)
    if request["origin"] is not None:
        places.append(request["origin"])
    cities = {place["ref_id"]: place["city"] for place in places}
    current_city = request["origin"]["city"] if request["origin"] is not None else destinations[0]["city"]
    arrivals: Dict[str, List[Mapping[str, Any]]] = {travel_date: [] for travel_date in dates}
    for leg in legs:
        depart_at = leg.get("depart_at")
        if leg.get("travel_mode") == "flight" or not isinstance(depart_at, str):
            continue
        travel_date = depart_at[:10]
        if travel_date in arrivals and leg.get("to_ref") in cities:
            arrivals[travel_date].append(leg)

    result: Dict[str, str] = {}
    for travel_date in dates:
        for leg in sorted(
            arrivals[travel_date],
            key=lambda item: (item["depart_at"], item.get("arrive_at") or ""),
        ):
            current_city = cities[leg["to_ref"]]
        result[travel_date] = current_city
    return result


def _merge_lodging_candidates(
    researched: Sequence[Mapping[str, Any]],
    researched_unknowns: Sequence[Mapping[str, Any]],
    flyai: Sequence[Mapping[str, Any]],
    flyai_unknowns: Sequence[Mapping[str, Any]],
    amap: Sequence[Mapping[str, Any]],
    amap_unknowns: Sequence[Mapping[str, Any]],
) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]]]:
    """Merge sources while keeping locked research ahead of live alternatives."""

    researched_items = copy.deepcopy(list(researched))
    flyai_items = copy.deepcopy(list(flyai))
    amap_items = copy.deepcopy(list(amap))
    locked = [item for item in researched_items if item.get("locked")]
    unlocked = [item for item in researched_items if not item.get("locked")]
    merged = []
    seen_ids = set()
    for item in locked + flyai_items + amap_items + unlocked:
        lodging_id = item["lodging_id"]
        if lodging_id in seen_ids:
            continue
        seen_ids.add(lodging_id)
        merged.append(item)
    identifiers = [item["lodging_id"] for item in merged]
    target_indices = {identifier: index for index, identifier in enumerate(identifiers)}

    unknowns = _reindex_lodging_unknowns(
        researched_unknowns, researched_items, target_indices, include_non_lodging=True,
    )
    unknowns.extend(_reindex_lodging_unknowns(
        flyai_unknowns, flyai_items, target_indices, include_non_lodging=False,
    ))
    unknowns.extend(_reindex_lodging_unknowns(
        amap_unknowns, amap_items, target_indices, include_non_lodging=False,
    ))
    return merged, unknowns


def _reindex_lodging_unknowns(
    unknowns: Sequence[Mapping[str, Any]],
    source_candidates: Sequence[Mapping[str, Any]],
    target_indices: Mapping[str, int],
    *,
    include_non_lodging: bool,
) -> List[Mapping[str, Any]]:
    result: List[Mapping[str, Any]] = []
    for unknown in unknowns:
        path = unknown["field_path"]
        if not path.startswith("/lodgings/"):
            if include_non_lodging:
                result.append(copy.deepcopy(unknown))
            continue
        parts = path.split("/", 3)
        if len(parts) != 4 or not parts[2].isdigit():
            raise ValueError("lodging unknown has an invalid candidate path")
        source_index = int(parts[2])
        if source_index >= len(source_candidates):
            raise ValueError("lodging unknown references a missing candidate")
        lodging_id = source_candidates[source_index]["lodging_id"]
        if lodging_id not in target_indices:
            raise ValueError("lodging unknown candidate was lost during merge")
        selected = copy.deepcopy(unknown)
        selected["field_path"] = "/lodgings/%d/%s" % (
            target_indices[lodging_id], parts[3],
        )
        result.append(selected)
    return result


def _select_stays(
    request: Mapping[str, Any],
    legs: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    claims: Sequence[Mapping[str, Any]],
) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]], List[Mapping[str, Any]]]:
    dates = _trip_dates(request)
    cities = _day_city_by_date(request, legs)
    required_nights = [(travel_date, cities[travel_date]) for travel_date in dates[:-1]]
    candidate_list = list(candidates)
    segments: List[Mapping[str, Any]] = []
    position = 0
    while position < len(required_nights):
        night, city = required_nights[position]
        eligible = []
        for candidate_index, candidate in enumerate(candidate_list):
            if candidate["city"] != city or not (candidate["check_in"] <= night < candidate["check_out"]):
                continue
            coverage = 0
            for later_night, later_city in required_nights[position:]:
                if later_city != city or not (candidate["check_in"] <= later_night < candidate["check_out"]):
                    break
                coverage += 1
            eligible.append((not bool(candidate.get("locked")), -coverage, candidate_index, coverage))
        if not eligible:
            conflict = {"code": "NO_STAY_FOR_NIGHT", "date": night, "city": city}
            raise ValueError("plan has no feasible stay: " + canonical_json(conflict))
        _, _, candidate_index, coverage = min(eligible)
        selected_nights = [item[0] for item in required_nights[position:position + coverage]]
        segments.append({
            "candidate_index": candidate_index,
            "selected_nights": selected_nights,
            "check_in": selected_nights[0],
            "check_out": (date.fromisoformat(selected_nights[-1]) + timedelta(days=1)).isoformat(),
        })
        position += coverage

    occurrences: Dict[int, int] = {}
    candidate_ids = {candidate["lodging_id"] for candidate in candidate_list}
    identity_subjects = set()
    selections: List[Mapping[str, Any]] = []
    stays: List[Mapping[str, Any]] = []
    claim_by_id = {claim["claim_id"]: claim for claim in claims}
    cloned_claims: List[Mapping[str, Any]] = []

    for stay_index, segment in enumerate(segments):
        candidate_index = int(segment["candidate_index"])
        candidate = candidate_list[candidate_index]
        source_id = candidate["lodging_id"]
        occurrence = occurrences.get(candidate_index, 0)
        occurrences[candidate_index] = occurrence + 1
        stay_id = source_id if occurrence == 0 else stable_id(
            "stay-selection", source_id, segment["check_in"], segment["check_out"],
        )
        stay = copy.deepcopy(candidate)
        stay["lodging_id"] = stay_id
        stay["check_in"] = segment["check_in"]
        stay["check_out"] = segment["check_out"]
        stay["candidate_ref"] = source_id
        stay["selection_status"] = "selected"
        stay["selected_nights"] = list(segment["selected_nights"])
        referenced_claim_ids = list(stay["claim_ids"])
        price = stay.get("price")
        if price and price.get("claim_id") is not None and price["claim_id"] not in referenced_claim_ids:
            referenced_claim_ids.append(price["claim_id"])
        claim_id_map: Dict[str, str] = {}
        if stay_id == source_id:
            identity_subjects.add(source_id)
            claim_id_map.update((claim_id, claim_id) for claim_id in referenced_claim_ids)
        else:
            for claim_id in referenced_claim_ids:
                source_claim = claim_by_id.get(claim_id)
                if source_claim is None:
                    raise ValueError("selected stay references a missing claim: %s" % claim_id)
                cloned_id = stable_id("claim-stay-selection", claim_id, stay_id)
                cloned = copy.deepcopy(source_claim)
                cloned["claim_id"] = cloned_id
                cloned["subject_ref"] = stay_id
                cloned_claims.append(cloned)
                claim_id_map[claim_id] = cloned_id
            stay["claim_ids"] = [claim_id_map[claim_id] for claim_id in stay["claim_ids"]]
            if price and price.get("claim_id") is not None:
                price["claim_id"] = claim_id_map[price["claim_id"]]
        stays.append(stay)
        selections.append({
            "source_index": candidate_index,
            "stay_index": stay_index,
            "claim_id_map": claim_id_map,
        })

    selected_claims = [
        copy.deepcopy(claim) for claim in claims
        if claim["subject_ref"] not in candidate_ids or claim["subject_ref"] in identity_subjects
    ]
    selected_claims.extend(cloned_claims)
    return stays, selected_claims, selections


def _selected_candidate_unknowns(
    unknowns: Sequence[Mapping[str, Any]],
    selections: Sequence[Mapping[str, Any]],
) -> List[Mapping[str, Any]]:
    result: List[Mapping[str, Any]] = []
    by_source: Dict[int, List[Mapping[str, Any]]] = {}
    for selection in selections:
        by_source.setdefault(int(selection["source_index"]), []).append(selection)
    for unknown in unknowns:
        path = unknown["field_path"]
        if not path.startswith("/lodgings/"):
            result.append(copy.deepcopy(unknown))
            continue
        parts = path.split("/", 3)
        if len(parts) != 4 or not parts[2].isdigit():
            continue
        source_index = int(parts[2])
        for selection in by_source.get(source_index, ()):
            selected = copy.deepcopy(unknown)
            selected["field_path"] = "/lodgings/%d/%s" % (selection["stay_index"], parts[3])
            claim_id = selected.get("claim_id")
            if claim_id is not None:
                selected["claim_id"] = selection["claim_id_map"].get(claim_id, claim_id)
            result.append(selected)
    return result


def _resolve_rail(
    routes: Sequence[RouteSpec],
    clock: Clock,
    backend: RailBackend,
) -> Tuple[List[Mapping[str, Any]], List[Mapping[str, Any]], List[Mapping[str, Any]], Mapping[str, Any], Tuple[str, ...]]:
    legs: List[Mapping[str, Any]] = []
    claims: List[Mapping[str, Any]] = []
    unknowns: List[Mapping[str, Any]] = []
    calls: List[str] = []
    errors: List[str] = []
    live_count = 0

    for route in routes:
        result = backend.query(route, clock)
        if result is not None:
            calls.append("rail12306.%s:%s:%s:%s" % (
                backend.mode,
                route.travel_date,
                route.from_place["name"],
                route.to_place["name"],
            ))
        selected: Optional[Mapping[str, Any]] = None
        selected_claims: Sequence[Mapping[str, Any]] = ()
        if result is not None and result.normalized_items:
            candidates = [
                item for item in result.normalized_items
                if isinstance(item.get("depart_at"), str) and item["depart_at"][:10] == route.travel_date
            ]
            if candidates:
                selected = min(
                    candidates,
                    key=(lambda item: (item["depart_at"], item["arrive_at"])) if route.return_leg
                    else (lambda item: (item["arrive_at"], item["depart_at"])),
                )
                selected_ids = set(selected["claim_ids"])
                selected_claims = [claim for claim in result.claims if claim["claim_id"] in selected_ids]
                if len(selected_claims) != len(selected_ids):
                    selected = None
                    errors.append("selected rail leg has incomplete claims")
        if selected is not None:
            legs.append(copy.deepcopy(selected))
            claims.extend(copy.deepcopy(list(selected_claims)))
            live_count += 1
            continue
        if result is not None:
            errors.append(result.error_class or "rail result did not match the requested date")
        elif backend.mode == "off":
            errors.append("rail disabled")
        fallback, fallback_claims = _deep_link_leg(route, clock)
        leg_index = len(legs)
        legs.append(fallback)
        claims.extend(fallback_claims)
        unknowns.extend((
            {
                "field_path": "/transport_legs/%d/service_number" % leg_index,
                "reason": "actual dated service must be selected on 12306",
                "provider": "12306-mcp",
                "claim_id": fallback_claims[0]["claim_id"],
            },
            {
                "field_path": "/transport_legs/%d/price/amount" % leg_index,
                "reason": "dated fare and availability remain unknown",
                "provider": "12306-mcp",
                "claim_id": fallback_claims[1]["claim_id"],
            },
        ))

    checked_at = isoformat_seconds(clock)
    if not routes:
        health = _health(
            "12306-mcp", "0.3.10", "static", "ready", checked_at, ("rail",),
            "no cross-city rail leg was required; MCP was not called",
        )
    elif live_count == len(routes):
        health = _health(
            "12306-mcp", "0.3.10", "live", "ready", checked_at, ("rail",),
            "all dated rail legs were normalized from live MCP inventory",
        )
    else:
        status = "missing" if backend.mode == "off" else "degraded"
        health = _health(
            "12306-mcp", "0.3.10", "static", status, checked_at, ("rail",),
            "dated deep-link fallback used: " + ", ".join(sorted(set(errors))),
        )
    return legs, claims, unknowns, health, tuple(calls)


def _deep_link_leg(route: RouteSpec, clock: Clock) -> Tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]:
    hour = 16 if route.return_leg else 8
    duration = 300
    depart = datetime.fromisoformat("%sT%02d:00:00+08:00" % (route.travel_date, hour))
    arrive = depart + timedelta(minutes=duration)
    query = urllib.parse.urlencode({
        "linktypeid": "dc",
        "fs": route.from_place["name"],
        "ts": route.to_place["name"],
        "date": route.travel_date,
        "flag": "N,N,Y",
    })
    url = "https://kyfw.12306.cn/otn/leftTicket/init?" + query
    leg_id = stable_id("leg-rail-fallback", route.travel_date, route.from_place["ref_id"], route.to_place["ref_id"])
    time_claim = make_claim(
        subject_ref=leg_id,
        field_path="/depart_at",
        value="planning window; verify the actual service on 12306",
        source_url=url,
        provider="12306-deep-link",
        status="hypothesis",
        confidence=0.3,
        mode="static",
        clock=clock,
    )
    price_claim = make_claim(
        subject_ref=leg_id,
        field_path="/price",
        value=None,
        source_url=url,
        provider="12306-deep-link",
        status="unknown",
        confidence=0,
        mode="static",
        clock=clock,
    )
    leg = {
        "leg_id": leg_id,
        "travel_mode": "rail",
        "data_mode": "static",
        "from_ref": route.from_place["ref_id"],
        "to_ref": route.to_place["ref_id"],
        "depart_at": depart.isoformat(timespec="seconds"),
        "arrive_at": arrive.isoformat(timespec="seconds"),
        "duration_minutes": duration,
        "provider": "12306-deep-link",
        "service_number": None,
        "price": {
            "amount": None,
            "currency": "CNY",
            "price_type": "unknown",
            "unit": "per_person",
            "includes_taxes": True,
            "queried_at": price_claim["queried_at"],
            "claim_id": price_claim["claim_id"],
        },
        "booking_url": url,
        "claim_ids": [time_claim["claim_id"], price_claim["claim_id"]],
        "locked": False,
    }
    return leg, (time_claim, price_claim)


def _schedule_problems(
    request: Mapping[str, Any],
    legs: Sequence[Mapping[str, Any]],
    lodgings: Sequence[Mapping[str, Any]],
    pois: Sequence[Mapping[str, Any]],
    mobility: MobilityResult,
) -> Tuple[List[Mapping[str, Any]], int, int]:
    start = date.fromisoformat(request["start_date"])
    end = date.fromisoformat(request["end_date"])
    dates = [(start + timedelta(days=index)).isoformat() for index in range((end - start).days + 1)]
    by_date: Dict[str, List[Mapping[str, Any]]] = {day: [] for day in dates}
    city_by_date = _day_city_by_date(request, legs)

    for leg in legs:
        if leg["travel_mode"] == "flight":
            continue
        assert leg["depart_at"] is not None and leg["arrive_at"] is not None
        day = leg["depart_at"][:10]
        if day not in by_date:
            raise ValueError("rail leg is outside the request date range")
        by_date[day].append({
            "ref_id": leg["leg_id"],
            "title": "%s → %s 铁路" % (_place_name(request, leg["from_ref"]), _place_name(request, leg["to_ref"])),
            "kind": "transport",
            "duration_minutes": leg["duration_minutes"],
            "windows": [{"start_at": leg["depart_at"], "end_at": leg["arrive_at"]}],
            "utility": 1000,
            "required": True,
            "locked": False,
            "fixed_start": leg["depart_at"],
            "cost_cny": 0,
            "closed": False,
            "blocked_reason": None,
        })

    for lodging in lodgings:
        day = lodging["check_in"]
        if day not in by_date:
            raise ValueError("lodging check-in is outside the request date range")
        default_checkin = datetime.fromisoformat("%sT14:00:00+08:00" % day)
        inbound_arrivals = [
            datetime.fromisoformat(leg["arrive_at"].replace("Z", "+00:00"))
            for leg in legs
            if leg.get("travel_mode") != "flight"
            and isinstance(leg.get("arrive_at"), str)
            and leg["arrive_at"][:10] == day
            and _place_city(request, leg["to_ref"]) == lodging["city"]
        ]
        fixed_at = max([default_checkin] + [arrival + timedelta(minutes=30) for arrival in inbound_arrivals])
        fixed = fixed_at.isoformat(timespec="seconds")
        by_date[day].append({
            "ref_id": lodging["lodging_id"],
            "title": "%s 入住" % lodging["name"],
            "kind": "checkin",
            "duration_minutes": 45,
            "windows": [{"start_at": fixed, "end_at": "%sT23:30:00+08:00" % day}],
            "utility": 900,
            "required": True,
            "locked": False,
            "fixed_start": fixed,
            "cost_cny": 0,
            "closed": False,
            "blocked_reason": None,
        })

    unslotted: List[Mapping[str, Any]] = []
    for poi in pois:
        usable = [window for window in poi["opening_windows"] if window["status"] in ("verified", "tentative")]
        matching = [
            window for window in usable
            if window["start_at"][:10] in by_date
            and city_by_date[window["start_at"][:10]] == poi["city"]
        ]
        if matching:
            day = sorted(matching, key=lambda item: item["start_at"])[0]["start_at"][:10]
        elif usable:
            continue
        else:
            unslotted.append(poi)
            continue
        by_date[day].append(_poi_candidate(poi, matching))
    city_offsets: Dict[str, int] = {}
    for poi in unslotted:
        matching_dates = [day for day in dates if city_by_date[day] == poi["city"]]
        if not matching_dates:
            continue
        offset = city_offsets.get(poi["city"], 0)
        day = matching_dates[offset % len(matching_dates)]
        city_offsets[poi["city"]] = offset + 1
        by_date[day].append(_poi_candidate(poi, []))

    problems = []
    cell_count = 0
    live_cell_count = 0
    live_cells = {
        (item.from_ref, item.to_ref, item.travel_mode): item
        for item in mobility.cells
    }
    for index, day in enumerate(dates):
        candidates = by_date[day]
        matrix = []
        for left in candidates:
            for right in candidates:
                if left["ref_id"] == right["ref_id"]:
                    continue
                live = live_cells.get((left["ref_id"], right["ref_id"], "transit"))
                if live is not None:
                    matrix.append(live.as_dict())
                    live_cell_count += 1
                else:
                    distance = _estimated_distance(left["ref_id"], right["ref_id"], lodgings, pois)
                    matrix.append(static_estimate_cell(
                        left["ref_id"], right["ref_id"], "transit", distance, 22.0, 8
                    ).as_dict())
        cell_count += len(matrix)
        problems.append({
            "day_id": "day-%d" % (index + 1),
            "date": day,
            "start_at": "%sT07:00:00+08:00" % day,
            "end_at": "%sT23:30:00+08:00" % day,
            "travel_mode": "transit",
            "buffer_minutes": 10,
            "budget_cny": request["budget_cny"],
            "max_optional": 8,
            "max_travel_minutes": None,
            "candidates": candidates,
            "matrix": matrix,
        })
    return problems, cell_count, live_cell_count


def _poi_candidate(poi: Mapping[str, Any], windows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    duration = poi["recommended_duration_minutes"] or 90
    return {
        "ref_id": poi["poi_id"],
        "title": poi["name"],
        "kind": "meal" if poi["category"] == "food" else "poi",
        "duration_minutes": duration,
        "windows": [{"start_at": item["start_at"], "end_at": item["end_at"]} for item in windows],
        "utility": 100,
        "required": False,
        "locked": False,
        "fixed_start": None,
        "cost_cny": 0,
        "closed": False,
        "blocked_reason": None,
    }


def _estimated_distance(
    left_ref: str,
    right_ref: str,
    lodgings: Sequence[Mapping[str, Any]],
    pois: Sequence[Mapping[str, Any]],
) -> int:
    coordinates: Dict[str, Mapping[str, Any]] = {}
    for item in lodgings:
        if item["coordinates"]:
            coordinates[item["lodging_id"]] = item["coordinates"]
    for item in pois:
        if item["coordinates"]:
            coordinates[item["poi_id"]] = item["coordinates"]
    left = _point(coordinates.get(left_ref))
    right = _point(coordinates.get(right_ref))
    if left is not None and right is not None:
        return max(500, haversine_meters(left[0], left[1], right[0], right[1]))
    if left_ref.startswith("leg-") or right_ref.startswith("leg-"):
        return 12000
    if left_ref.startswith("lodging-") or right_ref.startswith("lodging-"):
        return 6000
    return 4500


def _point(coordinates: Optional[Mapping[str, Any]]) -> Optional[Tuple[float, float]]:
    if coordinates is None:
        return None
    point = coordinates.get("gcj02") or coordinates.get("wgs84") or coordinates.get("native")
    if not isinstance(point, dict):
        return None
    return float(point["lng"]), float(point["lat"])


def _trip_days(
    request: Mapping[str, Any],
    scheduled: Mapping[str, Any],
    entities: Mapping[str, Sequence[Mapping[str, Any]]],
) -> List[Mapping[str, Any]]:
    claim_ids: Dict[str, Sequence[str]] = {}
    for group, id_key in (("transport_legs", "leg_id"), ("lodgings", "lodging_id"), ("pois", "poi_id")):
        claim_ids.update((item[id_key], item["claim_ids"]) for item in entities[group])
    city_by_date = _day_city_by_date(request, entities["transport_legs"])
    days = []
    for index, result in enumerate(scheduled["days"]):
        slots = []
        for slot in result["slots"]:
            slots.append({
                "slot_id": slot["slot_id"],
                "start_at": slot["start_at"],
                "end_at": slot["end_at"],
                "kind": slot["kind"],
                "ref_id": slot["ref_id"],
                "title": slot["title"],
                "locked": slot["locked"],
                "status": "scheduled",
                "claim_ids": list(claim_ids[slot["ref_id"]]),
            })
        travel_date = (date.fromisoformat(request["start_date"]) + timedelta(days=index)).isoformat()
        covering_stays = [
            lodging for lodging in entities["lodgings"]
            if lodging["check_in"] <= travel_date < lodging["check_out"]
        ] if index < len(scheduled["days"]) - 1 else []
        if index < len(scheduled["days"]) - 1 and len(covering_stays) != 1:
            raise ValueError("plan has no feasible stay coverage for %s" % travel_date)
        days.append({
            "day_id": "day-%d" % (index + 1),
            "date": travel_date,
            "city": city_by_date[travel_date],
            "timezone": "Asia/Shanghai",
            "stay_id": covering_stays[0]["lodging_id"] if covering_stays else None,
            "slots": slots,
        })
    return days


def _combined_amap_health(
    mobility: Mapping[str, Any],
    lodging: Optional[Mapping[str, Any]],
) -> Mapping[str, Any]:
    if lodging is None:
        return copy.deepcopy(dict(mobility))
    severity = {
        "contract_mismatch": 7,
        "forbidden": 6,
        "rate_limited": 5,
        "unavailable": 4,
        "degraded": 3,
        "expired": 2,
        "missing": 1,
        "ready": 0,
    }
    successful = any(item.get("status") == "ready" and item.get("mode") == "live" for item in (mobility, lodging))
    if successful:
        status = "ready"
    else:
        status = max(
            (str(item.get("status", "degraded")) for item in (mobility, lodging)),
            key=lambda value: severity.get(value, 3),
        )
    capabilities = list(dict.fromkeys(
        list(mobility.get("capabilities", ())) + list(lodging.get("capabilities", ()))
    ))
    return {
        "provider": "amap",
        "version": mobility["version"],
        "mode": "live" if any(item.get("mode") == "live" for item in (mobility, lodging)) else "static",
        "status": status,
        "checked_at": max(str(mobility["checked_at"]), str(lodging["checked_at"])),
        "capabilities": capabilities,
        "reason": "lodging=%s; mobility=%s" % (lodging["reason"], mobility["reason"]),
    }


def _provider_health(
    now: str,
    rail_health: Mapping[str, Any],
    flyai_health: Mapping[str, Any],
    amap_health: Mapping[str, Any],
    variflight_health: Mapping[str, Any],
) -> List[Mapping[str, Any]]:
    return [
        rail_health,
        _health("host-web", "candidate-file", "static", "ready", now, ("research",), "researched candidate file supplied; no web call was made"),
        copy.deepcopy(dict(flyai_health)),
        copy.deepcopy(dict(amap_health)),
        copy.deepcopy(dict(variflight_health)),
        _health("anysearch", "runtime-probe-v1", "static", "missing", now, ("research",), "optional search supplement is disabled; no auto-registration or business call was made"),
    ]


def _health(provider: str, version: str, mode: str, status: str, checked_at: str, capabilities: Sequence[str], reason: str) -> Mapping[str, Any]:
    return {
        "provider": provider,
        "version": version,
        "mode": mode,
        "status": status,
        "checked_at": checked_at,
        "capabilities": list(capabilities),
        "reason": reason,
    }


def _place_name(request: Mapping[str, Any], ref_id: str) -> str:
    places = list(request["destinations"])
    if request["origin"]:
        places.append(request["origin"])
    return next((item["name"] for item in places if item["ref_id"] == ref_id), ref_id)


def _place_city(request: Mapping[str, Any], ref_id: str) -> str:
    places = list(request["destinations"])
    if request["origin"]:
        places.append(request["origin"])
    return next((item["city"] for item in places if item["ref_id"] == ref_id), ref_id)
