# Research Plan — Institutional-Grade Strategy Development

## 1. Research Framework

### Universe Definition
- **Primary universe**: S&P 500 constituents + 30 major ETFs
- **Minimum criteria**: Average daily volume > $5M, price > $5
- **Survivorship bias mitigation**: Use EODHD adjusted prices. Test on both current constituents and verify on ETFs (no survivorship bias in ETFs like SPY, QQQ, XLF)
- **Total symbols**: ~200-250 liquid instruments
- **Data period**: 2014-01-01 to 2024-12-31 (10 years, 6 full market cycles)

### Data Integrity
- Adjusted close prices for all signal generation (split/dividend adjusted)
- Raw close for position sizing (actual fill price approximation)
- Volume filter: exclude days with zero volume
- Missing data: forward-fill up to 5 days, then exclude
- Corporate actions: handled by EODHD adjusted_close field

### Rebalancing Options (to be tested)
- **Daily**: highest signal fidelity, highest turnover
- **Weekly (Monday)**: reduced costs, still captures short-term signals
- **Monthly (1st trading day)**: lowest costs, suited for slower signals

### Transaction Cost Model
```
Equity commission:     $0.005/share (IB rate)
Slippage:              0.05% of trade value (conservative for liquid stocks)
Market impact:         0% (small positions relative to ADV)
Short borrowing cost:  NOT APPLICABLE (long-only strategies preferred)
```
**Justification**: Our QC validation showed stocks at $0.005/share is negligible. Slippage of 5bps is conservative for S&P 500 names with >$5M daily volume.

## 2. Hypothesis Space

### H1: Short-Term Mean Reversion (Primary Focus)
**Economic rationale**: Overreaction to short-term news creates temporary mispricings. Market microstructure (bid-ask bounce, forced selling, momentum overshoot) causes prices to revert within 1-5 days.

**Signals**:
- RSI(2) extreme oversold (< 10) → buy, hold 1-2 days
- IBS (Internal Bar Strength) < 0.20 AND RSI(3) < 30 → confirmed oversold
- Bollinger Band z-score < -2σ AND RSI < 35 → statistical extreme
- Price deviation from SMA(20) > 1.5 ATR below → structural oversold
- Consecutive down days (3+) with IBS < 0.30 → momentum exhaustion

**Expected win rate**: 50-55% with avg winner > avg loser
**Expected Sharpe**: 0.5-0.8 (based on our QC-validated V2 result of 0.674)
**Expected failure modes**: Extended bear markets (2008-2009, Mar 2020) where "oversold" stays oversold. Low-volatility grind-ups where signals rarely fire.

### H2: Cross-Sectional Momentum (Secondary)
**Economic rationale**: Winners continue to win over medium horizons (3-12 months) due to under-reaction to positive information, institutional herding, and behavioral anchoring.

**Signals**:
- 6-month return ranking → long top quintile
- 12-month return minus last month (Jegadeesh-Titman) → long top quintile
- Relative strength vs sector → overweight strongest

**Expected win rate**: 48-52% (slight edge, many small trades)
**Expected Sharpe**: 0.3-0.5
**Expected failure modes**: Momentum crashes (2009, 2020 reversals). Regime transitions where previous winners suddenly lose.

### H3: Volatility-Regime Filter (Overlay)
**Economic rationale**: Mean reversion works best in normal-to-low volatility. In high-volatility panics, mean reversion fails catastrophically (buying dips that keep dipping).

**Signals**:
- VIX level or realized vol regime
- ATR expansion/contraction
- Bollinger bandwidth

**Application**: NOT a standalone strategy. Used to FILTER H1/H2 signals — reduce exposure when volatility is extreme.

### H4: Fundamental Overlay (if EODHD supports)
**Economic rationale**: Value stocks (low P/E, high dividend yield) have a long-term return premium.

**Signals**:
- P/E ratio ranking (buy low P/E quintile)
- Dividend yield ranking
- Earnings momentum (change in EPS estimates)

**Application**: Monthly rebalance, combined with H1 for signal confirmation.

## 3. Expected Failure Modes

| Regime | H1 (Mean Rev) | H2 (Momentum) | H3 (Vol Filter) |
|--------|---------------|---------------|-----------------|
| Bull market | ✓ Moderate signals | ✓ Strong | N/A |
| Bear market | ✗ Buying falling knives | ✗ Momentum crashes | ✓ Reduces exposure |
| Sideways/Range | ✓ Many signals | ✗ No direction | N/A |
| High volatility | ✗ MR fails | ✗ Whipsaw | ✓ Key protection |
| Low volatility | ✗ Few signals | ✓ Grind-up captured | N/A |

## 4. Strategy Selection Criteria

A strategy PASSES if:
1. **Sharpe > 0.5** after costs across full 10-year period
2. **Positive** in at least 7 of 10 years
3. **Max DD < 25%** (absolute limit)
4. **Consistent across 3 sub-periods** (2014-2017, 2018-2021, 2022-2024)
5. **Parameter stable**: ±20% parameter change produces < 20% Sharpe change
6. **Survives bootstrap**: 95% CI of Sharpe excludes zero
7. **Beats SPY** on risk-adjusted basis (Sharpe, not raw return)
8. **Economically plausible**: clear explanation for why the edge exists

A strategy FAILS if:
- Sharpe < 0.3 in any 3-year sub-period
- Max DD > 30%
- Turnover > 500% annually (cost-prohibitive)
- Only works on small subset of stocks (not generalizable)
- Parameter sensitivity > 50% (overfit)

## 5. Research Execution Plan

| Phase | Task | Estimated Time | Dependency |
|-------|------|----------------|-----------|
| 1 | Research plan | Done | — |
| 2 | Data pipeline | 15 min | — |
| 3 | Feature engineering | 20 min | Phase 2 |
| 4 | Strategy generation | 30 min | Phase 3 |
| 5 | Backtesting | 30 min | Phase 4 |
| 6 | Statistical validation | 20 min | Phase 5 |
| 7 | Strategy selection | 10 min | Phase 6 |
| 8 | Production readiness | 15 min | Phase 7 |

**Total**: ~2.5 hours of autonomous execution.

## 6. Prior Knowledge (From This Session)

We have QC-validated results that inform our hypotheses:
- **RSI(2) extreme on stocks works**: 51.8% WR across 80 stocks (QC validated)
- **IBS + RSI(3) confirmation is best**: 54.9% WR (QC validated)
- **Long-only is superior**: short selling on stocks costs edge through borrowing/friction
- **1-3 day holding is optimal**: longer holds dilute the mean-reversion edge
- **Stocks > Futures for this strategy**: lower commission, no rolls, daily bars work
- **Casino Stocks V2 achieved Sharpe 0.674, CAGR 18%** on QC (the benchmark to beat)

This prior knowledge is used to INFORM hypotheses, not to pre-select strategies. All strategies must pass the full validation pipeline independently.
