"""
Realistic Portfolio Backtester — Calibrated Against QuantConnect

Models the execution reality of futures trading:
1. Monthly rebalancing (1st trading day of month)
2. Contract rolls with flat periods (no position during roll gap)
3. Roll schedule per instrument (quarterly, monthly, etc.)
4. ATR-based vol targeting
5. Transaction costs (commission + spread)

Calibration target: match QC ZT-only backtest within 5%.
"""
import numpy as np
import pandas as pd
from src.config import CONTRACT_MULTIPLIERS, COMMISSIONS


# ── Roll Schedules ──
# For each instrument, which months do contracts expire?
# The system flattens at roll and re-enters next month.
ROLL_MONTHS = {
    # Quarterly: Mar, Jun, Sep, Dec → flat in those months, re-enter next
    "ES": [3, 6, 9, 12], "NQ": [3, 6, 9, 12], "RTY": [3, 6, 9, 12],
    "NKD": [3, 6, 9, 12],
    "ZT": [3, 6, 9, 12], "ZN": [3, 6, 9, 12], "ZB": [3, 6, 9, 12],
    "6E": [3, 6, 9, 12], "6B": [3, 6, 9, 12], "6J": [3, 6, 9, 12],
    "6A": [3, 6, 9, 12], "6C": [3, 6, 9, 12], "6S": [3, 6, 9, 12],
    "6N": [3, 6, 9, 12],
    # Monthly: all months
    "CL": list(range(1, 13)), "NG": list(range(1, 13)),
    "RB": list(range(1, 13)), "HO": list(range(1, 13)),
    # Bi-monthly: Feb, Apr, Jun, Aug, Oct, Dec
    "GC": [2, 4, 6, 8, 10, 12], "SI": [3, 5, 7, 9, 12],
    "HG": [3, 5, 7, 9, 12], "PL": [1, 4, 7, 10],
    # Ag: Mar, May, Jul, Sep, Dec (approx)
    "ZC": [3, 5, 7, 9, 12], "ZS": [1, 3, 5, 7, 8, 9, 11],
    "ZW": [3, 5, 7, 9, 12], "LE": [2, 4, 6, 8, 10, 12],
}

# How many trading days flat after a roll before re-entry?
# QC data shows ~33 days for quarterly instruments
# This is because: flatten end of month, skip next month, enter 1st of month after
ROLL_FLAT_DAYS = 25  # ~1 month flat after each roll


