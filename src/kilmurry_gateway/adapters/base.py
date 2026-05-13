"""Adapter contract — the only thing the rest of the gateway depends on."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ..models import RezLynxSnapshot


class FetchError(RuntimeError):
    """Raised when an adapter cannot produce a valid snapshot.

    Carries an optional `endpoint` for log/manifest provenance.
    """

    def __init__(self, message: str, endpoint: str | None = None) -> None:
        super().__init__(message)
        self.endpoint = endpoint


class RezLynxAdapter(ABC):
    """Pulls a normalised snapshot of PMS data for a given target date."""

    @abstractmethod
    def fetch(self, target_date: date) -> RezLynxSnapshot:
        """Return a complete snapshot for `target_date`.

        Must either succeed with a valid `RezLynxSnapshot` or raise
        `FetchError` — never return a partially-built object that
        would publish as false-success.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def source_label(self) -> str:
        """Short human label for provenance (e.g. 'guestline-rezlynx')."""
        raise NotImplementedError
