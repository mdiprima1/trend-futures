# region imports
from AlgorithmImports import *
import numpy as np
# endregion

class Test5FuturesRSI(QCAlgorithm):
    """
    Calibration Test 5: RSI(3) on ES futures, hourly bars.
    Single instrument, single contract at a time.
    Export EVERY detail for comparison.
    """
    def initialize(self):
        self.set_start_date(2023, 1, 1)  # Short period for debugging
        self.set_end_date(2023, 12, 31)
        self.set_cash(500_000)

        self.es = self.add_future(Futures.Indices.SP_500_E_MINI,
            resolution=Resolution.HOUR,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            contract_depth_offset=0)
        self.es.set_filter(0, 90)

        self._prev_mapped = None
        self._in_trade = False
        self._dir = 0
        self._entry = 0
        self._pt = 0
        self._sl = 0
        self._bars = 0
        self._entry_time = None

        self._eq = []
        self._led = None
        self._trades = []
        self._bar_log = []  # Log first 50 bars for debugging

        self.set_warm_up(timedelta(days=7))

    def on_data(self, data):
        if self.is_warming_up: return

        mapped = self.es.mapped
        if mapped is None: return

        # Roll
        if self._prev_mapped and self._prev_mapped != mapped:
            if self.portfolio[self._prev_mapped].invested:
                q = self.portfolio[self._prev_mapped].quantity
                self.liquidate(self._prev_mapped, tag="Roll")
                self.market_order(mapped, q, tag="Roll")
                self._in_trade = False  # Reset trade tracking
        self._prev_mapped = mapped

        # Equity
        eq = self.portfolio.total_portfolio_value
        t = self.time.strftime("%Y%m%d_%H%M")
        day = self.time.strftime("%Y%m%d")
        if day != self._led:
            self._eq.append(f"{day}:{eq:.0f}")
            self._led = day

        # Flatten at 15:00
        if self.time.hour >= 15:
            if self._in_trade and self.portfolio[mapped].invested:
                self.liquidate(mapped, tag="EOD")
                self._in_trade = False
            return

        # Only trade 10:00 - 14:00
        if self.time.hour < 10 or self.time.hour >= 14:
            return

        price = float(self.securities[mapped].price)
        if price <= 0: return

        # Get history for RSI and ATR
        try:
            h = self.history(mapped, 20, Resolution.HOUR)
            if h.empty or len(h) < 14: return
            closes = h["close"].values
            highs = h["high"].values
            lows = h["low"].values
        except: return

        # RSI(3)
        d = np.diff(closes)
        g = np.where(d > 0, d, 0); l = np.where(d < 0, -d, 0)
        ag = np.mean(g[-3:]); al = np.mean(l[-3:])
        rsi = 100 - (100/(1+ag/al)) if al > 0 else 100

        # ATR(14)
        pc = np.roll(closes,1); pc[0]=closes[0]
        tr = np.maximum(highs-lows, np.maximum(np.abs(highs-pc), np.abs(lows-pc)))
        atr = float(np.mean(tr[-14:]))
        if atr <= 0: return

        # Log first 50 bars
        if len(self._bar_log) < 50:
            self._bar_log.append(f"{t}|{price:.2f}|RSI={rsi:.1f}|ATR={atr:.2f}")

        # Manage trade
        if self._in_trade:
            self._bars -= 1
            hit = False; won = False
            if self._dir == 1:
                if price <= self._sl: hit=True; won=False
                elif price >= self._pt: hit=True; won=True
            else:
                if price >= self._sl: hit=True; won=False
                elif price <= self._pt: hit=True; won=True
            if self._bars <= 0:
                hit = True
                won = (price - self._entry) * self._dir > 0
            if hit:
                self.liquidate(mapped, tag=f"{'W' if won else 'L'}")
                pnl = (price - self._entry) * self._dir * 50  # ES multiplier
                self._trades.append(
                    f"{self._entry_time}→{t}|{'L' if self._dir==1 else 'S'}|"
                    f"entry={self._entry:.2f}|exit={price:.2f}|"
                    f"pnl_pts={(price-self._entry)*self._dir:.2f}|pnl$={pnl:.0f}|{'W' if won else 'L'}"
                )
                self._in_trade = False
            return

        # New signal
        sig = 0
        if rsi < 25: sig = 1
        elif rsi > 75: sig = -1
        if sig == 0: return

        # Enter 1 contract
        self.market_order(mapped, sig, tag=f"{'BUY' if sig==1 else 'SHORT'} RSI={rsi:.0f}")
        if sig == 1:
            self._pt = price + 1.5 * atr
            self._sl = price - 1.0 * atr
        else:
            self._pt = price - 1.5 * atr
            self._sl = price + 1.0 * atr
        self._dir = sig
        self._entry = price
        self._bars = 4
        self._in_trade = True
        self._entry_time = t

    def on_end_of_algorithm(self):
        # Equity
        bs = 40
        for i in range(0, len(self._eq), bs):
            self.set_runtime_statistic(f"eq_{i//bs:03d}", "|".join(self._eq[i:i+bs]))
        self.set_runtime_statistic("eq_count", str((len(self._eq)+bs-1)//bs))

        # Trades
        for i, tr in enumerate(self._trades[:100]):  # Cap at 100
            self.set_runtime_statistic(f"tr_{i:03d}", tr)
        self.set_runtime_statistic("tr_count", str(len(self._trades)))

        # Bar log
        for i, bl in enumerate(self._bar_log[:30]):
            self.set_runtime_statistic(f"bl_{i:03d}", bl)

        eq = self.portfolio.total_portfolio_value
        wins = sum(1 for t in self._trades if '|W' in t and t.endswith('W'))
        self.set_runtime_statistic("final_equity", f"{eq:.2f}")
        self.set_runtime_statistic("n_trades", str(len(self._trades)))
        self.set_runtime_statistic("n_wins", str(wins))
