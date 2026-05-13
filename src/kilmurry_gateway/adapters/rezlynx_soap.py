"""RezLynx SOAP adapter — bookings + availability.

Endpoint, methods, and auth model confirmed from Gary Hunt's email
to Hunter (2026-01-16) and Hunter's sample CSV evidence (2026-03-04).

  Endpoint:      https://pmsws.eu.guestline.net/RLXSoapRouter/rlxsoap.asmx
  Interface ID:  727
  Site ID:       KILMURRY
  Operator Code: KILMURRY_API
  Password:      <sent in separate email, NOT in archive>

Sandbox methods granted (use these only):
  - pmsavl_AvailAndRateV2          (availability + rates)
  - pmsbkg_BookingSearch           (booking records, polling-friendly)
  - pmsbkg_GetReservationTransactions  (Phase 2)
  - pmsprf_GetProfileSummaryV4     (GDPR-sensitive, defer)

This adapter uses raw SOAP envelopes via `requests` (lightweight) — no
hard zeep dependency. If the live envelope shape needs WSDL-driven
introspection, swap to zeep later (the optional `[soap]` extra in
pyproject.toml installs it).

Phase 1 status: SHAPED, NOT YET RUN AGAINST LIVE SANDBOX. The XML
envelope templates below are derived from the confirmed method names
and sample data shapes. Stephen should run `python -m kilmurry_gateway
soap-probe` (TODO) once the password is recovered to validate envelopes
and adjust field paths if Guestline's actual response shape diverges.
"""
from __future__ import annotations

import logging
import os
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import requests

from ..config import RezLynxConfig
from ..models import InventorySnapshot, ReservationRecord, RezLynxSnapshot
from .base import FetchError, RezLynxAdapter

logger = logging.getLogger("kilmurry_gateway.adapters.rezlynx_soap")

DEFAULT_ENDPOINT = "https://pmsws.eu.guestline.net/RLXSoapRouter/rlxsoap.asmx"
DEFAULT_INTERFACE_ID = "727"
SOAP_NS = "{http://schemas.xmlsoap.org/soap/envelope/}"
GL_NS = "http://tempuri.org/RLXSOAP19/RLXSOAP19"


def _build_envelope(method: str, params_xml: str) -> str:
    """Build a SOAP 1.1 envelope. Method name and namespace from live WSDL.

    The exact body shape may need adjustment after first live response —
    that's the point of the `soap-probe` step. We keep this rendering
    explicit (rather than hidden behind zeep) so divergences are obvious.
    """
    return f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:gl="{GL_NS}"
               xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <soap:Body>
    <gl:{method}>
      {params_xml}
    </gl:{method}>
  </soap:Body>
