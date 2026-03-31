# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class CasinoV1(QCAlgorithm):
    """
    Casino V1 — 8 Bet Streams on ES, NQ, CL

    Each bet uses 60-min bars with ATR-based triple barrier.
    All positions close intraday (no overnight exposure).

    Bet Catalog:
    1. NQ RSI(3)+BB(2.5): PT=2.5 SL=1.0 Time=45bars
    2. NQ Keltner BO(30,2.0): PT=3.0 SL=1.0 Time=15bars
    3. CL RSI(3)+Keltner(2.5): PT=2.5 SL=2.0 Time=120bars
    4. NQ IBS(0.15/0.85): PT=3.0 SL=2.0 Time=30bars
    5. NQ RSI(3) 30/70: PT=3.0 SL=1.0 Time=90bars
    6. CL Keltner MR(14,2.5): PT=2.5 SL=2.0 Time=60bars
    7. CL IBS(0.1/0.9): PT=3.0 SL=0.75 Time=15bars
    8. ES RSI(3) 30/70: PT=3.0 SL=1.5 Time=15bars
    """

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(1_000_000)

        # Add futures
        self.contracts = {}
        for key, fut in [
            ("ES", Futures.Indices.SP_500_E_MINI),
            ("NQ", Futures.Indices.NASDAQ_100_E_MINI),
            ("CL", Futures.Energies.CRUDE_OIL_WTI),
        ]:
            f = self.add_future(fut, resolution=Resolution.HOUR,
                data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
                data_mapping_mode=DataMappingMode.OPEN_INTEREST,
                contract_depth_offset=0)
            f.set_filter(0, 90)
            self.contracts[f.symbol] = key

        # Bet definitions: (name, instrument, signal_fn_name, pt, sl, max_bars)
        self.bet_defs = [
            ("NQ_RSI_BB",     "NQ", "rsi_bb",       2.5, 1.0, 45),
            ("NQ_KeltBO",     "NQ", "kelt_bo",      3.0, 1.0, 15),
            ("CL_RSI_Kelt",   "CL", "rsi_kelt",     2.5, 2.0, 120),
            ("NQ_IBS",        "NQ", "ibs_nq",       3.0, 2.0, 30),
            ("NQ_RSI_MR",     "NQ", "rsi_mr_nq",    3.0, 1.0, 90),
            ("CL_KeltMR",     "CL", "kelt_mr_cl",   2.5, 2.0, 60),
            ("CL_IBS",        "CL", "ibs_cl",       3.0, 0.75, 15),
            ("ES_RSI_MR",     "ES", "rsi_mr_es",    3.0, 1.5, 15),
        ]

        # Active bets tracking
        self._active_bets = {}  # name -> {symbol, direction, entry_price, pt, sl, bars_left}
        self._prev_contracts = {}
        self._bars_seen = 0

        # Equity tracking
        self._year_start = {}
        self._year_rets = {}
        self._prev_eq = None
        self._eq_log = []
        self._led = None
        self._bet_count = {}  # year -> count
        self._bet_wins = {}   # year -> wins

        self.set_warm_up(timedelta(days=30))

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Handle rolls
        for cs, f in [(cs, self.securities[cs]) for cs in self.contracts]:
            key = self.contracts[cs]
            mapped = f.mapped
            if mapped is None:
                continue
            prev = self._prev_contracts.get(key)
            if prev and prev != mapped and self.portfolio[prev].invested:
                qty = self.portfolio[prev].quantity
                self.liquidate(prev, tag=f"Roll {key}")
                self.market_order(mapped, qty, tag=f"Roll {key}")
            self._prev_contracts[key] = mapped

        # Record equity
        eq = self.portfolio.total_portfolio_value
        year = self.time.year
        if year not in self._year_start:
            self._year_start[year] = eq
            self._year_rets[year] = []
            self._bet_count[year] = 0
            self._bet_wins[year] = 0
        if self._prev_eq and self._prev_eq > 0:
            self._year_rets[year].append((eq - self._prev_eq) / self._prev_eq)
        self._prev_eq = eq
        t = self.time.strftime("%Y%m%d")
        if t != self._led:
            self._eq_log.append(f"{t}:{eq:.0f}")
            self._led = t

        self._bars_seen += 1

        # Flatten at end of day (15:00 for safety margin)
        if self.time.hour >= 15:
            for name, bet in list(self._active_bets.items()):
                sym = self._get_mapped(bet["instrument"])
                if sym and self.portfolio[sym].invested:
                    self.liquidate(sym, tag=f"EOD {name}")
            self._active_bets.clear()
            return

        # Manage active bets (check barriers)
        for name, bet in list(self._active_bets.items()):
            sym = self._get_mapped(bet["instrument"])
            if sym is None:
                continue
            sec = self.securities.get(sym)
            if sec is None:
                continue

            price = float(sec.price)
            bet["bars_left"] -= 1

            hit = False
            won = False
            if bet["direction"] == 1:  # Long
                if price >= bet["pt_price"]:
                    hit = True; won = True
                elif price <= bet["sl_price"]:
                    hit = True; won = False
            else:  # Short
                if price <= bet["pt_price"]:
                    hit = True; won = True
                elif price >= bet["sl_price"]:
                    hit = True; won = False

            if bet["bars_left"] <= 0:
                hit = True
                won = (price - bet["entry_price"]) * bet["direction"] > 0

            if hit:
                if self.portfolio[sym].invested:
                    self.liquidate(sym, tag=f"{'WIN' if won else 'LOSS'} {name}")
                if won:
                    self._bet_wins[year] = self._bet_wins.get(year, 0) + 1
                del self._active_bets[name]

        # Check for new bet signals (only if not already in that bet)
        for bet_def in self.bet_defs:
            name, instrument, sig_fn, pt_mult, sl_mult, max_bars = bet_def

            if name in self._active_bets:
                continue

            sym = self._get_mapped(instrument)
            if sym is None:
                continue

            signal = self._compute_signal(sig_fn, sym)
            if signal == 0:
                continue

            # Get ATR for barrier placement
            atr_val = self._get_atr(sym)
            if atr_val is None or atr_val <= 0:
                continue

            price = float(self.securities[sym].price)
            if price <= 0:
                continue

            # Set barriers
            if signal == 1:
                pt_price = price + pt_mult * atr_val
                sl_price = price - sl_mult * atr_val
            else:
                pt_price = price - pt_mult * atr_val
                sl_price = price + sl_mult * atr_val

            # Enter position (1 contract)
            self.market_order(sym, signal, tag=f"ENTRY {name}")
            self._active_bets[name] = {
                "instrument": instrument,
                "direction": signal,
                "entry_price": price,
                "pt_price": pt_price,
                "sl_price": sl_price,
                "bars_left": max_bars,
            }
            self._bet_count[year] = self._bet_count.get(year, 0) + 1

    def _get_mapped(self, key):
        for cs in self.contracts:
            if self.contracts[cs] == key:
                mapped = self.securities[cs].mapped
                return mapped
        return None

    def _compute_signal(self, sig_fn, sym):
        try:
            h = self.history(sym, 30, Resolution.HOUR)
            if h.empty or len(h) < 20:
                return 0
            closes = h["close"].values
            highs = h["high"].values
            lows = h["low"].values
            opens = h["open"].values if "open" in h.columns else closes

            if sig_fn == "rsi_mr_nq" or sig_fn == "rsi_mr_es":
                r = self._rsi(closes, 3)
                if r < 30: return 1
                if r > 70: return -1

            elif sig_fn == "rsi_bb":
                r = self._rsi(closes, 3)
                mid = np.mean(closes[-20:])
                std = np.std(closes[-20:])
                lower = mid - 2.5 * std
                upper = mid + 2.5 * std
                if r < 25 and closes[-1] < lower: return 1
                if r > 75 and closes[-1] > upper: return -1

            elif sig_fn == "kelt_bo":
                ema = self._ema(closes, 30)
                atr_val = self._calc_atr(highs, lows, closes, 30)
                upper = ema + 2.0 * atr_val
                lower = ema - 2.0 * atr_val
                if len(closes) >= 2:
                    if closes[-2] <= upper and closes[-1] > upper: return 1
                    if closes[-2] >= lower and closes[-1] < lower: return -1

            elif sig_fn == "rsi_kelt":
                r = self._rsi(closes, 3)
                ema = self._ema(closes, 20)
                atr_val = self._calc_atr(highs, lows, closes, 20)
                lower = ema - 2.5 * atr_val
                upper = ema + 2.5 * atr_val
                if r < 25 and closes[-1] < lower: return 1
                if r > 75 and closes[-1] > upper: return -1

            elif sig_fn == "ibs_nq":
                rng = highs[-1] - lows[-1]
                if rng > 0:
                    ibs = (closes[-1] - lows[-1]) / rng
                    if ibs < 0.15: return 1
                    if ibs > 0.85: return -1

            elif sig_fn == "kelt_mr_cl":
                ema = self._ema(closes, 14)
                atr_val = self._calc_atr(highs, lows, closes, 14)
                lower = ema - 2.5 * atr_val
                upper = ema + 2.5 * atr_val
                if closes[-1] < lower: return 1
                if closes[-1] > upper: return -1

            elif sig_fn == "ibs_cl":
                rng = highs[-1] - lows[-1]
                if rng > 0:
                    ibs = (closes[-1] - lows[-1]) / rng
                    if ibs < 0.1: return 1
                    if ibs > 0.9: return -1

            return 0
        except Exception:
            return 0

    def _rsi(self, closes, period):
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0: return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _ema(self, data, span):
        a = 2.0 / (span + 1)
        e = float(data[0])
        for v in data[1:]:
            e = a * float(v) + (1 - a) * e
        return e

    def _calc_atr(self, highs, lows, closes, period):
        trs = []
        for i in range(1, len(closes)):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
            trs.append(tr)
        return np.mean(trs[-period:]) if len(trs) >= period else (np.mean(trs) if trs else 0)

    def _get_atr(self, sym):
        try:
            h = self.history(sym, 20, Resolution.HOUR)
            if h.empty or len(h) < 14: return None
            return self._calc_atr(h["high"].values, h["low"].values, h["close"].values, 14)
        except: return None

    def on_end_of_algorithm(self):
        for y in sorted(self._year_start.keys()):
            rets = self._year_rets.get(y, [])
            se = self._year_start[y]
            bc = self._bet_count.get(y, 0)
            bw = self._bet_wins.get(y, 0)
            if rets:
                a = np.array(rets)
                s = float(np.std(a, ddof=1)) if len(a) > 1 else 0
                sh = (float(np.mean(a)) / s * np.sqrt(252)) if s > 0 else 0
                cu = np.cumprod(1 + a)
                ee = se * cu[-1]
                rp = (ee / se - 1) * 100
                dd = float(np.min(cu / np.maximum.accumulate(cu) - 1) * 100)
            else:
                sh = rp = dd = 0; ee = se
            self.set_runtime_statistic(f"y_{y}", f"{sh:.3f}|{rp:.1f}|{dd:.1f}|{ee:.0f}|{bc}|{bw}")

        if self._eq_log:
            bs = 25; nb = 0
            for i in range(0, len(self._eq_log), bs):
                self.set_runtime_statistic(f"eq_{nb:03d}", "|".join(self._eq_log[i:i+bs]))
                nb += 1
            self.set_runtime_statistic("eq_count", str(nb))

    def on_securities_changed(self, changes):
        for sec in changes.added_securities:
            if sec.symbol.security_type != SecurityType.BASE:
                sec.set_fee_model(InteractiveBrokersFeeModel())
