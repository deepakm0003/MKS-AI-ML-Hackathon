"""Paths and canonical reference values used across the pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
QUALITY = ROOT / "outputs" / "quality"

HISTORY_START = "2019-01"
HISTORY_END = "2026-10"
FORECAST_START = "2026-11"
FORECAST_END = "2028-05"

REGIONS = [
    "North America", "Europe", "Asia Pacific", "India",
    "Latin America", "Middle East & Africa",
]
CHANNELS = ["Direct OEM", "Tier-1 Distributor", "Aftermarket", "Export"]

# Every spelling seen in the raw extract, lower-cased and stripped -> canonical label.
REGION_ALIASES = {
    "north america": "North America", "n. america": "North America", "na": "North America",
    "europe": "Europe", "eu": "Europe",
    "asia pacific": "Asia Pacific", "asia-pacific": "Asia Pacific", "apac": "Asia Pacific",
    "india": "India",
    "latin america": "Latin America", "latin-america": "Latin America", "latam": "Latin America",
    "middle east & africa": "Middle East & Africa", "middle east and africa": "Middle East & Africa",
    "me&a": "Middle East & Africa", "mea": "Middle East & Africa",
}
CHANNEL_ALIASES = {
    "direct oem": "Direct OEM", "direct-oem": "Direct OEM", "oem direct": "Direct OEM",
    "tier-1 distributor": "Tier-1 Distributor", "tier 1 distributor": "Tier-1 Distributor",
    "t1 distributor": "Tier-1 Distributor",
    "aftermarket": "Aftermarket", "after-market": "Aftermarket",
    "export": "Export",
}

# Tolerances used when reconciling units x price = revenue.
PRICE_TOL = 0.02     # a price within 2% of the SKU reference price is treated as correct
RECON_TOL = 0.02     # units x price within 2% of revenue reconciles
EUR_PER_USD = 0.89   # Europe rows priced at 0.89x list are EUR amounts booked as USD
