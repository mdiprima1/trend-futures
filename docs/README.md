# Trend Futures — Research Documentation

## Overview

This project builds a comprehensive multi-futures trend following system, grounded in academic research and practitioner best practices. The research is organized into 7 sprints across 3 phases.

## Research Architecture

### Phase A: Foundation (Sprints 1-3)
- **Sprint 1**: Signal Landscape & Baseline — implement and compare all major signal types
- **Sprint 2**: Volatility Targeting & Position Sizing — establish the risk framework
- **Sprint 3**: Transaction Costs & Execution Reality — realistic cost modeling

### Phase B: Enhancement (Sprints 4-6)
- **Sprint 4**: Multi-Scale Signal Blending & Regime Detection
- **Sprint 5**: Machine Learning Enhancement (De Prado Pipeline)
- **Sprint 6**: Cross-Asset Dynamics & Network Effects

### Phase C: Integration (Sprint 7)
- **Sprint 7**: Full System Integration & Stress Testing

## Directory Structure

```
docs/
├── README.md                  ← this file
├── 00-research-overview.md    ← big picture, thesis, key findings
├── 01-paper-registry.md       ← all papers with summaries and relevance
├── 02-signal-taxonomy.md      ← complete signal type reference
├── 03-de-prado-pipeline.md    ← De Prado methods mapped to trend following
├── 04-universe-plan.md        ← futures market selection and expansion
├── papers/                    ← detailed notes on individual papers (as needed)
└── sprints/
    ├── sprint-01-signals.md
    ├── sprint-02-position-sizing.md
    ├── sprint-03-costs.md
    ├── sprint-04-regimes.md
    ├── sprint-05-ml-pipeline.md
    ├── sprint-06-cross-asset.md
    └── sprint-07-integration.md
```

## Calibration Baseline

Before building the trend system, we validated our backtest environment by replicating the ORB V10 winner strategy from QuantConnect:
- Equity correlation: 0.953
- Final equity diff: 2.7%
- CAGR match: 21.7% vs 22.1%
- See `run_calibration.py` and `src/orb_strategy.py`

## Data Infrastructure

- **Databento** (GLBX.MDP3): Futures 1-min bars, continuous front-month
- **yfinance**: SPY/VIX daily for supplementary data
- **Local cache**: Parquet files in `data/cache/`
