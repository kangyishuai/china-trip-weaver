"""Pinned 12306 MCP adapter for raw recorded or live MCP tool results."""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..clock import Clock
from ..contracts import AdapterResult, ProviderRequest
from ..evidence import make_claim
from .base import (
    BaseAdapter,
    ContractMismatch,
    Normalization,
    ProviderContext,
    ProviderFailure,
    sanitize_text,
    stable_id,
)
from .mcp_stdio import EXPECTED_12306_TOOLS


EXPECTED_TOOLS = EXPECTED_12306_TOOLS
MCP_PROTOCOL_VERSION = "2025-06-18"
PRESALE_DAYS = 15
NO_INVENTORY = frozenset(("", "无", "--", "候补", "售罄", "not available"))


def _minutes(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and re.fullmatch(r"\d{1,3}:\d{2}", value):
        hours, minutes = value.split(":")
        if int(minutes) < 60:
            return int(hours) * 60 + int(minutes)
    raise ContractMismatch("rail duration has wrong shape")


class Rail12306Adapter(BaseAdapter):
    provider = "12306-mcp"
    provider_version = "0.3.10"
    capabilities = ("rail", "station")

    def query(self, request: ProviderRequest, context: ProviderContext) -> AdapterResult:
        result = super().query(request, context)
        if "station_resolution_ambiguous" not in result.warnings:
            return result
        return AdapterResult.build(
            provider=result.provider,
            provider_version=result.provider_version,
            capability=result.capability,
            mode=result.mode,
            queried_at=result.queried_at,
            normalized_items=result.normalized_items,
            claims=result.claims,
            health=self._health(
                "ready",
                "ambiguous: multiple station candidates require caller selection",
                result.mode,
                context.clock,
            ),
            warnings=result.warnings,
            raw_ref=result.raw_ref,
            response_hash=result.response_hash,
            error_class="ambiguous",
        )

    def normalize(self, body: Any, request: ProviderRequest, clock: Clock) -> Normalization:
        transcript = _transcript(body)
        calls = transcript["calls"]
        if request.capability == "station":
            call = _single_call(calls, ("get-stations-code-in-city", "get-station-code-of-citys"))
            payload = _call_payload(call, request, clock)
            return Normalization(tuple(_stations(payload, request)), ())

        resolution_status, station_candidates = _station_resolution(transcript, request)
        if resolution_status in ("no_results", "ambiguous"):
            if any(call.get("name") in ("get-tickets", "get-interline-tickets") for call in calls):
                raise ContractMismatch("12306 queried tickets before station ambiguity was resolved")
            if resolution_status == "no_results":
                return Normalization((), (), ("station_resolution_no_results",))
            return Normalization(station_candidates, (), ("station_resolution_ambiguous", "ambiguous"))

        call = _single_call(calls, ("get-tickets", "get-interline-tickets"))
        payload = _call_payload(call, request, clock)
        if not isinstance(payload, list):
            raise ContractMismatch("12306 ticket text must decode to an array")
        raw_tickets: Iterable[Any]
        if call["name"] == "get-interline-tickets":
            flattened: List[Any] = []
            for itinerary in payload:
                if not isinstance(itinerary, dict) or not isinstance(itinerary.get("ticketList"), list):
                    raise ContractMismatch("12306 interline result has the wrong shape")
                flattened.extend(itinerary["ticketList"])
            raw_tickets = flattened
        else:
            raw_tickets = payload

        items: List[Mapping[str, Any]] = []
        claims: List[Mapping[str, Any]] = []
        for raw in raw_tickets:
            if not isinstance(raw, dict):
                raise ContractMismatch("12306 ticket item is not an object")
            leg, leg_claims = self._ticket(raw, request, clock)
            items.append(leg)
            claims.extend(leg_claims)
        return Normalization(tuple(items), tuple(claims))

    def _failure(self, error_class: str, reason: str, request: ProviderRequest, clock: Clock) -> AdapterResult:
        if error_class == "no_results" and reason.startswith("outside_presale_window"):
            return AdapterResult.build(
                provider=self.provider,
                provider_version=self.provider_version,
                capability=request.capability,
                mode="static",
                queried_at=clock.now().isoformat(timespec="seconds"),
                normalized_items=(),
                claims=(),
                health=self._health(
                    "degraded",
                    "no_results: requested date is outside the 12306 %d-day presale window" % PRESALE_DAYS,
                    "static",
                    clock,
                ),
                warnings=("no_results", "outside_presale_window"),
                error_class="no_results",
            )
        return super()._failure(error_class, reason, request, clock)

    def _ticket(self, raw: Mapping[str, Any], request: ProviderRequest, clock: Clock) -> Tuple[Mapping[str, Any], Sequence[Mapping[str, Any]]]:
        service = sanitize_text(raw["start_train_code"], 32)
        depart_at = _rail_datetime(raw["start_date"], raw["start_time"])
        arrive_at = _rail_datetime(raw.get("arrive_date", raw["start_date"]), raw["arrive_time"])
        duration = _minutes(raw["lishi"])
        from_ref = sanitize_text(request.parameters["from_ref"], 80)
        to_ref = sanitize_text(request.parameters["to_ref"], 80)
        leg_id = stable_id("leg-rail", service, depart_at, from_ref, to_ref)
        source_url = _deep_link(raw, request)

        prices = raw.get("prices")
        if not isinstance(prices, list) or not all(isinstance(entry, dict) for entry in prices):
            raise ContractMismatch("12306 prices are missing")
        availability = tuple(_seat(entry) for entry in prices)
        price_entry = _select_price(availability)
        amount = price_entry["price"] if price_entry is not None else None

        time_claim = make_claim(
            subject_ref=leg_id,
            field_path="/depart_at",
            value={"depart_at": depart_at, "arrive_at": arrive_at, "duration_minutes": duration},
            source_url=source_url,
            provider=self.provider,
            status="verified",
            confidence=0.95,
            mode="live",
            clock=clock,
            as_of=depart_at,
            json_path="/start_time",
        )
        price_claim = make_claim(
            subject_ref=leg_id,
            field_path="/price",
            value={
                "amount": amount,
                "currency": "CNY",
                "seat_name": price_entry["seat_name"] if price_entry is not None else None,
            },
            source_url=source_url,
            provider=self.provider,
            status="verified" if amount is not None else "unknown",
            confidence=0.95 if amount is not None else 0,
            mode="live",
            clock=clock,
            as_of=depart_at,
            json_path="/prices",
        )
        availability_claim = make_claim(
            subject_ref=leg_id,
            field_path="/availability",
            value=list(availability),
            source_url=source_url,
            provider=self.provider,
            status="verified",
            confidence=0.95,
            mode="live",
            clock=clock,
            as_of=depart_at,
            json_path="/prices",
        )
        price = {
            "amount": amount,
            "currency": "CNY",
            "price_type": "live" if amount is not None else "unknown",
            "unit": "per_person",
            "includes_taxes": True,
            "queried_at": price_claim["queried_at"],
            "claim_id": price_claim["claim_id"],
        }
        return ({
            "leg_id": leg_id,
            "travel_mode": "rail",
            "data_mode": "live",
            "from_ref": from_ref,
            "to_ref": to_ref,
            "depart_at": depart_at,
            "arrive_at": arrive_at,
            "duration_minutes": duration,
            "provider": self.provider,
            "service_number": service,
            "price": price,
            "booking_url": source_url,
            "claim_ids": [time_claim["claim_id"], price_claim["claim_id"], availability_claim["claim_id"]],
            "locked": False,
        }, (time_claim, price_claim, availability_claim))


def _transcript(body: Any) -> Mapping[str, Any]:
    if not isinstance(body, dict):
        raise ContractMismatch("12306 MCP transcript is not an object")
    if body.get("protocol_version") != MCP_PROTOCOL_VERSION:
        raise ContractMismatch("12306 MCP protocol version mismatch")
    server_info = body.get("server_info")
    if not isinstance(server_info, dict) or server_info.get("name") != "12306-mcp" or server_info.get("version") != "0.3.10":
        raise ContractMismatch("12306 MCP server fingerprint mismatch")
    tools = body.get("tools")
    if not isinstance(tools, list) or tuple(tools) != EXPECTED_TOOLS:
        raise ContractMismatch("12306 tool fingerprint mismatch")
    calls = body.get("calls")
    if not isinstance(calls, list) or not all(isinstance(call, dict) for call in calls):
        raise ContractMismatch("12306 MCP transcript calls have the wrong shape")
    return body


def _single_call(calls: Sequence[Mapping[str, Any]], names: Sequence[str]) -> Mapping[str, Any]:
    matches = [call for call in calls if call.get("name") in names]
    if len(matches) != 1:
        raise ContractMismatch("12306 MCP transcript has the wrong tool-call sequence")
    call = matches[0]
    if set(call) != {"name", "arguments", "result"} or not isinstance(call.get("arguments"), dict):
        raise ContractMismatch("12306 MCP tool call has the wrong shape")
    return call


def _station_resolution(
    transcript: Mapping[str, Any],
    request: ProviderRequest,
) -> Tuple[Optional[str], Tuple[Mapping[str, Any], ...]]:
    resolution = transcript.get("station_resolution")
    if resolution is None:
        return None, ()
    if not isinstance(resolution, dict) or set(resolution) != {"status", "endpoints"}:
        raise ContractMismatch("12306 station resolution has the wrong shape")
    status = resolution.get("status")
    if status not in ("resolved", "no_results", "ambiguous"):
        raise ContractMismatch("12306 station resolution status is invalid")
    endpoints = resolution.get("endpoints")
    if not isinstance(endpoints, dict) or set(endpoints) != {"from", "to"}:
        raise ContractMismatch("12306 station resolution endpoints have the wrong shape")

    normalized: List[Mapping[str, Any]] = []
    counts: List[int] = []
    for endpoint, parameter_name in (("from", "from_name"), ("to", "to_name")):
        value = endpoints.get(endpoint)
        if not isinstance(value, dict) or set(value) != {"query", "candidates"}:
            raise ContractMismatch("12306 station resolution endpoint has the wrong shape")
        query = value.get("query")
        if query != request.parameters.get(parameter_name):
            raise ContractMismatch("12306 station resolution query does not match the request")
        candidates = value.get("candidates")
        if not isinstance(candidates, list):
            raise ContractMismatch("12306 station resolution candidates are not an array")
        endpoint_items: List[Mapping[str, Any]] = []
        seen_codes = set()
        for candidate in candidates:
            if not isinstance(candidate, dict) or not {"station_code", "station_name"}.issubset(candidate):
                raise ContractMismatch("12306 station resolution candidate has the wrong shape")
            if not set(candidate).issubset({"station_code", "station_name", "distance_meters"}):
                raise ContractMismatch("12306 station resolution candidate has unexpected fields")
            code = candidate.get("station_code")
            name = candidate.get("station_name")
            if not isinstance(code, str) or not re.fullmatch(r"[A-Z]{3}", code):
                raise ContractMismatch("12306 station resolution code is invalid")
            if code in seen_codes:
                raise ContractMismatch("12306 station resolution contains duplicate station codes")
            seen_codes.add(code)
            if not isinstance(name, str) or not name.strip():
                raise ContractMismatch("12306 station resolution name is invalid")
            distance = candidate.get("distance_meters")
            if distance is not None and (
                isinstance(distance, bool)
                or not isinstance(distance, (int, float))
                or distance < 0
            ):
                raise ContractMismatch("12306 station resolution distance is invalid")
            item: Dict[str, Any] = {
                "ref_id": "station-" + code.lower(),
                "name": sanitize_text(name, 80),
                "city": sanitize_text(query, 80),
                "station_code": code,
                "resolution_for": endpoint,
            }
            if distance is not None:
                item["distance_meters"] = distance
            endpoint_items.append(item)
        endpoint_items.sort(key=lambda item: (
            0 if "distance_meters" in item else 1,
            float(item.get("distance_meters", 0)),
            item["name"],
            item["station_code"],
        ))
        normalized.extend(endpoint_items)
        counts.append(len(endpoint_items))

    derived_status = (
        "no_results" if any(count == 0 for count in counts)
        else "ambiguous" if any(count > 1 for count in counts)
        else "resolved"
    )
    if status != derived_status:
        raise ContractMismatch("12306 station resolution status contradicts its candidates")
    return status, tuple(normalized)


def _call_payload(call: Mapping[str, Any], request: ProviderRequest, clock: Clock) -> Any:
    result = call.get("result")
    if not isinstance(result, dict):
        raise ContractMismatch("12306 MCP tool result is not an object")
    if result.get("isError") is True:
        if request.capability == "station":
            raise ProviderFailure("no_results", "station lookup returned no matching stations")
        requested = _request_date(request)
        today = clock.now().date()
        last_sale_date = today + timedelta(days=PRESALE_DAYS - 1)
        if requested < today or requested > last_sale_date:
            raise ProviderFailure("no_results", "outside_presale_window")
        raise ProviderFailure("network", "12306 MCP reported an upstream query error")
    content = result.get("content")
    if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict):
        raise ContractMismatch("12306 MCP content has the wrong shape")
    if content[0].get("type") != "text" or not isinstance(content[0].get("text"), str):
        raise ContractMismatch("12306 MCP content is not text JSON")
    text = content[0]["text"].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        if request.capability == "station" and text.rstrip(". ") == "Error: City not found":
            raise ProviderFailure("no_results", "station lookup returned no matching stations") from exc
        raise ContractMismatch("12306 MCP text is not JSON") from exc
    if (
        request.capability == "station"
        and isinstance(payload, dict)
        and set(payload) == {"error"}
        and isinstance(payload.get("error"), str)
    ):
        raise ProviderFailure("no_results", "station lookup returned no matching stations")
    return payload


