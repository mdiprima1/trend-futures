# region imports
from AlgorithmImports import *
import numpy as np
# endregion

class QCDiagnostic(QCAlgorithm):
    """
    Export EXACT indicator values and trade decisions from QC.
    This is the ground truth — our local engine must match these numbers.
    """
    def initialize(self):
        self._strategy = "ema_cross"  # Change per test
        self._ticker = "SPY"

        self.set_start_date(2020, 1, 2)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.asset = self.add_equity(self._ticker, Resolution.DAILY).symbol

        self._position = 0
        self._snapshots = []  # date|price|indicator_values|signal|position|equity
        self._trades = []
        self._eq = []
        self._led = None
        self.set_warm_up(200, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up or not data.contains_key(self.asset):
            return

        price = self.securities[self.asset].price
        eq = self.portfolio.total_portfolio_value
        t = self.time.strftime("%Y%m%d")

        if t != self._led:
            self._eq.append(f"{t}:{eq:.2f}")
            self._led = t

        # Get history
        h = self.history(self.asset, 200, Resolution.DAILY)
        if h.empty or len(h) < 30:
            return
        closes = h["close"].values

        # Compute EMA(12) and EMA(26) — EXACTLY as QC does it
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        signal = 1 if ema12 > ema26 else -1

        # Log snapshot (first 500 days)
        if len(self._snapshots) < 500:
            self._snapshots.append(
                f"{t}|{price:.4f}|E12={ema12:.4f}|E26={ema26:.4f}|sig={signal}|pos={self._position}|eq={eq:.2f}"
            )

        # Execute
        should_be = signal
        if should_be != self._position:
            # Close existing
            if self._position == 1:
                qty = self.portfolio[self.asset].quantity
                self.liquidate(self.asset, tag=f"CLOSE LONG")
                self._trades.append(f"CLOSE_L|{t}|{qty}|{price:.2f}")
            elif self._position == -1:
                qty = self.portfolio[self.asset].quantity
                self.liquidate(self.asset, tag=f"CLOSE SHORT")
                self._trades.append(f"CLOSE_S|{t}|{qty}|{price:.2f}")

            # Open new
            if should_be == 1:
                qty = int(self.portfolio.cash / price) if self.portfolio.cash > 0 else 0
                if qty > 0:
                    self.market_order(self.asset, qty, tag=f"BUY {qty}")
                    self._trades.append(f"BUY|{t}|{qty}|{price:.2f}")
            elif should_be == -1:
                qty = int(self.portfolio.total_portfolio_value * 0.95 / price)
                if qty > 0:
                    self.market_order(self.asset, -qty, tag=f"SHORT {qty}")
                    self._trades.append(f"SHORT|{t}|{qty}|{price:.2f}")

            self._position = should_be

    def _ema(self, data, span):
        a = 2.0 / (span + 1)
        e = float(data[0])
        for v in data[1:]:
            e = a * float(v) + (1 - a) * e
        return e

    def on_end_of_algorithm(self):
        # Snapshots (batched)
        bs = 20
        for i in range(0, len(self._snapshots), bs):
            self.set_runtime_statistic(f"sn_{i//bs:03d}", "|".join(self._snapshots[i:i+bs]).replace("||", "| |"))
        self.set_runtime_statistic("sn_count", str((len(self._snapshots) + bs - 1) // bs))
        self.set_runtime_statistic("sn_total", str(len(self._snapshots)))

        # Trades
        for i, tr in enumerate(self._trades[:100]):
            self.set_runtime_statistic(f"tr_{i:03d}", tr)
        self.set_runtime_statistic("tr_count", str(len(self._trades)))

        # Equity
        bs2 = 40
        for i in range(0, len(self._eq), bs2):
            self.set_runtime_statistic(f"eq_{i//bs2:03d}", "|".join(self._eq[i:i+bs2]))
        self.set_runtime_statistic("eq_count", str((len(self._eq) + bs2 - 1) // bs2))

        self.set_runtime_statistic("final_equity", f"{self.portfolio.total_portfolio_value:.2f}")
