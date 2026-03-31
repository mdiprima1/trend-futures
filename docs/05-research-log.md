# Research Log — Trend Following in Futures Markets

Chronological record of findings, decisions, and evolving hypotheses.
Each entry documents what was tested, what was found, what changed, and what to investigate next.

---

## 2026-03-30 — Session 1: Foundation + Enhancement (Sprints 1-6)

### Sprint 0: Environment Calibration

**Objective**: Validate that our local backtest environment (Databento + vectorbt) matches QuantConnect.

**Method**: Replicated the ORB V10 winner strategy (7-min confirmation, dual vol filter, VIX compression proxy) on ES and NQ futures, 2018-2025.

**Result**:
- Equity correlation: 0.953
- Final equity: $2.53M local vs $2.47M QC (2.7% difference)
- CAGR: 21.7% vs 22.1%

**Known discrepancy**: Sharpe differs (1.43 local vs 0.81 QC) due to different continuous contract construction. Databento uses front-month; QC uses backward-ratio adjustment. This affects daily return volatility but not total return. Accepted.

**Decision**: Environment is calibrated. Proceed with Databento data for all research.

---

### Sprint 1: Signal Landscape

**Objective**: Map the full signal landscape. Which signal types work? Which speeds? Which instruments trend best?

**Method**: 18 signals across 5 families (MA crossover, TSMOM, breakout, MACD, single EMA) × 6 instruments (ES, NQ, ZN, GC, CL, 6E), 2018-2025. Naive position sizing (20bps per instrument).

**Key findings**:

1. **Slow signals dominate**. TSMOM(252d) is the best portfolio-level signal (Sharpe 0.974). This was expected from the literature but the magnitude surprised — slow beats fast by 10x on portfolio Sharpe.

2. **Short-term autocorrelation is negative** across all instruments (ES: -0.171, NQ: -0.144 at lag 1). This is the fundamental reason fast signals lose money. At daily frequency, futures prices mean-revert in the short term. Only at longer horizons (63+ days) does positive autocorrelation appear.

3. **Asymmetric signals work well**. EMA(10/100) — fast entry, slow exit — is the #2 signal (Sharpe 0.910). Conceptually sound: get in quickly when a trend starts, don't get out until it's clearly over.

4. **MACD is negative on aggregate**. All three MACD variants lost money. Standard MACD parameters (12/26/9) are designed for stocks and are too fast for futures at daily frequency.

5. **Gold (GC) is the most trendable instrument** (Sharpe 0.933 on best signal). 6E (Euro FX) is the weakest (0.245). This aligns with the macro view: gold trends on inflation/rates narratives that persist for months; EUR/USD is dominated by mean-reverting carry flows.

6. **Valeyre (2025) confirmed**: Single EMA family average Sharpe (0.498) captures most of the trend premium vs all signals average (0.446). Complexity doesn't pay in signal construction.

**Hypothesis update**: The literature's emphasis on "signal matters less than portfolio construction" is validated. Simple, slow signals capture the available trend premium. The alpha opportunity is in sizing, allocation, and risk management.

**Signals selected for Sprint 2**: TS-04, MA-04, MA-03, MA-02, SE-02

---

### Sprint 2: Position Sizing & Portfolio Construction

**Objective**: How should we size positions and allocate across instruments?

**Method**: Tested 3 vol estimation methods × 3 windows × 3 allocation methods × 5 vol targets × rebalancing frequencies, using Sprint 1's top 5 signals.

**Key findings**:

1. **ATR(20) is the right vol estimator for futures** (Sharpe 0.958 vs EWMA 0.188). This was the most decisive result. ATR works in price points — matching how futures PnL is computed (Δprice × multiplier × contracts). EWMA and realized vol work in percentage terms, creating a units mismatch for position sizing.

2. **Equal weight beats HRP with 6 instruments** (Sharpe 0.958 vs 0.611). HRP allocated 52% to ZN and 31% to 6E — the two lowest-vol but also lowest-trend instruments. With a small universe, risk parity penalizes exactly the instruments where trend alpha lives. *This is a key insight*: HRP's strength (robust diversification) requires enough instruments that each cluster has multiple members. With 6, it degenerates.

