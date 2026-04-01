"""
PHASE 4 — Strategy Generation Engine
PHASE 5 — Backtester

Generates candidate strategies and backtests them with realistic costs.
"""
import numpy as np
import pandas as pd
import json
from pathlib import Path
from features import compute_all_features, SIGNAL_FEATURES


# ── Strategy Definition ──

class MeanReversionStrategy:
    """
    Long-only mean reversion: buy when indicators are oversold,
    sell after N days.
    """
    def __init__(self, name, entry_rules, hold_days=1, position_pct=0.025,
                 max_positions=25, cost_per_share=0.005, slippage_pct=0.0005):
        self.name = name
        self.entry_rules = entry_rules  # list of (feature, operator, threshold)
        self.hold_days = hold_days
        self.position_pct = position_pct
        self.max_positions = max_positions
        self.cost_per_share = cost_per_share
        self.slippage_pct = slippage_pct

    def generate_signals(self, features_dict):
        """
        Generate buy signals across all stocks.
        features_dict: {ticker: features_df}
        Returns: {ticker: Series of 0/1}
        """
        signals = {}
        for ticker, feats in features_dict.items():
            mask = pd.Series(True, index=feats.index)
            for feature, op, threshold in self.entry_rules:
                if feature not in feats.columns:
                    mask = pd.Series(False, index=feats.index)
                    break
                if op == "<":
                    mask = mask & (feats[feature] < threshold)
                elif op == ">":
                    mask = mask & (feats[feature] > threshold)
                elif op == "<=":
                    mask = mask & (feats[feature] <= threshold)
                elif op == ">=":
                    mask = mask & (feats[feature] >= threshold)
            signals[ticker] = mask.astype(int)
        return signals


# ── Candidate Strategies ──

