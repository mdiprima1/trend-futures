# Casino V1 — Research Plan

## Core Concept

Replicate casino house odds through systematic futures trading:
- Make **multiple defined-outcome bets per day** using technical indicators
- Each bet has **known win rate, known risk/reward, known expected value**
- Control risk per bet (fixed % of capital)
- The edge compounds through **frequency × small edge** (Law of Large Numbers)

The casino doesn't win every hand — it wins 51-55% of the time and makes millions of hands.

## The Math (Fundamental Law of Active Management)

```
IR = IC × √(BR)
```
- **IR** = Information Ratio (target: 2.0 = excellent Sharpe)
- **IC** = Information Coefficient (per-bet accuracy: 0.05-0.10)
- **BR** = Breadth (number of independent bets per year)

| IC (per-bet skill) | Bets needed for IR=2.0 | Bets per day |
|--------------------|-----------------------|-------------|
| 0.02 (very low) | 10,000/year | 40/day |
| 0.05 (modest) | 1,600/year | 6.4/day |
| 0.10 (good) | 400/year | 1.6/day |

**Target: 5-10 independent bets per day across 4-5 uncorrelated instruments.**

## What the Research Shows

### Indicators with Proven Edge on Futures

| Setup | Win Rate | Profit Factor | Best Instrument | Frequency |
|-------|----------|--------------|-----------------|-----------|
| RSI(2) mean reversion | 71-91% | ~3.0 | ES, NQ | ~30/year |
| Filtered ORB | 65% | 2.0 | NQ | ~40/year |
| Keltner channel MR | 77% | 2.0 | ES | ~25/year |
| Candlestick + RSI filter | 75-83% | 2.5-2.7 | ES (15-min) | ~60/year |
| CL mean reversion (Tue/Thu) | High | ~1.5 | CL | 50-150/year |
| Gap fills (NQ Tue) | 70% | ~1.3 | NQ | ~50/year |
| Volatility squeeze | 80% | Moderate | ES | ~20/year |
| VWAP deviation | ~65% | ~1.5 | CL, ES | 2-3/week |
| IB single break | 76-84% | Varies | NQ > ES | Daily |

### Key Insight: Combine Across Uncorrelated Instruments

ES/NQ are 90%+ correlated — running the same setup on both is NOT 2 independent bets. But:
- **ES + CL**: low correlation → 2 genuine independent bets
- **ES + GC**: low correlation → 2 genuine independent bets
- **ES + ZN**: moderate negative correlation → diversification benefit
- **CL + GC**: moderate correlation → ~1.5 independent bets

**Effective independence across 5 instruments (ES, NQ, CL, GC, ZN): ~3.5 independent bet streams.**

## Research Architecture

### Phase 1: Indicator Testing (Sprint 1-3)

#### Sprint 1: Mean Reversion Indicators
**Goal**: Test every mean reversion setup on the top 5 most liquid futures.

Indicators to test:
- RSI(2), RSI(3), RSI(5) with various thresholds (10/90, 15/85, 20/80, 25/75, 30/70)
- Bollinger Band touches (1σ, 2σ, 3σ)
- Keltner Channel touches and mean reversion
- VWAP deviation (1σ, 2σ, 3σ from VWAP)
- IBS (Internal Bar Strength) extremes
- Price vs SMA deviation (oversold/overbought)

For each setup × instrument:
- Win rate
- Average win / average loss
- Profit factor
- Expected value per trade (in $)
- Frequency (trades per day/week)
- Time of day analysis (is the edge concentrated in specific hours?)
- Holding period distribution

Timeframes: 1-min, 5-min, 15-min, 30-min, 60-min, daily
Instruments: ES, NQ, CL, GC, ZN

#### Sprint 2: Breakout / Momentum Indicators
**Goal**: Test breakout and continuation setups.

Indicators to test:
- Opening Range Breakout (5-min, 15-min, 30-min, 60-min ranges)
- Initial Balance breakout/extension
- ATR channel breakouts
- Donchian channel breakouts (intraday)
- Volume breakouts (relative volume > 2x average)
- Momentum thrust (ROC > 2σ)
- MACD crossovers (optimized for intraday)
- Moving average crossovers (fast: 5/15, 10/30)

Same analysis framework as Sprint 1.

#### Sprint 3: Pattern & Composite Indicators
**Goal**: Test candlestick patterns, composite indicators, and filtered setups.

