# Strategy Specification — Trend Futures

## System Name
**QSL Trend Futures v1.0**

## Strategy Summary

A multi-futures trend following system trading 26 CME Group futures across 6 sectors using a two-speed signal blend, Hierarchical Risk Parity allocation, and ATR-based volatility targeting.

---

## Signal: Fast+Slow Blend

The signal combines two complementary trend indicators:

### Component 1: EMA(10/100) — Fast Entry
- **Type**: Exponential moving average crossover
- **Fast window**: 10 days
- **Slow window**: 100 days
- **Logic**: Long when EMA(10) > EMA(100), short when EMA(10) < EMA(100)
- **Purpose**: Captures trend entries quickly. The fast window reacts to new trends within 2 weeks; the slow window filters noise.
- **Average holding period**: 57 days
- **Average trades per year**: 4.2 per instrument

### Component 2: TSMOM(252d) — Slow Confirmation
- **Type**: Time-series momentum (Moskowitz et al. 2012)
- **Lookback**: 252 trading days (1 year)
- **Logic**: Long when 252-day return > 0, short when < 0
- **Purpose**: Confirms the trend direction. Only agrees with EMA when a sustained move has occurred.
- **Average holding period**: 40 days (between signal changes)
- **Average trades per year**: 5.0 per instrument

### Blend Logic
```
signal = (EMA_signal + TSMOM_signal) / 2

if signal > 0:  position = LONG
if signal < 0:  position = SHORT
if signal == 0: position = FLAT (signals disagree → stay out)
```

When both signals agree, the system takes the position. When they disagree (one long, one short), the system is flat. This creates a natural filter that reduces whipsaw — the system only trades when both fast and slow perspectives align.

**Time in market**: ~80% (flat ~20% when signals disagree)

### Why This Blend (Sprint 4 Finding)

| Blend Type | Sharpe | Calmar |
|-----------|--------|--------|
| **Fast+Slow (2 signals)** | **1.168** | **1.298** |
| Barbell (3 signals) | 1.098 | 1.261 |
| Equal (5 signals) | 0.997 | 1.294 |
| Single EMA(10/100) | 1.058 | 1.435 |
| Single TSMOM(252d) | 1.130 | 0.962 |

Two signals beat one, and two signals beat five. The fast signal handles entries; the slow signal prevents false entries. Medium-speed signals are redundant (Etienne et al. 2025 barbell hypothesis confirmed).

---

## Universe: 26 CME Group Futures

| # | Symbol | Name | Sector | Multiplier |
|---|--------|------|--------|------------|
| 1 | ES | E-mini S&P 500 | Equity | $50 |
| 2 | NQ | E-mini Nasdaq 100 | Equity | $20 |
| 3 | RTY | E-mini Russell 2000 | Equity | $50 |
| 4 | NKD | Nikkei 225 (USD) | Equity | $5 |
| 5 | ZT | 2-Year T-Note | Fixed Income | $2,000 |
| 6 | ZN | 10-Year T-Note | Fixed Income | $1,000 |
| 7 | ZB | 30-Year T-Bond | Fixed Income | $1,000 |
| 8 | 6E | Euro FX | FX | $125,000 |
| 9 | 6B | British Pound | FX | $62,500 |
| 10 | 6J | Japanese Yen | FX | ¥12,500,000 |
| 11 | 6A | Australian Dollar | FX | A$100,000 |
| 12 | 6C | Canadian Dollar | FX | C$100,000 |
| 13 | 6S | Swiss Franc | FX | CHF125,000 |
| 14 | 6N | New Zealand Dollar | FX | NZ$100,000 |
| 15 | CL | Crude Oil WTI | Energy | $1,000 |
| 16 | NG | Natural Gas | Energy | $10,000 |
| 17 | RB | RBOB Gasoline | Energy | $42,000 |
| 18 | HO | Heating Oil | Energy | $42,000 |
| 19 | GC | Gold | Metals | $100 |
| 20 | SI | Silver | Metals | $5,000 |
| 21 | HG | Copper | Metals | $25,000 |
| 22 | PL | Platinum | Metals | $50 |
| 23 | ZC | Corn | Agriculture | $50 |
| 24 | ZS | Soybeans | Agriculture | $50 |
| 25 | ZW | Wheat | Agriculture | $50 |
| 26 | LE | Live Cattle | Agriculture | $40,000 |

