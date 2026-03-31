#!/usr/bin/env python3
"""
Casino V1 — Sprint 4-5: Triple Barrier Optimization + Bet Catalog + Independence

1. Take top 8 setups from Sprints 1-3
2. Fine-tune PT/SL/time barriers for each
3. Build formal bet catalog with all statistics
4. Correlation/independence analysis between bets
5. Combined portfolio simulation
"""
import sys
import time
sys.path.insert(0, ".")
sys.path.insert(0, "casino-v1")

import numpy as np
import pandas as pd
from pathlib import Path

from casino_src.indicators import (
    rsi_mean_reversion, keltner_breakout, keltner_mean_reversion,
    ibs_signal, bollinger_mean_reversion, rsi, bollinger_bands,
    keltner_channel,
)
from casino_src.bet_engine import run_bets, compute_bet_stats

INSTRUMENTS = {
    "ES": {"multiplier": 50.0, "commission": 2.10},
    "NQ": {"multiplier": 20.0, "commission": 2.10},
    "CL": {"multiplier": 1000.0, "commission": 2.10},
}


def load_1min(symbol):
    cache = Path("data/cache")
    for f in sorted(cache.glob(f"{symbol}_1m_2018*")):
        df = pd.read_parquet(f)
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df = df.between_time("09:30", "15:59")
        return df
    return None


def resample(df, minutes):
    if minutes == 1: return df
    return df.resample(f"{minutes}min", label='right').agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["close"])


# ── Top 8 setups to optimize ──
def get_setups(daily_data):
    """Return dict of {name: (df, signals, multiplier, commission)}"""
    setups = {}

    # 1. NQ RSI(3) 30/70 on 60min
    df = resample(daily_data["NQ"], 60)
    sig = rsi_mean_reversion(df, 3, 30, 70)
    setups["NQ_RSI3_30_70_60m"] = (df, sig, 20.0, 2.10)

    # 2. NQ Keltner BO(30,2.0) on 60min
    df = resample(daily_data["NQ"], 60)
    sig = keltner_breakout(df, 30, 2.0)
    setups["NQ_KeltBO_30_2_60m"] = (df, sig, 20.0, 2.10)

    # 3. NQ IBS(0.15/0.85) on 60min
    df = resample(daily_data["NQ"], 60)
    sig = ibs_signal(df, 0.15, 0.85)
    setups["NQ_IBS_15_85_60m"] = (df, sig, 20.0, 2.10)

    # 4. CL Keltner MR(14,2.5) on 60min
    df = resample(daily_data["CL"], 60)
    sig = keltner_mean_reversion(df, 14, 2.5)
    setups["CL_KeltMR_14_25_60m"] = (df, sig, 1000.0, 2.10)

    # 5. NQ RSI+BB composite on 60min
    df = resample(daily_data["NQ"], 60)
    r = rsi(df["close"], 3)
    _, upper, lower = bollinger_bands(df, 20, 2.5)
    sig = pd.Series(0, index=df.index)
    sig[(r < 25) & (df["close"] < lower)] = 1
    sig[(r > 75) & (df["close"] > upper)] = -1
    setups["NQ_RSI3_BB25_60m"] = (df, sig, 20.0, 2.10)

    # 6. CL RSI+Keltner composite on 60min
    df = resample(daily_data["CL"], 60)
    r = rsi(df["close"], 3)
    _, upper, lower = keltner_channel(df, 20, 2.5)
    sig = pd.Series(0, index=df.index)
    sig[(r < 25) & (df["close"] < lower)] = 1
    sig[(r > 75) & (df["close"] > upper)] = -1
    setups["CL_RSI3_Kelt25_60m"] = (df, sig, 1000.0, 2.10)

    # 7. ES RSI(3) 30/70 on 60min (diversification from NQ)
    df = resample(daily_data["ES"], 60)
    sig = rsi_mean_reversion(df, 3, 30, 70)
    setups["ES_RSI3_30_70_60m"] = (df, sig, 50.0, 2.10)

    # 8. CL IBS(0.1/0.9) on 60min
    df = resample(daily_data["CL"], 60)
    sig = ibs_signal(df, 0.1, 0.9)
    setups["CL_IBS_10_90_60m"] = (df, sig, 1000.0, 2.10)

    return setups


