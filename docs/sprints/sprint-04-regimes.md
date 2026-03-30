# Sprint 4: Multi-Scale Signal Blending & Regime Detection

**Status**: COMPLETE (2026-03-30)
**Phase**: B (Enhancement)
**Depends on**: Sprint 3

## Objective

Combine signals across timeframes and detect market regimes to activate/deactivate trend strategies. Test the barbell hypothesis (short + long, skip medium).

## Key Papers

1. **Etienne et al. 2025** — barbell horizon structure (short + long, medium redundant)
2. **Zakamulin & Giner 2024** — optimal rules under regime switching
3. **Levy & Lopes 2021** — dynamic momentum learning

## Scope

- Multi-speed trend blending: equal weight vs barbell (short + long only)
- Regime filters: ADX, Hurst exponent, entropy, HMM
- Adaptive lookback: KAMA, Kalman filter, dynamic momentum
- CUSUM filters (De Prado) for event-driven sampling
- Signal weighting: static vs dynamic (based on regime)

## Deliverables

1. Optimal signal blend (multi-speed) with documented tradeoffs
2. Regime detection framework
3. CUSUM event sampling implementation
4. Comparison: static blend vs regime-adaptive blend

---

## Results (2026-03-30)

### All Signals Ranked

| Rank | Signal | Type | Sharpe | CAGR | Max DD | Calmar | In Market |
|------|--------|------|--------|------|--------|--------|-----------|
| 1 | **Fast+Slow** | blend | **1.168** | 5.7% | 4.4% | **1.298** | 80% |
| 2 | Barbell+Hurst | regime | 1.156 | 4.5% | 4.4% | 1.017 | 63% |
| 3 | Barbell (S+L) | blend | 1.098 | **6.0%** | 4.7% | 1.261 | 96% |
| 4 | FastSlow+ADX | regime | 1.050 | 4.5% | 4.2% | 1.067 | 63% |
| 5 | Barbell+ADX | regime | 1.000 | 4.6% | 4.7% | 0.980 | 76% |
| 6 | Equal Blend (5) | blend | 0.997 | 5.4% | 4.2% | 1.294 | 97% |
| 7 | Barbell+CUSUM | regime | 0.991 | 5.4% | 5.1% | 1.051 | 96% |
| 8 | Consensus (4/5) | blend | 0.971 | 4.0% | 4.1% | 0.974 | 50% |
| 9 | Barbell+VolReg | regime | 0.816 | 3.7% | 4.6% | 0.801 | 77% |
| 10 | Consensus+ADX | regime | 0.741 | 2.6% | 4.2% | 0.629 | 40% |

Best Sprint 1 baseline: TSMOM(252d) Sharpe=1.130

### Key Findings

**1. Fast+Slow blend is the winner (Sharpe 1.168, Calmar 1.298)**
Just two signals — EMA(10/100) + TSMOM(252d) — produce the best risk-adjusted returns. The fast signal captures entries; the slow signal confirms the trend. This is the simplest and best blend.

**2. Etienne (2025) barbell hypothesis CONFIRMED**
Barbell (S+L) Sharpe=1.098 beats Equal Blend of all 5 at Sharpe=0.997. Medium-term signals (EMA 20/50, Price>EMA 50) are indeed redundant when short + long are present.

**3. Regime filters mostly hurt more than they help**
- Only **Barbell+Hurst** improved on the base barbell (Sharpe 1.156 vs 1.098)
- ADX, CUSUM, and VolReg filters all reduced Sharpe
- Regime filters reduce time in market (63-77%) which cuts returns more than it cuts risk
- The base signals are already slow enough that they self-filter for trends

**4. Pure blends outperform regime-filtered blends**
Blend avg Sharpe: 1.058 vs Regime avg: 0.959. The overhead of regime detection (missed re-entries, delayed signals) outweighs the benefit of avoiding whipsaw.

**5. Hurst is the only useful regime filter**
Barbell+Hurst (Sharpe 1.156) slightly beats the base barbell. Hurst exponent correctly identifies trending vs mean-reverting regimes, but the improvement is marginal (+0.058 Sharpe) at the cost of being in market only 63% of the time.

### Signals Carried Forward

1. **BL-FS (Fast+Slow)**: Best Sharpe and Calmar. Simple two-signal blend.
2. **BL-BAR (Barbell)**: Highest CAGR. Three-signal blend confirming the barbell thesis.
3. **RF-BAR-HUR (Barbell+Hurst)**: Best regime-filtered signal. Useful as a conservative variant.
4. Keep individual **TS-04** and **MA-04** as single-signal baselines.
