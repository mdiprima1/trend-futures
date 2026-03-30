# Sprint 1: Signal Landscape & Baseline

**Status**: Not Started
**Phase**: A (Foundation)
**Depends on**: Calibrated backtest environment (done)

## Objective

Implement and compare all major trend signal types on our 6-market core universe. Establish which signals work best on which markets, and create a robust baseline that all future sprints improve upon.

## Key Papers for This Sprint

1. **Sepp & Lucic 2025** — unified taxonomy, P&L = f(autocorrelation)
2. **Valeyre 2025** — single EMA sufficiency, anti-overfitting
3. **Moskowitz et al. 2012** — TSMOM foundation
4. **Baz et al. 2015** — MACD equivalence to weighted TSMOM
5. **Babu et al. 2020** — multi-window TSMOM blend

## Data Requirements

- ES, NQ, ZN, GC, CL, 6E — daily bars (aggregated from Databento 1-min)
- SPY, VIX daily (from yfinance, already cached)
- Period: 2010-2025 (extend from 2018 for more robust signal evaluation)

## Signals to Implement

### A. Moving Average Crossover

| ID | Fast | Slow | MA Type | Notes |
|----|------|------|---------|-------|
| MA-01 | 10 | 30 | EMA | Fast |
| MA-02 | 20 | 50 | EMA | Standard |
| MA-03 | 50 | 200 | SMA | Classic trend |
| MA-04 | 10 | 100 | EMA | Asymmetric: fast entry, slow exit |
| MA-05 | 20 | 50 | Hull | Low lag variant |

### B. TSMOM (Binary Sign of Past Return)

| ID | Lookback | Notes |
|----|----------|-------|
| TS-01 | 21 days (1 month) | Short-term |
| TS-02 | 63 days (3 months) | Medium |
| TS-03 | 126 days (6 months) | |
| TS-04 | 252 days (12 months) | Moskowitz original |
| TS-05 | Blend: equal weight 21/63/126/252 | Babu et al. |

### C. Breakout

| ID | Entry | Exit | Notes |
|----|-------|------|-------|
| BR-01 | 20-day high/low | 10-day reversal | Turtle System 1 |
| BR-02 | 55-day high/low | 20-day reversal | Turtle System 2 |
| BR-03 | 20-day ATR channel (2x) | Channel reversal | Keltner variant |

### D. MACD Variants

| ID | Fast | Slow | Signal | Notes |
|----|------|------|--------|-------|
| MC-01 | 12 | 26 | 9 | Standard |
| MC-02 | 8 | 21 | 5 | Faster variant |
| MC-03 | 16 | 36 | 12 | Slower variant |

### E. Single EMA (Valeyre Reference)

| ID | Period | Notes |
|----|--------|-------|
| SE-01 | 20 | Price vs EMA(20) |
| SE-02 | 50 | Price vs EMA(50) |
| SE-03 | 100 | Price vs EMA(100) |

**Total signals: 18**

## Position Sizing (Sprint 1 Baseline)

For this sprint, use simple inverse-volatility scaling:
```
position_size = target_risk / (ATR(20) * multiplier)
```
- Target risk per instrument: 20 bps of portfolio (1/6 of ~12% vol target ÷ √6)
- Max position: 20 contracts
- Equal allocation across 6 instruments

This will be replaced with proper risk parity and HRP in Sprint 2.

## Cost Model (Sprint 1 Baseline)

Simple fixed cost per trade:
- Commission: $2.10 round trip per contract
- Slippage: 1 tick per side (varies by instrument)
- No market impact modeling yet (Sprint 3)

## Evaluation Metrics

For each signal × instrument combination:

| Metric | How Computed |
|--------|-------------|
| Sharpe (annualized) | mean(daily_ret) / std(daily_ret) * √252 |
| Max Drawdown | max peak-to-trough |
| CAGR | (final/initial)^(1/years) - 1 |
| Turnover (annual) | Sum of |position_change| / avg_position |
| Win Rate | % of profitable trades |
| Profit Factor | Gross profit / gross loss |
| Avg Win / Avg Loss | Ratio of average winning trade to average losing trade |
| Calmar Ratio | CAGR / Max DD |

## Deliverables

1. **Signal comparison table**: All 18 signals × 6 instruments, ranked by Sharpe
2. **Aggregate portfolio results**: Equal-weight portfolio of each signal across all instruments
3. **Autocorrelation analysis**: Per-instrument return autocorrelation at various lags (validates Sepp & Lucic theory)
4. **Signal correlation matrix**: How correlated are the signals with each other?
5. **Best-of-breed selection**: Top 3-5 signals to carry forward into Sprint 2
6. **Jupyter notebook** with all analysis and visualizations

## Implementation Plan

### Step 1: Extend data fetcher
- Add ZN, GC, CL, 6E to Databento download
- Extend date range to 2010-01-01 if affordable
- Build daily bar aggregation for all instruments

### Step 2: Signal engine
- Create `src/signals.py` with a base class and implementations for all 18 signals
- Each signal takes daily OHLCV and returns a pd.Series of positions (-1, 0, +1 or continuous)

### Step 3: Backtest engine
- Create `src/backtest.py` — vectorized daily backtest
- Input: signal series + daily bars + params
- Output: equity curve, trade log, stats

### Step 4: Run all combinations
- 18 signals × 6 instruments = 108 backtests
- Store results in structured format

### Step 5: Analysis
- Rank signals, analyze autocorrelation, produce report
- Select top signals for Sprint 2

## Notes

- Do NOT optimize parameters at this stage. Use standard values from literature.
- The goal is to understand the landscape, not to find the "best" signal.
- Any signal with Sharpe > 0.3 on the aggregate portfolio is worth investigating further.
- Pay attention to turnover — high-Sharpe signals that trade constantly may not survive costs.
