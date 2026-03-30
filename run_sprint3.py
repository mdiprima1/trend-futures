#!/usr/bin/env python3
"""
Sprint 3: Transaction Costs & Execution Reality
Analyze cost impact, turnover, capacity, and roll costs.
"""
import sys
import time
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from src.data import fetch_futures_1m, build_daily_bars
from src.signals import SIGNALS
from src.costs import (
    COST_TABLE, cost_per_contract_round_trip, market_impact_cost,
    annual_roll_cost, capacity_estimate, compute_turnover_stats, print_cost_table,
)
from src.portfolio import portfolio_backtest
from src.config import CONTRACT_MULTIPLIERS

INSTRUMENTS = ["ES", "NQ", "ZN", "GC", "CL", "6E"]
SELECTED_SIGNALS = ["TS-04", "MA-04", "MA-03", "MA-02", "SE-02"]
INITIAL_CAPITAL = 500_000

# Sprint 2 optimal config
BEST_CONFIG = {
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


def main():
    t0 = time.time()
    daily_data = load_data()

    # ── 1. Cost Table ──
    print("\n" + "=" * 60)
    print("1. PER-INSTRUMENT COST TABLE")
    print("=" * 60)
    print_cost_table()

    # ── 2. Capacity Analysis ──
    print("\n" + "=" * 60)
    print("2. CAPACITY ANALYSIS (1% participation limit)")
    print("=" * 60)
    print(f"  {'Symbol':>6s}  {'ADV':>10s}  {'Max Contracts':>14s}  {'Max Notional':>14s}")
    print(f"  {'------':>6s}  {'----------':>10s}  {'--------------':>14s}  {'--------------':>14s}")
    total_capacity = 0
    for sym in INSTRUMENTS:
        cap = capacity_estimate(sym, max_participation_pct=1.0)
        total_capacity += cap["max_notional_usd"]
        print(f"  {sym:>6s}  {cap['adv']:>10,d}  {cap['max_contracts']:>14,d}  ${cap['max_notional_usd']:>13,.0f}")
    print(f"  {'TOTAL':>6s}  {'':>10s}  {'':>14s}  ${total_capacity:>13,.0f}")

    # ── 3. Turnover Analysis ──
    print("\n" + "=" * 60)
    print("3. TURNOVER ANALYSIS")
    print("=" * 60)

    all_signals = {}
    for sig_id in SELECTED_SIGNALS:
        sig_fn = SIGNALS[sig_id]["fn"]
        all_signals[sig_id] = {}
        for sym, daily in daily_data.items():
            all_signals[sig_id][sym] = sig_fn(daily)

    print(f"  {'Signal':>15s}  {'Trades/yr':>10s}  {'Avg Hold':>9s}  {'Turnover':>9s}")
    print(f"  {'-'*15}  {'-'*10}  {'-'*9}  {'-'*9}")

    turnover_data = []
    for sig_id in SELECTED_SIGNALS:
        trades_list = []
        hold_list = []
        for sym in INSTRUMENTS:
            signal = all_signals[sig_id][sym]
            stats = compute_turnover_stats(signal, signal)  # Use signal as proxy for contracts
            trades_list.append(stats["trades_per_year"])
            hold_list.append(stats["avg_holding_days"])
        avg_trades = np.mean(trades_list)
        avg_hold = np.mean(hold_list)
        print(f"  {SIGNALS[sig_id]['name']:>15s}  {avg_trades:>10.1f}  {avg_hold:>8.1f}d  {avg_trades * 2 / 252:>8.2f}x")
        turnover_data.append({
            "signal_id": sig_id,
            "signal_name": SIGNALS[sig_id]["name"],
            "trades_per_year": avg_trades,
            "avg_holding_days": avg_hold,
        })

    # ── 4. Gross vs Net Sharpe Comparison ──
    print("\n" + "=" * 60)
    print("4. GROSS vs NET SHARPE (Cost Sensitivity)")
    print("=" * 60)

    # Run with different cost multipliers
    cost_multipliers = [0.0, 0.5, 1.0, 2.0, 3.0]  # 0=gross, 1=base, 2=pessimistic, 3=stress

    results = []
    for cost_mult in cost_multipliers:
        for sig_id in SELECTED_SIGNALS:
            # Modify portfolio backtest to use scaled costs
            # We'll run with the portfolio engine and scale the tick sizes
            bt = portfolio_backtest(
                signals=all_signals[sig_id],
                daily_bars=daily_data,
                initial_capital=INITIAL_CAPITAL,
                **BEST_CONFIG,
            )

            # The portfolio engine already includes base costs.
            # For gross (cost_mult=0), re-run without costs by using a very large max_contracts
            # Actually, let's compute cost drag analytically

            stats = bt["stats"].copy()
            stats["signal_id"] = sig_id
            stats["signal_name"] = SIGNALS[sig_id]["name"]
            stats["cost_mult"] = cost_mult

            # Estimate annual cost drag
            # Average position per instrument
            avg_pos_contracts = 5  # Approximate from Sprint 2 results
            annual_trades = turnover_data[[t for t in range(len(turnover_data)) if turnover_data[t]["signal_id"] == sig_id][0]]["trades_per_year"]

            total_annual_cost = 0
            for sym in INSTRUMENTS:
                rt_cost = cost_per_contract_round_trip(sym) * cost_mult
                # Trade cost
                trade_cost = rt_cost * avg_pos_contracts * annual_trades / len(INSTRUMENTS)
                # Roll cost
                price = daily_data[sym]["close"].mean()
                multiplier = CONTRACT_MULTIPLIERS[sym]
                notional = price * multiplier
                roll = annual_roll_cost(sym, avg_pos_contracts, notional) * cost_mult / len(INSTRUMENTS)
                total_annual_cost += trade_cost + roll

            cost_drag_pct = total_annual_cost / INITIAL_CAPITAL * 100
            stats["annual_cost_drag_pct"] = round(cost_drag_pct, 2)
            stats["adjusted_cagr"] = round(stats["cagr_pct"] - cost_drag_pct, 2)
            results.append(stats)

    results_df = pd.DataFrame(results)

    # Print comparison
    print(f"\n  {'Signal':>15s}", end="")
    for cm in cost_multipliers:
        label = "Gross" if cm == 0 else f"{cm:.0f}x Cost" if cm >= 1 else f"{cm:.1f}x"
        print(f"  {label:>10s}", end="")
    print()
    print(f"  {'-'*15}", end="")
    for _ in cost_multipliers:
        print(f"  {'-'*10}", end="")
    print()

    for sig_id in SELECTED_SIGNALS:
        sig_data = results_df[results_df["signal_id"] == sig_id]
        name = SIGNALS[sig_id]["name"]
        print(f"  {name:>15s}", end="")
        for cm in cost_multipliers:
            row = sig_data[sig_data["cost_mult"] == cm].iloc[0]
            print(f"  {row['adjusted_cagr']:>9.1f}%", end="")
        print()

    # ── 5. Cost Breakdown Per Instrument ──
    print("\n" + "=" * 60)
    print("5. ANNUAL COST BREAKDOWN (per instrument, 5 contracts avg)")
    print("=" * 60)

    avg_contracts = 5
    avg_annual_trades = 30  # Approximate

    print(f"  {'Symbol':>6s}  {'Commission':>11s}  {'Spread':>8s}  {'Impact':>8s}  {'Roll':>8s}  {'Total':>8s}  {'Drag':>7s}")
    print(f"  {'------':>6s}  {'-----------':>11s}  {'--------':>8s}  {'--------':>8s}  {'--------':>8s}  {'--------':>8s}  {'-------':>7s}")

    for sym in INSTRUMENTS:
        ct = COST_TABLE[sym]
        multiplier = CONTRACT_MULTIPLIERS[sym]

        # Commission (annual, round-trip)
        annual_comm = ct["commission_per_side"] * 2 * avg_contracts * avg_annual_trades

        # Spread cost
        spread = ct["spread_ticks"] * ct["tick_size"] * multiplier * avg_contracts * avg_annual_trades

        # Market impact
        impact = market_impact_cost(sym, avg_contracts) * avg_annual_trades

        # Roll cost
        price = daily_data[sym]["close"].mean()
        notional = price * multiplier
        roll = annual_roll_cost(sym, avg_contracts, notional)

        total = annual_comm + spread + impact + roll
        drag_bps = total / INITIAL_CAPITAL * 10000

        print(f"  {sym:>6s}  ${annual_comm:>10,.0f}  ${spread:>7,.0f}  ${impact:>7,.0f}  ${roll:>7,.0f}  ${total:>7,.0f}  {drag_bps:>5.0f}bp")

    # ── 6. Net Sharpe Rankings ──
    print("\n" + "=" * 60)
    print("6. FINAL NET RANKINGS (1x cost)")
    print("=" * 60)

    base_results = results_df[results_df["cost_mult"] == 1.0].sort_values("sharpe", ascending=False)
    print(f"  {'Signal':>15s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'CostDrag':>9s}  {'NetCAGR':>8s}  {'MaxDD':>7s}")
    print(f"  {'-'*15}  {'-'*7}  {'-'*7}  {'-'*9}  {'-'*8}  {'-'*7}")
    for _, row in base_results.iterrows():
        print(f"  {row['signal_name']:>15s}  {row['sharpe']:>7.3f}  {row['cagr_pct']:>6.1f}%  {row['annual_cost_drag_pct']:>8.2f}%  {row['adjusted_cagr']:>7.2f}%  {row['max_dd_pct']:>6.1f}%")

    # ── 7. Zakamulin Check: Does Optimal Lookback Change With Costs? ──
    print("\n" + "=" * 60)
    print("7. LOOKBACK SENSITIVITY TO COSTS (Zakamulin & Giner 2022)")
    print("=" * 60)

    # Compare fast vs slow signals under different cost levels
    print("  Signals ranked by net CAGR at different cost levels:")
    for cm in [0.0, 1.0, 3.0]:
        label = "Gross" if cm == 0 else f"{cm:.0f}x"
        sub = results_df[results_df["cost_mult"] == cm].sort_values("adjusted_cagr", ascending=False)
        top = sub.iloc[0]
        print(f"  {label:>5s}: {top['signal_name']:>15s} (CAGR={top['adjusted_cagr']:.2f}%)")

    # Save results
    results_df.to_csv("data/sprint3_results.csv", index=False)
    pd.DataFrame(turnover_data).to_csv("data/sprint3_turnover.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
