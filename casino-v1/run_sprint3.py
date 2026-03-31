#!/usr/bin/env python3
"""
Casino V1 — Sprint 3: Patterns, Composites, Time-of-Day

1. Candlestick patterns (engulfing, hammer, inside bar) with RSI/volume filters
2. Composite setups (RSI + Bollinger, ORB + VWAP alignment)
3. Time-of-day analysis on all winning setups
4. Day-of-week effects
"""
import sys
import time
sys.path.insert(0, ".")
sys.path.insert(0, "casino-v1")

import numpy as np
import pandas as pd
from pathlib import Path

from casino_src.indicators import (
    rsi, rsi_mean_reversion, bollinger_bands, keltner_channel,
    vwap_deviation_signal, ibs_signal, atr as compute_atr,
)
from casino_src.bet_engine import run_bets, compute_bet_stats

INSTRUMENTS = {
    "ES": {"multiplier": 50.0, "commission": 2.10},
    "NQ": {"multiplier": 20.0, "commission": 2.10},
    "CL": {"multiplier": 1000.0, "commission": 2.10},
}

PT_SL_CONFIGS = [(1.5, 1.0, "1.5:1"), (2.0, 1.0, "2:1")]
MAX_BARS = 60


def load_1min(symbol):
    cache = Path("data/cache")
    for f in sorted(cache.glob(f"{symbol}_1m_2018*")):
        df = pd.read_parquet(f)
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df = df.between_time("09:30", "15:59")
        return df
    return None


def resample(df, minutes):
    if minutes == 1: return df
    return df.resample(f"{minutes}min").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["close"])


def test_setup(name, df, signals, multiplier, commission, results):
    n_signals = (signals != 0).sum()
    if n_signals < 20: return
    for pt, sl, rr in PT_SL_CONFIGS:
        bets = run_bets(df, signals, pt_atr_mult=pt, sl_atr_mult=sl,
                         max_bars=MAX_BARS, atr_period=14)
        if len(bets) < 20: continue
        stats = compute_bet_stats(bets, multiplier=multiplier, commission_rt=commission)
        stats["setup"] = name
        stats["pt_sl"] = rr
        results.append(stats)


# ── Pattern Detection ──

def detect_engulfing(df):
    """Bullish/bearish engulfing patterns."""
    signal = pd.Series(0, index=df.index)
    o, c, po, pc = df["open"], df["close"], df["open"].shift(1), df["close"].shift(1)
    # Bullish: prev was red, current green body engulfs prev
    bullish = (pc < po) & (c > o) & (o <= pc) & (c >= po)
    # Bearish: prev was green, current red body engulfs prev
    bearish = (pc > po) & (c < o) & (o >= pc) & (c <= po)
    signal[bullish] = 1
    signal[bearish] = -1
    return signal


def detect_hammer(df, body_ratio=0.3, wick_ratio=2.0):
    """Hammer (bullish) and shooting star (bearish) patterns."""
    signal = pd.Series(0, index=df.index)
    body = (df["close"] - df["open"]).abs()
    rng = df["high"] - df["low"]
    rng = rng.replace(0, np.nan)

    lower_wick = pd.concat([df["open"], df["close"]], axis=1).min(axis=1) - df["low"]
    upper_wick = df["high"] - pd.concat([df["open"], df["close"]], axis=1).max(axis=1)

    small_body = body / rng < body_ratio
    # Hammer: long lower wick, small upper wick
    hammer = small_body & (lower_wick / rng > 0.6) & (upper_wick / rng < 0.15)
    # Shooting star: long upper wick, small lower wick
    star = small_body & (upper_wick / rng > 0.6) & (lower_wick / rng < 0.15)

    signal[hammer] = 1
    signal[star] = -1
    return signal


def detect_inside_bar(df):
    """Inside bar: current bar's range is within previous bar's range."""
    signal = pd.Series(0, index=df.index)
    inside = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    # Direction from the close relative to midpoint of the inside bar
    mid = (df["high"] + df["low"]) / 2
    prev_mid = (df["high"].shift(1) + df["low"].shift(1)) / 2
    signal[inside & (df["close"] > prev_mid)] = 1  # Closing in upper half → bullish breakout
    signal[inside & (df["close"] < prev_mid)] = -1
    return signal


# ── Composite Indicators ──

def rsi_bollinger_composite(df, rsi_period=3, rsi_thresh=25, boll_period=20, boll_std=2.0):
    """RSI oversold + price at lower Bollinger = high-conviction mean reversion."""
    r = rsi(df["close"], rsi_period)
    _, _, lower = bollinger_bands(df, boll_period, boll_std)
    _, upper, _ = bollinger_bands(df, boll_period, boll_std)

    signal = pd.Series(0, index=df.index)
    signal[(r < rsi_thresh) & (df["close"] < lower)] = 1      # Oversold + below lower BB
    signal[(r > (100 - rsi_thresh)) & (df["close"] > upper)] = -1  # Overbought + above upper BB
    return signal


