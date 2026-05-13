"""Config loading. Reads from `config/settings.toml` and `config/secrets.toml`
(or env vars). Never logs secret values.

Layout::

    config/
      settings.toml      # non-secret, may be checked in
      secrets.toml       # gitignored, contains creds
"""
from __future__ import annotations

import os
import sys
import tomllib  # py3.11+
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv


@dataclass
class RezLynxConfig:
    base_url: str = ""
    site_id: str = "KILMURRY"
    # Live composition: which mechanisms to use when adapter_mode = "live".
    # Subset of: "soap", "report_data".
    live_sources: list[str] = field(default_factory=lambda: ["soap", "report_data"])
    # SOAP-specific (defaults match Hunter's confirmed sandbox).
    interface_id: str = "727"
    operator_code: str = "KILMURRY_API"
    # REST-specific
    group_id: str = ""
    api_key_header: str = "X-API-KEY"
    timeout_seconds: int = 30
    verify_ssl: bool = True

    def has_soap_credentials(self) -> bool:
        return bool(os.getenv("REZLYNX_PASSWORD"))

    def has_report_data_credentials(self) -> bool:
        return bool(os.getenv("REZLYNX_REPORT_DATA_API_KEY"))

    def has_credentials(self) -> bool:
        """True if *all* enabled live sources have credentials."""
        ok = True
        if "soap" in self.live_sources:
            ok = ok and self.has_soap_credentials()
        if "report_data" in self.live_sources:
            ok = ok and self.has_report_data_credentials()
        return ok


@dataclass
class PublishConfig:
    # The local path that OneDrive syncs. The desktop owner sets this.
    onedrive_root: Path = Path("./output")
    # Subfolders inside onedrive_root.
    feeds_dir: str = "feeds"
    summaries_dir: str = "summaries"
    manifests_dir: str = "manifests"
    # If True, also writes `*-latest.{json,html}` pointers.
    write_latest_pointer: bool = True


@dataclass
class GatewayConfig:
    site_label: str = "Kilmurry Lodge"
    site_id: str = "KILMURRY"
    poll_interval_hours: int = 6
    timezone: str = "UTC"
    # adapter_mode controls which adapter is selected:
    #   "mock"          - synthetic deterministic data
    #   "hunter_replay" - real Hunter 2026-03-04 CSV exports (offline shadow)
    #   "live"          - SOAP + Report Data hybrid (requires creds)
    adapter_mode: str = "mock"
    # When adapter_mode = "hunter_replay", look for CSVs here.
    hunter_samples_dir: Path = Path("./samples/hunter-2026-03-04")
    log_dir: Path = Path("./logs")
    log_level: str = "INFO"
    rezlynx: RezLynxConfig = field(default_factory=RezLynxConfig)
    publish: PublishConfig = field(default_factory=PublishConfig)

    @classmethod
    def load(cls, settings_path: Path | None = None, secrets_path: Path | None = None) -> "GatewayConfig":
        # Always load .env first (devs prefer it on Windows)
        load_dotenv(override=False)

        cfg_dir = Path(os.getenv("GATEWAY_CONFIG_DIR", "config")).resolve()
        settings_path = settings_path or cfg_dir / "settings.toml"
        secrets_path = secrets_path or cfg_dir / "secrets.toml"

        data: dict[str, Any] = {}
        if settings_path.exists():
            with settings_path.open("rb") as f:
                data = tomllib.load(f)

        # Secrets file is optional. If present, fold non-empty entries into env vars
        # so downstream code can read them via os.getenv without re-reading TOML.
        if secrets_path.exists():
            with secrets_path.open("rb") as f:
                secrets_data = tomllib.load(f)
            for key, val in (secrets_data.get("rezlynx") or {}).items():
                env_name = f"REZLYNX_{key.upper()}"
                if val and not os.getenv(env_name):
                    os.environ[env_name] = str(val)

        gw_block: Mapping[str, Any] = data.get("gateway", {})
        rl_block: Mapping[str, Any] = data.get("rezlynx", {})
        pub_block: Mapping[str, Any] = data.get("publish", {})

        # Back-compat: old `mock_mode = true` keeps mock behaviour.
        adapter_mode = gw_block.get("adapter_mode")
        if adapter_mode is None:
            adapter_mode = "mock" if gw_block.get("mock_mode", True) else "live"

        cfg = cls(
            site_label=gw_block.get("site_label", "Kilmurry Lodge"),
            site_id=gw_block.get("site_id", "KILMURRY"),
            poll_interval_hours=int(gw_block.get("poll_interval_hours", 6)),
            timezone=gw_block.get("timezone", "UTC"),
            adapter_mode=str(adapter_mode).lower(),
            hunter_samples_dir=Path(
                gw_block.get("hunter_samples_dir", "./samples/hunter-2026-03-04")
            ).expanduser(),
            log_dir=Path(gw_block.get("log_dir", "./logs")),
            log_level=str(gw_block.get("log_level", "INFO")).upper(),
        )

        live_sources = rl_block.get("live_sources", ["soap", "report_data"])
        if isinstance(live_sources, str):
            live_sources = [s.strip() for s in live_sources.split(",") if s.strip()]

        cfg.rezlynx = RezLynxConfig(
            base_url=rl_block.get("base_url", ""),
            site_id=rl_block.get("site_id", cfg.site_id),
            live_sources=list(live_sources),
            interface_id=str(rl_block.get("interface_id", "727")),
            operator_code=rl_block.get("operator_code", "KILMURRY_API"),
            group_id=rl_block.get("group_id", ""),
            api_key_header=rl_block.get("api_key_header", "X-API-KEY"),
            timeout_seconds=int(rl_block.get("timeout_seconds", 30)),
            verify_ssl=bool(rl_block.get("verify_ssl", True)),
        )

        cfg.publish = PublishConfig(
            onedrive_root=Path(pub_block.get("onedrive_root", "./output")).expanduser(),
            feeds_dir=pub_block.get("feeds_dir", "feeds"),
            summaries_dir=pub_block.get("summaries_dir", "summaries"),
            manifests_dir=pub_block.get("manifests_dir", "manifests"),
            write_latest_pointer=bool(pub_block.get("write_latest_pointer", True)),
        )

        return cfg

    # Convenience helpers
    def feeds_path(self) -> Path:
        return self.publish.onedrive_root / self.publish.feeds_dir

    def summaries_path(self) -> Path:
        return self.publish.onedrive_root / self.publish.summaries_dir

    def manifests_path(self) -> Path:
        return self.publish.onedrive_root / self.publish.manifests_dir
