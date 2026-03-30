# Sprint 4: Multi-Scale Signal Blending & Regime Detection

**Status**: Not Started
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
