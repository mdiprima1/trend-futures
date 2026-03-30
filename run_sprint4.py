#!/usr/bin/env python3
"""
Sprint 4: Multi-Scale Signal Blending & Regime Detection
"""
import sys
import time
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from src.data import fetch_futures_1m, build_daily_bars
from src.signals import SIGNALS
from src.regimes import BLEND_SIGNALS
from src.portfolio import portfolio_backtest

INSTRUMENTS = ["ES", "NQ", "ZN", "GC", "CL", "6E"]
INITIAL_CAPITAL = 500_000

# Sprint 2 best config
PORTFOLIO_CONFIG = {
    "vol_method": "atr",
    "vol_window": 20,
    "allocation_method": "equal_weight",
    "portfolio_vol_target": 0.12,
    "rebalance_freq": "weekly",
}

DATE_RANGES = [("2018-01-01", "2025-12-31"), ("2010-06-07", "2025-12-31")]


def load_data():
    print("=" * 60)
    print("LOADING DATA")
    print("=" * 60)
    daily_data = {}
    for sym in INSTRUMENTS:
        for start, end in DATE_RANGES:
            try:
                m = fetch_futures_1m(sym, start, end)
                m = m[m.index >= pd.Timestamp("2018-01-01", tz="US/Eastern")]
                daily_data[sym] = build_daily_bars(m)
                print(f"  {sym}: {len(daily_data[sym])} daily bars")
                break
            except Exception:
                continue
    return daily_data


def run_single_signal_baseline(daily_data):
    """Run Sprint 1 winners as baseline for comparison."""
    print("\n" + "=" * 60)
    print("BASELINE: Sprint 1 Individual Signals")
    print("=" * 60)

    baselines = {}
    for sig_id in ["TS-04", "MA-04", "MA-03", "MA-02", "SE-02"]:
        sig_fn = SIGNALS[sig_id]["fn"]
        signals = {sym: sig_fn(daily) for sym, daily in daily_data.items()}
        bt = portfolio_backtest(
            signals=signals, daily_bars=daily_data,
            initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG,
        )
        baselines[sig_id] = bt["stats"]
        s = bt["stats"]
        print(f"  {SIGNALS[sig_id]['name']:>15s}  Sharpe={s['sharpe']:.3f}  CAGR={s['cagr_pct']:.1f}%  MaxDD={s['max_dd_pct']:.1f}%")

    return baselines


def run_blend_sweep(daily_data):
    """Run all blend and regime-filtered signals."""
    print("\n" + "=" * 60)
    print("SPRINT 4: BLEND & REGIME SWEEP")
    print("=" * 60)

    results = []

    for sig_id, sig_info in BLEND_SIGNALS.items():
        sig_fn = sig_info["fn"]
        signals = {}

        for sym, daily in daily_data.items():
            try:
                signals[sym] = sig_fn(daily)
            except Exception as e:
                print(f"  Warning: {sig_id}/{sym}: {e}")
                signals[sym] = pd.Series(0.0, index=daily.index)

        try:
            bt = portfolio_backtest(
                signals=signals, daily_bars=daily_data,
                initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG,
            )
            stats = bt["stats"].copy()
            stats["signal_id"] = sig_id
            stats["signal_name"] = sig_info["name"]
            stats["signal_type"] = sig_info["type"]

            # Compute time-in-market
            common_idx = list(signals.values())[0].index
            in_market_pcts = []
            for sym in INSTRUMENTS:
                sig = signals[sym].reindex(common_idx).fillna(0)
                in_market_pcts.append((sig != 0).mean() * 100)
            stats["avg_time_in_market"] = round(np.mean(in_market_pcts), 1)

            results.append(stats)
        except Exception as e:
            print(f"  ERROR {sig_id}: {e}")

    return pd.DataFrame(results)


