"""Kilmurry Desktop Data Gateway.

Pulls data from the Guestline RezLynx PMS, normalises it to the
`kilmurry.rezlynx.revenue_feed.v1` contract, and publishes JSON + HTML
artifacts into a OneDrive-synced folder for OpenClaw to consume.

Phase 1 MVP — see project planning docs for scope.
"""

__version__ = "0.1.0"
SCHEMA_ID = "kilmurry.rezlynx.revenue_feed.v1"
