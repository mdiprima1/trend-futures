"""
Signal Blending & Regime Detection — Sprint 4

Multi-scale signal combination:
- Equal weight blend of all speeds
- Barbell: short + long only (Etienne et al. 2025)
- Dynamic weighting based on regime

Regime filters:
- ADX trend strength
- Volatility regime (high/low vol)
- Hurst exponent (trending vs mean-reverting)
- CUSUM filter (De Prado structural break detection)
"""
import numpy as np
import pandas as pd

from src.signals import (
    signal_MA01, signal_MA02, signal_MA03, signal_MA04,
    signal_TS01, signal_TS02, signal_TS03, signal_TS04, signal_TS05,
    signal_SE01, signal_SE02, signal_SE03,
    signal_MC01,
    _ema, _sma, _atr,
)


# ── Signal Blending ──────────────────────────────────────────────────

def blend_equal_weight(df: pd.DataFrame, signal_fns: list) -> pd.Series:
    """Equal-weight blend of multiple signals. Discretize to -1/0/+1."""
    signals = [fn(df) for fn in signal_fns]
    avg = sum(signals) / len(signals)
    result = pd.Series(0.0, index=df.index)
    result[avg > 0.1] = 1.0
    result[avg < -0.1] = -1.0
    return result


def blend_continuous(df: pd.DataFrame, signal_fns: list) -> pd.Series:
    """Equal-weight blend, keep continuous value in [-1, +1]."""
    signals = [fn(df) for fn in signal_fns]
    avg = sum(signals) / len(signals)
    return avg.clip(-1, 1)


# ── Pre-defined Blends ──────────────────────────────────────────────

def signal_BLEND_ALL(df: pd.DataFrame) -> pd.Series:
    """Equal blend of all 5 Sprint 1 winners."""
    fns = [signal_TS04, signal_MA04, signal_MA03, signal_MA02, signal_SE02]
    return blend_equal_weight(df, fns)


def signal_BLEND_BARBELL(df: pd.DataFrame) -> pd.Series:
    """
    Barbell: short-term + long-term only (Etienne et al. 2025).
    Short: EMA(10/100) — fast entry
    Long: TSMOM(252d) + SMA(50/200) — slow confirmation
    Skip medium (EMA(20/50), Price>EMA(50)).
    """
    short = signal_MA04(df)    # EMA(10/100)
    long1 = signal_TS04(df)    # TSMOM(252d)
    long2 = signal_MA03(df)    # SMA(50/200)
    avg = (short + long1 + long2) / 3.0
    result = pd.Series(0.0, index=df.index)
    result[avg > 0.1] = 1.0
    result[avg < -0.1] = -1.0
    return result


def signal_BLEND_FAST_SLOW(df: pd.DataFrame) -> pd.Series:
    """
    Two-speed blend: fastest + slowest from Sprint 1.
    Fast: EMA(10/100) — captures entry
    Slow: TSMOM(252d) — confirms trend
    """
    fast = signal_MA04(df)
    slow = signal_TS04(df)
    avg = (fast + slow) / 2.0
    result = pd.Series(0.0, index=df.index)
    result[avg > 0] = 1.0
    result[avg < 0] = -1.0
    return result


def signal_BLEND_CONSENSUS(df: pd.DataFrame) -> pd.Series:
    """
    Consensus: only enter when 4+ of 5 signals agree on direction.
    More conservative — fewer trades, higher conviction.
    """
    fns = [signal_TS04, signal_MA04, signal_MA03, signal_MA02, signal_SE02]
    signals = [fn(df) for fn in fns]
    total = sum(signals)
    result = pd.Series(0.0, index=df.index)
    result[total >= 4] = 1.0
    result[total <= -4] = -1.0
    return result


# ── Regime Filters ───────────────────────────────────────────────────

def compute_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average Directional Index — measures trend strength (not direction)."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    plus_dm = high.diff()
    minus_dm = -low.diff()

    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    atr = _atr(df, period)

    plus_di = 100 * _ema(plus_dm, period) / atr
    minus_di = 100 * _ema(minus_dm, period) / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = _ema(dx.fillna(0), period)

    return adx


def compute_hurst(series: pd.Series, window: int = 100) -> pd.Series:
    """
    Rolling Hurst exponent via R/S analysis.
    H > 0.5 = trending, H < 0.5 = mean-reverting, H = 0.5 = random walk.
    """
    def rs_hurst(x):
        if len(x) < 20:
            return 0.5
        returns = np.diff(x) / x[:-1]
        mean_r = returns.mean()
        deviate = np.cumsum(returns - mean_r)
        R = deviate.max() - deviate.min()
        S = returns.std(ddof=1)
        if S == 0 or R == 0:
            return 0.5
        return np.log(R / S) / np.log(len(returns))

    return series.rolling(window).apply(rs_hurst, raw=True)


def compute_vol_regime(df: pd.DataFrame, fast: int = 20, slow: int = 60) -> pd.Series:
    """
    Volatility regime: ratio of short-term to long-term vol.
    > 1 = vol expanding (good for trend), < 1 = vol contracting.
    """
    returns = df["close"].pct_change()
    fast_vol = returns.rolling(fast).std()
    slow_vol = returns.rolling(slow).std()
    return (fast_vol / slow_vol).replace([np.inf, -np.inf], 1.0).fillna(1.0)


