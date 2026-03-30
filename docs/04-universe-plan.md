# Futures Universe Plan

## Selection Criteria

1. **Liquidity**: Sufficient open interest and volume for realistic execution
2. **Diversification**: Low correlation to existing markets in the portfolio
3. **Data availability**: Databento GLBX.MDP3 coverage (CME/CBOT/NYMEX/COMEX)
4. **Cost**: Reasonable commission and roll costs
5. **Trendability**: Historical evidence of positive autocorrelation at relevant timescales

## Phased Expansion

### Phase 1: Core Universe (Sprints 1-3) — 6 Markets

| Symbol | Name | Sector | Exchange | Multiplier | Databento Symbol |
|--------|------|--------|----------|------------|-----------------|
| ES | E-mini S&P 500 | Equity Index | CME | $50 | ES.c.0 |
| NQ | E-mini Nasdaq 100 | Equity Index | CME | $20 | NQ.c.0 |
| ZN | 10-Year T-Note | Fixed Income | CBOT | $1,000 | ZN.c.0 |
| GC | Gold | Metals | COMEX | $100 | GC.c.0 |
| CL | Crude Oil (WTI) | Energy | NYMEX | $1,000 | CL.c.0 |
| 6E | Euro FX | FX | CME | $125,000 | 6E.c.0 |

**Rationale**: One instrument per major sector. All highly liquid. Provides diversification across equity, rates, commodities, and FX risk factors.

### Phase 2: Extended Universe (Sprints 4-5) — Add 10-14 Markets

| Symbol | Name | Sector | Exchange | Multiplier | Databento Symbol |
|--------|------|--------|----------|------------|-----------------|
| ZT | 2-Year T-Note | Fixed Income | CBOT | $2,000 | ZT.c.0 |
| ZB | 30-Year T-Bond | Fixed Income | CBOT | $1,000 | ZB.c.0 |
| 6B | British Pound | FX | CME | $62,500 | 6B.c.0 |
| 6J | Japanese Yen | FX | CME | ¥12,500,000 | 6J.c.0 |
| 6A | Australian Dollar | FX | CME | A$100,000 | 6A.c.0 |
| NG | Natural Gas | Energy | NYMEX | $10,000 | NG.c.0 |
| HG | Copper | Metals | COMEX | $25,000 | HG.c.0 |
| SI | Silver | Metals | COMEX | $5,000 | SI.c.0 |
| ZC | Corn | Agriculture | CBOT | $50 | ZC.c.0 |
| ZS | Soybeans | Agriculture | CBOT | $50 | ZS.c.0 |

**Rationale**: Fills out the yield curve (2Y/10Y/30Y), adds FX diversification, expands commodities. All CME Group — single Databento dataset.

### Phase 3: Full Universe (Sprints 6-7) — Add 10-15 Markets

| Symbol | Name | Sector | Exchange | Multiplier | Databento Symbol |
|--------|------|--------|----------|------------|-----------------|
| RTY | E-mini Russell 2000 | Equity Index | CME | $50 | RTY.c.0 |
| NKD | Nikkei 225 (USD) | Equity Index | CME | $5 | NKD.c.0 |
| 6C | Canadian Dollar | FX | CME | C$100,000 | 6C.c.0 |
| 6S | Swiss Franc | FX | CME | CHF125,000 | 6S.c.0 |
| 6N | New Zealand Dollar | FX | CME | NZ$100,000 | 6N.c.0 |
| RB | RBOB Gasoline | Energy | NYMEX | $42,000 | RB.c.0 |
| HO | Heating Oil | Energy | NYMEX | $42,000 | HO.c.0 |
| ZW | Wheat | Agriculture | CBOT | $50 | ZW.c.0 |
| SB | Sugar #11 | Agriculture | ICE* | $1,120 | TBD |
| KC | Coffee | Agriculture | ICE* | $37,500 | TBD |
| CT | Cotton | Agriculture | ICE* | $50,000 | TBD |
| PL | Platinum | Metals | NYMEX | $50 | PL.c.0 |
| LE | Live Cattle | Agriculture | CME | $40,000 | LE.c.0 |

*Note: ICE markets (Sugar, Coffee, Cotton) may need IFEU.IMPACT or IFUS.IMPACT dataset on Databento. Verify availability and cost before including.

### Target Final Universe: 30-35 Markets

| Sector | Count | Target Risk Allocation |
|--------|-------|----------------------|
| Equity Indices | 3-4 | 20-25% |
| Fixed Income | 3 | 20-25% |
| FX | 5-6 | 15-20% |
| Energy | 3-4 | 15-20% |
| Metals | 3-4 | 10-15% |
| Agriculture | 5-6 | 10-15% |

## Databento Data Costs

Preliminary cost check (2026-03-30):
- ES.c.0, NQ.c.0: $0.00 for 2018-2025 (previously purchased or free tier)
- Need to verify costs for remaining symbols before downloading

**Action item for Sprint 1**: Run `metadata.get_cost()` for all Phase 1 symbols before downloading.

## Sector Correlation Notes

Key correlation clusters to be aware of:
- **Equity indices**: ES, NQ, RTY highly correlated (~0.85-0.95). Treat as one sector.
- **Rates curve**: ZT, ZN, ZB correlated but with useful differences. ZT < ZN < ZB in sensitivity.
- **Energy**: CL, RB, HO very correlated. NG is relatively independent.
- **Precious metals**: GC, SI moderately correlated (~0.6-0.7).
- **Grains**: ZC, ZS, ZW moderately correlated (~0.5-0.7).
- **FX**: Grouped by USD pairs. Commodity currencies (AUD, CAD, NZD) cluster together.

HRP portfolio construction (Sprint 2) will automatically handle these clusters.

## Roll Schedule Considerations

| Contract | Typical Roll | Method |
|----------|-------------|--------|
| ES, NQ | Quarterly (Mar/Jun/Sep/Dec), ~8 days before expiry | Volume switch |
| ZN, ZB, ZT | Quarterly, ~7 days before first notice | Volume switch |
| CL | Monthly, ~3-5 days before expiry | Calendar |
| GC | Feb/Apr/Jun/Aug/Oct/Dec, ~5 days before first notice | Volume switch |
| 6E, 6B, 6J | Quarterly, ~5 days before expiry | Volume switch |

Databento continuous contracts (`.c.0`) handle roll automatically. We'll use front-month continuous for signal generation and track roll costs separately for PnL.
