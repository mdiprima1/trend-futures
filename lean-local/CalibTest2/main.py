# region imports
from AlgorithmImports import *
import numpy as np
# endregion

class Test2SMACrossover(QCAlgorithm):
    """
    Calibration Test 2: SMA(50)/SMA(200) crossover on SPY.
    Long when SMA50 > SMA200, flat otherwise. Daily rebalance.
    Export trade log + equity curve.
    """
    def initialize(self):
        self.set_start_date(2020, 1, 2)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self._sma50 = self.sma(self.spy, 50, Resolution.DAILY)
        self._sma200 = self.sma(self.spy, 200, Resolution.DAILY)
        self._eq = []
        self._led = None
        self._trades = []
        self.set_warm_up(200, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up or not self._sma50.is_ready or not self._sma200.is_ready:
            return

        # Record equity
        eq = self.portfolio.total_portfolio_value
        t = self.time.strftime("%Y%m%d")
        if t != self._led:
            self._eq.append(f"{t}:{eq:.2f}")
            self._led = t

        # Signal
        should_be_long = self._sma50.current.value > self._sma200.current.value
        is_long = self.portfolio[self.spy].invested

        if should_be_long and not is_long:
            price = self.securities[self.spy].price
            qty = int(self.portfolio.cash / price)
            if qty > 0:
                self.market_order(self.spy, qty, tag=f"BUY {qty}")
                self._trades.append(f"BUY|{t}|{qty}|{price:.2f}")
        elif not should_be_long and is_long:
            qty = self.portfolio[self.spy].quantity
            self.liquidate(self.spy, tag=f"SELL {qty}")
            price = self.securities[self.spy].price
            self._trades.append(f"SELL|{t}|{qty}|{price:.2f}")

    def on_end_of_algorithm(self):
        # Equity
        bs = 40
        for i in range(0, len(self._eq), bs):
            self.set_runtime_statistic(f"eq_{i//bs:03d}", "|".join(self._eq[i:i+bs]))
        self.set_runtime_statistic("eq_count", str((len(self._eq)+bs-1)//bs))

        # Trades
        for i, tr in enumerate(self._trades):
            self.set_runtime_statistic(f"tr_{i:03d}", tr)
        self.set_runtime_statistic("tr_count", str(len(self._trades)))

        eq = self.portfolio.total_portfolio_value
        self.set_runtime_statistic("final_equity", f"{eq:.2f}")
        self.set_runtime_statistic("n_trades", str(len(self._trades)))