def _request_date(request: ProviderRequest) -> date:
    value = request.parameters.get("date")
    if not isinstance(value, str):
        raise ContractMismatch("rail request date is missing")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContractMismatch("rail request date is invalid") from exc


def _stations(payload: Any, request: ProviderRequest) -> Sequence[Mapping[str, Any]]:
    city = sanitize_text(request.parameters["city"], 80)
    raw_items: List[Tuple[str, Mapping[str, Any]]] = []
    if isinstance(payload, list):
        for raw in payload:
            if not isinstance(raw, dict):
                raise ContractMismatch("12306 station item is not an object")
            raw_items.append((city, raw))
    elif isinstance(payload, dict):
        for raw_city, raw in payload.items():
            if not isinstance(raw_city, str) or not isinstance(raw, dict):
                raise ContractMismatch("12306 representative station result has the wrong shape")
            raw_items.append((raw_city, raw))
    else:
        raise ContractMismatch("12306 station text has the wrong shape")
    stations = []
    for raw_city, raw in raw_items:
        code = sanitize_text(raw["station_code"], 16)
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ContractMismatch("12306 station code is invalid")
        name = sanitize_text(raw["station_name"], 80)
        stations.append({"ref_id": "station-" + code.lower(), "name": name, "city": sanitize_text(raw_city, 80)})
    return stations


