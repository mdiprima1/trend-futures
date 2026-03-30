"""
Portfolio Construction & Vol Targeting Engine — Sprint 2

Combines multiple instruments with proper risk management:
- Individual instrument vol targeting (ATR or EWMA)
- Portfolio-level vol scaling
- Allocation methods: equal weight, inverse-vol risk parity, HRP
- Rebalancing with threshold and frequency controls
"""
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import squareform

from src.config import CONTRACT_MULTIPLIERS, COMMISSIONS
from src.backtest import TICK_SIZES


# ── Volatility Estimation ────────────────────────────────────────────

def estimate_vol_atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """ATR-based daily volatility estimate (in price points)."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def estimate_vol_ewma(df: pd.DataFrame, span: int = 20) -> pd.Series:
    """EWMA volatility estimate (annualized, as fraction of price)."""
    returns = df["close"].pct_change()
    ewma_var = returns.ewm(span=span).var()
    return np.sqrt(ewma_var * 252)


def estimate_vol_realized(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Realized volatility (annualized, as fraction of price)."""
    returns = df["close"].pct_change()
    return returns.rolling(period).std() * np.sqrt(252)


# ── Allocation Methods ───────────────────────────────────────────────

def allocate_equal_weight(n_instruments: int) -> np.ndarray:
    """Equal weight allocation."""
    return np.ones(n_instruments) / n_instruments


def allocate_inverse_vol(vol_series: dict) -> dict:
    """
    Inverse-volatility risk parity.
    Each instrument gets weight proportional to 1/vol.
    """
    symbols = list(vol_series.keys())
    vols = np.array([vol_series[s] for s in symbols])
    vols = np.where(vols > 0, vols, 1.0)  # Avoid div by zero
    inv_vol = 1.0 / vols
    weights = inv_vol / inv_vol.sum()
    return {s: w for s, w in zip(symbols, weights)}


def allocate_hrp(returns_df: pd.DataFrame) -> dict:
    """
    Hierarchical Risk Parity (De Prado 2016).

    Parameters
    ----------
    returns_df : pd.DataFrame
        Daily returns with instrument symbols as columns.

    Returns
    -------
    dict of {symbol: weight}
    """
    # Step 1: Correlation and distance matrix
    corr = returns_df.corr()
    dist = np.sqrt(0.5 * (1 - corr))

    # Step 2: Hierarchical clustering (single linkage on distance)
    condensed = squareform(dist.values, checks=False)
    # Handle NaN in distance matrix
    condensed = np.nan_to_num(condensed, nan=1.0)
    link = linkage(condensed, method="single")

    # Step 3: Quasi-diagonalization
    sort_idx = leaves_list(link).tolist()
    sorted_cols = [returns_df.columns[i] for i in sort_idx]

    # Step 4: Recursive bisection
    cov = returns_df.cov()
    weights = pd.Series(1.0, index=sorted_cols)
    cluster_items = [sorted_cols]

    while cluster_items:
        new_clusters = []
        for cluster in cluster_items:
            if len(cluster) <= 1:
                continue
            mid = len(cluster) // 2
            left = cluster[:mid]
            right = cluster[mid:]

            # Cluster variance
            left_var = _cluster_var(cov, left)
            right_var = _cluster_var(cov, right)

            # Allocate inversely proportional to variance
            total_var = left_var + right_var
            if total_var > 0:
                alpha = 1.0 - left_var / total_var
            else:
                alpha = 0.5

            weights[left] *= alpha
            weights[right] *= (1 - alpha)

            if len(left) > 1:
                new_clusters.append(left)
            if len(right) > 1:
                new_clusters.append(right)

        cluster_items = new_clusters

    # Normalize
    weights = weights / weights.sum()
    return weights.to_dict()


def _cluster_var(cov: pd.DataFrame, items: list) -> float:
    """Compute variance of an inverse-variance weighted cluster."""
    sub_cov = cov.loc[items, items]
    ivp = 1.0 / np.diag(sub_cov)
    ivp = ivp / ivp.sum()
    return float(ivp @ sub_cov.values @ ivp)


# ── Portfolio Backtest ───────────────────────────────────────────────

