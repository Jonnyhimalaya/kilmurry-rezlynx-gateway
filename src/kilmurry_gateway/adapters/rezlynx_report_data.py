"""Guestline Report Data REST adapter — booked-revenue (and optional dashboard-sales).

This is the second half of the hybrid live source. SOAP gives us
reservations and availability; Report Data REST gives us authoritative
realised room revenue with `cancelled` and `is_no_show` flags pre-applied
at the source.

Hunter requested `X-API-KEY` access for Event Archive + Report Data on
2026-01-20. The email archive doesn't confirm whether the keys were
issued. Stephen needs to confirm with Gary Hunt at Access (gary.hunt@theaccessgroup.com).

CSV columns from Hunter's 2026-03-04 production sample:

  booked-revenue.csv (';'-separated):
    date, booking_type, cancelled, media_source, market_segment,
    rate_plan_code, room_type_code, revenue_type_long_description,
    revenue_type_group, is_no_show, amount_before_tax, amount_after_tax

  dashboard-sales.csv (';'-separated):
    date, analysis_code, amount_before_tax, amount_after_tax

This adapter is SHAPED, NOT YET RUN against the live REST endpoint.
Endpoint URL and auth scheme are placeholders until Stephen confirms.
"""
from __future__ import annotations

import csv
import io
import logging
import os
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import requests

from ..config import RezLynxConfig
from ..models import DashboardSalesLine, RevenueLine
from .base import FetchError

logger = logging.getLogger("kilmurry_gateway.adapters.rezlynx_report_data")

DEFAULT_REPORT_DATA_BASE = "https://api.guestline.com/report-data"  # PLACEHOLDER, confirm with Gary Hunt


class RezLynxReportDataAdapter:
    """Fetches booked-revenue (and optionally dashboard-sales) from Report Data REST."""

    def __init__(self, cfg: RezLynxConfig, api_key: str | None = None) -> None:
        self._cfg = cfg
        self._api_key = api_key or os.getenv("REZLYNX_REPORT_DATA_API_KEY", "")
        if not self._api_key:
            raise FetchError(
                "REZLYNX_REPORT_DATA_API_KEY not set — escalate to Gary Hunt to "
                "issue Event Archive + Report Data keys per Hunter's 2026-01-20 request",
                endpoint="report-data",
            )
        self._base_url = os.getenv("REZLYNX_REPORT_DATA_BASE_URL", DEFAULT_REPORT_DATA_BASE)
        self._group_id = os.getenv("REZLYNX_GROUP_ID", "")
        self._site_id = cfg.site_id or "KILMURRY"
        self._session = requests.Session()
        self._session.headers.update({
            "X-API-KEY": self._api_key,
            "Accept": "text/csv, application/json",
        })

    def fetch_revenue(self, target_date: date) -> list[RevenueLine]:
        """Pull booked-revenue rows covering target_date.

        Real endpoint path needs confirmation. Hunter sample filename
        `rezlynx-booked-revenue-{date}.csv` suggests the report is
        run for a date range; we ask for [target-1, target+1] to cover
        timezone fuzz and adjustments.
        """
        path = "/booked-revenue"
        params: dict[str, Any] = {
            "siteId": self._site_id,
            "from": (target_date - timedelta(days=1)).isoformat(),
            "to": (target_date + timedelta(days=1)).isoformat(),
        }
        if self._group_id:
            params["groupId"] = self._group_id

        url = f"{self._base_url.rstrip('/')}{path}"
        resp = self._session.get(
            url,
            params=params,
            timeout=self._cfg.timeout_seconds,
            verify=self._cfg.verify_ssl,
        )
        if resp.status_code >= 400:
            raise FetchError(
                f"GET {path} failed: {resp.status_code} {resp.text[:200]}",
                endpoint=path,
            )
        return list(self._parse_revenue_csv(resp.text))

    def _parse_revenue_csv(self, text: str):
        # Try ';' first (Hunter evidence), fall back to ','.
        delim = ";" if ";" in text.splitlines()[0] else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        for row in reader:
            try:
                d = date.fromisoformat(row["date"])
            except (KeyError, ValueError):
                continue
            yield RevenueLine(
                date=d,
                revenue_type=row.get("revenue_type_long_description", "") or "",
                revenue_type_group=row.get("revenue_type_group", "") or "",
                market_segment=row.get("market_segment") or None,
                media_source=row.get("media_source") or None,
                rate_plan_code=row.get("rate_plan_code") or None,
                room_type_code=row.get("room_type_code") or None,
                cancelled=str(row.get("cancelled", "")).strip().lower() == "true",
                is_no_show=str(row.get("is_no_show", "")).strip().lower() == "true",
                amount_before_tax=_to_dec(row.get("amount_before_tax")),
                amount_after_tax=_to_dec(row.get("amount_after_tax")),
            )

    def fetch_dashboard_sales(self, target_date: date) -> list[DashboardSalesLine]:
        """Optional cross-check totals by analysis_code."""
        url = f"{self._base_url.rstrip('/')}/dashboard-sales"
        params: dict[str, Any] = {
            "siteId": self._site_id,
            "from": target_date.isoformat(),
            "to": target_date.isoformat(),
        }
        if self._group_id:
            params["groupId"] = self._group_id
        resp = self._session.get(
            url, params=params,
            timeout=self._cfg.timeout_seconds, verify=self._cfg.verify_ssl,
        )
        if resp.status_code >= 400:
            logger.warning(
                "dashboard_sales.skip",
                extra={"event": "dashboard_sales.skip", "status": resp.status_code},
            )
            return []
        delim = ";" if ";" in resp.text.splitlines()[0] else ","
        out: list[DashboardSalesLine] = []
        for row in csv.DictReader(io.StringIO(resp.text), delimiter=delim):
            try:
                d = date.fromisoformat(row["date"])
            except (KeyError, ValueError):
                continue
            out.append(DashboardSalesLine(
                date=d,
                analysis_code=row.get("analysis_code", "") or "",
                amount_before_tax=_to_dec(row.get("amount_before_tax")),
                amount_after_tax=_to_dec(row.get("amount_after_tax")),
            ))
        return out


def _to_dec(s: Any) -> Decimal:
    if s is None or s == "":
        return Decimal("0")
    try:
        return Decimal(str(s))
    except Exception:
        return Decimal("0")