def main():
    t0 = time.time()
    print("=" * 70)
    print("CASINO V1 — SPRINT 4-5: BARRIER OPTIMIZATION + BET CATALOG")
    print("=" * 70)

    # Load data
    daily_data = {}
    for sym in INSTRUMENTS:
        daily_data[sym] = load_1min(sym)
        print(f"  {sym}: {len(daily_data[sym]):,} bars")

    setups = get_setups(daily_data)
    print(f"\n  {len(setups)} setups to optimize")

    # ── Phase 1: Barrier Optimization ──
    print(f"\n{'='*70}")
    print("PHASE 1: BARRIER OPTIMIZATION")
    print(f"{'='*70}")

    PT_MULTS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
    SL_MULTS = [0.5, 0.75, 1.0, 1.5, 2.0]
    TIME_BARS = [15, 30, 45, 60, 90, 120]

    catalog = []

    for setup_name, (df, signals, mult, comm) in setups.items():
        n_signals = (signals != 0).sum()
        print(f"\n  {setup_name} ({n_signals} signals):")

        best_ev = -999
        best_config = None
        all_configs = []

        for pt in PT_MULTS:
            for sl in SL_MULTS:
                for tb in TIME_BARS:
                    bets = run_bets(df, signals, pt_atr_mult=pt, sl_atr_mult=sl,
                                     max_bars=tb, atr_period=14)
                    if len(bets) < 30:
                        continue

                    stats = compute_bet_stats(bets, multiplier=mult, commission_rt=comm)
                    stats["pt_mult"] = pt
                    stats["sl_mult"] = sl
                    stats["time_bars"] = tb
                    stats["setup"] = setup_name
                    all_configs.append(stats)

                    if stats["ev_per_bet"] > best_ev:
                        best_ev = stats["ev_per_bet"]
                        best_config = stats

        if best_config:
            b = best_config
            print(f"    Best: PT={b['pt_mult']}x SL={b['sl_mult']}x Time={b['time_bars']}bars"
                  f" → WR={b['win_rate']:.1f}% PF={b['profit_factor']:.2f}"
                  f" EV=${b['ev_per_bet']:.0f} {b['bets_per_day']:.2f}/day"
                  f" Total=${b['total_pnl']:,.0f}")

            # Also find best "frequent" config (>0.3 bets/day)
            frequent = [c for c in all_configs if c["ev_per_bet"] > 0 and c["bets_per_day"] > 0.3]
            if frequent:
                best_freq = max(frequent, key=lambda x: x["ev_per_bet"])
                if best_freq != best_config:
                    f = best_freq
                    print(f"    Best frequent (>0.3/day): PT={f['pt_mult']}x SL={f['sl_mult']}x Time={f['time_bars']}bars"
                          f" → WR={f['win_rate']:.1f}% PF={f['profit_factor']:.2f}"
                          f" EV=${f['ev_per_bet']:.0f} {f['bets_per_day']:.2f}/day")

            catalog.append(best_config)

    # ── Phase 2: Bet Catalog ──
    print(f"\n{'='*70}")
    print("PHASE 2: BET CATALOG")
    print(f"{'='*70}")

    catalog_df = pd.DataFrame(catalog).sort_values("ev_per_bet", ascending=False)

    print(f"\n  {'#':>2s}  {'Setup':>25s}  {'PT':>4s} {'SL':>4s} {'Bars':>4s}"
          f"  {'WR':>5s} {'PF':>5s} {'EV':>7s} {'B/d':>5s} {'Annual$':>9s}")
    print(f"  {'-'*2}  {'-'*25}  {'-'*4} {'-'*4} {'-'*4}"
          f"  {'-'*5} {'-'*5} {'-'*7} {'-'*5} {'-'*9}")

    for i, (_, r) in enumerate(catalog_df.iterrows()):
        annual = r["ev_per_bet"] * r["bets_per_day"] * 252
        print(f"  {i+1:>2d}  {r['setup']:>25s}  {r['pt_mult']:>4.1f} {r['sl_mult']:>4.1f} {r['time_bars']:>4.0f}"
              f"  {r['win_rate']:>4.1f}% {r['profit_factor']:>5.2f} ${r['ev_per_bet']:>6.0f} {r['bets_per_day']:>5.2f} ${annual:>8,.0f}")

    total_bets_day = catalog_df["bets_per_day"].sum()
    total_annual = sum(r["ev_per_bet"] * r["bets_per_day"] * 252 for _, r in catalog_df.iterrows())
    print(f"\n  Total bets/day: {total_bets_day:.2f}")
    print(f"  Total annual EV: ${total_annual:,.0f}")

    # ── Phase 3: Independence Analysis ──
    print(f"\n{'='*70}")
    print("PHASE 3: INDEPENDENCE ANALYSIS")
    print(f"{'='*70}")

    # For each setup, generate daily PnL series and compute correlations
    daily_pnls = {}
    for _, row in catalog_df.iterrows():
        setup_name = row["setup"]
        df, signals, mult, comm = setups[setup_name]
        bets = run_bets(df, signals, pt_atr_mult=row["pt_mult"],
                         sl_atr_mult=row["sl_mult"], max_bars=int(row["time_bars"]),
                         atr_period=14)
        if bets.empty:
            continue

        # Aggregate to daily PnL
        bets["exit_date"] = pd.to_datetime(bets["exit_time"]).dt.date
        daily = bets.groupby("exit_date")["pnl_points"].sum() * mult
        daily_pnls[setup_name] = daily

    if len(daily_pnls) > 1:
        pnl_df = pd.DataFrame(daily_pnls).fillna(0)
        corr = pnl_df.corr()

        print(f"\n  Correlation matrix (daily PnL):")
        # Short names
        short = {n: n.split("_")[0] + "_" + n.split("_")[1][:4] for n in corr.columns}
        print(f"  {'':>12s}", end="")
        for c in corr.columns:
            print(f"  {short[c]:>10s}", end="")
        print()
        for r_name in corr.index:
            print(f"  {short[r_name]:>12s}", end="")
            for c_name in corr.columns:
                v = corr.loc[r_name, c_name]
                print(f"  {v:>10.3f}", end="")
            print()

        # Effective number of bets
        upper = corr.values[np.triu_indices_from(corr.values, k=1)]
        avg_corr = np.mean(np.abs(upper))
        effective_bets = len(corr) / (1 + (len(corr) - 1) * avg_corr)
        print(f"\n  Average |correlation|: {avg_corr:.3f}")
        print(f"  Nominal bets: {len(corr)}")
        print(f"  Effective independent bets: {effective_bets:.1f}")

    # ── Phase 4: Combined Portfolio Simulation ──
    print(f"\n{'='*70}")
    print("PHASE 4: COMBINED PORTFOLIO SIMULATION")
    print(f"{'='*70}")

    if len(daily_pnls) > 1:
        combined = pd.DataFrame(daily_pnls).fillna(0)
        total_daily = combined.sum(axis=1)

        initial = 1_000_000
        equity = initial + total_daily.cumsum()
        daily_ret = equity.pct_change().dropna()
        n_years = len(daily_ret) / 252

        sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
        cagr = (equity.iloc[-1] / initial) ** (1 / n_years) - 1 if n_years > 0.5 else 0
        peak = equity.cummax()
        max_dd = ((equity - peak) / peak).min()

        print(f"\n  Combined Portfolio (all {len(daily_pnls)} bet streams, 1 contract each):")
        print(f"  {'Sharpe':>10s}: {sharpe:.3f}")
        print(f"  {'CAGR':>10s}: {cagr*100:.1f}%")
        print(f"  {'Max DD':>10s}: {abs(max_dd)*100:.1f}%")
        print(f"  {'Total PnL':>10s}: ${total_daily.sum():,.0f}")
        print(f"  {'Final':>10s}: ${equity.iloc[-1]:,.0f}")
        print(f"  {'Bets/day':>10s}: {total_bets_day:.1f}")

        # Yearly
        print(f"\n  Yearly:")
        for year in range(2018, 2026):
            mask = equity.index.year == year if hasattr(equity.index, 'year') else pd.Series(False)
            # Use total_daily instead
            yr_mask = pd.Series(total_daily.index).apply(lambda x: x.year == year if hasattr(x, 'year') else False).values
            yr_pnl = total_daily.iloc[yr_mask].sum() if yr_mask.any() else 0
            print(f"    {year}: ${yr_pnl:>+10,.0f}")

    # Save
    catalog_df.to_csv("casino-v1/data/bet_catalog.csv", index=False)

    elapsed = time.time() - t0
    print(f"\nCompleted in {elapsed:.0f} seconds")


if __name__ == "__main__":
    main()
