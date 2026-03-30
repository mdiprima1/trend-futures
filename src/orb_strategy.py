"""
ORB V10 Winner Strategy — vectorbt implementation.

Replicates the QuantConnect ORB V10 winner for calibration:
- 9:30-9:45 opening range on ES and NQ
- 7-minute breakout confirmation
- 20-day SMA trend filter (per instrument, using futures daily close)
- Dual vol filter (realized vol < 12% OR VIX < 15 → skip)
- VIX compression proxy (VIX fell >20% in 10d AND VIX < 18 → skip)
- Asymmetric risk: ES 1.0%, NQ 0.5% of portfolio per trade
- 2:1 reward/risk ratio
- Flatten at 15:45 ET
- No Mondays
"""
import numpy as np
import pandas as pd

from src.config import CONTRACT_MULTIPLIERS, COMMISSIONS


# ── Strategy Parameters ──────────────────────────────────────────────

DEFAULT_PARAMS = {
    "range_start": "09:30",
    "range_end": "09:45",
    "flatten_time": "15:45",
    "confirmation_minutes": 7,
    "reward_risk_ratio": 2.0,
    "min_range_pct": 0.0015,
    "max_range_pct": 0.015,
    "sma_period": 20,
    "max_contracts": 20,
    # Risk per trade (fraction of portfolio)
    "risk_per_trade": {"ES": 0.010, "NQ": 0.005},
    # Dual vol filter
    "vol_lookback": 20,
    "min_realized_vol": 0.12,
    "min_vix": 15.0,
    # VIX compression
    "vix_drop_pct": 0.20,
    "vix_drop_days": 10,
    "vix_compression_ceil": 18.0,
    # Capital
    "initial_capital": 500_000,
}


def _compute_daily_filters(spy_daily: pd.DataFrame, vix_daily: pd.Series, params: dict) -> dict:
    """
    Compute daily filter values as a dict keyed by date (no tz).
    Returns dict[date] -> bool (True = trade allowed).
    """
    spy_close = spy_daily["close"]
    spy_returns = spy_close.pct_change()
    realized_vol = spy_returns.rolling(params["vol_lookback"]).std() * np.sqrt(252)

    # Align VIX to SPY dates
    vix_aligned = vix_daily.reindex(spy_daily.index, method="ffill")

    filters = {}
    vix_values = {}
    for i, idx in enumerate(spy_daily.index):
        date = idx.date() if hasattr(idx, 'date') else idx

        vol = realized_vol.iloc[i] if not pd.isna(realized_vol.iloc[i]) else 0.20
        vix_val = vix_aligned.iloc[i] if i < len(vix_aligned) and not pd.isna(vix_aligned.iloc[i]) else 20.0
        vix_values[date] = vix_val

        # Dual vol filter: skip if realized vol < 12% OR VIX < 15
        vol_skip = vol < params["min_realized_vol"]
        vix_skip = vix_val < params["min_vix"]
        dual_skip = vol_skip or vix_skip

        # VIX compression proxy
        vix_comp_skip = False
        if i >= params["vix_drop_days"]:
            vix_ago = vix_aligned.iloc[i - params["vix_drop_days"]]
            if not pd.isna(vix_ago) and vix_ago > 0:
                vix_change = (vix_val - vix_ago) / vix_ago
                if vix_change < -params["vix_drop_pct"] and vix_val < params["vix_compression_ceil"]:
                    vix_comp_skip = True

        # Monday check
        is_monday = idx.dayofweek == 0

        filters[date] = not (dual_skip or vix_comp_skip or is_monday)

    return filters


def _precompute_trends(daily_bars: pd.DataFrame, period: int) -> dict:
    """Precompute SMA trend per date. Returns dict[date] -> int (+1, -1, or 0)."""
    sma = daily_bars["close"].rolling(period).mean()
    trends = {}
    for idx in daily_bars.index:
        date = idx.date() if hasattr(idx, 'date') else idx
        close = daily_bars.loc[idx, "close"]
        sma_val = sma.loc[idx]
        if pd.isna(sma_val):
            trends[date] = 0
        elif close > sma_val:
            trends[date] = 1
        else:
            trends[date] = -1
    return trends


def _find_most_recent(trend_dict: dict, target_date) -> int:
    """Find the most recent trend value on or before target_date."""
    # Sort dates and binary search
    dates = sorted(trend_dict.keys())
    result = 0
    for d in dates:
        if d <= target_date:
            result = trend_dict[d]
        else:
            break
    return result


