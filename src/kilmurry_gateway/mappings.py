"""Canonical mappings between live RezLynx sources.

Sources differ in their representation:

- SOAP `bookings.source` is the **display name** ("Booking.com", "Avvio", ...).
- Report Data `booked-revenue.media_source` is **UPPER_SNAKE** ("BOOKING_COM").
- SOAP `bookings.extra_fields.distribution_channel_id` is an **integer**
  Guestline internal ID. We capture it for future mapping but do not need
  it for Phase 1 display.

Phase 1 evidence (Hunter 2026-03-04) shows 5 production channels for
Kilmurry. Update this table when new channels appear.
"""
from __future__ import annotations

# SOAP source name -> Report Data media_source code (for joins on segment
# and channel revenue blocks). Production evidence (Hunter 2026-03-04):
#
#  Booked-revenue media_source values observed: EMAIL, WEBSITE,
#  BOOKING_COM, SYNXIS, EXPEDIA, PHONE, WALK_IN.
#  SOAP booking sources observed: Avvio, Booking.com, Expedia,
#  HotelBeds, SynXis (plus 49 rows with NO source).
#
# Note: Avvio (booking engine for direct website) maps to WEBSITE in
# revenue media. The 49 SOAP rows with empty source likely correspond
# to EMAIL/PHONE/WALK_IN revenue rows. This will need a small
# heuristic when we have more days of data to confirm.
SOAP_SOURCE_TO_REPORT_MEDIA: dict[str, str] = {
    "Booking.com": "BOOKING_COM",
    "Expedia": "EXPEDIA",
    "Avvio": "WEBSITE",       # Avvio = direct website booking engine
    "HotelBeds": "HOTELBEDS",
    "SynXis": "SYNXIS",
}

# Inverse lookup: media_source code -> SOAP source name.
# For codes that don't have a direct SOAP source (EMAIL, PHONE, WALK_IN),
# we fall back to a Title-Case display name.
REPORT_MEDIA_TO_SOAP_SOURCE: dict[str, str] = {
    "BOOKING_COM": "Booking.com",
    "EXPEDIA": "Expedia",
    "WEBSITE": "Avvio",        # direct website -> Avvio in our display
    "HOTELBEDS": "HotelBeds",
    "SYNXIS": "SynXis",
    "EMAIL": "Email",
    "PHONE": "Phone",
    "WALK_IN": "Walk-in",
}


def normalise_channel_name(name: str | None) -> str:
    """Pretty-print channel for display. Handles the Avvio/AVVIO quirk.

    The legacy HotSoft data had an inconsistent capitalisation quirk where
    AVVIO bookings were routed to Group Blocks. In RezLynx the canonical
    casing is `Avvio`. We normalise everything to canonical form.
    """
    if not name:
        return "Unmapped"
    upper = name.upper().strip()
    if upper == "AVVIO":
        return "Avvio"
    if upper == "BOOKING.COM":
        return "Booking.com"
    # Fall back to title-cased, but preserve known canonical names exactly.
    for canonical in SOAP_SOURCE_TO_REPORT_MEDIA:
        if upper == canonical.upper():
            return canonical
    return name


# Market segments are short codes in BOTH sources, no mapping required.
KNOWN_SEGMENTS = {"CORPORATE", "DIRECT", "OTA", "COMP", "GDS", "LNR"}

# RezLynx-native booking statuses (full set seen in production).
KNOWN_STATUSES = {
    "PreArrival", "Resident", "CheckedOut", "Cancelled", "NoShow", "Waitlist",
}


def segment_display(code: str | None) -> str:
    """Pretty-print segment code. Phase 1 keeps codes as-is for trust."""
    if not code:
        return "Unmapped"
    # Future: map LNR -> "Local Negotiated Rate" etc. Keep raw for now.
    return code.upper().strip()
