# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class CasinoStocksFull(QCAlgorithm):
    """
    Casino Stocks Full System — Multi-Indicator, 80 Stocks, Long Only

    Indicators (each generates independent buy signals):
    1. IBS < threshold (closed near low → bounce)
    2. RSI(2) < threshold (extremely oversold → bounce)
    3. RSI(3) < threshold (oversold → bounce)
    4. Bollinger Band: close < lower band (oversold → bounce)
    5. 3-day losing streak + IBS < 0.3 (momentum exhaustion)
    6. Large down day (> 2 ATR drop) → bounce

    All signals: LONG ONLY, sell after N days.
    Position: 2% of portfolio per trade, max 20 simultaneous positions.
    """

    def initialize(self):
        self.set_start_date(2020, 1, 2)
        self.set_end_date(2024, 12, 31)
        self.set_cash(200_000)

        # 80 stocks: mega cap + large cap across sectors
        tickers = [
            # Tech
            "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "AVGO", "ORCL", "ADBE",
            "AMD", "INTC", "CRM", "PYPL", "SQ",
            # Financials
            "JPM", "BAC", "WFC", "GS", "MS", "C", "BLK", "SCHW", "AXP", "USB",
            # Healthcare
            "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY",
            # Consumer
            "WMT", "PG", "KO", "PEP", "COST", "HD", "MCD", "NKE", "SBUX", "TGT",
            # Industrials
            "CAT", "GE", "HON", "UNP", "BA", "DE", "LMT", "MMM", "FDX",
            # Energy
            "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "VLO", "PSX", "OXY", "HAL",
            # Materials
            "LIN", "APD", "SHW", "NEM", "FCX", "NUE", "DOW",
            # Communications
            "NFLX", "DIS", "CMCSA", "T", "VZ",
            # ETFs
            "SPY", "QQQ", "IWM",
        ]

        self.symbols = {}
        for t in tickers:
            try:
                s = self.add_equity(t, Resolution.DAILY).symbol
                self.symbols[t] = s
            except:
                pass

        # Holding tracker: ticker -> {days_left, entry_price, signal_type}
        self._holding = {}
        self._max_positions = 25
        self._position_pct = 0.02  # 2% per trade

        # Performance tracking
        self._trades_by_signal = {}  # signal_type -> {n, wins}
        self._yeq = {}; self._yret = {}; self._peq = None
        self._eql = []; self._led = None
        self._total_trades = 0; self._total_wins = 0

        # RSI history tracker (rolling)
        self._rsi2 = {}  # ticker -> last RSI(2) value
        self._rsi3 = {}

    def on_data(self, data):
        # Equity tracking
        eq = self.portfolio.total_portfolio_value
        y = self.time.year
        if y not in self._yeq: self._yeq[y] = eq; self._yret[y] = []
        if self._peq and self._peq > 0: self._yret[y].append((eq - self._peq) / self._peq)
        self._peq = eq
        t = self.time.strftime("%Y%m%d")
        if t != self._led: self._eql.append(f"{t}:{eq:.0f}"); self._led = t

        # Exit existing positions
        for ticker in list(self._holding.keys()):
            if not ticker.startswith("_"):
                info = self._holding[ticker]
                info["days_left"] -= 1
                if info["days_left"] <= 0:
                    sym = self.symbols.get(ticker)
                    if sym and self.portfolio[sym].invested:
                        price = self.securities[sym].price
                        won = price > info["entry_price"]
                        self.liquidate(sym, tag=f"{'W' if won else 'L'} {ticker}")

                        self._total_trades += 1
                        if won: self._total_wins += 1
                        sig = info.get("signal", "unknown")
                        if sig not in self._trades_by_signal:
                            self._trades_by_signal[sig] = {"n": 0, "w": 0}
                        self._trades_by_signal[sig]["n"] += 1
                        if won: self._trades_by_signal[sig]["w"] += 1

                    del self._holding[ticker]

        # Count current positions
        n_positions = len([k for k in self._holding if not k.startswith("_")])

        # Scan for new entries
        for ticker, sym in self.symbols.items():
            if ticker in self._holding:
                continue  # Already holding
            if n_positions >= self._max_positions:
                break  # Too many positions

            if not data.bars.contains_key(sym):
                continue

            bar = data.bars[sym]
            c = float(bar.close); h = float(bar.high)
            l = float(bar.low); o = float(bar.open)
            if c <= 0 or h <= l:
                continue

            price = c
            rng = h - l

            # Get 20-day history for indicators
            hist = self.history(sym, 25, Resolution.DAILY)
            if hist.empty or len(hist) < 20:
                continue

            closes = hist["close"].values
            highs = hist["high"].values
            lows = hist["low"].values

            # ── Compute Indicators ──

            # IBS
            ibs = (c - l) / rng

            # RSI(2) and RSI(3)
            d = np.diff(closes)
            g2 = np.mean(np.maximum(d[-2:], 0))
            l2 = np.mean(np.maximum(-d[-2:], 0))
            rsi2 = 100 - 100/(1+g2/l2) if l2 > 0 else 100

            g3 = np.mean(np.maximum(d[-3:], 0))
            l3 = np.mean(np.maximum(-d[-3:], 0))
            rsi3 = 100 - 100/(1+g3/l3) if l3 > 0 else 100

            # Bollinger position
            mid20 = np.mean(closes[-20:])
            std20 = np.std(closes[-20:])
            bb_lower = mid20 - 2 * std20
            bb_zscore = (c - mid20) / std20 if std20 > 0 else 0

            # ATR(14)
            pc = np.roll(closes, 1); pc[0] = closes[0]
            tr = np.maximum(highs - lows, np.maximum(np.abs(highs - pc), np.abs(lows - pc)))
            atr14 = float(np.mean(tr[-14:]))

            # Consecutive down days
            down_days = 0
            for j in range(1, min(6, len(closes))):
                if closes[-j] < closes[-j-1]:
                    down_days += 1
                else:
                    break

            # Today's move in ATR units
            day_move = (c - o) / atr14 if atr14 > 0 else 0

            # ── Check Signals (priority order, take first match) ──

            signal = None; hold_days = 1

            # Signal 1: IBS < 0.15 (extreme)
            if ibs < 0.15:
                signal = "IBS_extreme"; hold_days = 1

            # Signal 2: RSI(2) < 10 (extreme oversold)
            elif rsi2 < 10:
                signal = "RSI2_extreme"; hold_days = 2

            # Signal 3: IBS < 0.25 AND RSI(3) < 30 (double confirmation)
            elif ibs < 0.25 and rsi3 < 30:
                signal = "IBS_RSI3"; hold_days = 2

            # Signal 4: Bollinger < -2 AND RSI(3) < 35
            elif bb_zscore < -2 and rsi3 < 35:
                signal = "BB_RSI3"; hold_days = 3

            # Signal 5: 3+ down days AND IBS < 0.30
            elif down_days >= 3 and ibs < 0.30:
                signal = "DownStreak_IBS"; hold_days = 2

            # Signal 6: Large down day (> 2 ATR) → bounce
            elif day_move < -2.0:
                signal = "LargeDown"; hold_days = 1

            if signal is None:
                continue

            # Enter position
            qty = int(eq * self._position_pct / price)
            if qty < 1:
                continue

            self.market_order(sym, qty, tag=f"B {ticker} {signal}")
            self._holding[ticker] = {
                "days_left": hold_days, "entry_price": price, "signal": signal
            }
            n_positions += 1

    def on_end_of_algorithm(self):
        # Yearly stats
        for y in sorted(self._yeq.keys()):
            r = self._yret.get(y, []); se = self._yeq[y]
            if r:
                a = np.array(r); s = float(np.std(a, ddof=1)) if len(a) > 1 else 0
                sh = (float(np.mean(a)) / s * np.sqrt(252)) if s > 0 else 0
                cu = np.cumprod(1 + a); ee = se * cu[-1]
                rp = (ee / se - 1) * 100
                dd = float(np.min(cu / np.maximum.accumulate(cu) - 1) * 100)
            else: sh = rp = dd = 0; ee = se
            self.set_runtime_statistic(f"y_{y}", f"{sh:.3f}|{rp:.1f}|{dd:.1f}|{ee:.0f}")

        # Signal performance
        for sig, counts in self._trades_by_signal.items():
            wr = counts["w"] / counts["n"] * 100 if counts["n"] > 0 else 0
            self.set_runtime_statistic(f"sig_{sig}", f"{counts['n']}|{counts['w']}|{wr:.1f}")

        # Summary
        wr = self._total_wins / self._total_trades * 100 if self._total_trades > 0 else 0
        self.set_runtime_statistic("total_trades", str(self._total_trades))
        self.set_runtime_statistic("total_wins", str(self._total_wins))
        self.set_runtime_statistic("win_rate", f"{wr:.1f}")

        # Equity curve
        if self._eql:
            bs = 25; nb = 0
            for i in range(0, len(self._eql), bs):
                self.set_runtime_statistic(f"eq_{nb:03d}", "|".join(self._eql[i:i + bs]))
                nb += 1
            self.set_runtime_statistic("eq_count", str(nb))
