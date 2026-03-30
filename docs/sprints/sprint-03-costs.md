# Sprint 3: Transaction Costs & Execution Reality

**Status**: Not Started
**Phase**: A (Foundation)
**Depends on**: Sprint 2

## Objective

Build a realistic cost model and verify that strategy results survive implementation friction. Model commissions, spreads, slippage, market impact, and roll costs per instrument.

## Key Papers

1. **Chevalier & Darolles 2020** — trading costs didn't erode trend alpha; volatility did
2. **Quantica 2025** — capacity constraints and liquidity concentration
3. **Zakamulin & Giner 2022** — optimal lookback lengthens with costs

## Scope

- Per-instrument cost tables (commission + spread + slippage)
- Market impact model (square-root model based on volume participation)
- Futures roll cost modeling (calendar spread, contango/backwardation)
- Turnover analysis by signal type × instrument
- Capacity estimation per market
- Optimal lookback re-evaluation after costs
- Net Sharpe comparison: gross vs net across all Sprint 1 signals

## Deliverables

1. Cost model integrated into backtest engine
2. Net Sharpe rankings (may reorder Sprint 1 results)
3. Capacity limits per market
4. Roll cost analysis and optimal roll timing
