# Position Stacking Discovery

QC stacks multiple bets on the same instrument.
When NQ_IBS and NQ_RSI_MR both go short, QC holds -2 NQ contracts.
This is why single-stream matches 99.1% but multi-stream diverges 35x.

Fix: limit to 1 bet per instrument, or track combined positions.
