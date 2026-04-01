#!/usr/bin/env python3
"""
DEEP RESEARCH — All Technical Indicators × S&P 500 × 10 Years

Uses ta library (86 indicators) on ~500 stocks.
For each indicator, tests mean-reversion signals at percentile thresholds.
Measures: next-day return, 3-day return, 5-day return after signal fires.

Output: which indicators predict positive forward returns most reliably.
"""
import os
import sys
import time
import json
import requests
import numpy as np
import pandas as pd
import ta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(".env")
EODHD_KEY = os.getenv("EODHD_API_KEY")
DATA_DIR = Path("casino-stocks/data/sp500")
RESULTS_DIR = Path("casino-stocks/results/deep_research")
DATA_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# ── S&P 500 Universe ──

SP500 = [
    "AAPL","MSFT","AMZN","GOOGL","GOOG","META","NVDA","TSLA","AVGO","ORCL",
    "ADBE","AMD","INTC","CRM","PYPL","CSCO","NFLX","QCOM","TXN","AMAT",
    "MU","LRCX","KLAC","SNPS","CDNS","MRVL","FTNT","PANW",
    "JPM","BAC","WFC","GS","MS","C","BLK","SCHW","AXP","USB","PNC","TFC",
    "COF","BK","STT","FITB","RF","CFG","KEY","HBAN","ZION","CMA",
    "UNH","JNJ","LLY","PFE","ABBV","MRK","TMO","ABT","DHR","BMY",
    "AMGN","GILD","ISRG","MDT","ELV","CI","HUM","CVS","ZTS","REGN",
    "WMT","PG","KO","PEP","COST","HD","MCD","NKE","SBUX","TGT",
    "LOW","TJX","ROST","DG","DLTR","YUM","CMG","DPZ",
    "CAT","GE","HON","UNP","BA","DE","LMT","RTX","MMM","FDX",
    "UPS","GD","NOC","LHX","TDG","ITW","EMR","ROK",
    "XOM","CVX","COP","SLB","EOG","MPC","VLO","PSX","OXY","HAL",
    "PXD","DVN","FANG","HES","WMB","KMI","OKE",
    "LIN","APD","SHW","ECL","NEM","FCX","NUE","DOW","CF","ALB",
    "DIS","CMCSA","T","VZ","TMUS","CHTR","EA","TTWO",
    "NEE","DUK","SO","AEP","D","SRE","EXC","XEL","WEC","ED",
    "PLD","AMT","CCI","EQIX","PSA","DLR","O","WELL","AVB","EQR",
    "V","MA","FIS","FISV","GPN","ADP","PAYX","CPAY",
    "SPY","QQQ","IWM","XLF","XLE","XLK","XLV","XLP","XLI","XLU",
    "GLD","TLT","HYG","LQD","EEM","EFA","VNQ","XBI",
    "SQ","SHOP","UBER","ABNB","COIN","SNAP","PINS","ROKU","ZM","DKNG",
    "RIVN","LCID","PLTR","SOFI","HOOD","PATH","CRWD","DDOG","SNOW","NET",
    "ENPH","SEDG","FSLR","RUN",
    "SMCI","ARM","MSTR",
]


def fetch_stock(ticker, start="2014-01-01", end="2025-01-01"):
    """Fetch from EODHD with caching."""
    cache = DATA_DIR / f"{ticker}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)

    url = f"https://eodhd.com/api/eod/{ticker}.US"
    params = {"api_token": EODHD_KEY, "period": "d", "from": start, "to": end, "fmt": "json"}
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
        df.to_parquet(cache)
        return df
    except:
        return None


def compute_indicators(df):
    """Compute all 86 ta indicators. Returns DataFrame with indicator columns."""
    try:
        result = ta.add_all_ta_features(
            df.copy(), open="open", high="high", low="low",
            close="close", volume="volume", fillna=True,
        )
        indicator_cols = [c for c in result.columns if c not in ["open","high","low","close","volume","adj_close"]]
        return result[indicator_cols]
    except:
        return pd.DataFrame()


def compute_forward_returns(df, periods=[1, 2, 3, 5]):
    """Compute forward returns at various horizons."""
    returns = {}
    for p in periods:
        returns[f"fwd_{p}d"] = df["adj_close"].pct_change(p).shift(-p) * 100
    return pd.DataFrame(returns, index=df.index)


