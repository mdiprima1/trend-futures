# Sprint 6: Cross-Asset Dynamics & Network Effects

**Status**: Not Started
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