def _run_day_for_instrument(
    day_bars: pd.DataFrame,
    range_high: float,
    range_low: float,
    range_width: float,
    day_trend: int,
    symbol: str,
    portfolio_value: float,
    params: dict,
) -> dict | None:
    """
    Process one day for one instrument. Returns trade dict or None.
    """
    multiplier = CONTRACT_MULTIPLIERS[symbol]
    commission_rt = COMMISSIONS[symbol]
    risk_frac = params["risk_per_trade"].get(symbol, 0.01)

    # Bars from 09:45 to 15:44 for breakout scanning
    trade_bars = day_bars.between_time("09:45", "15:44")
    if len(trade_bars) == 0:
        return None

    flatten_cutoff = day_bars.index[0].replace(hour=15, minute=15, second=0)

    breakout_dir = None
    breakout_start_idx = None

    for i, (ts, bar) in enumerate(trade_bars.iterrows()):
        if ts >= flatten_cutoff:
            break

        price = bar["close"]

        if breakout_dir is None:
            if price > range_high and day_trend >= 0:
                breakout_dir = "long"
                breakout_start_idx = i
            elif price < range_low and day_trend <= 0:
                breakout_dir = "short"
                breakout_start_idx = i
        else:
            still_valid = (
                (breakout_dir == "long" and price > range_high) or
                (breakout_dir == "short" and price < range_low)
            )
            if not still_valid:
                breakout_dir = None
                breakout_start_idx = None
                if price > range_high and day_trend >= 0:
                    breakout_dir = "long"
                    breakout_start_idx = i
                elif price < range_low and day_trend <= 0:
                    breakout_dir = "short"
                    breakout_start_idx = i
                continue

            elapsed_minutes = i - breakout_start_idx
            if elapsed_minutes >= params["confirmation_minutes"]:
                entry_price = price
                if breakout_dir == "long":
                    stop_price = range_low
                    target_price = entry_price + params["reward_risk_ratio"] * range_width
                else:
                    stop_price = range_high
                    target_price = entry_price - params["reward_risk_ratio"] * range_width

                # Position sizing
                risk_per_contract = range_width * multiplier
                if risk_per_contract <= 0:
                    breakout_dir = None
                    continue
                dollar_risk = portfolio_value * risk_frac
                n_contracts = int(dollar_risk / risk_per_contract)
                n_contracts = max(1, min(n_contracts, params["max_contracts"]))

                # Scan for exit
                exit_price = None
                exit_time = None
                remaining = trade_bars.iloc[i:]

                for exit_ts, exit_bar in remaining.iterrows():
                    p = exit_bar["close"]
                    h = exit_bar["high"]
                    l = exit_bar["low"]

                    flatten_ts = exit_ts.replace(hour=15, minute=45, second=0)
                    if exit_ts >= flatten_ts:
                        exit_price = p
                        exit_time = exit_ts
                        break

                    if breakout_dir == "long":
                        if l <= stop_price:
                            exit_price = stop_price
                            exit_time = exit_ts
                            break
                        if h >= target_price:
                            exit_price = target_price
                            exit_time = exit_ts
                            break
                    else:
                        if h >= stop_price:
                            exit_price = stop_price
                            exit_time = exit_ts
                            break
                        if l <= target_price:
                            exit_price = target_price
                            exit_time = exit_ts
                            break

                if exit_price is None:
                    last_bar = trade_bars.iloc[-1]
                    exit_price = last_bar["close"]
                    exit_time = trade_bars.index[-1]

                if breakout_dir == "long":
                    pnl_points = exit_price - entry_price
                else:
                    pnl_points = entry_price - exit_price

                pnl_dollars = pnl_points * multiplier * n_contracts
                total_commission = commission_rt * n_contracts

                return {
                    "symbol": symbol,
                    "date": day_bars.index[0].date(),
                    "entry_time": ts,
                    "exit_time": exit_time,
                    "direction": breakout_dir,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "stop_price": stop_price,
                    "target_price": target_price,
                    "contracts": n_contracts,
                    "range_high": range_high,
                    "range_low": range_low,
                    "pnl_points": pnl_points,
                    "pnl_dollars": pnl_dollars,
                    "commission": total_commission,
                    "net_pnl": pnl_dollars - total_commission,
                }

    return None


