#!/usr/bin/env python3
"""
Calibration Suite: Run 20 strategy variants on QC cloud and collect results.
Uses lean-cli to push, run, and collect.
"""
import hashlib, time, requests, json, sys, os
from pathlib import Path

USER_ID = '184399'
API_TOKEN = 'cd2c781599607914f77cc08798e35cfcd9b4da52155b73efdbd21b3417367ca7'
BASE_URL = 'https://www.quantconnect.com/api/v2'

# Create a dedicated QC project for calibration
PROJECT_NAME = "CalibrationSuite"


def api(method, endpoint, **kwargs):
    ts = str(int(time.time()))
    h = hashlib.sha256(f'{API_TOKEN}:{ts}'.encode()).hexdigest()
    kwargs.setdefault('headers', {}).update({'Timestamp': ts})
    r = getattr(requests, method)(f'{BASE_URL}/{endpoint}', auth=(USER_ID, h), **kwargs)
    return r.json()


def run_test(project_id, code, test_name, params):
    """Upload code with params, compile, run backtest, return results."""
    # Inject parameters into config
    config_content = json.dumps({
        "algorithm-language": "Python",
        "parameters": params,
    })

    # Upload main.py
    api('post', 'files/update', json={
        'projectId': project_id, 'name': 'main.py', 'content': code,
    })

    # Update config with parameters
    api('post', 'files/update', json={
        'projectId': project_id, 'name': 'config.json', 'content': config_content,
    })

    # Compile
    r = api('post', 'compile/create', json={'projectId': project_id})
    cid = r.get('compileId'); state = r.get('state', '')
    for _ in range(60):
        if state == 'BuildSuccess': break
        if state == 'BuildError':
            return {'error': f'Build error: {r.get("logs", [])}'}
        time.sleep(2)
        r = api('get', 'compile/read', params={'projectId': project_id, 'compileId': cid})
        state = r.get('state', '')

    if state != 'BuildSuccess':
        return {'error': 'Compile timeout'}

    # Run backtest
    r = api('post', 'backtests/create', json={
        'projectId': project_id, 'compileId': cid, 'backtestName': test_name,
    })
    bt_id = r.get('backtestId') or r.get('backtest', {}).get('backtestId')
    if not bt_id:
        return {'error': f'No backtest ID: {r}'}

    # Poll
    for i in range(240):
        time.sleep(10)
        r = api('get', 'backtests/read', params={'projectId': project_id, 'backtestId': bt_id})
        bt = r.get('backtest', r)
        if bt.get('completed'):
            time.sleep(3)
            r = api('get', 'backtests/read', params={'projectId': project_id, 'backtestId': bt_id})
            bt = r.get('backtest', r)
            stats = bt.get('statistics', {})
            runtime = bt.get('runtimeStatistics', {})
            return {
                'backtest_id': bt_id,
                'statistics': stats,
                'runtime_stats': runtime,
                'final_equity': runtime.get('final_equity', stats.get('End Equity', 'N/A')),
                'total_return': runtime.get('total_return', stats.get('Net Profit', 'N/A')),
                'n_trades': runtime.get('tr_count', stats.get('Total Orders', 'N/A')),
                'sharpe': stats.get('Sharpe Ratio', 'N/A'),
            }

    return {'error': 'Backtest timeout'}