def generate_candidates():
    """Generate all candidate strategies to test."""
    candidates = []

    # ── Category 1: RSI Mean Reversion ──
    for rsi_period in [2, 3]:
        for threshold in [5, 10, 15, 20, 25]:
            for hold in [1, 2, 3]:
                candidates.append(MeanReversionStrategy(
                    name=f"RSI{rsi_period}_{threshold}_hold{hold}",
                    entry_rules=[(f"rsi_{rsi_period}", "<", threshold)],
                    hold_days=hold,
                ))

    # ── Category 2: IBS Mean Reversion ──
    for ibs_thresh in [0.10, 0.15, 0.20, 0.25]:
        for hold in [1, 2]:
            candidates.append(MeanReversionStrategy(
                name=f"IBS_{ibs_thresh}_hold{hold}",
                entry_rules=[("ibs", "<", ibs_thresh)],
                hold_days=hold,
            ))

    # ── Category 3: IBS + RSI Confirmation ──
    for ibs_t in [0.15, 0.20, 0.25]:
        for rsi_t in [25, 30, 35]:
            for hold in [1, 2, 3]:
                candidates.append(MeanReversionStrategy(
                    name=f"IBS{ibs_t}_RSI3_{rsi_t}_hold{hold}",
                    entry_rules=[("ibs", "<", ibs_t), ("rsi_3", "<", rsi_t)],
                    hold_days=hold,
                ))

    # ── Category 4: Bollinger Band Extreme ──
    for bb_t in [-2.0, -2.5, -3.0]:
        for rsi_t in [30, 35, 40]:
            for hold in [2, 3, 5]:
                candidates.append(MeanReversionStrategy(
                    name=f"BB{bb_t}_RSI3_{rsi_t}_hold{hold}",
                    entry_rules=[("bb_z_20", "<", bb_t), ("rsi_3", "<", rsi_t)],
                    hold_days=hold,
                ))

    # ── Category 5: SMA Deviation ──
    for dev_t in [-1.0, -1.5, -2.0]:
        for rsi_t in [30, 35]:
            for hold in [2, 3]:
                candidates.append(MeanReversionStrategy(
                    name=f"SMAdev{dev_t}_RSI3_{rsi_t}_hold{hold}",
                    entry_rules=[("sma_dev_atr_20", "<", dev_t), ("rsi_3", "<", rsi_t)],
                    hold_days=hold,
                ))

    # ── Category 6: Williams %R ──
    for wr_t in [-90, -95]:
        for hold in [1, 2]:
            candidates.append(MeanReversionStrategy(
                name=f"WR_{wr_t}_hold{hold}",
                entry_rules=[("williams_r", "<", wr_t)],
                hold_days=hold,
            ))

    # ── Category 7: Stochastic ──
    for k_t in [10, 15, 20]:
        for hold in [1, 2, 3]:
            candidates.append(MeanReversionStrategy(
                name=f"Stoch_{k_t}_hold{hold}",
                entry_rules=[("stoch_k", "<", k_t)],
                hold_days=hold,
            ))

    # ── Category 8: CCI Extreme ──
    for cci_t in [-200, -150, -100]:
        for hold in [2, 3]:
            candidates.append(MeanReversionStrategy(
                name=f"CCI_{cci_t}_hold{hold}",
                entry_rules=[("cci_20", "<", cci_t)],
                hold_days=hold,
            ))

    # ── Category 9: Down Days + IBS ──
    for dd in [3, 4, 5]:
        for ibs_t in [0.25, 0.30]:
            candidates.append(MeanReversionStrategy(
                name=f"Down{dd}_IBS{ibs_t}_hold2",
                entry_rules=[("down_days", ">=", dd), ("ibs", "<", ibs_t)],
                hold_days=2,
            ))

    # ── Category 10: MFI Extreme ──
    for mfi_t in [15, 20, 25]:
        for hold in [2, 3]:
            candidates.append(MeanReversionStrategy(
                name=f"MFI_{mfi_t}_hold{hold}",
                entry_rules=[("mfi_14", "<", mfi_t)],
                hold_days=hold,
            ))

    # ── Category 11: RSI(14) Weekly Oversold ──
    for rsi14_t in [20, 25, 30]:
        for rsi3_t in [35, 40]:
            candidates.append(MeanReversionStrategy(
                name=f"RSI14_{rsi14_t}_RSI3_{rsi3_t}_hold3",
                entry_rules=[("rsi_14", "<", rsi14_t), ("rsi_3", "<", rsi3_t)],
                hold_days=3,
            ))

    # ── Category 12: Multi-indicator (triple confirmation) ──
    candidates.append(MeanReversionStrategy(
        name="Triple_IBS15_RSI3_25_BB2",
        entry_rules=[("ibs", "<", 0.15), ("rsi_3", "<", 25), ("bb_z_20", "<", -2.0)],
        hold_days=2,
    ))
    candidates.append(MeanReversionStrategy(
        name="Triple_IBS20_RSI3_30_SMA15",
        entry_rules=[("ibs", "<", 0.20), ("rsi_3", "<", 30), ("sma_dev_atr_20", "<", -1.5)],
        hold_days=2,
    ))

    return candidates


# ── Backtester ──