def cusum_filter(series: pd.Series, threshold: float) -> pd.Series:
    """
    CUSUM filter (De Prado AFML Ch. 2).
    Returns a boolean series: True when cumulative deviation exceeds threshold.
    Used to detect structural breaks / meaningful moves.
    """
    returns = series.pct_change().fillna(0)
    s_pos = pd.Series(0.0, index=series.index)
    s_neg = pd.Series(0.0, index=series.index)
    events = pd.Series(False, index=series.index)

    for i in range(1, len(returns)):
        s_pos.iloc[i] = max(0, s_pos.iloc[i-1] + returns.iloc[i])
        s_neg.iloc[i] = min(0, s_neg.iloc[i-1] + returns.iloc[i])

        if s_pos.iloc[i] > threshold:
            events.iloc[i] = True
            s_pos.iloc[i] = 0
        elif s_neg.iloc[i] < -threshold:
            events.iloc[i] = True
            s_neg.iloc[i] = 0

    return events


# ── Regime-Filtered Signals ──────────────────────────────────────────

def apply_adx_filter(signal: pd.Series, df: pd.DataFrame, threshold: float = 20) -> pd.Series:
    """Only trade when ADX > threshold (strong trend)."""
    adx = compute_adx(df)
    filtered = signal.copy()
    filtered[adx < threshold] = 0.0
    return filtered


def apply_vol_regime_filter(signal: pd.Series, df: pd.DataFrame, min_ratio: float = 0.8) -> pd.Series:
    """Only trade when vol is not collapsing (fast/slow vol ratio > min_ratio)."""
    vol_ratio = compute_vol_regime(df)
    filtered = signal.copy()
    filtered[vol_ratio < min_ratio] = 0.0
    return filtered


def apply_hurst_filter(signal: pd.Series, df: pd.DataFrame, min_hurst: float = 0.5, window: int = 100) -> pd.Series:
    """Only trade when Hurst > threshold (trending regime)."""
    hurst = compute_hurst(df["close"], window)
    filtered = signal.copy()
    filtered[hurst < min_hurst] = 0.0
    return filtered


def apply_cusum_gate(signal: pd.Series, df: pd.DataFrame, threshold: float = 0.02) -> pd.Series:
    """
    CUSUM gating: only allow position changes when CUSUM event fires.
    Between events, hold the previous position.
    """
    events = cusum_filter(df["close"], threshold)
    gated = pd.Series(0.0, index=signal.index)
    current_pos = 0.0

    for i in range(len(signal)):
        if events.iloc[i]:
            current_pos = signal.iloc[i]
        gated.iloc[i] = current_pos

    return gated


# ── Combined Regime-Adaptive Signals ─────────────────────────────────

def signal_BARBELL_ADX(df: pd.DataFrame) -> pd.Series:
    """Barbell blend with ADX filter — only trade in strong trends."""
    base = signal_BLEND_BARBELL(df)
    return apply_adx_filter(base, df, threshold=20)


def signal_BARBELL_VOL(df: pd.DataFrame) -> pd.Series:
    """Barbell blend with vol regime filter."""
    base = signal_BLEND_BARBELL(df)
    return apply_vol_regime_filter(base, df, min_ratio=0.8)


def signal_BARBELL_HURST(df: pd.DataFrame) -> pd.Series:
    """Barbell blend with Hurst filter — only trade in trending regimes."""
    base = signal_BLEND_BARBELL(df)
    return apply_hurst_filter(base, df, min_hurst=0.50)


def signal_BARBELL_CUSUM(df: pd.DataFrame) -> pd.Series:
    """Barbell blend with CUSUM gating — only change position on structural breaks."""
    base = signal_BLEND_BARBELL(df)
    return apply_cusum_gate(base, df, threshold=0.02)


def signal_FASTSLOW_ADX(df: pd.DataFrame) -> pd.Series:
    """Fast/slow blend with ADX filter."""
    base = signal_BLEND_FAST_SLOW(df)
    return apply_adx_filter(base, df, threshold=20)


def signal_CONSENSUS_ADX(df: pd.DataFrame) -> pd.Series:
    """Consensus blend with ADX filter."""
    base = signal_BLEND_CONSENSUS(df)
    return apply_adx_filter(base, df, threshold=20)


# ── Signal Registry ──────────────────────────────────────────────────

BLEND_SIGNALS = {
    # Pure blends (no regime filter)
    "BL-ALL":  {"fn": signal_BLEND_ALL, "name": "Equal Blend (5)", "type": "blend"},
    "BL-BAR":  {"fn": signal_BLEND_BARBELL, "name": "Barbell (S+L)", "type": "blend"},
    "BL-FS":   {"fn": signal_BLEND_FAST_SLOW, "name": "Fast+Slow", "type": "blend"},
    "BL-CON":  {"fn": signal_BLEND_CONSENSUS, "name": "Consensus (4/5)", "type": "blend"},
    # Regime-filtered blends
    "RF-BAR-ADX":   {"fn": signal_BARBELL_ADX, "name": "Barbell+ADX", "type": "regime"},
    "RF-BAR-VOL":   {"fn": signal_BARBELL_VOL, "name": "Barbell+VolReg", "type": "regime"},
    "RF-BAR-HUR":   {"fn": signal_BARBELL_HURST, "name": "Barbell+Hurst", "type": "regime"},
    "RF-BAR-CUS":   {"fn": signal_BARBELL_CUSUM, "name": "Barbell+CUSUM", "type": "regime"},
    "RF-FS-ADX":    {"fn": signal_FASTSLOW_ADX, "name": "FastSlow+ADX", "type": "regime"},
    "RF-CON-ADX":   {"fn": signal_CONSENSUS_ADX, "name": "Consensus+ADX", "type": "regime"},
}
