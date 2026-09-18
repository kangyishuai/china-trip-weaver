"""AMap POI/geocode/route adapter with explicit GCJ-02 provenance."""

from __future__ import annotations

import urllib.parse
from typing import Any, Dict, List, Mapping, Optional

from ..clock import Clock, isoformat_seconds
from ..contracts import ProviderRequest
from ..evidence import make_claim
from ..geo import Point, coordinate_record
from .base import BaseAdapter, ContractMismatch, Normalization, ProviderFailure, sanitize_text, stable_id


#: lbs.amap.com/api/webservice/guide/tools/info — codes AMap documents as quota/QPS
#: limits, regardless of which endpoint returns them.
_RATE_LIMITED_INFOCODES = frozenset((
    "10003", "10004", "10010", "10014", "10015", "10019", "10020", "10021",
    "10029", "10044", "10045", "40000", "40003",
))
#: Codes AMap documents as the engine or gateway itself failing, not the request.
_UPSTREAM_5XX_INFOCODES = frozenset(("10016", "10017"))
#: Codes AMap documents as the request's own parameters/content being rejected.
#: Every 3xxxx code is engine-side data/params rejection for a single request, so
#: the whole prefix is treated as invalid_request without enumerating each one.
_INVALID_REQUEST_INFOCODES = frozenset((
    "20000", "20001", "20002", "20003", "20011", "20012",
    "20800", "20801", "20802", "20803",
))


def _classify_amap_infocode(code: str) -> Optional[str]:
    if code in _RATE_LIMITED_INFOCODES:
        return "rate_limited"
    if code in _UPSTREAM_5XX_INFOCODES:
        return "upstream_5xx"
    if code in _INVALID_REQUEST_INFOCODES:
        return "invalid_request"
    if len(code) == 5 and code[0] == "3" and code.isdigit():
        return "invalid_request"
    return None


_FAILURE_MESSAGES = {
    "rate_limited": "AMap quota response",
    "upstream_5xx": "AMap engine reported a temporary failure",
    "invalid_request": "AMap rejected this request's parameters or content",
}


