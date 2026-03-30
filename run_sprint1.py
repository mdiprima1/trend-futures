#!/usr/bin/env python3
"""
Sprint 1: Signal Landscape & Baseline
Run all 18 signals across 6 instruments, produce comparison report.
"""
import sys
import time
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from src.data import fetch_futures_1m, build_daily_bars, fetch_spy_daily, fetch_vix_daily
from src.signals import SIGNALS, generate_all_signals
from src.backtest import backtest_signal

# ── Configuration ─────────────────────────────────────────────────────

INSTRUMENTS = ["ES", "NQ", "ZN", "GC", "CL", "6E"]
# Use 2018 as common start (ES/NQ cached from 2018, others from 2010)
START_DATE = "2018-01-01"
END_DATE = "2025-12-31"
INITIAL_CAPITAL = 500_000
RISK_PER_INSTRUMENT = 0.002  # 20 bps per instrument

# Try these date ranges in order when loading data
DATE_RANGES = [
    ("2018-01-01", "2025-12-31"),
    ("2010-06-07", "2025-12-31"),
]


def load_data():
    """Load minute bars and build daily bars for all instruments."""
    print("=" * 60)
    print("LOADING DATA")
    print("=" * 60)

    minute_data = {}
    daily_data = {}

    for sym in INSTRUMENTS:
        loaded = False
        for start, end in DATE_RANGES:
            try:
                m = fetch_futures_1m(sym, start, end)
                # Filter to common period (2018+)
                m = m[m.index >= pd.Timestamp("2018-01-01", tz="US/Eastern")]
                minute_data[sym] = m
                daily_data[sym] = build_daily_bars(m)
                print(f"  {sym}: {len(daily_data[sym])} daily bars (from {start})")
                loaded = True
                break
            except Exception:
                continue
        if not loaded:
            print(f"  {sym}: FAILED to load from any date range")

    return minute_data, daily_data


def run_all_signals(daily_data):
    """Generate signals and run backtests for all combinations."""
    print("\n" + "=" * 60)
    print("RUNNING SIGNAL SWEEP")
    print("=" * 60)

    all_results = []
    all_equities = {}  # {(symbol, signal_id): equity_series}

    total = len(daily_data) * len(SIGNALS)
    done = 0

    for sym, daily in daily_data.items():
        print(f"\n  {sym}:")
        sig_df = generate_all_signals(daily)

        for sig_id, sig_info in SIGNALS.items():
            signal = sig_df[sig_id]
            try:
                bt = backtest_signal(
                    signal, daily, sym,
                    initial_capital=INITIAL_CAPITAL,
                    risk_per_instrument=RISK_PER_INSTRUMENT,
                )
                stats = bt["stats"].copy()
                stats["signal_id"] = sig_id
                stats["signal_name"] = sig_info["name"]
                stats["signal_family"] = sig_info["family"]
                stats["signal_speed"] = sig_info["speed"]
                all_results.append(stats)
                all_equities[(sym, sig_id)] = bt["equity"]
                done += 1
            except Exception as e:
                print(f"    {sig_id}: ERROR - {e}")
                done += 1

        # Print top 3 for this instrument
        sym_results = [r for r in all_results if r["symbol"] == sym]
        sym_df = pd.DataFrame(sym_results).sort_values("sharpe", ascending=False)
        top3 = sym_df.head(3)[["signal_id", "signal_name", "sharpe", "cagr", "max_dd", "n_trades"]].to_string(index=False)
        print(f"    Top 3:\n{top3}")

    results_df = pd.DataFrame(all_results)
    return results_df, all_equities


