# Calibration Findings

## QC Execution Model (Learned from Tests 1-2)

### Key Rules
1. **Market orders fill NEXT DAY at open** — not same-day close
2. **Commissions**: ~$0.005/share on equities ($1.68 for 336 shares)
3. **Price adjustment**: QC uses backward-ratio for dividends/splits
4. **SMA/indicators**: Computed on adjusted close prices
5. **Cash management**: Unfilled cash sits at 0% interest

### What Matches Perfectly
- Share quantities (same buy logic → same qty)
- Trade dates (same signal → same trigger day, fill T+1)
- Number of trades (signal logic is deterministic)

### Remaining Gaps
| Source | Impact | Fixable? |
|--------|--------|----------|
| yfinance vs QC adjusted prices | ~$0.03/share | Yes — use QC prices |
| Fill price (local open vs QC fill) | ~$230 over 5yr | Small, acceptable |
| Commission model | $1.68 vs $0 if forgotten | Yes — include fees |

## Test Results

### Test 1: Buy-and-Hold SPY (2020-2024)
| Metric | Local | QC | Diff |
|--------|-------|-----|------|
| Final Equity | $195,481.18 | $195,481.16 | **$0.02** |
| Match | **PERFECT** (after fixing fill model) | | |

### Test 2: SMA(50/200) Crossover on SPY
| Metric | Local | QC | Diff |
|--------|-------|-----|------|
| Final Equity | $162,647 | $162,877 | **$230 (0.14%)** |
| Trades | 5 | 5 | Match |
| Trade dates | Match | Match | Match |
| Match | **EXCELLENT** | | |

## Rules for Local Backtester to Match QC

```python
# 1. Signal computed on day T at close
# 2. Order submitted (not filled)
# 3. Fill on day T+1 at OPEN price
# 4. Commission charged on fill
# 5. Position valued at close each day
# 6. Cash earns 0%
```

## Next: Futures Tests
The equity tests prove the execution model is correct. Now test with
futures to understand:
- How does QC's `Resolution.HOUR` construct bars?
- How do rolls affect fills?
- What happens with multiple positions?