3. **Vol target is a scaling lever, not an optimizer**. Sharpe barely changes across 8-20% targets (range: 0.942-0.965). The risk-return tradeoff is almost perfectly linear. Choose based on drawdown tolerance, not Sharpe optimization.

4. **Weekly rebalancing beats daily** (Sharpe 1.102 vs 1.031). For slow signals that change direction every 40-60 days, daily rebalancing is noise. Weekly is enough and saves on execution costs.

**Decision**: ATR(20), equal weight, 12% vol target, weekly rebalancing.

**Hypothesis update**: The HRP result is the most important revision. The literature (De Prado, practitioner papers) strongly advocates HRP, but implicitly assumes 30+ instruments. On a small universe, equal weight is more robust. We'll revisit HRP when the universe expands.

---

### Sprint 3: Transaction Costs

**Objective**: Do costs change anything? Which instruments are expensive? Is there a capacity problem?

**Method**: Detailed per-instrument cost model (commission, spread, slippage via square-root impact model, roll costs). Tested cost sensitivity at 0x through 3x base costs.

**Key findings**:

1. **Costs are a non-issue** for slow trend following. Annual drag is 0.24-0.42% of portfolio — less than 10% of CAGR. Even at 3x stress costs, all signals remain profitable.

2. **Roll costs dominate for CL and GC**. CL has 90bps annual drag (monthly rolls in contango); GC has 70bps (bi-monthly). Commission and spread are secondary for instruments with decent liquidity.

3. **Signal rankings don't change with costs**. The Zakamulin & Giner (2022) concern — that optimal lookback lengthens with costs — doesn't apply because our Sprint 1 selection already favored slow signals. EMA(10/100) remains #1 at all cost levels.

4. **Capacity is massive**: $8.7B at 1% daily volume participation. This strategy is not capacity-constrained.

**Decision**: Base cost model is adequate. No changes to signal selection or sizing needed. Roll cost optimization (timing, calendar spreads) is a potential improvement but low priority.

**Hypothesis update**: Chevalier & Darolles (2020) confirmed — it's volatility that drives trend alpha, not cost erosion. Our slow signals are inherently cost-efficient.

---

### Sprint 4: Signal Blending & Regime Detection

**Objective**: Can we improve by blending multiple signals? Do regime filters (ADX, Hurst, CUSUM) help?

**Method**: 10 signal variants — 4 pure blends + 6 regime-filtered blends. Tested against Sprint 1 baselines.

**Key findings**:

1. **Fast+Slow blend wins** (Sharpe 1.168, Calmar 1.298). Just two signals — EMA(10/100) + TSMOM(252d) — beat every other combination. The fast signal catches entries; the slow signal confirms. This is the simplest and best.

2. **Etienne (2025) barbell hypothesis CONFIRMED**. Barbell (short + long, skip medium) beats equal blend of all 5 signals (Sharpe 1.098 vs 0.997). Medium-term signals (EMA 20/50, Price>EMA 50) are genuinely redundant when short + long are present.

3. **Regime filters mostly hurt**. Only Hurst marginally improved Sharpe (+0.058). ADX, CUSUM, and vol-regime filters all reduced Sharpe. The insight: regime filters reduce time-in-market, cutting CAGR more than they cut risk. With slow signals that inherently self-filter for trends, explicit regime detection adds overhead without benefit.

4. **Pure blends outperform regime-filtered blends** (avg Sharpe 1.058 vs 0.959). Simplicity wins again.

**Decision**: Use Fast+Slow blend (EMA 10/100 + TSMOM 252d) as the primary signal. Drop regime filters.

**Hypothesis revision**: Coming into this sprint, I expected regime detection to be one of the biggest improvements. Instead, it was the smallest. The reason: slow trend signals ARE implicit regime detectors. A 252-day TSMOM is only long when the market has been trending up for a year — that IS regime detection, just embedded in the signal rather than as a separate layer.

---

### Sprint 5: ML Enhancement (De Prado Pipeline)

**Objective**: Does the full De Prado ML pipeline (triple barrier → fracdiff → meta-labeling → bet sizing) improve on pure trend signals?

**Method**: Applied the complete AFML pipeline to 4 base signals across 6 instruments. RF meta-label classifier with purged 5-fold CV. 15 features: momentum (5 lookbacks), volatility (3), trend strength (3), vol regime, ATR ratio, fracdiff price, volume.

