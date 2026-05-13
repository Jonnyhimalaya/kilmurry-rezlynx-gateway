"""Validator tests."""
from __future__ import annotations

import copy
from datetime import date

import pytest

from kilmurry_gateway.adapters import MockRezLynxAdapter
from kilmurry_gateway.run_context import RunContext
from kilmurry_gateway.transform import build_feed
from kilmurry_gateway.validate import FeedValidationError, validate_feed, assert_valid_feed


def _good_feed() -> dict:
    adapter = MockRezLynxAdapter()
    snap = adapter.fetch(date(2026, 5, 11))
    return build_feed(snap, run_ctx=RunContext(), source_label="mock-rezlynx", poll_interval_hours=6)


def test_good_feed_passes() -> None:
    feed = _good_feed()
    assert validate_feed(feed) == []


def test_missing_schema_caught() -> None:
    feed = _good_feed()
    del feed["schema"]
    errs = validate_feed(feed)
    assert any("schema" in e for e in errs)


def test_bad_freshness_status_caught() -> None:
    feed = _good_feed()
    feed["freshness"]["status"] = "SUNNY"
    errs = validate_feed(feed)
    assert any("freshness" in e for e in errs)


def test_assert_raises_on_invalid() -> None:
    feed = _good_feed()
    del feed["kpi"]["rooms_sold"]
    with pytest.raises(FeedValidationError):
        assert_valid_feed(feed)


def test_validate_rejects_non_dict() -> None:
    with pytest.raises(FeedValidationError):
        validate_feed("not a dict")  # type: ignore[arg-type]
