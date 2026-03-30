# Paper Registry — Trend Following Research

All papers reviewed for this project, organized by topic. Each entry includes relevance rating (A = must-read, B = should-read, C = reference).

---

## 1. Time-Series Momentum (TSMOM)

| # | Title | Authors | Year | Source | Relevance | Key Finding |
|---|-------|---------|------|--------|-----------|-------------|
| 1 | Trends Everywhere | Babu, Levine, Ooi, Pedersen, Stamelos (AQR) | 2020 | J. Investment Management | A | TSMOM generalizes beyond traditional futures to 82 securities including EM, swaps, CDS, vol futures |
| 2 | Time Series Momentum and Reversal: Intraday Info from Realized Semivariance | Liu, Lu, Li, Wang | 2022 | SSRN | B | Realized semivariance predicts momentum reversals; improves TSMOM timing |
| 3 | Trend Following Strategies: A Practical Guide | Shi, Lian | 2025 | SSRN 5140633 | C | Multi-scale trend on China futures: 16.24% return, 0.88 Sharpe |
| 4 | Time Series Momentum | Moskowitz, Ooi, Pedersen | 2012 | J. Financial Economics | A | The foundational TSMOM paper. 12-month lookback, inverse vol scaling |
| 5 | A Century of Evidence on Trend-Following Investing | Hurst, Ooi, Pedersen (AQR) | 2017 | AQR White Paper | A | Confirms trend following across 10 decades and multiple asset classes |
| 6 | Two Centuries of Trend Following | Lempérière et al. (CFM) | 2014 | CFM Working Paper | A | Extended evidence back to 1800 across all asset classes |

## 2. Signal Construction & System Design

| # | Title | Authors | Year | Source | Relevance | Key Finding |
|---|-------|---------|------|--------|-----------|-------------|
| 7 | The Science and Practice of Trend-Following Systems | Sepp, Lucic | 2025 | SSRN 3167787 | A | Unified taxonomy (European/American/TSMOM). Exact P&L = f(autocorrelation) |
| 8 | A Guide to Trend Following Strategies | Broadfoot, Leveau | 2023 | SSRN 4438260 | B | Practitioner guide: signal construction, portfolio weighting, implementation |
| 9 | Breaking the Trend: How to Avoid Cherry-Picked Signals | Valeyre | 2025 | arXiv 2504.10914 | A | Single EMA sufficient. Complex baskets invite overfitting. Validates Grebenkov-Serror Sharpe model |
| 10 | Dissecting Investment Strategies (MACD equivalence) | Baz et al. (AQR) | 2015 | AQR | B | MACD is mathematically equivalent to exponentially-weighted TSMOM |

## 3. Portfolio Construction, Risk & Capacity

| # | Title | Authors | Year | Source | Relevance | Key Finding |
|---|-------|---------|------|--------|-----------|-------------|
| 11 | Revisiting the Structure of Trend Premia | Etienne, Ohana, Benhamou et al. | 2025 | arXiv 2510.23150 | A | Medium-term band is redundant. Barbell (short+long) improves Sharpe and DD efficiency |
| 12 | Re-evaluating Short/Long Trend Factors (Bayesian) | Benhamou, Ohana, Etienne et al. | 2025 | arXiv 2507.15876 | B | Bayesian graphical model decomposes CTA returns; raw-beta sleeve outperforms classic breakouts |
| 13 | Optimal Trend-Following With Transaction Costs | Zakamulin, Giner | 2022 | SSRN 4282126 / IRFA 2023 | A | Optimal lookback lengthens with costs. MA crossover approximates theoretical optimum |
| 14 | Futures Market Liquidity and Trading Cost of TF | Chevalier, Darolles | 2020 | SSRN 3523005 | B | Disappointing CTA performance was from lower vol, not higher costs |
| 15 | When Trend-Following Hits Capacity | Quantica Capital | 2025 | Quantica Quarterly | B | 70% of commodity liquidity in 10 markets. AUM growth shifts risk to liquid markets |

