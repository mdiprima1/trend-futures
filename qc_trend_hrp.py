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
    Rebalance: Weekly (Monday)
    """

    def initialize(self):
        self.set_start_date(2018, 1, 1)
        self.set_end_date(2025, 12, 31)
        self._initial_capital = 1_000_000
        self.set_cash(self._initial_capital)

        # ── Parameters ──
        self.ema_fast = 10
        self.ema_slow = 100
        self.tsmom_lookback = 252
        self.atr_period = 20
        self.vol_target = 0.15
        self.max_contracts = 200

        # ── HRP Weights ──
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

        # ── Futures Configuration ──
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

        # ── Initialize Futures ──
        self.futures = {}
        self.symbol_keys = {}
        self.current_contracts = {}
        self._previous_contracts = {}

        for key, contract in self.instrument_configs.items():
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

        # ── State ──
        self._last_rebalance_week = None

        # ── Equity Tracking ──
        self._equity_log = []
        self._last_equity_date = None
        self._year_start_equity = {}
        self._daily_returns = {}
        self._prev_equity = None

        self.set_warm_up(timedelta(days=300))

    def on_data(self, data):
        if self.is_warming_up:
            return

        # Handle rollovers every day
        self._handle_rollovers()

        # Record equity daily
        self._record_daily()

        # Rebalance weekly (Monday only)
        current_week = f"{self.time.year}-{self.time.isocalendar()[1]}"
        if current_week == self._last_rebalance_week:
            return
        if self.time.weekday() != 0:  # Monday = 0
            return

        self._last_rebalance_week = current_week
        self._rebalance()

    def _rebalance(self):
        portfolio_value = self.portfolio.total_portfolio_value
        rebal_count = 0

        for s, future in self.futures.items():
            key = self.symbol_keys[s]
            mapped = future.mapped
            if mapped is None:
                continue

            self.current_contracts[s] = mapped

            # Compute signal
            signal = self._compute_signal(mapped)
            weight = self.hrp_weights.get(key, 0)

            if signal == 0 or weight < 0.0005:
                if self.portfolio[mapped].invested:
                    self.liquidate(mapped, tag=f"{key} FLAT")
                    rebal_count += 1
                continue

            # Position sizing
            target_qty = self._compute_position(mapped, key, signal, weight, portfolio_value)
            if target_qty is None:
                continue

            current_qty = self.portfolio[mapped].quantity
            diff = target_qty - current_qty
            if abs(diff) >= 1:
                self.market_order(mapped, diff, tag=f"{key} {'LONG' if target_qty > 0 else 'SHORT'} {abs(target_qty)}")
                rebal_count += 1

    def _compute_signal(self, mapped):
        """Compute Fast+Slow blend signal for one instrument."""
        try:
            h = self.history(mapped, self.tsmom_lookback + 20, Resolution.DAILY)
            if h.empty or len(h) < self.ema_slow + 10:
                return 0

            closes = h["close"].values

            # EMA(10/100)
            ema_f = self._ema_val(closes, self.ema_fast)
            ema_s = self._ema_val(closes, self.ema_slow)
            ema_signal = 1 if ema_f > ema_s else -1

            # TSMOM(252)
            if len(closes) >= self.tsmom_lookback:
                ret = closes[-1] / closes[-self.tsmom_lookback] - 1
                tsmom_signal = 1 if ret > 0 else -1
            else:
                tsmom_signal = 0

            # Blend
            blend = (ema_signal + tsmom_signal) / 2.0
            if blend > 0:
                return 1
            elif blend < 0:
                return -1
            return 0
        except Exception:
            return 0

    def _compute_position(self, mapped, key, signal, weight, portfolio_value):
        """
        Compute target contracts using ATR-based risk sizing.
        contracts = (portfolio $ * weight * vol_target / sqrt(252)) / (ATR * multiplier)
        """
        try:
            h = self.history(mapped, self.atr_period + 5, Resolution.DAILY)
            if h.empty or len(h) < self.atr_period:
                return None

            closes = h["close"].values
            highs = h["high"].values
            lows = h["low"].values

            # ATR in price points
            prev_c = np.roll(closes, 1)
            prev_c[0] = closes[0]
            tr = np.maximum(highs - lows, np.maximum(np.abs(highs - prev_c), np.abs(lows - prev_c)))
            atr = float(np.mean(tr[-self.atr_period:]))

            if atr <= 0:
                return None

            sec = self.securities[mapped]
            mult = sec.symbol_properties.contract_multiplier
            if not mult or mult <= 0:
                mult = 1

            # Dollar risk per day per contract = ATR * multiplier
            risk_per_contract = atr * mult
            if risk_per_contract <= 0:
                return None

            # Target daily dollar risk for this instrument
            # = portfolio * weight * (vol_target / sqrt(252))
            target_daily_risk = portfolio_value * weight * (self.vol_target / np.sqrt(252))

            n = int(target_daily_risk / risk_per_contract)
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
            if mapped is None:
                continue
            prev = self._previous_contracts.get(s)
            self.current_contracts[s] = mapped
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
            start_eq = self._year_start_equity[year]
            rets = self._daily_returns.get(year, [])
            if rets:
                arr = np.array(rets)
                mean_r = float(np.mean(arr))
                std_r = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
                sharpe = (mean_r / std_r * np.sqrt(252)) if std_r > 0 else 0.0
                cum = np.cumprod(1.0 + arr)
                end_eq = start_eq * cum[-1]
                ret_pct = (end_eq / start_eq - 1.0) * 100
                peak = np.maximum.accumulate(cum)
                dd = float(np.min(cum / peak - 1.0) * 100)
            else:
                sharpe = ret_pct = dd = 0.0
                end_eq = start_eq
            self.set_runtime_statistic(f"y_{year}", f"{sharpe:.3f}|{ret_pct:.1f}|{dd:.1f}|{end_eq:.0f}")

        if self._equity_log:
            bs = 25
            nb = 0
            for i in range(0, len(self._equity_log), bs):
                self.set_runtime_statistic(f"eq_{nb:03d}", "|".join(self._equity_log[i:i+bs]))
                nb += 1
            self.set_runtime_statistic("eq_count", str(nb))

    def on_securities_changed(self, changes):
        for sec in changes.added_securities:
            if sec.symbol.security_type != SecurityType.BASE:
                sec.set_fee_model(InteractiveBrokersFeeModel())
