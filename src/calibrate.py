"""
Calibration: compare vectorbt ORB results against QuantConnect equity curve.

Loads the QC trial_winner.json equity curve, runs the same strategy locally,
and produces a comparison report.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# QC results path
QC_RESULTS_PATH = Path(__file__).parent.parent.parent / "Momentum Demo" / "ORB V10 Explorations" / "results" / "trial_winner.json"


def load_qc_equity_curve() -> pd.Series:
    """Parse QC equity curve from runtime stats (eq_xxx batches)."""
    with open(QC_RESULTS_PATH) as f:
        data = json.load(f)

    runtime = data["runtime_stats"]
    eq_count = int(runtime.get("eq_count", "0"))

    dates = []
    vals = []
    for i in range(eq_count):
        key = f"eq_{i:03d}"
        batch_str = runtime.get(key, "")
        for entry in batch_str.split("|"):
            parts = entry.split(":")
            if len(parts) == 2:
                try:
                    dt = pd.Timestamp(parts[0])
                    eq = float(parts[1])
                    dates.append(dt)
                    vals.append(eq)
                except (ValueError, TypeError):
                    continue

    equity = pd.Series(vals, index=pd.DatetimeIndex(dates), name="qc_equity")
    return equity.sort_index()


def compare_equity_curves(local_equity: pd.Series, qc_equity: pd.Series) -> dict:
    """Compare local and QC equity curves."""
    # Align on common dates
    local_daily = local_equity.copy()
    local_daily.index = local_daily.index.normalize()

    qc_daily = qc_equity.copy()
    qc_daily.index = qc_daily.index.normalize()

    common = local_daily.index.intersection(qc_daily.index)
    if len(common) == 0:
        print("WARNING: No overlapping dates between local and QC equity curves")
        return {}

    local_aligned = local_daily.loc[common]
    qc_aligned = qc_daily.loc[common]

    # Correlation
    corr = local_aligned.corr(qc_aligned)

    # RMSE of returns
    local_ret = local_aligned.pct_change().dropna()
    qc_ret = qc_aligned.pct_change().dropna()
    common_ret = local_ret.index.intersection(qc_ret.index)
    rmse = np.sqrt(np.mean((local_ret.loc[common_ret] - qc_ret.loc[common_ret]) ** 2))

    # Final equity comparison
    local_final = local_aligned.iloc[-1]
    qc_final = qc_aligned.iloc[-1]
    pct_diff = (local_final - qc_final) / qc_final * 100

    # Sharpe comparison
    def sharpe(returns):
        if returns.std() == 0:
            return 0
        return returns.mean() / returns.std() * np.sqrt(252)

    local_sharpe = sharpe(local_ret)
    qc_sharpe = sharpe(qc_ret)

    # Max DD comparison
    def max_dd(equity_series):
        peak = equity_series.cummax()
        dd = (equity_series - peak) / peak
        return dd.min()

    local_mdd = max_dd(local_aligned)
    qc_mdd = max_dd(qc_aligned)

    report = {
        "equity_correlation": round(corr, 4),
        "return_rmse": round(rmse, 6),
        "local_final_equity": round(local_final, 0),
        "qc_final_equity": round(qc_final, 0),
        "final_equity_diff_pct": round(pct_diff, 2),
        "local_sharpe": round(local_sharpe, 3),
        "qc_sharpe": round(qc_sharpe, 3),
        "sharpe_diff": round(local_sharpe - qc_sharpe, 3),
        "local_max_dd": f"{abs(local_mdd) * 100:.1f}%",
        "qc_max_dd": f"{abs(qc_mdd) * 100:.1f}%",
    }

    return report


def print_calibration_report(local_stats: dict, comparison: dict):
    """Print a formatted calibration report."""
    print("=" * 60)
    print("CALIBRATION REPORT: vectorbt vs QuantConnect")
    print("=" * 60)

    print("\n── Local Strategy Stats ──")
    for k, v in local_stats.items():
        print(f"  {k:20s}: {v}")

    print("\n── QC Reference ──")
    print(f"  {'sharpe':20s}: 0.618")
    print(f"  {'cagr':20s}: 22.1%")
    print(f"  {'max_dd':20s}: 31.9%")
    print(f"  {'total_trades':20s}: 2166")
    print(f"  {'win_rate':20s}: 54%")

    if comparison:
        print("\n── Equity Curve Comparison ──")
        for k, v in comparison.items():
            print(f"  {k:25s}: {v}")

        # Grade the calibration
        # Primary metrics: equity correlation, CAGR match, final equity match
        # Sharpe can differ due to continuous contract construction (backward-ratio vs front-month)
        # which affects daily return volatility but not total return
        print("\n── Calibration Grade ──")
        corr = comparison.get("equity_correlation", 0)
        eq_diff = abs(comparison.get("final_equity_diff_pct", 999))

        if corr > 0.95 and eq_diff < 5:
            grade = "EXCELLENT"
        elif corr > 0.90 and eq_diff < 10:
            grade = "GOOD"
        elif corr > 0.80 and eq_diff < 20:
            grade = "ACCEPTABLE"
        else:
            grade = "NEEDS WORK"

        print(f"  Grade: {grade}")
        print(f"  (Equity correlation: {corr:.4f}, Final equity diff: {eq_diff:.1f}%)")
        if abs(comparison.get("sharpe_diff", 0)) > 0.2:
            print(f"  Note: Sharpe diff ({comparison['sharpe_diff']:.3f}) expected due to")
            print(f"  different continuous contract construction (Databento front-month")
            print(f"  vs QC backward-ratio) affecting daily return volatility.")

    print("=" * 60)