def _atr(df, period=20):
    """ATR in price points."""
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def realistic_backtest(
    signals: dict,
    daily_bars: dict,
    initial_capital: float = 1_000_000,
    vol_target: float = 0.15,
    atr_period: int = 20,
    max_contracts: int = 200,
    allocation: str = "equal_weight",
    weights: dict = None,
    roll_flat_days: int = ROLL_FLAT_DAYS,
) -> dict:
    """
    Run a realistic multi-instrument backtest with roll gaps.

    Parameters
    ----------
    signals : dict {symbol: pd.Series of +1/-1/0}
    daily_bars : dict {symbol: pd.DataFrame OHLCV}
    initial_capital : float
    vol_target : float (annualized)
    atr_period : int
    max_contracts : int per instrument
    allocation : str "equal_weight" or "custom"
    weights : dict {symbol: weight} if allocation="custom"
    roll_flat_days : int days flat after each roll

    Returns
    -------
    dict with: equity, stats, trades, roll_gaps
    """
    symbols = sorted(signals.keys())
    n = len(symbols)

    if weights is None:
        weights = {s: 1.0 / n for s in symbols}

    # Build common date index (union)
    all_idx = [daily_bars[s].index for s in symbols]
    common_idx = all_idx[0]
    for idx in all_idx[1:]:
        common_idx = common_idx.union(idx)
    common_idx = common_idx.sort_values()

    # Pre-compute ATR for each instrument
    inst_atr = {}
    for s in symbols:
        inst_atr[s] = _atr(daily_bars[s], atr_period)

    # Pre-compute roll blackout dates for each instrument
    roll_blackout = {}
    for s in symbols:
        blackout = set()
        roll_months = ROLL_MONTHS.get(s, [3, 6, 9, 12])
        bars = daily_bars[s]

        for year in range(bars.index[0].year, bars.index[-1].year + 1):
            for month in roll_months:
                # Find last trading day of the roll month
                month_mask = (bars.index.year == year) & (bars.index.month == month)
                month_dates = bars.index[month_mask]
                if len(month_dates) == 0:
                    continue
                roll_date = month_dates[-1]

                # Blackout: from roll_date for roll_flat_days trading days
                roll_idx = common_idx.get_loc(roll_date) if roll_date in common_idx else None
                if roll_idx is not None:
                    for j in range(roll_flat_days):
                        if roll_idx + j < len(common_idx):
                            blackout.add(common_idx[roll_idx + j])

        roll_blackout[s] = blackout

    # ── Simulation ──
    equity = pd.Series(initial_capital, index=common_idx, dtype=float)
    portfolio_value = initial_capital
    positions = {s: 0.0 for s in symbols}  # contracts held
    trades = []
    roll_gap_days = {s: 0 for s in symbols}

    prev_date = None

    for i, date in enumerate(common_idx):
        if i < atr_period + 1:
            equity.iloc[i] = portfolio_value
            continue

        # ── PnL from existing positions ──
        day_pnl = 0.0
        for s in symbols:
            if positions[s] == 0:
                continue
            bars = daily_bars[s]
            if date not in bars.index or prev_date not in bars.index:
                continue
            price_change = bars.loc[date, "close"] - bars.loc[prev_date, "close"]
            multiplier = CONTRACT_MULTIPLIERS.get(s, 1.0)
            day_pnl += positions[s] * price_change * multiplier

        portfolio_value += day_pnl
        equity.iloc[i] = portfolio_value

        # ── Monthly rebalance (1st-5th of month) ──
        is_new_month = prev_date is not None and date.month != prev_date.month
        is_early_month = date.day <= 5

        if not (is_new_month and is_early_month):
            prev_date = date
            continue

        # ── Process each instrument ──
        for s in symbols:
            bars = daily_bars[s]
            if date not in bars.index:
                continue

            # Check if in roll blackout
            if date in roll_blackout[s]:
                # Flatten if we have a position
                if positions[s] != 0:
                    # Cost of flattening
                    cost = abs(positions[s]) * COMMISSIONS.get(s, 2.10)
                    portfolio_value -= cost
                    trades.append({
                        "date": date, "symbol": s, "action": "ROLL_FLAT",
                        "contracts": positions[s], "cost": cost,
                    })
                    positions[s] = 0.0
                    roll_gap_days[s] += 1
                continue

            # Get signal
            sig_val = 0.0
            if date in signals[s].index:
                sig_val = signals[s].loc[date]
            elif len(signals[s]) > 0:
                # Use most recent signal
                prior = signals[s].index[signals[s].index <= date]
                if len(prior) > 0:
                    sig_val = signals[s].iloc[signals[s].index.get_loc(prior[-1])]

            if pd.isna(sig_val):
                sig_val = 0.0

            weight = weights.get(s, 1.0 / n)

            if sig_val == 0:
                if positions[s] != 0:
                    cost = abs(positions[s]) * COMMISSIONS.get(s, 2.10)
                    portfolio_value -= cost
                    positions[s] = 0.0
                continue

            # Position sizing
            atr_val = inst_atr[s].loc[date] if date in inst_atr[s].index else None
            if atr_val is None or pd.isna(atr_val) or atr_val <= 0:
                continue

            multiplier = CONTRACT_MULTIPLIERS.get(s, 1.0)
            risk_per_contract = atr_val * multiplier
            if risk_per_contract <= 0:
                continue

            target_daily_risk = portfolio_value * weight * vol_target / np.sqrt(252)
            n_contracts = int(target_daily_risk / risk_per_contract)
            n_contracts = min(abs(n_contracts), max_contracts)

            if n_contracts < 1:
                continue

            target = int(sig_val) * n_contracts
            diff = target - positions[s]

            if abs(diff) >= 1:
                cost = abs(diff) * COMMISSIONS.get(s, 2.10)
                portfolio_value -= cost
                equity.iloc[i] = portfolio_value
                trades.append({
                    "date": date, "symbol": s, "action": "TRADE",
                    "old_pos": positions[s], "new_pos": target,
                    "contracts_changed": diff, "cost": cost,
                })
                positions[s] = target

        prev_date = date

    # ── Compute Stats ──
    daily_ret = equity.pct_change().dropna()
    n_days = len(daily_ret)
    n_years = n_days / 252

    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0
    final = equity.iloc[-1]
    cagr = (final / initial_capital) ** (1 / n_years) - 1 if n_years > 0 else 0
    peak = equity.cummax()
    dd = (equity - peak) / peak
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0

    stats = {
        "sharpe": round(float(sharpe), 3),
        "cagr_pct": round(float(cagr * 100), 2),
        "max_dd_pct": round(float(abs(max_dd) * 100), 2),
        "calmar": round(float(calmar), 3),
        "total_return_pct": round(float((final / initial_capital - 1) * 100), 2),
        "final_equity": round(float(final), 0),
        "n_trades": len([t for t in trades if t["action"] == "TRADE"]),
        "n_rolls": len([t for t in trades if t["action"] == "ROLL_FLAT"]),
        "n_years": round(n_years, 1),
    }

    return {
        "equity": equity,
        "stats": stats,
        "trades": pd.DataFrame(trades) if trades else pd.DataFrame(),
    }