def compute_portfolio_results(all_equities, daily_data):
    """Compute aggregate portfolio results per signal (equal weight across instruments)."""
    print("\n" + "=" * 60)
    print("PORTFOLIO AGGREGATION (Equal Weight)")
    print("=" * 60)

    portfolio_results = []

    for sig_id in SIGNALS:
        # Average equity curves across instruments (normalized to 1.0)
        curves = []
        for sym in daily_data:
            key = (sym, sig_id)
            if key in all_equities:
                eq = all_equities[key]
                normalized = eq / INITIAL_CAPITAL
                curves.append(normalized)

        if not curves:
            continue

        # Align and average
        combined = pd.concat(curves, axis=1).dropna()
        avg_equity = combined.mean(axis=1) * INITIAL_CAPITAL

        # Compute stats on the portfolio equity
        daily_ret = avg_equity.pct_change().dropna()
        n_years = len(daily_ret) / 252

        sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
        final = avg_equity.iloc[-1]
        cagr = (final / INITIAL_CAPITAL) ** (1 / n_years) - 1 if n_years > 0 else 0
        peak = avg_equity.cummax()
        max_dd = ((avg_equity - peak) / peak).min()
        calmar = cagr / abs(max_dd) if max_dd != 0 else 0

        portfolio_results.append({
            "signal_id": sig_id,
            "signal_name": SIGNALS[sig_id]["name"],
            "family": SIGNALS[sig_id]["family"],
            "speed": SIGNALS[sig_id]["speed"],
            "portfolio_sharpe": round(sharpe, 3),
            "portfolio_cagr": round(cagr * 100, 2),
            "portfolio_max_dd": round(abs(max_dd) * 100, 2),
            "portfolio_calmar": round(calmar, 3),
        })

    port_df = pd.DataFrame(portfolio_results).sort_values("portfolio_sharpe", ascending=False)
    return port_df


def compute_autocorrelation(daily_data):
    """Compute return autocorrelation per instrument at various lags."""
    print("\n" + "=" * 60)
    print("AUTOCORRELATION ANALYSIS")
    print("=" * 60)

    lags = [1, 5, 10, 21, 63, 126, 252]
    ac_results = []

    for sym, daily in daily_data.items():
        returns = daily["close"].pct_change().dropna()
        row = {"symbol": sym}
        for lag in lags:
            ac = returns.autocorr(lag)
            row[f"ac_lag_{lag}"] = round(ac, 4) if not pd.isna(ac) else 0.0
        ac_results.append(row)

    ac_df = pd.DataFrame(ac_results)
    print(ac_df.to_string(index=False))
    return ac_df


def compute_signal_correlations(all_equities, daily_data):
    """Compute correlation between signal returns across the portfolio."""
    print("\n" + "=" * 60)
    print("SIGNAL CORRELATION MATRIX (Portfolio Level)")
    print("=" * 60)

    # Build portfolio-level return series per signal
    sig_returns = {}
    for sig_id in SIGNALS:
        curves = []
        for sym in daily_data:
            key = (sym, sig_id)
            if key in all_equities:
                eq = all_equities[key]
                curves.append(eq.pct_change().dropna())
        if curves:
            combined = pd.concat(curves, axis=1).dropna()
            sig_returns[sig_id] = combined.mean(axis=1)

    if sig_returns:
        ret_df = pd.DataFrame(sig_returns).dropna()
        corr = ret_df.corr()

        # Print average correlation by family
        for family in ["MA", "TS", "BR", "MC", "SE"]:
            family_sigs = [s for s in SIGNALS if SIGNALS[s]["family"] == family]
            if len(family_sigs) > 1:
                family_corr = corr.loc[family_sigs, family_sigs]
                avg = family_corr.values[np.triu_indices_from(family_corr.values, k=1)].mean()
                print(f"  {family} intra-family avg correlation: {avg:.3f}")

        # Cross-family average
        all_vals = corr.values[np.triu_indices_from(corr.values, k=1)]
        print(f"  Overall avg signal correlation: {all_vals.mean():.3f}")

        return corr
    return None