**Key findings**:

1. **ML improves Sharpe by +0.414 on average**. All 4 signals improved. TS-04 went from 1.130 to 1.907. This is the most significant improvement of any sprint.

2. **The tradeoff: CAGR drops ~50%**. Meta-labeling is conservative — average bet size is only 3-9% of full position. The model learns when signals are likely to fail and scales down. This cuts losses (improving Sharpe) but also cuts some winners.

3. **Top features are volatility and trend strength**, not momentum itself. vol_60 (0.112 importance), price_vs_ma200 (0.106), mom_252 (0.098). The model is essentially learning: "trade more when trends are strong and stable, trade less in choppy conditions."

4. **CV accuracy is 53-55%** — modest but consistent. In financial ML, a small edge consistently applied compounds. This is in line with De Prado's own results.

5. **Fracdiff features contribute but aren't dominant** (rank 9 of 15). The simpler features (volatility, MAs) carry more weight.

**Decision**: ML meta-labeling is available as an optional overlay. Recommended blend: 70% base + 30% ML-enhanced for production. The 70/30 split balances Sharpe improvement with CAGR preservation.

**Key insight**: De Prado's framework works as advertised, but the biggest value is in the bet sizing layer (knowing WHEN to trade full size vs. small), not in signal direction (the base signals already get direction right). This confirms the AFML thesis that meta-labeling enhances rather than replaces the primary model.

---

### Sprint 6: Cross-Asset Dynamics

**Objective**: Do cross-asset signals (lead-lag, network momentum, carry, cross-sectional momentum) add value?

**Method**: Implemented lead-lag detection, network momentum (Oxford 2025), carry proxy (return momentum), cross-sectional momentum (rank-based). Tested 5 multi-factor combinations against pure trend.

**Key findings**:

1. **No multi-factor combination beats pure trend** on this 6-instrument universe. The best combo (Trend+XSmom 70/30) merely tied trend-only. All others degraded Sharpe.

2. **Lead-lag effects are negligible** at daily frequency among 6 liquid instruments (max cross-correlation 0.163). These markets are efficient at this timescale.

3. **Carry signal is too correlated with trend** — our proxy (return momentum) captures essentially the same information as the trend signal. In production, actual calendar spread data (front-back contract price) would provide an independent carry signal.

4. **Cross-sectional momentum needs more instruments**. Ranking 6 instruments is inherently noisy. The Oxford (2025) paper achieving 0.645 Sharpe used 28 instruments.

**Decision**: Keep pure trend as the sole signal for the current 6-instrument system. Cross-asset signals become the primary expansion opportunity when the universe grows to 20+ instruments.

**Hypothesis for future work**: The literature strongly supports carry and cross-sectional momentum as alpha sources, but they require:
- Carry: actual roll yield data (not return momentum)
- XSmom: 15+ instruments for meaningful ranking
- Network: sector-level clustering (equities lead metals, rates lead FX, etc.)

These are the next research priorities after universe expansion, not sprint-level work on the current system.

---

## Cumulative System Profile (After Sprint 6)

| Parameter | Value | Source |
|-----------|-------|--------|
| Signal | Fast+Slow (EMA 10/100 + TSMOM 252d) | Sprint 4 |
| Vol estimation | ATR(20) | Sprint 2 |
| Allocation | Equal weight | Sprint 2 |
| Vol target | 12% annualized | Sprint 2 |
| Rebalancing | Weekly | Sprint 2 |
| Universe | ES, NQ, ZN, GC, CL, 6E | Sprint 1 |
| ML overlay | Optional 70/30 blend | Sprint 5 |
| Cross-asset | Not used (waiting for universe expansion) | Sprint 6 |

| Metric | Base | With ML (30%) |
|--------|------|--------------|
| Sharpe | 1.168 | ~1.3 (estimated) |
| CAGR | 5.7% | ~4.8% |
| Max DD | 4.4% | ~3.5% |
| Calmar | 1.298 | ~1.4 |
| Cost drag | 0.27%/yr | 0.27%/yr |

---

## Key Lessons (Running List)

