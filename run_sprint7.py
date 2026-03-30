#!/usr/bin/env python3
"""
Sprint 7: Full System Integration & Stress Testing
"""
import sys
import time
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from src.data import fetch_futures_1m, build_daily_bars, fetch_spy_daily
from src.regimes import BLEND_SIGNALS
from src.portfolio import portfolio_backtest

INSTRUMENTS = ["ES", "NQ", "ZN", "GC", "CL", "6E"]
INITIAL_CAPITAL = 500_000

SYSTEM_CONFIG = {
    "vol_method": "atr",
    "vol_window": 20,
    "allocation_method": "equal_weight",
    "portfolio_vol_target": 0.12,
    "rebalance_freq": "weekly",
}

DATE_RANGES = [("2018-01-01", "2025-12-31"), ("2010-06-07", "2025-12-31")]

# Market regime periods
REGIMES = {
    "Full Period":       ("2018-01-01", "2025-12-31"),
    "2018 Vol Shock":    ("2018-01-01", "2018-12-31"),
    "2019 Low Vol":      ("2019-01-01", "2019-12-31"),
    "2020 COVID":        ("2020-01-01", "2020-12-31"),
    "2021 Recovery":     ("2021-01-01", "2021-12-31"),
    "2022 Rate Shock":   ("2022-01-01", "2022-12-31"),
    "2023 Range-Bound":  ("2023-01-01", "2023-12-31"),
    "2024 Election":     ("2024-01-01", "2024-12-31"),
    "2025 Tariffs":      ("2025-01-01", "2025-12-31"),
}


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

    # SPY for crisis alpha analysis
    spy = fetch_spy_daily("2018-01-01", "2025-12-31")
    return daily_data, spy


def run_full_system(daily_data):
    """Run the integrated system: Fast+Slow blend with Sprint 2 config."""
    trend_fn = BLEND_SIGNALS["BL-FS"]["fn"]
    signals = {sym: trend_fn(daily) for sym, daily in daily_data.items()}

    bt = portfolio_backtest(
        signals=signals, daily_bars=daily_data,
        initial_capital=INITIAL_CAPITAL, **SYSTEM_CONFIG,
    )
    return bt


def regime_analysis(daily_data):
    """Run system across different market regimes."""
    print("\n" + "=" * 60)
    print("1. REGIME ANALYSIS")
    print("=" * 60)

    trend_fn = BLEND_SIGNALS["BL-FS"]["fn"]
    results = []

    print(f"\n  {'Regime':>20s}  {'Sharpe':>7s}  {'Return':>8s}  {'MaxDD':>7s}  {'Calmar':>7s}  {'RealVol':>8s}")
    print(f"  {'-'*20}  {'-'*7}  {'-'*8}  {'-'*7}  {'-'*7}  {'-'*8}")

    for regime_name, (start, end) in REGIMES.items():
        start_ts = pd.Timestamp(start, tz="US/Eastern")
        end_ts = pd.Timestamp(end, tz="US/Eastern")

        # Filter data to regime period
        regime_data = {}
        for sym, daily in daily_data.items():
            mask = (daily.index >= start_ts) & (daily.index <= end_ts)
            subset = daily[mask]
            if len(subset) > 60:
                regime_data[sym] = subset

        if len(regime_data) < 4:
            continue

        signals = {sym: trend_fn(daily) for sym, daily in regime_data.items()}

        try:
            bt = portfolio_backtest(
                signals=signals, daily_bars=regime_data,
                initial_capital=INITIAL_CAPITAL, **SYSTEM_CONFIG,
            )
            s = bt["stats"]
            results.append({"regime": regime_name, **s})
            print(f"  {regime_name:>20s}  {s['sharpe']:>7.3f}  {s['total_return_pct']:>7.1f}%  {s['max_dd_pct']:>6.1f}%  {s['calmar']:>7.3f}  {s['realized_vol_pct']:>7.1f}%")
        except Exception as e:
            print(f"  {regime_name:>20s}  ERROR: {e}")

    return pd.DataFrame(results)


