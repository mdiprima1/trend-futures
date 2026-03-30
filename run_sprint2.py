#!/usr/bin/env python3
"""
Sprint 2: Volatility Targeting & Position Sizing
Test 5 signals × allocation methods × vol targets.
"""
import sys
import time
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from src.data import fetch_futures_1m, build_daily_bars
from src.signals import SIGNALS
from src.portfolio import portfolio_backtest

# ── Configuration ─────────────────────────────────────────────────────

INSTRUMENTS = ["ES", "NQ", "ZN", "GC", "CL", "6E"]
START_DATE = "2018-01-01"
END_DATE = "2025-12-31"
INITIAL_CAPITAL = 500_000

# Sprint 1 winners
SELECTED_SIGNALS = ["TS-04", "MA-04", "MA-03", "MA-02", "SE-02"]

# Date ranges to try for loading cached data
DATE_RANGES = [
    ("2018-01-01", "2025-12-31"),
    ("2010-06-07", "2025-12-31"),
]


def load_data():
    """Load daily bars for all instruments."""
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


def generate_signals(daily_data):
    """Generate selected signals for all instruments."""
    print("\nGenerating signals...")
    all_signals = {}  # {signal_id: {symbol: signal_series}}

    for sig_id in SELECTED_SIGNALS:
        sig_fn = SIGNALS[sig_id]["fn"]
        all_signals[sig_id] = {}
        for sym, daily in daily_data.items():
            all_signals[sig_id][sym] = sig_fn(daily)

    return all_signals


