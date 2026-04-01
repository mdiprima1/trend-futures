# region imports
from AlgorithmImports import *
import numpy as np
# endregion

class IBS_Simple(QCAlgorithm):
    """
    Simplest possible IBS strategy on stocks.
    No history() calls. Use current bar's IBS directly.
    Buy when IBS < 0.2, sell next day at close.
    Long only.
    """
    def initialize(self):
        self.set_start_date(2020, 1, 2)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)

        self.tickers = ["NUE", "C", "MS", "CVX", "WFC",
                        "JPM", "BAC", "GS", "XOM", "COP",
                        "FCX", "DOW", "HAL", "SLB", "MPC",
                        "CAT", "DE", "GE", "SCHW", "AXP"]

        self.symbols = {}
        for t in self.tickers:
            self.symbols[t] = self.add_equity(t, Resolution.DAILY).symbol

        self._holding = {}  # ticker -> days_held

        self._yeq = {}; self._yret = {}; self._peq = None
        self._eql = []; self._led = None
        self._n_trades = 0; self._n_wins = 0

    def on_data(self, data):
        eq = self.portfolio.total_portfolio_value
        y = self.time.year
        if y not in self._yeq: self._yeq[y] = eq; self._yret[y] = []
        if self._peq and self._peq > 0: self._yret[y].append((eq - self._peq) / self._peq)
        self._peq = eq
        t = self.time.strftime("%Y%m%d")
        if t != self._led: self._eql.append(f"{t}:{eq:.0f}"); self._led = t

        for ticker in self.tickers:
            sym = self.symbols[ticker]
            if not data.bars.contains_key(sym):
                continue

            bar = data.bars[sym]
            c = float(bar.close); h = float(bar.high); l = float(bar.low)
            if c <= 0 or h <= l: continue

            # Exit: sell after 1 day holding
            if ticker in self._holding:
                self._holding[ticker] -= 1
                if self._holding[ticker] <= 0:
                    entry = self._holding.get(f"{ticker}_entry", c)
                    won = c > entry
                    self.liquidate(sym, tag=f"{'W' if won else 'L'} {ticker}")
                    if won: self._n_wins += 1
                    del self._holding[ticker]
                    if f"{ticker}_entry" in self._holding:
                        del self._holding[f"{ticker}_entry"]
                continue

            # IBS signal (current bar)
            ibs = (c - l) / (h - l)
            if ibs < 0.20:
                # Buy 5% of portfolio
                qty = int(eq * 0.05 / c)
                if qty >= 1:
                    self.market_order(sym, qty, tag=f"B {ticker} IBS={ibs:.2f}")
                    self._holding[ticker] = 1  # Exit tomorrow
                    self._holding[f"{ticker}_entry"] = c
                    self._n_trades += 1

    def on_end_of_algorithm(self):
        for y in sorted(self._yeq.keys()):
            r = self._yret.get(y, []); se = self._yeq[y]
            if r:
                a = np.array(r); s = float(np.std(a, ddof=1)) if len(a) > 1 else 0
                sh = (float(np.mean(a)) / s * np.sqrt(252)) if s > 0 else 0
                cu = np.cumprod(1 + a); ee = se * cu[-1]; rp = (ee / se - 1) * 100
                dd = float(np.min(cu / np.maximum.accumulate(cu) - 1) * 100)
            else: sh = rp = dd = 0; ee = se
            self.set_runtime_statistic(f"y_{y}", f"{sh:.3f}|{rp:.1f}|{dd:.1f}|{ee:.0f}")

        self.set_runtime_statistic("n_trades", str(self._n_trades))
        self.set_runtime_statistic("n_wins", str(self._n_wins))
        wr = self._n_wins / self._n_trades * 100 if self._n_trades > 0 else 0
        self.set_runtime_statistic("win_rate", f"{wr:.1f}")

        if self._eql:
            bs = 25; nb = 0
            for i in range(0, len(self._eql), bs):
                self.set_runtime_statistic(f"eq_{nb:03d}", "|".join(self._eql[i:i + bs]))
                nb += 1
            self.set_runtime_statistic("eq_count", str(nb))