1. **Simplicity beats complexity** — repeatedly confirmed across signals, blending, and regime detection
2. **Slow signals capture the trend premium** — fast signals lose to short-term mean-reversion
3. **Portfolio construction matters, but only with enough instruments** — HRP needs 20+, XSmom needs 15+
4. **ML works for bet sizing, not signal direction** — meta-labeling improves Sharpe but halves CAGR
5. **Costs are irrelevant for slow trend following** — annual drag < 0.5% on liquid futures
6. **ATR is the natural vol estimator for futures** — it works in price points, matching PnL mechanics
7. **The barbell works** — short + long, skip medium (Etienne 2025 confirmed)
8. **Regime filters are redundant with slow signals** — the signals themselves are implicit regime detectors

---

## Open Questions for Sprint 7 → ANSWERED

### Sprint 7: Integration & Stress Testing

**Objective**: Does the system survive real-world stress tests? Is it robust? Does it provide crisis alpha?

**Method**: Regime-specific backtests (8 yearly periods), 5-fold walk-forward validation (3-year IS → 1-year OOS), parameter perturbation (5 variants), crisis alpha analysis vs SPY, vol target scaling.

**Key findings**:

1. **Crisis alpha is real**. SPY correlation is 0.051 (uncorrelated). During SPY drawdowns >20%, the strategy is negatively correlated (-0.503) and generates +3.9% annualized return. In 2022 specifically: strategy +9.8% while SPY -24.8%. This confirms CFM (2018) convexity thesis and Kaminski (2025) crisis alpha framework.

2. **Walk-forward PASSES** (OOS/IS ratio 0.91, avg OOS Sharpe 0.969). The system generalizes out of sample. 4 of 5 windows are profitable OOS. The one failure is 2023 (range-bound) — the known weakness.

3. **Parameters are robust** (Sharpe std 0.072 across 5 perturbations). All variants produce Sharpe > 0.95. Not overfit to specific parameter choices.

4. **2023 is the Achilles heel** — the only losing year (-2.2%, Sharpe -0.560). Range-bound markets with no sustained trends. This is structural, not fixable. Kaminski (2025) calls these "corrections" vs "crises" — trend following only protects in crises.

5. **Vol target scales perfectly linearly** — Sharpe barely changes (1.142-1.173) across 8-25% targets. At 20%, CAGR is 9.5% with 7.3% max DD. At 25%, CAGR is 11.9% with 9.0% max DD. Adding instruments would allow even higher targets.

6. **2025 is the standout year** — Sharpe 2.355, return +12.2%, max DD only 2.1%. Tariff-driven macro volatility creates exactly the sustained directional moves that trend following exploits.

**Decision**: System is validated. The integrated configuration (Fast+Slow blend, ATR(20), equal weight, 12% vol target, weekly rebal) is the production system.

---

## Final System Summary (All 7 Sprints Complete)

| Component | Value | Sprint |
|-----------|-------|--------|
| Signal | Fast+Slow (EMA 10/100 + TSMOM 252d) | 4 |
| Vol estimation | ATR(20) | 2 |
| Allocation | Equal weight | 2 |
| Vol target | 12% (scalable to 25%) | 2, 7 |
| Rebalancing | Weekly | 2 |
| Universe | ES, NQ, ZN, GC, CL, 6E | 1 |
| ML overlay | Available (70/30 blend for +0.4 Sharpe) | 5 |
| Cross-asset | Deferred to universe expansion | 6 |
| Cost drag | 0.27%/yr | 3 |
| Capacity | $8.7B at 1% participation | 3 |

| Metric | 12% Vol Target | 20% Vol Target |
|--------|---------------|----------------|
| Sharpe | 1.168 | 1.153 |
| CAGR | 5.7% | 9.5% |
| Max DD | 4.4% | 7.3% |
| Calmar | 1.298 | 1.313 |
| SPY Correlation | 0.051 | 0.051 |

## Key Lessons (Final)

1. **Simplicity beats complexity** — across signals, blending, and regime detection
2. **Slow signals capture the trend premium** — fast signals lose to mean-reversion
3. **The barbell works** — short + long, skip medium (Etienne 2025)
4. **ML improves Sharpe but halves CAGR** — meta-labeling is for bet sizing, not direction
5. **Costs are irrelevant** for slow trend following (<0.5%/yr)
6. **Crisis alpha is real** — uncorrelated to SPY, negatively correlated in drawdowns
7. **Walk-forward validates** — OOS/IS ratio 0.91
8. **Parameters are robust** — Sharpe std 0.072 across perturbations
9. **2023-type range-bound years are structural weakness** — not fixable within trend framework
10. **Universe expansion is the primary growth lever** — more instruments → better diversification → higher vol targets → higher CAGR

