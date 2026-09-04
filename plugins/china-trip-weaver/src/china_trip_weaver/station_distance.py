"""Best-effort AMap distance signals for ambiguous rail stations."""

from __future__ import annotations

import copy
import math
import unicodedata
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .clock import Clock, SystemClock
from .contracts import ProviderRequest
from .credentials import CredentialResolution
from .geo import Point
from .matrix import haversine_meters


DEFAULT_CALL_DEADLINE_MS = 2_000


class StationDistanceEnrichmentError(RuntimeError):
    """AMap could not safely provide an optional station-distance signal."""


class _CapturingTransport:
    def __init__(self, transport: Any) -> None:
        self.transport = transport
        self.last_envelope: Optional[Any] = None
        # Optional enrichment gets one bounded attempt per request. The main AMap
        # workflows retain their normal retry behavior.
        self.retry_rate_limits = False
        progress = getattr(transport, "progress", None)
        if callable(progress):
            self.progress = progress

    def execute(self, provider: str, request: ProviderRequest) -> Any:
        self.last_envelope = self.transport.execute(provider, request)
        return self.last_envelope


class AMapStationDistanceEnricher:
    """Add city-centre distances without removing or selecting rail candidates."""

    def __init__(
        self,
        credentials: CredentialResolution,
        *,
        transport: Optional[Any] = None,
        clock: Optional[Clock] = None,
        call_deadline_ms: int = DEFAULT_CALL_DEADLINE_MS,
    ) -> None:
        if call_deadline_ms <= 0:
            raise ValueError("station distance call deadline must be positive")
        if transport is None:
            # Imported lazily so this root-level helper cannot create a providers
            # package import cycle when rail12306 imports mcp_stdio.
            from .providers.amap_http import AMapHTTPTransport

            transport = AMapHTTPTransport(credentials)
        self.credentials = credentials
        self.transport = transport
        self.clock = clock or SystemClock()
        self.call_deadline_ms = int(call_deadline_ms)

    def enrich(
        self,
        resolution: Mapping[str, Any],
        request: ProviderRequest,
    ) -> Mapping[str, Any]:
        """Return a copied resolution; provider failures intentionally propagate.

        RailMCPStdioTransport owns the outer best-effort boundary and replaces any
        failed enrichment with the untouched 12306 resolution. A clean POI miss is
        different: other stations may still receive truthful distances.
        """

        enriched = copy.deepcopy(dict(resolution))
        if not self.credentials.get("AMAP_WEBSERVICE_KEY"):
            return enriched
        endpoints = enriched.get("endpoints")
        if enriched.get("status") != "ambiguous" or not isinstance(endpoints, dict):
            return enriched

        centre_cache: Dict[str, Optional[Point]] = {}
        station_cache: Dict[Tuple[str, str], Optional[Point]] = {}
        for endpoint_name in ("from", "to"):
            endpoint = endpoints.get(endpoint_name)
            if not isinstance(endpoint, dict):
                raise StationDistanceEnrichmentError("rail station endpoint has the wrong shape")
            city = endpoint.get("query")
            candidates = endpoint.get("candidates")
            if not isinstance(city, str) or not city.strip() or not isinstance(candidates, list):
                raise StationDistanceEnrichmentError("rail station endpoint has the wrong shape")
            missing_indexes = [
                index for index, candidate in enumerate(candidates)
                if isinstance(candidate, dict) and "distance_meters" not in candidate
            ]
            if len(candidates) <= 1 or not missing_indexes:
                continue

            city_key = city.strip()
            if city_key not in centre_cache:
                centre_cache[city_key] = self._city_centre(city_key, request)
            centre = centre_cache[city_key]
            if centre is None:
                continue

            for index in missing_indexes:
                candidate = candidates[index]
                if not isinstance(candidate, dict):
                    raise StationDistanceEnrichmentError("rail station candidate has the wrong shape")
                station_name = candidate.get("station_name")
                if not isinstance(station_name, str) or not station_name.strip():
                    raise StationDistanceEnrichmentError("rail station name has the wrong shape")
                lookup_key = (city_key, station_name.strip())
                if lookup_key not in station_cache:
                    station_cache[lookup_key] = self._station_point(city_key, station_name.strip(), request)
                station = station_cache[lookup_key]
                if station is not None:
                    candidate["distance_meters"] = haversine_meters(
                        centre.lng,
                        centre.lat,
                        station.lng,
                        station.lat,
                    )
        return enriched

    def _city_centre(self, city: str, parent: ProviderRequest) -> Optional[Point]:
        request = self._request(
            parent,
            capability="geocode",
            identity=(city, "centre"),
            parameters={"address": city, "city": city},
        )
        result, _ = self._query(request)
        points = []
        for item in result.normalized_items:
            if not isinstance(item, dict) or not _city_matches(city, item.get("city")):
                continue
            ref_id = item.get("ref_id")
            matching_claims = [
                claim for claim in result.claims
                if claim.get("subject_ref") == ref_id and claim.get("field_path") == "/coordinates"
            ]
            if len(matching_claims) != 1:
                raise StationDistanceEnrichmentError("AMap geocode coordinates are ambiguous")
            point = _coordinate_record_point(matching_claims[0].get("value"))
            if point is not None:
                points.append(point)
        return _unique_point(points)

    def _station_point(self, city: str, station_name: str, parent: ProviderRequest) -> Optional[Point]:
        request = self._request(
            parent,
            capability="poi",
            identity=(city, station_name),
            parameters={
                "keywords": station_name,
                "city": city,
                "page_size": 5,
                "page_num": 1,
            },
        )
        result, body = self._query(request)
        if not result.normalized_items:
            return None
        if not isinstance(body, dict) or not isinstance(body.get("pois"), list):
            raise StationDistanceEnrichmentError("AMap POI response body is unavailable")
        raw_by_id = {
            raw.get("id"): raw
            for raw in body["pois"]
            if isinstance(raw, dict) and isinstance(raw.get("id"), str)
        }
        points = []
        for item in result.normalized_items:
            if (
                not isinstance(item, dict)
                or not _station_names_match(station_name, item.get("name"))
                or not _city_matches(city, item.get("city"))
                or not _rail_station_category(item.get("category"))
            ):
                continue
            claim_ids = item.get("claim_ids")
            if not isinstance(claim_ids, list):
                raise StationDistanceEnrichmentError("AMap POI identity claims are missing")
            identities = [
                claim.get("value") for claim in result.claims
                if claim.get("claim_id") in claim_ids and claim.get("field_path") == "/provider_identity"
            ]
            if len(identities) != 1 or not isinstance(identities[0], dict):
                raise StationDistanceEnrichmentError("AMap POI identity is ambiguous")
            provider_poi_id = identities[0].get("provider_poi_id")
            raw = raw_by_id.get(provider_poi_id)
            if not isinstance(raw, dict):
                raise StationDistanceEnrichmentError("AMap POI raw identity does not match normalization")
            point = _location_point(raw.get("location"))
            if point is not None:
                points.append(point)
        return _unique_point(points)

    def _query(self, request: ProviderRequest) -> Tuple[Any, Optional[Mapping[str, Any]]]:
        from .providers.amap import AMapAdapter
        from .providers.base import ProviderContext

        capture = _CapturingTransport(self.transport)
        adapter = AMapAdapter()
        adapter.max_attempts = 1
        result = adapter.query(
            request,
            ProviderContext(
                clock=self.clock,
                credentials=self.credentials,
                transport=capture,
            ),
        )
        if result.error_class == "no_results":
            return result, None
        if result.error_class is not None:
            raise StationDistanceEnrichmentError("AMap %s failed: %s" % (request.capability, result.error_class))
        envelope = capture.last_envelope
        if envelope is None:
            raise StationDistanceEnrichmentError("AMap response envelope is unavailable")
        body = envelope.body if isinstance(envelope.body, dict) else None
        return result, body

    def _request(
        self,
        parent: ProviderRequest,
        *,
        capability: str,
        identity: Sequence[str],
        parameters: Mapping[str, Any],
    ) -> ProviderRequest:
        from .providers.base import stable_id

        return ProviderRequest(
            request_id=stable_id("rail-station-amap", capability, *identity),
            capability=capability,
            parameters=dict(parameters),
            deadline_ms=max(1, min(parent.deadline_ms, self.call_deadline_ms)),
            as_of=parent.as_of,
            cache_policy="bypass",
            trace={"stage": "rail-station-distance"},
        )


