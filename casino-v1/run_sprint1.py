#!/usr/bin/env python3
"""
Casino V1 — Sprint 1: RSI Mean Reversion Sweep

Test RSI(2,3,5) with various thresholds on multiple timeframes
across ES, NQ, CL. Triple barrier exits with ATR-based targets.
"""
import sys
import time
sys.path.insert(0, ".")
sys.path.insert(0, "casino-v1")

import numpy as np
import pandas as pd
from pathlib import Path

from casino_src.indicators import rsi_mean_reversion, atr
from casino_src.bet_engine import run_bets, compute_bet_stats
from src.config import CONTRACT_MULTIPLIERS, COMMISSIONS


# ── Configuration ──
INSTRUMENTS = {
    "ES": {"multiplier": 50.0, "commission": 2.10},
    "NQ": {"multiplier": 20.0, "commission": 2.10},
    "CL": {"multiplier": 1000.0, "commission": 2.10},
}

# Parameter grid
RSI_PERIODS = [2, 3, 5]
THRESHOLDS = [
    (5, 95), (10, 90), (15, 85), (20, 80), (25, 75), (30, 70),
]
TIMEFRAMES = {
    "5min": 5,
    "15min": 15,
    "30min": 30,
    "60min": 60,
}
PT_SL_CONFIGS = [
    (1.0, 1.0, "1:1"),
    (1.5, 1.0, "1.5:1"),
    (2.0, 1.0, "2:1"),
    (1.0, 0.5, "1:0.5"),
]
MAX_BARS = 60  # Max holding in resampled bars


def load_1min_data(symbol):
    """Load 1-minute data from Databento cache."""
    cache = Path("data/cache")
    for f in sorted(cache.glob(f"{symbol}_1m_2018*")):
        df = pd.read_parquet(f)
        # Filter to RTH
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df = df.between_time("09:30", "15:59")
        return df
    return None


