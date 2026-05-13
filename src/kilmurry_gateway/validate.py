"""Validate a feed dict against the v1 contract.

Light-touch on purpose: catches structural bugs that would let bad JSON
leak to OneDrive, without becoming a full JSON-schema project.
A real JSON schema can be added later from `samples/feed.schema.json`.
"""
from __future__ import annotations

from typing import Any

from . import SCHEMA_ID


REQUIRED_TOP_LEVEL = [
    "schema",
    "generated_at_utc",
    "as_of_utc",
    "source_system",
    "source_site",
    "confidence",
    "freshness",
    "kpi",
    "operations",
    "segments",
    "channels",
    "rates",
    "provenance",
]

REQUIRED_KPI = [
    "occupancy_pct", "adr_eur", "revpar_eur",
    "room_revenue_eur", "rooms_sold", "rooms_available",
]
REQUIRED_OPS = [
    "arrivals_today", "departures_today", "stayovers_today",
    "in_house_rooms", "cancellations_today", "no_shows_today",
]


class FeedValidationError(ValueError):
    pass


def validate_feed(feed: dict[str, Any]) -> list[str]:
    """Return a list of errors. Empty list = valid.

    Raises only on truly malformed input (non-dict).
    """
    if not isinstance(feed, dict):
        raise FeedValidationError("feed is not a dict")

    errors: list[str] = []

    for key in REQUIRED_TOP_LEVEL:
        if key not in feed:
            errors.append(f"missing required top-level key: {key}")

    if feed.get("schema") != SCHEMA_ID:
        errors.append(f"schema must be {SCHEMA_ID!r}, got {feed.get('schema')!r}")

    fresh = feed.get("freshness") or {}
    if fresh.get("status") not in {"LIVE", "STALE", "BLOCKED"}:
        errors.append(f"freshness.status invalid: {fresh.get('status')!r}")

    kpi = feed.get("kpi") or {}
    for k in REQUIRED_KPI:
        if k not in kpi:
            errors.append(f"missing kpi.{k}")
        elif not isinstance(kpi[k], (int, float)):
            errors.append(f"kpi.{k} must be numeric, got {type(kpi[k]).__name__}")

    ops = feed.get("operations") or {}
    for k in REQUIRED_OPS:
        if k not in ops:
            errors.append(f"missing operations.{k}")
        elif not isinstance(ops[k], int):
            errors.append(f"operations.{k} must be int")

    if feed.get("confidence") not in {"high", "medium", "low", "blocked"}:
        errors.append(f"confidence invalid: {feed.get('confidence')!r}")

    # operations counts must be non-negative
    for k, v in ops.items():
        if isinstance(v, int) and v < 0:
            errors.append(f"operations.{k} negative: {v}")

    # kpi numerics must be non-negative
    for k, v in kpi.items():
        if isinstance(v, (int, float)) and v < 0:
            errors.append(f"kpi.{k} negative: {v}")

    return errors


def assert_valid_feed(feed: dict[str, Any]) -> None:
    errs = validate_feed(feed)
    if errs:
        raise FeedValidationError("invalid feed:\n  - " + "\n  - ".join(errs))
