"""
Cross-Asset Dynamics & Network Effects — Sprint 6

Complementary signals beyond pure trend:
- Lead-lag detection across markets
- Network momentum (aggregate cross-asset signals)
- Carry signal (roll yield proxy)
- Cross-sectional momentum (relative strength ranking)
- Multi-factor combination: trend + carry + cross-sectional
"""
import numpy as np
import pandas as pd
from itertools import combinations


# ── Lead-Lag Detection ───────────────────────────────────────────────

def compute_lead_lag_matrix(returns_dict: dict, max_lag: int = 5) -> pd.DataFrame:
    """
    Compute lead-lag relationships between instruments using cross-correlation.

    Returns DataFrame where entry (i, j) is the lag at which instrument i
    best predicts instrument j. Positive = i leads j.
    """
    symbols = sorted(returns_dict.keys())
    n = len(symbols)

    # Align returns
    ret_df = pd.DataFrame(returns_dict).dropna()

    lead_lag = pd.DataFrame(0.0, index=symbols, columns=symbols)
    best_corr = pd.DataFrame(0.0, index=symbols, columns=symbols)

    for i, si in enumerate(symbols):
        for j, sj in enumerate(symbols):
            if i == j:
                continue
            max_c = 0
            best_l = 0
            si_vals = ret_df[si].values
            sj_vals = ret_df[sj].values
            n = len(si_vals)
            for lag in range(1, max_lag + 1):
                # Does si at time t predict sj at time t+lag?
                c_pos = np.corrcoef(si_vals[:n-lag], sj_vals[lag:])[0, 1]
                # Does sj at time t predict si at time t+lag?
                c_neg = np.corrcoef(sj_vals[:n-lag], si_vals[lag:])[0, 1]
                if not np.isnan(c_pos) and abs(c_pos) > abs(max_c):
                    max_c = c_pos
                    best_l = lag  # si leads sj
                if not np.isnan(c_neg) and abs(c_neg) > abs(max_c):
                    max_c = c_neg
                    best_l = -lag  # sj leads si
            lead_lag.loc[si, sj] = best_l
            best_corr.loc[si, sj] = max_c

    return lead_lag, best_corr


# ── Network Momentum ─────────────────────────────────────────────────

def network_momentum_signal(
    returns_dict: dict,
    daily_bars_dict: dict,
    lookback: int = 63,
    corr_window: int = 126,
) -> dict:
    """
    Network momentum: for each instrument, blend its own momentum with
    momentum of correlated instruments, weighted by rolling correlation.

    Inspired by Oxford 2025 "Follow the Leader" paper.

    Returns {symbol: signal_series}
    """
    symbols = sorted(returns_dict.keys())
    ret_df = pd.DataFrame(returns_dict).dropna()

    signals = {}
    for target_sym in symbols:
        # Own momentum signal
        own_mom = ret_df[target_sym].rolling(lookback).sum()

        # Network component: weighted average of other instruments' momentum
        network_mom = pd.Series(0.0, index=ret_df.index)
        total_weight = pd.Series(0.0, index=ret_df.index)

        for other_sym in symbols:
            if other_sym == target_sym:
                continue
            # Rolling correlation
            rolling_corr = ret_df[target_sym].rolling(corr_window).corr(ret_df[other_sym])
            # Only use positive correlations (lead instruments)
            pos_corr = rolling_corr.clip(lower=0)
            other_mom = ret_df[other_sym].rolling(lookback).sum()

            network_mom += pos_corr * other_mom
            total_weight += pos_corr

        # Normalize
        network_mom = network_mom / total_weight.replace(0, np.nan)
        network_mom = network_mom.fillna(0)

        # Blend: 60% own momentum + 40% network
        combined = 0.6 * own_mom + 0.4 * network_mom

        # Convert to signal
        signal = pd.Series(0.0, index=ret_df.index)
        signal[combined > 0] = 1.0
        signal[combined < 0] = -1.0

        # Reindex to original daily bars index
        if target_sym in daily_bars_dict:
            signal = signal.reindex(daily_bars_dict[target_sym].index, method="ffill").fillna(0)

        signals[target_sym] = signal

    return signals


# ── Carry Signal ─────────────────────────────────────────────────────

