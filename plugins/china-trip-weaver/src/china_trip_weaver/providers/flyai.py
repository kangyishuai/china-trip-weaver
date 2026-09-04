"""Pinned FlyAI 1.0.16 stdout-envelope adapter."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, List, Mapping, Optional, Sequence, Tuple

from ..clock import Clock
from ..contracts import ProviderRequest
from ..evidence import make_claim
from ..geo import Point, coordinate_record
from .base import BaseAdapter, ContractMismatch, Normalization, ProviderFailure, safe_https_url, sanitize_text, stable_id


class FlyAIAdapter(BaseAdapter):
    provider = "flyai"
    provider_version = "1.0.16"
    capabilities = ("flight", "lodging")
    required_secret_names = ("FLYAI_API_KEY",)
    allow_keyless = True

    def normalize(self, body: Any, request: ProviderRequest, clock: Clock) -> Normalization:
        if not isinstance(body, dict):
            raise ContractMismatch("FlyAI stdout is not JSON")
        if body.get("cliVersion") != self.provider_version:
            raise ContractMismatch("FlyAI CLI version mismatch")
        commands = body.get("commands")
        if not isinstance(commands, list) or commands != ["search-hotel", "search-flight"]:
            raise ContractMismatch("FlyAI help fingerprint mismatch")
        probe = body.get("probe")
        if not isinstance(probe, dict) or probe.get("command") not in commands or not isinstance(probe.get("flags"), list):
            raise ContractMismatch("FlyAI command help fingerprint is missing")
        if body.get("status") in (401, 403):
            raise ProviderFailure("forbidden", "FlyAI rejected the credential")
        if body.get("status") == 429:
            raise ProviderFailure("rate_limited", "FlyAI quota response")
        if (
            body.get("status") == 1
            and body.get("data") is None
            and isinstance(body.get("message"), str)
            and ("结果为空" in body["message"] or "no result" in body["message"].lower())
        ):
            return Normalization((), ())
        if body.get("status") != 0 or body.get("message") != "success" or not isinstance(body.get("data"), dict):
            raise ContractMismatch("FlyAI success envelope changed")
        item_list = body["data"].get("itemList")
        if not isinstance(item_list, list):
            raise ContractMismatch("FlyAI itemList is missing")
        items: List[Mapping[str, Any]] = []
        claims: List[Mapping[str, Any]] = []
        for raw in item_list:
            if request.capability == "flight":
                item, item_claims = self._flight(raw, request, clock)
            else:
                item, item_claims = self._lodging(raw, request, clock)
            items.append(item)
            claims.extend(item_claims)
        return Normalization(tuple(items), tuple(claims))

    def _flight(self, raw: Mapping[str, Any], request: ProviderRequest, clock: Clock) -> Tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]:
        if not isinstance(raw, dict):
            raise ContractMismatch("FlyAI flight item is not an object")
        journeys = raw.get("journeys")
        if not isinstance(journeys, list) or not journeys or not isinstance(journeys[0], dict) or not isinstance(journeys[0].get("segments"), list) or not journeys[0]["segments"]:
            raise ContractMismatch("FlyAI flight segments are missing")
        segments = journeys[0]["segments"]
        if any(not isinstance(item, dict) for item in segments):
            raise ContractMismatch("FlyAI flight segment is not an object")
        first = segments[0]
        last = segments[-1]
        amount, price_type, price_value = _price(raw.get("ticketPrice", raw.get("adultPrice")), require_numeric=True)
        service = "/".join(sanitize_text(item.get("marketingTransportNo", item.get("transportNo")), 32) for item in segments)
        depart_at = _iso_with_zone(first.get("depDateTime", first.get("departureDateTime")))
        arrive_at = _iso_with_zone(last.get("arrDateTime", last.get("arrivalDateTime")))
        leg_id = stable_id("leg-air", service, depart_at, request.parameters["from_ref"], request.parameters["to_ref"])
        detail = safe_https_url(raw["jumpUrl"])
        schedule_claim = make_claim(
            subject_ref=leg_id, field_path="/depart_at",
            value={"depart_at": depart_at, "arrive_at": arrive_at},
            source_url=detail, provider=self.provider,
            status="verified", confidence=0.75, mode="live", clock=clock,
        )
        price_claim = make_claim(
            subject_ref=leg_id, field_path="/price", value=price_value,
            source_url=detail, provider=self.provider,
            status="partial", confidence=0.65, mode="live", clock=clock,
        )
        duration = int(raw.get("totalDuration", journeys[0].get("totalDuration", first.get("duration", first.get("durationMinutes")))))
        if duration <= 0:
            raise ContractMismatch("FlyAI flight duration is invalid")
        return ({
            "leg_id": leg_id,
            "travel_mode": "flight",
            "data_mode": "live",
            "from_ref": sanitize_text(request.parameters["from_ref"], 80),
            "to_ref": sanitize_text(request.parameters["to_ref"], 80),
            "depart_at": depart_at,
            "arrive_at": arrive_at,
            "duration_minutes": duration,
            "provider": self.provider,
            "service_number": service,
            "price": {
                "amount": amount, "currency": "CNY", "price_type": price_type,
                "unit": "per_person", "includes_taxes": None,
                "queried_at": price_claim["queried_at"], "claim_id": price_claim["claim_id"],
            },
            "booking_url": detail,
            "claim_ids": [schedule_claim["claim_id"], price_claim["claim_id"]],
            "locked": False,
        }, (schedule_claim, price_claim))

    def _lodging(self, raw: Mapping[str, Any], request: ProviderRequest, clock: Clock) -> Tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]:
        if not isinstance(raw, dict):
            raise ContractMismatch("FlyAI lodging item is not an object")
        name = sanitize_text(raw["name"], 160)
        detail = safe_https_url(raw["detailUrl"])
        lodging_id = stable_id("lodging-flyai", raw.get("shId"), name, request.parameters["check_in"])
        context_required = _has_lodging_request_context(request.parameters)
        context = _matching_lodging_context(raw, request.parameters) if context_required else None
        amount, price_type, price_value = _price(
            raw.get("price"),
            require_numeric=False,
            live_allowed=not context_required or context is not None,
        )
        price_claim = make_claim(
            subject_ref=lodging_id, field_path="/price", value=price_value,
            source_url=detail, provider=self.provider,
            status="partial" if amount is not None else "unknown",
            confidence=0.55 if amount is not None else 0,
            mode="live", clock=clock,
        )
        coordinates = None
        if raw.get("longitude") is not None and raw.get("latitude") is not None:
            coordinates = coordinate_record("provider-unknown", Point(float(raw["longitude"]), float(raw["latitude"])), clock)
        return ({
            "lodging_id": lodging_id,
            "name": name,
            "city": sanitize_text(request.parameters["city"], 80),
            "area": sanitize_text(raw.get("area") or raw.get("interestsPoi") or raw.get("address") or request.parameters["city"], 120),
            "check_in": request.parameters["check_in"],
            "check_out": request.parameters["check_out"],
            "coordinates": coordinates,
            "price": {
                "amount": amount, "currency": "CNY", "price_type": price_type,
                "unit": "per_night",
                "includes_taxes": context["includes_taxes"] if context is not None else None,
                "queried_at": price_claim["queried_at"], "claim_id": price_claim["claim_id"],
            },
            "deep_links": [detail],
            "claim_ids": [price_claim["claim_id"]],
            "locked": False,
        }, (price_claim,))


def _iso_with_zone(value: Any) -> str:
    if not isinstance(value, str):
        raise ContractMismatch("FlyAI datetime is not text")
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError as exc:
        raise ContractMismatch("FlyAI datetime is invalid") from exc
    if parsed.tzinfo is None:
        return parsed.isoformat(timespec="seconds") + "+08:00"
    return parsed.isoformat(timespec="seconds")


MASKED_PRICE_RE = re.compile(r"^[¥￥]\d*x+$", re.IGNORECASE)
EXACT_CNY_PRICE_RE = re.compile(r"^[¥￥](\d+(?:\.\d{1,2})?)$")


def _price(
    value: Any,
    *,
    require_numeric: bool,
    live_allowed: bool = True,
) -> Tuple[Optional[float], str, Any]:
    if isinstance(value, bool) or value is None:
        if require_numeric:
            raise ContractMismatch("FlyAI price lacks numeric context")
        return None, "verify-on-click", None
    if isinstance(value, (int, float)):
        if not live_allowed:
            return None, "verify-on-click", None
        return float(value), "live", float(value)
    if isinstance(value, str):
        text = value.strip()
        exact_cny = EXACT_CNY_PRICE_RE.fullmatch(text)
        if exact_cny:
            amount = float(exact_cny.group(1))
            if not live_allowed:
                return None, "verify-on-click", None
            return amount, "live", amount
        try:
            amount = float(text)
        except ValueError:
            if not require_numeric and MASKED_PRICE_RE.fullmatch(text):
                return None, "verify-on-click", text
            raise ContractMismatch("FlyAI price lacks numeric context")
        if not live_allowed:
            return None, "verify-on-click", None
        return amount, "live", amount
    raise ContractMismatch("FlyAI price has an unsupported type")


LODGING_REQUEST_CONTEXT_FIELDS = frozenset((
    "party", "rooms", "adult_count", "occupancy", "bed_config",
    "parking_required", "cancellation_preference",
))


def _has_lodging_request_context(parameters: Mapping[str, Any]) -> bool:
    """Identify the context-aware request contract used by every public caller."""

    return bool(LODGING_REQUEST_CONTEXT_FIELDS.intersection(parameters))


def _matching_lodging_context(
    raw: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> Optional[Mapping[str, Any]]:
    """Return complete matching quote context, or ``None`` to force degradation."""

    context = raw.get("lodgingContext")
    if not isinstance(context, dict):
        return None
    cancellation_policy = context.get("cancellation_policy")
    if not isinstance(cancellation_policy, str) or not cancellation_policy.strip():
        return None
    includes_taxes = context.get("includes_taxes")
    if not isinstance(includes_taxes, bool):
        return None
    required_matches = (
        ("check_in", parameters.get("check_in")),
        ("check_out", parameters.get("check_out")),
        ("party", parameters.get("party")),
        ("rooms", parameters.get("rooms")),
        ("adult_count", parameters.get("adult_count")),
        ("occupancy", parameters.get("occupancy")),
        ("bed_config", parameters.get("bed_config")),
        ("parking_required", parameters.get("parking_required")),
        ("cancellation_preference", parameters.get("cancellation_preference")),
    )
    if any(context.get(name) != expected for name, expected in required_matches):
        return None
    return context
