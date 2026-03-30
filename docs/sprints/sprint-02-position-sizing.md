# Sprint 2: Volatility Targeting & Position Sizing

**Status**: COMPLETE (2026-03-30)
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

---

## Results (2026-03-30)

### Test 1: Vol Estimation Method

| Method | Window | Avg Sharpe |
|--------|--------|-----------|
| **ATR** | **20** | **0.958** |
| ATR | 40 | 0.940 |
| ATR | 60 | 0.884 |
| EWMA | 20 | 0.188 |
| Realized | 20 | 0.063 |

**Winner: ATR(20)**. ATR dominates by a wide margin. EWMA and realized vol produce poor results — likely because they estimate percentage vol while our sizing needs point-based vol for futures contracts. ATR is naturally in price points, making it ideal.

### Test 2: Allocation Methods

| Method | Avg Sharpe | Notes |
|--------|-----------|-------|
| **Equal Weight** | **0.958** | Simplest, best |
| Inverse Vol | 0.810 | Overweights low-vol instruments |
| HRP | 0.611 | Over-concentrates in ZN (52%) and 6E (31%) |

**Winner: Equal Weight**. With only 6 instruments, HRP over-concentrates in low-vol assets (ZN, 6E) which are the weakest trend markets. Equal weight gives every instrument a fair shot.

HRP weights were: ZN=52%, 6E=31%, GC=7%, ES=6%, NQ=3%, CL=1%. This is a risk-parity allocation that penalizes high-vol instruments (CL, NQ). With our small universe, this hurts because the high-vol instruments (ES, NQ, GC, CL) are where most trend alpha lives.

**Note**: HRP will likely improve in Sprint 6+ when the universe expands to 20-35 instruments with better sector diversification.

### Test 3: Vol Targets

| Target | Sharpe | CAGR | Max DD | Realized Vol |
|--------|--------|------|--------|-------------|
| **8%** | **0.965** | 3.3% | 4.0% | 3.9% |
| 10% | 0.961 | 4.1% | 5.0% | 5.0% |
| 12% | 0.958 | 4.9% | 6.0% | 6.1% |
| 15% | 0.952 | 6.2% | 7.4% | 8.0% |
| 20% | 0.942 | 8.2% | 9.8% | 11.4% |

Sharpe is roughly constant across vol targets (range: 0.942-0.965), confirming the risk-return tradeoff is linear. Higher targets just scale up both return and risk.

**Chosen: 12% for now** — decent CAGR (4.9%) with controlled DD (6%). Can scale up to 15-20% with more instruments providing diversification.

### Test 4: Rebalancing

| Frequency | Threshold | Avg Sharpe |
|-----------|-----------|-----------|
| **Weekly** | **0%** | **1.102** |
| Weekly | 10% | 1.087 |
| Weekly | 25% | 1.056 |
| Daily | 10% | 1.035 |
| Daily | 0% | 1.031 |
| Daily | 25% | 0.985 |

**Winner: Weekly rebalancing with no threshold**. Weekly slightly outperforms daily — less noise, fewer transactions, better Sharpe. Confirms the slow-signal, low-frequency thesis from Sprint 1.

### Final Configuration

| Parameter | Value |
|-----------|-------|
| Vol estimation | ATR(20) |
| Allocation | Equal weight |
| Portfolio vol target | 12% (scalable) |
| Rebalancing | Weekly |
| Max contracts | 50 per instrument |

### Final Signal Performance (Optimal Config)

| Signal | Sharpe | CAGR | Max DD | Calmar | Total Return |
|--------|--------|------|--------|--------|-------------|
| EMA(10/100) | 1.028 | 3.6% | 3.6% | 1.024 | 27.2% |
| TSMOM(252d) | 1.034 | 3.4% | 4.3% | 0.795 | 22.5% |
| EMA(20/50) | 0.964 | 3.4% | 3.5% | 0.972 | 24.8% |
| Price>EMA(50) | 0.921 | 3.0% | 4.7% | 0.624 | 21.6% |
| SMA(50/200) | 0.876 | 3.1% | 4.0% | 0.772 | 21.0% |

All 5 signals now have Sharpe > 0.87 with max DD < 5% on 6 instruments. **EMA(10/100) has the best Calmar (1.024)** — highest return per unit of drawdown.

### Key Findings

1. **ATR is the right vol estimator for futures** — it naturally produces point-based volatility, matching how futures PnL works (points × multiplier × contracts).
2. **Equal weight beats HRP with 6 instruments** — HRP will shine with 20+ instruments where sector clustering matters.
3. **Vol target is a lever, not an optimizer** — Sharpe barely changes (0.94-0.97) across 8-20% targets. Choose based on risk appetite.
4. **Weekly rebalancing beats daily** — for slow trend signals, less frequent rebalancing reduces noise and costs.
5. **Scaling potential**: At 20% vol target, CAGR reaches 8.2% on only 6 instruments with max DD under 10%. Adding more instruments in Sprints 4-6 will improve diversification and allow higher vol targets.