def run_sweep(daily_data, all_signals):
    """Run the full Sprint 2 parameter sweep."""
    print("\n" + "=" * 60)
    print("SPRINT 2: POSITION SIZING SWEEP")
    print("=" * 60)

    results = []

    # ── Test 1: Vol estimation methods ──
    print("\n── Test 1: Vol Estimation Methods ──")
    for vol_method in ["atr", "ewma", "realized"]:
        for vol_window in [20, 40, 60]:
            for sig_id in SELECTED_SIGNALS:
                try:
                    bt = portfolio_backtest(
                        signals=all_signals[sig_id],
                        daily_bars=daily_data,
                        allocation_method="equal_weight",
                        vol_method=vol_method,
                        vol_window=vol_window,
                        portfolio_vol_target=0.12,
                        initial_capital=INITIAL_CAPITAL,
                    )
                    row = bt["stats"].copy()
                    row["signal_id"] = sig_id
                    row["signal_name"] = SIGNALS[sig_id]["name"]
                    row["test"] = "vol_estimation"
                    results.append(row)
                except Exception as e:
                    print(f"    ERROR {sig_id}/{vol_method}/{vol_window}: {e}")

    # Print best vol method
    vol_df = pd.DataFrame([r for r in results if r["test"] == "vol_estimation"])
    if not vol_df.empty:
        vol_summary = vol_df.groupby(["vol_method", "vol_window"])["sharpe"].mean().sort_values(ascending=False)
        print("  Avg Sharpe by vol method/window:")
        for (method, window), sharpe in vol_summary.head(6).items():
            print(f"    {method}({window}): {sharpe:.3f}")
        best_vol_method = vol_summary.index[0][0]
        best_vol_window = vol_summary.index[0][1]
        print(f"  → Best: {best_vol_method}({best_vol_window})")
    else:
        best_vol_method = "atr"
        best_vol_window = 20

    # ── Test 2: Allocation Methods ──
    print("\n── Test 2: Allocation Methods ──")
    for alloc in ["equal_weight", "inverse_vol", "hrp"]:
        for sig_id in SELECTED_SIGNALS:
            try:
                bt = portfolio_backtest(
                    signals=all_signals[sig_id],
                    daily_bars=daily_data,
                    allocation_method=alloc,
                    vol_method=best_vol_method,
                    vol_window=best_vol_window,
                    portfolio_vol_target=0.12,
                    initial_capital=INITIAL_CAPITAL,
                )
                row = bt["stats"].copy()
                row["signal_id"] = sig_id
                row["signal_name"] = SIGNALS[sig_id]["name"]
                row["test"] = "allocation"
                results.append(row)

                if alloc == "hrp":
                    print(f"    {sig_id} HRP weights: {', '.join(f'{k}={v:.2f}' for k, v in bt['weights'].items())}")
            except Exception as e:
                print(f"    ERROR {sig_id}/{alloc}: {e}")

    alloc_df = pd.DataFrame([r for r in results if r["test"] == "allocation"])
    if not alloc_df.empty:
        alloc_summary = alloc_df.groupby("allocation")["sharpe"].mean().sort_values(ascending=False)
        print("  Avg Sharpe by allocation:")
        for alloc, sharpe in alloc_summary.items():
            print(f"    {alloc}: {sharpe:.3f}")
        best_alloc = alloc_summary.index[0]
        print(f"  → Best: {best_alloc}")
    else:
        best_alloc = "equal_weight"

    # ── Test 3: Vol Targets ──
    print("\n── Test 3: Portfolio Vol Targets ──")
    for vol_target in [0.08, 0.10, 0.12, 0.15, 0.20]:
        for sig_id in SELECTED_SIGNALS:
            try:
                bt = portfolio_backtest(
                    signals=all_signals[sig_id],
                    daily_bars=daily_data,
                    allocation_method=best_alloc,
                    vol_method=best_vol_method,
                    vol_window=best_vol_window,
                    portfolio_vol_target=vol_target,
                    initial_capital=INITIAL_CAPITAL,
                )
                row = bt["stats"].copy()
                row["signal_id"] = sig_id
                row["signal_name"] = SIGNALS[sig_id]["name"]
                row["test"] = "vol_target"
                results.append(row)
            except Exception as e:
                print(f"    ERROR {sig_id}/{vol_target}: {e}")

    vt_df = pd.DataFrame([r for r in results if r["test"] == "vol_target"])
    if not vt_df.empty:
        vt_summary = vt_df.groupby("vol_target").agg(
            sharpe=("sharpe", "mean"),
            cagr=("cagr_pct", "mean"),
            max_dd=("max_dd_pct", "mean"),
            realized_vol=("realized_vol_pct", "mean"),
        ).sort_values("sharpe", ascending=False)
        print("  Vol target comparison:")
        print(f"  {'Target':>8s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}  {'RealVol':>8s}")
        for target, row in vt_summary.iterrows():
            print(f"  {target*100:>7.0f}%  {row['sharpe']:>7.3f}  {row['cagr']:>6.1f}%  {row['max_dd']:>6.1f}%  {row['realized_vol']:>7.1f}%")
        best_vol_target = vt_summary.index[0]
        print(f"  → Best Sharpe at {best_vol_target*100:.0f}% target")
    else:
        best_vol_target = 0.12

    # ── Test 4: Rebalancing Frequency ──
    print("\n── Test 4: Rebalancing Frequency ──")
    for freq in ["daily", "weekly"]:
        for threshold in [0.0, 0.10, 0.25]:
            for sig_id in SELECTED_SIGNALS[:2]:  # Just top 2 to save time
                try:
                    bt = portfolio_backtest(
                        signals=all_signals[sig_id],
                        daily_bars=daily_data,
                        allocation_method=best_alloc,
                        vol_method=best_vol_method,
                        vol_window=best_vol_window,
                        portfolio_vol_target=best_vol_target,
                        initial_capital=INITIAL_CAPITAL,
                        rebalance_freq=freq,
                        rebalance_threshold=threshold,
                    )
                    row = bt["stats"].copy()
                    row["signal_id"] = sig_id
                    row["signal_name"] = SIGNALS[sig_id]["name"]
                    row["test"] = "rebalancing"
                    row["rebal_threshold"] = threshold
                    results.append(row)
                except Exception as e:
                    print(f"    ERROR {sig_id}/{freq}/{threshold}: {e}")

    rebal_df = pd.DataFrame([r for r in results if r["test"] == "rebalancing"])
    if not rebal_df.empty:
        rebal_summary = rebal_df.groupby(["rebalance_freq", "rebal_threshold"])["sharpe"].mean().sort_values(ascending=False)
        print("  Avg Sharpe by rebalancing:")
        for (freq, thresh), sharpe in rebal_summary.items():
            print(f"    {freq}, threshold={thresh:.0%}: {sharpe:.3f}")

    # ── Final: Best Configuration Per Signal ──
    print("\n" + "=" * 60)
    print("SPRINT 2 FINAL RESULTS")
    print("=" * 60)

    print(f"\n  Best configuration:")
    print(f"    Vol estimation: {best_vol_method}({best_vol_window})")
    print(f"    Allocation: {best_alloc}")
    print(f"    Vol target: {best_vol_target*100:.0f}%")

    # Run final config for all signals
    print(f"\n  Final results with optimal config:")
    print(f"  {'Signal':>15s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}  {'RealVol':>8s}  {'Return':>8s}  {'Calmar':>7s}")
    print(f"  {'-'*15}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*8}  {'-'*8}  {'-'*7}")

    final_results = []
    for sig_id in SELECTED_SIGNALS:
        try:
            bt = portfolio_backtest(
                signals=all_signals[sig_id],
                daily_bars=daily_data,
                allocation_method=best_alloc,
                vol_method=best_vol_method,
                vol_window=best_vol_window,
                portfolio_vol_target=best_vol_target,
                initial_capital=INITIAL_CAPITAL,
            )
            s = bt["stats"]
            print(f"  {SIGNALS[sig_id]['name']:>15s}  {s['sharpe']:>7.3f}  {s['cagr_pct']:>6.1f}%  {s['max_dd_pct']:>6.1f}%  {s['realized_vol_pct']:>7.1f}%  {s['total_return_pct']:>7.1f}%  {s['calmar']:>7.3f}")
            row = s.copy()
            row["signal_id"] = sig_id
            row["signal_name"] = SIGNALS[sig_id]["name"]
            final_results.append(row)
        except Exception as e:
            print(f"  {SIGNALS[sig_id]['name']:>15s}  ERROR: {e}")

    # Save all results
    all_results_df = pd.DataFrame(results)
    final_results_df = pd.DataFrame(final_results)
    all_results_df.to_csv("data/sprint2_all_results.csv", index=False)
    final_results_df.to_csv("data/sprint2_final_results.csv", index=False)

    return results, best_vol_method, best_vol_window, best_alloc, best_vol_target


def main():
    t0 = time.time()

    daily_data = load_data()
    all_signals = generate_signals(daily_data)
    results, vol_method, vol_window, alloc, vol_target = run_sweep(daily_data, all_signals)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")
    print(f"Results saved to data/sprint2_*.csv")


if __name__ == "__main__":
    main()
