"""
PHASE 3 — Feature Engineering

Modular, no-lookahead feature library.
All features are computed using ONLY past data (proper lagging).
"""
import numpy as np
import pandas as pd


def returns(close, periods=[1, 2, 3, 5, 10, 21, 63, 126, 252]):
    """Forward and backward returns at various horizons."""
    result = {}
    for p in periods:
        result[f"ret_{p}d"] = close.pct_change(p)  # Backward return (signal)
        result[f"fwd_ret_{p}d"] = close.pct_change(p).shift(-p)  # Forward (label, not for signals)
    return pd.DataFrame(result, index=close.index)


def rsi(close, period=2):
    """RSI indicator. No lookahead."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def ibs(high, low, close):
    """Internal Bar Strength. (close - low) / (high - low)."""
    rng = high - low
    return (close - low) / rng.replace(0, np.nan)


def bollinger_zscore(close, period=20):
    """(close - SMA) / rolling_std. Measures deviation from mean."""
    sma = close.rolling(period).mean()
    std = close.rolling(period).std()
    return (close - sma) / std.replace(0, np.nan)


def sma_deviation(close, period=20):
    """(close - SMA) / SMA. Percentage deviation from moving average."""
    sma = close.rolling(period).mean()
    return (close - sma) / sma.replace(0, np.nan)


def atr(high, low, close, period=14):
    """Average True Range."""
    pc = close.shift(1)
    tr = pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def sma_dev_atr(close, high, low, sma_period=20, atr_period=14):
    """SMA deviation in ATR units. More stable than percentage."""
    sma = close.rolling(sma_period).mean()
    atr_val = atr(high, low, close, atr_period)
    return (close - sma) / atr_val.replace(0, np.nan)


def rolling_volatility(close, period=20):
    """Annualized rolling volatility."""
    return close.pct_change().rolling(period).std() * np.sqrt(252)


def vol_ratio(close, fast=5, slow=20):
    """Ratio of short-term to long-term vol. >1 = expanding, <1 = contracting."""
    fast_vol = close.pct_change().rolling(fast).std()
    slow_vol = close.pct_change().rolling(slow).std()
    return fast_vol / slow_vol.replace(0, np.nan)


def consecutive_down_days(close, max_lookback=10):
    """Count of consecutive down days ending today."""
    neg = (close.diff() < 0).astype(int)
    result = pd.Series(0, index=close.index, dtype=int)
    for i in range(1, len(close)):
        if neg.iloc[i]:
            result.iloc[i] = result.iloc[i-1] + 1
        else:
            result.iloc[i] = 0
    return result


def gap_pct(open_price, prev_close):
    """Gap percentage from previous close to current open."""
    return (open_price - prev_close) / prev_close.replace(0, np.nan) * 100


def relative_volume(volume, period=20):
    """Current volume / average volume. >1 = above average."""
    avg_vol = volume.rolling(period).mean()
    return volume / avg_vol.replace(0, np.nan)


def williams_r(high, low, close, period=14):
    """Williams %R. -100 to 0. < -80 = oversold, > -20 = overbought."""
    highest = high.rolling(period).max()
    lowest = low.rolling(period).min()
    return -100 * (highest - close) / (highest - lowest).replace(0, np.nan)


def stochastic(high, low, close, k_period=14, d_period=3):
    """Stochastic %K and %D."""
    lowest = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    k = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


def cci(high, low, close, period=20):
    """Commodity Channel Index."""
    tp = (high + low + close) / 3
    sma = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    return (tp - sma) / (0.015 * mad).replace(0, np.nan)


def mfi(high, low, close, volume, period=14):
    """Money Flow Index (volume-weighted RSI)."""
    tp = (high + low + close) / 3
    mf = tp * volume
    pos_mf = mf.where(tp > tp.shift(1), 0).rolling(period).sum()
    neg_mf = mf.where(tp < tp.shift(1), 0).rolling(period).sum()
    ratio = pos_mf / neg_mf.replace(0, np.nan)
    return 100 - (100 / (1 + ratio))


def roc(close, period=10):
    """Rate of Change (momentum)."""
    return (close / close.shift(period) - 1) * 100


def compute_all_features(df):
    """
    Compute all features for a single stock DataFrame.
    Returns DataFrame of features (no lookahead bias).

    Input df must have: open, high, low, close, adj_close, volume
    """
    c = df["adj_close"]
    h = df["high"]
    l = df["low"]
    o = df["open"]
    v = df["volume"]

    features = pd.DataFrame(index=df.index)

    # RSI at multiple periods
    for p in [2, 3, 5, 14]:
        features[f"rsi_{p}"] = rsi(c, p)

    # IBS
    features["ibs"] = ibs(h, l, df["close"])

    # Bollinger z-score
    for p in [10, 20]:
        features[f"bb_z_{p}"] = bollinger_zscore(c, p)

    # SMA deviation (percentage)
    for p in [5, 10, 20, 50]:
        features[f"sma_dev_{p}"] = sma_deviation(c, p)

    # SMA deviation in ATR units
    features["sma_dev_atr_20"] = sma_dev_atr(c, h, l, 20, 14)

    # Returns (backward — for signal generation)
    for p in [1, 2, 3, 5, 10, 21]:
        features[f"ret_{p}d"] = c.pct_change(p) * 100

    # Volatility
    features["vol_20"] = rolling_volatility(c, 20)
    features["vol_5"] = rolling_volatility(c, 5)
    features["vol_ratio"] = vol_ratio(c, 5, 20)

    # Consecutive down days
    features["down_days"] = consecutive_down_days(c)

    # Gap
    features["gap_pct"] = gap_pct(o, df["close"].shift(1))

    # Volume
    features["rel_volume"] = relative_volume(v, 20)

    # Williams %R
    features["williams_r"] = williams_r(h, l, c, 14)

    # Stochastic
    k, d = stochastic(h, l, c, 14, 3)
    features["stoch_k"] = k
    features["stoch_d"] = d

    # CCI
    features["cci_20"] = cci(h, l, c, 20)

    # MFI
    features["mfi_14"] = mfi(h, l, c, v, 14)

    # ROC
    for p in [5, 10, 21]:
        features[f"roc_{p}"] = roc(c, p)

    # ATR (for position sizing, not a signal)
    features["atr_14"] = atr(h, l, c, 14)

    # Forward returns (LABELS — not features, used only for evaluation)
    for p in [1, 2, 3, 5]:
        features[f"fwd_ret_{p}d"] = c.pct_change(p).shift(-p) * 100

    return features


# ── Feature names by category ──

SIGNAL_FEATURES = [
    "rsi_2", "rsi_3", "rsi_5", "rsi_14",
    "ibs",
    "bb_z_10", "bb_z_20",
    "sma_dev_5", "sma_dev_10", "sma_dev_20", "sma_dev_50",
    "sma_dev_atr_20",
    "ret_1d", "ret_2d", "ret_3d", "ret_5d", "ret_10d", "ret_21d",
    "vol_20", "vol_5", "vol_ratio",
    "down_days",
    "gap_pct",
    "rel_volume",
    "williams_r",
    "stoch_k", "stoch_d",
    "cci_20",
    "mfi_14",
    "roc_5", "roc_10", "roc_21",
]

LABEL_FEATURES = ["fwd_ret_1d", "fwd_ret_2d", "fwd_ret_3d", "fwd_ret_5d"]

SIZING_FEATURES = ["atr_14", "vol_20"]
