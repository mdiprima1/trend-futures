"""
Casino V1 — Technical Indicators for Intraday Futures

All indicators return signal Series:
  +1 = long entry signal
  -1 = short entry signal
   0 = no signal
"""
import numpy as np
import pandas as pd


def rsi(series: pd.Series, period: int) -> pd.Series:
    """Compute RSI."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def rsi_mean_reversion(
    df: pd.DataFrame,
    rsi_period: int = 2,
    oversold: float = 10,
    overbought: float = 90,
) -> pd.Series:
    """
    RSI mean reversion signal.
    Long when RSI drops below oversold threshold.
    Short when RSI rises above overbought threshold.
    """
    r = rsi(df["close"], rsi_period)
    signal = pd.Series(0, index=df.index)
    signal[r < oversold] = 1   # Oversold → buy
    signal[r > overbought] = -1  # Overbought → sell
    return signal


def vwap(df: pd.DataFrame) -> pd.Series:
    """Compute VWAP (resets at session start — assumes RTH data)."""
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_vol = df["volume"].cumsum()
    cum_tp_vol = (typical_price * df["volume"]).cumsum()
    return cum_tp_vol / cum_vol.replace(0, np.nan)


def bollinger_bands(df: pd.DataFrame, period: int = 20, std_mult: float = 2.0):
    """Returns (middle, upper, lower) Bollinger Bands."""
    middle = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    upper = middle + std_mult * std
    lower = middle - std_mult * std
    return middle, upper, lower


def keltner_channel(df: pd.DataFrame, period: int = 20, atr_mult: float = 1.5):
    """Returns (middle, upper, lower) Keltner Channel."""
    middle = df["close"].ewm(span=period).mean()
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=period).mean()
    upper = middle + atr_mult * atr
    lower = middle - atr_mult * atr
    return middle, upper, lower


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range."""
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


# ── Breakout / Momentum Indicators ──────────────────────────────────

def opening_range_breakout(
    df_1m: pd.DataFrame,
    range_minutes: int = 15,
) -> pd.Series:
    """
    Opening Range Breakout on 1-minute bars.
    Computes the high/low of the first N minutes each day.
    Signals +1 when price breaks above range high, -1 when below range low.
    Only one signal per day (first breakout).
    """
    signal = pd.Series(0, index=df_1m.index)
    df_1m = df_1m.copy()
    df_1m["date"] = df_1m.index.date

    for date, day_bars in df_1m.groupby("date"):
        # Get first N minutes (RTH starts at 9:30)
        range_bars = day_bars.between_time("09:30", f"09:{29+range_minutes}")
        if len(range_bars) < max(3, range_minutes // 2):
            continue

        range_high = range_bars["high"].max()
        range_low = range_bars["low"].min()
        range_width = range_high - range_low
        if range_width <= 0:
            continue

        # Scan for breakout after range period
        post_range = day_bars.between_time(
            f"09:{30+range_minutes}" if range_minutes < 30 else f"10:{range_minutes-30:02d}",
            "15:30"
        )

        for ts, bar in post_range.iterrows():
            if bar["close"] > range_high:
                signal.loc[ts] = 1
                break
            elif bar["close"] < range_low:
                signal.loc[ts] = -1
                break

    return signal


def vwap_deviation_signal(
    df: pd.DataFrame,
    std_threshold: float = 2.0,
) -> pd.Series:
    """
    VWAP deviation mean reversion.
    Long when price is N std devs below VWAP, short when above.
    Computes session VWAP with rolling std deviation bands.
    """
    typical = (df["high"] + df["low"] + df["close"]) / 3
    vol = df["volume"].replace(0, np.nan)

    # Session VWAP (cumulative within each day)
    df_copy = df.copy()
    df_copy["date"] = df_copy.index.date
    df_copy["tp_vol"] = typical * vol

    signal = pd.Series(0, index=df.index)

    for date, day in df_copy.groupby("date"):
        cum_vol = day["volume"].cumsum()
        cum_tp_vol = day["tp_vol"].cumsum()
        day_vwap = cum_tp_vol / cum_vol.replace(0, np.nan)

        # Rolling std of price around VWAP
        deviation = day["close"] - day_vwap
        rolling_std = deviation.rolling(20, min_periods=10).std()

        z_score = deviation / rolling_std.replace(0, np.nan)

        # Signals
        signal.loc[z_score.index[z_score < -std_threshold]] = 1   # Below VWAP → buy
        signal.loc[z_score.index[z_score > std_threshold]] = -1  # Above VWAP → sell

    return signal


def keltner_mean_reversion(
    df: pd.DataFrame,
    period: int = 20,
    atr_mult: float = 2.0,
) -> pd.Series:
    """
    Keltner Channel mean reversion.
    Long when price touches/crosses below lower band.
    Short when price touches/crosses above upper band.
    """
    mid, upper, lower = keltner_channel(df, period, atr_mult)
    signal = pd.Series(0, index=df.index)
    signal[df["close"] < lower] = 1   # Below lower → buy
    signal[df["close"] > upper] = -1  # Above upper → sell
    return signal


def keltner_breakout(
    df: pd.DataFrame,
    period: int = 20,
    atr_mult: float = 2.0,
) -> pd.Series:
    """
    Keltner Channel breakout (momentum).
    Long when price breaks above upper band.
    Short when price breaks below lower band.
    """
    mid, upper, lower = keltner_channel(df, period, atr_mult)
    close = df["close"]
    prev_close = close.shift(1)

    signal = pd.Series(0, index=df.index)
    # Breakout: was inside, now outside
    signal[(prev_close <= upper) & (close > upper)] = 1
    signal[(prev_close >= lower) & (close < lower)] = -1
    return signal


def bollinger_mean_reversion(
    df: pd.DataFrame,
    period: int = 20,
    std_mult: float = 2.0,
) -> pd.Series:
    """
    Bollinger Band mean reversion.
    Long when price touches lower band, short when upper.
    """
    mid, upper, lower = bollinger_bands(df, period, std_mult)
    signal = pd.Series(0, index=df.index)
    signal[df["close"] < lower] = 1
    signal[df["close"] > upper] = -1
    return signal


def ibs_signal(df: pd.DataFrame, low_thresh: float = 0.2, high_thresh: float = 0.8) -> pd.Series:
    """
    Internal Bar Strength.
    IBS = (close - low) / (high - low)
    Low IBS → oversold → buy. High IBS → overbought → sell.
    """
    rng = df["high"] - df["low"]
    ibs = (df["close"] - df["low"]) / rng.replace(0, np.nan)
    signal = pd.Series(0, index=df.index)
    signal[ibs < low_thresh] = 1
    signal[ibs > high_thresh] = -1
    return signal