## 4. Machine Learning & Deep Learning

| # | Title | Authors | Year | Source | Relevance | Key Finding |
|---|-------|---------|------|--------|-----------|-------------|
| 16 | Enhancing TSMOM Using Deep Neural Networks | Lim, Zohren, Roberts | 2020 | arXiv 1904.04912 | A | Deep Momentum Networks: Sharpe-optimized LSTM improves TSMOM 2x on 88 futures. Turnover regularization |
| 17 | Trading with the Momentum Transformer | Wood, Giegerich, Roberts, Zohren | 2022 | arXiv 2112.08534 | B | Attention-based architecture; multiple heads capture concurrent regimes at different timescales |
| 18 | Few-Shot Learning for Trend-Following (X-Trend) | Wood, Kessler, Roberts, Zohren | 2023 | arXiv 2310.10500 | A | Few-shot learning + change-point detection. 18.9% Sharpe improvement over neural forecasters |
| 19 | Beyond Trend Following: Deep Learning for Prediction | Berzal, Garcia | 2024 | arXiv 2407.13685 | C | Argues for predictive ML over backward-looking trend signals |
| 20 | Enhancing TF Using ML and Time Series Models | Chandrinos, Lagaros | 2025 | SSRN 5205525 | C | TCN and Kalman filters improve trend-following returns with lower volatility |

## 5. Regime Detection & Adaptive Approaches

| # | Title | Authors | Year | Source | Relevance | Key Finding |
|---|-------|---------|------|--------|-----------|-------------|
| 21 | Trend-Following via Dynamic Momentum Learning | Levy, Lopes | 2021 | arXiv 2106.08420 | B | Dynamic binary classifier switches between time-varying and constant momentum relationships |
| 22 | Optimal Trend-Following in Regime-Switching Models | Zakamulin, Giner | 2024 | SSRN 4217513 / JAM | A | Derives optimal signals under two-state Markov regime switching |

## 6. Cross-Sectional Momentum & Network Effects

| # | Title | Authors | Year | Source | Relevance | Key Finding |
|---|-------|---------|------|--------|-----------|-------------|
| 23 | Follow the Leader: Network Momentum | Oxford/Imperial group | 2025 | arXiv 2501.07135 | A | Lead-lag dynamics across 28 futures. Net Sharpe 0.645 vs benchmark MACD. OOS 2005-2024 |
| 24 | Factor Momentum in Commodity Futures | Jiang, Liu | 2024 | EFMA Conference | C | Factor-level momentum extends cross-sectional signal to portfolio factors |

## 7. Crisis Alpha & Tail Risk

| # | Title | Authors | Year | Source | Relevance | Key Finding |
|---|-------|---------|------|--------|-----------|-------------|
| 25 | The Crisis Alpha of Managed Futures | Asif, Raheel, Frommel, Mende | 2022 | IRFA Vol. 80 | B | CTAs generated positive returns on average across all crisis periods studied |
| 26 | Enhancing Global Equity Returns with TF Overlay | Schwalbach, Auret | 2025 | Investment Analysts J. | C | 50% TF overlay on MSCI ACWI: 0.25%/month alpha. Blueprint for overlay implementation |
| 27 | Managed Futures and Crisis Alpha in 2025 | Kaminski, Zhao (AlphaSimplex) | 2025 | AlphaSimplex WP | A | Distinguishes crisis (sustained) vs correction (quick). TF excels in crises, not corrections |
| 28 | Market Cycles and Managed Futures Drawdowns | Kaminski, Wen (AlphaSimplex) | 2025 | AlphaSimplex WP | B | TF has more frequent but shallower drawdowns. Equity timing drives recovery |

## 8. Carry, Value & Complementary Signals

| # | Title | Authors | Year | Source | Relevance | Key Finding |
|---|-------|---------|------|--------|-----------|-------------|
| 29 | Carry | Koijen, Moskowitz, Pedersen, Vrugt | 2018 | J. Financial Economics | A | Carry predicts returns cross-sectionally and time-series across all asset classes |
| 30 | Risk Premia in Diversified Energy Portfolios | Bogorad | 2025 | SSRN 6374158 | C | Momentum, carry, value in energy futures specifically |

