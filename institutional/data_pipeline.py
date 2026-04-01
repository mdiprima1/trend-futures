"""
PHASE 2 — Data Pipeline

Clean, auditable data fetching and storage.
Uses EODHD API for adjusted daily OHLCV.
Stores as parquet with validation.
"""
import os
import time
import requests
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(".env")
EODHD_KEY = os.getenv("EODHD_API_KEY")
DATA_DIR = Path("institutional/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Universe ──

UNIVERSE = [
    # S&P 500 — diversified sample (200 most liquid)
    # Tech
    "AAPL","MSFT","AMZN","GOOGL","META","NVDA","TSLA","AVGO","ORCL","ADBE",
    "AMD","INTC","CRM","PYPL","CSCO","NFLX","QCOM","TXN","AMAT","MU",
    # Financials
    "JPM","BAC","WFC","GS","MS","C","BLK","SCHW","AXP","USB",
    "PNC","TFC","COF","BK","STT","FITB","RF","CFG","KEY","HBAN",
    # Healthcare
    "UNH","JNJ","LLY","PFE","ABBV","MRK","TMO","ABT","DHR","BMY",
    "AMGN","GILD","ISRG","MDT","ELV","CI","CVS","ZTS","REGN","VRTX",
    # Consumer Discretionary
    "HD","MCD","NKE","SBUX","TGT","LOW","TJX","ROST","DG","YUM",
    # Consumer Staples
    "WMT","PG","KO","PEP","COST","CL","KMB","GIS","SJM","MKC",
    # Industrials
    "CAT","GE","HON","UNP","BA","DE","LMT","RTX","MMM","FDX",
    "UPS","GD","NOC","ITW","EMR",
    # Energy
    "XOM","CVX","COP","SLB","EOG","MPC","VLO","PSX","OXY","HAL",
    "DVN","FANG","HES","WMB","KMI",
    # Materials
    "LIN","APD","SHW","ECL","NEM","FCX","NUE","DOW","CF",
    # Utilities
    "NEE","DUK","SO","AEP","D","SRE","EXC","XEL","WEC","ED",
    # Real Estate
    "PLD","AMT","CCI","EQIX","PSA","DLR","O","WELL","AVB","EQR",
    # Communications
    "DIS","CMCSA","T","VZ","TMUS","CHTR","EA",
    # ETFs (no survivorship bias)
    "SPY","QQQ","IWM","XLF","XLE","XLK","XLV","XLP","XLI","XLU",
    "XLB","XLRE","XLC","GLD","TLT","HYG","LQD","EEM","EFA","VNQ",
]

START_DATE = "2014-01-01"
END_DATE = "2025-01-01"


def fetch_stock(ticker):
    """Fetch daily OHLCV from EODHD. Returns DataFrame or None."""
    cache = DATA_DIR / f"{ticker}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)

    url = f"https://eodhd.com/api/eod/{ticker}.US"
    params = {"api_token": EODHD_KEY, "period": "d",
              "from": START_DATE, "to": END_DATE, "fmt": "json"}
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if not data or isinstance(data, dict):
            return None
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        df = df.rename(columns={"adjusted_close": "adj_close"})
        df = df[["open", "high", "low", "close", "adj_close", "volume"]].astype(float)

        # Basic validation
        if len(df) < 500:
            return None
        if df["close"].isna().sum() > len(df) * 0.05:
            return None  # >5% missing data

        df.to_parquet(cache)
        return df
    except Exception as e:
        return None


def load_universe(force_download=False):
    """Load all stocks in universe. Returns dict {ticker: DataFrame}."""
    data = {}
    failed = []

    for i, ticker in enumerate(UNIVERSE):
        if i % 50 == 0:
            print(f"  [{i}/{len(UNIVERSE)}] loading...", flush=True)

        if force_download:
            cache = DATA_DIR / f"{ticker}.parquet"
            if cache.exists():
                cache.unlink()

        df = fetch_stock(ticker)
        if df is not None:
            data[ticker] = df
        else:
            failed.append(ticker)
        time.sleep(0.12)

    print(f"  Loaded {len(data)} / {len(UNIVERSE)} stocks")
    if failed:
        print(f"  Failed ({len(failed)}): {failed[:20]}...")

    return data


def validate_data(data):
    """Run data integrity checks. Returns validation report."""
    report = {
        "n_stocks": len(data),
        "date_range": {},
        "missing_data": {},
        "zero_volume_days": {},
        "price_gaps": {},
        "issues": [],
    }

    all_dates = set()
    for ticker, df in data.items():
        all_dates.update(df.index.tolist())

    common_start = max(df.index[0] for df in data.values())
    common_end = min(df.index[-1] for df in data.values())
    report["date_range"] = {
        "common_start": str(common_start.date()),
        "common_end": str(common_end.date()),
        "total_trading_days": len(pd.bdate_range(common_start, common_end)),
    }

    for ticker, df in data.items():
        # Missing data
        n_missing = df["close"].isna().sum()
        if n_missing > 0:
            report["missing_data"][ticker] = int(n_missing)

        # Zero volume
        n_zero_vol = (df["volume"] == 0).sum()
        if n_zero_vol > 10:
            report["zero_volume_days"][ticker] = int(n_zero_vol)

        # Large price gaps (>20% in one day — possible split issue)
        returns = df["adj_close"].pct_change().dropna()
        large_gaps = returns[returns.abs() > 0.20]
        if len(large_gaps) > 5:
            report["price_gaps"][ticker] = len(large_gaps)
            report["issues"].append(f"{ticker}: {len(large_gaps)} days with >20% move")

    report["summary"] = {
        "stocks_with_missing": len(report["missing_data"]),
        "stocks_with_zero_vol": len(report["zero_volume_days"]),
        "stocks_with_gaps": len(report["price_gaps"]),
        "total_issues": len(report["issues"]),
    }

    return report


def build_aligned_panel(data, start="2014-06-01", end="2024-12-31"):
    """
    Build aligned price panel. All stocks on same date index.
    Forward-fills up to 5 days, then NaN.
    Returns dict of DataFrames: {field: DataFrame with tickers as columns}
    """
    start_dt = pd.Timestamp(start)
    end_dt = pd.Timestamp(end)

    # Common business day index
    idx = pd.bdate_range(start_dt, end_dt)

    panels = {}
    for field in ["open", "high", "low", "close", "adj_close", "volume"]:
        panel = pd.DataFrame(index=idx)
        for ticker, df in data.items():
            series = df[field].reindex(idx)
            series = series.ffill(limit=5)  # Forward fill max 5 days
            panel[ticker] = series
        panels[field] = panel

    return panels


if __name__ == "__main__":
    import json

    print("=" * 70)
    print("PHASE 2: DATA PIPELINE")
    print("=" * 70)

    data = load_universe()

    print("\nValidating data...")
    report = validate_data(data)
    print(f"  Stocks loaded: {report['n_stocks']}")
    print(f"  Common period: {report['date_range']['common_start']} to {report['date_range']['common_end']}")
    print(f"  Issues: {report['summary']['total_issues']}")

    # Save validation report
    report_path = Path("institutional/reports/data_validation_report.md")
    with open(report_path, "w") as f:
        f.write("# Data Validation Report\n\n")
        f.write(f"## Summary\n")
        f.write(f"- Stocks loaded: {report['n_stocks']}\n")
        f.write(f"- Period: {report['date_range']['common_start']} to {report['date_range']['common_end']}\n")
        f.write(f"- Trading days: {report['date_range']['total_trading_days']}\n")
        f.write(f"- Stocks with missing data: {report['summary']['stocks_with_missing']}\n")
        f.write(f"- Stocks with zero volume: {report['summary']['stocks_with_zero_vol']}\n")
        f.write(f"- Stocks with large gaps: {report['summary']['stocks_with_gaps']}\n")
        if report["issues"]:
            f.write(f"\n## Issues\n")
            for issue in report["issues"][:20]:
                f.write(f"- {issue}\n")

    print(f"\n  Building aligned panel...")
    panels = build_aligned_panel(data)
    for field, panel in panels.items():
        panel.to_parquet(DATA_DIR / f"panel_{field}.parquet")
    print(f"  Saved {len(panels)} panel files")

    # Save report JSON
    Path("institutional/reports/data_validation.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"  Validation report saved")
    print(f"\nPhase 2 complete.")
