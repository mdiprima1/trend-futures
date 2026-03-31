#!/usr/bin/env python3
"""
Universe Expansion: Run the integrated system on 20-26 instruments.
Re-evaluate HRP, sector risk parity, and cross-asset signals with the larger universe.
"""
import sys
import time
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from src.data import fetch_futures_1m, build_daily_bars
from src.regimes import BLEND_SIGNALS
from src.portfolio import portfolio_backtest
from src.config import SECTORS, SYMBOL_SECTOR, CONTRACT_MULTIPLIERS

# Full universe
ALL_INSTRUMENTS = list(CONTRACT_MULTIPLIERS.keys())
INITIAL_CAPITAL = 1_000_000  # Scale up for more instruments

SYSTEM_CONFIG = {
    "vol_method": "atr",
    "vol_window": 20,
    "portfolio_vol_target": 0.15,  # Can increase with more diversification
    "rebalance_freq": "weekly",
}

DATE_RANGES = [("2018-01-01", "2025-12-31"), ("2010-06-07", "2025-12-31")]


def load_all_data():
    print("=" * 60)
    print("LOADING EXPANDED UNIVERSE (cached data only)")
    print("=" * 60)

    from src.config import CACHE_DIR

    daily_data = {}
    failed = []

    for sym in ALL_INSTRUMENTS:
        loaded = False
        for start, end in DATE_RANGES:
            # Only load if cache file exists — don't download
            cache_name = f"{sym}_1m_{start}_{end}"
            cache_path = CACHE_DIR / f"{cache_name}.parquet"
            if not cache_path.exists():
                continue
            try:
                m = fetch_futures_1m(sym, start, end)
                m = m[m.index >= pd.Timestamp("2018-01-01", tz="US/Eastern")]
                d = build_daily_bars(m)
                if len(d) > 200:
                    daily_data[sym] = d
                    loaded = True
                    break
            except Exception:
                continue
        if loaded:
            print(f"  {sym:>4s} ({SYMBOL_SECTOR.get(sym, '?'):>14s}): {len(daily_data[sym]):>5d} daily bars")
        else:
            failed.append(sym)

    if failed:
        print(f"\n  Failed to load: {', '.join(failed)}")

    # Summary by sector
    print(f"\n  Total instruments loaded: {len(daily_data)}")
    for sector, syms in SECTORS.items():
        loaded = [s for s in syms if s in daily_data]
        print(f"    {sector:>14s}: {len(loaded)}/{len(syms)} ({', '.join(loaded)})")

    return daily_data


def run_comparison(daily_data):
    """Compare allocation methods on the expanded universe."""
    print("\n" + "=" * 60)
    print("ALLOCATION METHOD COMPARISON (Expanded Universe)")
    print("=" * 60)

    trend_fn = BLEND_SIGNALS["BL-FS"]["fn"]
    signals = {sym: trend_fn(daily) for sym, daily in daily_data.items()}

    results = []

    for alloc in ["equal_weight", "inverse_vol", "hrp"]:
        for vt in [0.12, 0.15, 0.20]:
            config = SYSTEM_CONFIG.copy()
            config["allocation_method"] = alloc
            config["portfolio_vol_target"] = vt

            try:
                bt = portfolio_backtest(
                    signals=signals, daily_bars=daily_data,
                    initial_capital=INITIAL_CAPITAL, **config,
                )
                s = bt["stats"]
                s["allocation"] = alloc
                s["vol_target"] = vt
                results.append(s)

                if alloc == "hrp" and vt == 0.15:
                    print(f"\n  HRP weights (15% target):")
                    sorted_w = sorted(bt["weights"].items(), key=lambda x: x[1], reverse=True)
                    for sym, w in sorted_w:
                        if w > 0.01:
                            print(f"    {sym:>4s} ({SYMBOL_SECTOR.get(sym, '?'):>14s}): {w:.1%}")
            except Exception as e:
                print(f"  ERROR {alloc}/{vt}: {e}")

    results_df = pd.DataFrame(results)

    print(f"\n  {'Allocation':>12s}  {'VolTgt':>7s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}  {'Calmar':>7s}  {'RealVol':>8s}")
    print(f"  {'-'*12}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*8}")

    for _, row in results_df.sort_values("sharpe", ascending=False).iterrows():
        print(f"  {row['allocation']:>12s}  {row['vol_target']*100:>6.0f}%  {row['sharpe']:>7.3f}  {row['cagr_pct']:>6.1f}%  {row['max_dd_pct']:>6.1f}%  {row['calmar']:>7.3f}  {row['realized_vol_pct']:>7.1f}%")

    return results_df


