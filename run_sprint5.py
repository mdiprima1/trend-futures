#!/usr/bin/env python3
"""
Sprint 5: Machine Learning Enhancement (De Prado Pipeline)
Compare base signals vs ML-enhanced signals with meta-labeling.
"""
import sys
import time
sys.path.insert(0, ".")

import numpy as np
import pandas as pd

from src.data import fetch_futures_1m, build_daily_bars
from src.signals import SIGNALS
from src.regimes import BLEND_SIGNALS
from src.ml_pipeline import run_ml_pipeline, find_min_d
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

# Signals to enhance with ML
BASE_SIGNALS = {
    "TS-04": SIGNALS["TS-04"]["fn"],        # TSMOM(252d)
    "MA-04": SIGNALS["MA-04"]["fn"],        # EMA(10/100)
    "BL-FS": BLEND_SIGNALS["BL-FS"]["fn"],  # Fast+Slow blend (Sprint 4 winner)
    "BL-BAR": BLEND_SIGNALS["BL-BAR"]["fn"],# Barbell
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


def run_baselines(daily_data):
    """Run base signals without ML for comparison."""
    print("\n" + "=" * 60)
    print("BASELINES (No ML)")
    print("=" * 60)

    results = {}
    for sig_id, sig_fn in BASE_SIGNALS.items():
        signals = {sym: sig_fn(daily) for sym, daily in daily_data.items()}
        bt = portfolio_backtest(
            signals=signals, daily_bars=daily_data,
            initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG,
        )
        results[sig_id] = bt["stats"]
        s = bt["stats"]
        name = sig_id
        print(f"  {name:>8s}  Sharpe={s['sharpe']:.3f}  CAGR={s['cagr_pct']:.1f}%  MaxDD={s['max_dd_pct']:.1f}%")

    return results


def run_ml_enhancement(daily_data):
    """Run ML pipeline on each signal × instrument, then portfolio backtest."""
    print("\n" + "=" * 60)
    print("ML ENHANCEMENT (De Prado Pipeline)")
    print("=" * 60)

    results = {}
    all_importance = {}

    for sig_id, sig_fn in BASE_SIGNALS.items():
        print(f"\n  ── {sig_id} ──")
        enhanced_signals = {}
        sig_cv_scores = []
        sig_importances = []

        for sym, daily in daily_data.items():
            base_signal = sig_fn(daily)

            # Find optimal fracdiff d
            try:
                d = find_min_d(daily["close"])
            except Exception:
                d = 0.4

            # Run ML pipeline
            result = run_ml_pipeline(
                daily, base_signal, sym,
                fracdiff_d=d, pt_mult=2.0, sl_mult=1.0, max_hold=20,
            )

            enhanced_signals[sym] = result["enhanced_signal"]

            if result["status"] == "success":
                cv_mean = np.mean(result["cv_scores"]) if result["cv_scores"] else 0
                sig_cv_scores.append(cv_mean)
                if result["feature_importance"]:
                    sig_importances.append(result["feature_importance"])

                # Report
                n_labels = len(result["labels"])
                win_rate = (result["labels"]["label"] == 1).mean() * 100 if n_labels > 0 else 0
                avg_bet = result["bet_sizes"].mean() if "bet_sizes" in result else 0
                print(f"    {sym}: d={d:.2f}, labels={n_labels}, CV_acc={cv_mean:.1%}, win={win_rate:.0f}%, avg_bet={avg_bet:.2f}")
            else:
                print(f"    {sym}: {result['status']}")

        # Portfolio backtest with enhanced signals
        try:
            bt = portfolio_backtest(
                signals=enhanced_signals, daily_bars=daily_data,
                initial_capital=INITIAL_CAPITAL, **PORTFOLIO_CONFIG,
            )
            results[sig_id] = bt["stats"]

            # Average feature importance across instruments
            if sig_importances:
                avg_imp = {}
                for key in sig_importances[0]:
                    avg_imp[key] = np.mean([imp.get(key, 0) for imp in sig_importances])
                all_importance[sig_id] = avg_imp
        except Exception as e:
            print(f"    Portfolio backtest failed: {e}")

        if sig_cv_scores:
            print(f"    Avg CV accuracy: {np.mean(sig_cv_scores):.1%}")

    return results, all_importance


def main():
    t0 = time.time()
    daily_data = load_data()

    # Baselines
    baselines = run_baselines(daily_data)

    # ML-enhanced
    ml_results, all_importance = run_ml_enhancement(daily_data)

    # ── Comparison Report ──
    print("\n" + "=" * 60)
    print("SPRINT 5 RESULTS: Base vs ML-Enhanced")
    print("=" * 60)

    print(f"\n  {'Signal':>8s}  {'':>5s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}  {'Calmar':>7s}")
    print(f"  {'-'*8}  {'-'*5}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}")

    comparison = []
    for sig_id in BASE_SIGNALS:
        base = baselines.get(sig_id, {})
        ml = ml_results.get(sig_id, {})

        if base:
            print(f"  {sig_id:>8s}  {'base':>5s}  {base['sharpe']:>7.3f}  {base['cagr_pct']:>6.1f}%  {base['max_dd_pct']:>6.1f}%  {base['calmar']:>7.3f}")
        if ml:
            delta_sharpe = ml['sharpe'] - base.get('sharpe', 0)
            marker = "+" if delta_sharpe > 0 else ""
            print(f"  {sig_id:>8s}  {'ML':>5s}  {ml['sharpe']:>7.3f}  {ml['cagr_pct']:>6.1f}%  {ml['max_dd_pct']:>6.1f}%  {ml['calmar']:>7.3f}  ({marker}{delta_sharpe:.3f})")

        comparison.append({
            "signal_id": sig_id,
            "base_sharpe": base.get("sharpe", 0),
            "ml_sharpe": ml.get("sharpe", 0),
            "base_cagr": base.get("cagr_pct", 0),
            "ml_cagr": ml.get("cagr_pct", 0),
            "base_max_dd": base.get("max_dd_pct", 0),
            "ml_max_dd": ml.get("max_dd_pct", 0),
            "sharpe_delta": ml.get("sharpe", 0) - base.get("sharpe", 0),
        })

    # Feature importance
    if all_importance:
        print("\n── Top Features (Avg Importance Across Signals) ──")
        # Average across all signals
        all_features = set()
        for imp in all_importance.values():
            all_features.update(imp.keys())

        avg_all = {}
        for feat in all_features:
            vals = [imp.get(feat, 0) for imp in all_importance.values()]
            avg_all[feat] = np.mean(vals)

        sorted_feats = sorted(avg_all.items(), key=lambda x: x[1], reverse=True)
        for feat, imp in sorted_feats[:10]:
            print(f"  {feat:>20s}: {imp:.4f}")

    # Summary
    print("\n── Summary ──")
    comp_df = pd.DataFrame(comparison)
    avg_delta = comp_df["sharpe_delta"].mean()
    improved = (comp_df["sharpe_delta"] > 0).sum()
    total = len(comp_df)
    print(f"  Average Sharpe change: {avg_delta:+.3f}")
    print(f"  Signals improved: {improved}/{total}")

    if avg_delta > 0.05:
        print("  → ML enhancement provides meaningful improvement")
    elif avg_delta > 0:
        print("  → ML enhancement provides marginal improvement")
    else:
        print("  → ML enhancement does not improve over base signals")

    # Save
    comp_df.to_csv("data/sprint5_results.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
