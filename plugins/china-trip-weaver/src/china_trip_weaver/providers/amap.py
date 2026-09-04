"""AMap POI/geocode/route adapter with explicit GCJ-02 provenance."""

from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Mapping, Optional

from ..clock import Clock, isoformat_seconds
from ..contracts import ProviderRequest
from ..evidence import make_claim
from ..geo import Point, coordinate_record
from .base import BaseAdapter, ContractMismatch, Normalization, ProviderFailure, sanitize_text, stable_id


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
        for index, raw in enumerate(body["pois"]):
            if not isinstance(raw, dict):
                raise ContractMismatch("AMap POI item is not an object")
            provider_poi_id = sanitize_text(raw.get("id"), 80)
            if not provider_poi_id:
                raise ContractMismatch("AMap POI id is empty")
            poi_id = "poi-amap-" + provider_poi_id.lower()
            name = sanitize_text(raw["name"], 160)
            if not name:
                raise ContractMismatch("AMap POI name is empty")
            city = _provider_city(raw, poi=True)
            district = _optional_text(raw, "adname", 80) or _optional_text(raw, "district", 80)
            poi_type = _optional_text(raw, "type", 120)
            business = _business(raw.get("business"))
            subject_ref = sanitize_text(request.parameters.get("subject_ref", ""), 80) or poi_id
            identity = {
                "provider_poi_id": provider_poi_id,
                "matched_name": name,
                "formatted_address": _formatted_address(raw),
                "district": district,
                "adcode": _optional_text(raw, "adcode", 20),
                "type": poi_type,
                "business": business,
            }
            identity_claim = make_claim(
                subject_ref=subject_ref, field_path="/provider_identity", value=identity,
                source_url="https://restapi.amap.com/v5/place/text", provider=self.provider,
                status="verified", confidence=0.9, mode="live", clock=clock,
                json_path="/pois/%d" % index,
            )
            business_claim = make_claim(
                subject_ref=subject_ref, field_path="/business", value=business,
                source_url="https://restapi.amap.com/v5/place/text", provider=self.provider,
                status="partial", confidence=0.65, mode="live", clock=clock,
                json_path="/pois/%d/business" % index,
                claim_id=stable_id(
                    "claim-amap-business", subject_ref, provider_poi_id,
                    business, isoformat_seconds(clock),
                ),
            )
            items.append({
                "poi_id": poi_id,
                "name": name,
                "city": city,
                "category": poi_type or "poi",
                "coordinates": None,
                "recommended_duration_minutes": None,
                "opening_windows": [],
                "price": None,
                "deep_links": ["https://www.amap.com/search?" + urllib.parse.urlencode({"id": provider_poi_id})],
                "claim_ids": [identity_claim["claim_id"], business_claim["claim_id"]],
            })
            claims.extend((identity_claim, business_claim))
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
            city_value = _provider_city(raw, poi=False)
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


def _optional_text(raw: Mapping[str, Any], field: str, max_length: int) -> Optional[str]:
    value = raw.get(field)
    if not isinstance(value, str):
        return None
    clean = sanitize_text(value, max_length)
    if not clean or clean.lower() in ("[]", "null", "none"):
        return None
    return clean


def _provider_city(raw: Mapping[str, Any], *, poi: bool) -> str:
    city_field = "cityname" if poi else "city"
    province_field = "pname" if poi else "province"
    city = _optional_text(raw, city_field, 80)
    if city:
        return city
    province = _optional_text(raw, province_field, 80)
    if province and any(name in province for name in ("北京", "上海", "天津", "重庆", "香港", "澳门")):
        return province
    return "unknown"


def _formatted_address(raw: Mapping[str, Any]) -> str:
    address = _optional_text(raw, "address", 240)
    if not address:
        return ""
    prefix = ""
    for field in ("pname", "cityname", "adname"):
        part = _optional_text(raw, field, 80)
        if part and part not in prefix and part not in address:
            prefix += part
    return (prefix + address)[:320]


def _business(value: Any) -> Mapping[str, Any]:
    if value in (None, "", []):
        return {}
    if not isinstance(value, dict):
        raise ContractMismatch("AMap business field is not an object")
    return _sanitize_json_object(value, depth=0)


def _sanitize_json_object(value: Mapping[str, Any], *, depth: int) -> Mapping[str, Any]:
    if depth > 2 or len(value) > 40:
        raise ContractMismatch("AMap business field is too deeply nested or too large")
    clean: Dict[str, Any] = {}
    for raw_key in sorted(value):
        key = sanitize_text(raw_key, 80)
        if not key:
            raise ContractMismatch("AMap business field has an empty key")
        clean[key] = _sanitize_json_value(value[raw_key], depth=depth + 1)
    return clean


def _sanitize_json_value(value: Any, *, depth: int) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return sanitize_text(value, 500)
    if isinstance(value, dict):
        return _sanitize_json_object(value, depth=depth)
    if isinstance(value, list):
        if len(value) > 40:
            raise ContractMismatch("AMap business list is too large")
        return [_sanitize_json_value(item, depth=depth) for item in value]
    raise ContractMismatch("AMap business field contains an unsupported value")


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
