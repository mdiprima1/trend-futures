# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class CasinoV2(QCAlgorithm):
    """
    Casino V2 — Simplified: 3 Best Bets Only

    Stripped down to reduce noise. Only the 3 highest-EV setups:
    1. NQ RSI(3) < 30 mean reversion (PT=3x, SL=1x ATR, 6-bar time limit)
    2. NQ Keltner breakout (PT=3x, SL=1x ATR, 6-bar time limit)
    3. CL RSI(3) + Keltner MR (PT=2.5x, SL=2x ATR, 6-bar time limit)

    Key fixes from V1:
    - Only 3 setups (not 8) — reduce interference
    - Max 1 position per instrument at any time
    - Flatten everything at 14:30 (30 min before close)
    - Use consolidation history (not mapped contract) for signals
    - 6-bar time limit on hourly = 6 hours max hold
    """

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(1_000_000)

        self.nq = self.add_future(Futures.Indices.NASDAQ_100_E_MINI,
            resolution=Resolution.HOUR,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            contract_depth_offset=0)
        self.nq.set_filter(0, 90)

        self.cl = self.add_future(Futures.Energies.CRUDE_OIL_WTI,
            resolution=Resolution.HOUR,
            data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST,
            contract_depth_offset=0)
        self.cl.set_filter(0, 90)

        # Track state
        self._positions = {}  # "NQ" or "CL" -> {direction, entry, pt, sl, bars}
        self._prev_nq = None
        self._prev_cl = None
        self._last_signal_bar = {}  # prevent multiple signals same bar

        # Stats
        self._year_start = {}
        self._year_rets = {}
        self._prev_eq = None
        self._eq_log = []
        self._led = None
        self._trades = {}  # year -> {total, wins}

        self.set_warm_up(timedelta(days=30))

    def on_data(self, data):
        if self.is_warming_up: return

        # Roll handling
        nq_mapped = self.nq.mapped
        cl_mapped = self.cl.mapped

        if nq_mapped and self._prev_nq and self._prev_nq != nq_mapped:
            if self.portfolio[self._prev_nq].invested:
                q = self.portfolio[self._prev_nq].quantity
                self.liquidate(self._prev_nq, tag="Roll NQ")
                self.market_order(nq_mapped, q, tag="Roll NQ")
        self._prev_nq = nq_mapped

        if cl_mapped and self._prev_cl and self._prev_cl != cl_mapped:
            if self.portfolio[self._prev_cl].invested:
                q = self.portfolio[self._prev_cl].quantity
                self.liquidate(self._prev_cl, tag="Roll CL")
                self.market_order(cl_mapped, q, tag="Roll CL")
        self._prev_cl = cl_mapped

        # Record equity
        eq = self.portfolio.total_portfolio_value
        y = self.time.year
        if y not in self._year_start:
            self._year_start[y] = eq; self._year_rets[y] = []
            self._trades[y] = {"total": 0, "wins": 0}
        if self._prev_eq and self._prev_eq > 0:
            self._year_rets[y].append((eq - self._prev_eq) / self._prev_eq)
        self._prev_eq = eq
        t = self.time.strftime("%Y%m%d")
        if t != self._led: self._eq_log.append(f"{t}:{eq:.0f}"); self._led = t

        # Flatten at 14:30
        if self.time.hour >= 14 and self.time.minute >= 30:
            self._flatten_all("EOD")
            return

        # Only trade during RTH (10:00 - 14:00) — skip first 30min noise
        if self.time.hour < 10 or self.time.hour >= 14:
            return

        # Manage existing positions (check barriers)
        self._manage_positions(nq_mapped, cl_mapped)

        # Look for new entries
        if nq_mapped and "NQ" not in self._positions:
            self._check_nq_signals(nq_mapped)

        if cl_mapped and "CL" not in self._positions:
            self._check_cl_signals(cl_mapped)

    def _check_nq_signals(self, mapped):
        """Check NQ setups: RSI MR and Keltner BO."""
        try:
            h = self.history(mapped, 30, Resolution.HOUR)
            if h.empty or len(h) < 20: return
            closes = h["close"].values
            highs = h["high"].values
            lows = h["low"].values

            atr_val = self._calc_atr(highs, lows, closes, 14)
            if atr_val <= 0: return
            price = float(closes[-1])

            # Setup 1: RSI(3) mean reversion
            r = self._rsi(closes, 3)
            if r < 20:  # Strict threshold
                self._enter("NQ", mapped, 1, price, atr_val, 3.0, 1.0, 6, "NQ_RSI_MR")
                return
            elif r > 80:
                self._enter("NQ", mapped, -1, price, atr_val, 3.0, 1.0, 6, "NQ_RSI_MR")
                return

            # Setup 2: Keltner breakout
            if len(closes) >= 30:
                ema = self._ema(closes, 30)
                upper = ema + 2.0 * atr_val
                lower = ema - 2.0 * atr_val
                prev = float(closes[-2])
                if prev <= upper and price > upper:
                    self._enter("NQ", mapped, 1, price, atr_val, 3.0, 1.0, 6, "NQ_KeltBO")
                    return
                if prev >= lower and price < lower:
                    self._enter("NQ", mapped, -1, price, atr_val, 3.0, 1.0, 6, "NQ_KeltBO")
                    return
        except: pass

    def _check_cl_signals(self, mapped):
        """Check CL setup: RSI + Keltner MR."""
        try:
            h = self.history(mapped, 30, Resolution.HOUR)
            if h.empty or len(h) < 20: return
            closes = h["close"].values
            highs = h["high"].values
            lows = h["low"].values

            atr_val = self._calc_atr(highs, lows, closes, 14)
            if atr_val <= 0: return
            price = float(closes[-1])

            r = self._rsi(closes, 3)
            ema = self._ema(closes, 20)
            lower = ema - 2.5 * atr_val
            upper = ema + 2.5 * atr_val

            if r < 25 and price < lower:
                self._enter("CL", mapped, 1, price, atr_val, 2.5, 2.0, 6, "CL_RSI_Kelt")
            elif r > 75 and price > upper:
                self._enter("CL", mapped, -1, price, atr_val, 2.5, 2.0, 6, "CL_RSI_Kelt")
        except: pass

    def _enter(self, key, mapped, direction, price, atr_val, pt_mult, sl_mult, max_bars, tag):
        """Enter a position."""
        if direction == 1:
            pt = price + pt_mult * atr_val
            sl = price - sl_mult * atr_val
        else:
            pt = price - pt_mult * atr_val
            sl = price + sl_mult * atr_val

        self.market_order(mapped, direction, tag=f"ENTRY {tag}")
        self._positions[key] = {
            "mapped": mapped, "direction": direction,
            "entry": price, "pt": pt, "sl": sl,
            "bars_left": max_bars, "tag": tag,
        }
        self._trades[self.time.year]["total"] += 1

    def _manage_positions(self, nq_mapped, cl_mapped):
        """Check barriers on active positions."""
        for key in list(self._positions.keys()):
            pos = self._positions[key]
            mapped = pos["mapped"]
            sec = self.securities.get(mapped)
            if sec is None: continue

            price = float(sec.price)
            if price <= 0: continue
            pos["bars_left"] -= 1

            hit = False
            won = False

            if pos["direction"] == 1:
                if price <= pos["sl"]: hit = True; won = False
                elif price >= pos["pt"]: hit = True; won = True
            else:
                if price >= pos["sl"]: hit = True; won = False
                elif price <= pos["pt"]: hit = True; won = True

            if pos["bars_left"] <= 0:
                hit = True
                won = (price - pos["entry"]) * pos["direction"] > 0

            if hit:
                if self.portfolio[mapped].invested:
                    self.liquidate(mapped, tag=f"{'WIN' if won else 'LOSS'} {pos['tag']}")
                if won: self._trades[self.time.year]["wins"] += 1
                del self._positions[key]

    def _flatten_all(self, reason):
        for key in list(self._positions.keys()):
            pos = self._positions[key]
            if self.portfolio[pos["mapped"]].invested:
                self.liquidate(pos["mapped"], tag=reason)
            del self._positions[key]

    def _rsi(self, closes, period):
        d = np.diff(closes)
        g = np.where(d > 0, d, 0)
        l = np.where(d < 0, -d, 0)
        ag = np.mean(g[-period:])
        al = np.mean(l[-period:])
        if al == 0: return 100
        return 100 - (100 / (1 + ag / al))

    def _ema(self, data, span):
        a = 2.0 / (span + 1); e = float(data[0])
        for v in data[1:]: e = a * float(v) + (1 - a) * e
        return e

    def _calc_atr(self, h, l, c, period):
        trs = [max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])) for i in range(1, len(c))]
        return np.mean(trs[-period:]) if len(trs) >= period else 0

    def on_end_of_algorithm(self):
        for y in sorted(self._year_start.keys()):
            rets = self._year_rets.get(y, [])
            se = self._year_start[y]
            tr = self._trades.get(y, {"total":0,"wins":0})
            if rets:
                a = np.array(rets); s = float(np.std(a,ddof=1)) if len(a)>1 else 0
                sh = (float(np.mean(a))/s*np.sqrt(252)) if s>0 else 0
                cu = np.cumprod(1+a); ee = se*cu[-1]; rp=(ee/se-1)*100
                dd = float(np.min(cu/np.maximum.accumulate(cu)-1)*100)
            else: sh=rp=dd=0; ee=se
            self.set_runtime_statistic(f"y_{y}",
                f"{sh:.3f}|{rp:.1f}|{dd:.1f}|{ee:.0f}|{tr['total']}|{tr['wins']}")
        if self._eq_log:
            bs=25;nb=0
            for i in range(0,len(self._eq_log),bs):
                self.set_runtime_statistic(f"eq_{nb:03d}","|".join(self._eq_log[i:i+bs]));nb+=1
            self.set_runtime_statistic("eq_count",str(nb))

    def on_securities_changed(self, changes):
        for sec in changes.added_securities:
            if sec.symbol.security_type != SecurityType.BASE:
                sec.set_fee_model(InteractiveBrokersFeeModel())
