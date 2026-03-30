#!/usr/bin/env python3
"""
Sprint 6: Cross-Asset Dynamics & Network Effects
"""
import sys
import time
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from src.data import fetch_futures_1m, build_daily_bars
from src.regimes import BLEND_SIGNALS
from src.cross_asset import (
    compute_lead_lag_matrix, network_momentum_signal,
    carry_signal_from_returns, cross_sectional_momentum,
    multi_factor_signal,
)
from src.portfolio import portfolio_backtest

INSTRUMENTS = ["ES", "NQ", "ZN", "GC", "CL", "6E"]
INITIAL_CAPITAL = 500_000

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


def main():
    t0 = time.time()
    daily_data = load_data()

    # Build returns dict
    returns_dict = {}
    for sym, daily in daily_data.items():
        returns_dict[sym] = daily["close"].pct_change()

    # ── 1. Lead-Lag Analysis ──
    print("\n" + "=" * 60)
    print("1. LEAD-LAG ANALYSIS")
    print("=" * 60)

    lead_lag, best_corr = compute_lead_lag_matrix(returns_dict, max_lag=5)
    print("\n  Lead-lag matrix (positive = row leads column):")
    print(lead_lag.to_string(float_format=lambda x: f"{x:>4.0f}"))
    print("\n  Cross-correlation at best lag:")
    print(best_corr.to_string(float_format=lambda x: f"{x:>6.3f}"))

    # Find strongest lead-lag pairs
    print("\n  Strongest lead-lag relationships:")
    for i, si in enumerate(INSTRUMENTS):
        for j, sj in enumerate(INSTRUMENTS):
            if i >= j:
                continue
            lag = lead_lag.loc[si, sj]
            corr = best_corr.loc[si, sj]
            if abs(corr) > 0.05:
                leader = si if lag > 0 else sj
                follower = sj if lag > 0 else si
                print(f"    {leader} leads {follower} by {abs(lag):.0f} days (corr={corr:.3f})")

    # ── 2. Baseline: Trend-Only (Sprint 4 winner) ──
    print("\n" + "=" * 60)
    print("2. BASELINES")
    print("=" * 60)

    # Fast+Slow trend (Sprint 4 winner)
    trend_fn = BLEND_SIGNALS["BL-FS"]["fn"]
    trend_signals = {sym: trend_fn(daily) for sym, daily in daily_data.items()}

    bt_trend = portfolio_backtest(
        signals=trend_signals, daily_bars=daily_data,
        initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG,
    )
    s = bt_trend["stats"]
    print(f"  Trend-only (Fast+Slow):  Sharpe={s['sharpe']:.3f}  CAGR={s['cagr_pct']:.1f}%  MaxDD={s['max_dd_pct']:.1f}%  Calmar={s['calmar']:.3f}")

    # ── 3. Individual Cross-Asset Signals ──
    print("\n" + "=" * 60)
    print("3. INDIVIDUAL CROSS-ASSET SIGNALS")
    print("=" * 60)

    # Network Momentum
    print("\n  Network Momentum:")
    net_signals = network_momentum_signal(returns_dict, daily_data, lookback=63, corr_window=126)
    bt_net = portfolio_backtest(
        signals=net_signals, daily_bars=daily_data,
        initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG,
    )
    s = bt_net["stats"]
    print(f"    Sharpe={s['sharpe']:.3f}  CAGR={s['cagr_pct']:.1f}%  MaxDD={s['max_dd_pct']:.1f}%")

    # Carry
    print("\n  Carry Signal:")
    carry_signals = {sym: carry_signal_from_returns(daily, sym) for sym, daily in daily_data.items()}
    bt_carry = portfolio_backtest(
        signals=carry_signals, daily_bars=daily_data,
        initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG,
    )
    s = bt_carry["stats"]
    print(f"    Sharpe={s['sharpe']:.3f}  CAGR={s['cagr_pct']:.1f}%  MaxDD={s['max_dd_pct']:.1f}%")

    # Cross-Sectional Momentum
    print("\n  Cross-Sectional Momentum:")
    xsmom_signals = cross_sectional_momentum(returns_dict, daily_data, lookback=126)
    bt_xsmom = portfolio_backtest(
        signals=xsmom_signals, daily_bars=daily_data,
        initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG,
    )
    s = bt_xsmom["stats"]
    print(f"    Sharpe={s['sharpe']:.3f}  CAGR={s['cagr_pct']:.1f}%  MaxDD={s['max_dd_pct']:.1f}%")

    # ── 4. Multi-Factor Combinations ──
    print("\n" + "=" * 60)
    print("4. MULTI-FACTOR COMBINATIONS")
    print("=" * 60)

    results = []

    # Combo 1: Trend + Carry (no network/xsmom)
    combo1 = multi_factor_signal(
        trend_signals, carry_signals, xsmom_signals={s: pd.Series(0, index=daily_data[s].index) for s in INSTRUMENTS},
        weights={"trend": 0.70, "carry": 0.30, "xsmom": 0.00},
    )
    bt = portfolio_backtest(signals=combo1, daily_bars=daily_data, initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG)
    results.append({"name": "Trend+Carry (70/30)", **bt["stats"]})
    print(f"  Trend+Carry (70/30):       Sharpe={bt['stats']['sharpe']:.3f}  CAGR={bt['stats']['cagr_pct']:.1f}%  MaxDD={bt['stats']['max_dd_pct']:.1f}%")

    # Combo 2: Trend + XSmom
    combo2 = multi_factor_signal(
        trend_signals, carry_signals={s: pd.Series(0, index=daily_data[s].index) for s in INSTRUMENTS},
        xsmom_signals=xsmom_signals,
        weights={"trend": 0.70, "carry": 0.00, "xsmom": 0.30},
    )
    bt = portfolio_backtest(signals=combo2, daily_bars=daily_data, initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG)
    results.append({"name": "Trend+XSmom (70/30)", **bt["stats"]})
    print(f"  Trend+XSmom (70/30):       Sharpe={bt['stats']['sharpe']:.3f}  CAGR={bt['stats']['cagr_pct']:.1f}%  MaxDD={bt['stats']['max_dd_pct']:.1f}%")

    # Combo 3: Trend + Network
    combo3 = multi_factor_signal(
        trend_signals, carry_signals={s: pd.Series(0, index=daily_data[s].index) for s in INSTRUMENTS},
        xsmom_signals={s: pd.Series(0, index=daily_data[s].index) for s in INSTRUMENTS},
        network_signals=net_signals,
        weights={"trend": 0.70, "carry": 0.00, "xsmom": 0.00, "network": 0.30},
    )
    bt = portfolio_backtest(signals=combo3, daily_bars=daily_data, initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG)
    results.append({"name": "Trend+Network (70/30)", **bt["stats"]})
    print(f"  Trend+Network (70/30):     Sharpe={bt['stats']['sharpe']:.3f}  CAGR={bt['stats']['cagr_pct']:.1f}%  MaxDD={bt['stats']['max_dd_pct']:.1f}%")

    # Combo 4: Full multi-factor (default weights)
    combo4 = multi_factor_signal(
        trend_signals, carry_signals, xsmom_signals, net_signals,
        weights={"trend": 0.50, "carry": 0.20, "xsmom": 0.15, "network": 0.15},
    )
    bt = portfolio_backtest(signals=combo4, daily_bars=daily_data, initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG)
    results.append({"name": "Full Multi-Factor", **bt["stats"]})
    print(f"  Full Multi-Factor:         Sharpe={bt['stats']['sharpe']:.3f}  CAGR={bt['stats']['cagr_pct']:.1f}%  MaxDD={bt['stats']['max_dd_pct']:.1f}%")

    # Combo 5: Trend-heavy multi-factor
    combo5 = multi_factor_signal(
        trend_signals, carry_signals, xsmom_signals, net_signals,
        weights={"trend": 0.60, "carry": 0.15, "xsmom": 0.10, "network": 0.15},
    )
    bt = portfolio_backtest(signals=combo5, daily_bars=daily_data, initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG)
    results.append({"name": "Trend-Heavy Multi", **bt["stats"]})
    print(f"  Trend-Heavy Multi:         Sharpe={bt['stats']['sharpe']:.3f}  CAGR={bt['stats']['cagr_pct']:.1f}%  MaxDD={bt['stats']['max_dd_pct']:.1f}%")

    # ── 5. Correlation Between Signal Types ──
    print("\n" + "=" * 60)
    print("5. SIGNAL CORRELATION ANALYSIS")
    print("=" * 60)

    # Build portfolio-level daily returns for each signal type
    sig_types = {
        "Trend": trend_signals,
        "Network": net_signals,
        "Carry": carry_signals,
        "XSmom": xsmom_signals,
    }

    type_returns = {}
    for name, sigs in sig_types.items():
        # Simple proxy: average signal × instrument return
        ret_list = []
        for sym in INSTRUMENTS:
            sig = sigs[sym].reindex(returns_dict[sym].index).fillna(0)
            ret = sig * returns_dict[sym]
            ret_list.append(ret)
        combined = pd.concat(ret_list, axis=1).dropna()
        type_returns[name] = combined.mean(axis=1)

    type_ret_df = pd.DataFrame(type_returns).dropna()
    corr = type_ret_df.corr()
    print("\n  Signal type return correlations:")
    print(corr.to_string(float_format=lambda x: f"{x:.3f}"))

    # ── Final Report ──
    print("\n" + "=" * 60)
    print("SPRINT 6 FINAL REPORT")
    print("=" * 60)

    trend_sharpe = bt_trend["stats"]["sharpe"]
    print(f"\n  Trend-only baseline: Sharpe={trend_sharpe:.3f}")

    results_df = pd.DataFrame(results).sort_values("sharpe", ascending=False)
    print(f"\n  {'Signal':>25s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}  {'Calmar':>7s}  {'vs Trend':>9s}")
    print(f"  {'-'*25}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*9}")
    for _, row in results_df.iterrows():
        delta = row["sharpe"] - trend_sharpe
        marker = "+" if delta > 0 else ""
        print(f"  {row['name']:>25s}  {row['sharpe']:>7.3f}  {row['cagr_pct']:>6.1f}%  {row['max_dd_pct']:>6.1f}%  {row['calmar']:>7.3f}  {marker}{delta:>8.3f}")

    # Save
    results_df.to_csv("data/sprint6_results.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
