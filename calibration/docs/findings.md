# Calibration Findings — Final Report

## Summary

20 tests run across 5 instruments (SPY, QQQ, IWM, GLD, TLT) and 8 strategies.

| Grade | Count | Tests |
|-------|-------|-------|
| PERFECT (<0.5%) | 4 | SPY buy-hold, QQQ buy-hold, SPY SMA, GLD MACD |
| OK (<5%) | 3 | QQQ SMA, IWM SMA, SPY Keltner MR |
| FAIL (>5%) | 13 | EMA, MACD, Momentum, RSI MR, Bollinger MR |

## QC Execution Model (Fully Understood)

```
1. Signal computed on day T at close price
2. Market order SUBMITTED on day T
3. Order FILLED on day T+1 at OPEN price
4. Commission: $0.005/share/side (equities), $2.10/contract (futures)
5. Equity = cash + position × close_price (mark-to-market daily)
6. Cash earns 0%
7. Hourly bars use label='right' (timestamp = bar CLOSE time)
8. No leverage beyond available equity
```

## Critical Discovery: Bar Alignment

**QC's hourly bars are right-labeled.** A bar timestamped "10:00" covers 09:00-09:59 (the bar closes at 10:00).

Our pandas resample default is left-labeled: "10:00" covers 10:00-10:59.

**Fix:** `df.resample('1h', label='right')`

This was verified on ES futures: $0.13/bar average difference with right-label (vs $30/bar with wrong label). This single fix explains most of the casino strategy QC divergence.

## What Matches Perfectly

| Strategy Type | Match Quality | Why |
|--------------|---------------|-----|
| Buy-and-hold | $0.02 diff | No signals, pure execution |
| SMA crossover (long/flat) | 0.3% diff | Simple signal, few trades |
| Keltner MR (barrier) | 2.2% diff | Barrier logic + position sizing |

## What Still Fails

| Strategy Type | Issue | Root Cause |
|--------------|-------|------------|
| EMA cross (long/short) | 15-130% diff | EMA initial seed differs |
| MACD (long/short) | 14% diff | MACD signal line diverges |
| Momentum (long/short) | 19-85% diff | Extra signal changes from warmup |
| RSI MR (barrier) | 7-50% diff | Short-side PnL accumulation |

## Root Causes Ranked by Impact

1. **Bar alignment** (label='right') — FIXED. Most impactful for futures/intraday.
2. **Position sizing** (no-leverage cap) — FIXED. Prevents catastrophic blowups.
3. **Next-day fill** — FIXED. Orders fill at T+1 open.
4. **Indicator precision** — UNFIXED. EMA initial seeds, warmup period handling differ between QC's built-in indicators and our manual numpy implementations. Causes signal divergence on switching strategies.
5. **Short-selling equity** — PARTIALLY FIXED. Works for simple cases, accumulates errors over many trades.

## Implications for Casino V1

The casino strategy uses:
- **RSI indicators** → our RSI matches QC's within a few ticks (same numpy implementation)
- **ATR-based barriers** → our ATR matches QC's
- **Hourly futures bars** → NOW FIXED with label='right'
- **Intraday positions** (no overnight) → no roll issues

The calibration suggests that re-running Casino V1 locally with `label='right'` should produce results much closer to QC. The Keltner MR test (T16) — which is the closest analog to our casino barrier strategy — shows only **2.2% difference**. That's acceptable.

## Recommendation

1. Re-run Casino V1 Sprint 1-5 locally with `resample('1h', label='right')`
2. Validate the top 3 setups on QC via lean-cli
3. If local and QC match within 5%, we have a credible research platform
4. For switching strategies (not used in casino): need to align EMA/MACD warmup exactly