class AMapAdapter(BaseAdapter):
    provider = "amap"
    provider_version = "web-service-v5-v3-route"
    capabilities = ("poi", "geocode", "route", "poi_around", "weather")
    required_secret_names = ("AMAP_WEBSERVICE_KEY",)
    allow_keyless = False

    def normalize(self, body: Any, request: ProviderRequest, clock: Clock) -> Normalization:
        if not isinstance(body, dict):
            raise ContractMismatch("AMap response is not an object")
        api = body.get("api")
        if api == "route-riding-v4" and "errcode" in body:
            if str(body.get("errcode")) != "0":
                info = str(body.get("errmsg", "unknown"))
                error_class = _classify_amap_infocode(str(body.get("errcode")))
                if error_class is None:
                    error_class = (
                        "rate_limited" if ("LIMIT" in info.upper() or "QUOTA" in info.upper())
                        else "forbidden"
                    )
                raise ProviderFailure(error_class, _FAILURE_MESSAGES.get(error_class, "AMap rejected the request"))
        elif body.get("status") != "1":
            info = str(body.get("info", "unknown"))
            error_class = _classify_amap_infocode(str(body.get("infocode", "")))
            if error_class is None:
                error_class = "rate_limited" if "LIMIT" in info.upper() else "forbidden"
            raise ProviderFailure(error_class, _FAILURE_MESSAGES.get(error_class, "AMap rejected the request"))
        if api in ("poi-v5", "around-v5"):
            return self._pois(body, request, clock)
        if api == "geocode-v3":
            return self._geocodes(body, request, clock)
        if api in ("route-walking-v3", "route-transit-v3", "route-driving-v3", "route-riding-v4"):
            return self._route(body, request, clock)
        if api == "weather-v3":
            return self._weather(body, request, clock)
        raise ContractMismatch("AMap endpoint fingerprint mismatch")

    def _pois(self, body: Mapping[str, Any], request: ProviderRequest, clock: Clock) -> Normalization:
        if (
            not isinstance(body.get("pois"), list)
            or not isinstance(body.get("page_num"), int)
            or not isinstance(body.get("page_size"), int)
        ):
            raise ContractMismatch("AMap v5 POI pagination or pois shape drifted")
        source_url = (
            "https://restapi.amap.com/v5/place/around" if body.get("api") == "around-v5"
            else "https://restapi.amap.com/v5/place/text"
        )
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
                source_url=source_url, provider=self.provider,
                status="verified", confidence=0.9, mode="live", clock=clock,
                json_path="/pois/%d" % index,
            )
            business_claim = make_claim(
                subject_ref=subject_ref, field_path="/business", value=business,
                source_url=source_url, provider=self.provider,
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
                "coordinates": _poi_coordinates(raw.get("location"), clock),
                "recommended_duration_minutes": None,
                "opening_windows": [],
                "price": None,
                "distance_meters": int(raw["distance"]) if body.get("api") == "around-v5" else None,
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
            places.append({"ref_id": ref_id, "name": name, "city": sanitize_text(city_value, 80), "district": _optional_text(raw, "district", 80)})
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

    def _weather(self, body: Mapping[str, Any], request: ProviderRequest, clock: Clock) -> Normalization:
        forecasts = body.get("forecasts")
        if not isinstance(forecasts, list):
            raise ContractMismatch("AMap weather forecasts shape drifted")
        if len(forecasts) > 1:
            return Normalization((), (), warnings=("weather_ambiguous:%d" % len(forecasts),))
        if not forecasts:
            raise ProviderFailure("no_results", "AMap weather forecast is empty")
        forecast = forecasts[0]
        if not isinstance(forecast, dict):
            raise ContractMismatch("AMap weather forecast entry is not an object")
        casts = forecast.get("casts")
        if not isinstance(casts, list):
            raise ContractMismatch("AMap weather casts shape drifted")
        if not casts:
            raise ProviderFailure("no_results", "AMap weather forecast has no casts")
        adcode = sanitize_text(forecast["adcode"], 20)
        if len(adcode) != 6 or not adcode.isdigit():
            raise ContractMismatch("AMap weather adcode is not a 6-digit code")
        city = sanitize_text(forecast["city"], 80)
        if not city:
            raise ContractMismatch("AMap weather city is empty")
        reported_at = _weather_reported_at(forecast["reporttime"])
        subject_ref = sanitize_text(request.parameters.get("subject_ref", ""), 80) or ("weather-" + adcode)
        source_url = "https://restapi.amap.com/v3/weather/weatherInfo"
        claims: List[Mapping[str, Any]] = []
        for index, cast in enumerate(casts):
            if not isinstance(cast, dict):
                raise ContractMismatch("AMap weather cast entry is not an object")
            value = {
                "forecast_date": _weather_date(cast["date"]),
                "adcode": adcode,
                "city": city,
                "day_text": sanitize_text(cast["dayweather"], 40),
                "night_text": sanitize_text(cast["nightweather"], 40),
                "temp_high_c": _weather_temp(cast["daytemp"]),
                "temp_low_c": _weather_temp(cast["nighttemp"]),
                "wind_day": _weather_wind(cast["daywind"], cast["daypower"]),
                "wind_night": _weather_wind(cast["nightwind"], cast["nightpower"]),
                "reported_at": reported_at,
            }
            claims.append(make_claim(
                subject_ref=subject_ref, field_path="/weather", value=value,
                source_url=source_url, provider=self.provider,
                status="verified", confidence=0.7, mode="live", clock=clock,
                json_path="/forecasts/0/casts/%d" % index,
            ))
        return Normalization((), tuple(claims))


def _location(value: Any) -> Point:
    if not isinstance(value, str) or value.count(",") != 1:
        raise ContractMismatch("AMap location is not lng,lat")
    lng, lat = value.split(",")
    return Point(float(lng), float(lat))


def _poi_coordinates(value: Any, clock: Clock) -> Optional[Mapping[str, Any]]:
    try:
        point = _location(value)
    except (ContractMismatch, TypeError, ValueError, OverflowError):
        return None
    if not (-180.0 <= point.lng <= 180.0 and -90.0 <= point.lat <= 90.0):
        return None
    return coordinate_record("GCJ02", point, clock, accuracy_m=50)


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


def _weather_date(value: Any) -> str:
    text = sanitize_text(value, 20)
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        raise ContractMismatch("AMap weather date is not YYYY-MM-DD")
    return text


def _weather_temp(value: Any) -> int:
    text = sanitize_text(value, 10)
    try:
        return int(text)
    except ValueError as exc:
        raise ContractMismatch("AMap weather temperature is not an integer") from exc


def _weather_wind(direction: Any, power: Any) -> str:
    direction_text = sanitize_text(direction, 20)
    power_text = sanitize_text(power, 20)
    if not direction_text or not power_text:
        raise ContractMismatch("AMap weather wind fields are missing")
    return direction_text + power_text + "级"


def _weather_reported_at(value: Any) -> str:
    text = sanitize_text(value, 40)
    if (
        len(text) != 19
        or text[4] != "-" or text[7] != "-"
        or text[10] != " " or text[13] != ":" or text[16] != ":"
    ):
        raise ContractMismatch("AMap weather reporttime shape drifted")
    return text.replace(" ", "T") + "+08:00"


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