def run_orb_strategy(data: dict, params: dict | None = None) -> dict:
    """
    Run full ORB V10 strategy across ES and NQ with shared portfolio.

    Both instruments trade from the same capital pool, matching QC behavior.
    """
    if params is None:
        params = DEFAULT_PARAMS.copy()

    # Precompute filters and trends
    filters = _compute_daily_filters(data["spy_daily"], data["vix_daily"], params)

    # Trend uses each instrument's own daily bars (matching QC which uses futures symbol)
    es_trend = _precompute_trends(data["es_daily"], params["sma_period"])
    nq_trend = _precompute_trends(data["nq_daily"], params["sma_period"])

    # Group minute bars by date
    es_by_date = dict(list(data["es_1m"].groupby(data["es_1m"].index.date)))
    nq_by_date = dict(list(data["nq_1m"].groupby(data["nq_1m"].index.date)))

    all_dates = sorted(set(list(es_by_date.keys()) + list(nq_by_date.keys())))

    trades = []
    portfolio_value = params["initial_capital"]

    for date in all_dates:
        # Check filter
        allowed = filters.get(date, None)
        if allowed is None:
            # Date not in SPY calendar — use most recent filter
            # Find closest prior date
            prior_dates = [d for d in filters if d < date]
            if prior_dates:
                allowed = filters[prior_dates[-1]]
            else:
                allowed = True  # Default allow if no filter data yet

        if not allowed:
            continue

        # Monday check (in case date isn't in SPY calendar)
        if pd.Timestamp(date).dayofweek == 0:
            continue

        # Process each instrument for this date
        for sym, bars_by_date, trend_dict in [
            ("ES", es_by_date, es_trend),
            ("NQ", nq_by_date, nq_trend),
        ]:
            if date not in bars_by_date:
                continue

            day_bars = bars_by_date[date]

            # Opening range
            range_bars = day_bars.between_time("09:30", "09:44")
            if len(range_bars) < 5:
                continue

            range_high = range_bars["high"].max()
            range_low = range_bars["low"].min()
            range_width = range_high - range_low
            mid_price = (range_high + range_low) / 2

            if mid_price <= 0 or range_width <= 0:
                continue

            range_pct = range_width / mid_price
            if range_pct < params["min_range_pct"] or range_pct > params["max_range_pct"]:
                continue

            # Get trend
            day_trend = trend_dict.get(date, None)
            if day_trend is None:
                day_trend = _find_most_recent(trend_dict, date)

            trade = _run_day_for_instrument(
                day_bars, range_high, range_low, range_width,
                day_trend, sym, portfolio_value, params,
            )

            if trade is not None:
                trades.append(trade)
                portfolio_value += trade["net_pnl"]

    all_trades = pd.DataFrame(trades)
    if not all_trades.empty:
        all_trades = all_trades.sort_values("entry_time").reset_index(drop=True)

    # Build equity curve
    start_date = all_dates[0] if all_dates else data["es_1m"].index[0].date()
    end_date = all_dates[-1] if all_dates else data["es_1m"].index[-1].date()
    equity_curve = _build_equity_curve(all_trades, params["initial_capital"], start_date, end_date)

    stats = _compute_stats(equity_curve, all_trades, params["initial_capital"])

    return {
        "trades": all_trades,
        "equity_curve": equity_curve,
        "stats": stats,
    }


def _build_equity_curve(
    trades: pd.DataFrame,
    initial_capital: float,
    start_date,
    end_date,
) -> pd.Series:
    """Build daily equity curve from trade log."""
    dates = pd.bdate_range(start_date, end_date, freq="B")
    equity = pd.Series(initial_capital, index=dates, dtype=float)

    if trades.empty:
        return equity

    # Accumulate PnL by exit date
    daily_pnl = trades.groupby(trades["exit_time"].dt.date)["net_pnl"].sum()

    cumulative = initial_capital
    for date in dates:
        d = date.date()
        if d in daily_pnl.index:
            cumulative += daily_pnl.loc[d]
        equity.loc[date] = cumulative

    return equity


def _compute_stats(equity: pd.Series, trades: pd.DataFrame, initial_capital: float) -> dict:
    """Compute summary statistics matching QC output format."""
    daily_returns = equity.pct_change().dropna()

    n_years = len(equity) / 252
    total_return = (equity.iloc[-1] / initial_capital - 1)
    cagr = (equity.iloc[-1] / initial_capital) ** (1 / n_years) - 1 if n_years > 0 else 0

    if daily_returns.std() > 0:
        sharpe = daily_returns.mean() / daily_returns.std() * np.sqrt(252)
    else:
        sharpe = 0.0

    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    max_dd = drawdown.min()

    if not trades.empty:
        wins = (trades["net_pnl"] > 0).sum()
        total = len(trades)
        win_rate = wins / total if total > 0 else 0
    else:
        win_rate = 0
        total = 0

    return {
        "sharpe": round(sharpe, 3),
        "cagr": f"{cagr * 100:.1f}%",
        "max_dd": f"{abs(max_dd) * 100:.1f}%",
        "total_return": f"{total_return * 100:.1f}%",
        "total_trades": total,
        "win_rate": f"{win_rate * 100:.0f}%",
        "final_equity": round(equity.iloc[-1], 0),
        "initial_capital": initial_capital,
    }
