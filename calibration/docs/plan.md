# Calibration Plan — Match Local Backtest to QC/LEAN Exactly

## Goal
Build a local backtesting engine that produces results within 1% of QuantConnect
on the SAME algorithm. No approximations, no "close enough."

## Approach
Start simple (stocks/ETFs), understand every difference, then scale to futures.

### Test 1: Buy-and-Hold SPY
Simplest possible test. Zero logic, just hold.
- QC: AddEquity("SPY"), buy on day 1, hold
- Local: SPY daily data, compute returns
- Match: total return, daily equity curve

### Test 2: SMA Crossover on SPY
Simple signal logic, daily rebalance.
- QC: SMA(50)/SMA(200) crossover, long/flat
- Local: same logic on same data
- Match: trade dates, number of trades, equity curve

### Test 3: RSI Mean Reversion on SPY
Closer to our casino strategy.
- QC: RSI(3) < 30 → buy, RSI(3) > 70 → sell
- Local: same logic
- Match: trade-by-trade comparison

### Test 4: RSI on SPY with Triple Barrier
Add the barrier exit logic.
- QC: RSI entry + ATR-based PT/SL
- Local: same
- Match: per-trade entry/exit prices and PnL

### Test 5: Single Futures Contract (ES)
First futures test. Use mapped contract.
- QC: ES hourly, RSI MR, single contract
- Local: same
- Compare: how do rolls, bar construction, and fills differ?

### Test 6: Casino V1 on ES Only
Single instrument casino bet.
- QC: our actual casino algo on ES only
- Local: same
- This should tell us EXACTLY where the gap comes from

## Method
For each test:
1. Write QC algo, run via lean-cli
2. Export equity curve + trade log from QC (via runtime stats)
3. Write identical local Python version
4. Compare day-by-day, trade-by-trade
5. Document every difference found
