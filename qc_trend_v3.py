# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class TrendFuturesV3(QCAlgorithm):
    """
    QSL Trend Futures v3.0 — Monthly TSMOM, Simple Rolls

    Changes from v2:
    - Monthly rebalance (not weekly) — reduces friction
    - Pure TSMOM(252d) signal — simplest, matches academic spec
    - Simple continuous contract rolls (QC handles mapping)
    - Daily gap-fill for positions that should exist but don't
    - Equal weight across 10 trend-positive instruments
    """

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2025, 12, 31)
        self._initial_capital = 1_000_000
        self.set_cash(self._initial_capital)

        self.tsmom_lookback = 252
        self.atr_period = 20
        self.vol_target = 0.15
        self.max_contracts = 200

        self.instrument_map = {
            "ZT":  Futures.Financials.Y_2_TREASURY_NOTE,
            "GC":  Futures.Metals.GOLD,
            "ZN":  Futures.Financials.Y_10_TREASURY_NOTE,
            "NQ":  Futures.Indices.NASDAQ_100_E_MINI,
            "SI":  Futures.Metals.SILVER,
            "LE":  Futures.Meats.LIVE_CATTLE,
            "HG":  Futures.Metals.COPPER,
            "ZS":  Futures.Grains.SOYBEANS,
            "ES":  Futures.Indices.SP_500_E_MINI,
            "6J":  Futures.Currencies.JPY,
        }

        n = len(self.instrument_map)
        self.weights = {k: 1.0 / n for k in self.instrument_map}

        self.futures = {}
        self.symbol_keys = {}
        self._prev_contracts = {}
        self._target_signals = {}
        self._target_quantities = {}
        self._last_rebal_month = None

        for key, contract in self.instrument_map.items():
            future = self.add_future(
                contract,
                resolution=Resolution.DAILY,
                data_normalization_mode=DataNormalizationMode.BACKWARDS_RATIO,
                data_mapping_mode=DataMappingMode.OPEN_INTEREST,
                contract_depth_offset=0,
            )
            future.set_filter(0, 90)
            self.futures[future.symbol] = future
            self.symbol_keys[future.symbol] = key

        self._equity_log = []
        self._last_equity_date = None
        self._year_start_equity = {}
        self._daily_returns = {}
        self._prev_equity = None
        self.set_warm_up(timedelta(days=300))

    def on_data(self, data):
        if self.is_warming_up:
            return

        self._handle_rolls()
        self._record_daily()

        # Monthly signal update
        month = f"{self.time.year}-{self.time.month:02d}"
        if month != self._last_rebal_month and self.time.day <= 5:
            self._last_rebal_month = month
            self._monthly_rebalance()
            return

        # Daily: fill any gaps from rolls
        self._daily_fill()

    def _monthly_rebalance(self):
        pv = self.portfolio.total_portfolio_value

        for canon, future in self.futures.items():
            key = self.symbol_keys[canon]
            mapped = future.mapped
            if mapped is None:
                self._target_signals[key] = 0
                continue

            # TSMOM signal
            sig = self._tsmom(mapped)
            self._target_signals[key] = sig
            weight = self.weights.get(key, 0)

            if sig == 0:
                if self.portfolio[mapped].invested:
                    self.liquidate(mapped, tag=f"{key} FLAT")
                self._target_quantities[key] = 0
                continue

            qty = self._size(mapped, key, sig, weight, pv)
            self._target_quantities[key] = qty if qty else 0

            if qty is None or qty == 0:
                continue

            current = self.portfolio[mapped].quantity
            diff = qty - current
            if abs(diff) >= 1:
                self.market_order(mapped, diff, tag=f"{key} MO")

    def _daily_fill(self):
        """If we should be in a position but aren't (roll gap), enter."""
        pv = self.portfolio.total_portfolio_value

        for canon, future in self.futures.items():
            key = self.symbol_keys[canon]
            mapped = future.mapped
            if mapped is None:
                continue

            sig = self._target_signals.get(key, 0)
            target_qty = self._target_quantities.get(key, 0)

            if sig == 0 or target_qty == 0:
                continue

            current = self.portfolio[mapped].quantity
            if current == 0:
                # Gap detected — re-enter
                qty = self._size(mapped, key, sig, self.weights.get(key, 0), pv)
                if qty and qty != 0:
                    self.market_order(mapped, qty, tag=f"{key} FILL")
                    self._target_quantities[key] = qty

    def _tsmom(self, mapped):
        try:
            h = self.history(mapped, self.tsmom_lookback + 10, Resolution.DAILY)
            if h.empty or len(h) < self.tsmom_lookback:
                return 0
            closes = h["close"].values
            ret = closes[-1] / closes[-self.tsmom_lookback] - 1
            return 1 if ret > 0 else -1
        except:
            return 0

    def _size(self, mapped, key, signal, weight, pv):
        try:
            h = self.history(mapped, self.atr_period + 5, Resolution.DAILY)
            if h.empty or len(h) < self.atr_period:
                return None
            c = h["close"].values; hi = h["high"].values; lo = h["low"].values
            pc = np.roll(c, 1); pc[0] = c[0]
            tr = np.maximum(hi-lo, np.maximum(np.abs(hi-pc), np.abs(lo-pc)))
            atr = float(np.mean(tr[-self.atr_period:]))
            if atr <= 0: return None
            mult = self.securities[mapped].symbol_properties.contract_multiplier
            if not mult or mult <= 0: mult = 1
            risk = atr * mult
            if risk <= 0: return None
            target = pv * weight * self.vol_target / np.sqrt(252)
            n = min(int(target / risk), self.max_contracts)
            return max(1, n) * signal if n >= 1 else 0
        except:
            return None

    def _handle_rolls(self):
        for canon, future in self.futures.items():
            key = self.symbol_keys[canon]
            mapped = future.mapped
            if mapped is None: continue
            prev = self._prev_contracts.get(key)
            if prev is not None and prev != mapped:
                if self.portfolio[prev].invested:
                    qty = self.portfolio[prev].quantity
                    self.liquidate(prev, tag=f"Roll {key}")
                    self.market_order(mapped, qty, tag=f"Roll {key}")
            self._prev_contracts[key] = mapped

    def _record_daily(self):
        eq = self.portfolio.total_portfolio_value
        year = self.time.year
        if year not in self._year_start_equity:
            self._year_start_equity[year] = eq
            self._daily_returns[year] = []
        if self._prev_equity and self._prev_equity > 0:
            self._daily_returns[year].append((eq - self._prev_equity) / self._prev_equity)
        self._prev_equity = eq
        today = self.time.strftime("%Y%m%d")
        if today != self._last_equity_date:
            self._equity_log.append(f"{today}:{eq:.0f}")
            self._last_equity_date = today

    def on_end_of_algorithm(self):
        for year in sorted(self._year_start_equity.keys()):
            rets = self._daily_returns.get(year, [])
            seq = self._year_start_equity[year]
            if rets:
                a = np.array(rets); s = float(np.std(a, ddof=1)) if len(a)>1 else 0
                sh = (float(np.mean(a))/s*np.sqrt(252)) if s>0 else 0
                cu = np.cumprod(1+a); ee = seq*cu[-1]; rp=(ee/seq-1)*100
                dd = float(np.min(cu/np.maximum.accumulate(cu)-1)*100)
            else: sh=rp=dd=0; ee=seq
            self.set_runtime_statistic(f"y_{year}", f"{sh:.3f}|{rp:.1f}|{dd:.1f}|{ee:.0f}")
        if self._equity_log:
            bs=25; nb=0
            for i in range(0,len(self._equity_log),bs):
                self.set_runtime_statistic(f"eq_{nb:03d}","|".join(self._equity_log[i:i+bs])); nb+=1
            self.set_runtime_statistic("eq_count",str(nb))

    def on_securities_changed(self, changes):
        for sec in changes.added_securities:
            if sec.symbol.security_type != SecurityType.BASE:
                sec.set_fee_model(InteractiveBrokersFeeModel())
