# region imports
from AlgorithmImports import *
import numpy as np
# endregion

class Test3RSIMeanReversion(QCAlgorithm):
    """
    Calibration Test 3: RSI(3) mean reversion on SPY with triple barrier.
    Buy when RSI < 25, sell when RSI > 75.
    PT = 1.5x ATR, SL = 1.0x ATR, time limit = 5 bars.
    Export every trade detail.
    """
    def initialize(self):
        self.set_start_date(2020, 1, 2)
        self.set_end_date(2024, 12, 31)
        self.set_cash(100_000)
        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol

        self._in_trade = False
        self._direction = 0
        self._entry_price = 0
        self._pt_price = 0
        self._sl_price = 0
        self._bars_left = 0
        self._entry_date = None

        self._eq = []
        self._led = None
        self._trades = []

        self.set_warm_up(20, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        if not data.contains_key(self.spy):
            return

        # Record equity
        eq = self.portfolio.total_portfolio_value
        t = self.time.strftime("%Y%m%d")
        if t != self._led:
            self._eq.append(f"{t}:{eq:.2f}")
            self._led = t

        price = self.securities[self.spy].price
        if price <= 0:
            return

        # Get RSI and ATR
        h = self.history(self.spy, 20, Resolution.DAILY)
        if h.empty or len(h) < 14:
            return

        closes = h["close"].values
        highs = h["high"].values
        lows = h["low"].values

        # RSI(3)
        d = np.diff(closes)
        gains = np.where(d > 0, d, 0)
        losses = np.where(d < 0, -d, 0)
        avg_g = np.mean(gains[-3:])
        avg_l = np.mean(losses[-3:])
        rsi = 100 - (100 / (1 + avg_g / avg_l)) if avg_l > 0 else 100

        # ATR(14)
        prev_c = np.roll(closes, 1); prev_c[0] = closes[0]
        tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_c), np.abs(lows - prev_c)))
        atr_val = float(np.mean(tr[-14:]))

        # Manage existing trade
        if self._in_trade:
            self._bars_left -= 1
            hit = False
            won = False

            if self._direction == 1:
                if price <= self._sl_price:
                    hit = True; won = False
                elif price >= self._pt_price:
                    hit = True; won = True
            else:
                if price >= self._sl_price:
                    hit = True; won = False
                elif price <= self._pt_price:
                    hit = True; won = True

            if self._bars_left <= 0:
                hit = True
                won = (price - self._entry_price) * self._direction > 0

            if hit:
                self.liquidate(self.spy, tag=f"{'WIN' if won else 'LOSS'}")
                self._trades.append(
                    f"{self._entry_date}|{t}|{'L' if self._direction==1 else 'S'}|"
                    f"{self._entry_price:.2f}|{price:.2f}|{'W' if won else 'L'}|"
                    f"{(price-self._entry_price)*self._direction:.2f}"
                )
                self._in_trade = False
            return

        # New signal
        signal = 0
        if rsi < 25:
            signal = 1
        elif rsi > 75:
            signal = -1

        if signal == 0:
            return

        # Enter trade
        qty = max(1, int(100_000 * 0.1 / (atr_val * 1.0)))  # Risk 10% of initial
        if signal == 1:
            self.market_order(self.spy, qty, tag=f"BUY RSI={rsi:.0f}")
            self._pt_price = price + 1.5 * atr_val
            self._sl_price = price - 1.0 * atr_val
        else:
            self.market_order(self.spy, -qty, tag=f"SHORT RSI={rsi:.0f}")
            self._pt_price = price - 1.5 * atr_val
            self._sl_price = price + 1.0 * atr_val

        self._in_trade = True
        self._direction = signal
        self._entry_price = price
        self._bars_left = 5
        self._entry_date = t

    def on_end_of_algorithm(self):
        bs = 40
        for i in range(0, len(self._eq), bs):
            self.set_runtime_statistic(f"eq_{i//bs:03d}", "|".join(self._eq[i:i+bs]))
        self.set_runtime_statistic("eq_count", str((len(self._eq)+bs-1)//bs))

        for i, tr in enumerate(self._trades):
            self.set_runtime_statistic(f"tr_{i:03d}", tr)
        self.set_runtime_statistic("tr_count", str(len(self._trades)))

        eq = self.portfolio.total_portfolio_value
        self.set_runtime_statistic("final_equity", f"{eq:.2f}")

        # Summary
        wins = sum(1 for t in self._trades if '|W|' in t)
        total = len(self._trades)
        wr = wins / total * 100 if total > 0 else 0
        self.set_runtime_statistic("win_rate", f"{wr:.1f}")
