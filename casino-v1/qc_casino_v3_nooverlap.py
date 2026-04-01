# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class CasinoV3NoOverlap(QCAlgorithm):
    """
    Casino V3 — 1 strategy per instrument, NO position overlap.

    ES: RSI(3) 30/70, PT=3.0x ATR, SL=0.75x ATR, 6-bar limit
    NQ: RSI(3) 30/70, PT=3.0x ATR, SL=0.75x ATR, 6-bar limit
    CL: IBS(0.15/0.85), PT=3.0x ATR, SL=0.75x ATR, 6-bar limit

    Each instrument has exactly 1 bet at a time. No stacking.
    """

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(1_000_000)

        self.instruments = {}
        for key, fut in [
            ("ES", Futures.Indices.SP_500_E_MINI),
            ("NQ", Futures.Indices.NASDAQ_100_E_MINI),
            ("CL", Futures.Energies.CRUDE_OIL_WTI),
        ]:
            f = self.add_future(fut, resolution=Resolution.HOUR,
                data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
                data_mapping_mode=DataMappingMode.OPEN_INTEREST, contract_depth_offset=0)
            f.set_filter(0, 90)
            self.instruments[f.symbol] = key

        # Bet state per instrument
        self._active = {}  # key -> {dir, entry, pt, sl, bars}
        self._prev = {}

        # Stats
        self._yeq = {}; self._yret = {}; self._peq = None
        self._eql = []; self._led = None
        self._trades = {}  # year -> {n, w}
        self.set_warm_up(timedelta(days=14))

    def on_data(self, data):
        if self.is_warming_up: return

        # Rolls
        for cs in self.instruments:
            key = self.instruments[cs]
            mapped = self.securities[cs].mapped
            if mapped is None: continue
            prev = self._prev.get(key)
            if prev and prev != mapped and self.portfolio[prev].invested:
                q = self.portfolio[prev].quantity
                self.liquidate(prev, tag=f"Roll {key}")
                self.market_order(mapped, q, tag=f"Roll {key}")
                self._active.pop(key, None)
            self._prev[key] = mapped

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
        if t != self._led: self._eql.append(f"{t}:{eq:.0f}"); self._led = t

        # Only process bars 10:00-13:00 — ignore everything else
        if self.time.hour < 10 or self.time.hour > 13:
            # Flatten active positions at 14:00+
            if self.time.hour >= 14:
                for key in list(self._active.keys()):
                    mapped = self._get_mapped(key)
                    if mapped and self.portfolio[mapped].invested:
                        self.liquidate(mapped, tag=f"EOD {key}")
                    self._active.pop(key, None)
            return

        # Process each instrument (10:00-13:00 only)
        for cs in self.instruments:
            key = self.instruments[cs]
            mapped = self.securities[cs].mapped
            if mapped is None: continue

            price = float(self.securities[mapped].price)
            if price <= 0: continue

            # Get history
            try:
                h = self.history(mapped, 20, Resolution.HOUR)
                if h.empty or len(h) < 14: continue
                closes = h["close"].values
                highs = h["high"].values
                lows = h["low"].values
            except: continue

            # ATR
            pc = np.roll(closes, 1); pc[0] = closes[0]
            tr = np.maximum(highs-lows, np.maximum(np.abs(highs-pc), np.abs(lows-pc)))
            atr = float(np.mean(tr[-14:]))
            if atr <= 0: continue

            # Manage active bet
            if key in self._active:
                bet = self._active[key]
                bet["bars"] -= 1
                hit = False; won = False

                if bet["dir"] == 1:
                    if price <= bet["sl"]: hit=True; won=False
                    elif price >= bet["pt"]: hit=True; won=True
                else:
                    if price >= bet["sl"]: hit=True; won=False
                    elif price <= bet["pt"]: hit=True; won=True
                if bet["bars"] <= 0:
                    hit = True; won = (price - bet["entry"]) * bet["dir"] > 0

                if hit:
                    if self.portfolio[mapped].invested:
                        self.liquidate(mapped, tag=f"{'W' if won else 'L'} {key}")
                    if won: self._trades[y]["w"] += 1
                    del self._active[key]
                    # Fall through to check for re-entry
                else:
                    continue  # Still in trade

            # Signal (only if not in active trade for this instrument)
            if key in self._active:
                continue

            sig = self._get_signal(key, closes, highs, lows, price)
            if sig == 0: continue

            # Enter
            pt_mult = 3.0; sl_mult = 0.75
            if sig == 1:
                pt = price + pt_mult * atr
                sl = price - sl_mult * atr
            else:
                pt = price - pt_mult * atr
                sl = price + sl_mult * atr

            self.market_order(mapped, sig, tag=f"ENTRY {key}")
            self._active[key] = {"dir": sig, "entry": price, "pt": pt, "sl": sl, "bars": 6}
            self._trades[y]["n"] += 1

    def _get_signal(self, key, closes, highs, lows, price):
        if key in ("ES", "NQ"):
            # RSI(3) 25/75 — tighter than 30/70 to reduce over-trading
            d = np.diff(closes)
            g = np.where(d > 0, d, 0); l = np.where(d < 0, -d, 0)
            ag = np.mean(g[-3:]); al = np.mean(l[-3:])
            rsi = 100 - (100/(1+ag/al)) if al > 0 else 100
            if rsi < 25: return 1
            if rsi > 75: return -1
        elif key == "CL":
            # IBS(0.10/0.90) — tighter to reduce over-trading
            rng = highs[-1] - lows[-1]
            if rng > 0:
                ibs = (closes[-1] - lows[-1]) / rng
                if ibs < 0.10: return 1
                if ibs > 0.90: return -1
        return 0

    def _get_mapped(self, key):
        for cs in self.instruments:
            if self.instruments[cs] == key:
                return self.securities[cs].mapped
        return None

    def on_end_of_algorithm(self):
        for y in sorted(self._yeq.keys()):
            r = self._yret.get(y, []); se = self._yeq[y]
            tr = self._trades.get(y, {"n":0,"w":0})
            if r:
                a = np.array(r); s = float(np.std(a,ddof=1)) if len(a)>1 else 0
                sh = (float(np.mean(a))/s*np.sqrt(252)) if s>0 else 0
                cu = np.cumprod(1+a); ee = se*cu[-1]; rp=(ee/se-1)*100
                dd = float(np.min(cu/np.maximum.accumulate(cu)-1)*100)
            else: sh=rp=dd=0; ee=se
            self.set_runtime_statistic(f"y_{y}",f"{sh:.3f}|{rp:.1f}|{dd:.1f}|{ee:.0f}|{tr['n']}|{tr['w']}")
        if self._eql:
            bs=25;nb=0
            for i in range(0,len(self._eql),bs):
                self.set_runtime_statistic(f"eq_{nb:03d}","|".join(self._eql[i:i+bs]));nb+=1
            self.set_runtime_statistic("eq_count",str(nb))

    def on_securities_changed(self, c):
        for s in c.added_securities:
            if s.symbol.security_type != SecurityType.BASE:
                s.set_fee_model(InteractiveBrokersFeeModel())