Indicators to test:
- Candlestick patterns: engulfing, hammer, doji, inside bar, three soldiers/crows
- Each pattern filtered by RSI, volume, VWAP position
- Composite: RSI(2) + Bollinger + Volume confirmation
- Composite: ORB + VWAP alignment + trend filter
- Day-of-week effects per instrument
- Time-of-day effects per instrument

### Phase 2: Bet Construction (Sprint 4-5)

#### Sprint 4: Triple Barrier Optimization
**Goal**: For each winning indicator, find optimal profit target / stop loss / time limit.

- Apply De Prado triple barrier to every profitable setup
- Optimize PT/SL ratio: 1:1, 1.5:1, 2:1, 3:1
- Optimize time barrier: 5 min, 15 min, 30 min, 1 hour, end of day
- Compute the full outcome distribution for each bet type
- Identify which setups have the most stable edge

#### Sprint 5: Bet Catalog
**Goal**: Create the "house playbook" — a catalog of all defined bets with known statistics.

Each bet in the catalog has:
- Entry condition (specific indicator + threshold + filters)
- Profit target (in ATR units)
- Stop loss (in ATR units)
- Time limit
- Win rate (from backtest)
- Average win ($)
- Average loss ($)
- Expected value per bet ($)
- Frequency (bets per day per instrument)
- Instrument(s)
- Statistical significance (p-value, sample size)

### Phase 3: Portfolio of Bets (Sprint 6-7)

#### Sprint 6: Independence Analysis
**Goal**: Determine true independence between bets.

- Correlation matrix between all bet returns
- Effective number of independent bets (Meucci framework)
- Which bets can run simultaneously without correlation drag?
- Optimal bet schedule across instruments and time of day

#### Sprint 7: Full Casino System
**Goal**: Combine everything into the integrated system.

- Portfolio of bets with Kelly-based sizing
- Daily loss limit (2% of capital)
- Per-bet risk limit (0.5% of capital)
- Correlation-adjusted position sizing
- Monte Carlo simulation of outcomes
- Walk-forward validation
- **QC backtest for validation** (since intraday positions close same day, no roll issues!)

## Instruments

### Tier 1 (most liquid, primary focus)
| Symbol | Name | Why |
|--------|------|-----|
| ES | S&P 500 E-mini | Highest ADV, best studied, mean-reversion works |
| NQ | Nasdaq 100 E-mini | Best ORB edge, high volatility |
| CL | Crude Oil WTI | Uncorrelated to equities, mean-reversion edge |

### Tier 2 (add for diversification)
| Symbol | Name | Why |
|--------|------|-----|
| GC | Gold | Uncorrelated, breakout edge on Keltner |
| ZN | 10-Year Treasury | Negatively correlated to equities |

### Tier 3 (test if Tier 1-2 produce enough bets)
| Symbol | Name | Why |
|--------|------|-----|
| 6E | Euro FX | FX dynamics, different from commodities |
| NG | Natural Gas | Highest volatility, mean-reversion potential |

## Why This Works Where Trend Following Didn't

1. **No roll problem**: All positions close intraday. No overnight holds = no roll gaps.
2. **QC validation is reliable**: Intraday futures backtests on QC don't suffer from the contract mapping issues that killed our trend system.
3. **More bets = faster convergence**: The Law of Large Numbers means small edges compound reliably with enough repetitions.
4. **Defined risk per bet**: Every trade has a pre-set stop loss. No open-ended exposure.
5. **Testable on actual data**: We have 778K 1-minute bars per instrument. That's ~2,000 trading days × 390 minutes = enough to test with statistical significance.

## Data Requirements

Already available:
- ES: 778,661 1-min bars (2018-2025)
- NQ: 778,658 1-min bars
- CL: 761,757 1-min bars
- ZN: 643,805 1-min bars

Need to re-download (sparse data):
- GC: Only 34,658 bars — likely data issue, need to re-fetch

## Success Criteria

A bet qualifies for the catalog if:
1. Win rate × avg win > (1 - win rate) × avg loss (positive expected value)
2. Sample size > 100 trades
3. Profit factor > 1.3
4. Edge is consistent across 3+ years (not regime-dependent)
5. Survives realistic transaction costs (commission + 1 tick slippage)
6. Not correlated > 0.5 with another bet already in the catalog

The full system target:
- **5+ independent bet streams across 3+ instruments**
- **Sharpe > 2.0 (annualized)**
- **Max daily drawdown < 2%**
- **Validated on QC with actual contract execution**
