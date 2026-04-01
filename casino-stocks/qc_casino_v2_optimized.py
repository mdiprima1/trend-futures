# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class CasinoStocksV2(QCAlgorithm):
    """
    Casino Stocks V2 — Optimized

    Changes from V1:
    - REMOVED IBS_extreme (34.7% WR — dragged results)
    - REMOVED LargeDown (too rare)
    - KEPT RSI(2) extreme (51.8% WR — the workhorse)
    - KEPT IBS+RSI3 confirmation (49.8% WR)
    - KEPT BB+RSI3 (48.6% WR)
    - ADDED: RSI(2) < 5 with 1-day hold (ultra-extreme)
    - ADDED: Price < SMA(20) by > 1.5 ATR AND RSI(3) < 35
    - ADDED: Gap down > 1.5% from prev close (gap fill)
    - ADDED: 5-day RSI(14) < 25 (weekly oversold)
    - TUNED: RSI(2) hold from 2 days to 1 day
    - TUNED: max positions 30 (from 25)
    - TUNED: position size 2.5% (from 2%)
    - 80 stocks, long only
    """

    def initialize(self):
        self.set_start_date(2020, 1, 2)
        self.set_end_date(2024, 12, 31)
        self.set_cash(200_000)

        tickers = [
            # Tech
            "AAPL","MSFT","AMZN","GOOGL","META","NVDA","TSLA","AVGO","ORCL","ADBE",
            "AMD","INTC","CRM","PYPL","SQ",
            # Financials
            "JPM","BAC","WFC","GS","MS","C","BLK","SCHW","AXP","USB",
            # Healthcare
            "UNH","JNJ","LLY","PFE","ABBV","MRK","TMO","ABT","DHR","BMY",
            # Consumer
            "WMT","PG","KO","PEP","COST","HD","MCD","NKE","SBUX","TGT",
            # Industrials
            "CAT","GE","HON","UNP","BA","DE","LMT","MMM","FDX",
            # Energy
            "XOM","CVX","COP","SLB","EOG","MPC","VLO","PSX","OXY","HAL",
            # Materials
            "LIN","APD","SHW","NEM","FCX","NUE","DOW",
            # Communications
            "NFLX","DIS","CMCSA","T","VZ",
            # ETFs
            "SPY","QQQ","IWM",
        ]

        self.symbols = {}
        for t in tickers:
            try:
                self.symbols[t] = self.add_equity(t, Resolution.DAILY).symbol
            except: pass

        self._holding = {}
        self._max_positions = 30
        self._position_pct = 0.025

        self._sig_stats = {}
        self._yeq = {}; self._yret = {}; self._peq = None
        self._eql = []; self._led = None
        self._total_trades = 0; self._total_wins = 0

    def on_data(self, data):
        eq = self.portfolio.total_portfolio_value
        y = self.time.year
        if y not in self._yeq: self._yeq[y] = eq; self._yret[y] = []
        if self._peq and self._peq > 0: self._yret[y].append((eq - self._peq) / self._peq)
        self._peq = eq
        t = self.time.strftime("%Y%m%d")
        if t != self._led: self._eql.append(f"{t}:{eq:.0f}"); self._led = t

        # Exit
        for ticker in list(self._holding.keys()):
            info = self._holding[ticker]
            info["days_left"] -= 1
            if info["days_left"] <= 0:
                sym = self.symbols.get(ticker)
                if sym and self.portfolio[sym].invested:
                    price = self.securities[sym].price
                    won = price > info["entry_price"]
                    self.liquidate(sym, tag=f"{'W' if won else 'L'}")
                    self._total_trades += 1
                    if won: self._total_wins += 1
                    sig = info["signal"]
                    if sig not in self._sig_stats: self._sig_stats[sig] = {"n":0,"w":0}
                    self._sig_stats[sig]["n"] += 1
                    if won: self._sig_stats[sig]["w"] += 1
                del self._holding[ticker]

        n_pos = len(self._holding)

        for ticker, sym in self.symbols.items():
            if ticker in self._holding or n_pos >= self._max_positions:
                continue
            if not data.bars.contains_key(sym):
                continue

            bar = data.bars[sym]
            c = float(bar.close); h = float(bar.high)
            l = float(bar.low); o = float(bar.open)
            if c <= 0 or h <= l: continue

            hist = self.history(sym, 25, Resolution.DAILY)
            if hist.empty or len(hist) < 20: continue
            closes = hist["close"].values
            highs = hist["high"].values
            lows = hist["low"].values

            # ── Indicators ──
            ibs = (c - l) / (h - l)

            d = np.diff(closes)
            # RSI(2)
            g2 = np.mean(np.maximum(d[-2:], 0))
            l2 = np.mean(np.maximum(-d[-2:], 0))
            rsi2 = 100 - 100/(1+g2/l2) if l2 > 0 else 100

            # RSI(3)
            g3 = np.mean(np.maximum(d[-3:], 0))
            l3 = np.mean(np.maximum(-d[-3:], 0))
            rsi3 = 100 - 100/(1+g3/l3) if l3 > 0 else 100

            # RSI(14) for weekly oversold
            if len(d) >= 14:
                g14 = np.mean(np.maximum(d[-14:], 0))
                l14 = np.mean(np.maximum(-d[-14:], 0))
                rsi14 = 100 - 100/(1+g14/l14) if l14 > 0 else 100
            else:
                rsi14 = 50

            # Bollinger
            mid20 = np.mean(closes[-20:]); std20 = np.std(closes[-20:])
            bb_z = (c - mid20) / std20 if std20 > 0 else 0

            # SMA(20) deviation in ATR units
            pc = np.roll(closes, 1); pc[0] = closes[0]
            tr = np.maximum(highs-lows, np.maximum(np.abs(highs-pc), np.abs(lows-pc)))
            atr14 = float(np.mean(tr[-14:])) if len(tr) >= 14 else 0
            sma20_dev = (c - mid20) / atr14 if atr14 > 0 else 0

            # Gap from previous close
            prev_close = closes[-1]
            gap_pct = (o - prev_close) / prev_close * 100 if prev_close > 0 else 0

            # ── Signals (priority order) ──
            signal = None; hold = 1

            # 1. RSI(2) ultra-extreme (<5) — highest conviction
            if rsi2 < 5:
                signal = "RSI2_ultra"; hold = 1

            # 2. RSI(2) < 10 — the proven workhorse
            elif rsi2 < 10:
                signal = "RSI2_10"; hold = 1

            # 3. IBS < 0.20 AND RSI(3) < 30 — double confirmation
            elif ibs < 0.20 and rsi3 < 30:
                signal = "IBS_RSI3"; hold = 2

            # 4. Bollinger < -2σ AND RSI(3) < 35
            elif bb_z < -2 and rsi3 < 35:
                signal = "BB_RSI3"; hold = 2

            # 5. Price > 1.5 ATR below SMA(20) AND RSI(3) < 35
            elif sma20_dev < -1.5 and rsi3 < 35:
                signal = "SMA_dev"; hold = 2

            # 6. Gap down > 1.5% AND IBS < 0.30
            elif gap_pct < -1.5 and ibs < 0.30:
                signal = "GapDown"; hold = 1

            # 7. RSI(14) < 25 (weekly oversold)
            elif rsi14 < 25 and rsi3 < 40:
                signal = "RSI14_weekly"; hold = 3

            if signal is None: continue

            qty = int(eq * self._position_pct / c)
            if qty < 1: continue

            self.market_order(sym, qty, tag=f"B {ticker} {signal}")
            self._holding[ticker] = {"days_left": hold, "entry_price": c, "signal": signal}
            n_pos += 1

    def on_end_of_algorithm(self):
        for y in sorted(self._yeq.keys()):
            r = self._yret.get(y, []); se = self._yeq[y]
            if r:
                a = np.array(r); s = float(np.std(a,ddof=1)) if len(a)>1 else 0
                sh = (float(np.mean(a))/s*np.sqrt(252)) if s>0 else 0
                cu = np.cumprod(1+a); ee = se*cu[-1]; rp=(ee/se-1)*100
                dd = float(np.min(cu/np.maximum.accumulate(cu)-1)*100)
            else: sh=rp=dd=0; ee=se
            self.set_runtime_statistic(f"y_{y}",f"{sh:.3f}|{rp:.1f}|{dd:.1f}|{ee:.0f}")

        for sig, c in self._sig_stats.items():
            wr = c["w"]/c["n"]*100 if c["n"]>0 else 0
            self.set_runtime_statistic(f"sig_{sig}",f'{c["n"]}|{c["w"]}|{wr:.1f}')

        wr = self._total_wins/self._total_trades*100 if self._total_trades>0 else 0
        self.set_runtime_statistic("total_trades", str(self._total_trades))
        self.set_runtime_statistic("total_wins", str(self._total_wins))
        self.set_runtime_statistic("win_rate", f"{wr:.1f}")

        if self._eql:
            bs=25;nb=0
            for i in range(0,len(self._eql),bs):
                self.set_runtime_statistic(f"eq_{nb:03d}","|".join(self._eql[i:i+bs]));nb+=1
            self.set_runtime_statistic("eq_count",str(nb))
