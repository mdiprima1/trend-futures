#!/usr/bin/env python3
"""
Casino V1 — Sprint 2: Breakout, VWAP, Keltner, Bollinger, IBS

Test ORB, VWAP deviation, Keltner MR/breakout, Bollinger MR, IBS
across ES, NQ, CL on multiple timeframes.
"""
import sys
import time
sys.path.insert(0, ".")
sys.path.insert(0, "casino-v1")

import numpy as np
import pandas as pd
from pathlib import Path

from casino_src.indicators import (
    opening_range_breakout, vwap_deviation_signal,
    keltner_mean_reversion, keltner_breakout,
    bollinger_mean_reversion, ibs_signal,
)
from casino_src.bet_engine import run_bets, compute_bet_stats

INSTRUMENTS = {
    "ES": {"multiplier": 50.0, "commission": 2.10},
    "NQ": {"multiplier": 20.0, "commission": 2.10},
    "CL": {"multiplier": 1000.0, "commission": 2.10},
}

PT_SL_CONFIGS = [
    (1.0, 1.0, "1:1"),
    (1.5, 1.0, "1.5:1"),
    (2.0, 1.0, "2:1"),
]
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
    if minutes == 1:
        return df
    return df.resample(f"{minutes}min", label='right').agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["close"])


def test_setup(name, df, signals, multiplier, commission, results):
    """Test one setup across all PT/SL configs."""
    n_signals = (signals != 0).sum()
    if n_signals < 20:
        return

    for pt, sl, rr in PT_SL_CONFIGS:
        bets = run_bets(df, signals, pt_atr_mult=pt, sl_atr_mult=sl,
                         max_bars=MAX_BARS, atr_period=14)
        if len(bets) < 20:
            continue

        stats = compute_bet_stats(bets, multiplier=multiplier, commission_rt=commission)
        stats["setup"] = name
        stats["pt_sl"] = rr
        results.append(stats)


