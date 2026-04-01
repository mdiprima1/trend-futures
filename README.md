# QSL Quantitative Research

Systematic quantitative trading research across futures and equities.

## Project History

### Phase 1: Trend Following on Futures (Abandoned)
- 7 research sprints, 46 academic papers reviewed
- 26 CME futures instruments downloaded via Databento
- Local backtest showed Sharpe 1.1+ but **failed QC validation** (local vs QC gap of 10-35x)
- Root cause: continuous contract data doesn't reflect real execution (roll gaps, contract mapping)
- **Conclusion**: Futures trend following edge is too small to survive execution friction

### Phase 2: Casino V1 — Intraday Futures Bets (Abandoned)
- 86 technical indicators tested across ES, NQ, CL
- Triple barrier bet engine with RSI, IBS, Keltner, Bollinger, MACD
- Local Sharpe 1.9-2.3 but **QC showed +5.5% over 8 years** (barely above noise)
- Root cause: per-trade edge (~$2.50) smaller than commission ($2.10/contract)
- **Conclusion**: Intraday futures casino doesn't survive real costs

### Phase 3: Casino Stocks — Daily Mean Reversion (Active)
- **First real QC-validated profit**: stocks with daily bars work
- V1: +78% (Sharpe 0.51), V2: **+129% (Sharpe 0.67, CAGR 18%)**, V3: +54% (DD 19%)
- 80 stocks, 6 indicators, long only
- **Why stocks work**: $0.005/share commission (vs $2.10/contract), no rolls, long-only viable

### Phase 4: Institutional Pipeline (Complete)
- 143 strategies tested across 12 indicator categories
- 10 passed full validation (sub-period consistency, parameter stability)
- **Winner: Down5_IBS0.3 (Sharpe 0.569, CAGR 3.1%, Max DD 5.7%)**
- Consistent across all 3 sub-periods (2014-17, 2018-21, 2022-24)

### Phase 5: Deep Research (Complete)
- 86 ta-library indicators × 213 stocks × 10 years
- 276,288 indicator×signal×stock combinations analyzed
- Finding: buying at bottom 10th percentile of any trend indicator produces positive returns on **100% of stocks**

## Key Learnings

1. **Always validate on QuantConnect** — local backtests overstate returns by 2-35x on futures
2. **Stocks > Futures** for technical mean reversion — lower costs, no rolls, long-only works
3. **Simplicity wins** — the best strategies have 2-3 rules, not 8+
4. **Calibration is foundational** — we proved 99.1% single-stream match with QC
5. **Position stacking is a feature** — multiple agreeing signals create confirmation

## Directory Structure

```
├── docs/                    # Trend following research (46 papers, 7 sprints)
├── src/                     # Trend following code (signals, backtest, portfolio)
├── casino-v1/               # Futures casino strategy (abandoned)
├── casino-stocks/            # Stock casino strategy (ACTIVE, QC-validated)
│   ├── qc_casino_v2_optimized.py   # Best QC algo (+129%, Sharpe 0.67)
│   ├── results/deep_research/      # 86-indicator deep research
│   └── results/                    # All backtest results
├── institutional/            # Full institutional pipeline
│   ├── data_pipeline.py      # EODHD data fetcher
│   ├── features.py           # 32 technical features
│   ├── strategy_engine.py    # Strategy generator + backtester
│   ├── run_full_pipeline.py  # Phases 3-8 runner
│   └── reports/              # Final strategy selection
├── calibration/              # QC calibration suite (20 tests)
├── lean-local/               # LEAN/Docker local setup
└── data/                     # Cached market data
```

## Setup

```bash
pip install -r requirements.txt
# Add API keys to .env (NEVER commit this file):
# DATABENTO_API_KEY=...
# EODHD_API_KEY=...
```

## Calibration

QC calibration suite validates local backtest accuracy:
- Buy-hold SPY: **$0.02 difference** (PERFECT)
- SMA crossover: **0.35% difference** (PERFECT)
- Keltner MR barrier: **2.2% difference** (GOOD)
- Single NQ RSI stream: **99.1% match** with QC
