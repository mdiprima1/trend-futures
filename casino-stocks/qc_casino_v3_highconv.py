# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class CasinoStocksV3(QCAlgorithm):
    """
    Casino Stocks V3 — High Conviction Only

    Only signals with >48% win rate from V2:
    1. IBS < 0.20 AND RSI(3) < 30 → 54.9% WR (BEST)
    2. RSI(14) < 25 AND RSI(3) < 40 → 54.0% WR
    3. SMA deviation > 1.5 ATR below AND RSI(3) < 35 → 50.4% WR
    4. Bollinger < -2σ AND RSI(3) < 35 → 48.2% WR

    REMOVED: RSI(2) ultra/extreme (29-31% WR), GapDown (0% WR)

    80 stocks, long only, 2.5% position, max 30 positions
    """

    def initialize(self):
        self.set_start_date(2020, 1, 2)
        self.set_end_date(2024, 12, 31)
        self.set_cash(200_000)

        tickers = [
            "AAPL","MSFT","AMZN","GOOGL","META","NVDA","TSLA","AVGO","ORCL","ADBE",
            "AMD","INTC","CRM","PYPL","SQ",
            "JPM","BAC","WFC","GS","MS","C","BLK","SCHW","AXP","USB",
            "UNH","JNJ","LLY","PFE","ABBV","MRK","TMO","ABT","DHR","BMY",
            "WMT","PG","KO","PEP","COST","HD","MCD","NKE","SBUX","TGT",
            "CAT","GE","HON","UNP","BA","DE","LMT","MMM","FDX",
            "XOM","CVX","COP","SLB","EOG","MPC","VLO","PSX","OXY","HAL",
            "LIN","APD","SHW","NEM","FCX","NUE","DOW",
            "NFLX","DIS","CMCSA","T","VZ",
            "SPY","QQQ","IWM",
        ]

        self.symbols = {}
        for t in tickers:
            try: self.symbols[t] = self.add_equity(t, Resolution.DAILY).symbol
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
            if ticker in self._holding or n_pos >= self._max_positions: continue
            if not data.bars.contains_key(sym): continue

            bar = data.bars[sym]
            c = float(bar.close); h = float(bar.high); l = float(bar.low); o = float(bar.open)
            if c <= 0 or h <= l: continue

            hist = self.history(sym, 25, Resolution.DAILY)
            if hist.empty or len(hist) < 20: continue
            closes = hist["close"].values
            highs = hist["high"].values
            lows = hist["low"].values

            # Indicators
            ibs = (c - l) / (h - l)
            d = np.diff(closes)

            g3 = np.mean(np.maximum(d[-3:], 0)); l3 = np.mean(np.maximum(-d[-3:], 0))
            rsi3 = 100 - 100/(1+g3/l3) if l3 > 0 else 100

            if len(d) >= 14:
                g14 = np.mean(np.maximum(d[-14:], 0)); l14 = np.mean(np.maximum(-d[-14:], 0))
                rsi14 = 100 - 100/(1+g14/l14) if l14 > 0 else 100
            else: rsi14 = 50

            mid20 = np.mean(closes[-20:]); std20 = np.std(closes[-20:])
            bb_z = (c - mid20) / std20 if std20 > 0 else 0

            pc = np.roll(closes, 1); pc[0] = closes[0]
            tr = np.maximum(highs-lows, np.maximum(np.abs(highs-pc), np.abs(lows-pc)))
            atr14 = float(np.mean(tr[-14:])) if len(tr) >= 14 else 0
            sma_dev = (c - mid20) / atr14 if atr14 > 0 else 0

            # ── HIGH CONVICTION SIGNALS ONLY (>48% WR from V2) ──
            signal = None; hold = 1

            # 1. IBS + RSI(3) — 54.9% WR
            if ibs < 0.20 and rsi3 < 30:
                signal = "IBS_RSI3"; hold = 2

            # 2. RSI(14) weekly oversold — 54.0% WR
            elif rsi14 < 25 and rsi3 < 40:
                signal = "RSI14_weekly"; hold = 3

            # 3. SMA deviation — 50.4% WR
            elif sma_dev < -1.5 and rsi3 < 35:
                signal = "SMA_dev"; hold = 2

            # 4. Bollinger + RSI — 48.2% WR
            elif bb_z < -2 and rsi3 < 35:
                signal = "BB_RSI3"; hold = 2

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
