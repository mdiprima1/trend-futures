"""
Casino V1 — Bet Engine

Processes signals through triple barrier (profit target / stop loss / time limit).
Each signal becomes a "bet" with a defined outcome: win, loss, or scratch.
"""
import numpy as np
import pandas as pd


def run_bets(
    df: pd.DataFrame,
    signals: pd.Series,
    pt_atr_mult: float = 1.5,
    sl_atr_mult: float = 1.0,
    max_bars: int = 60,
    atr_period: int = 14,
) -> pd.DataFrame:
    """
    Process signals through triple barrier.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV data (1-min or any timeframe).
    signals : pd.Series
        +1 (long signal), -1 (short signal), 0 (no signal). Same index as df.
    pt_atr_mult : float
        Profit target as multiple of ATR.
    sl_atr_mult : float
        Stop loss as multiple of ATR.
    max_bars : int
        Maximum bars to hold before forced exit (time barrier).
    atr_period : int
        ATR lookback period.

    Returns
    -------
    pd.DataFrame with columns:
        entry_time, exit_time, direction, entry_price, exit_price,
        atr_at_entry, pt_price, sl_price, result (win/loss/scratch),
        pnl_points, bars_held
    """
    # Compute ATR
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr_series = tr.rolling(atr_period).mean()

    # Find entry points (signal != 0)
    entry_mask = signals != 0
    entry_indices = df.index[entry_mask]

    bets = []
    last_exit_idx = -1  # Don't enter while in a trade

    for entry_time in entry_indices:
        entry_loc = df.index.get_loc(entry_time)

        # Skip if we're still in a previous trade
        if entry_loc <= last_exit_idx:
            continue

        direction = int(signals.loc[entry_time])
        entry_price = float(df.loc[entry_time, "close"])
        entry_atr = float(atr_series.loc[entry_time]) if not pd.isna(atr_series.loc[entry_time]) else 0

        if entry_atr <= 0:
            continue

        # Set barriers
        if direction == 1:  # Long
            pt_price = entry_price + pt_atr_mult * entry_atr
            sl_price = entry_price - sl_atr_mult * entry_atr
        else:  # Short
            pt_price = entry_price - pt_atr_mult * entry_atr
            sl_price = entry_price + sl_atr_mult * entry_atr

        # Scan forward for barrier touch
        max_exit = min(entry_loc + max_bars, len(df) - 1)
        exit_price = None
        exit_time = None
        result = "scratch"
        bars_held = 0

        for j in range(entry_loc + 1, max_exit + 1):
            bar_high = float(df.iloc[j]["high"])
            bar_low = float(df.iloc[j]["low"])
            bar_close = float(df.iloc[j]["close"])
            bars_held = j - entry_loc

            if direction == 1:  # Long
                # Check stop first (conservative)
                if bar_low <= sl_price:
                    exit_price = sl_price
                    exit_time = df.index[j]
                    result = "loss"
                    break
                if bar_high >= pt_price:
                    exit_price = pt_price
                    exit_time = df.index[j]
                    result = "win"
                    break
            else:  # Short
                if bar_high >= sl_price:
                    exit_price = sl_price
                    exit_time = df.index[j]
                    result = "loss"
                    break
                if bar_low <= pt_price:
                    exit_price = pt_price
                    exit_time = df.index[j]
                    result = "win"
                    break

        # Time barrier (forced exit)
        if exit_price is None:
            exit_price = float(df.iloc[max_exit]["close"])
            exit_time = df.index[max_exit]
            bars_held = max_exit - entry_loc
            if direction == 1:
                result = "win" if exit_price > entry_price else "loss"
            else:
                result = "win" if exit_price < entry_price else "loss"

        # PnL in points
        if direction == 1:
            pnl_points = exit_price - entry_price
        else:
            pnl_points = entry_price - exit_price

        last_exit_idx = df.index.get_loc(exit_time)

        bets.append({
            "entry_time": entry_time,
            "exit_time": exit_time,
            "direction": "long" if direction == 1 else "short",
            "entry_price": entry_price,
            "exit_price": exit_price,
            "atr_at_entry": entry_atr,
            "pt_price": pt_price,
            "sl_price": sl_price,
            "result": result,
            "pnl_points": pnl_points,
            "pnl_atr": pnl_points / entry_atr if entry_atr > 0 else 0,
            "bars_held": bars_held,
        })

    return pd.DataFrame(bets) if bets else pd.DataFrame()


def compute_bet_stats(bets: pd.DataFrame, multiplier: float = 1.0, commission_rt: float = 2.10) -> dict:
    """
    Compute statistics for a set of bets.

    Parameters
    ----------
    bets : pd.DataFrame from run_bets()
    multiplier : float
        Contract multiplier for $ PnL.
    commission_rt : float
        Round-trip commission per contract.
    """
    if bets.empty:
        return {"n_bets": 0, "win_rate": 0, "profit_factor": 0, "ev_per_bet": 0}

    n = len(bets)
    wins = bets[bets["result"] == "win"]
    losses = bets[bets["result"] == "loss"]

    win_rate = len(wins) / n if n > 0 else 0

    # Dollar PnL (1 contract)
    bets_pnl = bets["pnl_points"] * multiplier - commission_rt
    avg_win_dollars = float((wins["pnl_points"] * multiplier - commission_rt).mean()) if len(wins) > 0 else 0
    avg_loss_dollars = float((losses["pnl_points"] * multiplier - commission_rt).mean()) if len(losses) > 0 else 0

    gross_profit = float(bets_pnl[bets_pnl > 0].sum()) if (bets_pnl > 0).any() else 0
    gross_loss = float(bets_pnl[bets_pnl < 0].sum()) if (bets_pnl < 0).any() else 0
    profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else 0

    ev_per_bet = float(bets_pnl.mean())
    total_pnl = float(bets_pnl.sum())

    # Time analysis
    n_days = (bets["entry_time"].iloc[-1] - bets["entry_time"].iloc[0]).days if n > 1 else 1
    n_years = max(n_days / 365, 0.1)
    bets_per_day = n / max(n_days, 1)
    bets_per_year = n / n_years

    avg_bars_held = float(bets["bars_held"].mean())

    return {
        "n_bets": n,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": round(win_rate * 100, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_win": round(avg_win_dollars, 2),
        "avg_loss": round(avg_loss_dollars, 2),
        "ev_per_bet": round(ev_per_bet, 2),
        "total_pnl": round(total_pnl, 2),
        "bets_per_day": round(bets_per_day, 2),
        "bets_per_year": round(bets_per_year, 0),
        "avg_bars_held": round(avg_bars_held, 1),
        "n_years": round(n_years, 1),
    }