def _seat(raw: Mapping[str, Any]) -> Mapping[str, Any]:
    name = sanitize_text(raw["seat_name"], 80)
    inventory = sanitize_text(raw.get("num", ""), 40)
    price_value = raw.get("price")
    if isinstance(price_value, bool) or (price_value is not None and not isinstance(price_value, (int, float))):
        raise ContractMismatch("12306 seat price has the wrong shape")
    return {
        "seat_name": name,
        "availability": inventory,
        "available": _has_inventory(inventory),
        "price": price_value,
    }


def _has_inventory(value: str) -> bool:
    if value.lower() in NO_INVENTORY:
        return False
    if value.isdigit():
        return int(value) > 0
    return value == "有" or bool(value)


def _select_price(prices: Sequence[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    numeric = [entry for entry in prices if isinstance(entry.get("price"), (int, float)) and not isinstance(entry.get("price"), bool)]
    available = [entry for entry in numeric if entry["available"]]
    choices = available or numeric
    return min(choices, key=lambda item: (float(item["price"]), str(item["seat_name"]))) if choices else None


def _deep_link(raw: Mapping[str, Any], request: ProviderRequest) -> str:
    from_name = sanitize_text(raw.get("from_station", request.parameters.get("from_name", "出发站")), 80)
    to_name = sanitize_text(raw.get("to_station", request.parameters.get("to_name", "到达站")), 80)
    from_code = sanitize_text(raw.get("from_station_telecode", ""), 16)
    to_code = sanitize_text(raw.get("to_station_telecode", ""), 16)
    travel_date = sanitize_text(raw.get("start_date", request.parameters.get("date", "")), 16)
    query = urllib.parse.urlencode({
        "linktypeid": "dc",
        "fs": "%s,%s" % (from_name, from_code),
        "ts": "%s,%s" % (to_name, to_code),
        "date": travel_date,
        "flag": "N,N,Y",
    })
    return "https://kyfw.12306.cn/otn/leftTicket/init?" + query


def _rail_datetime(day: Any, time_value: Any) -> str:
    if not isinstance(day, str) or not isinstance(time_value, str):
        raise ContractMismatch("rail date/time is not text")
    try:
        parsed = datetime.fromisoformat(day + "T" + time_value + ":00+08:00")
    except ValueError as exc:
        raise ContractMismatch("rail date/time is invalid") from exc
    return parsed.isoformat(timespec="seconds")
