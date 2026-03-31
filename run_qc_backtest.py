#!/usr/bin/env python3
"""
Run the Trend Futures HRP strategy on QuantConnect.
Upload → Compile → Backtest → Extract results.
"""
import sys
import json
import time
import hashlib
from pathlib import Path
from typing import Optional

import requests

# ── QC API Config ──
USER_ID = "184399"
API_TOKEN = "cd2c781599607914f77cc08798e35cfcd9b4da52155b73efdbd21b3417367ca7"
BASE_URL = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29466018  # Reuse existing project


def get_auth():
    timestamp = str(int(time.time()))
    hash_hex = hashlib.sha256(f"{API_TOKEN}:{timestamp}".encode()).hexdigest()
    return (USER_ID, hash_hex), {"Timestamp": timestamp}


def api(method, endpoint, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            auth, headers = get_auth()
            if "headers" in kwargs:
                kwargs["headers"].update(headers)
            else:
                kwargs["headers"] = headers
            r = getattr(requests, method)(f"{BASE_URL}/{endpoint}", auth=auth, **kwargs)
            r.raise_for_status()
            data = r.json()
            if not data.get("success", True):
                print(f"  API error: {json.dumps(data, indent=2)}", file=sys.stderr)
                return None
            return data
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))
            else:
                print(f"  API failed after {max_retries} retries: {e}", file=sys.stderr)
                return None


def upload_code(project_id, code, filename="main.py"):
    resp = api("post", "files/update", json={
        "projectId": project_id, "name": filename, "content": code,
    })
    return resp is not None


def compile_project(project_id, timeout_secs=120):
    resp = api("post", "compile/create", json={"projectId": project_id})
    if resp is None:
        return None
    compile_id = resp["compileId"]
    state = resp["state"]
    for _ in range(timeout_secs // 2):
        if state == "BuildSuccess":
            return compile_id
        if state == "BuildError":
            print(f"  BUILD ERROR: {resp.get('logs', [])}", file=sys.stderr)
            return None
        time.sleep(2)
        resp = api("get", "compile/read", params={
            "projectId": project_id, "compileId": compile_id,
        })
        if resp is None:
            return None
        state = resp["state"]
    print("  Compile timeout", file=sys.stderr)
    return None


def run_backtest(project_id, compile_id, name, poll_interval=15, max_polls=480):
    bt = api("post", "backtests/create", json={
        "projectId": project_id, "compileId": compile_id, "backtestName": name,
    })
    if bt is None:
        return None
    backtest_id = bt.get("backtestId") or bt.get("backtest", {}).get("backtestId")
    if not backtest_id:
        print(f"  No backtest ID: {bt}", file=sys.stderr)
        return None
    print(f"  Backtest {backtest_id} started...")

    for i in range(max_polls):
        time.sleep(poll_interval)
        resp = api("get", "backtests/read", params={
            "projectId": project_id, "backtestId": backtest_id,
        })
        if resp is None:
            continue
        bt_data = resp.get("backtest", resp)
        progress = bt_data.get("progress", 0)
        completed = bt_data.get("completed", False)
        if i % 4 == 0:
            print(f"  Progress: {progress:.0%}")
        if completed:
            time.sleep(5)
            # Read final stats
            for retry in range(3):
                final = api("get", "backtests/read", params={
                    "projectId": project_id, "backtestId": backtest_id,
                })
                if final:
                    final_bt = final.get("backtest", final)
                    stats = final_bt.get("statistics", {})
                    if stats and len(stats) > 5:
                        return final_bt
                time.sleep(5)
            return bt_data

    print("  Backtest timeout", file=sys.stderr)
    return None


def main():
    print("=" * 60)
    print("QC BACKTEST: Trend Futures HRP 15%")
    print("=" * 60)

    # Read algorithm code
    code_path = Path(__file__).parent / "qc_trend_hrp.py"
    code = code_path.read_text()
    print(f"  Algorithm: {len(code)} characters")

    # Upload
    print("\n  Uploading...")
    if not upload_code(PROJECT_ID, code):
        print("  UPLOAD FAILED")
        return
    print("  Upload OK")

    # Compile
    print("\n  Compiling...")
    compile_id = compile_project(PROJECT_ID)
    if compile_id is None:
        print("  COMPILE FAILED")
        return
    print(f"  Compile OK: {compile_id}")

    # Backtest
    print("\n  Running backtest (this may take 10-30 minutes)...")
    bt_data = run_backtest(PROJECT_ID, compile_id, "TrendFutures-HRP-15pct")
    if bt_data is None:
        print("  BACKTEST FAILED")
        return

    # Extract results
    stats = bt_data.get("statistics", {})
    runtime = bt_data.get("runtimeStatistics", {})
    backtest_id = bt_data.get("backtestId", "unknown")

    print("\n" + "=" * 60)
    print("QC BACKTEST RESULTS")
    print("=" * 60)

    print(f"\n  Backtest ID: {backtest_id}")
    print(f"  URL: https://www.quantconnect.com/terminal/{PROJECT_ID}#open/{backtest_id}")

    if stats:
        print(f"\n  ── QC Statistics ──")
        for key in ["Sharpe Ratio", "Compounding Annual Return", "Drawdown",
                     "Total Orders", "Win Rate", "Net Profit",
                     "Probabilistic Sharpe Ratio"]:
            val = stats.get(key, "N/A")
            print(f"  {key:>30s}: {val}")

    # Yearly stats from runtime
    print(f"\n  ── Yearly Performance ──")
    print(f"  {'Year':>6s}  {'Sharpe':>7s}  {'Return':>8s}  {'MaxDD':>7s}  {'Equity':>12s}")
    for key in sorted(runtime.keys()):
        if key.startswith("y_"):
            year = key.replace("y_", "")
            parts = runtime[key].split("|")
            if len(parts) >= 4:
                print(f"  {year:>6s}  {parts[0]:>7s}  {parts[1]:>7s}%  {parts[2]:>6s}%  ${float(parts[3]):>11,.0f}")

    # Save full results
    result = {
        "backtest_id": backtest_id,
        "url": f"https://www.quantconnect.com/terminal/{PROJECT_ID}#open/{backtest_id}",
        "statistics": stats,
        "runtime_stats": runtime,
    }
    output_path = Path("data/qc_trend_hrp_results.json")
    output_path.write_text(json.dumps(result, indent=2))
    print(f"\n  Results saved to {output_path}")

    # Compare with local
    print(f"\n  ── Comparison: Local vs QC ──")
    print(f"  {'Metric':>20s}  {'Local':>10s}  {'QC':>10s}")
    print(f"  {'-'*20}  {'-'*10}  {'-'*10}")
    qc_sharpe = stats.get("Sharpe Ratio", "N/A")
    qc_cagr = stats.get("Compounding Annual Return", "N/A")
    qc_dd = stats.get("Drawdown", "N/A")
    print(f"  {'Sharpe':>20s}  {'2.656':>10s}  {qc_sharpe:>10s}")
    print(f"  {'CAGR':>20s}  {'63.4%':>10s}  {qc_cagr:>10s}")
    print(f"  {'Max DD':>20s}  {'8.4%':>10s}  {qc_dd:>10s}")


if __name__ == "__main__":
    main()