def run_regime_analysis(daily_data):
    """Regime analysis on expanded universe."""
    print("\n" + "=" * 60)
    print("REGIME ANALYSIS (Expanded Universe)")
    print("=" * 60)

    trend_fn = BLEND_SIGNALS["BL-FS"]["fn"]

    regimes = {
        "Full Period":     ("2018-01-01", "2025-12-31"),
        "2020 COVID":      ("2020-01-01", "2020-12-31"),
        "2022 Rate Shock": ("2022-01-01", "2022-12-31"),
        "2023 Range-Bound":("2023-01-01", "2023-12-31"),
        "2025 Tariffs":    ("2025-01-01", "2025-12-31"),
    }

    # Use best config from comparison
    config = SYSTEM_CONFIG.copy()
    config["allocation_method"] = "equal_weight"
    config["portfolio_vol_target"] = 0.15

    print(f"\n  {'Regime':>20s}  {'Sharpe':>7s}  {'Return':>8s}  {'MaxDD':>7s}  {'Calmar':>7s}")
    print(f"  {'-'*20}  {'-'*7}  {'-'*8}  {'-'*7}  {'-'*7}")

    for name, (start, end) in regimes.items():
        start_ts = pd.Timestamp(start, tz="US/Eastern")
        end_ts = pd.Timestamp(end, tz="US/Eastern")

        regime_data = {}
        for sym, daily in daily_data.items():
            mask = (daily.index >= start_ts) & (daily.index <= end_ts)
            subset = daily[mask]
            if len(subset) > 60:
                regime_data[sym] = subset

        if len(regime_data) < 10:
            continue

        signals = {sym: trend_fn(daily) for sym, daily in regime_data.items()}
        bt = portfolio_backtest(
            signals=signals, daily_bars=regime_data,
            initial_capital=INITIAL_CAPITAL, **config,
        )
        s = bt["stats"]
        print(f"  {name:>20s}  {s['sharpe']:>7.3f}  {s['total_return_pct']:>7.1f}%  {s['max_dd_pct']:>6.1f}%  {s['calmar']:>7.3f}")


def compare_6_vs_26(daily_data):
    """Compare 6-instrument vs full universe."""
    print("\n" + "=" * 60)
    print("COMPARISON: 6 Instruments vs Full Universe")
    print("=" * 60)

    trend_fn = BLEND_SIGNALS["BL-FS"]["fn"]

    # 6-instrument (original)
    original_6 = ["ES", "NQ", "ZN", "GC", "CL", "6E"]
    data_6 = {s: daily_data[s] for s in original_6 if s in daily_data}
    signals_6 = {sym: trend_fn(daily) for sym, daily in data_6.items()}

    # Full universe
    signals_full = {sym: trend_fn(daily) for sym, daily in daily_data.items()}

    configs = [
        ("6 inst / 12% vol / EW", data_6, signals_6, {"allocation_method": "equal_weight", "portfolio_vol_target": 0.12}),
        ("6 inst / 15% vol / EW", data_6, signals_6, {"allocation_method": "equal_weight", "portfolio_vol_target": 0.15}),
        (f"{len(daily_data)} inst / 12% vol / EW", daily_data, signals_full, {"allocation_method": "equal_weight", "portfolio_vol_target": 0.12}),
        (f"{len(daily_data)} inst / 15% vol / EW", daily_data, signals_full, {"allocation_method": "equal_weight", "portfolio_vol_target": 0.15}),
        (f"{len(daily_data)} inst / 15% vol / HRP", daily_data, signals_full, {"allocation_method": "hrp", "portfolio_vol_target": 0.15}),
        (f"{len(daily_data)} inst / 20% vol / EW", daily_data, signals_full, {"allocation_method": "equal_weight", "portfolio_vol_target": 0.20}),
    ]

    print(f"\n  {'Config':>30s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}  {'Calmar':>7s}  {'RealVol':>8s}  {'Final $':>12s}")
    print(f"  {'-'*30}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*8}  {'-'*12}")

    for name, data, sigs, extra_config in configs:
        config = SYSTEM_CONFIG.copy()
        config.update(extra_config)
        bt = portfolio_backtest(
            signals=sigs, daily_bars=data,
            initial_capital=INITIAL_CAPITAL, **config,
        )
        s = bt["stats"]
        print(f"  {name:>30s}  {s['sharpe']:>7.3f}  {s['cagr_pct']:>6.1f}%  {s['max_dd_pct']:>6.1f}%  {s['calmar']:>7.3f}  {s['realized_vol_pct']:>7.1f}%  ${s['final_equity']:>11,.0f}")


def main():
    t0 = time.time()

    daily_data = load_all_data()

    if len(daily_data) < 8:
        print(f"\nOnly {len(daily_data)} instruments loaded. Need at least 8 for meaningful expansion.")
        print("Data may still be downloading. Try again later.")
        return

    # Run comparisons
    results_df = run_comparison(daily_data)
    run_regime_analysis(daily_data)
    compare_6_vs_26(daily_data)

    # Save
    results_df.to_csv("data/expanded_universe_results.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
