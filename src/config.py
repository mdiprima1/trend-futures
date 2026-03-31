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
    # Equity Indices
    "ES": 50.0,        # E-mini S&P 500
    "NQ": 20.0,        # E-mini Nasdaq 100
    "RTY": 50.0,       # E-mini Russell 2000
    "NKD": 5.0,        # Nikkei 225 (USD-denominated)
    # Fixed Income
    "ZT": 2000.0,      # 2-Year T-Note
    "ZN": 1000.0,      # 10-Year T-Note
    "ZB": 1000.0,      # 30-Year T-Bond
    # FX
    "6E": 125000.0,    # Euro FX
    "6B": 62500.0,     # British Pound
    "6J": 12500000.0,  # Japanese Yen
    "6A": 100000.0,    # Australian Dollar
    "6C": 100000.0,    # Canadian Dollar
    "6S": 125000.0,    # Swiss Franc
    "6N": 100000.0,    # New Zealand Dollar
    # Energy
    "CL": 1000.0,      # Crude Oil WTI
    "NG": 10000.0,     # Natural Gas
    "RB": 42000.0,     # RBOB Gasoline
    "HO": 42000.0,     # Heating Oil
    # Metals
    "GC": 100.0,       # Gold
    "SI": 5000.0,      # Silver
    "HG": 25000.0,     # Copper
    "PL": 50.0,        # Platinum
    # Agriculture
    "ZC": 50.0,        # Corn
    "ZS": 50.0,        # Soybeans
    "ZW": 50.0,        # Wheat
    "LE": 40000.0,     # Live Cattle
}

# IB commissions per contract (round trip)
COMMISSIONS = {s: 2.10 for s in CONTRACT_MULTIPLIERS}
COMMISSIONS["ZT"] = 1.52
COMMISSIONS["ZN"] = 1.52
COMMISSIONS["ZB"] = 1.52

# Sector classification
SECTORS = {
    "Equity": ["ES", "NQ", "RTY", "NKD"],
    "Fixed Income": ["ZT", "ZN", "ZB"],
    "FX": ["6E", "6B", "6J", "6A", "6C", "6S", "6N"],
    "Energy": ["CL", "NG", "RB", "HO"],
    "Metals": ["GC", "SI", "HG", "PL"],
    "Agriculture": ["ZC", "ZS", "ZW", "LE"],
}

# Reverse lookup: symbol → sector
SYMBOL_SECTOR = {}
for sector, symbols in SECTORS.items():
    for s in symbols:
        SYMBOL_SECTOR[s] = sector
