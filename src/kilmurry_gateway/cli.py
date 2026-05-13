"""CLI entry point: `gateway` (or `python -m kilmurry_gateway`).

Subcommands:
  gateway run         # fetch -> transform -> validate -> publish (default)
  gateway fetch       # fetch only, print summary
  gateway validate    # validate an existing feed JSON on disk
  gateway publish     # take a prepared feed JSON and write artifacts
  gateway backfill    # iterate run() across a date range
  gateway watch       # daemon mode, run every poll_interval_hours
  gateway sample      # write a sample feed/summary to ./samples/
  gateway doctor      # print env, paths, config (no secrets)

All subcommands honour the same config loader.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import click

from . import __version__
from .config import GatewayConfig
from .logging_setup import configure_logging
from .pipeline import run_pipeline
from .run_context import RunContext, utcnow
from .validate import validate_feed


def _load_cfg(config_dir: str | None) -> GatewayConfig:
    import os
    if config_dir:
        os.environ["GATEWAY_CONFIG_DIR"] = config_dir
    return GatewayConfig.load()


@click.group(help="Kilmurry Desktop Data Gateway — RezLynx → OneDrive handoff.")
@click.version_option(__version__)
@click.option("--config-dir", default=None, help="Override config directory (env: GATEWAY_CONFIG_DIR).")
@click.pass_context
def cli(ctx: click.Context, config_dir: str | None) -> None:
    ctx.ensure_object(dict)
    cfg = _load_cfg(config_dir)
    ctx.obj["cfg"] = cfg
    configure_logging(cfg.log_dir, level=cfg.log_level)


@cli.command("doctor", help="Print resolved config + paths (no secrets).")
@click.pass_context
def cmd_doctor(ctx: click.Context) -> None:
    cfg: GatewayConfig = ctx.obj["cfg"]
    info = {
        "version": __version__,
        "site_label": cfg.site_label,
        "site_id": cfg.site_id,
        "poll_interval_hours": cfg.poll_interval_hours,
        "adapter_mode": cfg.adapter_mode,
        "rezlynx": {
            "live_sources": cfg.rezlynx.live_sources,
            "has_credentials": cfg.rezlynx.has_credentials(),
            "has_soap_credentials": cfg.rezlynx.has_soap_credentials(),
            "has_report_data_credentials": cfg.rezlynx.has_report_data_credentials(),
            "base_url_set": bool(cfg.rezlynx.base_url),
            "site_id": cfg.rezlynx.site_id,
        },
        "publish": {
            "onedrive_root": str(cfg.publish.onedrive_root.resolve()),
            "feeds_dir": str(cfg.feeds_path()),
            "summaries_dir": str(cfg.summaries_path()),
            "manifests_dir": str(cfg.manifests_path()),
            "write_latest_pointer": cfg.publish.write_latest_pointer,
        },
        "log_dir": str(cfg.log_dir.resolve()),
        "now_utc": utcnow().isoformat().replace("+00:00", "Z"),
    }
    click.echo(json.dumps(info, indent=2))


@cli.command("run", help="Full pipeline: fetch -> transform -> validate -> publish.")
@click.option("--target-date", type=str, default=None, help="YYYY-MM-DD (default: today UTC).")
@click.option("--dry-run", is_flag=True, help="Don't write files.")
@click.pass_context
def cmd_run(ctx: click.Context, target_date: str | None, dry_run: bool) -> None:
    cfg: GatewayConfig = ctx.obj["cfg"]
    td = date.fromisoformat(target_date) if target_date else None
    result = run_pipeline(cfg, target_date=td, dry_run=dry_run)
    click.echo(json.dumps(result, indent=2))
    if result.get("status") not in {"ok", "dry_run_ok"}:
        raise SystemExit(2)


@cli.command("fetch", help="Fetch a snapshot only and print compact summary (no publish).")
@click.option("--target-date", type=str, default=None)
@click.pass_context
def cmd_fetch(ctx: click.Context, target_date: str | None) -> None:
    cfg: GatewayConfig = ctx.obj["cfg"]
    td = date.fromisoformat(target_date) if target_date else None
    result = run_pipeline(cfg, target_date=td, dry_run=True)
    click.echo(json.dumps(result, indent=2))


@cli.command("validate", help="Validate a feed JSON file on disk.")
@click.argument("feed_file", type=click.Path(exists=True, dir_okay=False, readable=True))
def cmd_validate(feed_file: str) -> None:
    data = json.loads(Path(feed_file).read_text(encoding="utf-8"))
    errs = validate_feed(data)
    if not errs:
        click.echo("OK — feed is valid against contract.")
        return
    click.echo("INVALID:")
    for e in errs:
        click.echo(f"  - {e}")
    raise SystemExit(1)


@cli.command("backfill", help="Run pipeline across a date range (inclusive).")
@click.option("--from", "from_date", required=True, type=str, help="YYYY-MM-DD")
@click.option("--to", "to_date", required=True, type=str, help="YYYY-MM-DD")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def cmd_backfill(ctx: click.Context, from_date: str, to_date: str, dry_run: bool) -> None:
    cfg: GatewayConfig = ctx.obj["cfg"]
    d_from = date.fromisoformat(from_date)
    d_to = date.fromisoformat(to_date)
    if d_to < d_from:
        raise click.UsageError("--to is before --from")
    day = d_from
    results = []
    while day <= d_to:
        res = run_pipeline(cfg, target_date=day, dry_run=dry_run)
        results.append({"date": day.isoformat(), "status": res.get("status")})
        day += timedelta(days=1)
    click.echo(json.dumps(results, indent=2))


@cli.command("watch", help="Run every poll_interval_hours forever (Ctrl+C to stop).")
@click.option("--once", is_flag=True, help="Run once then exit (useful for cron/Task Scheduler).")
@click.pass_context
def cmd_watch(ctx: click.Context, once: bool) -> None:
    cfg: GatewayConfig = ctx.obj["cfg"]
    interval = cfg.poll_interval_hours * 3600
    while True:
        result = run_pipeline(cfg)
        click.echo(json.dumps(result, indent=2))
        if once:
            return
        click.echo(f"sleeping for {cfg.poll_interval_hours}h...")
        time.sleep(interval)


@cli.command("sample", help="Write a sample mock feed + summary into ./samples/ for review.")
@click.pass_context
def cmd_sample(ctx: click.Context) -> None:
    cfg: GatewayConfig = ctx.obj["cfg"]
    cfg.adapter_mode = "mock"
    cfg.publish.onedrive_root = Path("./samples").resolve()
    cfg.publish.write_latest_pointer = True
    result = run_pipeline(cfg)
    click.echo(json.dumps(result, indent=2))


@cli.command("hunter-replay", help="Run pipeline against real Hunter 2026-03-04 CSV exports.")
@click.option("--target-date", type=str, default="2026-03-04", help="YYYY-MM-DD (default: 2026-03-04, the snapshot date).")
@click.option("--out", "out_dir", type=str, default="./samples/hunter-replay-out", help="Where to write artifacts.")
@click.option("--samples-dir", type=str, default="./samples/hunter-2026-03-04", help="Where to read Hunter CSVs from.")
@click.pass_context
def cmd_hunter_replay(ctx: click.Context, target_date: str, out_dir: str, samples_dir: str) -> None:
    cfg: GatewayConfig = ctx.obj["cfg"]
    cfg.adapter_mode = "hunter_replay"
    cfg.hunter_samples_dir = Path(samples_dir).resolve()
    cfg.publish.onedrive_root = Path(out_dir).resolve()
    cfg.publish.write_latest_pointer = True
    td = date.fromisoformat(target_date)
    result = run_pipeline(cfg, target_date=td)
    click.echo(json.dumps(result, indent=2))
    if result.get("status") != "ok":
        raise SystemExit(2)


@cli.command("soap-probe", help="Quick SOAP connectivity check (requires REZLYNX_PASSWORD).")
@click.pass_context
def cmd_soap_probe(ctx: click.Context) -> None:
    cfg: GatewayConfig = ctx.obj["cfg"]
    if not cfg.rezlynx.has_soap_credentials():
        click.echo("REZLYNX_PASSWORD not set; cannot probe.", err=True)
        raise SystemExit(2)
    from .adapters.rezlynx_soap import RezLynxSoapAdapter
    from datetime import datetime, timezone as _tz
    adapter = RezLynxSoapAdapter(cfg.rezlynx)
    today = datetime.now(tz=_tz.utc).date()
    try:
        snap = adapter.fetch(today)
    except Exception as e:
        click.echo(f"SOAP probe failed: {e}", err=True)
        raise SystemExit(2)
    click.echo(json.dumps({
        "status": "ok",
        "reservations_returned": len(snap.reservations),
        "rooms_available_today": snap.inventory.rooms_available,
        "notes": snap.notes,
    }, indent=2))


if __name__ == "__main__":
    cli(obj={})
