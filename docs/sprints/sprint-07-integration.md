# Sprint 7: Full System Integration & Stress Testing

**Status**: Not Started
**Phase**: C (Integration)
**Depends on**: Sprints 1-6

## Objective

Combine all components into a production-ready system. Validate rigorously. Stress test across regimes.

## Key Papers

1. **Man AHL 2025** — speed, market set, carry explain CTA dispersion
2. **Kaminski 2025** — crisis vs correction framework
3. **Kaminski & Wen 2025** — drawdown patterns and recovery
4. **CFM 2018** — convexity of trend following

## Scope

### Integration
- Combine best signals (Sprint 1), sizing (Sprint 2), costs (Sprint 3)
- Add regime overlay (Sprint 4), ML enhancement (Sprint 5), cross-asset (Sprint 6)
- Full 30-40 market universe

### Risk Management
- Portfolio-level vol targeting with dynamic scaling
- Drawdown controls (proportional deleveraging)
- Correlation-based exposure limits
- Sector concentration limits

### Validation
- Walk-forward out-of-sample testing
- CPCV with deflated Sharpe ratio
- QSL 8-Gate evaluation
- Monte Carlo robustness (parameter perturbation)
- Regime-specific analysis: bull, bear, crisis, range-bound

### Stress Testing
- 2008 Financial Crisis
- 2020 COVID crash and V-recovery
- 2022 inflation/rate shock
- 2023 range-bound low-vol
- 2025 tariff-driven volatility
- Hypothetical: sustained mean-reversion regime

### Crisis Alpha Analysis
- Correlation with equity drawdowns
- Conditional Sharpe during equity >10% drawdowns
- Recovery analysis after CTA drawdowns

## Deliverables

1. Integrated system code (production-ready)
2. Full backtest report (2010-2025)
3. 8-Gate evaluation score
4. Stress test results across all regimes
5. Crisis alpha documentation
6. Parameter sensitivity analysis
7. Capacity and scalability assessment
8. Implementation plan for live trading