def _station_names_match(expected: str, actual: Any) -> bool:
    if not isinstance(actual, str):
        return False
    expected_key = _station_name_key(expected)
    return bool(expected_key) and expected_key == _station_name_key(actual)


def _station_name_key(value: str) -> str:
    key = "".join(unicodedata.normalize("NFKC", value).split()).casefold()
    for suffix in ("火车站", "站"):
        if key.endswith(suffix):
            return key[:-len(suffix)]
    return key


def _city_matches(expected: str, actual: Any) -> bool:
    if not isinstance(actual, str):
        return False
    expected_key = _city_key(expected)
    return bool(expected_key) and expected_key == _city_key(actual)


def _city_key(value: str) -> str:
    key = "".join(unicodedata.normalize("NFKC", value).split()).casefold()
    return key[:-1] if key.endswith("市") else key


def _rail_station_category(value: Any) -> bool:
    return isinstance(value, str) and ("火车站" in value or "铁路" in value)


def _coordinate_record_point(value: Any) -> Optional[Point]:
    if not isinstance(value, dict):
        return None
    coordinates = value.get("gcj02")
    if not isinstance(coordinates, dict):
        return None
    return _point(coordinates.get("lng"), coordinates.get("lat"))


def _location_point(value: Any) -> Optional[Point]:
    if not isinstance(value, str) or value.count(",") != 1:
        return None
    lng, lat = value.split(",")
    try:
        return _point(float(lng), float(lat))
    except ValueError:
        return None


def _point(lng: Any, lat: Any) -> Optional[Point]:
    if (
        isinstance(lng, bool)
        or isinstance(lat, bool)
        or not isinstance(lng, (int, float))
        or not isinstance(lat, (int, float))
        or not math.isfinite(float(lng))
        or not math.isfinite(float(lat))
        or not -180 <= float(lng) <= 180
        or not -90 <= float(lat) <= 90
    ):
        return None
    return Point(float(lng), float(lat))


def _unique_point(points: Sequence[Point]) -> Optional[Point]:
    unique = {(point.lng, point.lat): point for point in points}
    return next(iter(unique.values())) if len(unique) == 1 else None