def carry_signal_from_returns(
    daily_bars: pd.DataFrame,
    symbol: str,
    lookback: int = 60,
) -> pd.Series:
    """
    Carry signal proxy using price trend relative to long-term mean.

    For futures without direct roll yield data, we approximate carry as:
    - Positive carry: when recent returns are positive and vol is moderate
    - Negative carry: when recent returns are negative

    In production, this would use the actual calendar spread (front - back contract).
    For now, we use a mean-reversion proxy: deviation from 252-day MA normalized by vol.
    """
    close = daily_bars["close"]
    returns = close.pct_change()

    # Carry proxy: 60-day return momentum (captures roll yield + drift)
    carry_raw = returns.rolling(lookback).mean() * 252  # Annualized

    # Normalize by volatility
    vol = returns.rolling(lookback).std() * np.sqrt(252)
    carry_zscore = carry_raw / vol.replace(0, np.nan)

    signal = pd.Series(0.0, index=daily_bars.index)
    signal[carry_zscore > 0.5] = 1.0
    signal[carry_zscore < -0.5] = -1.0

    return signal


# ── Cross-Sectional Momentum ─────────────────────────────────────────

def cross_sectional_momentum(
    returns_dict: dict,
    daily_bars_dict: dict,
    lookback: int = 126,
    long_pct: float = 0.33,
    short_pct: float = 0.33,
) -> dict:
    """
    Cross-sectional momentum: rank instruments by past return.
    Go long top tercile, short bottom tercile.

    Returns {symbol: signal_series}
    """
    symbols = sorted(returns_dict.keys())
    ret_df = pd.DataFrame(returns_dict).dropna()

    # Rolling cumulative returns
    cum_ret = ret_df.rolling(lookback).sum()

    signals = {s: pd.Series(0.0, index=ret_df.index) for s in symbols}

    n_long = max(1, int(len(symbols) * long_pct))
    n_short = max(1, int(len(symbols) * short_pct))

    for i in range(lookback, len(cum_ret)):
        row = cum_ret.iloc[i].dropna()
        if len(row) < 3:
            continue
        ranked = row.sort_values(ascending=False)

        # Long the top, short the bottom
        longs = ranked.index[:n_long]
        shorts = ranked.index[-n_short:]

        date = cum_ret.index[i]
        for s in longs:
            signals[s].iloc[i] = 1.0
        for s in shorts:
            signals[s].iloc[i] = -1.0

    # Reindex to daily bars
    for s in symbols:
        if s in daily_bars_dict:
            signals[s] = signals[s].reindex(daily_bars_dict[s].index, method="ffill").fillna(0)

    return signals


# ── Multi-Factor Combination ─────────────────────────────────────────

def multi_factor_signal(
    trend_signals: dict,
    carry_signals: dict,
    xsmom_signals: dict,
    network_signals: dict = None,
    weights: dict = None,
) -> dict:
    """
    Combine trend + carry + cross-sectional + network into a multi-factor signal.

    Default weights: trend=0.50, carry=0.20, xsmom=0.15, network=0.15
    """
    if weights is None:
        weights = {"trend": 0.50, "carry": 0.20, "xsmom": 0.15, "network": 0.15}

    if network_signals is None:
        # Redistribute network weight to trend
        weights = {"trend": 0.60, "carry": 0.25, "xsmom": 0.15}

    symbols = sorted(trend_signals.keys())
    combined = {}

    for s in symbols:
        trend = trend_signals.get(s, pd.Series(0.0))
        carry = carry_signals.get(s, pd.Series(0.0))
        xsmom = xsmom_signals.get(s, pd.Series(0.0))

        # Align indices
        common = trend.index
        for sig in [carry, xsmom]:
            common = common.intersection(sig.index)

        blend = (
            weights.get("trend", 0) * trend.reindex(common).fillna(0) +
            weights.get("carry", 0) * carry.reindex(common).fillna(0) +
            weights.get("xsmom", 0) * xsmom.reindex(common).fillna(0)
        )

        if network_signals and s in network_signals:
            net = network_signals[s].reindex(common).fillna(0)
            blend += weights.get("network", 0) * net

        # Discretize
        signal = pd.Series(0.0, index=common)
        signal[blend > 0.15] = 1.0
        signal[blend < -0.15] = -1.0
        combined[s] = signal

    return combined
