"""Central configuration for Trend Futures project."""
from pathlib import Path
from dotenv import load_dotenv
import os

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

DATABENTO_API_KEY = os.getenv("DATABENTO_API_KEY")
CACHE_DIR = ROOT_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Futures contract multipliers (for PnL calculation)
CONTRACT_MULTIPLIERS = {
    "ES": 50.0,   # E-mini S&P 500: $50 per point
    "NQ": 20.0,   # E-mini Nasdaq 100: $20 per point
}

# IB commissions per contract (round trip)
COMMISSIONS = {
    "ES": 2.10,   # ~$1.05 each way
    "NQ": 2.10,
}
