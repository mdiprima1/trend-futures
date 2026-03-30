# Trend Futures

A comprehensive multi-futures trend following system built on rigorous academic research (46 papers reviewed) and systematic engineering.

## Architecture

- **Data**: Databento (CME futures 1-min bars) + yfinance (SPY/VIX)
- **Backtesting**: vectorbt / custom vectorized engine
- **Universe**: 6 → 20 → 35 futures across equities, rates, FX, commodities
- **Research**: 7 sprints covering signals, sizing, costs, regimes, ML, cross-asset dynamics

## Research Phases

| Phase | Sprints | Focus |
|-------|---------|-------|
| A: Foundation | 1-3 | Signal landscape, position sizing, transaction costs |
| B: Enhancement | 4-6 | Regime detection, De Prado ML pipeline, cross-asset network effects |
| C: Integration | 7 | Full system, stress testing, validation |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # Add your DATABENTO_API_KEY
```

## Calibration

The backtest environment was validated by replicating an existing QuantConnect strategy:
- Equity correlation: 0.953
- Final equity difference: 2.7%

```bash
python run_calibration.py
```

## Documentation

All research documentation is in `docs/`:
- `00-research-overview.md` — thesis, key findings, sprint plan
- `01-paper-registry.md` — 46 papers with summaries and relevance ratings
- `02-signal-taxonomy.md` — complete signal type reference
- `03-de-prado-pipeline.md` — ML methods mapped to trend following
- `04-universe-plan.md` — futures market selection and phased expansion
- `sprints/` — detailed plans for each research sprint
