# Trend Futures

Multi-futures trend following system using Databento data and vectorbt backtesting.

## Project Structure
```
trend-futures/
├── src/
│   ├── config.py          — API keys, contract specs, commissions
│   ├── data.py            — Databento fetcher, yfinance, parquet caching
│   ├── orb_strategy.py    — ORB V10 winner (calibration reference)
│   └── calibrate.py       — Compare local vs QuantConnect results
├── docs/
│   ├── README.md          — Research documentation index
│   ├── 00-research-overview.md  — Big picture thesis and findings
│   ├── 01-paper-registry.md     — All 46 papers with summaries
│   ├── 02-signal-taxonomy.md    — Complete signal type reference
│   ├── 03-de-prado-pipeline.md  — De Prado methods for trend following
│   ├── 04-universe-plan.md      — Futures market selection (6→20→35)
│   └── sprints/           — Individual sprint plans (01 through 07)
├── notebooks/             — Jupyter analysis notebooks
├── data/cache/            — Parquet cache (gitignored)
├── run_calibration.py     — Calibration runner
└── requirements.txt
```

## Research Plan

7 sprints across 3 phases:
- **Phase A (Foundation)**: Sprints 1-3 — signals, sizing, costs
- **Phase B (Enhancement)**: Sprints 4-6 — regimes, ML (De Prado), cross-asset
- **Phase C (Integration)**: Sprint 7 — full system, stress testing, 8-Gate

Current status: **Sprint 1 next** — Signal Landscape & Baseline on 6 core markets.

## Data Sources
- **Databento** (GLBX.MDP3): Futures continuous front-month 1-min bars
- **yfinance**: SPY daily, VIX daily (supplementary filters)

## Calibration Baseline
ORB V10 winner replicated locally (QC project 29466018):
- Equity correlation: 0.953, Final equity diff: 2.7%, CAGR: 21.7% vs 22.1%

## Key Research Findings
1. Signal simplicity beats complexity (single EMA captures most trend premium)
2. Portfolio construction is where the alpha lives (HRP, risk parity, vol targeting)
3. ML enhances but does not replace trend (meta-labeling for bet sizing)
4. Cross-asset lead-lag dynamics add meaningful value
5. Transaction costs determine optimal lookback and turnover

## Dev Branch Workflow
Always work on dev branch first, test, then merge to main.
Read docs/ before starting any sprint work.
