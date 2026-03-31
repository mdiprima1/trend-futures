#!/usr/bin/env python3
"""
Run all 20 calibration tests locally and compare against QC results.
"""
import sys
sys.path.insert(0, ".")
import json
import pandas as pd
from pathlib import Path
from calibration.local_engine import run_backtest

# Load QC results
qc_results = json.loads(Path("calibration/results/qc_results.json").read_text())

# Test configs (must match QC tests exactly)
TESTS = [
    ("T01_SPY_BuyHold",     {"strategy": "buyhold", "ticker": "SPY"}),
    ("T02_QQQ_BuyHold",     {"strategy": "buyhold", "ticker": "QQQ"}),
    ("T03_SPY_SMA",         {"strategy": "sma_cross", "ticker": "SPY"}),
    ("T04_QQQ_SMA",         {"strategy": "sma_cross", "ticker": "QQQ"}),
    ("T05_IWM_SMA",         {"strategy": "sma_cross", "ticker": "IWM"}),
    ("T06_SPY_EMA",         {"strategy": "ema_cross", "ticker": "SPY"}),
    ("T07_QQQ_EMA",         {"strategy": "ema_cross", "ticker": "QQQ"}),
    ("T08_SPY_MACD",        {"strategy": "macd", "ticker": "SPY"}),
    ("T09_GLD_MACD",        {"strategy": "macd", "ticker": "GLD"}),
    ("T10_TLT_Momentum",    {"strategy": "momentum", "ticker": "TLT"}),
    ("T11_SPY_RSI_MR",      {"strategy": "rsi_mr", "ticker": "SPY"}),
    ("T12_QQQ_RSI_MR",      {"strategy": "rsi_mr", "ticker": "QQQ"}),
    ("T13_SPY_RSI_2to1",    {"strategy": "rsi_mr", "ticker": "SPY", "pt_mult": 2.0, "max_bars": 10}),
    ("T14_SPY_Boll_MR",     {"strategy": "boll_mr", "ticker": "SPY"}),
    ("T15_QQQ_Boll_MR",     {"strategy": "boll_mr", "ticker": "QQQ"}),
    ("T16_SPY_Keltner_MR",  {"strategy": "keltner_mr", "ticker": "SPY"}),
    ("T17_GLD_RSI_MR",      {"strategy": "rsi_mr", "ticker": "GLD"}),
    ("T18_TLT_RSI_MR",      {"strategy": "rsi_mr", "ticker": "TLT"}),
    ("T19_SPY_Momentum",    {"strategy": "momentum", "ticker": "SPY"}),
    ("T20_IWM_EMA",         {"strategy": "ema_cross", "ticker": "IWM"}),
]


def main():
    print("=" * 80)
    print("CALIBRATION: LOCAL vs QC COMPARISON")
    print("=" * 80)

    results = []

    for i, (name, params) in enumerate(TESTS):
        print(f"[{i+1:>2d}/{len(TESTS)}] {name:>20s}...", end=" ", flush=True)

        # Find matching QC result
        qc = None
        for qr in qc_results:
            if qr.get("name") == name and "error" not in qr:
                qc = qr
                break

        if qc is None:
            print("SKIP (no QC result)")
            continue

        # Run local
        try:
            strategy = params.pop("strategy")
            ticker = params.pop("ticker")
            local = run_backtest(strategy, ticker, **params)
            params["strategy"] = strategy
            params["ticker"] = ticker
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        # Compare
        qc_eq = float(qc["final_equity"])
        local_eq = local["final_equity"]
        qc_ret = float(qc["total_return"])
        local_ret = local["total_return"]
        qc_trades = int(qc["n_trades"])
        local_trades = local["n_trades"]

        eq_diff = local_eq - qc_eq
        eq_pct = eq_diff / qc_eq * 100 if qc_eq != 0 else 0
        ret_diff = local_ret - qc_ret
        trade_diff = local_trades - qc_trades

        grade = "PERFECT" if abs(eq_pct) < 0.5 else ("GOOD" if abs(eq_pct) < 2 else ("OK" if abs(eq_pct) < 5 else "FAIL"))

        results.append({
            "name": name, "strategy": params.get("strategy", strategy),
            "ticker": params.get("ticker", ticker),
            "qc_equity": qc_eq, "local_equity": local_eq,
            "eq_diff_pct": round(eq_pct, 3),
            "qc_return": qc_ret, "local_return": local_ret,
            "qc_trades": qc_trades, "local_trades": local_trades,
            "trade_diff": trade_diff, "grade": grade,
        })

        print(f"QC=${qc_eq:>11,.2f}  Local=${local_eq:>11,.2f}  Diff={eq_pct:>+7.3f}%  "
              f"Trades={qc_trades}/{local_trades}  [{grade}]")

    # Summary
    print(f"\n{'='*80}")
    print("CALIBRATION REPORT")
    print(f"{'='*80}")

    n_perfect = sum(1 for r in results if r["grade"] == "PERFECT")
    n_good = sum(1 for r in results if r["grade"] == "GOOD")
    n_ok = sum(1 for r in results if r["grade"] == "OK")
    n_fail = sum(1 for r in results if r["grade"] == "FAIL")

    print(f"\n  PERFECT (<0.5%):  {n_perfect}")
    print(f"  GOOD (<2%):       {n_good}")
    print(f"  OK (<5%):         {n_ok}")
    print(f"  FAIL (>5%):       {n_fail}")

    avg_diff = sum(abs(r["eq_diff_pct"]) for r in results) / len(results) if results else 0
    print(f"\n  Avg absolute equity diff: {avg_diff:.3f}%")

    # Detailed table
    print(f"\n  {'#':>3s}  {'Test':>20s}  {'QC Equity':>12s}  {'Local':>12s}  {'Diff%':>8s}  {'Trades':>10s}  {'Grade':>8s}")
    print(f"  {'-'*3}  {'-'*20}  {'-'*12}  {'-'*12}  {'-'*8}  {'-'*10}  {'-'*8}")
    for i, r in enumerate(results):
        print(f"  {i+1:>3d}  {r['name']:>20s}  ${r['qc_equity']:>11,.2f}  ${r['local_equity']:>11,.2f}"
              f"  {r['eq_diff_pct']:>+7.3f}%  {r['qc_trades']:>4d}/{r['local_trades']:<4d}  {r['grade']:>8s}")

    # Save
    Path("calibration/results/comparison.json").write_text(json.dumps(results, indent=2))
    print(f"\n  Results saved to calibration/results/comparison.json")

    # Final verdict
    if n_fail == 0 and avg_diff < 2:
        print(f"\n  VERDICT: CALIBRATION PASSED ✓")
    elif n_fail <= 2 and avg_diff < 5:
        print(f"\n  VERDICT: CALIBRATION ACCEPTABLE (minor issues)")
    else:
        print(f"\n  VERDICT: CALIBRATION NEEDS WORK")


if __name__ == "__main__":
    main()
