"""
Local Backtesting Engine — QC-Compatible (v3)

QC execution model:
1. Signal computed on day T at close
2. Market order SUBMITTED on day T
3. Order FILLED on day T+1 at open
4. Commission: $0.005/share/side
5. Equity = cash + position * close_price
"""
import numpy as np
import pandas as pd
import yfinance as yf

COMM = 0.005  # per share per side


def load_data(ticker, start_year=2019, end_year=2025):
    df = yf.download(ticker, start=f"{start_year}-01-01", end=f"{end_year+1}-01-01",
                      auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df.columns = [c.lower() for c in df.columns]
    return df


# ── Indicators ──

def ema_series(data, span):
    a = 2.0 / (span + 1)
    out = np.empty(len(data))
    out[0] = data.iloc[0]
    for i in range(1, len(data)):
        out[i] = a * data.iloc[i] + (1 - a) * out[i - 1]
    return pd.Series(out, index=data.index)


def rsi_point(closes_arr, period=3):
    if len(closes_arr) < period + 1:
        return 50.0
    d = np.diff(closes_arr)
    ag = np.mean(np.maximum(d[-period:], 0))
    al = np.mean(np.maximum(-d[-period:], 0))
    return 100 - 100 / (1 + ag / al) if al > 0 else 100


def atr_point(h, l, c, period=14):
    if len(c) < period + 1:
        return 0
    pc = np.roll(c, 1); pc[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return float(np.mean(tr[-period:]))


# ── Signal Functions ──
# All return int: +1=long, -1=short, 0=flat
# Barrier strategies return (signal, atr_value)

def sig_buyhold(closes, highs, lows, price, window, idx):
    return 1

def sig_sma_cross(closes, highs, lows, price, window, idx):
    if len(closes) < 200: return 0
    return 1 if np.mean(closes[-50:]) > np.mean(closes[-200:]) else 0

def sig_ema_cross(closes, highs, lows, price, window, idx):
    if len(window) < 26: return 0
    e12 = ema_series(window["close"], 12).iloc[-1]
    e26 = ema_series(window["close"], 26).iloc[-1]
    return 1 if e12 > e26 else -1

def sig_macd(closes, highs, lows, price, window, idx):
    if len(window) < 35: return 0
    ml = ema_series(window["close"], 12) - ema_series(window["close"], 26)
    ms = ema_series(ml, 9)
    return 1 if ml.iloc[-1] > ms.iloc[-1] else -1

def sig_momentum(closes, highs, lows, price, window, idx):
    if len(closes) < 63: return 0
    return 1 if closes[-1] / closes[-63] - 1 > 0 else -1

def sig_rsi_mr(closes, highs, lows, price, window, idx):
    r = rsi_point(closes, 3)
    a = atr_point(highs, lows, closes, 14)
    sig = 1 if r < 25 else (-1 if r > 75 else 0)
    return (sig, a)

def sig_boll_mr(closes, highs, lows, price, window, idx):
    if len(closes) < 20: return (0, 0)
    mid = np.mean(closes[-20:]); std = np.std(closes[-20:])
    a = atr_point(highs, lows, closes, 14)
    sig = 1 if price < mid - 2*std else (-1 if price > mid + 2*std else 0)
    return (sig, a)

def sig_keltner_mr(closes, highs, lows, price, window, idx):
    if len(window) < 20: return (0, 0)
    ema = ema_series(window["close"], 20).iloc[-1]
    a = atr_point(highs, lows, closes, 14)
    sig = 1 if price < ema - 2*a else (-1 if price > ema + 2*a else 0)
    return (sig, a)

STRATS = {
    "buyhold": sig_buyhold, "sma_cross": sig_sma_cross,
    "ema_cross": sig_ema_cross, "macd": sig_macd,
    "momentum": sig_momentum, "rsi_mr": sig_rsi_mr,
    "boll_mr": sig_boll_mr, "keltner_mr": sig_keltner_mr,
}
BARRIER = {"rsi_mr", "boll_mr", "keltner_mr"}


# ── Engine ──

def run_backtest(strategy_name, ticker, start_year=2020, end_year=2024,
                 pt_mult=1.5, sl_mult=1.0, max_bars=5):

    df = load_data(ticker, start_year - 1, end_year)
    start = pd.Timestamp(f"{start_year}-01-02")
    is_barrier = strategy_name in BARRIER
    sig_fn = STRATS[strategy_name]

    cash = 100_000.0
    pos = 0        # shares held (+long, -short)
    avg_cost = 0.0 # average entry price

    # Barrier state
    b_active = False
    b_dir = 0; b_entry = 0; b_pt = 0; b_sl = 0; b_bars = 0

    # Pending: list of (action, qty) to execute at next open
    # action: "buy", "sell", "short", "cover"
    pending = []

    eq_list = []
    trades = []

    trade_df = df[df.index >= start]

    for i in range(len(trade_df)):
        date = trade_df.index[i]
        o = float(trade_df.iloc[i]["open"])
        c = float(trade_df.iloc[i]["close"])

        # ── Execute pending orders at open ──
        for action, qty in pending:
            if action == "buy":
                cost = qty * o + qty * COMM
                cash -= cost
                pos = qty
                avg_cost = o
            elif action == "sell":
                proceeds = qty * o - qty * COMM
                cash += proceeds
                pos = 0; avg_cost = 0
            elif action == "short":
                proceeds = qty * o - qty * COMM
                cash += proceeds
                pos = -qty
                avg_cost = o
            elif action == "cover":
                cost = qty * o + qty * COMM
                cash -= cost
                pos = 0; avg_cost = 0
        pending = []

        # ── Equity ──
        if pos > 0:
            eq = cash + pos * c
        elif pos < 0:
            eq = cash + pos * c  # pos is negative, so this subtracts the short liability
        else:
            eq = cash
        eq_list.append({"date": date, "equity": eq})

        # ── Lookback ──
        idx = df.index.get_loc(date)
        if idx < 200: continue
        w = df.iloc[idx - 199:idx + 1]
        closes = w["close"].values
        highs = w["high"].values
        lows = w["low"].values

        # ── Barrier management ──
        if is_barrier and b_active:
            b_bars -= 1
            hit = False; won = False
            if b_dir == 1:
                if c <= b_sl: hit = True; won = False
                elif c >= b_pt: hit = True; won = True
            else:
                if c >= b_sl: hit = True; won = False
                elif c <= b_pt: hit = True; won = True
            if b_bars <= 0:
                hit = True; won = (c - b_entry) * b_dir > 0
            if hit:
                if pos > 0:
                    pending.append(("sell", pos))
                elif pos < 0:
                    pending.append(("cover", abs(pos)))
                trades.append({"date": date, "result": "W" if won else "L"})
                b_active = False
            continue

        # ── Signal ──
        result = sig_fn(closes, highs, lows, c, w, idx)

        if is_barrier:
            sig, atr_v = result if isinstance(result, tuple) else (result, 1)
            if sig != 0 and not b_active:
                # Size: risk 10% equity / ATR, capped to affordable
                raw_q = max(1, int(eq * 0.1 / max(atr_v, 0.01)))
                max_q = max(1, int(eq / max(c, 1)))
                qty = min(raw_q, max_q)

                if sig == 1:
                    pending.append(("buy", qty))
                    b_pt = c + pt_mult * atr_v
                    b_sl = c - sl_mult * atr_v
                else:
                    pending.append(("short", qty))
                    b_pt = c - pt_mult * atr_v
                    b_sl = c + sl_mult * atr_v
                b_dir = sig; b_entry = c; b_bars = max_bars; b_active = True
        else:
            sig = result
            target_dir = 1 if sig == 1 else (-1 if sig == -1 else 0)
            current_dir = 1 if pos > 0 else (-1 if pos < 0 else 0)

            if target_dir != current_dir:
                # Close existing
                if pos > 0:
                    pending.append(("sell", pos))
                elif pos < 0:
                    pending.append(("cover", abs(pos)))

                # Open new (will execute at tomorrow's open)
                if target_dir == 1:
                    qty = max(1, int(eq / max(c, 1)))
                    pending.append(("buy", qty))
                    trades.append({"date": date, "action": "BUY", "price": c, "qty": qty})
                elif target_dir == -1:
                    qty = max(1, int(eq * 0.95 / max(c, 1)))
                    pending.append(("short", qty))
                    trades.append({"date": date, "action": "SHORT", "price": c, "qty": qty})
                elif target_dir == 0:
                    trades.append({"date": date, "action": "FLAT", "price": c})

    eq_df = pd.DataFrame(eq_list).set_index("date")
    final = float(eq_df.iloc[-1]["equity"]) if len(eq_df) > 0 else 100_000

    return {
        "final_equity": round(final, 2),
        "total_return": round((final / 100_000 - 1) * 100, 2),
        "n_trades": len(trades),
        "equity": eq_df,
        "trades": trades,
    }
