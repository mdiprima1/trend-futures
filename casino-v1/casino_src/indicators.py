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
