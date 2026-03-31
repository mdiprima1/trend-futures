#!/usr/bin/env python3
"""
Research V2: Full re-run on QC-exported prices.

Uses data/qc_prices/ as source of truth. These prices include natural
gaps (mapped=None days) which represent real execution reality.

Covers:
1. Signal landscape (all 18 signals × 10 instruments)
2. Best allocation and vol target
3. Final system with honest numbers
"""
import sys
import time
sys.path.insert(0, ".")

import numpy as np
import pandas as pd
from pathlib import Path

from src.signals import SIGNALS
from src.config import CONTRACT_MULTIPLIERS, COMMISSIONS


# ── Load QC Prices ───────────────────────────────────────────────────

def load_qc_prices():
    """Load all QC-exported daily OHLC."""
    qc_dir = Path("data/qc_prices")
    data = {}
    for f in sorted(qc_dir.glob("*.parquet")):
        sym = f.stem.replace("_daily", "")
        df = pd.read_parquet(f)
        if len(df) > 200:
            data[sym] = df
            print(f"  {sym}: {len(df)} bars, {df.index[0].strftime('%Y-%m-%d')} to {df.index[-1].strftime('%Y-%m-%d')}")
    return data


# ── Backtest Engine (QC-realistic) ───────────────────────────────────

def backtest_single(signal, daily, symbol, risk_bps=20):
    """
    Backtest one signal on one instrument using QC prices.
    Gaps in data = flat (no position). This IS the QC reality.
    """
    multiplier = CONTRACT_MULTIPLIERS.get(symbol, 1.0)
    commission_rt = COMMISSIONS.get(symbol, 2.10)
    initial = 500_000

    # Align signal to data (only trade on days we have prices)
    common = signal.index.intersection(daily.index)
    sig = signal.reindex(common).fillna(0)
    close = daily["close"].reindex(common)

    # ATR for sizing
    h, l, c = daily["high"], daily["low"], daily["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.rolling(20).mean().reindex(common)

    # Position: contracts = risk_$ / (ATR * multiplier)
    risk_dollar = initial * risk_bps / 10000
    raw_contracts = risk_dollar / (atr * multiplier)
    raw_contracts = raw_contracts.clip(0, 50).fillna(0)
    contracts = sig * raw_contracts

    # PnL
    price_change = close.diff()
    position = contracts.shift(1).fillna(0)
    gross_pnl = position * price_change * multiplier

    # Costs on position changes
    pos_change = contracts.diff().fillna(0).abs()
    costs = pos_change * commission_rt
    net_pnl = gross_pnl - costs

    equity = initial + net_pnl.cumsum()
    daily_ret = equity.pct_change().dropna()

    n_days = len(daily_ret)
    n_years = n_days / 252

    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 and n_days > 60 else 0
    final = equity.iloc[-1] if len(equity) > 0 else initial
    cagr = (final / initial) ** (1 / n_years) - 1 if n_years > 0.5 else 0
    peak = equity.cummax()
    max_dd = ((equity - peak) / peak).min() if len(equity) > 0 else 0

    # Trade count
    sig_changes = sig.diff().fillna(0)
    n_trades = (sig_changes != 0).sum()

    return {
        "sharpe": round(float(sharpe), 3),
        "cagr": round(float(cagr * 100), 2),
        "max_dd": round(float(abs(max_dd) * 100), 2),
        "n_trades": int(n_trades),
        "n_bars": len(common),
        "total_return": round(float((final / initial - 1) * 100), 2),
    }


def portfolio_backtest_qc(signals, daily_data, vol_target=0.15, weights=None):
    """
    Multi-instrument portfolio backtest on QC prices.
    Monthly rebalancing. Instruments only traded when they have data.
    """
    symbols = sorted(signals.keys())
    n = len(symbols)
    if weights is None:
        weights = {s: 1.0 / n for s in symbols}

    initial = 1_000_000

    # Union of all dates
    all_idx = daily_data[symbols[0]].index
    for s in symbols[1:]:
        all_idx = all_idx.union(daily_data[s].index)
    all_idx = all_idx.sort_values()

    # Pre-compute ATR
    inst_atr = {}
    for s in symbols:
        d = daily_data[s]
        h, l, c = d["high"], d["low"], d["close"]
        pc = c.shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        inst_atr[s] = tr.rolling(20).mean()

    equity = pd.Series(float(initial), index=all_idx)
    portfolio_value = float(initial)
    positions = {s: 0.0 for s in symbols}
    prev_date = None
    last_rebal_month = None

    for i, date in enumerate(all_idx):
        if i < 21:
            equity.iloc[i] = portfolio_value
            prev_date = date
            continue

        # PnL
        day_pnl = 0.0
        for s in symbols:
            if positions[s] == 0:
                continue
            d = daily_data[s]
            if date in d.index and prev_date is not None and prev_date in d.index:
                pc = d.loc[date, "close"] - d.loc[prev_date, "close"]
                day_pnl += positions[s] * pc * CONTRACT_MULTIPLIERS.get(s, 1.0)

        portfolio_value += day_pnl
        equity.iloc[i] = portfolio_value

        # Monthly rebalance
        month = f"{date.year}-{date.month:02d}"
        if month == last_rebal_month or date.day > 5 or (prev_date is not None and date.month == prev_date.month):
            prev_date = date
            continue
        last_rebal_month = month

        for s in symbols:
            d = daily_data[s]
            if date not in d.index:
                # No data today — flatten if holding
                if positions[s] != 0:
                    portfolio_value -= abs(positions[s]) * COMMISSIONS.get(s, 2.10)
                    positions[s] = 0.0
                continue

            # Signal
            sig_val = 0.0
            if date in signals[s].index:
                sig_val = float(signals[s].loc[date])
            else:
                prior = signals[s].index[signals[s].index <= date]
                if len(prior) > 0:
                    sig_val = float(signals[s].iloc[-1])
            if np.isnan(sig_val):
                sig_val = 0.0

            if sig_val == 0:
                if positions[s] != 0:
                    portfolio_value -= abs(positions[s]) * COMMISSIONS.get(s, 2.10)
                    positions[s] = 0.0
                continue

            # Size
            atr_val = inst_atr[s].get(date, None) if date in inst_atr[s].index else None
            if atr_val is None or np.isnan(atr_val) or atr_val <= 0:
                continue

            mult = CONTRACT_MULTIPLIERS.get(s, 1.0)
            risk = atr_val * mult
            if risk <= 0:
                continue

            w = weights.get(s, 1.0 / n)
            target_risk = portfolio_value * w * vol_target / np.sqrt(252)
            nc = min(int(target_risk / risk), 200)
            if nc < 1:
                continue

            target = int(sig_val) * nc
            diff = target - positions[s]
            if abs(diff) >= 1:
                portfolio_value -= abs(diff) * COMMISSIONS.get(s, 2.10)
                positions[s] = target

        equity.iloc[i] = portfolio_value
        prev_date = date

    # Stats
    dr = equity.pct_change().dropna()
    ny = len(dr) / 252
    sharpe = float(dr.mean() / dr.std() * np.sqrt(252)) if dr.std() > 0 else 0
    final = equity.iloc[-1]
    cagr = (final / initial) ** (1 / ny) - 1 if ny > 0.5 else 0
    peak = equity.cummax()
    max_dd = ((equity - peak) / peak).min()

    stats = {
        "sharpe": round(sharpe, 3),
        "cagr_pct": round(float(cagr * 100), 2),
        "max_dd_pct": round(float(abs(max_dd) * 100), 2),
        "total_return_pct": round(float((final / initial - 1) * 100), 2),
        "final_equity": round(float(final), 0),
    }

    return {"equity": equity, "stats": stats}


# ── Main Research ────────────────────────────────────────────────────

def main():
    t0 = time.time()

    print("=" * 60)
    print("RESEARCH V2: QC PRICES (HONEST NUMBERS)")
    print("=" * 60)

    daily_data = load_qc_prices()
    symbols = sorted(daily_data.keys())
    print(f"\nLoaded {len(daily_data)} instruments: {', '.join(symbols)}")

    # ══════════════════════════════════════════════════════════════
    # PHASE 1: Signal Landscape
    # ══════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("PHASE 1: SIGNAL LANDSCAPE (18 signals × 10 instruments)")
    print("=" * 60)

    all_results = []
    for sym in symbols:
        for sig_id, sig_info in SIGNALS.items():
            try:
                signal = sig_info["fn"](daily_data[sym])
                bt = backtest_single(signal, daily_data[sym], sym)
                bt["symbol"] = sym
                bt["signal_id"] = sig_id
                bt["signal_name"] = sig_info["name"]
                bt["family"] = sig_info["family"]
                bt["speed"] = sig_info["speed"]
                all_results.append(bt)
            except Exception as e:
                pass

    results_df = pd.DataFrame(all_results)

    # Portfolio-level ranking (avg Sharpe across instruments)
    portfolio = results_df.groupby(["signal_id", "signal_name", "family", "speed"]).agg(
        avg_sharpe=("sharpe", "mean"),
        avg_cagr=("cagr", "mean"),
        avg_max_dd=("max_dd", "mean"),
    ).sort_values("avg_sharpe", ascending=False).reset_index()

    print(f"\n  Top 10 Signals (avg Sharpe across {len(symbols)} instruments):")
    print(f"  {'Signal':>18s}  {'Family':>6s}  {'Speed':>10s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}")
    print(f"  {'-'*18}  {'-'*6}  {'-'*10}  {'-'*7}  {'-'*7}  {'-'*7}")
    for _, r in portfolio.head(10).iterrows():
        print(f"  {r['signal_name']:>18s}  {r['family']:>6s}  {r['speed']:>10s}  {r['avg_sharpe']:>7.3f}  {r['avg_cagr']:>6.1f}%  {r['avg_max_dd']:>6.1f}%")

    print(f"\n  Bottom 5:")
    for _, r in portfolio.tail(5).iterrows():
        print(f"  {r['signal_name']:>18s}  {r['family']:>6s}  {r['speed']:>10s}  {r['avg_sharpe']:>7.3f}  {r['avg_cagr']:>6.1f}%")

    # Best per instrument
    print(f"\n  Best Signal per Instrument:")
    for sym in symbols:
        sym_data = results_df[results_df["symbol"] == sym].sort_values("sharpe", ascending=False)
        if len(sym_data) > 0:
            best = sym_data.iloc[0]
            print(f"    {sym}: {best['signal_name']:>18s}  Sharpe={best['sharpe']:.3f}  CAGR={best['cagr']:.1f}%  Bars={best['n_bars']}")

    # Family comparison
    print(f"\n  Family Comparison:")
    for fam, group in portfolio.groupby("family"):
        print(f"    {fam}: avg Sharpe = {group['avg_sharpe'].mean():.3f}")

    # ══════════════════════════════════════════════════════════════
    # PHASE 2: Portfolio Construction
    # ══════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("PHASE 2: PORTFOLIO CONSTRUCTION")
    print("=" * 60)

    # Use top 5 signals from Phase 1
    top5_ids = portfolio.head(5)["signal_id"].tolist()
    print(f"  Top 5 signals: {top5_ids}")

    from src.signals import signal_MA04, signal_TS04

    def fast_slow(df):
        s1 = signal_MA04(df)
        s2 = signal_TS04(df)
        avg = (s1 + s2) / 2.0
        result = pd.Series(0.0, index=df.index)
        result[avg > 0] = 1.0
        result[avg < 0] = -1.0
        return result

    # Test configs
    print(f"\n  {'Config':>35s}  {'Sharpe':>7s}  {'CAGR':>7s}  {'MaxDD':>7s}  {'Return':>8s}")
    print(f"  {'-'*35}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*8}")

    for sig_name, sig_fn in [
        ("TSMOM(252d)", lambda df: SIGNALS["TS-04"]["fn"](df)),
        ("EMA(10/100)", lambda df: SIGNALS["MA-04"]["fn"](df)),
        ("Fast+Slow blend", fast_slow),
        ("SMA(50/200)", lambda df: SIGNALS["MA-03"]["fn"](df)),
    ]:
        for vt in [0.10, 0.15, 0.20]:
            signals = {s: sig_fn(daily_data[s]) for s in symbols}
            bt = portfolio_backtest_qc(signals, daily_data, vol_target=vt)
            s = bt["stats"]
            name = f"{sig_name} / {vt*100:.0f}%"
            print(f"  {name:>35s}  {s['sharpe']:>7.3f}  {s['cagr_pct']:>6.1f}%  {s['max_dd_pct']:>6.1f}%  {s['total_return_pct']:>7.1f}%")

    # ══════════════════════════════════════════════════════════════
    # PHASE 3: Yearly Breakdown of Best Config
    # ══════════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("PHASE 3: YEARLY BREAKDOWN (Best Config)")
    print("=" * 60)

    # Run the best config and show yearly
    signals = {s: fast_slow(daily_data[s]) for s in symbols}
    bt = portfolio_backtest_qc(signals, daily_data, vol_target=0.15)
    eq = bt["equity"]
    s = bt["stats"]

    print(f"\n  Fast+Slow / 15% vol / Equal Weight / Monthly")
    print(f"  Sharpe: {s['sharpe']:.3f}, CAGR: {s['cagr_pct']:.1f}%, MaxDD: {s['max_dd_pct']:.1f}%")
    print(f"  Total Return: {s['total_return_pct']:.1f}%, Final: ${s['final_equity']:,.0f}")

    print(f"\n  {'Year':>6s}  {'Return':>8s}  {'Equity':>12s}")
    print(f"  {'-'*6}  {'-'*8}  {'-'*12}")
    for year in range(2018, 2026):
        mask = eq.index.year == year
        yr = eq[mask]
        if len(yr) > 1:
            ret = (yr.iloc[-1] / yr.iloc[0] - 1) * 100
            print(f"  {year}  {ret:>+7.1f}%  ${yr.iloc[-1]:>11,.0f}")

    # Save
    results_df.to_csv("data/research_v2_signals.csv", index=False)
    portfolio.to_csv("data/research_v2_portfolio_ranking.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")
    print("Results saved to data/research_v2_*.csv")


if __name__ == "__main__":
    main()