</soap:Envelope>
""".strip()


def _findall_local(elem: ET.Element, local_name: str) -> list[ET.Element]:
    """Find descendants by local name regardless of namespace prefix."""
    return [e for e in elem.iter() if e.tag.rsplit("}", 1)[-1] == local_name]


def _find_local(elem: ET.Element, local_name: str) -> ET.Element | None:
    for e in elem.iter():
        if e.tag.rsplit("}", 1)[-1] == local_name:
            return e
    return None


def _child_text(parent: ET.Element, local_name: str) -> str | None:
    for c in parent:
        if c.tag.rsplit("}", 1)[-1] == local_name:
            return (c.text or "").strip() or None
    return None


class RezLynxSoapAdapter(RezLynxAdapter):
    def __init__(self, cfg: RezLynxConfig, password: str | None = None) -> None:
        self._cfg = cfg
        # Endpoint: config wins, otherwise the known production endpoint.
        self._endpoint = cfg.base_url or DEFAULT_ENDPOINT
        self._interface_id = os.getenv("REZLYNX_INTERFACE_ID") or DEFAULT_INTERFACE_ID
        self._site_id = cfg.site_id or "KILMURRY"
        self._operator_code = os.getenv("REZLYNX_OPERATOR_CODE") or "KILMURRY_API"
        self._password = password or os.getenv("REZLYNX_PASSWORD") or ""
        if not self._password:
            raise FetchError(
                "REZLYNX_PASSWORD not set — recover from Hunter's mailbox or "
                "request re-issue from Gary Hunt at Access",
                endpoint=self._endpoint,
            )
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "text/xml; charset=utf-8"})
        self._session_id: str | None = None

    @property
    def source_label(self) -> str:
        return "guestline-rezlynx"

    def _post(self, method: str, params_xml: str) -> ET.Element:
        envelope = _build_envelope(method, params_xml)
        soap_action = f"{GL_NS}/{method}"
        resp = self._session.post(
            self._endpoint,
            data=envelope.encode("utf-8"),
            headers={"SOAPAction": f'"{soap_action}"'},
            timeout=self._cfg.timeout_seconds,
            verify=self._cfg.verify_ssl,
        )
        if resp.status_code >= 400:
            raise FetchError(
                f"SOAP {method} failed: {resp.status_code} {resp.text[:300]}",
                endpoint=method,
            )
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError as e:
            raise FetchError(
                f"SOAP {method}: malformed XML response: {e}",
                endpoint=method,
            ) from e
        # Detect SOAP Fault
        fault = _find_local(root, "Fault")
        if fault is not None:
            reason = _child_text(fault, "faultstring") or "unknown fault"
            raise FetchError(f"SOAP {method} fault: {reason}", endpoint=method)
        code = _find_local(root, "ExceptionCode")
        if code is not None and (code.text or "").strip() not in {"", "0"}:
            desc = ""
            desc_node = _find_local(root, "ExceptionDescription")
            if desc_node is not None:
                desc = (desc_node.text or "").strip()
            raise FetchError(f"SOAP {method} application error {code.text}: {desc}", endpoint=method)
        return root

    def _login(self) -> str:
        if self._session_id:
            return self._session_id
        root = self._post(
            "LogIn",
            f"""
            <gl:SiteID>{self._site_id}</gl:SiteID>
            <gl:InterfaceID>{self._interface_id}</gl:InterfaceID>
            <gl:OperatorCode>{self._operator_code}</gl:OperatorCode>
            <gl:Password>{self._password}</gl:Password>
            <gl:SessionID></gl:SessionID>
            """.strip(),
        )
        session_id = _child_text(_find_local(root, "LogInResponse") or root, "SessionID") or ""
        if not session_id:
            raise FetchError("SOAP LogIn succeeded but returned no SessionID", endpoint="LogIn")
        self._session_id = session_id
        return session_id

    def fetch(self, target_date: date) -> RezLynxSnapshot:
        # BookingSearch filters by exact arrival date. Pull a window around the
        # target so the transform can still compute arrivals / upcoming pickup.
        # Current in-house stayovers whose arrival was before the window remain
        # a known Phase 1 limitation until Report Data / residents endpoint is
        # explicitly added to the contract.
        from_date = target_date - timedelta(days=14)
        to_date = target_date + timedelta(days=45)

        reservations = self._fetch_bookings(from_date, to_date)
        inventory = self._fetch_availability(target_date)

        return RezLynxSnapshot(
            as_of_utc=datetime.now(tz=timezone.utc),
            target_date=target_date,
            site_id=self._site_id,
            reservations=reservations,
            inventory=inventory,
            notes=[
                f"soap.pmsbkg_BookingSearch arrival dates {from_date} .. {to_date}",
                f"soap.pmsfoh_GetAvailability target_date {target_date}",
            ],
        )

    # ------------------------------------------------------------------ #
    # Method-specific fetchers                                           #
    # ------------------------------------------------------------------ #

    def _fetch_bookings(self, from_date: date, to_date: date) -> list[ReservationRecord]:
        out: list[ReservationRecord] = []
        session_id = self._login()
        day = from_date
        while day <= to_date:
            params = f"""
            <gl:SessionID>{session_id}</gl:SessionID>
            <gl:Filters>
              <gl:RoomPickID xsi:nil="true" />
              <gl:ArrivalDate>{day.isoformat()}T00:00:00</gl:ArrivalDate>
              <gl:DepartureDate xsi:nil="true" />
              <gl:CreationDate xsi:nil="true" />
              <gl:BookingType xsi:nil="true" />
              <gl:ShiftAllowances xsi:nil="true" />
              <gl:Limit>250</gl:Limit>
              <gl:ReturnAllGuestsInNameSearches>false</gl:ReturnAllGuestsInNameSearches>
              <gl:LastEditFrom xsi:nil="true" />
              <gl:LastEditTo xsi:nil="true" />
              <gl:CreatedFrom xsi:nil="true" />
              <gl:CreatedTo xsi:nil="true" />
              <gl:SystemSource xsi:nil="true" />
              <gl:DistributionChannelID xsi:nil="true" />
              <gl:PreCheckIn xsi:nil="true" />
              <gl:IncludeMasterBookings>false</gl:IncludeMasterBookings>
              <gl:IncludeReservationAttributes>false</gl:IncludeReservationAttributes>
            </gl:Filters>
            <gl:SearchResults></gl:SearchResults>
            """.strip()
            root = self._post("pmsbkg_BookingSearch", params)
            for node in _findall_local(root, "Reservation"):
                rec = self._parse_booking_node(node)
                if rec:
                    out.append(rec)
            day += timedelta(days=1)

        logger.info(
            "soap.bookings.parsed",
            extra={"event": "soap.bookings.parsed", "count": len(out)},
        )
        return out

    def _parse_booking_node(self, node: ET.Element) -> ReservationRecord | None:
        booking_ref = _child_text(node, "BookRef") or _child_text(node, "BookingReference") or _child_text(node, "BookingRef")
        room_pick = _child_text(node, "RoomPickId") or _child_text(node, "RoomPickID") or "1"
        arr = _child_text(node, "Arrival") or _child_text(node, "ArrivalDate") or _child_text(node, "DateArrive")
        dep = _child_text(node, "Departure") or _child_text(node, "DepartureDate") or _child_text(node, "DateDepart")
        if not (booking_ref and arr and dep):
            return None
        try:
            arrival = datetime.fromisoformat(arr.replace("Z", "+00:00")).date()
            departure = datetime.fromisoformat(dep.replace("Z", "+00:00")).date()
        except ValueError:
            return None
        status_raw = (_child_text(node, "BookingStatus") or _child_text(node, "Status") or "Unknown").strip()
        # Normalise to our internal vocabulary (RezLynx-native casing).
        status = {
            "prearrival": "PreArrival",
            "resident": "Resident",
            "checkedout": "CheckedOut",
            "cancelled": "Cancelled",
            "canceled": "Cancelled",
            "noshow": "NoShow",
            "no-show": "NoShow",
            "waitlist": "Waitlist",
        }.get(status_raw.lower().replace(" ", ""), status_raw)

        market_segment = _child_text(node, "MarketSegmentCode") or _child_text(node, "MarketSegment")
        media_source = _child_text(node, "Source") or _child_text(node, "MediaSource") or _child_text(node, "SystemSource")
        rate_plan = _child_text(node, "PackageCode") or _child_text(node, "RateCode") or _child_text(node, "RatePlanCode")
        room_type = _child_text(node, "RoomTypeCode") or _child_text(node, "RoomType")
        try:
            total_gross = Decimal(_child_text(node, "TotalCostGross") or "0")
        except Exception:
            total_gross = Decimal("0")
        try:
            dci_text = _child_text(node, "DistributionChannelId") or _child_text(node, "DistributionChannelID")
            dci = int(dci_text) if dci_text else None
        except ValueError:
            dci = None

        return ReservationRecord(
            reservation_id=f"{booking_ref}_{room_pick}",
            arrival_date=arrival,
            departure_date=departure,
            status=status,  # type: ignore[arg-type]
            rooms=1,
            room_revenue=total_gross,
            market_segment=market_segment,
            media_source=media_source,
            rate_plan=rate_plan,
            room_type=room_type,
            distribution_channel_id=dci,
        )

    def _fetch_availability(self, target_date: date) -> InventorySnapshot:
        session_id = self._login()
        root = self._post(
            "pmsfoh_GetAvailability",
            f"""
            <gl:SessionID>{session_id}</gl:SessionID>
            <gl:StartDate>{target_date.isoformat()}T00:00:00</gl:StartDate>
            <gl:GetAvailability></gl:GetAvailability>
            """.strip(),
        )
        total = 0
        data = _find_local(root, "Data")
        if data is not None:
            for room_type_node in data:
                if _child_text(room_type_node, "RoomTypeCode") is None:
                    continue
                availability_node = _find_local(room_type_node, "Availability")
                if availability_node is None or not list(availability_node):
                    continue
                # pmsfoh_GetAvailability returns one row per room type and a
                # sequence of daily values starting at StartDate. We requested
                # target_date as StartDate, so the first value is today's
                # remaining inventory for that room type.
                first_value = (list(availability_node)[0].text or "0").strip()
                try:
                    total += int(first_value)
                except ValueError:
                    continue
        logger.info(
            "soap.availability.parsed",
            extra={"event": "soap.availability.parsed", "rooms_available": total, "target_date": target_date.isoformat()},
        )
        return InventorySnapshot(as_of_date=target_date, rooms_available=total)
