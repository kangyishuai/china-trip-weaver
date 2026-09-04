"""AMap POI/geocode/route adapter with explicit GCJ-02 provenance."""

from __future__ import annotations

from typing import Any, List, Mapping, Sequence, Tuple

from ..clock import Clock
from ..contracts import ProviderRequest
from ..evidence import make_claim
from ..geo import Point, coordinate_record
from .base import BaseAdapter, ContractMismatch, Normalization, ProviderFailure, safe_https_url, sanitize_text, stable_id


class AMapAdapter(BaseAdapter):
    provider = "amap"
    provider_version = "web-service-v5-v3-route"
    capabilities = ("poi", "geocode", "route")
    required_secret_names = ("AMAP_WEBSERVICE_KEY",)
    allow_keyless = False

    def normalize(self, body: Any, request: ProviderRequest, clock: Clock) -> Normalization:
        if not isinstance(body, dict):
            raise ContractMismatch("AMap response is not an object")
        api = body.get("api")
        if api == "route-riding-v4" and "errcode" in body:
            if str(body.get("errcode")) != "0":
                info = str(body.get("errmsg", "unknown"))
                if "LIMIT" in info.upper() or "QUOTA" in info.upper():
                    raise ProviderFailure("rate_limited", "AMap quota response")
                raise ProviderFailure("forbidden", "AMap rejected the request")
        elif body.get("status") != "1":
            info = str(body.get("info", "unknown"))
            if "LIMIT" in info.upper():
                raise ProviderFailure("rate_limited", "AMap quota response")
            raise ProviderFailure("forbidden", "AMap rejected the request")
        if api == "poi-v5":
            return self._pois(body, request, clock)
        if api == "geocode-v3":
            return self._geocodes(body, request, clock)
        if api in ("route-walking-v3", "route-transit-v3", "route-driving-v3", "route-riding-v4"):
            return self._route(body, request, clock)
        raise ContractMismatch("AMap endpoint fingerprint mismatch")

    def _pois(self, body: Mapping[str, Any], request: ProviderRequest, clock: Clock) -> Normalization:
        if (
            not isinstance(body.get("pois"), list)
            or not isinstance(body.get("page_num"), int)
            or not isinstance(body.get("page_size"), int)
        ):
            raise ContractMismatch("AMap v5 POI pagination or pois shape drifted")
        items: List[Mapping[str, Any]] = []
        claims: List[Mapping[str, Any]] = []
        for raw in body["pois"]:
            point = _location(raw["location"])
            poi_id = "poi-amap-" + sanitize_text(raw["id"], 80).lower()
            name = sanitize_text(raw["name"], 160)
            evidence = make_claim(
                subject_ref=poi_id, field_path="/coordinates", value=point.as_dict(),
                source_url="https://restapi.amap.com/v5/place/text", provider=self.provider,
                status="verified", confidence=0.9, mode="live", clock=clock,
            )
            items.append({
                "poi_id": poi_id,
                "name": name,
                "city": sanitize_text(raw.get("cityname", request.parameters["city"]), 80),
                "category": sanitize_text(raw.get("type", "poi"), 120),
                "coordinates": coordinate_record("GCJ02", point, clock, accuracy_m=25),
                "recommended_duration_minutes": None,
                "opening_windows": [],
                "price": None,
                "deep_links": ["https://www.amap.com/search?id=" + sanitize_text(raw["id"], 80)],
                "claim_ids": [evidence["claim_id"]],
            })
            claims.append(evidence)
        return Normalization(tuple(items), tuple(claims))

    def _geocodes(self, body: Mapping[str, Any], request: ProviderRequest, clock: Clock) -> Normalization:
        if not isinstance(body.get("geocodes"), list):
            raise ContractMismatch("AMap geocode shape drifted")
        places = []
        claims = []
        for raw in body["geocodes"]:
            if not isinstance(raw, dict):
                raise ContractMismatch("AMap geocode item is not an object")
            point = _location(raw["location"])
            name = sanitize_text(raw.get("formatted_address", request.parameters.get("address", "place")), 160)
            ref_id = sanitize_text(request.parameters.get("subject_ref", ""), 80) or stable_id("place-amap", name, raw["location"])
            city_value = raw.get("city") if isinstance(raw.get("city"), str) and raw.get("city") else request.parameters["city"]
            coordinates = coordinate_record("GCJ02", point, clock, accuracy_m=50)
            claim = make_claim(
                subject_ref=ref_id, field_path="/coordinates", value=coordinates,
                source_url="https://restapi.amap.com/v3/geocode/geo", provider=self.provider,
                status="verified", confidence=0.85, mode="live", clock=clock,
            )
            places.append({"ref_id": ref_id, "name": name, "city": sanitize_text(city_value, 80)})
            claims.append(claim)
        return Normalization(tuple(places), tuple(claims))

    def _route(self, body: Mapping[str, Any], request: ProviderRequest, clock: Clock) -> Normalization:
        route = body.get("data") if body["api"] == "route-riding-v4" and isinstance(body.get("data"), dict) else body.get("route")
        if not isinstance(route, dict):
            raise ContractMismatch("AMap route object is missing")
        candidates = route.get("transits") if body["api"] == "route-transit-v3" else route.get("paths")
        if not isinstance(candidates, list):
            raise ContractMismatch("AMap route alternatives are missing")
        if not candidates:
            return Normalization((), (), ("unreachable",))
        raw = candidates[0]
        if not isinstance(raw, dict):
            raise ContractMismatch("AMap route alternative is not an object")
        duration = int(raw["duration"])
        distance = int(raw["distance"])
        if duration < 0 or distance < 0:
            raise ContractMismatch("AMap route duration or distance is negative")
        leg_id = stable_id("leg-amap", request.parameters["from_ref"], request.parameters["to_ref"], request.parameters["travel_mode"])
        duration_claim = make_claim(
            subject_ref=leg_id, field_path="/duration_minutes", value=(duration + 59) // 60,
            source_url=_route_source(request.parameters["travel_mode"]),
            provider=self.provider, status="verified", confidence=0.9, mode="live", clock=clock,
        )
        distance_claim = make_claim(
            subject_ref=leg_id, field_path="/distance_meters", value=distance,
            source_url=_route_source(request.parameters["travel_mode"]),
            provider=self.provider, status="verified", confidence=0.9, mode="live", clock=clock,
        )
        return Normalization(({
            "leg_id": leg_id,
            "travel_mode": request.parameters["travel_mode"],
            "data_mode": "live",
            "from_ref": request.parameters["from_ref"],
            "to_ref": request.parameters["to_ref"],
            "depart_at": None,
            "arrive_at": None,
            "duration_minutes": (duration + 59) // 60,
            "provider": self.provider,
            "service_number": None,
            "price": None,
            "booking_url": None,
            "claim_ids": [duration_claim["claim_id"], distance_claim["claim_id"]],
            "locked": False,
        },), (duration_claim, distance_claim))


def _location(value: Any) -> Point:
    if not isinstance(value, str) or value.count(",") != 1:
        raise ContractMismatch("AMap location is not lng,lat")
    lng, lat = value.split(",")
    return Point(float(lng), float(lat))


def _route_source(travel_mode: str) -> str:
    paths = {
        "walk": "/v3/direction/walking",
        "transit": "/v3/direction/transit/integrated",
        "drive": "/v3/direction/driving",
        "ride": "/v4/direction/bicycling",
    }
    if travel_mode not in paths:
        raise ContractMismatch("AMap travel mode is unsupported")
    return "https://restapi.amap.com" + paths[travel_mode]
