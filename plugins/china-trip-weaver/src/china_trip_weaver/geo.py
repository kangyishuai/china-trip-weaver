"""Explicit, single-pass WGS-84 / GCJ-02 coordinate conversion."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .clock import Clock, isoformat_seconds


_A = 6378245.0
_EE = 0.00669342162296594323
_X_PI = math.pi * 3000.0 / 180.0


@dataclass(frozen=True)
class Point:
    lng: float
    lat: float

    def as_dict(self) -> Dict[str, float]:
        return {"lng": round(self.lng, 7), "lat": round(self.lat, 7)}


def outside_mainland_china(point: Point) -> bool:
    return point.lng < 72.004 or point.lng > 137.8347 or point.lat < 0.8293 or point.lat > 55.8271


def _transform_lat(x: float, y: float) -> float:
    value = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    value += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    value += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    value += (160.0 * math.sin(y / 12.0 * math.pi) + 320 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return value


def _transform_lng(x: float, y: float) -> float:
    value = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    value += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    value += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    value += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return value


def wgs84_to_gcj02(point: Point) -> Point:
    if outside_mainland_china(point):
        return point
    delta_lat = _transform_lat(point.lng - 105.0, point.lat - 35.0)
    delta_lng = _transform_lng(point.lng - 105.0, point.lat - 35.0)
    rad_lat = point.lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - _EE * magic * magic
    sqrt_magic = math.sqrt(magic)
    delta_lat = (delta_lat * 180.0) / ((_A * (1 - _EE)) / (magic * sqrt_magic) * math.pi)
    delta_lng = (delta_lng * 180.0) / (_A / sqrt_magic * math.cos(rad_lat) * math.pi)
    return Point(point.lng + delta_lng, point.lat + delta_lat)


def gcj02_to_wgs84(point: Point) -> Point:
    if outside_mainland_china(point):
        return point
    estimate = Point(point.lng, point.lat)
    for _ in range(8):
        projected = wgs84_to_gcj02(estimate)
        estimate = Point(estimate.lng - (projected.lng - point.lng), estimate.lat - (projected.lat - point.lat))
    return estimate


def bd09_to_gcj02(point: Point) -> Point:
    x = point.lng - 0.0065
    y = point.lat - 0.006
    z = math.sqrt(x * x + y * y) - 0.00002 * math.sin(y * _X_PI)
    theta = math.atan2(y, x) - 0.000003 * math.cos(x * _X_PI)
    return Point(z * math.cos(theta), z * math.sin(theta))


def coordinate_record(source_crs: str, native: Point, clock: Clock, accuracy_m: Optional[float] = None) -> Dict[str, Any]:
    native_dict = native.as_dict()
    if source_crs == "provider-unknown":
        return {
            "source_crs": source_crs,
            "native": native_dict,
            "wgs84": None,
            "gcj02": None,
            "conversion": {
                "status": "unavailable",
                "method": "none-unknown-source-crs",
                "version": "ctw-1",
                "derived_fields": [],
                "converted_at": None,
                "accuracy_m": None,
            },
        }
    if source_crs == "WGS84":
        converted = wgs84_to_gcj02(native)
        outside = outside_mainland_china(native)
        return {
            "source_crs": source_crs,
            "native": native_dict,
            "wgs84": native_dict,
            "gcj02": converted.as_dict(),
            "conversion": {
                "status": "not-needed" if outside else "converted",
                "method": "identity-outside-mainland" if outside else "wgs84-to-gcj02",
                "version": "ctw-1",
                "derived_fields": [] if outside else ["gcj02"],
                "converted_at": None if outside else isoformat_seconds(clock),
                "accuracy_m": accuracy_m,
            },
        }
    if source_crs == "GCJ02":
        converted = gcj02_to_wgs84(native)
        outside = outside_mainland_china(native)
        return {
            "source_crs": source_crs,
            "native": native_dict,
            "wgs84": converted.as_dict(),
            "gcj02": native_dict,
            "conversion": {
                "status": "not-needed" if outside else "converted",
                "method": "identity-outside-mainland" if outside else "gcj02-to-wgs84-iterative",
                "version": "ctw-1",
                "derived_fields": [] if outside else ["wgs84"],
                "converted_at": None if outside else isoformat_seconds(clock),
                "accuracy_m": accuracy_m,
            },
        }
    if source_crs == "BD09":
        gcj = bd09_to_gcj02(native)
        wgs = gcj02_to_wgs84(gcj)
        return {
            "source_crs": source_crs,
            "native": native_dict,
            "wgs84": wgs.as_dict(),
            "gcj02": gcj.as_dict(),
            "conversion": {
                "status": "converted",
                "method": "bd09-to-gcj02-to-wgs84",
                "version": "ctw-1",
                "derived_fields": ["wgs84", "gcj02"],
                "converted_at": isoformat_seconds(clock),
                "accuracy_m": accuracy_m,
            },
        }
    raise ValueError("unsupported source CRS: %s" % source_crs)