def rsi_keltner_composite(df, rsi_period=3, rsi_thresh=25, kelt_period=20, kelt_mult=2.0):
    """RSI + Keltner channel composite."""
    r = rsi(df["close"], rsi_period)
    _, upper, lower = keltner_channel(df, kelt_period, kelt_mult)

    signal = pd.Series(0, index=df.index)
    signal[(r < rsi_thresh) & (df["close"] < lower)] = 1
    signal[(r > (100 - rsi_thresh)) & (df["close"] > upper)] = -1
    return signal


def momentum_thrust(df, roc_period=5, threshold=2.0):
    """Momentum thrust: ROC exceeds N std devs → continuation or reversal."""
    roc = df["close"].pct_change(roc_period)
    roc_std = roc.rolling(50).std()
    z = roc / roc_std.replace(0, np.nan)

    signal = pd.Series(0, index=df.index)
    # Mean reversion after extreme thrust
    signal[z < -threshold] = 1   # Extreme selloff → buy
    signal[z > threshold] = -1   # Extreme rally → sell
    return signal


def main():
    t0 = time.time()
    print("=" * 70)
    print("CASINO V1 — SPRINT 3: PATTERNS + COMPOSITES + TIME ANALYSIS")
    print("=" * 70)

    all_results = []

    for sym, cfg in INSTRUMENTS.items():
        print(f"\n{'='*70}\n  {sym}\n{'='*70}")

        df_1m = load_1min(sym)
        if df_1m is None: print("  No data"); continue
        print(f"  {len(df_1m):,} 1-min bars")
        mult, comm = cfg["multiplier"], cfg["commission"]

        # ── 1. Candlestick Patterns ──
        print(f"\n  Candlestick patterns:")
        for tf_mins in [15, 30, 60]:
            df_tf = resample(df_1m, tf_mins)
            for name_fn, fn in [
                ("Engulf", detect_engulfing),
                ("Hammer", detect_hammer),
                ("Inside", detect_inside_bar),
            ]:
                # Raw pattern
                signals = fn(df_tf)
                setup = f"{sym}/{name_fn}/{tf_mins}min"
                test_setup(setup, df_tf, signals, mult, comm, all_results)

                # Pattern + RSI filter (only trade when RSI confirms)
                r = rsi(df_tf["close"], 3)
                filtered = signals.copy()
                # For longs: only when RSI < 40. For shorts: only when RSI > 60.
                filtered[(signals == 1) & (r > 40)] = 0
                filtered[(signals == -1) & (r < 60)] = 0
                setup_f = f"{sym}/{name_fn}+RSI/{tf_mins}min"
                test_setup(setup_f, df_tf, filtered, mult, comm, all_results)

            n = len([r for r in all_results if f"{sym}/" in r["setup"] and f"/{tf_mins}min" in r["setup"] and any(p in r["setup"] for p in ["Engulf","Hammer","Inside"])])
            print(f"    {tf_mins}min: {n} configs")

        # ── 2. Composite Indicators ──
        print(f"\n  Composites:")
        for tf_mins in [15, 30, 60]:
            df_tf = resample(df_1m, tf_mins)

            # RSI + Bollinger
            for rsi_p in [2, 3, 5]:
                for rsi_t in [20, 25, 30]:
                    for boll_s in [1.5, 2.0, 2.5]:
                        signals = rsi_bollinger_composite(df_tf, rsi_p, rsi_t, 20, boll_s)
                        name = f"{sym}/RSI({rsi_p})+BB({boll_s})/{tf_mins}min"
                        test_setup(name, df_tf, signals, mult, comm, all_results)

            # RSI + Keltner
            for rsi_p in [2, 3]:
                for rsi_t in [20, 25, 30]:
                    for kelt_m in [1.5, 2.0, 2.5]:
                        signals = rsi_keltner_composite(df_tf, rsi_p, rsi_t, 20, kelt_m)
                        name = f"{sym}/RSI({rsi_p})+Kelt({kelt_m})/{tf_mins}min"
                        test_setup(name, df_tf, signals, mult, comm, all_results)

            # Momentum thrust reversal
            for roc_p in [3, 5, 10]:
                for thresh in [1.5, 2.0, 2.5, 3.0]:
                    signals = momentum_thrust(df_tf, roc_p, thresh)
                    name = f"{sym}/MomThrust({roc_p},{thresh})/{tf_mins}min"
                    test_setup(name, df_tf, signals, mult, comm, all_results)

            n_comp = len([r for r in all_results if f"{sym}/" in r["setup"] and ("RSI(" in r["setup"] and ("BB" in r["setup"] or "Kelt" in r["setup"])) or "MomThrust" in r["setup"]])
            print(f"    {tf_mins}min composites: tested")

        sym_results = [r for r in all_results if r["setup"].startswith(f"{sym}/")]
        sym_prof = [r for r in sym_results if r["ev_per_bet"] > 0]
        print(f"\n  {sym} total: {len(sym_results)} configs, {len(sym_prof)} profitable")

    # ── Report ──
    results_df = pd.DataFrame(all_results)
    if results_df.empty: print("No results!"); return

    profitable = results_df[results_df["ev_per_bet"] > 0].sort_values("ev_per_bet", ascending=False)
    print(f"\n{'='*70}")
    print(f"TOTAL: {len(results_df)} configs, {len(profitable)} profitable ({len(profitable)/len(results_df)*100:.0f}%)")
    print(f"{'='*70}")

    print(f"\nTOP 20 BY EV:")
    print(f"  {'Setup':>45s} {'R:R':>5s} {'WR':>5s} {'PF':>5s} {'EV':>7s} {'B/d':>5s} {'Total$':>10s}")
    print(f"  {'-'*45} {'-'*5} {'-'*5} {'-'*5} {'-'*7} {'-'*5} {'-'*10}")
    for _, r in profitable.head(20).iterrows():
        print(f"  {r['setup']:>45s} {r['pt_sl']:>5s} {r['win_rate']:>4.1f}% {r['profit_factor']:>5.2f} {r['ev_per_bet']:>7.0f} {r['bets_per_day']:>5.2f} ${r['total_pnl']:>9,.0f}")

    # By type
    print(f"\nBY SETUP TYPE (profitable only):")
    types = {"Pattern": ["Engulf","Hammer","Inside"], "Pattern+RSI": ["+RSI"],
             "RSI+BB": ["RSI(", "+BB"], "RSI+Kelt": ["RSI(", "+Kelt("],
             "MomThrust": ["MomThrust"]}
    for tname, keywords in types.items():
        subset = profitable[profitable["setup"].apply(lambda x: all(k in x for k in keywords))]
        if len(subset) > 0:
            print(f"  {tname:>12s}: {len(subset):>3d} profitable, avg EV=${subset['ev_per_bet'].mean():.0f},"
                  f" avg WR={subset['win_rate'].mean():.1f}%, avg {subset['bets_per_day'].mean():.2f}/day")
        else:
            print(f"  {tname:>12s}: 0 profitable")

    # Save
    results_df.to_csv("casino-v1/data/sprint3_all_results.csv", index=False)
    profitable.to_csv("casino-v1/data/sprint3_profitable.csv", index=False)

    # ── Time of Day Analysis on best setups from Sprint 1+2 ──
    print(f"\n{'='*70}")
    print("TIME-OF-DAY ANALYSIS (NQ RSI(3) 30/70 on 60min — best Sprint 1 setup)")
    print(f"{'='*70}")

    df_nq = load_1min("NQ")
    df_60 = resample(df_nq, 60)
    signals = rsi_mean_reversion(df_60, rsi_period=3, oversold=30, overbought=70)
    bets = run_bets(df_60, signals, pt_atr_mult=2.0, sl_atr_mult=1.0, max_bars=60, atr_period=14)

    if not bets.empty:
        bets["hour"] = pd.to_datetime(bets["entry_time"]).dt.hour
        print(f"\n  {'Hour':>6s}  {'Bets':>5s}  {'WinR':>5s}  {'AvgPnL':>8s}  {'TotalPnL':>10s}")
        for hour in sorted(bets["hour"].unique()):
            hb = bets[bets["hour"] == hour]
            wr = (hb["result"] == "win").mean() * 100
            avg = hb["pnl_points"].mean() * 20  # NQ multiplier
            total = hb["pnl_points"].sum() * 20
            print(f"  {hour:>5d}h  {len(hb):>5d}  {wr:>4.1f}%  ${avg:>7.0f}  ${total:>9,.0f}")

    # Day of week
    if not bets.empty:
        bets["dow"] = pd.to_datetime(bets["entry_time"]).dt.day_name()
        print(f"\n  {'Day':>10s}  {'Bets':>5s}  {'WinR':>5s}  {'TotalPnL':>10s}")
        for dow in ["Monday","Tuesday","Wednesday","Thursday","Friday"]:
            db = bets[bets["dow"] == dow]
            if len(db) > 0:
                wr = (db["result"] == "win").mean() * 100
                total = db["pnl_points"].sum() * 20
                print(f"  {dow:>10s}  {len(db):>5d}  {wr:>4.1f}%  ${total:>9,.0f}")

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
