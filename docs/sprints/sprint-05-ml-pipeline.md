# Sprint 5: Machine Learning Enhancement (De Prado Pipeline)

**Status**: Not Started
**Phase**: B (Enhancement)
**Depends on**: Sprint 4

## Objective

Apply the full De Prado framework to enhance trend signals with ML. Implement meta-labeling for bet sizing, validate with CPCV.

## Key Papers

1. **De Prado AFML** — full pipeline (triple barrier, meta-labeling, CPCV, MDA)
2. **Wood et al. 2023** — X-Trend few-shot learning
3. **Lim et al. 2020** — Deep Momentum Networks, turnover regularization

## Pipeline Steps

1. CUSUM filter → event sampling (from Sprint 4)
2. Triple barrier labeling per instrument
3. Fractional differentiation features (FFD)
4. Feature engineering (momentum, vol, carry, cross-asset, macro)
5. Meta-labeling classifier (RF/XGBoost)
6. Bet sizing from meta-label probability
7. Purged K-Fold / CPCV validation
8. Feature importance analysis (MDA)

## Deliverables

1. Complete ML pipeline code
2. Meta-label model per instrument cluster
3. CPCV validation with Sharpe distribution
4. Feature importance rankings
5. Comparison: base signal vs ML-enhanced signal (Sharpe, DD, turnover)
