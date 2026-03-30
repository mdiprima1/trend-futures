"""
Trend Following Signal Engine — Sprint 1

18 signals across 5 families:
- MA: Moving average crossover (5 variants)
- TS: Time-series momentum / TSMOM (5 variants)
- BR: Breakout / channel (3 variants)
- MC: MACD-based (3 variants)
- SE: Single EMA vs price (3 variants — Valeyre reference)

Each function takes a daily OHLCV DataFrame and returns a pd.Series of positions:
  +1 = long, -1 = short, 0 = flat
"""
import numpy as np
import pandas as pd


# ── Helpers ──────────────────────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()


def _hull_ma(series: pd.Series, period: int) -> pd.Series:
    """Hull Moving Average: WMA(2*WMA(n/2) - WMA(n), sqrt(n))"""
    half = max(1, period // 2)
    sqrt_n = max(1, int(np.sqrt(period)))
    wma_half = series.rolling(half).apply(
        lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True
    )
    wma_full = series.rolling(period).apply(
        lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True
    )
    diff = 2 * wma_half - wma_full
    hull = diff.rolling(sqrt_n).apply(
        lambda x: np.average(x, weights=np.arange(1, len(x) + 1)), raw=True
    )
    return hull


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Average True Range."""
    high = df["high"]
    low = df["low"]
    close = df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ── Moving Average Crossover Signals ─────────────────────────────────

def ma_crossover(df: pd.DataFrame, fast: int, slow: int, ma_type: str = "ema") -> pd.Series:
    """
    Moving average crossover signal.
    +1 when fast MA > slow MA, -1 when fast MA < slow MA.
    """
    close = df["close"]
    if ma_type == "ema":
        fast_ma = _ema(close, fast)
        slow_ma = _ema(close, slow)
    elif ma_type == "sma":
        fast_ma = _sma(close, fast)
        slow_ma = _sma(close, slow)
    elif ma_type == "hull":
        fast_ma = _hull_ma(close, fast)
        slow_ma = _hull_ma(close, slow)
    else:
        raise ValueError(f"Unknown MA type: {ma_type}")

    signal = pd.Series(0.0, index=df.index)
    signal[fast_ma > slow_ma] = 1.0
    signal[fast_ma < slow_ma] = -1.0
    return signal


def signal_MA01(df: pd.DataFrame) -> pd.Series:
    """EMA(10) / EMA(30) crossover — fast"""
    return ma_crossover(df, 10, 30, "ema")


def signal_MA02(df: pd.DataFrame) -> pd.Series:
    """EMA(20) / EMA(50) crossover — standard"""
    return ma_crossover(df, 20, 50, "ema")


def signal_MA03(df: pd.DataFrame) -> pd.Series:
    """SMA(50) / SMA(200) crossover — classic trend"""
    return ma_crossover(df, 50, 200, "sma")


def signal_MA04(df: pd.DataFrame) -> pd.Series:
    """EMA(10) / EMA(100) crossover — asymmetric"""
    return ma_crossover(df, 10, 100, "ema")


def signal_MA05(df: pd.DataFrame) -> pd.Series:
    """Hull(20) / Hull(50) crossover — low lag"""
    return ma_crossover(df, 20, 50, "hull")


# ── TSMOM Signals ────────────────────────────────────────────────────

def tsmom(df: pd.DataFrame, lookback: int) -> pd.Series:
    """
    Time-series momentum: sign of past N-day return.
    +1 if past return > 0, -1 if < 0.
    """
    ret = df["close"].pct_change(lookback)
    signal = pd.Series(0.0, index=df.index)
    signal[ret > 0] = 1.0
    signal[ret < 0] = -1.0
    return signal


def signal_TS01(df: pd.DataFrame) -> pd.Series:
    """TSMOM 21-day (1 month)"""
    return tsmom(df, 21)


def signal_TS02(df: pd.DataFrame) -> pd.Series:
    """TSMOM 63-day (3 months)"""
    return tsmom(df, 63)


def signal_TS03(df: pd.DataFrame) -> pd.Series:
    """TSMOM 126-day (6 months)"""
    return tsmom(df, 126)


def signal_TS04(df: pd.DataFrame) -> pd.Series:
    """TSMOM 252-day (12 months) — Moskowitz original"""
    return tsmom(df, 252)


def signal_TS05(df: pd.DataFrame) -> pd.Series:
    """TSMOM blend: equal weight of 21/63/126/252 day — Babu et al."""
    s1 = tsmom(df, 21)
    s2 = tsmom(df, 63)
    s3 = tsmom(df, 126)
    s4 = tsmom(df, 252)
    blend = (s1 + s2 + s3 + s4) / 4.0
    # Discretize: > 0 → long, < 0 → short, 0 → flat
    signal = pd.Series(0.0, index=df.index)
    signal[blend > 0] = 1.0
    signal[blend < 0] = -1.0
    return signal


# ── Breakout Signals ─────────────────────────────────────────────────

def signal_BR01(df: pd.DataFrame) -> pd.Series:
    """Donchian 20/10 — Turtle System 1"""
    high_20 = df["high"].rolling(20).max()
    low_10 = df["low"].rolling(10).min()
    close = df["close"]

    signal = pd.Series(0.0, index=df.index)
    pos = 0.0
    for i in range(1, len(df)):
        if close.iloc[i] > high_20.iloc[i - 1] and not pd.isna(high_20.iloc[i - 1]):
            pos = 1.0
        elif close.iloc[i] < low_10.iloc[i - 1] and not pd.isna(low_10.iloc[i - 1]):
            if pos > 0:
                pos = 0.0
        low_20 = df["low"].iloc[max(0, i - 19):i + 1].min()
        high_10_val = df["high"].iloc[max(0, i - 9):i + 1].max()
        if close.iloc[i] < df["low"].rolling(20).min().iloc[i - 1] if i > 0 and not pd.isna(df["low"].rolling(20).min().iloc[i - 1]) else False:
            pos = -1.0
        elif close.iloc[i] > df["high"].rolling(10).max().iloc[i - 1] if i > 0 and not pd.isna(df["high"].rolling(10).max().iloc[i - 1]) else False:
            if pos < 0:
                pos = 0.0
        signal.iloc[i] = pos
    return signal


def signal_BR02(df: pd.DataFrame) -> pd.Series:
    """Donchian 55/20 — Turtle System 2"""
    high_55 = df["high"].rolling(55).max().shift(1)
    low_55 = df["low"].rolling(55).min().shift(1)
    high_20 = df["high"].rolling(20).max().shift(1)
    low_20 = df["low"].rolling(20).min().shift(1)
    close = df["close"]

    signal = pd.Series(0.0, index=df.index)
    pos = 0.0
    for i in range(len(df)):
        if pd.isna(high_55.iloc[i]):
            signal.iloc[i] = 0.0
            continue
        if close.iloc[i] > high_55.iloc[i]:
            pos = 1.0
        elif close.iloc[i] < low_55.iloc[i]:
            pos = -1.0

        # Exit: 20-day reversal
        if pos > 0 and close.iloc[i] < low_20.iloc[i]:
            pos = 0.0
        elif pos < 0 and close.iloc[i] > high_20.iloc[i]:
            pos = 0.0

        signal.iloc[i] = pos
    return signal


def signal_BR03(df: pd.DataFrame) -> pd.Series:
    """ATR Channel breakout: MA(20) ± 2*ATR(14)"""
    close = df["close"]
    ma = _sma(close, 20)
    atr_val = _atr(df, 14)
    upper = ma + 2 * atr_val
    lower = ma - 2 * atr_val

    signal = pd.Series(0.0, index=df.index)
    pos = 0.0
    for i in range(len(df)):
        if pd.isna(upper.iloc[i]):
            continue
        if close.iloc[i] > upper.iloc[i]:
            pos = 1.0
        elif close.iloc[i] < lower.iloc[i]:
            pos = -1.0
        elif pos > 0 and close.iloc[i] < ma.iloc[i]:
            pos = 0.0
        elif pos < 0 and close.iloc[i] > ma.iloc[i]:
            pos = 0.0
        signal.iloc[i] = pos
    return signal


# ── MACD Signals ─────────────────────────────────────────────────────

def macd_signal(df: pd.DataFrame, fast: int, slow: int, signal_period: int) -> pd.Series:
    """MACD signal: long when MACD > signal line, short when below."""
    close = df["close"]
    macd_line = _ema(close, fast) - _ema(close, slow)
    signal_line = _ema(macd_line, signal_period)

    signal = pd.Series(0.0, index=df.index)
    signal[macd_line > signal_line] = 1.0
    signal[macd_line < signal_line] = -1.0
    return signal


def signal_MC01(df: pd.DataFrame) -> pd.Series:
    """MACD(12, 26, 9) — standard"""
    return macd_signal(df, 12, 26, 9)


def signal_MC02(df: pd.DataFrame) -> pd.Series:
    """MACD(8, 21, 5) — faster"""
    return macd_signal(df, 8, 21, 5)


def signal_MC03(df: pd.DataFrame) -> pd.Series:
    """MACD(16, 36, 12) — slower"""
    return macd_signal(df, 16, 36, 12)


# ── Single EMA Signals (Valeyre Reference) ────────────────────────────

def single_ema(df: pd.DataFrame, period: int) -> pd.Series:
    """Price vs EMA: long when price > EMA, short when below."""
    close = df["close"]
    ema = _ema(close, period)
    signal = pd.Series(0.0, index=df.index)
    signal[close > ema] = 1.0
    signal[close < ema] = -1.0
    return signal


def signal_SE01(df: pd.DataFrame) -> pd.Series:
    """Price vs EMA(20)"""
    return single_ema(df, 20)


def signal_SE02(df: pd.DataFrame) -> pd.Series:
    """Price vs EMA(50)"""
    return single_ema(df, 50)


def signal_SE03(df: pd.DataFrame) -> pd.Series:
    """Price vs EMA(100)"""
    return single_ema(df, 100)


# ── Signal Registry ──────────────────────────────────────────────────

SIGNALS = {
    # Moving Average Crossover
    "MA-01": {"fn": signal_MA01, "name": "EMA(10/30)", "family": "MA", "speed": "fast"},
    "MA-02": {"fn": signal_MA02, "name": "EMA(20/50)", "family": "MA", "speed": "medium"},
    "MA-03": {"fn": signal_MA03, "name": "SMA(50/200)", "family": "MA", "speed": "slow"},
    "MA-04": {"fn": signal_MA04, "name": "EMA(10/100)", "family": "MA", "speed": "asymmetric"},
    "MA-05": {"fn": signal_MA05, "name": "Hull(20/50)", "family": "MA", "speed": "fast"},
    # TSMOM
    "TS-01": {"fn": signal_TS01, "name": "TSMOM(21d)", "family": "TS", "speed": "fast"},
    "TS-02": {"fn": signal_TS02, "name": "TSMOM(63d)", "family": "TS", "speed": "medium"},
    "TS-03": {"fn": signal_TS03, "name": "TSMOM(126d)", "family": "TS", "speed": "medium"},
    "TS-04": {"fn": signal_TS04, "name": "TSMOM(252d)", "family": "TS", "speed": "slow"},
    "TS-05": {"fn": signal_TS05, "name": "TSMOM(blend)", "family": "TS", "speed": "blend"},
    # Breakout
    "BR-01": {"fn": signal_BR01, "name": "Donchian(20/10)", "family": "BR", "speed": "medium"},
    "BR-02": {"fn": signal_BR02, "name": "Donchian(55/20)", "family": "BR", "speed": "slow"},
    "BR-03": {"fn": signal_BR03, "name": "ATR Channel(20,2)", "family": "BR", "speed": "medium"},
    # MACD
    "MC-01": {"fn": signal_MC01, "name": "MACD(12/26/9)", "family": "MC", "speed": "medium"},
    "MC-02": {"fn": signal_MC02, "name": "MACD(8/21/5)", "family": "MC", "speed": "fast"},
    "MC-03": {"fn": signal_MC03, "name": "MACD(16/36/12)", "family": "MC", "speed": "slow"},
    # Single EMA
    "SE-01": {"fn": signal_SE01, "name": "Price>EMA(20)", "family": "SE", "speed": "fast"},
    "SE-02": {"fn": signal_SE02, "name": "Price>EMA(50)", "family": "SE", "speed": "medium"},
    "SE-03": {"fn": signal_SE03, "name": "Price>EMA(100)", "family": "SE", "speed": "slow"},
}


def generate_all_signals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Generate all 18 signals for a single instrument.
    Returns DataFrame with signal IDs as columns.
    """
    results = {}
    for sig_id, sig_info in SIGNALS.items():
        try:
            results[sig_id] = sig_info["fn"](df)
        except Exception as e:
            print(f"  Warning: {sig_id} failed: {e}")
            results[sig_id] = pd.Series(0.0, index=df.index)
    return pd.DataFrame(results)
