# De Prado ML Pipeline — Applied to Trend Following

## Overview

De Prado's framework (AFML 2018) provides a rigorous ML infrastructure that maps directly onto the classical trend-following pipeline:

| Traditional TF | De Prado Equivalent |
|-----------------|---------------------|
| Signal generation | Primary model + CUSUM event sampling |
| Entry/exit rules | Triple barrier labeling |
| Position sizing | Meta-labeling + bet sizing (Kelly) |
| Portfolio allocation | HRP (Hierarchical Risk Parity) |
| Backtest validation | Purged K-Fold / CPCV + Deflated Sharpe |

---

## Step 1: CUSUM Filters (Event-Driven Sampling)

**What**: Replace fixed-interval sampling (daily bars) with event-driven sampling. A new observation is generated only when the cumulative sum of price changes exceeds threshold h.

**Why for trend following**: Reduces overtrading in range-bound markets. Triggers entries only when genuine trend moves begin. Naturally adapts to market conditions.

**Calibration**:
- h = 1-2 daily standard deviations (per instrument)
- Asymmetric h for markets with asymmetric behavior (equities crash faster than rally)
- Can combine with volume/dollar bars for better statistical properties

**Implementation priority**: HIGH — directly reduces false signals

---

## Step 2: Triple Barrier Labeling

**What**: Label each CUSUM event with the outcome of a hypothetical trade, using three concurrent barriers:
- Upper barrier: profit target (e.g., 2x ATR)
- Lower barrier: stop loss (e.g., 1x ATR)
- Vertical barrier: max holding period (e.g., 20 days)

First barrier touched determines the label: +1, -1, or 0.

**Why for trend following**: Traditional labels (e.g., sign of 20-day forward return) ignore the path. A trade that goes +5% then -10% before ending +1% is labeled as profitable, but would have been stopped out. Triple barriers produce realistic labels.

**Calibration per instrument**:
- Barriers scaled by volatility (ATR or EWMA)
- Vertical barrier: holding period should match trend signal's typical duration
- Asymmetric barriers allowed (wider profit, tighter stop)

**Implementation priority**: HIGH — foundation for meta-labeling

---

## Step 3: Fractional Differentiation (FFD)

**What**: Apply fractional differencing with order d ∈ (0,1) to price series. Standard differencing (d=1) destroys all memory. No differencing (d=0) is non-stationary. FFD finds the minimum d that achieves stationarity while preserving maximum trending behavior.

**Why for trend following**: Trend following exploits serial correlation (memory). Raw returns discard this memory. Fracdiff features retain it while being stationary enough for ML models.

**Typical d* values**:
- Equity index futures: 0.3-0.5
- Interest rate futures: 0.2-0.4
- Commodity futures: 0.4-0.6

**Calibration**: Find minimum d where ADF test p-value < 0.05. Use FFD window with weight threshold 1e-5.

**Implementation priority**: MEDIUM — improves feature quality for ML models

---

## Step 4: Feature Engineering

Features to construct for each instrument:

| Category | Features |
|----------|----------|
| Fracdiff | fracdiff(price, d*), fracdiff(volume, d*) |
| Momentum | ROC at 1, 5, 21, 63, 126, 252 days |
| Volatility | Realized vol (20d, 60d), ATR(14), vol-of-vol |
| Trend strength | ADX(14), Hurst exponent(60d) |
| Carry | Roll yield (front/back spread) |
| Volume | Relative volume, OBV trend |
| Cross-asset | Sector average momentum, lead-lag scores |
| Macro regime | VIX level, yield curve slope, credit spreads |

**Implementation priority**: MEDIUM — build incrementally

---

## Step 5: Meta-Labeling

**What**: Two-stage approach:
1. Primary model generates a directional signal (e.g., EMA crossover says "go long")
2. Meta-label classifier predicts whether that signal will be profitable (probability p)

**Why for trend following**: Not every trend signal is worth taking. A trend signal in a choppy market will fail. Meta-labeling learns to distinguish good signal environments from bad ones without overriding the primary signal's direction.

