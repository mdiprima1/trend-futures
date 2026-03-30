"""
Vectorized Daily Backtest Engine — Sprint 1

Takes a signal series + daily bars + parameters.
Returns equity curve, trade log, and statistics.

Position sizing: inverse-volatility (ATR-based).
Costs: commission + 1-tick slippage per side.
"""
import numpy as np
import pandas as pd

from src.config import CONTRACT_MULTIPLIERS, COMMISSIONS


# Tick sizes for slippage modeling
TICK_SIZES = {
    "ES": 0.25,
    "NQ": 0.25,
    "ZN": 1 / 64,  # 1/64 of a point
    "GC": 0.10,
    "CL": 0.01,
    "6E": 0.00005,
}


def backtest_signal(
    signal: pd.Series,
    daily_bars: pd.DataFrame,
    symbol: str,
    initial_capital: float = 500_000,
    risk_per_instrument: float = 0.002,  # 20 bps of portfolio
    max_contracts: int = 20,
    atr_period: int = 20,
) -> dict:
    """
    Backtest a single signal on a single instrument.

    Parameters
    ----------
    signal : pd.Series
        Position signal: +1 (long), -1 (short), 0 (flat). Same index as daily_bars.
    daily_bars : pd.DataFrame
        Daily OHLCV with columns: open, high, low, close, volume.
    symbol : str
        Instrument symbol (ES, NQ, ZN, GC, CL, 6E).
    initial_capital : float
        Starting portfolio value.
    risk_per_instrument : float
        Target daily risk as fraction of portfolio (per instrument).
    max_contracts : int
        Maximum position size in contracts.
    atr_period : int
        ATR period for volatility estimation and position sizing.

    Returns
    -------
    dict with keys: equity, returns, trades, stats
    """
    multiplier = CONTRACT_MULTIPLIERS.get(symbol, 1.0)
    commission_rt = COMMISSIONS.get(symbol, 2.10)
    tick_size = TICK_SIZES.get(symbol, 0.01)
    slippage_per_side = tick_size  # 1 tick per side

    # Align signal to daily bars
    common_idx = signal.index.intersection(daily_bars.index)
    signal = signal.reindex(common_idx).fillna(0.0)
    bars = daily_bars.reindex(common_idx)

    # Compute ATR for position sizing
    high = bars["high"]
    low = bars["low"]
    close = bars["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()

    # ── Vectorized PnL computation ──
    # Position in contracts (inverse-vol sizing)
    # contracts = (portfolio_risk $) / (ATR * multiplier)
    # For simplicity in Sprint 1: use initial capital for sizing (no compounding)
    dollar_risk = initial_capital * risk_per_instrument
    raw_contracts = dollar_risk / (atr * multiplier)
    raw_contracts = raw_contracts.clip(0, max_contracts)
    contracts = (signal * raw_contracts).fillna(0.0)

    # Daily price change
    price_change = close.diff()

    # Daily PnL from position (marked to close)
    # Position is entered at today's close, P&L starts next day
    position_contracts = contracts.shift(1).fillna(0.0)
    gross_pnl = position_contracts * price_change * multiplier

    # Transaction costs: triggered on position changes
    position_change = contracts.diff().fillna(0.0).abs()
    # Each contract change: commission (half RT) + slippage per side
    cost_per_change = (commission_rt / 2) + (slippage_per_side * multiplier)
    total_costs = position_change * cost_per_change

    net_pnl = gross_pnl - total_costs

    # Equity curve
    equity = initial_capital + net_pnl.cumsum()

    # Daily returns
    returns = net_pnl / initial_capital  # Simple returns off initial capital

    # ── Extract trade log ──
    trades = _extract_trades(signal, close, contracts, multiplier, commission_rt, slippage_per_side)

    # ── Compute stats ──
    stats = _compute_stats(equity, returns, trades, initial_capital)
    stats["symbol"] = symbol
    stats["turnover_annual"] = _compute_turnover(position_change, contracts, len(common_idx))

    return {
        "equity": equity,
        "returns": returns,
        "trades": trades,
        "stats": stats,
        "signal": signal,
        "contracts": contracts,
    }


def _extract_trades(signal, close, contracts, multiplier, commission_rt, slippage):
    """Extract trade log from signal changes."""
    trades = []
    pos = 0.0
    entry_price = None
    entry_date = None
    entry_contracts = 0

    for i in range(len(signal)):
        new_pos = signal.iloc[i]
        if new_pos != pos:
            # Close existing position
            if pos != 0 and entry_price is not None:
                exit_price = close.iloc[i]
                direction = "long" if pos > 0 else "short"
                if direction == "long":
                    pnl_pts = exit_price - entry_price
                else:
                    pnl_pts = entry_price - exit_price
                pnl_dollars = pnl_pts * multiplier * abs(entry_contracts)
                cost = commission_rt * abs(entry_contracts) + slippage * multiplier * abs(entry_contracts) * 2
                trades.append({
                    "entry_date": entry_date,
                    "exit_date": signal.index[i],
                    "direction": direction,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "contracts": abs(entry_contracts),
                    "pnl_points": pnl_pts,
                    "pnl_dollars": pnl_dollars,
                    "cost": cost,
                    "net_pnl": pnl_dollars - cost,
                    "holding_days": (signal.index[i] - entry_date).days if entry_date else 0,
                })

            # Open new position
            if new_pos != 0:
                entry_price = close.iloc[i]
                entry_date = signal.index[i]
                entry_contracts = contracts.iloc[i]
            else:
                entry_price = None
                entry_date = None
                entry_contracts = 0

            pos = new_pos

    return pd.DataFrame(trades) if trades else pd.DataFrame()


def _compute_stats(equity, returns, trades, initial_capital):
    """Compute summary statistics."""
    daily_ret = returns.dropna()
    n_days = len(daily_ret)
    n_years = n_days / 252

    # Sharpe
    if daily_ret.std() > 0 and n_days > 30:
        sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252)
    else:
        sharpe = 0.0

    # CAGR
    final_eq = equity.iloc[-1] if len(equity) > 0 else initial_capital
    if n_years > 0 and final_eq > 0:
        cagr = (final_eq / initial_capital) ** (1 / n_years) - 1
    else:
        cagr = 0.0

    # Max drawdown
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    max_dd = drawdown.min() if len(drawdown) > 0 else 0.0

    # Calmar
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0.0

    # Trade stats
    n_trades = len(trades) if isinstance(trades, pd.DataFrame) and not trades.empty else 0
    if n_trades > 0:
        win_rate = (trades["net_pnl"] > 0).mean()
        avg_win = trades.loc[trades["net_pnl"] > 0, "net_pnl"].mean() if (trades["net_pnl"] > 0).any() else 0
        avg_loss = trades.loc[trades["net_pnl"] <= 0, "net_pnl"].mean() if (trades["net_pnl"] <= 0).any() else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        avg_hold = trades["holding_days"].mean()
    else:
        win_rate = 0
        avg_win = 0
        avg_loss = 0
        profit_factor = 0
        avg_hold = 0

    return {
        "sharpe": round(sharpe, 3),
        "cagr": round(cagr * 100, 2),
        "max_dd": round(abs(max_dd) * 100, 2),
        "calmar": round(calmar, 3),
        "n_trades": n_trades,
        "win_rate": round(win_rate * 100, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_win": round(avg_win, 0),
        "avg_loss": round(avg_loss, 0),
        "avg_hold_days": round(avg_hold, 1),
        "total_return": round((final_eq / initial_capital - 1) * 100, 2),
        "final_equity": round(final_eq, 0),
    }


def _compute_turnover(position_change, contracts, n_days):
    """Compute annualized turnover as fraction of average position."""
    avg_pos = contracts.abs().mean()
    if avg_pos > 0:
        total_change = position_change.sum()
        return round(total_change / avg_pos / n_days * 252, 2)
    return 0.0


def run_signal_sweep(
    daily_bars_dict: dict,
    signals_dict: dict,
    initial_capital: float = 500_000,
    risk_per_instrument: float = 0.002,
) -> pd.DataFrame:
    """
    Run all signals across all instruments.

    Parameters
    ----------
    daily_bars_dict : dict
        {symbol: daily_bars_df}
    signals_dict : dict
        {symbol: {signal_id: signal_series}}
    initial_capital : float
    risk_per_instrument : float

    Returns
    -------
    pd.DataFrame with one row per signal×instrument combination.
    """
    results = []

    for symbol, sig_dict in signals_dict.items():
        daily = daily_bars_dict[symbol]
        for sig_id, signal in sig_dict.items():
            try:
                bt = backtest_signal(
                    signal, daily, symbol,
                    initial_capital=initial_capital,
                    risk_per_instrument=risk_per_instrument,
                )
                row = bt["stats"].copy()
                row["signal_id"] = sig_id
                row["signal_name"] = signal.name if hasattr(signal, "name") else sig_id
                results.append(row)
            except Exception as e:
                print(f"  Error: {symbol}/{sig_id}: {e}")

    return pd.DataFrame(results)
