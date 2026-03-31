# region imports
from AlgorithmImports import *
import numpy as np
# endregion

class Test1BuyHoldSPY(QCAlgorithm):
    """
    Calibration Test 1: Buy and hold SPY.
    Simplest possible test — buy $100K of SPY on day 1, hold forever.
    Export daily equity + trade details for comparison.
    """
    def initialize(self):
        self.set_start_date(2020, 1, 2)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self._bought = False
        self._eq = []
        self._led = None

    def on_data(self, data):
        if not self._bought and data.contains_key(self.spy):
            price = self.securities[self.spy].price
            qty = int(self.portfolio.cash / price)
            self.market_order(self.spy, qty, tag=f"BUY {qty}@{price:.2f}")
            self._bought = True
            self.log(f"BOUGHT {qty} SPY @ {price:.2f}, cost={qty*price:.2f}")

        # Record equity
        eq = self.portfolio.total_portfolio_value
        t = self.time.strftime("%Y%m%d")
        if t != self._led:
            self._eq.append(f"{t}:{eq:.2f}")
            self._led = t

    def on_end_of_algorithm(self):
        # Export equity curve
        bs = 40
        for i in range(0, len(self._eq), bs):
            self.set_runtime_statistic(f"eq_{i//bs:03d}", "|".join(self._eq[i:i+bs]))
        self.set_runtime_statistic("eq_count", str((len(self._eq) + bs - 1) // bs))
        self.set_runtime_statistic("eq_total", str(len(self._eq)))

        # Final stats
        eq = self.portfolio.total_portfolio_value
        ret = (eq / 100_000 - 1) * 100
        self.set_runtime_statistic("final_equity", f"{eq:.2f}")
        self.set_runtime_statistic("total_return_pct", f"{ret:.2f}")
