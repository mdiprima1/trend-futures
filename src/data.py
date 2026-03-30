"""
Data fetching and caching for futures and supplementary data.

Uses Databento for ES/NQ minute bars (continuous front-month).
Uses yfinance for SPY daily and VIX daily (free, sufficient for filters).
"""
import hashlib
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
import yfinance as yf

from src.config import DATABENTO_API_KEY, CACHE_DIR


def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{name}.parquet"


def _load_cache(name: str) -> pd.DataFrame | None:
    path = _cache_path(name)
    if path.exists():
        return pd.read_parquet(path)
    return None


def _save_cache(name: str, df: pd.DataFrame) -> None:
    df.to_parquet(_cache_path(name))


def fetch_futures_1m(
    symbol: str,
    start: str = "2018-01-01",
    end: str = "2025-12-31",
    force: bool = False,
) -> pd.DataFrame:
    """
    Fetch 1-minute OHLCV bars for a CME futures continuous front-month contract.

    Parameters
    ----------
    symbol : str
        Root symbol, e.g. "ES" or "NQ".
    start, end : str
        Date range in YYYY-MM-DD format.
    force : bool
        If True, bypass cache and re-download.

    Returns
    -------
    pd.DataFrame
        Columns: open, high, low, close, volume
        Index: DatetimeIndex in US/Eastern (market time)
    """
    cache_name = f"{symbol}_1m_{start}_{end}"

    if not force:
        cached = _load_cache(cache_name)
        if cached is not None:
            print(f"  Loaded {symbol} 1m from cache ({len(cached):,} bars)")
            return cached

    print(f"  Downloading {symbol} 1m bars from Databento ({start} to {end})...")
    client = db.Historical(DATABENTO_API_KEY)

    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        symbols=[f"{symbol}.c.0"],
        stype_in="continuous",
        schema="ohlcv-1m",
        start=start,
        end=end,
    )

    df = data.to_df()

    if df.empty:
        raise ValueError(f"No data returned for {symbol}")

    # Databento returns ts_event as index, prices in fixed-point (divide by 1e9)
    # Schema ohlcv-1m columns: open, high, low, close, volume
    price_cols = ["open", "high", "low", "close"]
    for col in price_cols:
        if col in df.columns:
            # Databento fixed-point prices: already float in ohlcv schema
            pass

    # Keep only OHLCV columns
    keep_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep_cols].copy()

    # Convert index to US/Eastern
    if df.index.tz is not None:
        df.index = df.index.tz_convert("US/Eastern")
    else:
        df.index = df.index.tz_localize("UTC").tz_convert("US/Eastern")

    # Filter to RTH (Regular Trading Hours): 9:30 - 16:00 ET
    df = df.between_time("09:30", "15:59")

    # Drop any rows with zero or NaN prices
    df = df[(df["close"] > 0) & df["close"].notna()]

    print(f"  {symbol}: {len(df):,} RTH bars, {df.index[0].date()} to {df.index[-1].date()}")
    _save_cache(cache_name, df)
    return df


def fetch_spy_daily(
    start: str = "2018-01-01",
    end: str = "2025-12-31",
    force: bool = False,
) -> pd.DataFrame:
    """Fetch SPY daily OHLCV from yfinance."""
    cache_name = f"SPY_daily_{start}_{end}"

    if not force:
        cached = _load_cache(cache_name)
        if cached is not None:
            print(f"  Loaded SPY daily from cache ({len(cached)} rows)")
            return cached

    print("  Downloading SPY daily from yfinance...")
    df = yf.download("SPY", start=start, end=end, auto_adjust=True, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    df.columns = [c.lower() for c in df.columns]
    df.index = pd.DatetimeIndex(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("US/Eastern")

    print(f"  SPY: {len(df)} daily bars")
    _save_cache(cache_name, df)
    return df


def fetch_vix_daily(
    start: str = "2018-01-01",
    end: str = "2025-12-31",
    force: bool = False,
) -> pd.Series:
    """Fetch VIX daily close from yfinance."""
    cache_name = f"VIX_daily_{start}_{end}"

    if not force:
        cached = _load_cache(cache_name)
        if cached is not None:
            print(f"  Loaded VIX daily from cache ({len(cached)} rows)")
            return cached["close"]

    print("  Downloading VIX daily from yfinance...")
    df = yf.download("^VIX", start=start, end=end, auto_adjust=True, progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)

    df.columns = [c.lower() for c in df.columns]
    df.index = pd.DatetimeIndex(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("US/Eastern")

    _save_cache(cache_name, df[["close"]])
    print(f"  VIX: {len(df)} daily bars")
    return df["close"]


def build_daily_bars(minute_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1-minute bars to daily OHLCV (RTH only)."""
    daily = minute_df.resample("1D").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["close"])
    return daily


def load_all_data(
    start: str = "2018-01-01",
    end: str = "2025-12-31",
    force: bool = False,
) -> dict:
    """
    Load all data needed for the ORB strategy.

    Returns dict with keys:
        es_1m, nq_1m: minute bars (pd.DataFrame)
        es_daily, nq_daily: daily bars aggregated from minute data
        spy_daily: SPY daily bars
        vix_daily: VIX daily close (pd.Series)
    """
    print("Loading data...")

    es_1m = fetch_futures_1m("ES", start, end, force)
    nq_1m = fetch_futures_1m("NQ", start, end, force)
    spy_daily = fetch_spy_daily(start, end, force)
    vix_daily = fetch_vix_daily(start, end, force)

    es_daily = build_daily_bars(es_1m)
    nq_daily = build_daily_bars(nq_1m)

    print("Data loading complete.\n")

    return {
        "es_1m": es_1m,
        "nq_1m": nq_1m,
        "es_daily": es_daily,
        "nq_daily": nq_daily,
        "spy_daily": spy_daily,
        "vix_daily": vix_daily,
    }
