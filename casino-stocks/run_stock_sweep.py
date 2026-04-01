#!/usr/bin/env python3
"""
Casino Stocks — Comprehensive Technical Indicator Test

Test RSI, IBS, Bollinger, Keltner, MACD, momentum on 100+ stocks.
Daily bars, triple barrier exits, defined bets.

Key advantage over futures:
- Commission: $0.005/share (vs $2.10/contract)
- 100+ independent instruments = many uncorrelated bets
- No roll issues
- QC calibration proven on stocks (4 PERFECT tests)
"""
import sys
import os
import time
import json
import requests
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv(".env")
EODHD_KEY = os.getenv("EODHD_API_KEY")

# ── Stock Universe ──
# Top 100 most liquid US stocks by volume
UNIVERSE = [
    # Mega cap tech
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "AVGO", "ORCL", "ADBE",
    # Financials
    "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "USB",
    # Healthcare
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY",
    # Consumer
    "WMT", "PG", "KO", "PEP", "COST", "HD", "MCD", "NKE", "SBUX", "TGT",
    # Industrials
    "CAT", "GE", "HON", "UNP", "BA", "RTX", "DE", "LMT", "MMM", "FDX",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "VLO", "PSX", "OXY", "HAL",
    # Communications
    "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR", "EA", "ATVI", "WBD",
    # Materials
    "LIN", "APD", "SHW", "ECL", "DD", "NEM", "FCX", "NUE", "DOW", "CF",
    # ETFs for sector comparison
    "SPY", "QQQ", "IWM", "XLF", "XLE", "XLK", "XLV", "XLP", "GLD", "TLT",
    # More tech/growth
    "AMD", "INTC", "CRM", "PYPL", "SQ", "SHOP", "UBER", "ABNB", "COIN", "SNAP",
]

# ── Data Loading ──

def fetch_stock(ticker, start="2018-01-01", end="2025-01-01"):
    """Fetch daily OHLCV from EODHD."""
    cache = Path(f"casino-stocks/data/{ticker}.parquet")
    if cache.exists():
        return pd.read_parquet(cache)

    url = f"https://eodhd.com/api/eod/{ticker}.US"
    params = {"api_token": EODHD_KEY, "period": "d", "from": start, "to": end, "fmt": "json"}
    try:
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        if not data or isinstance(data, dict):
            return None
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        df = df.rename(columns={"adjusted_close": "adj_close"})
        df = df[["open", "high", "low", "close", "adj_close", "volume"]].astype(float)
        # Use adjusted close for signals, raw close for fills
        df.to_parquet(cache)
        return df
    except Exception as e:
        return None


def load_universe():
    """Load all stocks, return dict of {ticker: df}."""
    print(f"Loading {len(UNIVERSE)} stocks from EODHD...")
    data = {}
    for i, ticker in enumerate(UNIVERSE):
        if i % 20 == 0:
            print(f"  [{i}/{len(UNIVERSE)}]...", end=" ", flush=True)
        df = fetch_stock(ticker)
        if df is not None and len(df) > 500:
            data[ticker] = df
        time.sleep(0.15)  # Rate limit
    print(f"\n  Loaded {len(data)} stocks with >500 bars")
    return data


# ── Indicators ──

def rsi(closes, period=3):
    d = np.diff(closes)
    result = np.full(len(closes), 50.0)
    for i in range(period + 1, len(closes)):
        g = np.mean(np.maximum(d[i-period:i], 0))
        l = np.mean(np.maximum(-d[i-period:i], 0))
        result[i] = 100 - 100/(1+g/l) if l > 0 else 100
    return result


def ibs(highs, lows, closes):
    rng = highs - lows
    return np.where(rng > 0, (closes - lows) / rng, 0.5)


def atr(highs, lows, closes, period=14):
    pc = np.roll(closes, 1); pc[0] = closes[0]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - pc), np.abs(lows - pc)))
    result = np.full(len(closes), 0.0)
    for i in range(period, len(closes)):
        result[i] = np.mean(tr[i-period+1:i+1])
    return result


def bollinger_position(closes, period=20):
    """Returns z-score: (close - mid) / std."""
    result = np.full(len(closes), 0.0)
    for i in range(period, len(closes)):
        mid = np.mean(closes[i-period+1:i+1])
        std = np.std(closes[i-period+1:i+1])
        result[i] = (closes[i] - mid) / std if std > 0 else 0
    return result


# ── Signal Functions ──

def sig_rsi_mr(df, os_thresh=25, ob_thresh=75, period=3):
    c = df["adj_close"].values
    r = rsi(c, period)
    sig = np.zeros(len(c))
    sig[r < os_thresh] = 1
    sig[r > ob_thresh] = -1
    return pd.Series(sig, index=df.index)


