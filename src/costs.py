"""
Transaction Cost Model — Sprint 3

Realistic cost modeling for futures trend following:
- Commission (IB rates)
- Bid-ask spread (typical for each instrument)
- Slippage (market impact, square-root model)
- Roll costs (contango/backwardation, per-instrument)

All costs are per-contract, one-way unless noted.
"""
import numpy as np
import pandas as pd

from src.config import CONTRACT_MULTIPLIERS


# ── Per-Instrument Cost Table ────────────────────────────────────────
# Sources: IB commission schedules, CME market data, practitioner estimates

COST_TABLE = {
    "ES": {
        "commission_per_side": 1.05,       # IB rate
        "spread_ticks": 0.25,              # 1 tick = $12.50 per contract
        "tick_size": 0.25,
        "avg_daily_volume": 1_500_000,     # Contracts/day (approximate)
        "roll_cost_bps": 0.5,              # Annualized roll cost in bps of notional
        "rolls_per_year": 4,               # Quarterly rolls
    },
    "NQ": {
        "commission_per_side": 1.05,
        "spread_ticks": 0.25,              # 1 tick = $5.00
        "tick_size": 0.25,
        "avg_daily_volume": 600_000,
        "roll_cost_bps": 0.5,
        "rolls_per_year": 4,
    },
    "ZN": {
        "commission_per_side": 0.76,
        "spread_ticks": 1.0,               # 1 tick = 1/64 point = $15.625
        "tick_size": 1.0 / 64,
        "avg_daily_volume": 1_200_000,
        "roll_cost_bps": 2.0,              # Rates roll costs higher (carry)
        "rolls_per_year": 4,
    },
    "GC": {
        "commission_per_side": 1.05,
        "spread_ticks": 1.0,               # 1 tick = $10.00
        "tick_size": 0.10,
        "avg_daily_volume": 250_000,
        "roll_cost_bps": 1.5,              # Gold contango
        "rolls_per_year": 6,               # Bi-monthly
    },
    "CL": {
        "commission_per_side": 1.05,
        "spread_ticks": 1.0,               # 1 tick = $10.00
        "tick_size": 0.01,
        "avg_daily_volume": 800_000,
        "roll_cost_bps": 3.0,              # Oil contango can be significant
        "rolls_per_year": 12,              # Monthly rolls
    },
    "6E": {
        "commission_per_side": 1.05,
        "spread_ticks": 1.0,               # 1 tick = $6.25
        "tick_size": 0.00005,
        "avg_daily_volume": 200_000,
        "roll_cost_bps": 1.0,              # Interest rate differential
        "rolls_per_year": 4,
    },
}


def cost_per_contract_one_way(symbol: str) -> float:
    """Total one-way cost per contract (commission + half spread)."""
    ct = COST_TABLE[symbol]
    multiplier = CONTRACT_MULTIPLIERS[symbol]
    commission = ct["commission_per_side"]
    spread_cost = ct["spread_ticks"] * ct["tick_size"] * multiplier * 0.5  # Half spread
    return commission + spread_cost


def cost_per_contract_round_trip(symbol: str) -> float:
    """Total round-trip cost per contract."""
    return 2 * cost_per_contract_one_way(symbol)


def market_impact_cost(symbol: str, n_contracts: float, participation_rate: float = 0.01) -> float:
    """
    Square-root market impact model.
    Impact = sigma * sqrt(n / ADV) * multiplier

    Parameters
    ----------
    symbol : str
    n_contracts : float
        Number of contracts traded.
    participation_rate : float
        Fraction of daily volume (default 1%).

    Returns
    -------
    float: estimated market impact cost in dollars.
    """
    ct = COST_TABLE[symbol]
    multiplier = CONTRACT_MULTIPLIERS[symbol]
    adv = ct["avg_daily_volume"]

    if adv <= 0 or n_contracts <= 0:
        return 0.0

    # Participation fraction
    participation = n_contracts / adv

    # Impact in ticks: roughly sqrt(participation) * spread
    impact_ticks = ct["spread_ticks"] * np.sqrt(participation / participation_rate)
    impact_dollars = impact_ticks * ct["tick_size"] * multiplier * n_contracts

    return impact_dollars


