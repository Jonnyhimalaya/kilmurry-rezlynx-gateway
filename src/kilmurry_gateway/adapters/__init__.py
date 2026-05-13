"""Adapters wrap a specific PMS access mechanism behind a stable interface.

Available adapters:

- `MockRezLynxAdapter` — deterministic synthetic data for unit tests.
- `HunterReplayAdapter` — replays real Hunter 2026-03-04 CSV exports for
  shadow validation without live credentials.
- `RezLynxSoapAdapter` — live SOAP (bookings + availability). Needs
  REZLYNX_PASSWORD.
- `RezLynxReportDataAdapter` — live Report Data REST (booked-revenue).
  Needs REZLYNX_REPORT_DATA_API_KEY.
- `CompositeLiveAdapter` — fuses SOAP + Report Data for the production
  hybrid path.
"""
from .base import RezLynxAdapter, FetchError
from .mock import MockRezLynxAdapter
from .hunter_replay import HunterReplayAdapter

__all__ = [
    "RezLynxAdapter",
    "FetchError",
    "MockRezLynxAdapter",
    "HunterReplayAdapter",
]
