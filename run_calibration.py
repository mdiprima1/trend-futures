#!/usr/bin/env python3
"""
Run ORB V10 strategy locally and compare against QuantConnect results.
"""
import sys
sys.path.insert(0, ".")

from src.data import load_all_data
from src.orb_strategy import run_orb_strategy, DEFAULT_PARAMS
from src.calibrate import (
    load_qc_equity_curve,
    compare_equity_curves,
    print_calibration_report,
)


def main():
    # Load data
    data = load_all_data("2018-01-01", "2025-12-31")

    # Run strategy
    print("Running ORB V10 strategy...")
    results = run_orb_strategy(data, DEFAULT_PARAMS)

    print(f"\nTrades: {len(results['trades'])}")
    if not results["trades"].empty:
        print(f"ES trades: {(results['trades']['symbol'] == 'ES').sum()}")
        print(f"NQ trades: {(results['trades']['symbol'] == 'NQ').sum()}")
        print(f"Long trades: {(results['trades']['direction'] == 'long').sum()}")
        print(f"Short trades: {(results['trades']['direction'] == 'short').sum()}")

    # Load QC equity curve and compare
    print("\nLoading QC reference equity curve...")
    qc_equity = load_qc_equity_curve()
    print(f"QC equity points: {len(qc_equity)}")

    comparison = compare_equity_curves(results["equity_curve"], qc_equity)
    print_calibration_report(results["stats"], comparison)

    # Trade-level diagnostics
    if not results["trades"].empty:
        trades = results["trades"]
        print("\n── Trade Diagnostics ──")
        print(f"  Avg PnL per trade: ${trades['net_pnl'].mean():.2f}")
        print(f"  Median PnL: ${trades['net_pnl'].median():.2f}")
        print(f"  Avg contracts: {trades['contracts'].mean():.1f}")
        print(f"  Avg range width (ES): {trades[trades['symbol']=='ES']['pnl_points'].apply(abs).mean():.2f} pts" if len(trades[trades['symbol']=='ES']) > 0 else "")

        # Yearly breakdown
        trades["year"] = pd.to_datetime(trades["entry_time"]).dt.year
        yearly = trades.groupby("year").agg(
            n_trades=("net_pnl", "count"),
            total_pnl=("net_pnl", "sum"),
            win_rate=("net_pnl", lambda x: (x > 0).mean()),
        )
        print("\n── Yearly Breakdown ──")
        print(yearly.to_string())


if __name__ == "__main__":
    import pandas as pd
    main()