def portfolio_backtest(
    signals: dict,
    daily_bars: dict,
    allocation_method: str = "equal_weight",
    vol_method: str = "atr",
    vol_window: int = 20,
    portfolio_vol_target: float = 0.12,
    initial_capital: float = 500_000,
    max_contracts: int = 50,
    rebalance_freq: str = "daily",
    rebalance_threshold: float = 0.0,
) -> dict:
    """
    Run a multi-instrument portfolio backtest.

    Parameters
    ----------
    signals : dict
        {symbol: pd.Series of positions (-1, 0, +1)}
    daily_bars : dict
        {symbol: pd.DataFrame with OHLCV}
    allocation_method : str
        "equal_weight", "inverse_vol", "hrp"
    vol_method : str
        "atr", "ewma", "realized"
    vol_window : int
        Lookback for volatility estimation.
    portfolio_vol_target : float
        Annualized portfolio volatility target (e.g., 0.12 = 12%).
    initial_capital : float
    max_contracts : int
        Per-instrument max.
    rebalance_freq : str
        "daily" or "weekly"
    rebalance_threshold : float
        Only rebalance if position changes by more than this fraction.

    Returns
    -------
    dict with: equity, returns, stats, weights, positions
    """
    symbols = sorted(signals.keys())
    n = len(symbols)

    # Find common date range
    all_indices = [daily_bars[s].index for s in symbols]
    common_idx = all_indices[0]
    for idx in all_indices[1:]:
        common_idx = common_idx.intersection(idx)
    common_idx = common_idx.sort_values()

    # Estimate per-instrument volatility
    vol_fn = {"atr": estimate_vol_atr, "ewma": estimate_vol_ewma, "realized": estimate_vol_realized}[vol_method]

    inst_vol = {}  # {symbol: pd.Series of vol}
    inst_returns = {}  # {symbol: pd.Series of daily returns}
    for s in symbols:
        bars = daily_bars[s].reindex(common_idx)
        inst_vol[s] = vol_fn(bars, vol_window).reindex(common_idx)
        inst_returns[s] = bars["close"].pct_change().reindex(common_idx)

    returns_df = pd.DataFrame(inst_returns).dropna()

    # Compute allocation weights
    if allocation_method == "equal_weight":
        static_weights = {s: 1.0 / n for s in symbols}
    elif allocation_method == "inverse_vol":
        # Use average vol over the full period for static allocation
        avg_vols = {s: inst_vol[s].dropna().mean() for s in symbols}
        # Convert ATR vol to comparable annualized pct vol
        if vol_method == "atr":
            for s in symbols:
                avg_price = daily_bars[s].reindex(common_idx)["close"].mean()
                if avg_price > 0:
                    avg_vols[s] = avg_vols[s] / avg_price * np.sqrt(252)
        static_weights = allocate_inverse_vol(avg_vols)
    elif allocation_method == "hrp":
        # Use first 252 days as in-sample for initial weights, then recompute quarterly
        static_weights = allocate_hrp(returns_df.iloc[:min(504, len(returns_df))].dropna())
    else:
        raise ValueError(f"Unknown allocation method: {allocation_method}")

    # ── Day-by-day portfolio simulation ──
    equity = pd.Series(0.0, index=common_idx, dtype=float)
    portfolio_value = initial_capital
    prev_contracts = {s: 0.0 for s in symbols}
    daily_pnl_list = []

    # For weekly rebalancing
    last_rebal_date = None

    # HRP quarterly recomputation
    hrp_weights = static_weights.copy()
    last_hrp_recompute = None

    for i, date in enumerate(common_idx):
        if i < vol_window + 1:
            equity.iloc[i] = portfolio_value
            daily_pnl_list.append(0.0)
            continue

        # PnL from previous positions
        day_pnl = 0.0
        for s in symbols:
            contracts = prev_contracts[s]
            if contracts != 0:
                bars = daily_bars[s]
                if date in bars.index and common_idx[i - 1] in bars.index:
                    price_change = bars.loc[date, "close"] - bars.loc[common_idx[i - 1], "close"]
                    multiplier = CONTRACT_MULTIPLIERS.get(s, 1.0)
                    day_pnl += contracts * price_change * multiplier

        portfolio_value += day_pnl
        daily_pnl_list.append(day_pnl)
        equity.iloc[i] = portfolio_value

        # Check if we should rebalance
        should_rebal = True
        if rebalance_freq == "weekly":
            if last_rebal_date is not None and (date - last_rebal_date).days < 5:
                should_rebal = False

        if not should_rebal:
            continue

        # Recompute HRP weights quarterly
        if allocation_method == "hrp":
            if last_hrp_recompute is None or (date - last_hrp_recompute).days >= 63:
                lookback_start = max(0, i - 504)
                recent_returns = returns_df.iloc[lookback_start:i].dropna()
                if len(recent_returns) >= 60:
                    try:
                        hrp_weights = allocate_hrp(recent_returns)
                    except Exception:
                        pass  # Keep previous weights
                    last_hrp_recompute = date

        weights = hrp_weights if allocation_method == "hrp" else static_weights

        # Compute target positions
        # Portfolio vol scaling: scale all positions so portfolio vol ≈ target
        # Per-instrument vol in annualized pct terms
        current_vols = {}
        for s in symbols:
            v = inst_vol[s].iloc[i]
            if vol_method == "atr":
                price = daily_bars[s].reindex(common_idx).loc[date, "close"]
                current_vols[s] = (v / price * np.sqrt(252)) if price > 0 and not pd.isna(v) else 0.15
            else:
                current_vols[s] = v if not pd.isna(v) else 0.15

        # Target dollar risk per instrument = portfolio_value * weight * vol_target
        # Contracts = dollar_risk / (ATR * multiplier) or equivalent
        new_contracts = {}
        total_cost = 0.0

        for s in symbols:
            sig_val = signals[s].reindex(common_idx).iloc[i] if date in signals[s].index else 0.0
            if pd.isna(sig_val):
                sig_val = 0.0

            weight = weights.get(s, 1.0 / n)
            inst_vol_ann = current_vols[s]

            if inst_vol_ann > 0 and sig_val != 0:
                # Dollar allocation to this instrument
                dollar_alloc = portfolio_value * weight

                # Target notional = dollar_alloc * (vol_target / inst_vol)
                # This scales notional so each instrument contributes vol_target * weight to portfolio
                target_notional = dollar_alloc * (portfolio_vol_target / inst_vol_ann)

                # Convert to contracts
                multiplier = CONTRACT_MULTIPLIERS.get(s, 1.0)
                price = daily_bars[s].reindex(common_idx).loc[date, "close"]
                if price > 0 and multiplier > 0:
                    raw_contracts = target_notional / (price * multiplier)
                    raw_contracts = min(abs(raw_contracts), max_contracts)
                    target = sig_val * raw_contracts
                else:
                    target = 0.0
            else:
                target = 0.0

            # Threshold check
            if rebalance_threshold > 0 and prev_contracts[s] != 0:
                pct_change = abs(target - prev_contracts[s]) / abs(prev_contracts[s])
                if pct_change < rebalance_threshold:
                    target = prev_contracts[s]

            new_contracts[s] = target

            # Transaction costs
            change = abs(target - prev_contracts[s])
            if change > 0.01:
                commission = COMMISSIONS.get(s, 2.10) * change
                tick = TICK_SIZES.get(s, 0.01)
                slippage = tick * CONTRACT_MULTIPLIERS.get(s, 1.0) * change
                total_cost += commission + slippage

        portfolio_value -= total_cost
        equity.iloc[i] = portfolio_value
        prev_contracts = new_contracts
        last_rebal_date = date

    # Compute stats
    daily_pnl = pd.Series(daily_pnl_list, index=common_idx)
    daily_ret = daily_pnl / initial_capital
    stats = _portfolio_stats(equity, daily_ret, initial_capital)
    stats["allocation"] = allocation_method
    stats["vol_method"] = vol_method
    stats["vol_window"] = vol_window
    stats["vol_target"] = portfolio_vol_target
    stats["rebalance_freq"] = rebalance_freq

    return {
        "equity": equity,
        "returns": daily_ret,
        "stats": stats,
        "weights": static_weights if allocation_method != "hrp" else hrp_weights,
    }