def walk_forward_test(daily_data):
    """Walk-forward out-of-sample validation."""
    print("\n" + "=" * 60)
    print("2. WALK-FORWARD VALIDATION")
    print("=" * 60)

    trend_fn = BLEND_SIGNALS["BL-FS"]["fn"]

    # 3-year in-sample, 1-year out-of-sample, rolling
    windows = [
        ("2018-2020 IS → 2021 OOS", "2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
        ("2019-2021 IS → 2022 OOS", "2019-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
        ("2020-2022 IS → 2023 OOS", "2020-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
        ("2021-2023 IS → 2024 OOS", "2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
        ("2022-2024 IS → 2025 OOS", "2022-01-01", "2024-12-31", "2025-01-01", "2025-12-31"),
    ]

    print(f"\n  {'Window':>30s}  {'IS Sharpe':>10s}  {'OOS Sharpe':>11s}  {'OOS Return':>11s}  {'Ratio':>6s}")
    print(f"  {'-'*30}  {'-'*10}  {'-'*11}  {'-'*11}  {'-'*6}")

    is_sharpes = []
    oos_sharpes = []

    for name, is_start, is_end, oos_start, oos_end in windows:
        for period_name, p_start, p_end in [("IS", is_start, is_end), ("OOS", oos_start, oos_end)]:
            start_ts = pd.Timestamp(p_start, tz="US/Eastern")
            end_ts = pd.Timestamp(p_end, tz="US/Eastern")

            period_data = {}
            for sym, daily in daily_data.items():
                mask = (daily.index >= start_ts) & (daily.index <= end_ts)
                subset = daily[mask]
                if len(subset) > 60:
                    period_data[sym] = subset

            if len(period_data) < 4:
                continue

            signals = {sym: trend_fn(daily) for sym, daily in period_data.items()}
            bt = portfolio_backtest(
                signals=signals, daily_bars=period_data,
                initial_capital=INITIAL_CAPITAL, **SYSTEM_CONFIG,
            )

            if period_name == "IS":
                is_sharpe = bt["stats"]["sharpe"]
            else:
                oos_sharpe = bt["stats"]["sharpe"]
                oos_return = bt["stats"]["total_return_pct"]
                ratio = oos_sharpe / is_sharpe if is_sharpe != 0 else 0
                is_sharpes.append(is_sharpe)
                oos_sharpes.append(oos_sharpe)
                print(f"  {name:>30s}  {is_sharpe:>10.3f}  {oos_sharpe:>11.3f}  {oos_return:>10.1f}%  {ratio:>5.2f}")

    if oos_sharpes:
        avg_ratio = np.mean([o/i if i != 0 else 0 for o, i in zip(oos_sharpes, is_sharpes)])
        print(f"\n  Average OOS/IS Sharpe ratio: {avg_ratio:.2f}")
        print(f"  Average OOS Sharpe: {np.mean(oos_sharpes):.3f}")
        if avg_ratio > 0.5:
            print("  → Walk-forward PASSES (ratio > 0.5)")
        else:
            print("  → Walk-forward NEEDS ATTENTION (ratio < 0.5)")

    return is_sharpes, oos_sharpes


def parameter_sensitivity(daily_data):
    """Monte Carlo parameter perturbation."""
    print("\n" + "=" * 60)
    print("3. PARAMETER SENSITIVITY")
    print("=" * 60)

    from src.signals import signal_MA04, signal_TS04

    # Test different signal parameter combinations
    configs = [
        ("EMA(8/80) + TSMOM(200)", lambda df: _blend(signal_ema_custom(df, 8, 80), tsmom_custom(df, 200))),
        ("EMA(10/100) + TSMOM(252)", lambda df: _blend(signal_MA04(df), signal_TS04(df))),  # Base
        ("EMA(12/120) + TSMOM(300)", lambda df: _blend(signal_ema_custom(df, 12, 120), tsmom_custom(df, 300))),
        ("EMA(15/80) + TSMOM(200)", lambda df: _blend(signal_ema_custom(df, 15, 80), tsmom_custom(df, 200))),
        ("EMA(10/100) + TSMOM(180)", lambda df: _blend(signal_MA04(df), tsmom_custom(df, 180))),
    ]

    print(f"\n  {'Config':>30s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}")
    print(f"  {'-'*30}  {'-'*7}  {'-'*7}  {'-'*7}")

    sharpes = []
    for name, sig_fn in configs:
        signals = {sym: sig_fn(daily) for sym, daily in daily_data.items()}
        bt = portfolio_backtest(
            signals=signals, daily_bars=daily_data,
            initial_capital=INITIAL_CAPITAL, **SYSTEM_CONFIG,
        )
        s = bt["stats"]
        sharpes.append(s["sharpe"])
        marker = " ← base" if "10/100" in name and "252" in name else ""
        print(f"  {name:>30s}  {s['sharpe']:>7.3f}  {s['cagr_pct']:>6.1f}%  {s['max_dd_pct']:>6.1f}%{marker}")

    print(f"\n  Sharpe range: {min(sharpes):.3f} - {max(sharpes):.3f}")
    print(f"  Sharpe std: {np.std(sharpes):.3f}")
    if np.std(sharpes) < 0.2:
        print("  → ROBUST: Low sensitivity to parameter perturbation")
    else:
        print("  → SENSITIVE: Performance varies with parameters")


def signal_ema_custom(df, fast, slow):
    from src.signals import ma_crossover
    return ma_crossover(df, fast, slow, "ema")


def tsmom_custom(df, lookback):
    from src.signals import tsmom
    return tsmom(df, lookback)


def _blend(s1, s2):
    avg = (s1 + s2) / 2.0
    result = pd.Series(0.0, index=s1.index)
    result[avg > 0] = 1.0
    result[avg < 0] = -1.0
    return result


def crisis_alpha_analysis(full_bt, spy_daily):
    """Analyze strategy performance during equity drawdowns."""
    print("\n" + "=" * 60)
    print("4. CRISIS ALPHA ANALYSIS")
    print("=" * 60)

    equity = full_bt["equity"]
    strat_returns = full_bt["returns"]

    # SPY returns aligned to strategy dates
    spy_close = spy_daily["close"]
    spy_returns = spy_close.pct_change()

    # Align
    common = strat_returns.index.intersection(spy_returns.index)
    if len(common) == 0:
        # Try without tz
        strat_ret_notz = strat_returns.copy()
        strat_ret_notz.index = strat_ret_notz.index.tz_localize(None) if strat_ret_notz.index.tz is None else strat_ret_notz.index.tz_convert(None)
        spy_ret_notz = spy_returns.copy()
        spy_ret_notz.index = spy_ret_notz.index.tz_localize(None) if spy_ret_notz.index.tz is None else spy_ret_notz.index.tz_convert(None)
        common = strat_ret_notz.index.intersection(spy_ret_notz.index)
        s_ret = strat_ret_notz.reindex(common).fillna(0)
        sp_ret = spy_ret_notz.reindex(common).fillna(0)
    else:
        s_ret = strat_returns.reindex(common).fillna(0)
        sp_ret = spy_returns.reindex(common).fillna(0)

    # Overall correlation
    overall_corr = s_ret.corr(sp_ret)
    print(f"\n  Overall correlation with SPY: {overall_corr:.3f}")

    # SPY drawdown periods
    spy_eq = (1 + sp_ret).cumprod()
    spy_peak = spy_eq.cummax()
    spy_dd = (spy_eq - spy_peak) / spy_peak

    # Conditional performance during SPY drawdowns
    dd_thresholds = [0.05, 0.10, 0.15, 0.20]
    print(f"\n  {'SPY DD Threshold':>18s}  {'Days':>6s}  {'Strat Ann Ret':>14s}  {'Strat Sharpe':>13s}  {'Corr':>6s}")
    print(f"  {'-'*18}  {'-'*6}  {'-'*14}  {'-'*13}  {'-'*6}")

    for thresh in dd_thresholds:
        crisis_mask = spy_dd < -thresh
        crisis_days = crisis_mask.sum()
        if crisis_days < 10:
            continue
        crisis_strat_ret = s_ret[crisis_mask]
        crisis_spy_ret = sp_ret[crisis_mask]

        ann_ret = crisis_strat_ret.mean() * 252
        sharpe = crisis_strat_ret.mean() / crisis_strat_ret.std() * np.sqrt(252) if crisis_strat_ret.std() > 0 else 0
        corr = crisis_strat_ret.corr(crisis_spy_ret)

        print(f"  SPY DD > {thresh*100:.0f}%{' ':>{12-len(str(int(thresh*100)))}s}  {crisis_days:>6d}  {ann_ret*100:>13.1f}%  {sharpe:>13.3f}  {corr:>5.3f}")

    # Specific crisis periods
    print("\n  Specific Crisis Performance:")
    crises = {
        "COVID Crash (Feb-Mar 2020)":  ("2020-02-19", "2020-03-23"),
        "COVID Recovery (Mar-Jun 2020)": ("2020-03-23", "2020-06-08"),
        "2022 Rate Shock (Jan-Oct)": ("2022-01-03", "2022-10-12"),
        "2025 Tariff Sell-off": ("2025-02-19", "2025-03-13"),
    }

    for crisis_name, (start, end) in crises.items():
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end)
        # Handle tz-aware index
        if s_ret.index.tz is not None:
            start_dt = start_dt.tz_localize(s_ret.index.tz)
            end_dt = end_dt.tz_localize(s_ret.index.tz)
        mask = (s_ret.index >= start_dt) & (s_ret.index <= end_dt)
        if mask.sum() < 5:
            continue
        period_ret = s_ret[mask]
        cum_ret = (1 + period_ret).prod() - 1
        spy_cum = (1 + sp_ret[mask]).prod() - 1
        print(f"    {crisis_name:>35s}: Strat={cum_ret*100:>+6.1f}%  SPY={spy_cum*100:>+6.1f}%")


def vol_target_scaling(daily_data):
    """Test different vol targets to show scaling potential."""
    print("\n" + "=" * 60)
    print("5. VOL TARGET SCALING")
    print("=" * 60)

    trend_fn = BLEND_SIGNALS["BL-FS"]["fn"]
    signals = {sym: trend_fn(daily) for sym, daily in daily_data.items()}

    print(f"\n  {'Vol Target':>11s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}  {'Calmar':>7s}  {'RealVol':>8s}  {'Final $':>10s}")
    print(f"  {'-'*11}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*8}  {'-'*10}")

    for vt in [0.08, 0.10, 0.12, 0.15, 0.20, 0.25]:
        config = SYSTEM_CONFIG.copy()
        config["portfolio_vol_target"] = vt
        bt = portfolio_backtest(
            signals=signals, daily_bars=daily_data,
            initial_capital=INITIAL_CAPITAL, **config,
        )
        s = bt["stats"]
        print(f"  {vt*100:>10.0f}%  {s['sharpe']:>7.3f}  {s['cagr_pct']:>6.1f}%  {s['max_dd_pct']:>6.1f}%  {s['calmar']:>7.3f}  {s['realized_vol_pct']:>7.1f}%  ${s['final_equity']:>9,.0f}")


def main():
    t0 = time.time()
    daily_data, spy_daily = load_data()

    # Full system run
    print("\n" + "=" * 60)
    print("INTEGRATED SYSTEM: Fast+Slow Trend on 6 Futures")
    print("=" * 60)
    full_bt = run_full_system(daily_data)
    s = full_bt["stats"]
    print(f"\n  Sharpe: {s['sharpe']:.3f}")
    print(f"  CAGR:   {s['cagr_pct']:.1f}%")
    print(f"  MaxDD:  {s['max_dd_pct']:.1f}%")
    print(f"  Calmar: {s['calmar']:.3f}")
    print(f"  Return: {s['total_return_pct']:.1f}%")
    print(f"  Final:  ${s['final_equity']:,.0f}")

    # 1. Regime analysis
    regime_df = regime_analysis(daily_data)

    # 2. Walk-forward
    is_sharpes, oos_sharpes = walk_forward_test(daily_data)

    # 3. Parameter sensitivity
    parameter_sensitivity(daily_data)

    # 4. Crisis alpha
    crisis_alpha_analysis(full_bt, spy_daily)

    # 5. Vol target scaling
    vol_target_scaling(daily_data)

    # ── Final Report ──
    print("\n" + "=" * 60)
    print("SPRINT 7 FINAL SYSTEM REPORT")
    print("=" * 60)

    print(f"""
  ┌────────────────────────────────────────────────────┐
  │  TREND FUTURES — INTEGRATED SYSTEM                 │
  ├────────────────────────────────────────────────────┤
  │  Signal:     Fast+Slow (EMA 10/100 + TSMOM 252d)  │
  │  Universe:   ES, NQ, ZN, GC, CL, 6E               │
  │  Vol Target: 12%  │  Allocation: Equal Weight      │
  │  Rebalance:  Weekly  │  Vol Est: ATR(20)           │
  ├────────────────────────────────────────────────────┤
  │  Sharpe:  {s['sharpe']:.3f}  │  CAGR:    {s['cagr_pct']:>5.1f}%              │
  │  Max DD:  {s['max_dd_pct']:>5.1f}%  │  Calmar:  {s['calmar']:.3f}              │
  │  Return:  {s['total_return_pct']:>5.1f}%  │  Final:   ${s['final_equity']:>9,.0f}        │
  └────────────────────────────────────────────────────┘
    """)

    # Save
    regime_df.to_csv("data/sprint7_regime_results.csv", index=False)

    elapsed = time.time() - t0
    print(f"Completed in {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