def sig_ibs_mr(df, low=0.15, high=0.85):
    i = ibs(df["high"].values, df["low"].values, df["close"].values)
    sig = np.zeros(len(i))
    sig[i < low] = 1
    sig[i > high] = -1
    return pd.Series(sig, index=df.index)


def sig_boll_mr(df, period=20, threshold=2.0):
    z = bollinger_position(df["adj_close"].values, period)
    sig = np.zeros(len(z))
    sig[z < -threshold] = 1
    sig[z > threshold] = -1
    return pd.Series(sig, index=df.index)


# ── Bet Engine (Daily) ──

def run_bets(df, signals, pt_atr=1.5, sl_atr=1.0, max_days=5):
    """Run triple barrier bets on daily stock data."""
    closes = df["adj_close"].values
    highs = df["high"].values
    lows = df["low"].values
    atr_vals = atr(highs, lows, closes, 14)

    bets = []
    in_trade = False
    t_dir = 0; t_entry = 0; t_pt = 0; t_sl = 0; t_bars = 0; t_time = None

    for i in range(20, len(df)):
        s = signals.iloc[i]
        c = closes[i]; h = highs[i]; l = lows[i]
        a = atr_vals[i]

        if in_trade:
            t_bars -= 1
            hit = False; won = False; exit_p = c

            if t_dir == 1:
                if l <= t_sl: hit=True; won=False; exit_p=t_sl
                elif h >= t_pt: hit=True; won=True; exit_p=t_pt
            else:
                if h >= t_sl: hit=True; won=False; exit_p=t_sl
                elif l <= t_pt: hit=True; won=True; exit_p=t_pt

            if t_bars <= 0 and not hit:
                hit=True; exit_p=c; won=(c - t_entry) * t_dir > 0

            if hit:
                pnl_pct = (exit_p - t_entry) / t_entry * t_dir * 100
                bets.append({
                    "entry_date": t_time, "exit_date": df.index[i],
                    "dir": t_dir, "entry": t_entry, "exit": exit_p,
                    "pnl_pct": pnl_pct, "result": "W" if won else "L",
                })
                in_trade = False
                # Fall through for re-entry
            else:
                continue

        if s == 0 or a <= 0: continue
        if in_trade: continue

        # Enter
        t_dir = int(s); t_entry = c; t_time = df.index[i]
        if t_dir == 1:
            t_pt = c + pt_atr * a; t_sl = c - sl_atr * a
        else:
            t_pt = c - pt_atr * a; t_sl = c + sl_atr * a
        t_bars = max_days; in_trade = True

    return pd.DataFrame(bets) if bets else pd.DataFrame()


def bet_stats(bets, ticker=""):
    if bets.empty:
        return None
    n = len(bets)
    wins = (bets["result"] == "W").sum()
    wr = wins / n * 100
    avg_win = bets.loc[bets["result"] == "W", "pnl_pct"].mean() if wins > 0 else 0
    avg_loss = bets.loc[bets["result"] == "L", "pnl_pct"].mean() if n - wins > 0 else 0
    ev = bets["pnl_pct"].mean()
    total = bets["pnl_pct"].sum()
    pf = abs(bets.loc[bets["pnl_pct"] > 0, "pnl_pct"].sum() / bets.loc[bets["pnl_pct"] < 0, "pnl_pct"].sum()) if (bets["pnl_pct"] < 0).any() else 0

    n_days = (bets.iloc[-1]["exit_date"] - bets.iloc[0]["entry_date"]).days
    bpd = n / max(n_days, 1)

    return {
        "ticker": ticker, "n_bets": n, "win_rate": round(wr, 1),
        "avg_win_pct": round(avg_win, 3), "avg_loss_pct": round(avg_loss, 3),
        "ev_pct": round(ev, 3), "total_pnl_pct": round(total, 2),
        "profit_factor": round(pf, 2), "bets_per_day": round(bpd, 3),
    }


# ── Main Sweep ──

SETUPS = [
    ("RSI3_25_75", lambda df: sig_rsi_mr(df, 25, 75, 3)),
    ("RSI3_20_80", lambda df: sig_rsi_mr(df, 20, 80, 3)),
    ("RSI2_10_90", lambda df: sig_rsi_mr(df, 10, 90, 2)),
    ("IBS_15_85", lambda df: sig_ibs_mr(df, 0.15, 0.85)),
    ("IBS_10_90", lambda df: sig_ibs_mr(df, 0.10, 0.90)),
    ("Boll_2.0", lambda df: sig_boll_mr(df, 20, 2.0)),
    ("Boll_2.5", lambda df: sig_boll_mr(df, 20, 2.5)),
]

BARRIERS = [
    (1.5, 1.0, 5, "1.5:1/5d"),
    (2.0, 1.0, 5, "2:1/5d"),
    (1.0, 1.0, 3, "1:1/3d"),
]


