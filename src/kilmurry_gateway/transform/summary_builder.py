"""Render the feed dict to a human-readable HTML summary."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    keep_trailing_newline=True,
)


def build_summary(feed: dict[str, Any]) -> str:
    template = _env.get_template("summary.html.j2")
    now_iso = datetime.now(tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return template.render(feed=feed, generated_for_humans_at=now_iso)