**Model choices**: Random Forest, Gradient Boosting (XGBoost, LightGBM). Use features from Step 4.

**Output**: Probability p ∈ [0, 1] that the primary signal will be profitable.

**Implementation priority**: HIGH — this is where most of the ML value-add comes from

---

## Step 6: Bet Sizing

**What**: Map the meta-label probability p to a position size:
```
size = 2 * Φ(Z(p)) - 1
```
Where Φ is the CDF and Z is calibrated so p=0.5 → size=0, p→1 → size→1.

**Connection to Kelly**: The optimal bet size under Kelly criterion is f* = edge / odds. The meta-label probability provides the edge estimate.

**Practical adjustments**:
- Use fractional Kelly (0.25-0.5x) to reduce drawdowns
- Calibrate probabilities using Platt scaling or isotonic regression
- Discretize into position levels (0, 0.25, 0.5, 0.75, 1.0) to reduce turnover

**Implementation priority**: HIGH — transforms binary signals into continuous position sizes

---

## Step 7: Purged K-Fold CV / CPCV

**What**: Cross-validation that prevents information leakage in financial time series.

- **Purged K-Fold**: Removes training observations whose labels overlap with test set evaluation period
- **Embargo**: Additional buffer after purging for serial correlation
- **CPCV (Combinatorial Purged CV)**: Generates C(n,k) backtest paths; produces Sharpe ratio distribution

**Why critical**: Standard k-fold CV massively overstates strategy performance in financial data. Any model selection without purging is suspect.

**Calibration**:
- Purge window = vertical barrier width (e.g., 20 days)
- Embargo = 1-5 additional days
- CPCV: n=10 groups, k=2 test → 45 backtest paths

**Implementation priority**: HIGH — all model selection must use this

---

## Step 8: Feature Importance (MDA, MDI, SFI)

**What**: Identify which features actually contribute to prediction, drop the rest.

| Method | Type | Strength | Weakness |
|--------|------|----------|----------|
| MDI | In-sample (tree splits) | Fast | Biased toward high-cardinality |
| MDA | OOS (permutation) | Reliable | Expensive, correlation-sensitive |
| SFI | Single-feature models | Finds standalone value | Misses interactions |

**Workflow**:
1. Train meta-label model with all features
2. Run MDA with purged CV
3. Drop features with zero/negative importance
4. Run SFI to identify standalone predictors
5. Cluster correlated features to avoid importance splitting

**Implementation priority**: MEDIUM — important for preventing overfitting, but comes after core pipeline

---

## Step 9: HRP (Portfolio Construction)

**What**: Allocate across instruments using hierarchical clustering instead of mean-variance optimization.

Three steps:
1. Hierarchical clustering of strategy returns by correlation distance
2. Quasi-diagonalization (reorder covariance matrix)
3. Recursive bisection (allocate risk top-down through dendrogram)

**Why for trend following**:
- No covariance matrix inversion (stable, robust)
- Naturally groups correlated instruments (e.g., all energy markets)
- Adapts to changing correlations faster than static risk parity
- Rebalance monthly or quarterly

**Comparison to alternatives**:
- Equal weight: simple but ignores correlation structure
- Risk parity: better but assumes stable correlations
- Mean-variance: unstable, sensitive to estimation error
- HRP: robust, adaptive, no inversion required

**Implementation priority**: MEDIUM-HIGH — use in Sprint 2 for portfolio construction

---

## Implementation Order for Our System

| Sprint | De Prado Component | Integration Point |
|--------|-------------------|-------------------|
| 1 | — | Establish signal baselines without ML |
| 2 | HRP | Portfolio construction across instruments |
| 3 | — | Cost modeling |
| 4 | CUSUM | Event sampling for regime-aware signals |
| 5 | Full pipeline: triple barrier → fracdiff → meta-label → bet sizing → CPCV → MDA | ML enhancement layer |
| 6 | Mutual information (entropy) | Cross-asset dependency detection |
| 7 | CPCV + Deflated Sharpe | Final validation |