## 9. Convexity & Theoretical Foundations

| # | Title | Authors | Year | Source | Relevance | Key Finding |
|---|-------|---------|------|--------|-----------|-------------|
| 31 | The Convexity of Trend Following | Dao et al. (CFM) | 2018/2022 | CFM Working Paper | A | Trend following is structurally long large moves — inherent positive gamma |
| 32 | Does Trend-Following Still Work on Stocks? | Zarattini, Pagani, Wilcox | 2024 | SSRN 5084316 | C | <7% of trades drive cumulative profit. Turnover control critical for smaller portfolios |

## 10. Practitioner / Industry

| # | Title | Authors | Year | Source | Relevance | Key Finding |
|---|-------|---------|------|--------|-----------|-------------|
| 33 | Trend-Following: Why Now? | AQR | 2022 | AQR White Paper | B | SG Trend +36% in 2022. Macro vol is the driver, and it tends to persist |
| 34 | Trend Following and Rising Rates | AQR | 2023 | AQR White Paper | C | Rising rates benefit TF through collateral yield and macro vol |
| 35 | A TF Deep Dive: Dynamics of Dispersion | Man AHL | 2025 | Man Group Insights | A | Speed, market set, carry, allocation explain most CTA performance dispersion |
| 36 | A TF Deep Dive: Optimal Market Mix | Man AHL | 2025 | Man Group Insights | A | Defensive investors → traditional markets. Sharpe-focused → alternative markets |
| 37 | A TF Deep Dive: AI, Agents and Trend | Man AHL | 2025 | Man Group Insights | C | Agentic AI for trend-following research acceleration |
| 38 | Trend Following and Drawdowns | Man AHL | 2025 | Man Group Insights | B | Drawdown patterns and recovery timing across market cycles |

## 11. De Prado Methods (Applied to Trend Following)

| # | Method | Source | Relevance | Application to Trend Following |
|---|--------|--------|-----------|-------------------------------|
| 39 | Triple Barrier + Meta-Labeling | AFML Ch. 3, 10 | A | Path-dependent labels for trend trades; meta-model for bet sizing |
| 40 | Fractional Differentiation (FFD) | AFML Ch. 5 | B | Stationary features preserving memory; typical d*=0.3-0.5 for futures |
| 41 | CUSUM Filters | AFML Ch. 2 | A | Event-driven sampling aligned with meaningful trend moves |
| 42 | Bet Sizing (Kelly + probability mapping) | AFML Ch. 10 | A | size = f(meta-label probability). Dynamic position scaling |
| 43 | Feature Importance (MDA, MDI, SFI) | AFML Ch. 8 | B | Feature selection to prevent overfitting |
| 44 | Purged K-Fold / CPCV | AFML Ch. 7 | A | Cross-validation without data leakage; strategy robustness distribution |
| 45 | HRP (Hierarchical Risk Parity) | JPM 2016 | A | Portfolio construction without covariance inversion; robust to regime changes |
| 46 | Entropy Measures | AFML Ch. 18-19 | C | Regime detection (low entropy = trending, high = noisy) |

## Key Books

| Title | Author | Year | Relevance |
|-------|--------|------|-----------|
| Advances in Financial Machine Learning | Marcos Lopez de Prado | 2018 | A — the ML pipeline bible |
| Systematic Trading | Robert Carver | 2015 | A — most practical code-level guide |
| Following the Trend | Andreas Clenow | 2013 | B — practical CTA replication |
| Trend Following with Managed Futures | Kaminski & Greyserman | 2014 | B — academic-practitioner bridge |
| Trading Systems and Methods | Perry Kaufman | 2013 | C — encyclopedic signal reference |
| Machine Learning for Asset Managers | De Prado | 2020 | B — entropy, clustering, portfolio optimization |
