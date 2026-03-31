# region imports
from AlgorithmImports import *
import numpy as np
# endregion


class TrendFuturesV2(QCAlgorithm):
    """
    QSL Trend Futures v2.0 — Realistic Version

    After QC validation showed v1 (HRP concentrated) didn't work in practice,
    this version uses:
    - Top 10 trend-positive instruments only (no dead weight)
    - Equal weight allocation (no concentration risk)
    - 15% vol target with ATR sizing
    - Daily position enforcement (catches roll gaps)
    - Fast+Slow signal blend (EMA 10/100 + TSMOM 252d)
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

        # Only instruments with positive trend Sharpe from our research
        self.instrument_configs = {
            "ZT":  Futures.Financials.Y_2_TREASURY_NOTE,      # Sharpe 1.16
            "GC":  Futures.Metals.GOLD,                        # Sharpe 1.00
            "ZN":  Futures.Financials.Y_10_TREASURY_NOTE,      # Sharpe 0.59
            "NQ":  Futures.Indices.NASDAQ_100_E_MINI,          # Sharpe 0.57
            "SI":  Futures.Metals.SILVER,                      # Sharpe 0.43
            "LE":  Futures.Meats.LIVE_CATTLE,                  # Sharpe 0.36
            "HG":  Futures.Metals.COPPER,                      # Sharpe 0.31
            "ZS":  Futures.Grains.SOYBEANS,                    # Sharpe 0.31
            "ES":  Futures.Indices.SP_500_E_MINI,              # Sharpe 0.27
            "6J":  Futures.Currencies.JPY,                     # Sharpe 0.18
        }

        # Equal weight
        n = len(self.instrument_configs)
        self.weights = {k: 1.0 / n for k in self.instrument_configs}

        self.futures = {}
        self.symbol_keys = {}
        self._previous_contracts = {}
        self._target_signals = {}
        self._last_signal_week = None

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

        # Update signals weekly
        week = f"{self.time.year}-{self.time.isocalendar()[1]}"
        if week != self._last_signal_week and self.time.weekday() == 0:
            self._last_signal_week = week
            self._update_signals()

        # Enforce positions daily
        self._enforce_positions()

    def _update_signals(self):
        for s, future in self.futures.items():
            key = self.symbol_keys[s]
            mapped = future.mapped
            if mapped is None:
                self._target_signals[key] = 0
                continue
            self._target_signals[key] = self._compute_signal(mapped)

    def _enforce_positions(self):
        pv = self.portfolio.total_portfolio_value

        for s, future in self.futures.items():
            key = self.symbol_keys[s]
            mapped = future.mapped
            if mapped is None:
                continue

            signal = self._target_signals.get(key, 0)
            weight = self.weights.get(key, 0)

            if signal == 0 or weight < 0.001:
                if self.portfolio[mapped].invested:
                    self.liquidate(mapped, tag=f"{key} FLAT")
                continue

            target = self._size_position(mapped, key, signal, weight, pv)
            if target is None:
                continue

            current = self.portfolio[mapped].quantity

            # Enter if flat (roll gap recovery)
            if current == 0 and target != 0:
                self.market_order(mapped, target, tag=f"{key} ENTER")
                continue

            # Adjust if >25% off target
            if current != 0 and abs(target - current) / abs(current) > 0.25:
                diff = target - current
                if abs(diff) >= 1:
                    self.market_order(mapped, diff, tag=f"{key} ADJ")

    def _compute_signal(self, mapped):
        try:
            h = self.history(mapped, self.tsmom_lookback + 20, Resolution.DAILY)
            if h.empty or len(h) < self.ema_slow + 10:
                return 0
            closes = h["close"].values

            ema_f = self._ema(closes, self.ema_fast)
            ema_s = self._ema(closes, self.ema_slow)
            ema_sig = 1 if ema_f > ema_s else -1

            if len(closes) >= self.tsmom_lookback:
                tsmom_sig = 1 if closes[-1] / closes[-self.tsmom_lookback] - 1 > 0 else -1
            else:
                tsmom_sig = 0

            blend = (ema_sig + tsmom_sig) / 2.0
            return 1 if blend > 0 else (-1 if blend < 0 else 0)
        except:
            return 0

    def _size_position(self, mapped, key, signal, weight, portfolio_value):
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

            mult = self.securities[mapped].symbol_properties.contract_multiplier
            if not mult or mult <= 0: mult = 1

            risk_per_contract = atr * mult
            if risk_per_contract <= 0: return None

            target_daily_risk = portfolio_value * weight * self.vol_target / np.sqrt(252)
            n = int(target_daily_risk / risk_per_contract)
            n = min(abs(n), self.max_contracts)
            return max(1, n) * signal if n >= 1 else 0
        except:
            return None

    def _ema(self, data, span):
        a = 2.0 / (span + 1)
        e = float(data[0])
        for i in range(1, len(data)):
            e = a * float(data[i]) + (1 - a) * e
        return e

    def _handle_rollovers(self):
        for s, future in self.futures.items():
            key = self.symbol_keys[s]
            mapped = future.mapped
            if mapped is None: continue
            prev = self._previous_contracts.get(s)
            if prev is not None and prev != mapped:
                if self.portfolio[prev].invested:
                    qty = self.portfolio[prev].quantity
                    self.liquidate(prev, tag=f"Roll {key}")
                    self.market_order(mapped, qty, tag=f"Roll {key}")
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