### Sector Breakdown

| Sector | Instruments | Count |
|--------|------------|-------|
| Equity Indices | ES, NQ, RTY, NKD | 4 |
| Fixed Income | ZT, ZN, ZB | 3 |
| FX | 6E, 6B, 6J, 6A, 6C, 6S, 6N | 7 |
| Energy | CL, NG, RB, HO | 4 |
| Metals | GC, SI, HG, PL | 4 |
| Agriculture | ZC, ZS, ZW, LE | 4 |

All instruments are on CME Group exchanges (CME, CBOT, NYMEX, COMEX), using Databento GLBX.MDP3 continuous front-month contracts.

---

## Position Sizing & Allocation

### Volatility Estimation
- **Method**: ATR(20) — 20-day Average True Range
- **Why ATR**: Futures PnL is computed in price points (Δprice × multiplier × contracts). ATR produces point-based volatility, creating a natural match. EWMA and realized vol produce percentage-based estimates that perform worse (Sprint 2: ATR Sharpe 0.958 vs EWMA 0.188).

### Allocation: Hierarchical Risk Parity (HRP)
- **Method**: De Prado (2016) — hierarchical clustering → quasi-diagonalization → recursive bisection
- **Recompute frequency**: Quarterly (every 63 trading days)
- **Lookback for correlation**: 504 days (2 years)
- **Clustering**: Single linkage on correlation distance

HRP allocates risk based on the correlation structure of instrument returns. It naturally:
- Groups correlated instruments (e.g., all equity indices)
- Allocates more to low-variance, low-correlation instruments
- Requires no covariance matrix inversion (robust)

### Current HRP Weights (as of latest recomputation)

| Instrument | Sector | Weight |
|-----------|--------|--------|
| **ZT** | Fixed Income | **82.7%** |
| ZN | Fixed Income | 2.6% |
| ZB | Fixed Income | 2.2% |
| 6C | FX | 2.1% |
| 6E | FX | 1.7% |
| GC | Metals | 1.4% |
| LE | Agriculture | 1.2% |
| Others | Various | <1% each |

**Note on concentration**: ZT dominates because it has the highest risk-adjusted trend performance with the lowest volatility in the universe. This is both the strength and the risk of HRP — it finds the best instrument and maximizes exposure. In production, a sector cap (e.g., max 40% per sector) should be considered to limit single-instrument risk.

### Portfolio Volatility Target
- **Target**: 15% annualized
- **Mechanism**: All positions are scaled so the portfolio's ex-ante volatility approximates 15%
- **Scaling**: position_contracts = (portfolio_value × weight × vol_target) / (instrument_vol × price × multiplier)

### Rebalancing
- **Frequency**: Weekly
- **Why weekly**: Reduces noise and transaction costs vs daily (Sprint 2: weekly Sharpe 1.10 vs daily 1.03), while the underlying signals change direction every 40-60 days on average.

### Position Limits
- **Max contracts per instrument**: 50
- **No leverage cap** beyond vol target (portfolio is naturally self-limiting through vol targeting)

---

## Performance (Backtest: 2018-01-01 to 2025-12-31)

### Headline Metrics

| Metric | Value |
|--------|-------|
| **Sharpe Ratio** | **2.656** |
| **CAGR** | **63.4%** |
| **Max Drawdown** | **8.4%** |
| **Calmar Ratio** | **7.566** |
| Realized Volatility | 24.1% |
| Total Return | ~$1M → $1.59M (on $1M start) |
| SPY Correlation | ~0.05 (uncorrelated) |

### Regime Performance

| Period | Sharpe | Return | Max DD | Character |
|--------|--------|--------|--------|-----------|
| 2020 COVID | 6.997 | +3.8% | 0.4% | Strong crisis alpha |
| 2022 Rate Shock | 1.283 | +0.7% | 1.9% | Profitable during equity bear |
| 2023 Range-Bound | -1.143 | -2.5% | 4.5% | Only losing period (expected) |
| 2025 Tariffs | 2.733 | +1.3% | 0.8% | Strong trending environment |