def resample_bars(df, minutes):
    """Resample 1-min bars to N-minute bars."""
    if minutes == 1:
        return df
    return df.resample(f"{minutes}min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["close"])


def main():
    t0 = time.time()

    print("=" * 70)
    print("CASINO V1 — SPRINT 1: RSI MEAN REVERSION SWEEP")
    print("=" * 70)

    all_results = []

    for sym, cfg in INSTRUMENTS.items():
        print(f"\n{'='*70}")
        print(f"  {sym}")
        print(f"{'='*70}")

        df_1m = load_1min_data(sym)
        if df_1m is None:
            print(f"  No data for {sym}")
            continue
        print(f"  Loaded {len(df_1m):,} 1-min bars")

        for tf_name, tf_mins in TIMEFRAMES.items():
            df = resample_bars(df_1m, tf_mins)
            print(f"\n  {tf_name} ({len(df):,} bars):")

            for rsi_p in RSI_PERIODS:
                for oversold, overbought in THRESHOLDS:
                    # Generate signals
                    signals = rsi_mean_reversion(df, rsi_period=rsi_p,
                                                  oversold=oversold, overbought=overbought)
                    n_signals = (signals != 0).sum()
                    if n_signals < 30:
                        continue

                    for pt_mult, sl_mult, rr_name in PT_SL_CONFIGS:
                        bets = run_bets(df, signals,
                                         pt_atr_mult=pt_mult, sl_atr_mult=sl_mult,
                                         max_bars=MAX_BARS, atr_period=14)

                        if len(bets) < 30:
                            continue

                        stats = compute_bet_stats(bets, multiplier=cfg["multiplier"],
                                                   commission_rt=cfg["commission"])

                        stats["symbol"] = sym
                        stats["timeframe"] = tf_name
                        stats["rsi_period"] = rsi_p
                        stats["oversold"] = oversold
                        stats["overbought"] = overbought
                        stats["pt_sl"] = rr_name
                        stats["pt_mult"] = pt_mult
                        stats["sl_mult"] = sl_mult

                        all_results.append(stats)

            # Progress
            n_profitable = len([r for r in all_results if r["symbol"] == sym and r["ev_per_bet"] > 0])
            print(f"    Tested so far: {len([r for r in all_results if r['symbol']==sym])} configs, {n_profitable} profitable")

    results_df = pd.DataFrame(all_results)

    if results_df.empty:
        print("\nNo results!")
        return

    # ── Report ──
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    # Filter to profitable setups
    profitable = results_df[results_df["ev_per_bet"] > 0].sort_values("ev_per_bet", ascending=False)
    print(f"\nTotal configs tested: {len(results_df)}")
    print(f"Profitable configs: {len(profitable)} ({len(profitable)/len(results_df)*100:.0f}%)")

    # Top 20 by EV
    print(f"\n{'='*70}")
    print("TOP 20 SETUPS BY EXPECTED VALUE PER BET")
    print(f"{'='*70}")
    print(f"  {'Sym':>3s} {'TF':>5s} {'RSI':>3s} {'OS/OB':>6s} {'R:R':>5s}  {'WinR':>5s} {'PF':>5s}  {'AvgW':>8s} {'AvgL':>8s}  {'EV':>8s} {'Bets/d':>6s} {'Total$':>10s}")
    print(f"  {'-'*3} {'-'*5} {'-'*3} {'-'*6} {'-'*5}  {'-'*5} {'-'*5}  {'-'*8} {'-'*8}  {'-'*8} {'-'*6} {'-'*10}")

    for _, r in profitable.head(20).iterrows():
        print(f"  {r['symbol']:>3s} {r['timeframe']:>5s} {r['rsi_period']:>3.0f} {r['oversold']:>2.0f}/{r['overbought']:<2.0f} {r['pt_sl']:>5s}"
              f"  {r['win_rate']:>4.1f}% {r['profit_factor']:>5.2f}"
              f"  {r['avg_win']:>8.0f} {r['avg_loss']:>8.0f}"
              f"  {r['ev_per_bet']:>8.0f} {r['bets_per_day']:>6.2f} ${r['total_pnl']:>9,.0f}")

    # Top by win rate (>60%, enough bets)
    high_wr = results_df[(results_df["win_rate"] > 60) & (results_df["n_bets"] > 100)].sort_values("win_rate", ascending=False)
    print(f"\n{'='*70}")
    print("TOP 10 BY WIN RATE (>60%, >100 bets)")
    print(f"{'='*70}")
    for _, r in high_wr.head(10).iterrows():
        print(f"  {r['symbol']:>3s} {r['timeframe']:>5s} RSI({r['rsi_period']:.0f}) {r['oversold']:.0f}/{r['overbought']:.0f} {r['pt_sl']:>5s}"
              f"  WR={r['win_rate']:.1f}% PF={r['profit_factor']:.2f} EV=${r['ev_per_bet']:.0f}"
              f"  Bets={r['n_bets']:.0f} ({r['bets_per_day']:.2f}/day)")

    # Best per instrument
    print(f"\n{'='*70}")
    print("BEST SETUP PER INSTRUMENT (by EV)")
    print(f"{'='*70}")
    for sym in INSTRUMENTS:
        sym_data = profitable[profitable["symbol"] == sym]
        if len(sym_data) > 0:
            best = sym_data.iloc[0]
            print(f"  {sym}: RSI({best['rsi_period']:.0f}) {best['oversold']:.0f}/{best['overbought']:.0f} on {best['timeframe']}"
                  f" [{best['pt_sl']}] — WR={best['win_rate']:.1f}%, PF={best['profit_factor']:.2f},"
                  f" EV=${best['ev_per_bet']:.0f}/bet, {best['bets_per_day']:.2f}/day,"
                  f" Total=${best['total_pnl']:,.0f} over {best['n_years']:.1f}yr")
        else:
            print(f"  {sym}: No profitable setup found")

    # Timeframe comparison
    print(f"\n{'='*70}")
    print("TIMEFRAME COMPARISON (avg of profitable setups)")
    print(f"{'='*70}")
    if len(profitable) > 0:
        tf_summary = profitable.groupby("timeframe").agg(
            n_setups=("ev_per_bet", "count"),
            avg_wr=("win_rate", "mean"),
            avg_pf=("profit_factor", "mean"),
            avg_ev=("ev_per_bet", "mean"),
            avg_bets_day=("bets_per_day", "mean"),
        )
        for tf, row in tf_summary.iterrows():
            print(f"  {tf:>5s}: {row['n_setups']:.0f} setups, WR={row['avg_wr']:.1f}%, PF={row['avg_pf']:.2f}, EV=${row['avg_ev']:.0f}, {row['avg_bets_day']:.2f} bets/day")

    # Save
    results_df.to_csv("casino-v1/data/sprint1_rsi_results.csv", index=False)
    if len(profitable) > 0:
        profitable.to_csv("casino-v1/data/sprint1_profitable_setups.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")


if __name__ == "__main__":
    # Fix import path for casino-v1/src
    import importlib
    import casino_src
    main()
