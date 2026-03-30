# Sprint 6: Cross-Asset Dynamics & Network Effects

**Status**: COMPLETE (2026-03-30)
**Phase**: B (Enhancement)
**Depends on**: Sprint 5

## Objective

Exploit lead-lag relationships across futures markets. Add carry and value as complementary signals. Implement network momentum.

## Key Papers

1. **Oxford 2025** — network momentum across 28 futures (0.645 Sharpe)
2. **Koijen et al. 2018** — carry as complementary signal
3. **Jiang & Liu 2024** — factor momentum in commodity futures

## Scope

- Cross-asset correlation structure (rolling, DCC-GARCH)
- Lead-lag detection (Granger causality, transfer entropy, mutual information)
- Network momentum model
- Cross-sectional momentum (relative strength ranking)
- Carry signal construction (roll yield per instrument)
- Value signal (deviation from long-run fundamental)
- Multi-factor combination: trend + carry + value + network

## Deliverables

1. Lead-lag map across full universe
2. Network momentum signal implementation
3. Carry and value signal implementations
4. Multi-factor portfolio combining trend + carry + value
5. Comparison: trend-only vs multi-factor

---

## Results (2026-03-30)

### Lead-Lag Analysis

Cross-correlations are weak (max |0.163|) across the 6-instrument universe. Strongest relationships:
- ES leads 6E by 1 day (corr 0.149)
- ES and NQ are negatively correlated at lag 1 (-0.163) — mean-reversion between them
- ZN leads ES by 1 day (corr 0.100)

**Conclusion**: Lead-lag effects are too weak to exploit profitably with only 6 instruments. This may improve with 20+ instruments where sector-level lead-lag (e.g., oil leads airline stocks) becomes detectable.

### Individual Signal Performance

| Signal | Sharpe | CAGR | Max DD |
|--------|--------|------|--------|
| **Trend (Fast+Slow)** | **1.168** | **5.7%** | **4.4%** |
| Carry | 0.794 | 3.9% | 5.8% |
| Network Momentum | 0.674 | 3.9% | 7.4% |
| Cross-Sectional Momentum | 0.519 | 1.2% | 3.5% |

Trend dominates all complementary signals individually.

### Multi-Factor Combinations

| Combination | Sharpe | CAGR | Max DD | vs Trend |
|-------------|--------|------|--------|----------|
| **Trend-only** | **1.168** | **5.7%** | **4.4%** | baseline |
| Trend+XSmom (70/30) | 1.168 | 5.7% | 4.4% | 0.000 |
| Full Multi-Factor | 1.082 | 5.7% | 5.7% | -0.086 |
| Trend-Heavy Multi | 1.011 | 5.3% | 6.3% | -0.157 |
| Trend+Carry (70/30) | 0.989 | 5.3% | 6.1% | -0.179 |
| Trend+Network (70/30) | 0.947 | 5.2% | 5.4% | -0.221 |

**No multi-factor combination beats pure trend.**

### Key Findings

1. **Trend is king on a small universe** — with 6 instruments, cross-asset signals add noise, not alpha. Pure trend (Fast+Slow) remains the best signal.

2. **Cross-sectional momentum needs more instruments** — ranking 6 instruments is too noisy. The Oxford (2025) network momentum paper used 28 futures. This signal will become valuable when we expand to 20+ instruments.

3. **Carry hurts Sharpe** (-0.179 vs trend-only at 70/30 blend). Our carry proxy (return momentum) is too correlated with the trend signal itself. A proper carry signal using actual calendar spreads (front-back) would be less correlated and more additive.

4. **Lead-lag effects are negligible** at daily frequency among 6 liquid instruments. These markets are highly efficient at the daily horizon.

5. **Practical implication for the final system**: Keep trend as the primary signal. Add carry/network/XSmom only after expanding the universe (Sprint 7+). With 30+ instruments, sector-level effects and relative value will provide genuine diversification.

### What Changes with More Instruments

| Factor | 6 Instruments | 20+ Instruments |
|--------|--------------|-----------------|
| Cross-sectional momentum | Noisy | Meaningful ranking |
| Network momentum | Weak correlations | Sector-level lead-lag |
| Carry | Redundant with trend | Independent factor (actual roll yield) |
| HRP allocation | Over-concentrates | Proper sector clustering |
