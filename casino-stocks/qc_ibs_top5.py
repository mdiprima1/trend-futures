# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class IBS_Top5_Stocks(QCAlgorithm):
    """
    Casino Stocks — IBS Mean Reversion on Top 5 Stocks

    Stocks: NUE, C, MS, CVX, WFC (financials + energy)
    Signal: IBS < 0.10 → buy, IBS > 0.90 → short
    Barrier: PT=1.0x ATR, SL=1.0x ATR, max 3 days
    Position: 10% of portfolio per trade, max 1 position per stock
    """

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(100_000)

        # Expanded: 20 stocks across financials, energy, materials, industrials
        self.tickers = [
            "NUE", "C", "MS", "CVX", "WFC",  # Top 5 from sweep
            "JPM", "BAC", "GS", "XOM", "COP",  # More financials + energy
            "FCX", "DOW", "HAL", "SLB", "MPC",  # Materials + energy
            "CAT", "DE", "GE", "SCHW", "AXP",  # Industrials + financials
        ]
        self.symbols = {}
        for t in self.tickers:
            s = self.add_equity(t, Resolution.DAILY).symbol
            self.symbols[t] = s

        self._active = {}  # ticker -> {dir, entry, pt, sl, bars, qty}
        self._eq = []
        self._led = None
        self._trades = {}  # year -> {n, w}
        self._yeq = {}; self._yret = {}; self._peq = None

        self._debug_count = 0
        self.set_warm_up(20, Resolution.DAILY)

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Record equity
        eq = self.portfolio.total_portfolio_value
        y = self.time.year
        if y not in self._yeq:
            self._yeq[y] = eq; self._yret[y] = []
            self._trades[y] = {"n": 0, "w": 0}
        if self._peq and self._peq > 0:
            self._yret[y].append((eq - self._peq) / self._peq)
        self._peq = eq
        t = self.time.strftime("%Y%m%d")
        if t != self._led:
            self._eq.append(f"{t}:{eq:.0f}")
            self._led = t

        for ticker in self.tickers:
            sym = self.symbols[ticker]
            if not data.contains_key(sym):
                continue

            bar = data[sym]
            price = float(bar.close)
            high = float(bar.high)
            low = float(bar.low)
            if price <= 0:
                continue

            # Get history for ATR
            h = self.history(sym, 20, Resolution.DAILY)
            if h.empty or len(h) < 14:
                continue

            closes = h["close"].values
            highs = h["high"].values
            lows = h["low"].values

            # ATR(14)
            pc = np.roll(closes, 1); pc[0] = closes[0]
            tr = np.maximum(highs - lows,
                            np.maximum(np.abs(highs - pc), np.abs(lows - pc)))
            atr_val = float(np.mean(tr[-14:]))
            if atr_val <= 0:
                continue

            # Manage active trade
            if ticker in self._active:
                bet = self._active[ticker]
                bet["bars"] -= 1
                hit = False; won = False

                if bet["dir"] == 1:
                    if low <= bet["sl"]: hit = True; won = False
                    elif high >= bet["pt"]: hit = True; won = True
                else:
                    if high >= bet["sl"]: hit = True; won = False
                    elif low <= bet["pt"]: hit = True; won = True

                if bet["bars"] <= 0 and not hit:
                    hit = True
                    won = (price - bet["entry"]) * bet["dir"] > 0

                if hit:
                    self.liquidate(sym, tag=f"{'W' if won else 'L'} {ticker}")
                    if won:
                        self._trades[y]["w"] += 1
                    del self._active[ticker]
                    # Fall through to check re-entry
                else:
                    continue

            if ticker in self._active:
                continue

            # IBS signal from history (last completed bar)
            # history() returns bars BEFORE current time
            h_high = highs[-1]; h_low = lows[-1]; h_close = closes[-1]
            h_rng = h_high - h_low
            if h_rng <= 0:
                continue
            ibs_val = (h_close - h_low) / h_rng

            # Also check RSI for confirmation
            d = np.diff(closes)
            g = np.where(d > 0, d, 0); l = np.where(d < 0, -d, 0)
            ag = np.mean(g[-3:]); al = np.mean(l[-3:])
            rsi_val = 100 - (100/(1+ag/al)) if al > 0 else 100

            # LONG only (no shorting stocks)
            sig = 0
            if ibs_val < 0.25:
                sig = 1

            # Debug first 30 signal checks
            if self._debug_count < 30 and ticker == "NUE":
                self.set_runtime_statistic(f"dbg_{self._debug_count:03d}",
                    f"{t}|{ticker}|IBS={ibs_val:.3f}|price={price:.2f}|sig={sig}|active={'Y' if ticker in self._active else 'N'}")
                self._debug_count += 1

            if sig == 0:
                continue

            # Position size: 5% of portfolio (20 stocks × 5% = 100% max)
            qty = int(eq * 0.05 / price)
            if qty < 1:
                continue

            # Set barriers: 1:1 ATR, 3-day max
            if sig == 1:
                pt = price + 1.0 * atr_val
                sl = price - 1.0 * atr_val
            else:
                pt = price - 1.0 * atr_val
                sl = price + 1.0 * atr_val

            self.market_order(sym, sig * qty, tag=f"{'B' if sig==1 else 'S'} {ticker} x{qty}")
            self._active[ticker] = {
                "dir": sig, "entry": price,
                "pt": pt, "sl": sl, "bars": 3, "qty": qty,
            }
            self._trades[y]["n"] += 1

    def on_end_of_algorithm(self):
        for y in sorted(self._yeq.keys()):
            r = self._yret.get(y, []); se = self._yeq[y]
            tr = self._trades.get(y, {"n": 0, "w": 0})
            if r:
                a = np.array(r)
                s = float(np.std(a, ddof=1)) if len(a) > 1 else 0
                sh = (float(np.mean(a)) / s * np.sqrt(252)) if s > 0 else 0
                cu = np.cumprod(1 + a); ee = se * cu[-1]
                rp = (ee / se - 1) * 100
                dd = float(np.min(cu / np.maximum.accumulate(cu) - 1) * 100)
            else:
                sh = rp = dd = 0; ee = se
            self.set_runtime_statistic(
                f"y_{y}",
                f"{sh:.3f}|{rp:.1f}|{dd:.1f}|{ee:.0f}|{tr['n']}|{tr['w']}"
            )

        if self._eq:
            bs = 25; nb = 0
            for i in range(0, len(self._eq), bs):
                self.set_runtime_statistic(f"eq_{nb:03d}", "|".join(self._eq[i:i + bs]))
                nb += 1
            self.set_runtime_statistic("eq_count", str(nb))

        eq = self.portfolio.total_portfolio_value
        self.set_runtime_statistic("final_equity", f"{eq:.2f}")
