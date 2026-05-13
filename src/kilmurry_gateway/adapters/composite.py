"""CompositeLive adapter — fuses SOAP + Report Data into one snapshot.

This is the production live adapter once both SOAP and Report Data
credentials are available. It returns a single `RezLynxSnapshot` with
reservations + inventory from SOAP and `revenue_lines` from Report Data,
so the transform layer can compute authoritative room revenue.

If only one source is configured, the snapshot still works but is
flagged in `notes` and the transform downgrades confidence accordingly.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from ..config import GatewayConfig
from ..models import RezLynxSnapshot
from .base import FetchError, RezLynxAdapter
from .rezlynx_soap import RezLynxSoapAdapter
from .rezlynx_report_data import RezLynxReportDataAdapter

logger = logging.getLogger("kilmurry_gateway.adapters.composite")


class CompositeLiveAdapter(RezLynxAdapter):
    def __init__(self, cfg: GatewayConfig) -> None:
        self._cfg = cfg
        self._soap = RezLynxSoapAdapter(cfg.rezlynx) if "soap" in cfg.rezlynx.live_sources else None
        self._report = (
            RezLynxReportDataAdapter(cfg.rezlynx)
            if "report_data" in cfg.rezlynx.live_sources
            else None
        )
        if not (self._soap or self._report):
            raise FetchError("composite adapter requires at least one live source enabled")

    @property
    def source_label(self) -> str:
        return "guestline-rezlynx"

    def fetch(self, target_date: date) -> RezLynxSnapshot:
        notes: list[str] = []
        # 1. SOAP for reservations + availability
        if self._soap:
            base = self._soap.fetch(target_date)
            notes.extend(base.notes)
        else:
            # No SOAP — still build an empty snapshot so revenue can land.
            from ..models import InventorySnapshot
            base = RezLynxSnapshot(
                as_of_utc=datetime.now(tz=timezone.utc),
                target_date=target_date,
                site_id=self._cfg.site_id,
                inventory=InventorySnapshot(as_of_date=target_date, rooms_available=0),
            )
            notes.append("WARNING: SOAP source disabled — no reservations or inventory")

        # 2. Report Data for revenue
        if self._report:
            try:
                base.revenue_lines = self._report.fetch_revenue(target_date)
                notes.append(f"report_data.booked_revenue rows={len(base.revenue_lines)}")
            except FetchError as e:
                logger.error(
                    "composite.revenue_failed",
                    extra={"event": "composite.revenue_failed", "error": str(e)},
                )
                notes.append(f"WARNING: report_data fetch failed: {e}")
        else:
            notes.append("WARNING: Report Data source disabled — using contract revenue fallback")

        base.notes = base.notes + [n for n in notes if n not in base.notes]
        return base
