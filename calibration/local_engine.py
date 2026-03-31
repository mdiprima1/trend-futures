"""
Local Backtesting Engine — QC-Compatible (v2)

Replicates QC's execution model:
1. Market orders fill NEXT DAY at open price
2. Indicators computed on adjusted close (yfinance auto_adjust=True)
3. Commissions: $0.005/share per side
4. Cash earns 0%

Key insight: Track portfolio value directly, not cash+shares separately.
This avoids short-selling accounting errors.
"""
import numpy as np
import pandas as pd
import yfinance as yf


COMMISSION_PER_SHARE = 0.005


def load_data(ticker, start_year=2019, end_year=2025):
    df = yf.download(ticker, start=f"{start_year}-01-01", end=f"{end_year+1}-01-01",
                      auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df.columns = [c.lower() for c in df.columns]
    return df


# ── Indicators (matching QC's manual implementations) ──

def ema_val(data, span):
    a = 2.0 / (span + 1)
    e = float(data.iloc[0])
    result = pd.Series(0.0, index=data.index)
    for i in range(len(data)):
        e = a * float(data.iloc[i]) + (1 - a) * e
        result.iloc[i] = e
    return result


def rsi_calc(closes_arr, period=3):
    """RSI on numpy array, return single value."""
    if len(closes_arr) < period + 1:
        return 50.0
    d = np.diff(closes_arr)
    g = np.where(d > 0, d, 0)
    l = np.where(d < 0, -d, 0)
    ag = np.mean(g[-period:])
    al = np.mean(l[-period:])
    return 100 - (100 / (1 + ag / al)) if al > 0 else 100


def atr_calc(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return 0
    pc = np.roll(closes, 1); pc[0] = closes[0]
    tr = np.maximum(highs - lows, np.maximum(np.abs(highs - pc), np.abs(lows - pc)))
    return float(np.mean(tr[-period:]))


# ── Unified Backtest Engine ──

def run_backtest(strategy_name, ticker, start_year=2020, end_year=2024,
                 pt_mult=1.5, sl_mult=1.0, max_bars=5):
    df = load_data(ticker, start_year - 1, end_year)
    start_date = pd.Timestamp(f"{start_year}-01-02")

    initial = 100_000.0
    portfolio_value = initial
    position = 0       # +N = long N shares, -N = short N shares, 0 = flat
    entry_price = 0.0  # Price at which current position was entered

    # Barrier state
    in_barrier = False
    barrier_dir = 0
    barrier_entry = 0.0
    barrier_pt = 0.0
    barrier_sl = 0.0
    barrier_bars = 0

    # Pending order: ("buy", qty) or ("short", qty) or ("close",) or None
    pending = None

    equity_curve = []
    trades = []
    is_barrier = strategy_name in ("rsi_mr", "boll_mr", "keltner_mr")

    trade_df = df[df.index >= start_date]

    for i in range(len(trade_df)):
        date = trade_df.index[i]
        open_p = float(trade_df.iloc[i]["open"])
        close_p = float(trade_df.iloc[i]["close"])
        high_p = float(trade_df.iloc[i]["high"])
        low_p = float(trade_df.iloc[i]["low"])

        # ── Fill pending order at today's open ──
        if pending is not None:
            action = pending[0]
            fill = open_p

            if action == "close":
                # Close current position
                if position != 0:
                    pnl = (fill - entry_price) * position
                    fee = abs(position) * COMMISSION_PER_SHARE
                    portfolio_value += pnl - fee
                    position = 0
                    entry_price = 0

            elif action == "buy":
                qty = pending[1]
                fee = qty * COMMISSION_PER_SHARE
                portfolio_value -= fee
                position = qty
                entry_price = fill

            elif action == "short":
                qty = pending[1]
                fee = qty * COMMISSION_PER_SHARE
                portfolio_value -= fee
                position = -qty
                entry_price = fill

            elif action == "reverse":
                # Close then open opposite
                old_pos = pending[1]
                new_qty = pending[2]
                new_dir = pending[3]
                # Close old
                if old_pos != 0:
                    pnl = (fill - entry_price) * old_pos
                    fee = abs(old_pos) * COMMISSION_PER_SHARE
                    portfolio_value += pnl - fee
                # Open new
                fee2 = new_qty * COMMISSION_PER_SHARE
                portfolio_value -= fee2
                position = new_qty * new_dir
                entry_price = fill

            pending = None

        # ── Compute equity (mark-to-market) ──
        if position != 0:
            unrealized_pnl = (close_p - entry_price) * position
            equity = portfolio_value + unrealized_pnl
        else:
            equity = portfolio_value
        equity_curve.append({"date": date, "equity": equity})

        # ── Get lookback data for indicators ──
        idx = df.index.get_loc(date)
        if idx < 200:
            continue
        window = df.iloc[idx - 199:idx + 1]
        closes = window["close"].values
        highs = window["high"].values
        lows = window["low"].values

        # ── Barrier management ──
        if is_barrier and in_barrier:
            barrier_bars -= 1
            hit = False; won = False

            if barrier_dir == 1:
                if close_p <= barrier_sl: hit = True; won = False
                elif close_p >= barrier_pt: hit = True; won = True
            else:
                if close_p >= barrier_sl: hit = True; won = False
                elif close_p <= barrier_pt: hit = True; won = True

            if barrier_bars <= 0:
                hit = True
                won = (close_p - barrier_entry) * barrier_dir > 0

            if hit:
                trades.append({"date": date, "result": "W" if won else "L",
                               "dir": barrier_dir, "entry": barrier_entry, "exit": close_p})
                pending = ("close",)
                in_barrier = False
            continue

        # ── Compute signal ──
        signal = _compute_signal(strategy_name, closes, highs, lows, close_p, df, idx, window)

        if is_barrier:
            if isinstance(signal, tuple):
                sig, atr_v = signal
            else:
                sig = signal; atr_v = atr_calc(highs, lows, closes, 14)

            if sig != 0 and not in_barrier:
                # Size: 10% of portfolio value / ATR
                qty = max(1, int(equity * 0.1 / (atr_v if atr_v > 0 else 1)))

                if sig == 1:
                    pending = ("buy", qty)
                    barrier_pt = close_p + pt_mult * atr_v
                    barrier_sl = close_p - sl_mult * atr_v
                else:
                    pending = ("short", qty)
                    barrier_pt = close_p - pt_mult * atr_v
                    barrier_sl = close_p + sl_mult * atr_v

                barrier_dir = sig
                barrier_entry = close_p
                barrier_bars = max_bars
                in_barrier = True
        else:
            # Non-barrier strategies
            if signal == 1 and position <= 0:
                if position < 0:
                    # Reverse: close short, go long
                    qty = int(equity * 0.95 / close_p)
                    pending = ("reverse", position, qty, 1)
                else:
                    qty = int(equity * 0.95 / close_p)
                    if qty > 0:
                        pending = ("buy", qty)
                trades.append({"date": date, "action": "BUY", "price": close_p})

            elif signal == -1 and position >= 0:
                if position > 0:
                    qty = int(equity * 0.95 / close_p)
                    pending = ("reverse", position, qty, -1)
                else:
                    qty = int(equity * 0.95 / close_p)
                    if qty > 0:
                        pending = ("short", qty)
                trades.append({"date": date, "action": "SHORT", "price": close_p})

            elif signal == 0 and position != 0:
                pending = ("close",)
                trades.append({"date": date, "action": "FLAT", "price": close_p})

    eq_df = pd.DataFrame(equity_curve).set_index("date")
    final = float(eq_df.iloc[-1]["equity"]) if len(eq_df) > 0 else initial

    return {
        "final_equity": round(final, 2),
        "total_return": round((final / initial - 1) * 100, 2),
        "n_trades": len(trades),
        "equity": eq_df,
        "trades": trades,
    }


def _compute_signal(strategy, closes, highs, lows, price, df, idx, window):
    """Compute signal for given strategy. Returns int or (int, float) for barrier."""
    if strategy == "buyhold":
        return 1

    elif strategy == "sma_cross":
        s50 = np.mean(closes[-50:])
        s200 = np.mean(closes[-200:])
        return 1 if s50 > s200 else 0

    elif strategy == "ema_cross":
        e12 = ema_val(window["close"], 12).iloc[-1]
        e26 = ema_val(window["close"], 26).iloc[-1]
        return 1 if e12 > e26 else -1

    elif strategy == "macd":
        ml = ema_val(window["close"], 12).iloc[-1] - ema_val(window["close"], 26).iloc[-1]
        # Signal line: EMA(9) of MACD line
        macd_series = ema_val(window["close"], 12) - ema_val(window["close"], 26)
        ms = ema_val(macd_series, 9).iloc[-1]
        return 1 if ml > ms else -1

    elif strategy == "momentum":
        if len(closes) >= 63:
            return 1 if closes[-1] / closes[-63] - 1 > 0 else -1
        return 0

    elif strategy == "rsi_mr":
        r = rsi_calc(closes, 3)
        atr_v = atr_calc(highs, lows, closes, 14)
        sig = 0
        if r < 25: sig = 1
        elif r > 75: sig = -1
        return (sig, atr_v)

    elif strategy == "boll_mr":
        mid = np.mean(closes[-20:])
        std = np.std(closes[-20:])
        upper = mid + 2 * std
        lower = mid - 2 * std
        atr_v = atr_calc(highs, lows, closes, 14)
        sig = 0
        if price < lower: sig = 1
        elif price > upper: sig = -1
        return (sig, atr_v)

    elif strategy == "keltner_mr":
        ema_v = ema_val(window["close"], 20).iloc[-1]
        atr_v = atr_calc(highs, lows, closes, 14)
        upper = ema_v + 2 * atr_v
        lower = ema_v - 2 * atr_v
        sig = 0
        if price < lower: sig = 1
        elif price > upper: sig = -1
        return (sig, atr_v)

    return 0
