# Sprint 2: Volatility Targeting & Position Sizing

**Status**: Not Started
**Phase**: A (Foundation)
**Depends on**: Sprint 1 (top signals selected)

## Objective

Establish the risk framework for the trend-following system. Compare position sizing methods and portfolio construction approaches. This sprint determines how much to trade, not what to trade.

## Key Papers

1. **Zakamulin & Giner 2022** — optimal lookback as function of transaction costs
2. **De Prado 2016** — HRP (Hierarchical Risk Parity)
3. **Moskowitz et al. 2012** — inverse volatility scaling
4. **Carver 2015** — practical vol targeting framework

## Scope

### Individual Instrument Level
- Inverse ATR sizing vs EWMA volatility sizing
- Target risk per instrument: test 10, 15, 20, 25 bps of portfolio
- Vol estimation window: 20, 40, 60 days + EWMA(λ=0.94)
- Position capping (max contracts)

### Portfolio Level
- Equal weight vs sector risk parity vs full risk parity
- Portfolio vol targets: 8%, 10%, 12%, 15% annualized
- HRP (De Prado) vs inverse-vol vs mean-variance
- Kelly fraction comparison: full, half, quarter

### Rebalancing
- Daily vs weekly position updates
- Threshold-based rebalancing (only rebalance if position differs by >X%)
- Cost-of-rebalancing analysis

## Deliverables

1. Chosen vol estimation method and window
2. Risk allocation framework (instrument + sector + portfolio level)
3. HRP implementation and comparison vs alternatives
4. Rebalancing frequency recommendation
5. Updated backtest results with proper sizing (compare to Sprint 1 naive sizing)
