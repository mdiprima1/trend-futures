# Trend Futures

Multi-futures trend following system using Databento data and vectorbt backtesting.

## Project Structure
- `src/config.py` — API keys, contract specs, commissions
- `src/data.py` — Databento fetcher (ES/NQ 1m bars), yfinance (SPY/VIX daily), local parquet caching
- `src/orb_strategy.py` — ORB V10 winner strategy (calibration reference)
- `src/calibrate.py` — Compare local results against QuantConnect equity curve
- `run_calibration.py` — Main calibration runner
- `data/cache/` — Parquet cache for downloaded data (gitignored)

## Data Sources
- **Databento** (GLBX.MDP3): ES and NQ continuous front-month 1-min bars
- **yfinance**: SPY daily (for realized vol filter), VIX daily (for VIX filters)

## Calibration Status
Calibrated against QC ORB V10 winner (project 29466018, backtest 12aaf948):
- Equity correlation: 0.953
- Final equity: $2.53M local vs $2.47M QC (2.7% diff)
- CAGR: 21.7% vs 22.1%
- Known diff: Sharpe differs (1.43 vs 0.81) due to Databento front-month vs QC backward-ratio continuous contract construction affecting daily return volatility

## Dev Branch Workflow
Always work on dev branch first, test, then merge to main.