def _portfolio_stats(equity: pd.Series, returns: pd.Series, initial_capital: float) -> dict:
    """Compute portfolio-level statistics."""
    daily_ret = returns.dropna()
    # Remove leading zeros
    first_nonzero = (daily_ret != 0).idxmax() if (daily_ret != 0).any() else daily_ret.index[0]
    daily_ret = daily_ret.loc[first_nonzero:]

    n_days = len(daily_ret)
    n_years = n_days / 252

    # Realized vol
    realized_vol = daily_ret.std() * np.sqrt(252) if n_days > 30 else 0

    # Sharpe
    sharpe = daily_ret.mean() / daily_ret.std() * np.sqrt(252) if daily_ret.std() > 0 else 0

    # CAGR
    final = equity.iloc[-1]
    cagr = (final / initial_capital) ** (1 / n_years) - 1 if n_years > 0 and final > 0 else 0

    # Max DD
    peak = equity.cummax()
    dd = (equity - peak) / peak
    max_dd = dd.min()

    # Calmar
    calmar = cagr / abs(max_dd) if max_dd != 0 else 0

    # Skewness and kurtosis of returns
    skew = daily_ret.skew() if n_days > 30 else 0
    kurt = daily_ret.kurtosis() if n_days > 30 else 0

    return {
        "sharpe": round(sharpe, 3),
        "cagr_pct": round(cagr * 100, 2),
        "max_dd_pct": round(abs(max_dd) * 100, 2),
        "calmar": round(calmar, 3),
        "realized_vol_pct": round(realized_vol * 100, 2),
        "total_return_pct": round((final / initial_capital - 1) * 100, 2),
        "final_equity": round(final, 0),
        "skew": round(skew, 3),
        "kurtosis": round(kurt, 3),
        "n_years": round(n_years, 1),
    }
