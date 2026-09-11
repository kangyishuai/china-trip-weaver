"""Best-effort AMap distance signals for ambiguous rail stations."""

from __future__ import annotations

import copy
import math
import unicodedata
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .clock import Clock, SystemClock
from .contracts import ProviderRequest
from .credentials import CredentialResolution
from .geo import Point, administrative_area_key
from .matrix import haversine_meters


DEFAULT_CALL_DEADLINE_MS = 2_000

# A same-named station in a neighboring administrative area (e.g. 武夷山东站
# sitting in 建阳区 rather than 武夷山市) can still be the right one. The
# nationwide fallback in `_station_point` only accepts such a station within
# this distance of the researched city's centre; farther or ambiguous
# matches are left with an unknown distance rather than guessed.
STATION_MAX_DISTANCE_METERS = 80_000

# How far around a station-less place's centre (鼓浪屿, a scenic-area name, ...)
# to search for a real nearby train station once all of 12306's own
# station-resolution layers found nothing. Matches AMap's own /v5/place/around
# radius ceiling, so this is the widest search the endpoint allows.
NEARBY_STATION_SEARCH_RADIUS_METERS = 50_000


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
        station_cache: Dict[Tuple[str, str], Tuple[Optional[Point], bool]] = {}
        nationwide_cache: Dict[Tuple[str, str], Optional[Point]] = {}
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
                station, found_any_poi = station_cache[lookup_key]
                if station is None and found_any_poi:
                    # AMap has some opinion about this keyword within the
                    # city-limited search (just not a usable same-city match).
                    # A same-named station in a neighboring administrative
                    # area may still be it; a keyword AMap found nothing for
                    # at all is not worth the extra nationwide call.
                    if lookup_key not in nationwide_cache:
                        nationwide_point, _ = self._station_point(
                            city_key,
                            station_name.strip(),
                            request,
                            nationwide=True,
                            centre=centre,
                            max_distance_meters=STATION_MAX_DISTANCE_METERS,
                        )
                        nationwide_cache[lookup_key] = nationwide_point
                    station = nationwide_cache[lookup_key]
                if station is not None:
                    candidate["distance_meters"] = haversine_meters(
                        centre.lng,
                        centre.lat,
                        station.lng,
                        station.lat,
                    )
        return enriched

    def find_nearby_stations(
        self,
        city: str,
        parent: ProviderRequest,
    ) -> Sequence[Mapping[str, Any]]:
        """Find real train stations within `NEARBY_STATION_SEARCH_RADIUS_METERS` of `city`'s centre.

        Only meant to be tried once 12306's three station-resolution layers,
        plus the administrative-suffix retry, found nothing for `city` --
        e.g. `city` names a place with no station of its own (鼓浪屿, 湄洲岛,
        a scenic-area name). Returns AMap POI candidates carrying the
        straight-line `distance_meters` AMap itself reports for the search;
        the caller still has to cross-check each name against 12306's own
        station table before treating it as a real candidate -- this method
        never guesses one on its own.
        """

        if not self.credentials.get("AMAP_WEBSERVICE_KEY"):
            return ()
        centre = self._place_centre(city, parent)
        if centre is None:
            return ()
        request = self._request(
            parent,
            capability="poi_around",
            identity=(city, "nearby-stations"),
            parameters={
                "location": "%.6f,%.6f" % (centre.lng, centre.lat),
                "keywords": "火车站",
                "types": "150200",
                "radius": NEARBY_STATION_SEARCH_RADIUS_METERS,
                "page_size": 10,
            },
        )
        result, body = self._query(request)
        if not result.normalized_items:
            return ()
        if not isinstance(body, dict) or not isinstance(body.get("pois"), list):
            raise StationDistanceEnrichmentError("AMap POI-around response body is unavailable")
        raw_by_id = {
            raw.get("id"): raw
            for raw in body["pois"]
            if isinstance(raw, dict) and isinstance(raw.get("id"), str)
        }
        candidates: List[Mapping[str, Any]] = []
        for item in result.normalized_items:
            if not isinstance(item, dict) or not _rail_station_category(item.get("category")):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                raise StationDistanceEnrichmentError("AMap POI-around station name has the wrong shape")
            claim_ids = item.get("claim_ids")
            if not isinstance(claim_ids, list):
                raise StationDistanceEnrichmentError("AMap POI-around identity claims are missing")
            identity = _single_identity_claim(claim_ids, result.claims)
            if not isinstance(identity, dict):
                raise StationDistanceEnrichmentError("AMap POI-around identity is ambiguous")
            raw = raw_by_id.get(identity.get("provider_poi_id"))
            if not isinstance(raw, dict):
                raise StationDistanceEnrichmentError("AMap POI-around raw identity does not match normalization")
            distance = _nonnegative_float(raw.get("distance"))
            if distance is None:
                raise StationDistanceEnrichmentError("AMap POI-around distance is invalid")
            candidates.append({"station_name": name.strip(), "distance_meters": distance})
        return tuple(candidates)

    def _place_centre(self, city: str, parent: ProviderRequest) -> Optional[Point]:
        """Find a place's own coordinates through AMap POI search, not geocoding.

        `_city_centre` below requires the geocoded result's own city/district
        to admin-match `city`, which is correct for a real administrative
        city (used by `enrich()`) but wrong for `find_nearby_stations`'s
        callers: a scenic spot or island name such as 鼓浪屿/湄洲岛 is never
        itself a city or district, so AMap's structured-address geocoder
        treats it as a bare street-name fragment and matches unrelated
        same-named streets nationwide, never the actual place -- confirmed
        against the real API before writing this. A landmark-style POI
        keyword search finds it correctly instead. Since the only use of the
        result is a rough anchor for a wide-radius (up to
        `NEARBY_STATION_SEARCH_RADIUS_METERS`) nearby-station search -- never
        the identity of a specific station, which stays cross-checked against
        12306 regardless -- the top AMap result whose name contains the query
        is precise enough; this does not need `_unique_point`'s
        exact-coordinate agreement across every match.
        """

        request = self._request(
            parent,
            capability="poi",
            identity=(city, "place-centre"),
            parameters={
                "keywords": city,
                "city": city,
                "city_limit": "false",
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
        for item in result.normalized_items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or city not in name:
                continue
            claim_ids = item.get("claim_ids")
            identity = _single_identity_claim(claim_ids, result.claims) if isinstance(claim_ids, list) else None
            provider_poi_id = identity.get("provider_poi_id") if isinstance(identity, dict) else None
            raw = raw_by_id.get(provider_poi_id)
            if not isinstance(raw, dict):
                continue
            point = _location_point(raw.get("location"))
            if point is not None:
                return point
        return None

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
            if (
                not isinstance(item, dict)
                or not _city_or_district_matches(city, item.get("city"), item.get("district"))
            ):
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

    def _station_point(
        self,
        city: str,
        station_name: str,
        parent: ProviderRequest,
        *,
        nationwide: bool = False,
        centre: Optional[Point] = None,
        max_distance_meters: Optional[float] = None,
    ) -> Tuple[Optional[Point], bool]:
        """Find one station's coordinates by name.

        `nationwide=False` (the default, first-pass) query is AMap
        `city_limit=true` and additionally requires the POI's own city or
        district to match `city`. `nationwide=True` (the cross-city retry)
        drops both the AMap city limit and that match, since the point is
        for a same-named station outside `city`'s own administrative area;
        it instead requires the point be within `max_distance_meters` of
        `centre`, so a same-named station on the other side of the country
        is never mistaken for a local one.

        Returns `(point, found_any_poi)`. `found_any_poi` says whether AMap
        returned any raw POI at all for this keyword, regardless of whether
        it went on to match; the caller uses it to skip the nationwide retry
        for a keyword AMap has no opinion about in the first place.
        """

        request = self._request(
            parent,
            capability="poi",
            identity=(city, station_name, "nationwide" if nationwide else "city"),
            parameters={
                "keywords": station_name,
                "city": city,
                "city_limit": "false" if nationwide else "true",
                "page_size": 5,
                "page_num": 1,
            },
        )
        result, body = self._query(request)
        if not result.normalized_items:
            return None, False
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
                or not _rail_station_category(item.get("category"))
            ):
                continue
            claim_ids = item.get("claim_ids")
            identity = _single_identity_claim(claim_ids, result.claims) if isinstance(claim_ids, list) else None
            district = identity.get("district") if isinstance(identity, dict) else None
            if not nationwide and not _city_or_district_matches(city, item.get("city"), district):
                continue
            if not isinstance(claim_ids, list):
                raise StationDistanceEnrichmentError("AMap POI identity claims are missing")
            if not isinstance(identity, dict):
                raise StationDistanceEnrichmentError("AMap POI identity is ambiguous")
            provider_poi_id = identity.get("provider_poi_id")
            raw = raw_by_id.get(provider_poi_id)
            if not isinstance(raw, dict):
                raise StationDistanceEnrichmentError("AMap POI raw identity does not match normalization")
            point = _location_point(raw.get("location"))
            if point is None:
                continue
            if nationwide and centre is not None and max_distance_meters is not None:
                if haversine_meters(centre.lng, centre.lat, point.lng, point.lat) > max_distance_meters:
                    continue
            points.append(point)
        return _unique_point(points), True

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
    expected_key = administrative_area_key(expected)
    return bool(expected_key) and expected_key == administrative_area_key(actual)


def _city_or_district_matches(expected: str, city: Any, district: Any) -> bool:
    """A researched city may match either the provider's city or its district.

    Same administrative-area rule as mobility.py's `_poi_admin_matches`: a
    district/county name on one side and its enclosing city on the other is
    not a false mismatch.
    """

    if _city_matches(expected, city):
        return True
    return isinstance(district, str) and _city_matches(expected, district)


def _single_identity_claim(
    claim_ids: Sequence[Any], claims: Sequence[Mapping[str, Any]],
) -> Optional[Mapping[str, Any]]:
    identities = [
        claim.get("value") for claim in claims
        if claim.get("claim_id") in claim_ids and claim.get("field_path") == "/provider_identity"
    ]
    return identities[0] if len(identities) == 1 and isinstance(identities[0], dict) else None


def _rail_station_category(value: Any) -> bool:
    return isinstance(value, str) and ("火车站" in value or "铁路" in value)


def _coordinate_record_point(value: Any) -> Optional[Point]:
    if not isinstance(value, dict):
        return None
    coordinates = value.get("gcj02")
    if not isinstance(coordinates, dict):
        return None
    return _point(coordinates.get("lng"), coordinates.get("lat"))


def _nonnegative_float(value: Any) -> Optional[float]:
    """Parse an AMap numeric-shaped field that may arrive as a JSON string."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


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
