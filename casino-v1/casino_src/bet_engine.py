"""
Casino V1 — Bet Engine (v2)

Processes signals through triple barrier (profit target / stop loss / time limit).
Iterates bar-by-bar like QC's on_data — allows re-entry after any exit
if the signal persists. This matches QC's behavior of evaluating every bar.
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
    Process signals through triple barrier, bar by bar.
    Re-enters after any exit (time barrier, PT, SL) if signal persists.
    """
    # Compute ATR
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr_series = tr.rolling(atr_period).mean()

    bets = []

    # State machine
    in_trade = False
    direction = 0
    entry_price = 0.0
    entry_atr = 0.0
    pt_price = 0.0
    sl_price = 0.0
    bars_left = 0
    entry_time = None

    for i in range(len(df)):
        bar = df.iloc[i]
        bar_time = df.index[i]
        bar_close = float(bar["close"])
        bar_high = float(bar["high"])
        bar_low = float(bar["low"])
        sig = int(signals.iloc[i]) if i < len(signals) else 0

        atr_val = float(atr_series.iloc[i]) if not pd.isna(atr_series.iloc[i]) else 0

        # ── Manage active trade ──
        if in_trade:
            bars_left -= 1
            hit = False
            won = False

            if direction == 1:
                if bar_low <= sl_price:
                    hit = True; won = False
                    exit_price = sl_price
                elif bar_high >= pt_price:
                    hit = True; won = True
                    exit_price = pt_price
            else:
                if bar_high >= sl_price:
                    hit = True; won = False
                    exit_price = sl_price
                elif bar_low <= pt_price:
                    hit = True; won = True
                    exit_price = pt_price

            if bars_left <= 0 and not hit:
                hit = True
                exit_price = bar_close
                won = (bar_close - entry_price) * direction > 0

            if hit:
                if direction == 1:
                    pnl_points = exit_price - entry_price
                else:
                    pnl_points = entry_price - exit_price

                bets.append({
                    "entry_time": entry_time,
                    "exit_time": bar_time,
                    "direction": "long" if direction == 1 else "short",
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "atr_at_entry": entry_atr,
                    "pt_price": pt_price,
                    "sl_price": sl_price,
                    "result": "win" if won else "loss",
                    "pnl_points": pnl_points,
                    "pnl_atr": pnl_points / entry_atr if entry_atr > 0 else 0,
                    "bars_held": max_bars - bars_left if not hit else (max_bars - bars_left),
                })
                in_trade = False

                # DON'T continue — fall through to check for new entry on THIS bar
                # This allows re-entry after exit if signal persists
            else:
                continue  # Still in trade, skip to next bar

        # ── Check for new entry ──
        if sig == 0 or atr_val <= 0:
            continue

        # Enter new trade
        entry_price = bar_close
        entry_atr = atr_val
        entry_time = bar_time
        direction = sig
        bars_left = max_bars
        in_trade = True

        if direction == 1:
            pt_price = entry_price + pt_atr_mult * atr_val
            sl_price = entry_price - sl_atr_mult * atr_val
        else:
            pt_price = entry_price - pt_atr_mult * atr_val
            sl_price = entry_price + sl_atr_mult * atr_val

    return pd.DataFrame(bets) if bets else pd.DataFrame()


def compute_bet_stats(bets: pd.DataFrame, multiplier: float = 1.0, commission_rt: float = 2.10) -> dict:
    """Compute statistics for a set of bets."""
    if bets.empty:
        return {"n_bets": 0, "win_rate": 0, "profit_factor": 0, "ev_per_bet": 0}

    n = len(bets)
    wins = bets[bets["result"] == "win"]
    losses = bets[bets["result"] == "loss"]

    win_rate = len(wins) / n if n > 0 else 0

    bets_pnl = bets["pnl_points"] * multiplier - commission_rt
    avg_win = float((wins["pnl_points"] * multiplier - commission_rt).mean()) if len(wins) > 0 else 0
    avg_loss = float((losses["pnl_points"] * multiplier - commission_rt).mean()) if len(losses) > 0 else 0

    gross_profit = float(bets_pnl[bets_pnl > 0].sum()) if (bets_pnl > 0).any() else 0
    gross_loss = float(bets_pnl[bets_pnl < 0].sum()) if (bets_pnl < 0).any() else 0
    profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else 0

    ev_per_bet = float(bets_pnl.mean())
    total_pnl = float(bets_pnl.sum())

    n_days = (bets["entry_time"].iloc[-1] - bets["entry_time"].iloc[0]).days if n > 1 else 1
    n_years = max(n_days / 365, 0.1)
    bets_per_day = n / max(n_days, 1)

    return {
        "n_bets": n,
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": round(win_rate * 100, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "ev_per_bet": round(ev_per_bet, 2),
        "total_pnl": round(total_pnl, 2),
        "bets_per_day": round(bets_per_day, 2),
        "bets_per_year": round(n / n_years, 0),
        "avg_bars_held": round(float(bets["bars_held"].mean()), 1) if "bars_held" in bets else 0,
        "n_years": round(n_years, 1),
    }