def backtest_strategy(strategy, features_dict, price_data, benchmark_returns=None):
    """
    Backtest a strategy across all stocks.

    Args:
        strategy: MeanReversionStrategy instance
        features_dict: {ticker: features_df}
        price_data: {ticker: df with adj_close}
        benchmark_returns: Series of benchmark daily returns (optional)

    Returns: dict of metrics
    """
    signals = strategy.generate_signals(features_dict)

    all_trades = []
    daily_pnl = {}

    for ticker, sig in signals.items():
        if sig.sum() == 0:
            continue

        prices = price_data[ticker]["adj_close"]
        signal_dates = sig[sig == 1].index

        in_trade = False
        exit_date_idx = -1

        for entry_date in signal_dates:
            entry_idx = prices.index.get_loc(entry_date) if entry_date in prices.index else -1
            if entry_idx < 0 or entry_idx <= exit_date_idx:
                continue

            entry_price = float(prices.iloc[entry_idx])
            if entry_price <= 0:
                continue

            exit_idx = min(entry_idx + strategy.hold_days, len(prices) - 1)
            exit_price = float(prices.iloc[exit_idx])
            exit_date = prices.index[exit_idx]

            # PnL
            gross_return = (exit_price - entry_price) / entry_price
            cost = 2 * strategy.cost_per_share / entry_price + 2 * strategy.slippage_pct
            net_return = gross_return - cost

            all_trades.append({
                "ticker": ticker,
                "entry_date": entry_date,
                "exit_date": exit_date,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "gross_return": gross_return,
                "net_return": net_return,
                "won": net_return > 0,
            })

            exit_date_idx = exit_idx

            # Daily PnL attribution
            d = exit_date.strftime("%Y-%m-%d") if hasattr(exit_date, 'strftime') else str(exit_date)
            daily_pnl[d] = daily_pnl.get(d, 0) + net_return * strategy.position_pct

    if not all_trades:
        return None

    trades_df = pd.DataFrame(all_trades)

    # Metrics
    n = len(trades_df)
    wins = trades_df["won"].sum()
    win_rate = wins / n * 100

    avg_win = trades_df.loc[trades_df["won"], "net_return"].mean() * 100 if wins > 0 else 0
    avg_loss = trades_df.loc[~trades_df["won"], "net_return"].mean() * 100 if n - wins > 0 else 0

    # Build equity curve
    daily_pnl_series = pd.Series(daily_pnl).sort_index()
    daily_pnl_series.index = pd.to_datetime(daily_pnl_series.index)

    # Fill missing days with 0
    full_idx = pd.bdate_range(daily_pnl_series.index[0], daily_pnl_series.index[-1])
    daily_pnl_series = daily_pnl_series.reindex(full_idx, fill_value=0)

    equity = (1 + daily_pnl_series).cumprod()
    total_return = float(equity.iloc[-1] - 1) * 100

    n_years = len(daily_pnl_series) / 252
    cagr = (equity.iloc[-1] ** (1 / n_years) - 1) * 100 if n_years > 0 else 0

    daily_ret = daily_pnl_series
    sharpe = float(daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    sortino_denom = daily_ret[daily_ret < 0].std()
    sortino = float(daily_ret.mean() / sortino_denom * np.sqrt(252)) if sortino_denom > 0 else 0

    peak = equity.cummax()
    dd = (equity - peak) / peak
    max_dd = float(dd.min()) * 100

    trades_per_year = n / n_years if n_years > 0 else 0
    turnover = trades_per_year * 2 * strategy.position_pct * 100  # 2-way turnover as % of portfolio

    # Sub-period analysis
    sub_periods = {}
    for label, (start, end) in [
        ("2014-2017", ("2014-06-01", "2017-12-31")),
        ("2018-2021", ("2018-01-01", "2021-12-31")),
        ("2022-2024", ("2022-01-01", "2024-12-31")),
    ]:
        mask = (daily_pnl_series.index >= start) & (daily_pnl_series.index <= end)
        sub = daily_pnl_series[mask]
        if len(sub) > 60:
            sub_sharpe = float(sub.mean() / sub.std() * np.sqrt(252)) if sub.std() > 0 else 0
            sub_eq = (1 + sub).cumprod()
            sub_ret = float(sub_eq.iloc[-1] - 1) * 100
            sub_periods[label] = {"sharpe": round(sub_sharpe, 3), "return_pct": round(sub_ret, 2)}

    return {
        "strategy": strategy.name,
        "n_trades": n,
        "win_rate": round(win_rate, 2),
        "avg_win_pct": round(avg_win, 3),
        "avg_loss_pct": round(avg_loss, 3),
        "total_return_pct": round(total_return, 2),
        "cagr_pct": round(cagr, 2),
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "max_dd_pct": round(max_dd, 2),
        "trades_per_year": round(trades_per_year, 1),
        "turnover_pct": round(turnover, 1),
        "n_stocks_traded": trades_df["ticker"].nunique(),
        "sub_periods": sub_periods,
        "equity_curve": equity,
    }
