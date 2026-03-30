# Research Overview — Multi-Futures Trend Following

## Core Thesis

Trend following is a structural feature of financial markets, not a statistical artifact. It has persisted for 200+ years across all asset classes. The alpha comes from three sources:

1. **Behavioral** — anchoring, herding, disposition effect cause delayed price adjustment
2. **Institutional** — hedgers provide a risk premium to speculators; index rebalancing creates momentum
3. **Macro** — central bank policy, supply shocks, and credit cycles create sustained directional moves

## Key Findings from Literature Review (2020-2026)

### 1. Signal Simplicity Beats Complexity
- A single EMA captures most of the trend premium (Valeyre 2025)
- Complex indicator baskets invite cherry-picking and overfitting
- The P&L of any trend system is a direct function of return autocorrelation (Sepp & Lucic 2025)
- MACD is mathematically equivalent to exponentially-weighted TSMOM (Baz et al. 2015/AQR)

### 2. Portfolio Construction Is Where the Alpha Lives
- Speed, market set, carry inclusion, and allocation method explain most CTA performance dispersion (Man AHL 2025)
- The medium-term trend band (125-day) adds little when short + long are present — "barbell" structure is more efficient (Etienne et al. 2025)
- HRP outperforms equal-weight and risk parity during regime transitions (Lohre et al. 2023-2024)
- Optimal lookback periods lengthen as transaction costs increase (Zakamulin & Giner 2022)

### 3. ML Enhances but Does Not Replace Trend
- Deep Momentum Networks improve TSMOM by ~2x Sharpe, with turnover regularization (Lim et al. 2020)
- Momentum Transformer captures concurrent regimes at different timescales (Wood et al. 2022)
- X-Trend (few-shot learning + change-point detection) adapts to new regimes with minimal data (Wood et al. 2023)
- De Prado's preprocessing methods (data pipeline) matter more than model choice (consensus 2023-2025)

### 4. Crisis Alpha Is Real but Conditional
- Trend following is structurally long volatility — inherent positive convexity (CFM 2018)
- Works in sustained crises (2008: +13%, 2022: +36%), not quick corrections (Kaminski 2025)
- Equity market timing is the key driver of recovery from CTA drawdowns (Kaminski & Wen 2025)

### 5. Cross-Asset Dynamics Add Value
- Network momentum (lead-lag across markets) achieved 0.645 Sharpe on 28 futures (Oxford 2025)
- Carry predicts returns cross-sectionally and in time series (Koijen et al. 2018)
- Factor-level momentum in commodities extends the signal set beyond individual assets (Jiang & Liu 2024)

### 6. Capacity and Crowding Are Real Concerns
- 70% of commodity futures liquidity is in 10 markets (Quantica 2025)
- CTA performance declined as AUM grew, but strategy capacity is large given market liquidity (AQR)
- Differentiation in signal construction, execution, and universe selection mitigates crowding

## What This Means for Our System

We should:
1. **Start simple** — EMA/TSMOM baseline, prove it works on our data
2. **Invest heavily in portfolio construction** — risk parity, HRP, vol targeting
3. **Model costs accurately** — they determine optimal lookback and turnover
4. **Add ML as an enhancement layer** — meta-labeling for bet sizing, not signal replacement
5. **Exploit cross-asset structure** — lead-lag, carry, sector rotation
6. **Validate rigorously** — CPCV, 8-Gate, walk-forward, deflated Sharpe ratio

## Research Sprint Plan

| Sprint | Phase | Focus | Key Papers |
|--------|-------|-------|------------|
| 1 | A | Signal Landscape & Baseline | Sepp 2025, Valeyre 2025, Moskowitz 2012 |
| 2 | A | Volatility Targeting & Position Sizing | Zakamulin 2022, De Prado HRP |
| 3 | A | Transaction Costs & Execution | Chevalier 2020, Quantica 2025 |
| 4 | B | Multi-Scale Blending & Regimes | Etienne 2025, Zakamulin 2024, Levy 2021 |
| 5 | B | ML Enhancement (De Prado Pipeline) | AFML, Wood 2023, Lim 2020 |
| 6 | B | Cross-Asset Dynamics & Network Effects | Oxford 2025, Koijen 2018 |
| 7 | C | Full Integration & Stress Testing | Man AHL 2025, Kaminski 2025 |

## Universe Expansion

| Phase | Markets | Count |
|-------|---------|-------|
| Sprints 1-3 | ES, NQ, US 10Y, Gold, Crude, EUR/USD | 6 |
| Sprints 4-5 | + US 2Y/30Y, Bund, GBP, JPY, AUD, NatGas, Copper, Corn, Soybeans | 15-20 |
| Sprints 6-7 | + Nikkei, Euro Stoxx, BTP, Silver, Sugar, Coffee, Cotton, CAD, CHF | 30-40 |
