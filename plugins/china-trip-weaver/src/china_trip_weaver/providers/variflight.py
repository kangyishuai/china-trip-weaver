"""Pinned VariFlight MCP enrichment adapter."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Mapping

from ..clock import Clock
from ..contracts import ProviderRequest
from ..evidence import make_claim
from .base import BaseAdapter, ContractMismatch, Normalization, sanitize_text, stable_id


EXPECTED_TOOLS = (
    "searchFlightsByDepArr",
    "searchFlightsByNumber",
    "getFlightTransferInfo",
    "flightHappinessIndex",
    "getRealtimeLocationByAnum",
    "getTodayDate",
    "getFutureWeatherByAirport",
    "searchFlightItineraries",
    "getFlightPriceByCities",
)


class VariFlightAdapter(BaseAdapter):
    provider = "variflight"
    provider_version = "1.0.3"
    capabilities = ("flight", "weather")
    required_secret_names = ("VARIFLIGHT_API_KEY", "X_VARIFLIGHT_KEY")
    allow_keyless = False

    def normalize(self, body: Any, request: ProviderRequest, clock: Clock) -> Normalization:
        if not isinstance(body, dict) or tuple(body.get("tools", ())) != EXPECTED_TOOLS:
            raise ContractMismatch("VariFlight 9-tool fingerprint mismatch")
        content = body.get("content")
        if not isinstance(content, list) or not content or not isinstance(content[0].get("text"), str):
            raise ContractMismatch("VariFlight content is not text JSON")
        payload = json.loads(content[0]["text"])
        tool = body.get("tool")
        if tool in ("searchFlightsByDepArr", "flightHappinessIndex"):
            return self._live_payload(tool, payload, request, clock)
        if not isinstance(payload, dict) or not isinstance(payload.get("kind"), str):
            raise ContractMismatch("VariFlight payload kind is missing")
        kind = payload["kind"]
        if kind in ("weather", "comfort"):
            subject = sanitize_text(request.parameters.get("subject_ref", "flight-candidate"), 80)
            evidence = make_claim(
                subject_ref=subject,
                field_path="/" + kind,
                value=sanitize_text(payload["summary"], 300),
                source_url="https://mcp.variflight.com/", provider=self.provider,
                status="verified", confidence=0.8, mode="live", clock=clock,
            )
            return Normalization((), (evidence,))
        if kind not in ("flights", "raw_price") or not isinstance(payload.get("items"), list):
            raise ContractMismatch("VariFlight business response shape drifted")
        items: List[Mapping[str, Any]] = []
        claims: List[Mapping[str, Any]] = []
        for raw in payload["items"]:
            service = sanitize_text(raw["flight_no"], 32)
            depart = raw["depart_at"]
            arrive = raw["arrive_at"]
            amount = raw.get("price")
            if amount is not None and (not isinstance(amount, (int, float)) or isinstance(amount, bool)):
                raise ContractMismatch("VariFlight raw price is not numeric")
            leg_id = stable_id("leg-vf", service, depart, request.parameters["from_ref"], request.parameters["to_ref"])
            flight_claim = make_claim(
                subject_ref=leg_id, field_path="/depart_at", value={"depart_at": depart, "arrive_at": arrive},
                source_url="https://mcp.variflight.com/", provider=self.provider,
                status="verified", confidence=0.85, mode="live", clock=clock,
            )
            price_claim = make_claim(
                subject_ref=leg_id, field_path="/price", value=amount,
                source_url="https://mcp.variflight.com/", provider=self.provider,
                status="partial" if amount is not None else "unknown",
                confidence=0.7 if amount is not None else 0, mode="live", clock=clock,
            )
            items.append({
                "leg_id": leg_id, "travel_mode": "flight", "data_mode": "live",
                "from_ref": request.parameters["from_ref"], "to_ref": request.parameters["to_ref"],
                "depart_at": depart, "arrive_at": arrive,
                "duration_minutes": int(raw["duration_minutes"]),
                "provider": self.provider, "service_number": service,
                "price": {
                    "amount": amount, "currency": "CNY",
                    "price_type": "live" if amount is not None else "unknown",
                    "unit": "per_person", "includes_taxes": None,
                    "queried_at": price_claim["queried_at"], "claim_id": price_claim["claim_id"],
                },
                "booking_url": None,
                "claim_ids": [flight_claim["claim_id"], price_claim["claim_id"]],
                "locked": False,
            })
            claims.extend((flight_claim, price_claim))
        return Normalization(tuple(items), tuple(claims))

    def _live_payload(
        self,
        tool: str,
        payload: Any,
        request: ProviderRequest,
        clock: Clock,
    ) -> Normalization:
        if not isinstance(payload, dict) or payload.get("code") != 200 or payload.get("message") != "Success":
            raise ContractMismatch("VariFlight live envelope changed")
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ContractMismatch("VariFlight live data is not a list")
        if tool == "flightHappinessIndex":
            return self._live_comfort(rows, request, clock)
        if request.parameters.get("candidate_mode") is True:
            return self._live_candidates(rows, request, clock)

        subject_refs = request.parameters.get("subject_refs_by_service")
        if not isinstance(subject_refs, dict):
            raise ContractMismatch("VariFlight search requires service-to-subject mapping")
        claims = []
        for raw in rows:
            if not isinstance(raw, dict):
                raise ContractMismatch("VariFlight flight row is not an object")
            service = sanitize_text(raw.get("FlightNo"), 32)
            subject_ref = subject_refs.get(service)
            if not isinstance(subject_ref, str):
                continue
            depart = _live_datetime(raw.get("FlightDeptimePlanDate"))
            arrive = _live_datetime(raw.get("FlightArrtimePlanDate"))
            value = {
                "flight_no": service,
                "state": _optional_text(raw.get("FlightState"), 80),
                "state_code": raw.get("FlightStateNum") if isinstance(raw.get("FlightStateNum"), int) else None,
                "depart_at": depart,
                "arrive_at": arrive,
                "dep_airport": _optional_text(raw.get("FlightDepcode"), 12),
                "arr_airport": _optional_text(raw.get("FlightArrcode"), 12),
                "on_time_rate": _optional_text(raw.get("OntimeRate"), 20),
                "arrival_on_time_rate": _optional_text(raw.get("ArrOntimeRate"), 20),
            }
            claims.append(make_claim(
                subject_ref=subject_ref,
                field_path="/status",
                value=value,
                source_url="https://mcp.variflight.com/",
                provider=self.provider,
                status="verified",
                confidence=0.9,
                mode="live",
                clock=clock,
            ))
        return Normalization((), tuple(claims))

    def _live_candidates(
        self,
        rows: List[Any],
        request: ProviderRequest,
        clock: Clock,
    ) -> Normalization:
        from_ref = request.parameters.get("from_ref")
        to_ref = request.parameters.get("to_ref")
        if not isinstance(from_ref, str) or not isinstance(to_ref, str):
            raise ContractMismatch("VariFlight candidate endpoints are missing")
        items: List[Mapping[str, Any]] = []
        claims: List[Mapping[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                raise ContractMismatch("VariFlight flight row is not an object")
            service = sanitize_text(raw.get("FlightNo"), 32)
            depart = _live_datetime(raw.get("FlightDeptimePlanDate"))
            arrive = _live_datetime(raw.get("FlightArrtimePlanDate"))
            duration = _duration_minutes(depart, arrive)
            leg_id = stable_id("leg-vf", service, depart, from_ref, to_ref)
            schedule_claim = make_claim(
                subject_ref=leg_id,
                field_path="/depart_at",
                value={"depart_at": depart, "arrive_at": arrive},
                source_url="https://mcp.variflight.com/",
                provider=self.provider,
                status="verified",
                confidence=0.85,
                mode="live",
                clock=clock,
            )
            status_claim = make_claim(
                subject_ref=leg_id,
                field_path="/status",
                value=_live_status_value(raw, service, depart, arrive),
                source_url="https://mcp.variflight.com/",
                provider=self.provider,
                status="verified",
                confidence=0.9,
                mode="live",
                clock=clock,
            )
            price_claim = make_claim(
                subject_ref=leg_id,
                field_path="/price",
                value=None,
                source_url="https://mcp.variflight.com/",
                provider=self.provider,
                status="unknown",
                confidence=0,
                mode="live",
                clock=clock,
            )
            items.append({
                "leg_id": leg_id,
                "travel_mode": "flight",
                "data_mode": "live",
                "from_ref": sanitize_text(from_ref, 80),
                "to_ref": sanitize_text(to_ref, 80),
                "depart_at": depart,
                "arrive_at": arrive,
                "duration_minutes": duration,
                "provider": self.provider,
                "service_number": service,
                "price": {
                    "amount": None,
                    "currency": "CNY",
                    "price_type": "verify-on-click",
                    "unit": "per_person",
                    "includes_taxes": None,
                    "queried_at": price_claim["queried_at"],
                    "claim_id": price_claim["claim_id"],
                },
                "booking_url": None,
                "claim_ids": [
                    schedule_claim["claim_id"], status_claim["claim_id"],
                    price_claim["claim_id"],
                ],
                "locked": False,
            })
            claims.extend((schedule_claim, status_claim, price_claim))
        return Normalization(tuple(items), tuple(claims))

    def _live_comfort(
        self,
        rows: List[Any],
        request: ProviderRequest,
        clock: Clock,
    ) -> Normalization:
        subject_ref = request.parameters.get("subject_ref")
        flight_no = request.parameters.get("flight_no")
        if not isinstance(subject_ref, str) or not isinstance(flight_no, str):
            raise ContractMismatch("VariFlight comfort subject is missing")
        raw = next((item for item in rows if isinstance(item, dict) and item.get("FlightNo") == flight_no), None)
        if raw is None:
            return Normalization((), ())
        value: Dict[str, Any] = {"flight_no": flight_no}
        fields = {
            "OntimeRate": "on_time_rate",
            "ArrOntimeRate": "arrival_on_time_rate",
            "GenericNew": "aircraft_type",
            "FlightYear": "aircraft_age_years",
            "SeatWidth": "seat_width",
            "SeatSpace": "seat_space",
            "SeatTilt": "seat_tilt",
            "Seatlayout": "seat_layout",
            "Food": "food",
            "WiFi": "wifi",
            "Socket": "power",
            "Luggage": "luggage",
            "Comfort": "comfort",
        }
        for source, target in fields.items():
            text = _optional_text(raw.get(source), 160)
            if text is not None:
                value[target] = text
        claim = make_claim(
            subject_ref=subject_ref,
            field_path="/comfort",
            value=value,
            source_url="https://mcp.variflight.com/",
            provider=self.provider,
            status="verified",
            confidence=0.8,
            mode="live",
            clock=clock,
        )
        return Normalization((), (claim,))


def _live_datetime(value: Any) -> str:
    if not isinstance(value, str):
        raise ContractMismatch("VariFlight planned datetime is missing")
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError as exc:
        raise ContractMismatch("VariFlight planned datetime is invalid") from exc
    if parsed.tzinfo is None:
        return parsed.isoformat(timespec="seconds") + "+08:00"
    return parsed.isoformat(timespec="seconds")


def _duration_minutes(depart_at: str, arrive_at: str) -> int:
    depart = datetime.fromisoformat(depart_at)
    arrive = datetime.fromisoformat(arrive_at)
    duration = int((arrive - depart).total_seconds() // 60)
    if duration <= 0:
        raise ContractMismatch("VariFlight planned duration is invalid")
    return duration


def _live_status_value(
    raw: Mapping[str, Any],
    service: str,
    depart: str,
    arrive: str,
) -> Mapping[str, Any]:
    return {
        "flight_no": service,
        "state": _optional_text(raw.get("FlightState"), 80),
        "state_code": raw.get("FlightStateNum") if isinstance(raw.get("FlightStateNum"), int) else None,
        "depart_at": depart,
        "arrive_at": arrive,
        "dep_airport": _optional_text(raw.get("FlightDepcode"), 12),
        "arr_airport": _optional_text(raw.get("FlightArrcode"), 12),
        "on_time_rate": _optional_text(raw.get("OntimeRate"), 20),
        "arrival_on_time_rate": _optional_text(raw.get("ArrOntimeRate"), 20),
    }


def _optional_text(value: Any, maximum: int) -> Any:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        return None
    return sanitize_text(value, maximum)
