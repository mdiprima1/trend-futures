# Signal Taxonomy — Complete Reference

## Classification Framework (Sepp & Lucic 2025)

Three families of trend-following signals, all of which can be shown to profit from positive return autocorrelation:

| Family | Type | Mechanism |
|--------|------|-----------|
| European | Moving Average Crossover | Smooth price, detect direction change |
| American | Breakout / Channel | Buy/sell on new highs/lows |
| TSMOM | Time-Series Momentum | Past return predicts future return |

**Key insight**: All three are equivalent up to a linear transformation when the return process has constant autocorrelation. They diverge in performance when autocorrelation is time-varying.

---

## 1. Moving Average Crossover Systems

### MA Types

| MA | Formula | Lag | Responsiveness | Notes |
|----|---------|-----|----------------|-------|
| SMA(N) | Mean of last N prices | High | Low | Most studied, simplest |
| EMA(N) | α*price + (1-α)*prev, α=2/(N+1) | Medium | Medium | Standard in practice |
| DEMA(N) | 2*EMA(N) - EMA(EMA(N)) | Low | High | Reduces lag, may overfit |
| Hull(N) | WMA(2*WMA(N/2) - WMA(N), √N) | Very Low | Very High | Near zero lag, noisy |
| KAMA(N) | Adaptive α based on efficiency ratio | Variable | Adaptive | Kaufman. Good in theory, tricky to calibrate |
| FRAMA(N) | Fractal-adaptive smoothing | Variable | Adaptive | Ehlers. Niche use |

### Common Window Pairs (Fast/Slow)

| Pair | Character | Typical Use |
|------|-----------|-------------|
| 5/20 | Very fast | Short-term trading, high turnover |
| 10/30 | Fast | Active trend following |
| 20/50 | Medium | Standard CTA speed |
| 50/200 | Slow | Position trading, low turnover |
| 10/100 | Asymmetric | Faster entry, slower exit |

### Signal Construction
- **Binary**: Long if fast > slow, short if fast < slow. Position = ±1.
- **Continuous**: Position proportional to (fast - slow) / slow, capped at ±1.
- **Multi-speed blend**: Average signals across multiple window pairs.

### Valeyre (2025) Finding
A single EMA with appropriately chosen half-life captures the trend premium as well as any complex basket. Adding more indicators risks overfitting without adding information.

---

## 2. Breakout / Channel Systems

### Donchian Channel
- **Entry**: Buy when price > highest high of N days. Sell when price < lowest low of M days.
- **Turtle System 1**: N=20 entry, M=10 exit
- **Turtle System 2**: N=55 entry, M=20 exit
- **Advantage**: Pure price action, no parameters beyond lookback
- **Disadvantage**: Late entry by definition (N days after the move started)

### ATR Channel (Keltner Variant)
- **Channel**: MA(N) ± K * ATR(P)
- **Typical**: MA(20) ± 2 * ATR(14)
- **Entry**: Break above/below channel
- **Advantage**: Volatility-adaptive, fewer false breaks than fixed-width channels

### Bollinger Band Breakout
- **Channel**: MA(N) ± K * StdDev(N)
- **Typical**: MA(20) ± 2σ
- **Less common** for trend following; bands contract in low vol, producing premature signals

---

## 3. Time-Series Momentum (TSMOM)

### Core Signal (Moskowitz et al. 2012)
```
signal = sign(r_{t-K, t})
position = signal * (target_vol / realized_vol)
```
Where r_{t-K, t} is the return over the past K periods.

### Lookback Windows

| Window | Character | Academic Support |
|--------|-----------|-----------------|
| 1 month | Very short-term, noisy | Weak standalone, helps in blend |
| 3 months | Short-term | Moderate |
| 6 months | Medium-term | Strong |
| 12 months | Standard | Strongest single window (Moskowitz) |
| 24 months | Long-term | Moderate, captures structural trends |

### Multi-window Blend
Babu et al. (2020/AQR) showed combining 1/3/6/12-month lookbacks outperforms any single window. Equal-weight blend is robust.

### MACD as TSMOM (Baz et al. 2015)
MACD(12,26) is mathematically equivalent to a weighted sum of exponentially-decaying past returns with half-life ~19 days. It is a continuous TSMOM signal.

---

## 4. Momentum Indicators as Trend Signals

| Indicator | Trend Use | Signal |
|-----------|-----------|--------|
| ROC(N) | Raw TSMOM | Long if ROC > 0, short if < 0 |
| MACD | Continuous trend | Long if MACD > signal line |
| RSI(14) | Trend filter | Trade trend only if RSI > 50 (up) or < 50 (down) |
| ADX(14) | Trend strength filter | Trade only when ADX > 20 or 25 |

---

## 5. Kalman Filters & State-Space Models

### Linear Kalman Filter
- State: [level, slope]
- Observation: price = level + noise
- Produces: continuously-updated trend estimate + uncertainty
- **Advantage**: Adapts smoothing dynamically based on signal-to-noise
- **Disadvantage**: Assumes linear Gaussian dynamics

### Hidden Markov Models
- States: {trending_up, trending_down, mean_reverting}
- Transition matrix estimated from data
- **Use**: Regime detection to activate/deactivate trend strategies
- **Reference**: Bulla et al. 2011

---

## 6. Autocorrelation & Persistence Measures

### Hurst Exponent
- H > 0.5: persistent (trending) — trend signals should work
- H = 0.5: random walk — no edge
- H < 0.5: anti-persistent (mean-reverting) — trend signals lose money
- **Estimation**: R/S analysis, DFA, wavelet
- **Practical use**: Regime filter, not standalone signal. Noisy with short data.

### Return Autocorrelation
- Direct measurement at lag k
- Positive autocorrelation at lag k → k-period momentum strategy has positive expected return
- **Sepp & Lucic (2025)**: exact P&L formula as function of autocorrelation structure

---

## Signal Evaluation Criteria

For Sprint 1, all signals will be evaluated on:

| Metric | Why It Matters |
|--------|----------------|
| Sharpe ratio (net of costs) | Risk-adjusted return |
| Max drawdown | Tail risk |
| Turnover | Drives transaction costs |
| Win rate | Psychological sustainability |
| Avg win / avg loss | Profit factor |
| Autocorrelation of signal returns | Clustering of wins/losses |
| Correlation across instruments | Diversification potential |
| Stability across sub-periods | Robustness |