def annual_roll_cost(symbol: str, n_contracts: float, notional_per_contract: float) -> float:
    """
    Estimated annual roll cost.

    Parameters
    ----------
    symbol : str
    n_contracts : float
        Average position size.
    notional_per_contract : float
        Price * multiplier.

    Returns
    -------
    float: annualized roll cost in dollars.
    """
    ct = COST_TABLE[symbol]
    roll_cost_per_roll = notional_per_contract * n_contracts * (ct["roll_cost_bps"] / 10000)
    # Plus commission and spread for the roll itself (close old + open new)
    roll_trade_cost = cost_per_contract_round_trip(symbol) * n_contracts * 2  # Two legs
    total_per_roll = roll_cost_per_roll + roll_trade_cost
    return total_per_roll * ct["rolls_per_year"]


def capacity_estimate(symbol: str, max_participation_pct: float = 1.0) -> dict:
    """
    Estimate capacity (max contracts and notional) for a given participation limit.

    Parameters
    ----------
    symbol : str
    max_participation_pct : float
        Max percentage of daily volume per trade.

    Returns
    -------
    dict with max_contracts, max_notional_usd
    """
    ct = COST_TABLE[symbol]
    multiplier = CONTRACT_MULTIPLIERS[symbol]
    max_contracts = int(ct["avg_daily_volume"] * max_participation_pct / 100)

    # Approximate notional (use a rough typical price)
    typical_prices = {"ES": 5000, "NQ": 18000, "ZN": 110, "GC": 2500, "CL": 75, "6E": 1.10}
    price = typical_prices.get(symbol, 100)
    max_notional = max_contracts * price * multiplier

    return {
        "symbol": symbol,
        "adv": ct["avg_daily_volume"],
        "max_contracts": max_contracts,
        "max_notional_usd": max_notional,
        "participation_pct": max_participation_pct,
    }


def compute_turnover_stats(signal: pd.Series, contracts: pd.Series) -> dict:
    """
    Compute turnover statistics for a signal.

    Returns dict with: trades_per_year, avg_holding_days, annual_turnover_ratio
    """
    # Signal changes (entries and exits)
    changes = signal.diff().fillna(0)
    n_trades = (changes != 0).sum()
    n_years = len(signal) / 252

    trades_per_year = n_trades / n_years if n_years > 0 else 0

    # Average holding period
    holding_periods = []
    in_trade = False
    entry_idx = 0
    for i in range(len(signal)):
        if signal.iloc[i] != 0 and not in_trade:
            in_trade = True
            entry_idx = i
        elif signal.iloc[i] == 0 and in_trade:
            in_trade = False
            holding_periods.append(i - entry_idx)
        elif signal.iloc[i] != 0 and in_trade and i > 0 and signal.iloc[i] != signal.iloc[i - 1]:
            holding_periods.append(i - entry_idx)
            entry_idx = i

    avg_hold = np.mean(holding_periods) if holding_periods else 0

    # Turnover ratio: total contract changes / average position
    contract_changes = contracts.diff().abs().sum()
    avg_position = contracts.abs().mean()
    turnover_ratio = contract_changes / avg_position / n_years if avg_position > 0 and n_years > 0 else 0

    return {
        "trades_per_year": round(trades_per_year, 1),
        "avg_holding_days": round(avg_hold, 1),
        "annual_turnover_ratio": round(turnover_ratio, 2),
    }


def print_cost_table():
    """Print a formatted cost table for all instruments."""
    print(f"{'Symbol':>6s}  {'Comm RT':>8s}  {'Spread':>8s}  {'Total RT':>9s}  {'ADV':>10s}  {'Roll/yr':>8s}")
    print(f"{'------':>6s}  {'--------':>8s}  {'--------':>8s}  {'---------':>9s}  {'----------':>10s}  {'--------':>8s}")
    for sym in COST_TABLE:
        comm_rt = COST_TABLE[sym]["commission_per_side"] * 2
        spread = COST_TABLE[sym]["spread_ticks"] * COST_TABLE[sym]["tick_size"] * CONTRACT_MULTIPLIERS[sym]
        total_rt = cost_per_contract_round_trip(sym)
        adv = COST_TABLE[sym]["avg_daily_volume"]
        roll_bps = COST_TABLE[sym]["roll_cost_bps"]
        print(f"{sym:>6s}  ${comm_rt:>7.2f}  ${spread:>7.2f}  ${total_rt:>8.2f}  {adv:>10,d}  {roll_bps:>6.1f}bps")