def print_final_report(results_df, portfolio_df, ac_df):
    """Print the comprehensive Sprint 1 report."""
    print("\n" + "=" * 60)
    print("SPRINT 1 FINAL REPORT")
    print("=" * 60)

    # Best signals per instrument
    print("\n── Best Signal per Instrument (by Sharpe) ──")
    for sym in INSTRUMENTS:
        sym_data = results_df[results_df["symbol"] == sym].sort_values("sharpe", ascending=False)
        if len(sym_data) > 0:
            best = sym_data.iloc[0]
            print(f"  {sym}: {best['signal_name']:20s}  Sharpe={best['sharpe']:.3f}  CAGR={best['cagr']:.1f}%  MaxDD={best['max_dd']:.1f}%  Trades={best['n_trades']}")

    # Top 10 portfolio-level signals
    print("\n── Top 10 Signals (Portfolio Sharpe) ──")
    top10 = portfolio_df.head(10)
    print(top10[["signal_id", "signal_name", "family", "speed",
                  "portfolio_sharpe", "portfolio_cagr", "portfolio_max_dd"]].to_string(index=False))

    # Bottom 5 for context
    print("\n── Bottom 5 Signals (Portfolio Sharpe) ──")
    bottom5 = portfolio_df.tail(5)
    print(bottom5[["signal_id", "signal_name", "family", "speed",
                    "portfolio_sharpe", "portfolio_cagr", "portfolio_max_dd"]].to_string(index=False))

    # Family comparison
    print("\n── Family Comparison (Avg Portfolio Sharpe) ──")
    family_avg = portfolio_df.groupby("family")["portfolio_sharpe"].mean().sort_values(ascending=False)
    for fam, sharpe in family_avg.items():
        print(f"  {fam}: {sharpe:.3f}")

    # Speed comparison
    print("\n── Speed Comparison (Avg Portfolio Sharpe) ──")
    speed_avg = portfolio_df.groupby("speed")["portfolio_sharpe"].mean().sort_values(ascending=False)
    for speed, sharpe in speed_avg.items():
        print(f"  {speed}: {sharpe:.3f}")

    # Recommendations
    print("\n── Recommendations for Sprint 2 ──")
    top5 = portfolio_df.head(5)
    print(f"  Carry forward these signals:")
    for _, row in top5.iterrows():
        print(f"    {row['signal_id']} ({row['signal_name']}): Sharpe={row['portfolio_sharpe']:.3f}")

    # Check Valeyre hypothesis
    se_avg = portfolio_df[portfolio_df["family"] == "SE"]["portfolio_sharpe"].mean()
    all_avg = portfolio_df["portfolio_sharpe"].mean()
    print(f"\n  Valeyre check: Single EMA avg Sharpe = {se_avg:.3f} vs all signals avg = {all_avg:.3f}")
    if se_avg >= all_avg * 0.9:
        print("  → CONFIRMED: Single EMA captures most of the trend premium")
    else:
        print("  → NOT confirmed: More complex signals outperform single EMA")


def main():
    t0 = time.time()

    # Load data
    minute_data, daily_data = load_data()

    if len(daily_data) < 4:
        print("ERROR: Not enough instruments loaded. Check data downloads.")
        return

    # Run all signals
    results_df, all_equities = run_all_signals(daily_data)

    # Portfolio aggregation
    portfolio_df = compute_portfolio_results(all_equities, daily_data)

    # Autocorrelation analysis
    ac_df = compute_autocorrelation(daily_data)

    # Signal correlations
    corr_matrix = compute_signal_correlations(all_equities, daily_data)

    # Final report
    print_final_report(results_df, portfolio_df, ac_df)

    # Save results
    results_df.to_csv("data/sprint1_individual_results.csv", index=False)
    portfolio_df.to_csv("data/sprint1_portfolio_results.csv", index=False)
    ac_df.to_csv("data/sprint1_autocorrelation.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")
    print(f"Results saved to data/sprint1_*.csv")


if __name__ == "__main__":
    main()