def main():
    t0 = time.time()
    daily_data = load_data()

    # Baselines
    baselines = run_single_signal_baseline(daily_data)

    # Sprint 4 sweep
    results_df = run_blend_sweep(daily_data)

    if results_df.empty:
        print("No results!")
        return

    # ── Report ──
    print("\n" + "=" * 60)
    print("SPRINT 4 RESULTS")
    print("=" * 60)

    # Sort by Sharpe
    results_df = results_df.sort_values("sharpe", ascending=False)

    # Blends vs baselines
    print("\n── All Signals Ranked by Sharpe ──")
    print(f"  {'Signal':>18s}  {'Type':>7s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}  {'Calmar':>7s}  {'InMkt':>6s}")
    print(f"  {'-'*18}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*6}")

    for _, row in results_df.iterrows():
        print(f"  {row['signal_name']:>18s}  {row['signal_type']:>7s}  {row['sharpe']:>7.3f}  {row['cagr_pct']:>6.1f}%  {row['max_dd_pct']:>6.1f}%  {row['calmar']:>7.3f}  {row['avg_time_in_market']:>5.0f}%")

    # Best baseline for comparison
    best_base_sharpe = max(v["sharpe"] for v in baselines.values())
    best_base_id = max(baselines, key=lambda k: baselines[k]["sharpe"])
    print(f"\n  Best Sprint 1 baseline: {SIGNALS[best_base_id]['name']} (Sharpe={best_base_sharpe:.3f})")

    # Type comparison
    print("\n── Type Comparison ──")
    type_summary = results_df.groupby("signal_type").agg(
        sharpe=("sharpe", "mean"),
        cagr=("cagr_pct", "mean"),
        max_dd=("max_dd_pct", "mean"),
        calmar=("calmar", "mean"),
    )
    for typ, row in type_summary.iterrows():
        print(f"  {typ:>7s}: Sharpe={row['sharpe']:.3f}  CAGR={row['cagr']:.1f}%  MaxDD={row['max_dd']:.1f}%  Calmar={row['calmar']:.3f}")

    # Barbell hypothesis check
    print("\n── Etienne (2025) Barbell Hypothesis ──")
    barbell = results_df[results_df["signal_id"] == "BL-BAR"].iloc[0] if "BL-BAR" in results_df["signal_id"].values else None
    all_blend = results_df[results_df["signal_id"] == "BL-ALL"].iloc[0] if "BL-ALL" in results_df["signal_id"].values else None
    if barbell is not None and all_blend is not None:
        print(f"  Barbell (S+L):   Sharpe={barbell['sharpe']:.3f}  CAGR={barbell['cagr_pct']:.1f}%")
        print(f"  Equal (all 5):   Sharpe={all_blend['sharpe']:.3f}  CAGR={all_blend['cagr_pct']:.1f}%")
        if barbell["sharpe"] >= all_blend["sharpe"]:
            print("  → CONFIRMED: Barbell >= Equal blend. Medium-term signals are redundant.")
        else:
            print(f"  → NOT confirmed: Equal blend outperforms barbell by {all_blend['sharpe'] - barbell['sharpe']:.3f}")

    # Regime filter impact
    print("\n── Regime Filter Impact ──")
    base_barbell = results_df[results_df["signal_id"] == "BL-BAR"]
    if not base_barbell.empty:
        base_sharpe = base_barbell.iloc[0]["sharpe"]
        regime_signals = results_df[results_df["signal_type"] == "regime"]
        for _, row in regime_signals.iterrows():
            delta = row["sharpe"] - base_sharpe
            better = "+" if delta > 0 else ""
            print(f"  {row['signal_name']:>18s}: Sharpe={row['sharpe']:.3f} ({better}{delta:.3f} vs barbell)  InMarket={row['avg_time_in_market']:.0f}%")

    # Top pick
    best = results_df.iloc[0]
    print(f"\n── Sprint 4 Winner ──")
    print(f"  {best['signal_name']}: Sharpe={best['sharpe']:.3f}, CAGR={best['cagr_pct']:.1f}%, MaxDD={best['max_dd_pct']:.1f}%, Calmar={best['calmar']:.3f}")

    # Save
    results_df.to_csv("data/sprint4_results.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