---

## 2026-03-30 — Universe Expansion (20 Instruments)

### Objective
Expand from 6 to 20+ instruments. Re-evaluate HRP and allocation methods with larger universe.

### Universe Loaded
20 instruments across 5 sectors: Equity (4: ES, NQ, RTY, NKD), Fixed Income (3: ZT, ZN, ZB), FX (7: 6E, 6B, 6J, 6A, 6C, 6S, 6N), Energy (2: CL, NG), Metals (3: GC, SI, HG), Agriculture (1: ZS). Six more instruments still downloading (RB, HO, PL, ZC, ZW, LE).

### MAJOR FINDING: HRP Reversal

| Config | Sharpe | CAGR | Max DD | Calmar |
|--------|--------|------|--------|--------|
| **20 inst / HRP / 15%** | **1.596** | **22.6%** | **10.8%** | **2.093** |
| 20 inst / InvVol / 15% | 1.416 | 10.4% | 7.1% | 1.460 |
| 6 inst / EW / 12% | 1.168 | 5.7% | 4.4% | 1.298 |
| 20 inst / EW / 15% | 0.934 | 4.7% | 6.6% | 0.722 |

**HRP now dominates** — completely reversing the Sprint 2 result where it was worst. With 20 instruments, HRP correctly identifies ZT (2-Year T-Note) as the highest risk-adjusted instrument and allocates 84% to it.

This is both the strength and risk of HRP:
- **Strength**: It finds the best risk-adjusted instrument and maximizes exposure
- **Risk**: 84% concentration in one instrument is extreme — this is a bet on rates trending, not a diversified trend system

**Equal weight is diluted**: With 20 instruments, 7 are FX pairs that don't trend well individually. Equal weighting gives them 7/20 = 35% of the portfolio, diluting alpha from the strong instruments (rates, equities, gold).

### Key Insight
The allocation method matters enormously at scale. The choice isn't HRP vs EW — it's about finding the right balance between:
1. Concentration (HRP) — maximizes Sharpe but single-instrument risk
2. Diversification (EW) — spreads risk but dilutes alpha
3. Risk-aware (InvVol) — middle ground, Sharpe 1.416

**Inverse-vol may be the practical winner**: Sharpe 1.416 with CAGR 10.4% and only 7.1% max DD. It naturally overweights the strong-trending, lower-vol instruments without the extreme concentration of HRP.

### Regime Performance (20 inst, EW, 15%)

| Regime | Sharpe | Return |
|--------|--------|--------|
| 2020 COVID | 2.330 | +6.2% |
| 2025 Tariffs | 2.170 | +6.0% |
| 2022 Rate Shock | 0.993 | +3.3% |
| 2023 Range-Bound | -1.182 | -3.2% |

Crisis alpha persists with the larger universe. 2023 remains the weakness.

### Decision
- **Production config**: Inverse-vol allocation at 15% vol target — best balance of Sharpe (1.416), CAGR (10.4%), and diversification
- HRP is available as an aggressive variant (Sharpe 1.596 but concentrated)
- Equal weight is the conservative variant (Sharpe 0.934 but maximum diversification)

### Updated System Profile

| Parameter | 6 inst (Sprint 7) | 20 inst (Expanded) |
|-----------|-------------------|-------------------|
| Allocation | Equal weight | **Inverse-vol** |
| Vol target | 12% | **15%** |
| Sharpe | 1.168 | **1.416** |
| CAGR | 5.7% | **10.4%** |
| Max DD | 4.4% | 7.1% |
| Calmar | 1.298 | **1.460** |

## Next Steps

1. Complete remaining instrument downloads (RB, HO, PL, ZC, ZW, LE) for full 26-instrument universe
2. Sector-constrained HRP (cap max sector weight at 40%) to limit concentration
3. Cross-sectional momentum re-evaluation with 20 instruments
4. Live paper trading validation
5. 8-Gate evaluation