def main():
    t0 = time.time()
    print("=" * 70)
    print("CASINO STOCKS — COMPREHENSIVE INDICATOR SWEEP")
    print("=" * 70)

    data = load_universe()

    all_results = []
    n_total = len(data) * len(SETUPS) * len(BARRIERS)
    done = 0

    for setup_name, sig_fn in SETUPS:
        for pt, sl, md, barrier_name in BARRIERS:
            combo_name = f"{setup_name}/{barrier_name}"
            combo_results = []

            for ticker, df in data.items():
                try:
                    signals = sig_fn(df)
                    bets = run_bets(df, signals, pt_atr=pt, sl_atr=sl, max_days=md)
                    if len(bets) >= 20:
                        stats = bet_stats(bets, ticker)
                        if stats:
                            stats["setup"] = setup_name
                            stats["barriers"] = barrier_name
                            combo_results.append(stats)
                except Exception:
                    pass
                done += 1

            if combo_results:
                profitable = [r for r in combo_results if r["ev_pct"] > 0]
                avg_ev = np.mean([r["ev_pct"] for r in combo_results])
                avg_wr = np.mean([r["win_rate"] for r in combo_results])
                n_prof = len(profitable)
                print(f"  {combo_name:>20s}: {len(combo_results):>3d} stocks, {n_prof:>3d} profitable ({n_prof/len(combo_results)*100:.0f}%),"
                      f" avg EV={avg_ev:>+.3f}%, avg WR={avg_wr:.1f}%")
                all_results.extend(combo_results)

    results_df = pd.DataFrame(all_results)
    if results_df.empty:
        print("No results!"); return

    # ── Report ──
    print(f"\n{'='*70}")
    print(f"RESULTS: {len(results_df)} stock×setup combinations tested")
    print(f"{'='*70}")

    profitable = results_df[results_df["ev_pct"] > 0]
    print(f"\n  Profitable: {len(profitable)}/{len(results_df)} ({len(profitable)/len(results_df)*100:.0f}%)")

    # Best setups (avg across all stocks)
    print(f"\n  SETUP RANKING (avg across all stocks):")
    setup_avg = results_df.groupby(["setup", "barriers"]).agg(
        n_stocks=("ticker", "count"),
        pct_profitable=("ev_pct", lambda x: (x > 0).mean() * 100),
        avg_ev=("ev_pct", "mean"),
        avg_wr=("win_rate", "mean"),
        avg_pf=("profit_factor", "mean"),
        avg_total=("total_pnl_pct", "mean"),
    ).sort_values("avg_ev", ascending=False)

    print(f"  {'Setup':>20s}  {'Stocks':>6s}  {'%Prof':>6s}  {'AvgEV':>7s}  {'AvgWR':>6s}  {'AvgPF':>6s}  {'AvgTot':>8s}")
    for (setup, barriers), row in setup_avg.iterrows():
        print(f"  {setup+'/'+barriers:>20s}  {row['n_stocks']:>6.0f}  {row['pct_profitable']:>5.0f}%  {row['avg_ev']:>+6.3f}%  {row['avg_wr']:>5.1f}%  {row['avg_pf']:>6.2f}  {row['avg_total']:>+7.1f}%")

    # Top 20 individual stock×setup combos
    top20 = profitable.nlargest(20, "total_pnl_pct")
    print(f"\n  TOP 20 INDIVIDUAL STOCK×SETUP COMBINATIONS:")
    print(f"  {'Ticker':>6s}  {'Setup':>20s}  {'Bets':>5s}  {'WR':>5s}  {'EV':>7s}  {'PF':>5s}  {'Total':>8s}")
    for _, r in top20.iterrows():
        print(f"  {r['ticker']:>6s}  {r['setup']+'/'+r['barriers']:>20s}  {r['n_bets']:>5.0f}  {r['win_rate']:>4.1f}%  {r['ev_pct']:>+6.3f}%  {r['profit_factor']:>5.2f}  {r['total_pnl_pct']:>+7.1f}%")

    # Best stocks (avg across setups)
    print(f"\n  TOP 20 STOCKS (avg EV across all setups):")
    stock_avg = results_df.groupby("ticker").agg(
        avg_ev=("ev_pct", "mean"),
        pct_profitable=("ev_pct", lambda x: (x > 0).mean() * 100),
        avg_total=("total_pnl_pct", "mean"),
    ).sort_values("avg_ev", ascending=False)

    for ticker, row in stock_avg.head(20).iterrows():
        print(f"  {ticker:>6s}: avg EV={row['avg_ev']:>+.3f}%, {row['pct_profitable']:.0f}% profitable, avg total={row['avg_total']:>+.1f}%")

    # Save
    results_df.to_csv("casino-stocks/results/stock_sweep_results.csv", index=False)
    setup_avg.to_csv("casino-stocks/results/setup_ranking.csv")

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