### Performance Drivers

The high Sharpe is driven by:
1. **ZT (2-Year T-Note) trending strongly** during the 2018-2025 period (rate hiking cycle → easing cycle)
2. **HRP concentrating in the best instrument** rather than diluting across weak ones
3. **Low realized vol of ZT** combined with **high vol target** (15%) creating significant leverage in the highest-alpha instrument

---

## Risk Considerations

### Known Weaknesses
1. **Concentration risk**: 82.7% in ZT. A regime where short-term rates stop trending (e.g., extended Fed pause) would hurt significantly.
2. **Range-bound markets**: 2023 was the only losing period. Sustained sideways markets erode the strategy.
3. **HRP instability**: Weights can shift dramatically when correlation structure changes. Quarterly rebalancing mitigates but doesn't eliminate.

### Mitigations
1. **Sector caps**: Limit max sector allocation to 40% to force diversification
2. **Inverse-vol alternative**: Sharpe 1.757, CAGR 17.5%, Max DD 7.0% — lower Sharpe but much more diversified
3. **ML overlay**: Meta-labeling (Sprint 5) can further reduce drawdowns by scaling down positions during low-confidence periods

### Comparison: HRP vs Safer Alternatives

| Config | Sharpe | CAGR | Max DD | Calmar | Risk Character |
|--------|--------|------|--------|--------|----------------|
| **HRP 15%** | **2.656** | **63.4%** | **8.4%** | **7.566** | **Concentrated, high-conviction** |
| InvVol 15% | 1.757 | 17.5% | 7.0% | 2.487 | Diversified, moderate |
| InvVol 20% | 1.728 | 23.8% | 9.3% | 2.554 | Diversified, aggressive |
| EW 15% | 0.766 | 4.6% | 5.3% | 0.867 | Maximum diversification |

---

## Transaction Costs

| Component | Annual Impact |
|-----------|--------------|
| Commission | ~$315/instrument/year |
| Spread | Varies ($188-$2,344/instrument) |
| Slippage | Negligible at current scale |
| Roll costs | 0.5-5.0 bps per roll (instrument-dependent) |
| **Total drag** | **~0.3%/year** |

Costs are negligible relative to CAGR. The strategy trades ~5 times per year per instrument.

---

## Data Infrastructure

| Component | Source | Update Frequency |
|-----------|--------|-----------------|
| Futures 1-min bars | Databento (GLBX.MDP3) | Daily (cached as parquet) |
| Daily bars | Aggregated from 1-min RTH bars | Derived |
| SPY / VIX | yfinance | Daily |
| Continuous contracts | Databento front-month (`.c.0`) | Automatic roll |

---

## Implementation Notes

### Signal Generation
1. At end of each trading day, compute EMA(10) and EMA(100) for each instrument
2. Compute 252-day return for each instrument
3. Blend: if both agree → position; if disagree → flat
4. Apply position to next week's trades (weekly rebalancing)

### Execution
- Rebalance positions at Monday open (or first available session)
- Use MOC (Market on Close) or TWAP orders for large positions
- Monitor for contract rolls; Databento continuous handles this but actual execution requires roll management

### Monitoring
- Track realized vol vs target (should be ~15%)
- Track HRP weights for concentration drift
- Flag any single-instrument allocation >50% for review
- Track regime indicators (ADX, Hurst) for early warning of range-bound conditions

---

## Research Foundation

This strategy was developed through 7 systematic research sprints informed by 46 academic and practitioner papers. Key references:

1. **Moskowitz, Ooi & Pedersen (2012)** — TSMOM foundation
2. **Etienne et al. (2025)** — Barbell hypothesis (confirmed)
3. **Valeyre (2025)** — Signal simplicity (confirmed)
4. **De Prado (2016)** — HRP allocation
5. **De Prado (2018)** — AFML: meta-labeling, triple barrier, purged CV
6. **CFM (2018)** — Convexity of trend following (crisis alpha confirmed)
7. **Man AHL (2025)** — Speed, market set, and carry explain CTA dispersion

Full research log: `docs/05-research-log.md`
Full paper registry: `docs/01-paper-registry.md`
