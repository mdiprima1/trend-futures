# region imports
from AlgorithmImports import *
import numpy as np
# endregion

class CalibrationTest(QCAlgorithm):
    """
    Universal calibration test algorithm.
    Reads strategy config from parameters, runs the strategy,
    exports equity curve + every trade + indicator values for comparison.

    Strategies (set via 'strategy' parameter):
    1. buyhold — Buy and hold
    2. sma_cross — SMA crossover (long/flat)
    3. rsi_mr — RSI mean reversion with triple barrier
    4. boll_mr — Bollinger Band mean reversion
    5. ema_cross — EMA crossover (long/short)
    6. macd — MACD crossover
    7. keltner_mr — Keltner channel mean reversion
    8. momentum — N-day momentum (long/short)
    """

    def initialize(self):
        # Read parameters
        self._strategy = self.get_parameter("strategy", "buyhold")
        self._ticker = self.get_parameter("ticker", "SPY")
        self._start_year = int(self.get_parameter("start_year", "2020"))
        self._end_year = int(self.get_parameter("end_year", "2024"))

        self.set_start_date(self._start_year, 1, 2)
        self.set_end_date(self._end_year, 12, 31)
        self.set_cash(100_000)

        self.asset = self.add_equity(self._ticker, Resolution.DAILY).symbol
        self._position = 0  # 0=flat, 1=long, -1=short

        # Triple barrier params for MR strategies
        self._pt_mult = float(self.get_parameter("pt_mult", "1.5"))
        self._sl_mult = float(self.get_parameter("sl_mult", "1.0"))
        self._max_bars = int(self.get_parameter("max_bars", "5"))
        self._in_barrier = False
        self._barrier_dir = 0
        self._barrier_entry = 0
        self._barrier_pt = 0
        self._barrier_sl = 0
        self._barrier_bars = 0

        # Data export
        self._eq = []
        self._trades = []
        self._indicators = []  # First 100 indicator snapshots
        self._led = None

        self.set_warm_up(200, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up or not data.contains_key(self.asset):
            return

        price = self.securities[self.asset].price
        if price <= 0:
            return

        # Record equity
        eq = self.portfolio.total_portfolio_value
        t = self.time.strftime("%Y%m%d")
        if t != self._led:
            self._eq.append(f"{t}:{eq:.2f}")
            self._led = t

        # Get history for indicators
        h = self.history(self.asset, 200, Resolution.DAILY)
        if h.empty or len(h) < 50:
            return
        closes = h["close"].values
        highs = h["high"].values
        lows = h["low"].values

        # Compute indicators based on strategy
        signal = 0

        if self._strategy == "buyhold":
            signal = 1  # Always long

        elif self._strategy == "sma_cross":
            sma50 = np.mean(closes[-50:])
            sma200 = np.mean(closes[-200:]) if len(closes) >= 200 else sma50
            signal = 1 if sma50 > sma200 else 0
            if len(self._indicators) < 100:
                self._indicators.append(f"{t}|{price:.2f}|SMA50={sma50:.2f}|SMA200={sma200:.2f}|sig={signal}")

        elif self._strategy == "ema_cross":
            ema12 = self._ema(closes, 12)
            ema26 = self._ema(closes, 26)
            signal = 1 if ema12 > ema26 else -1
            if len(self._indicators) < 100:
                self._indicators.append(f"{t}|{price:.2f}|EMA12={ema12:.2f}|EMA26={ema26:.2f}|sig={signal}")

        elif self._strategy == "macd":
            ema12 = self._ema(closes, 12)
            ema26 = self._ema(closes, 26)
            macd_line = ema12 - ema26
            signal_line = self._ema_arr(self._macd_hist(closes), 9) if len(closes) >= 35 else 0
            signal = 1 if macd_line > signal_line else -1
            if len(self._indicators) < 100:
                self._indicators.append(f"{t}|{price:.2f}|MACD={macd_line:.4f}|Sig={signal_line:.4f}|sig={signal}")

        elif self._strategy == "rsi_mr":
            rsi_val = self._rsi(closes, 3)
            atr_val = self._atr(highs, lows, closes, 14)
            if len(self._indicators) < 100:
                self._indicators.append(f"{t}|{price:.2f}|RSI={rsi_val:.1f}|ATR={atr_val:.2f}")
            return self._handle_barrier(price, rsi_val, atr_val,
                                        buy_cond=rsi_val < 25, sell_cond=rsi_val > 75)

        elif self._strategy == "boll_mr":
            mid = np.mean(closes[-20:])
            std = np.std(closes[-20:])
            upper = mid + 2 * std
            lower = mid - 2 * std
            atr_val = self._atr(highs, lows, closes, 14)
            if len(self._indicators) < 100:
                self._indicators.append(f"{t}|{price:.2f}|BB_U={upper:.2f}|BB_L={lower:.2f}|ATR={atr_val:.2f}")
            return self._handle_barrier(price, 0, atr_val,
                                        buy_cond=price < lower, sell_cond=price > upper)

        elif self._strategy == "keltner_mr":
            ema_val = self._ema(closes, 20)
            atr_val = self._atr(highs, lows, closes, 14)
            upper = ema_val + 2 * atr_val
            lower = ema_val - 2 * atr_val
            if len(self._indicators) < 100:
                self._indicators.append(f"{t}|{price:.2f}|K_U={upper:.2f}|K_L={lower:.2f}|ATR={atr_val:.2f}")
            return self._handle_barrier(price, 0, atr_val,
                                        buy_cond=price < lower, sell_cond=price > upper)

        elif self._strategy == "momentum":
            period = 63  # ~3 months
            if len(closes) >= period:
                mom = closes[-1] / closes[-period] - 1
                signal = 1 if mom > 0 else -1
                if len(self._indicators) < 100:
                    self._indicators.append(f"{t}|{price:.2f}|MOM={mom:.4f}|sig={signal}")

        # Execute signal (non-barrier strategies)
        self._execute_signal(signal, price)

    def _handle_barrier(self, price, indicator_val, atr_val, buy_cond, sell_cond):
        """Handle triple barrier entry/exit logic."""
        t = self.time.strftime("%Y%m%d")

        if self._in_barrier:
            self._barrier_bars -= 1
            hit = False; won = False

            if self._barrier_dir == 1:
                if price <= self._barrier_sl: hit = True; won = False
                elif price >= self._barrier_pt: hit = True; won = True
            else:
                if price >= self._barrier_sl: hit = True; won = False
                elif price <= self._barrier_pt: hit = True; won = True

            if self._barrier_bars <= 0:
                hit = True
                won = (price - self._barrier_entry) * self._barrier_dir > 0

            if hit:
                self.liquidate(self.asset, tag=f"{'W' if won else 'L'}")
                pnl_pts = (price - self._barrier_entry) * self._barrier_dir
                self._trades.append(f"{'W' if won else 'L'}|{t}|{self._barrier_dir}|"
                                    f"entry={self._barrier_entry:.2f}|exit={price:.2f}|pnl={pnl_pts:.2f}")
                self._in_barrier = False
                self._position = 0
            return

        # New entry
        if buy_cond and not self._in_barrier:
            qty = max(1, int(self.portfolio.total_portfolio_value * 0.1 / (atr_val if atr_val > 0 else 1)))
            self.market_order(self.asset, qty, tag=f"BUY")
            self._barrier_dir = 1
            self._barrier_entry = price
            self._barrier_pt = price + self._pt_mult * atr_val
            self._barrier_sl = price - self._sl_mult * atr_val
            self._barrier_bars = self._max_bars
            self._in_barrier = True
            self._position = 1

        elif sell_cond and not self._in_barrier:
            qty = max(1, int(self.portfolio.total_portfolio_value * 0.1 / (atr_val if atr_val > 0 else 1)))
            self.market_order(self.asset, -qty, tag=f"SHORT")
            self._barrier_dir = -1
            self._barrier_entry = price
            self._barrier_pt = price - self._pt_mult * atr_val
            self._barrier_sl = price + self._sl_mult * atr_val
            self._barrier_bars = self._max_bars
            self._in_barrier = True
            self._position = -1

    def _execute_signal(self, signal, price):
        """Execute long/short/flat signal."""
        t = self.time.strftime("%Y%m%d")
        if signal == 1 and self._position != 1:
            if self._position == -1:
                self.liquidate(self.asset, tag="CLOSE SHORT")
            qty = int(self.portfolio.cash / price) if self.portfolio.cash > 0 else 0
            if qty > 0:
                self.market_order(self.asset, qty, tag=f"BUY {qty}")
                self._trades.append(f"BUY|{t}|{qty}|{price:.2f}")
            self._position = 1

        elif signal == -1 and self._position != -1:
            if self._position == 1:
                self.liquidate(self.asset, tag="CLOSE LONG")
                self._trades.append(f"SELL|{t}|{self.portfolio[self.asset].quantity}|{price:.2f}")
            qty = int(self.portfolio.total_portfolio_value * 0.95 / price)
            if qty > 0:
                self.market_order(self.asset, -qty, tag=f"SHORT {qty}")
                self._trades.append(f"SHORT|{t}|{qty}|{price:.2f}")
            self._position = -1

        elif signal == 0 and self._position != 0:
            self.liquidate(self.asset, tag="FLAT")
            self._trades.append(f"FLAT|{t}|{self.portfolio[self.asset].quantity}|{price:.2f}")
            self._position = 0

    # ── Helper Functions ──

    def _ema(self, data, span):
        a = 2.0 / (span + 1); e = float(data[0])
        for v in data[1:]: e = a * float(v) + (1 - a) * e
        return e

    def _ema_arr(self, data, span):
        """EMA of array, return last value."""
        if len(data) == 0: return 0
        a = 2.0 / (span + 1); e = float(data[0])
        for v in data[1:]: e = a * float(v) + (1 - a) * e
        return e

    def _macd_hist(self, closes):
        """Return MACD line as array."""
        result = []
        ema12 = float(closes[0]); ema26 = float(closes[0])
        a12 = 2/13; a26 = 2/27
        for c in closes:
            ema12 = a12 * float(c) + (1 - a12) * ema12
            ema26 = a26 * float(c) + (1 - a26) * ema26
            result.append(ema12 - ema26)
        return result

    def _rsi(self, closes, period):
        d = np.diff(closes)
        g = np.where(d > 0, d, 0); l = np.where(d < 0, -d, 0)
        ag = np.mean(g[-period:]); al = np.mean(l[-period:])
        return 100 - (100 / (1 + ag / al)) if al > 0 else 100

    def _atr(self, h, l, c, period):
        pc = np.roll(c, 1); pc[0] = c[0]
        tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
        return float(np.mean(tr[-period:])) if len(tr) >= period else 0

    # ── Export ──

    def on_end_of_algorithm(self):
        # Strategy info
        self.set_runtime_statistic("strategy", self._strategy)
        self.set_runtime_statistic("ticker", self._ticker)

        # Equity
        bs = 40
        for i in range(0, len(self._eq), bs):
            self.set_runtime_statistic(f"eq_{i//bs:03d}", "|".join(self._eq[i:i+bs]))
        self.set_runtime_statistic("eq_count", str((len(self._eq) + bs - 1) // bs))

        # Trades
        for i, tr in enumerate(self._trades[:200]):
            self.set_runtime_statistic(f"tr_{i:03d}", tr)
        self.set_runtime_statistic("tr_count", str(len(self._trades)))

        # Indicator snapshots
        for i, ind in enumerate(self._indicators[:50]):
            self.set_runtime_statistic(f"ind_{i:03d}", ind)
        self.set_runtime_statistic("ind_count", str(min(len(self._indicators), 50)))

        eq = self.portfolio.total_portfolio_value
        self.set_runtime_statistic("final_equity", f"{eq:.2f}")
        self.set_runtime_statistic("total_return", f"{(eq/100000-1)*100:.2f}")