# ── Test Definitions ──
TESTS = [
    # Trend strategies on different ETFs
    {"name": "T01_SPY_BuyHold",        "params": {"strategy": "buyhold", "ticker": "SPY", "start_year": "2020", "end_year": "2024"}},
    {"name": "T02_QQQ_BuyHold",        "params": {"strategy": "buyhold", "ticker": "QQQ", "start_year": "2020", "end_year": "2024"}},
    {"name": "T03_SPY_SMA_Cross",      "params": {"strategy": "sma_cross", "ticker": "SPY", "start_year": "2020", "end_year": "2024"}},
    {"name": "T04_QQQ_SMA_Cross",      "params": {"strategy": "sma_cross", "ticker": "QQQ", "start_year": "2020", "end_year": "2024"}},
    {"name": "T05_IWM_SMA_Cross",      "params": {"strategy": "sma_cross", "ticker": "IWM", "start_year": "2020", "end_year": "2024"}},
    {"name": "T06_SPY_EMA_Cross",      "params": {"strategy": "ema_cross", "ticker": "SPY", "start_year": "2020", "end_year": "2024"}},
    {"name": "T07_QQQ_EMA_Cross",      "params": {"strategy": "ema_cross", "ticker": "QQQ", "start_year": "2020", "end_year": "2024"}},
    {"name": "T08_SPY_MACD",           "params": {"strategy": "macd", "ticker": "SPY", "start_year": "2020", "end_year": "2024"}},
    {"name": "T09_GLD_MACD",           "params": {"strategy": "macd", "ticker": "GLD", "start_year": "2020", "end_year": "2024"}},
    {"name": "T10_TLT_MACD",           "params": {"strategy": "macd", "ticker": "TLT", "start_year": "2020", "end_year": "2024"}},
    {"name": "T11_SPY_Momentum",       "params": {"strategy": "momentum", "ticker": "SPY", "start_year": "2020", "end_year": "2024"}},
    {"name": "T12_QQQ_Momentum",       "params": {"strategy": "momentum", "ticker": "QQQ", "start_year": "2020", "end_year": "2024"}},
    # Mean reversion with barriers
    {"name": "T13_SPY_RSI_MR",         "params": {"strategy": "rsi_mr", "ticker": "SPY", "start_year": "2020", "end_year": "2024", "pt_mult": "1.5", "sl_mult": "1.0", "max_bars": "5"}},
    {"name": "T14_QQQ_RSI_MR",         "params": {"strategy": "rsi_mr", "ticker": "QQQ", "start_year": "2020", "end_year": "2024", "pt_mult": "1.5", "sl_mult": "1.0", "max_bars": "5"}},
    {"name": "T15_SPY_RSI_MR_2to1",    "params": {"strategy": "rsi_mr", "ticker": "SPY", "start_year": "2020", "end_year": "2024", "pt_mult": "2.0", "sl_mult": "1.0", "max_bars": "10"}},
    {"name": "T16_SPY_Boll_MR",        "params": {"strategy": "boll_mr", "ticker": "SPY", "start_year": "2020", "end_year": "2024", "pt_mult": "1.5", "sl_mult": "1.0", "max_bars": "5"}},
    {"name": "T17_QQQ_Boll_MR",        "params": {"strategy": "boll_mr", "ticker": "QQQ", "start_year": "2020", "end_year": "2024", "pt_mult": "1.5", "sl_mult": "1.0", "max_bars": "5"}},
    {"name": "T18_SPY_Keltner_MR",     "params": {"strategy": "keltner_mr", "ticker": "SPY", "start_year": "2020", "end_year": "2024", "pt_mult": "1.5", "sl_mult": "1.0", "max_bars": "5"}},
    {"name": "T19_GLD_RSI_MR",         "params": {"strategy": "rsi_mr", "ticker": "GLD", "start_year": "2020", "end_year": "2024", "pt_mult": "1.5", "sl_mult": "1.0", "max_bars": "5"}},
    {"name": "T20_TLT_RSI_MR",         "params": {"strategy": "rsi_mr", "ticker": "TLT", "start_year": "2020", "end_year": "2024", "pt_mult": "1.5", "sl_mult": "1.0", "max_bars": "5"}},
]


def main():
    print("=" * 70)
    print("CALIBRATION SUITE: 20 Tests on QC Cloud")
    print("=" * 70)

    # Create or find project
    r = api('post', 'projects/create', json={'name': PROJECT_NAME, 'language': 'Py'})
    if r.get('success'):
        project_id = r['projects'][0]['projectId']
        print(f"Created project {PROJECT_NAME} (ID: {project_id})")
    else:
        # Project might already exist, list and find
        r = api('get', 'projects/read')
        projects = r.get('projects', [])
        project_id = None
        for p in projects:
            if p['name'] == PROJECT_NAME:
                project_id = p['projectId']
                break
        if not project_id:
            print(f"Failed to create/find project: {r}")
            return
        print(f"Using existing project {PROJECT_NAME} (ID: {project_id})")

    # Read template code
    code = Path("calibration/qc_test_template.py").read_text()

    # Run all tests
    results = []
    for i, test in enumerate(TESTS):
        name = test['name']
        params = test['params']
        print(f"\n[{i+1}/{len(TESTS)}] {name} ({params['strategy']} on {params['ticker']})...", end=" ", flush=True)

        result = run_test(project_id, code, name, params)
        result['test_name'] = name
        result['params'] = params
        results.append(result)

        if 'error' in result:
            print(f"ERROR: {result['error']}")
        else:
            print(f"Done — Equity=${result['final_equity']}, Return={result['total_return']}%, "
                  f"Trades={result['n_trades']}")

    # Save results
    output = Path("calibration/results/qc_results.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(results, indent=2))

    # Summary table
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"  {'#':>3s}  {'Test':>25s}  {'Equity':>12s}  {'Return':>8s}  {'Trades':>7s}  {'Sharpe':>7s}")
    print(f"  {'-'*3}  {'-'*25}  {'-'*12}  {'-'*8}  {'-'*7}  {'-'*7}")
    for i, r in enumerate(results):
        if 'error' in r:
            print(f"  {i+1:>3d}  {r['test_name']:>25s}  {'ERROR':>12s}")
        else:
            print(f"  {i+1:>3d}  {r['test_name']:>25s}  ${float(r['final_equity']):>11,.2f}"
                  f"  {r['total_return']:>7s}%  {r['n_trades']:>7s}  {r['sharpe']:>7s}")

    print(f"\nResults saved to {output}")


if __name__ == "__main__":
    main()