def analyze_indicator(indicator_values, forward_returns, indicator_name):
    """
    For one indicator, check if extreme values predict forward returns.
    Tests: bottom 10%, bottom 20%, top 80%, top 90% percentiles.
    """
    results = []
    vals = indicator_values.dropna()
    if len(vals) < 200:
        return results

    # Compute percentiles
    for pctile, direction, label in [
        (10, "long", "P10_long"),   # Bottom 10% → buy (mean reversion)
        (20, "long", "P20_long"),   # Bottom 20% → buy
        (80, "short", "P80_short"), # Top 80% → sell
        (90, "short", "P90_short"), # Top 90% → sell
    ]:
        threshold = np.percentile(vals, pctile)
        if direction == "long":
            mask = indicator_values < threshold
        else:
            mask = indicator_values > threshold

        mask = mask & mask.notna()
        n_signals = mask.sum()
        if n_signals < 20:
            continue

        for fwd_col in forward_returns.columns:
            fwd = forward_returns.loc[mask, fwd_col].dropna()
            if len(fwd) < 20:
                continue

            avg_return = fwd.mean()
            win_rate = (fwd > 0).mean() * 100
            t_stat = avg_return / (fwd.std() / np.sqrt(len(fwd))) if fwd.std() > 0 else 0

            results.append({
                "indicator": indicator_name,
                "signal": label,
                "threshold": round(threshold, 4),
                "n_signals": int(n_signals),
                "horizon": fwd_col,
                "avg_return_pct": round(avg_return, 4),
                "win_rate": round(win_rate, 2),
                "t_stat": round(t_stat, 3),
                "direction": direction,
            })

    return results


def process_stock(ticker, stock_data):
    """Process one stock: compute indicators, forward returns, analyze all."""
    df = stock_data
    if df is None or len(df) < 500:
        return []

    # Compute indicators
    indicators = compute_indicators(df)
    if indicators.empty:
        return []

    # Compute forward returns
    fwd_returns = compute_forward_returns(df)

    # Analyze each indicator
    all_results = []
    for col in indicators.columns:
        try:
            results = analyze_indicator(indicators[col], fwd_returns, col)
            for r in results:
                r["ticker"] = ticker
            all_results.extend(results)
        except:
            continue

    return all_results


