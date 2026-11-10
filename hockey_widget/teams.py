"""The 32 NHL teams: panel colour for the widget and logo address on the NHL CDN.

Colours are each team's main colour, darkened where needed so white text stays readable.
"""

from __future__ import annotations

LOGO_URL = "https://assets.nhle.com/logos/nhl/svg/{abbrev}_dark.svg"  # version made for dark backgrounds
DEFAULT_COLOR = "#2A2F36"

COLORS: dict[str, str] = {
    "ANA": "#C9531B", "BOS": "#1C1C1C", "BUF": "#003087", "CGY": "#C8102E",
    "CAR": "#CE1126", "CHI": "#CF0A2C", "COL": "#6F263D", "CBJ": "#002654",
    "DAL": "#006847", "DET": "#CE1126", "EDM": "#041E42", "FLA": "#C8102E",
    "LAK": "#1C1C1C", "MIN": "#154734", "MTL": "#AF1E2D", "NSH": "#041E42",
    "NJD": "#CE1126", "NYI": "#00539B", "NYR": "#0038A8", "OTT": "#C52032",
    "PHI": "#D64000", "PIT": "#1C1C1C", "SJS": "#006D75", "SEA": "#001628",
    "STL": "#002F87", "TBL": "#002868", "TOR": "#00205B", "UTA": "#0B1F33",
    "VAN": "#00205B", "VGK": "#333F42", "WSH": "#C8102E", "WPG": "#041E42",
}


def color(abbrev: str) -> str:
    return COLORS.get(abbrev, DEFAULT_COLOR)


def logo(abbrev: str) -> str:
    return LOGO_URL.format(abbrev=abbrev) if abbrev in COLORS else ""
