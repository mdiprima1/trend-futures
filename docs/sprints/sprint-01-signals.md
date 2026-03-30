# Sprint 1: Signal Landscape & Baseline

**Status**: COMPLETE (2026-03-30)
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

---

## Results (2026-03-30)

### Top 10 Portfolio-Level Signals (Equal-Weight Across 6 Instruments)

| Rank | Signal | Name | Family | Speed | Portfolio Sharpe | CAGR | Max DD |
|------|--------|------|--------|-------|-----------------|------|--------|
| 1 | TS-04 | TSMOM(252d) | TS | slow | 0.974 | 1.22% | 1.60% |
| 2 | MA-04 | EMA(10/100) | MA | asymmetric | 0.910 | 1.31% | 1.87% |
| 3 | MA-03 | SMA(50/200) | MA | slow | 0.861 | 1.15% | 1.65% |
| 4 | MA-02 | EMA(20/50) | MA | medium | 0.783 | 1.16% | 1.76% |
| 5 | SE-02 | Price>EMA(50) | SE | medium | 0.745 | 1.05% | 1.93% |
| 6 | TS-05 | TSMOM(blend) | TS | blend | 0.739 | 0.99% | 1.80% |
| 7 | SE-03 | Price>EMA(100) | SE | slow | 0.732 | 1.04% | 2.43% |
| 8 | BR-02 | Donchian(55/20) | BR | slow | 0.728 | 0.88% | 1.75% |
| 9 | TS-02 | TSMOM(63d) | TS | medium | 0.722 | 1.02% | 2.02% |
| 10 | MA-01 | EMA(10/30) | MA | fast | 0.691 | 1.01% | 2.41% |

Note: CAGR and Max DD are low because position sizing uses only 20bps risk per instrument (Sprint 1 baseline). Absolute returns will scale with leverage in Sprint 2.

### Best Signal per Instrument

| Instrument | Best Signal | Sharpe | CAGR | Max DD | Trades |
|------------|------------|--------|------|--------|--------|
| ES | TSMOM(63d) | 0.563 | 1.4% | 4.1% | 89 |
| NQ | SMA(50/200) | 0.724 | 1.6% | 3.6% | 8 |
| ZN | EMA(20/50) | 0.742 | 1.8% | 3.7% | 27 |
| GC | EMA(10/100) | 0.933 | 3.0% | 7.6% | 29 |
| CL | TSMOM(21d) | 0.492 | 1.2% | 3.0% | 195 |
| 6E | Price>EMA(100) | 0.245 | 0.7% | 6.5% | 95 |

### Family Comparison

| Family | Avg Portfolio Sharpe | Notes |
|--------|---------------------|-------|
| TS (TSMOM) | 0.660 | Best family overall |
| MA (Moving Avg) | 0.584 | Strong, especially slow/asymmetric |
| SE (Single EMA) | 0.498 | Validates Valeyre (2025) |
| BR (Breakout) | 0.407 | Solid but fewer variants tested |
| MC (MACD) | -0.154 | **Negative on aggregate** — too fast/noisy |

### Speed Comparison

| Speed | Avg Portfolio Sharpe |
|-------|---------------------|
| Asymmetric (fast entry/slow exit) | 0.910 |
| Blend (multi-window) | 0.739 |
| Slow | 0.642 |
| Medium | 0.460 |
| Fast | 0.080 |

### Autocorrelation Analysis

| Symbol | Lag 1 | Lag 5 | Lag 21 | Lag 63 | Lag 252 |
|--------|-------|-------|--------|--------|---------|
| ES | -0.171 | -0.047 | -0.046 | 0.021 | 0.023 |
| NQ | -0.144 | -0.034 | -0.043 | 0.009 | 0.033 |
| ZN | -0.019 | -0.005 | 0.005 | -0.002 | 0.026 |
| GC | 0.012 | -0.017 | 0.054 | -0.019 | -0.022 |
| CL | -0.010 | -0.003 | -0.004 | -0.001 | -0.000 |
| 6E | 0.006 | 0.001 | 0.005 | 0.002 | 0.006 |

Key findings: Short-term autocorrelation is negative (mean-reversion), long-term is weakly positive (trending). This explains why slow signals outperform fast ones.

### Signal Correlations

- Overall average signal correlation: 0.467
- Breakout family most correlated internally (0.765)
- MA family least correlated internally (0.409) — different speeds provide diversification

### Key Findings

1. **Slow signals dominate**: TSMOM(252d) and SMA(50/200) are the top performers. Confirms the literature — trend following works best at longer horizons.
2. **Asymmetric wins**: EMA(10/100) — fast entry, slow exit — is the #2 signal. This makes intuitive sense: get in quickly when a trend starts, stay in until it clearly reverses.
3. **MACD is negative**: All 3 MACD variants produced negative aggregate Sharpe. The standard MACD parameters are too noisy for futures trend following at daily frequency.
4. **Valeyre confirmed**: Single EMA average Sharpe (0.498) captures most of the trend premium vs all signals average (0.446). Simple signals work.
5. **GC is the most trendable**: Gold produced the highest per-instrument Sharpe across most signals. 6E (Euro FX) is the weakest.
6. **Short-term autocorrelation is negative**: This is critical — it means trend strategies that trade too frequently (fast signals) will systematically lose to mean-reversion. Only medium-to-slow signals capture the positive long-term autocorrelation.

### Signals Selected for Sprint 2

1. **TS-04** — TSMOM(252d): Best overall portfolio Sharpe
2. **MA-04** — EMA(10/100): Best asymmetric; fast entry, slow exit
3. **MA-03** — SMA(50/200): Classic, robust, low turnover
4. **MA-02** — EMA(20/50): Strong medium-speed signal
5. **SE-02** — Price>EMA(50): Valeyre-validated simple signal