def main():
    t0 = time.time()

    print("=" * 70)
    print("CASINO V1 — SPRINT 2: BREAKOUT / VWAP / KELTNER / BOLL / IBS")
    print("=" * 70)

    all_results = []

    for sym, cfg in INSTRUMENTS.items():
        print(f"\n{'='*70}")
        print(f"  {sym}")
        print(f"{'='*70}")

        df_1m = load_1min(sym)
        if df_1m is None:
            print(f"  No data"); continue
        print(f"  {len(df_1m):,} 1-min bars")

        mult = cfg["multiplier"]
        comm = cfg["commission"]

        # ── 1. Opening Range Breakout (on 1-min data) ──
        print(f"\n  ORB setups:")
        for range_min in [5, 15, 30, 60]:
            try:
                signals = opening_range_breakout(df_1m, range_minutes=range_min)
                name = f"{sym}/ORB-{range_min}min"
                test_setup(name, df_1m, signals, mult, comm, all_results)
                n = (signals != 0).sum()
                print(f"    ORB-{range_min}min: {n} signals")
            except Exception as e:
                print(f"    ORB-{range_min}min: ERROR {e}")

        # ── 2. VWAP Deviation (on various timeframes) ──
        print(f"\n  VWAP deviation setups:")
        for tf_mins in [5, 15, 30]:
            df_tf = resample(df_1m, tf_mins)
            for std_thresh in [1.5, 2.0, 2.5, 3.0]:
                try:
                    signals = vwap_deviation_signal(df_tf, std_threshold=std_thresh)
                    name = f"{sym}/VWAP-{std_thresh}σ/{tf_mins}min"
                    test_setup(name, df_tf, signals, mult, comm, all_results)
                except Exception as e:
                    pass
            n_setups = len([r for r in all_results if r["setup"].startswith(f"{sym}/VWAP") and "/{tf_mins}min" in r["setup"]])
            print(f"    {tf_mins}min: {n_setups} configs tested")

        # ── 3. Keltner Channel (MR + Breakout) ──
        print(f"\n  Keltner setups:")
        for tf_mins in [15, 30, 60]:
            df_tf = resample(df_1m, tf_mins)
            for period in [14, 20, 30]:
                for atr_mult in [1.5, 2.0, 2.5]:
                    # Mean reversion
                    try:
                        signals = keltner_mean_reversion(df_tf, period, atr_mult)
                        name = f"{sym}/Kelt-MR({period},{atr_mult})/{tf_mins}min"
                        test_setup(name, df_tf, signals, mult, comm, all_results)
                    except:
                        pass
                    # Breakout
                    try:
                        signals = keltner_breakout(df_tf, period, atr_mult)
                        name = f"{sym}/Kelt-BO({period},{atr_mult})/{tf_mins}min"
                        test_setup(name, df_tf, signals, mult, comm, all_results)
                    except:
                        pass
            n_kelt = len([r for r in all_results if f"{sym}/Kelt" in r["setup"] and f"/{tf_mins}min" in r["setup"]])
            print(f"    {tf_mins}min: {n_kelt} configs")

        # ── 4. Bollinger Mean Reversion ──
        print(f"\n  Bollinger setups:")
        for tf_mins in [15, 30, 60]:
            df_tf = resample(df_1m, tf_mins)
            for period in [14, 20]:
                for std_m in [1.5, 2.0, 2.5, 3.0]:
                    try:
                        signals = bollinger_mean_reversion(df_tf, period, std_m)
                        name = f"{sym}/Boll-MR({period},{std_m})/{tf_mins}min"
                        test_setup(name, df_tf, signals, mult, comm, all_results)
                    except:
                        pass
            n_boll = len([r for r in all_results if f"{sym}/Boll" in r["setup"]])
            print(f"    Total Bollinger: {n_boll}")

        # ── 5. IBS (Internal Bar Strength) ──
        print(f"\n  IBS setups:")
        for tf_mins in [15, 30, 60]:
            df_tf = resample(df_1m, tf_mins)
            for low_t, high_t in [(0.1, 0.9), (0.15, 0.85), (0.2, 0.8), (0.25, 0.75)]:
                try:
                    signals = ibs_signal(df_tf, low_thresh=low_t, high_thresh=high_t)
                    name = f"{sym}/IBS({low_t}/{high_t})/{tf_mins}min"
                    test_setup(name, df_tf, signals, mult, comm, all_results)
                except:
                    pass
            n_ibs = len([r for r in all_results if f"{sym}/IBS" in r["setup"]])
            print(f"    Total IBS: {n_ibs}")

        # Summary
        sym_results = [r for r in all_results if r["setup"].startswith(f"{sym}/")]
        sym_profitable = [r for r in sym_results if r["ev_per_bet"] > 0]
        print(f"\n  {sym} total: {len(sym_results)} configs, {len(sym_profitable)} profitable")

    # ── Report ──
    results_df = pd.DataFrame(all_results)
    if results_df.empty:
        print("\nNo results!"); return

    profitable = results_df[results_df["ev_per_bet"] > 0].sort_values("ev_per_bet", ascending=False)
    print(f"\n{'='*70}")
    print(f"TOTAL: {len(results_df)} configs tested, {len(profitable)} profitable ({len(profitable)/len(results_df)*100:.0f}%)")
    print(f"{'='*70}")

    print(f"\nTOP 20 BY EXPECTED VALUE PER BET:")
    print(f"  {'Setup':>40s}  {'R:R':>5s}  {'WR':>5s} {'PF':>5s}  {'EV':>8s} {'B/d':>5s}  {'Total$':>10s}")
    print(f"  {'-'*40}  {'-'*5}  {'-'*5} {'-'*5}  {'-'*8} {'-'*5}  {'-'*10}")
    for _, r in profitable.head(20).iterrows():
        print(f"  {r['setup']:>40s}  {r['pt_sl']:>5s}  {r['win_rate']:>4.1f}% {r['profit_factor']:>5.2f}"
              f"  {r['ev_per_bet']:>8.0f} {r['bets_per_day']:>5.2f}  ${r['total_pnl']:>9,.0f}")

    # By indicator type
    print(f"\n{'='*70}")
    print("BY INDICATOR TYPE (profitable setups only):")
    print(f"{'='*70}")
    for indicator in ["ORB", "VWAP", "Kelt-MR", "Kelt-BO", "Boll-MR", "IBS"]:
        subset = profitable[profitable["setup"].str.contains(indicator)]
        if len(subset) > 0:
            print(f"  {indicator:>8s}: {len(subset):>3d} profitable, avg EV=${subset['ev_per_bet'].mean():.0f},"
                  f" avg WR={subset['win_rate'].mean():.1f}%, avg {subset['bets_per_day'].mean():.2f} bets/day")
        else:
            print(f"  {indicator:>8s}: 0 profitable")

    # Best per indicator per instrument
    print(f"\n{'='*70}")
    print("BEST SETUP PER INDICATOR × INSTRUMENT:")
    print(f"{'='*70}")
    for indicator in ["ORB", "VWAP", "Kelt-MR", "Kelt-BO", "Boll-MR", "IBS"]:
        for sym in INSTRUMENTS:
            subset = profitable[(profitable["setup"].str.contains(indicator)) & (profitable["setup"].str.startswith(f"{sym}/"))]
            if len(subset) > 0:
                best = subset.iloc[0]
                print(f"  {best['setup']:>40s} [{best['pt_sl']}] WR={best['win_rate']:.1f}% PF={best['profit_factor']:.2f}"
                      f" EV=${best['ev_per_bet']:.0f} {best['bets_per_day']:.2f}/day Total=${best['total_pnl']:,.0f}")

    # Save
    results_df.to_csv("casino-v1/data/sprint2_all_results.csv", index=False)
    profitable.to_csv("casino-v1/data/sprint2_profitable.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
