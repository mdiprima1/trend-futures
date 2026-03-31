# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class TrendFuturesHRP(QCAlgorithm):
    """
    QSL Trend Futures v1.0 — HRP 15% Vol Target

    Signal: Fast+Slow blend (EMA 10/100 + TSMOM 252d)
    Universe: 26 CME futures across 6 sectors
    Allocation: Pre-computed HRP weights
    Vol target: 15% annualized
    Rebalance: Daily check, weekly full rebalance

    Roll handling: check EVERY DAY if we should have a position
    but don't (due to roll gap). Re-enter immediately.
    """

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2025, 12, 31)
        self._initial_capital = 1_000_000
        self.set_cash(self._initial_capital)

        self.ema_fast = 10
        self.ema_slow = 100
        self.tsmom_lookback = 252
        self.atr_period = 20
        self.vol_target = 0.15
        self.max_contracts = 200

        # HRP Weights
        self.hrp_weights = {
            "ZT": 0.8270, "ZN": 0.0265, "ZB": 0.0221,
            "6C": 0.0208, "6E": 0.0170, "GC": 0.0142,
            "LE": 0.0117, "6J": 0.0097, "6S": 0.0091,
            "6B": 0.0076, "6A": 0.0043, "ZS": 0.0042,
            "6N": 0.0038, "ZW": 0.0038, "ZC": 0.0028,
            "HO": 0.0022, "PL": 0.0022, "SI": 0.0019,
            "HG": 0.0015, "ES": 0.0014, "NKD": 0.0012,
            "CL": 0.0011, "NG": 0.0010,
            "RTY": 0.0009, "NQ": 0.0008, "RB": 0.0005,
        }

        # Target signals (persisted between rebalances)
        self._target_signals = {}

        # Futures
        self.instrument_configs = {
            "ES":  Futures.Indices.SP_500_E_MINI,
            "NQ":  Futures.Indices.NASDAQ_100_E_MINI,
            "RTY": Futures.Indices.RUSSELL_2000_E_MINI,
            "NKD": Futures.Indices.NIKKEI_225_DOLLAR,
            "ZT":  Futures.Financials.Y_2_TREASURY_NOTE,
            "ZN":  Futures.Financials.Y_10_TREASURY_NOTE,
            "ZB":  Futures.Financials.Y_30_TREASURY_BOND,
            "6E":  Futures.Currencies.EUR,
            "6B":  Futures.Currencies.GBP,
            "6J":  Futures.Currencies.JPY,
            "6A":  Futures.Currencies.AUD,
            "6C":  Futures.Currencies.CAD,
            "6S":  Futures.Currencies.CHF,
            "6N":  Futures.Currencies.NZD,
            "CL":  Futures.Energies.CRUDE_OIL_WTI,
            "NG":  Futures.Energies.NATURAL_GAS,
            "RB":  Futures.Energies.GASOLINE,
            "HO":  Futures.Energies.HEATING_OIL,
            "GC":  Futures.Metals.GOLD,
            "SI":  Futures.Metals.SILVER,
            "HG":  Futures.Metals.COPPER,
            "PL":  Futures.Metals.PLATINUM,
            "ZC":  Futures.Grains.CORN,
            "ZS":  Futures.Grains.SOYBEANS,
            "ZW":  Futures.Grains.WHEAT,
            "LE":  Futures.Meats.LIVE_CATTLE,
        }

        self.futures = {}
        self.symbol_keys = {}
        self._previous_contracts = {}

        for key, contract in self.instrument_configs.items():
            future = self.add_future(
                contract,
                resolution=Resolution.DAILY,
                data_normalization_mode=DataNormalizationMode.FORWARD_PANAMA_CANAL,
                data_mapping_mode=DataMappingMode.OPEN_INTEREST,
                contract_depth_offset=0,
            )
            future.set_filter(0, 90)
            self.futures[future.symbol] = future
            self.symbol_keys[future.symbol] = key

        self._last_signal_week = None

        # Equity tracking
        self._equity_log = []
        self._last_equity_date = None
        self._year_start_equity = {}
        self._daily_returns = {}
        self._prev_equity = None

        self.set_warm_up(timedelta(days=300))

    def on_data(self, data):
        if self.is_warming_up:
            return

        self._handle_rollovers()
        self._record_daily()

        # Recompute signals weekly (Monday)
        current_week = f"{self.time.year}-{self.time.isocalendar()[1]}"
        if current_week != self._last_signal_week and self.time.weekday() == 0:
            self._last_signal_week = current_week
            self._update_signals()

        # Enforce positions DAILY — this catches roll gaps
        self._enforce_positions()

    def _update_signals(self):
        """Recompute target signals for all instruments."""
        for s, future in self.futures.items():
            key = self.symbol_keys[s]
            mapped = future.mapped
            if mapped is None:
                self._target_signals[key] = 0
                continue
            self._target_signals[key] = self._compute_signal(mapped)

    def _enforce_positions(self):
        """
        Check EVERY DAY: do we have the right position?
        If not (e.g., after a roll gap), fix it immediately.
        """
        portfolio_value = self.portfolio.total_portfolio_value

        for s, future in self.futures.items():
            key = self.symbol_keys[s]
            mapped = future.mapped
            if mapped is None:
                continue

            signal = self._target_signals.get(key, 0)
            weight = self.hrp_weights.get(key, 0)

            # What should we hold?
            if signal == 0 or weight < 0.0005:
                # Should be flat
                if self.portfolio[mapped].invested:
                    self.liquidate(mapped, tag=f"{key} FLAT")
                continue

            # Compute target position
            target_qty = self._compute_position(mapped, key, signal, weight, portfolio_value)
            if target_qty is None:
                continue

            current_qty = self.portfolio[mapped].quantity

            # If we're flat but should be in (roll gap), enter immediately
            if current_qty == 0 and target_qty != 0:
                self.market_order(mapped, target_qty, tag=f"{key} ENTER")
                continue

            # Normal weekly adjustment: only adjust if difference is >20%
            if current_qty != 0:
                pct_diff = abs(target_qty - current_qty) / abs(current_qty)
                if pct_diff > 0.20:
                    diff = target_qty - current_qty
                    if abs(diff) >= 1:
                        self.market_order(mapped, diff, tag=f"{key} ADJ")

    def _compute_signal(self, mapped):
        try:
            h = self.history(mapped, self.tsmom_lookback + 20, Resolution.DAILY)
            if h.empty or len(h) < self.ema_slow + 10:
                return 0

            closes = h["close"].values
            ema_f = self._ema_val(closes, self.ema_fast)
            ema_s = self._ema_val(closes, self.ema_slow)
            ema_signal = 1 if ema_f > ema_s else -1

            if len(closes) >= self.tsmom_lookback:
                ret = closes[-1] / closes[-self.tsmom_lookback] - 1
                tsmom_signal = 1 if ret > 0 else -1
            else:
                tsmom_signal = 0

            blend = (ema_signal + tsmom_signal) / 2.0
            if blend > 0: return 1
            elif blend < 0: return -1
            return 0
        except Exception:
            return 0

    def _compute_position(self, mapped, key, signal, weight, portfolio_value):
        try:
            h = self.history(mapped, self.atr_period + 5, Resolution.DAILY)
            if h.empty or len(h) < self.atr_period:
                return None

            closes = h["close"].values
            highs = h["high"].values
            lows = h["low"].values
            prev_c = np.roll(closes, 1); prev_c[0] = closes[0]
            tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_c), np.abs(lows - prev_c)))
            atr = float(np.mean(tr[-self.atr_period:]))
            if atr <= 0: return None

            sec = self.securities[mapped]
            mult = sec.symbol_properties.contract_multiplier
            if not mult or mult <= 0: mult = 1

            dollar_risk_per_contract = atr * mult
            if dollar_risk_per_contract <= 0: return None

            target_annual_risk = portfolio_value * weight * self.vol_target
            target_daily_risk = target_annual_risk / np.sqrt(252)
            n = int(target_daily_risk / dollar_risk_per_contract)
            n = min(abs(n), self.max_contracts)
            return max(1, n) * signal if n >= 1 else 0
        except Exception:
            return None

    def _ema_val(self, data, span):
        alpha = 2.0 / (span + 1)
        ema = float(data[0])
        for i in range(1, len(data)):
            ema = alpha * float(data[i]) + (1 - alpha) * ema
        return ema

    def _handle_rollovers(self):
        for s, future in self.futures.items():
            key = self.symbol_keys[s]
            mapped = future.mapped
            if mapped is None: continue
            prev = self._previous_contracts.get(s)
            if prev is not None and prev != mapped:
                if self.portfolio[prev].invested:
                    qty = self.portfolio[prev].quantity
                    self.liquidate(prev, tag=f"Roll out {key}")
                    self.market_order(mapped, qty, tag=f"Roll in {key}")
            self._previous_contracts[s] = mapped

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
            start_eq = self._year_start_equity[year]
            if rets:
                arr = np.array(rets)
                std_r = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
                sharpe = (float(np.mean(arr)) / std_r * np.sqrt(252)) if std_r > 0 else 0.0
                cum = np.cumprod(1.0 + arr)
                end_eq = start_eq * cum[-1]
                ret_pct = (end_eq / start_eq - 1.0) * 100
                dd = float(np.min(cum / np.maximum.accumulate(cum) - 1.0) * 100)
            else:
                sharpe = ret_pct = dd = 0.0; end_eq = start_eq
            self.set_runtime_statistic(f"y_{year}", f"{sharpe:.3f}|{ret_pct:.1f}|{dd:.1f}|{end_eq:.0f}")

        if self._equity_log:
            bs = 25; nb = 0
            for i in range(0, len(self._equity_log), bs):
                self.set_runtime_statistic(f"eq_{nb:03d}", "|".join(self._equity_log[i:i+bs]))
                nb += 1
            self.set_runtime_statistic("eq_count", str(nb))

    def on_securities_changed(self, changes):
        for sec in changes.added_securities:
            if sec.symbol.security_type != SecurityType.BASE:
                sec.set_fee_model(InteractiveBrokersFeeModel())