def main():
    t0 = time.time()
    print("=" * 70)
    print("DEEP RESEARCH — ALL INDICATORS × S&P 500 × 10 YEARS")
    print("=" * 70)
    print(f"Universe: {len(SP500)} tickers")
    print(f"Indicators: 86 (ta library)")
    print(f"Period: 2014-2024 (10 years)")
    print(f"Analysis: percentile thresholds → forward returns")

    # Phase 1: Download data
    print(f"\n{'='*70}")
    print("PHASE 1: DOWNLOADING DATA")
    print(f"{'='*70}")

    stock_data = {}
    for i, ticker in enumerate(SP500):
        if i % 50 == 0:
            print(f"  [{i}/{len(SP500)}] downloading...", flush=True)
        df = fetch_stock(ticker)
        if df is not None and len(df) > 500:
            stock_data[ticker] = df
        time.sleep(0.12)  # EODHD rate limit

    print(f"  Loaded {len(stock_data)} stocks with >500 daily bars")

    # Phase 2: Process all stocks
    print(f"\n{'='*70}")
    print("PHASE 2: COMPUTING INDICATORS & ANALYZING")
    print(f"{'='*70}")

    all_results = []
    for i, (ticker, df) in enumerate(stock_data.items()):
        if i % 25 == 0:
            print(f"  [{i}/{len(stock_data)}] {ticker}... ({len(all_results)} results so far)", flush=True)

        results = process_stock(ticker, df)
        all_results.extend(results)

    print(f"  Total results: {len(all_results)}")

    # Phase 3: Aggregate and rank
    print(f"\n{'='*70}")
    print("PHASE 3: AGGREGATING RESULTS")
    print(f"{'='*70}")

    results_df = pd.DataFrame(all_results)
    if results_df.empty:
        print("No results!"); return

    results_df.to_csv(RESULTS_DIR / "all_results.csv", index=False)

    # Aggregate by indicator × signal × horizon (avg across all stocks)
    agg = results_df.groupby(["indicator", "signal", "horizon", "direction"]).agg(
        n_stocks=("ticker", "nunique"),
        total_signals=("n_signals", "sum"),
        avg_return=("avg_return_pct", "mean"),
        median_return=("avg_return_pct", "median"),
        avg_win_rate=("win_rate", "mean"),
        avg_t_stat=("t_stat", "mean"),
        pct_stocks_positive=("avg_return_pct", lambda x: (x > 0).mean() * 100),
    ).reset_index()

    agg.to_csv(RESULTS_DIR / "aggregated_results.csv", index=False)

    # ── Report: Top indicators ──

    # LONG signals: buy on extreme low indicator → positive forward return
    longs = agg[(agg["direction"] == "long") & (agg["horizon"] == "fwd_1d")].sort_values("avg_return", ascending=False)
    print(f"\n  TOP 30 LONG SIGNALS (1-day forward return, avg across stocks):")
    print(f"  {'Indicator':>30s}  {'Signal':>10s}  {'Stocks':>6s}  {'AvgRet':>7s}  {'WR':>5s}  {'t':>5s}  {'%Pos':>5s}")
    for _, r in longs.head(30).iterrows():
        print(f"  {r['indicator']:>30s}  {r['signal']:>10s}  {r['n_stocks']:>6.0f}  {r['avg_return']:>+6.3f}%  {r['avg_win_rate']:>4.1f}%  {r['avg_t_stat']:>5.2f}  {r['pct_stocks_positive']:>4.0f}%")

    # Same for 3-day
    longs3 = agg[(agg["direction"] == "long") & (agg["horizon"] == "fwd_3d")].sort_values("avg_return", ascending=False)
    print(f"\n  TOP 20 LONG SIGNALS (3-day forward return):")
    print(f"  {'Indicator':>30s}  {'Signal':>10s}  {'AvgRet':>7s}  {'WR':>5s}  {'t':>5s}  {'%Pos':>5s}")
    for _, r in longs3.head(20).iterrows():
        print(f"  {r['indicator']:>30s}  {r['signal']:>10s}  {r['avg_return']:>+6.3f}%  {r['avg_win_rate']:>4.1f}%  {r['avg_t_stat']:>5.2f}  {r['pct_stocks_positive']:>4.0f}%")

    # SHORT signals: sell on extreme high indicator
    shorts = agg[(agg["direction"] == "short") & (agg["horizon"] == "fwd_1d")].sort_values("avg_return", ascending=True)
    print(f"\n  TOP 20 SHORT SIGNALS (most negative 1-day fwd return = best shorts):")
    print(f"  {'Indicator':>30s}  {'Signal':>10s}  {'AvgRet':>7s}  {'WR':>5s}  {'%Neg':>5s}")
    for _, r in shorts.head(20).iterrows():
        pct_neg = 100 - r['pct_stocks_positive']
        print(f"  {r['indicator']:>30s}  {r['signal']:>10s}  {r['avg_return']:>+6.3f}%  {r['avg_win_rate']:>4.1f}%  {pct_neg:>4.0f}%")

    # Most consistent across stocks (highest % of stocks where signal is profitable)
    consistent = agg[(agg["direction"] == "long") & (agg["horizon"] == "fwd_1d") & (agg["n_stocks"] >= 50)].sort_values("pct_stocks_positive", ascending=False)
    print(f"\n  MOST CONSISTENT ACROSS STOCKS (>50 stocks, long, 1-day):")
    print(f"  {'Indicator':>30s}  {'Signal':>10s}  {'Stocks':>6s}  {'%Positive':>10s}  {'AvgRet':>7s}  {'WR':>5s}")
    for _, r in consistent.head(20).iterrows():
        print(f"  {r['indicator']:>30s}  {r['signal']:>10s}  {r['n_stocks']:>6.0f}  {r['pct_stocks_positive']:>9.0f}%  {r['avg_return']:>+6.3f}%  {r['avg_win_rate']:>4.1f}%")

    # Best signals by t-statistic (statistical significance)
    significant = agg[(agg["direction"] == "long") & (agg["horizon"] == "fwd_1d") & (agg["avg_t_stat"] > 0)].sort_values("avg_t_stat", ascending=False)
    print(f"\n  MOST STATISTICALLY SIGNIFICANT (long, 1-day, by avg t-stat):")
    print(f"  {'Indicator':>30s}  {'Signal':>10s}  {'t-stat':>7s}  {'AvgRet':>7s}  {'WR':>5s}  {'%Pos':>5s}")
    for _, r in significant.head(20).iterrows():
        print(f"  {r['indicator']:>30s}  {r['signal']:>10s}  {r['avg_t_stat']:>7.3f}  {r['avg_return']:>+6.3f}%  {r['avg_win_rate']:>4.1f}%  {r['pct_stocks_positive']:>4.0f}%")

    # Summary stats
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  Stocks processed: {len(stock_data)}")
    print(f"  Total indicator×signal×stock results: {len(results_df)}")
    print(f"  Unique indicators tested: {results_df['indicator'].nunique()}")
    print(f"  Profitable long signals (avg across stocks): {len(longs[longs['avg_return'] > 0])}")
    print(f"  Results saved to: {RESULTS_DIR}")

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed/60:.1f} minutes")


if __name__ == "__main__":
    main()
