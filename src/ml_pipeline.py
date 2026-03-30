"""
De Prado ML Pipeline — Sprint 5

Implements the full AFML framework for trend following:
1. Triple barrier labeling
2. Fractional differentiation (FFD)
3. Feature engineering
4. Meta-labeling with Random Forest
5. Bet sizing from meta-label probability
6. Purged K-Fold cross-validation
7. Feature importance (MDA)
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, log_loss
from sklearn.calibration import CalibratedClassifierCV

from src.signals import _ema, _atr


# ── 1. Triple Barrier Labeling ───────────────────────────────────────

def triple_barrier_labels(
    close: pd.Series,
    signal: pd.Series,
    atr: pd.Series,
    pt_mult: float = 2.0,
    sl_mult: float = 1.0,
    max_hold: int = 20,
) -> pd.DataFrame:
    """
    Triple barrier method (De Prado AFML Ch. 3).

    For each signal event (signal != 0), compute which barrier is hit first:
    - Upper: entry + pt_mult * ATR → label = +1
    - Lower: entry - sl_mult * ATR → label = -1
    - Vertical: max_hold days → label = sign of return

    Returns DataFrame with columns: entry_date, exit_date, label, return, holding_days
    """
    events = []
    signal_dates = signal.index[signal != 0]

    for entry_date in signal_dates:
        if entry_date not in close.index or entry_date not in atr.index:
            continue

        entry_price = close.loc[entry_date]
        entry_atr = atr.loc[entry_date]
        direction = np.sign(signal.loc[entry_date])

        if pd.isna(entry_atr) or entry_atr <= 0:
            continue

        # Barriers (adjusted for direction)
        if direction > 0:
            upper = entry_price + pt_mult * entry_atr
            lower = entry_price - sl_mult * entry_atr
        else:
            upper = entry_price + sl_mult * entry_atr  # Stop for shorts
            lower = entry_price - pt_mult * entry_atr  # Target for shorts

        # Scan forward
        entry_idx = close.index.get_loc(entry_date)
        max_idx = min(entry_idx + max_hold, len(close) - 1)

        label = 0
        exit_date = close.index[max_idx]
        exit_price = close.iloc[max_idx]

        for j in range(entry_idx + 1, max_idx + 1):
            price = close.iloc[j]
            if direction > 0:
                if price >= upper:
                    label = 1
                    exit_date = close.index[j]
                    exit_price = price
                    break
                elif price <= lower:
                    label = -1
                    exit_date = close.index[j]
                    exit_price = price
                    break
            else:
                if price <= lower:
                    label = 1  # Profit for short
                    exit_date = close.index[j]
                    exit_price = price
                    break
                elif price >= upper:
                    label = -1  # Loss for short
                    exit_date = close.index[j]
                    exit_price = price
                    break

        if label == 0:
            # Vertical barrier hit
            ret = (exit_price - entry_price) / entry_price * direction
            label = 1 if ret > 0 else -1

        events.append({
            "entry_date": entry_date,
            "exit_date": exit_date,
            "direction": direction,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "label": label,
            "return": (exit_price - entry_price) / entry_price * direction,
            "holding_days": (exit_date - entry_date).days,
        })

    return pd.DataFrame(events) if events else pd.DataFrame()


# ── 2. Fractional Differentiation (FFD) ──────────────────────────────

def frac_diff_ffd(series: pd.Series, d: float, threshold: float = 1e-5) -> pd.Series:
    """
    Fixed-width window fractional differentiation (De Prado AFML Ch. 5).

    Parameters
    ----------
    series : pd.Series
        Price series.
    d : float
        Fractional differencing order (0 < d < 1).
    threshold : float
        Weight threshold for window truncation.

    Returns
    -------
    pd.Series of fractionally differenced values.
    """
    # Compute weights
    weights = [1.0]
    k = 1
    while True:
        w = -weights[-1] * (d - k + 1) / k
        if abs(w) < threshold:
            break
        weights.append(w)
        k += 1
        if k > 500:
            break

    weights = np.array(weights[::-1])
    width = len(weights)

    result = pd.Series(index=series.index, dtype=float)
    for i in range(width - 1, len(series)):
        result.iloc[i] = np.dot(weights, series.iloc[i - width + 1:i + 1].values)

    return result


def find_min_d(series: pd.Series, max_d: float = 1.0, step: float = 0.05) -> float:
    """Find minimum d that makes the series stationary (ADF test p < 0.05)."""
    from statsmodels.tsa.stattools import adfuller

    for d in np.arange(0.0, max_d + step, step):
        try:
            diffed = frac_diff_ffd(series, d)
            diffed = diffed.dropna()
            if len(diffed) < 100:
                continue
            result = adfuller(diffed, maxlag=1)
            if result[1] < 0.05:  # p-value < 5%
                return round(d, 2)
        except Exception:
            continue
    return 0.5  # Default


# ── 3. Feature Engineering ───────────────────────────────────────────

def build_features(df: pd.DataFrame, d: float = 0.4) -> pd.DataFrame:
    """
    Build feature matrix for meta-labeling.

    Features:
    - Fractionally differenced price
    - Multi-lookback momentum (5, 21, 63, 126, 252 days)
    - Volatility (20d, 60d realized vol)
    - ATR ratio (short/long)
    - Trend strength (ADX proxy)
    - Volume trend
    """
    close = df["close"]
    features = pd.DataFrame(index=df.index)

    # Fracdiff price
    features["fracdiff"] = frac_diff_ffd(close, d)

    # Momentum at multiple lookbacks
    for lb in [5, 21, 63, 126, 252]:
        features[f"mom_{lb}"] = close.pct_change(lb)

    # Realized vol
    returns = close.pct_change()
    features["vol_20"] = returns.rolling(20).std() * np.sqrt(252)
    features["vol_60"] = returns.rolling(60).std() * np.sqrt(252)
    features["vol_ratio"] = features["vol_20"] / features["vol_60"].replace(0, np.nan)

    # ATR ratio
    atr_fast = _atr(df, 5)
    atr_slow = _atr(df, 20)
    features["atr_ratio"] = atr_fast / atr_slow.replace(0, np.nan)

    # Price vs moving averages (trend strength proxies)
    for p in [20, 50, 200]:
        ma = _sma_safe(close, p)
        features[f"price_vs_ma{p}"] = (close - ma) / ma

    # Volume trend (if available)
    if "volume" in df.columns:
        vol = df["volume"]
        features["vol_ma_ratio"] = vol / vol.rolling(20).mean().replace(0, np.nan)

    return features


def _sma_safe(series, window):
    return series.rolling(window).mean()


# ── 4. Meta-Labeling ────────────────────────────────────────────────

def train_meta_label_model(
    features: pd.DataFrame,
    labels: pd.Series,
    n_splits: int = 5,
    purge_window: int = 20,
    embargo: int = 5,
) -> tuple:
    """
    Train meta-label classifier with purged k-fold CV.

    Parameters
    ----------
    features : pd.DataFrame
        Feature matrix (aligned with labels).
    labels : pd.Series
        Binary labels: 1 = profitable, 0 = unprofitable.
    n_splits : int
        Number of CV folds.
    purge_window : int
        Days to purge around test set boundaries.
    embargo : int
        Additional embargo days after purge.

    Returns
    -------
    tuple: (fitted_model, cv_scores, feature_importances)
    """
    # Clean
    common = features.index.intersection(labels.index)
    X = features.loc[common].copy()
    y = labels.loc[common].copy()

    # Drop rows with NaN
    mask = X.notna().all(axis=1) & y.notna()
    X = X[mask]
    y = y[mask]

    if len(X) < 100:
        return None, [], {}

    # Purged K-Fold CV
    fold_size = len(X) // n_splits
    cv_scores = []
    all_importances = []

    for fold in range(n_splits):
        test_start = fold * fold_size
        test_end = min((fold + 1) * fold_size, len(X))

        # Purge: remove training samples that overlap with test
        train_mask = np.ones(len(X), dtype=bool)
        purge_start = max(0, test_start - purge_window)
        purge_end = min(len(X), test_end + purge_window + embargo)
        train_mask[purge_start:purge_end] = False

        # Test set
        test_mask = np.zeros(len(X), dtype=bool)
        test_mask[test_start:test_end] = True

        X_train, y_train = X.iloc[train_mask], y.iloc[train_mask]
        X_test, y_test = X.iloc[test_mask], y.iloc[test_mask]

        if len(X_train) < 50 or len(X_test) < 10:
            continue

        rf = RandomForestClassifier(
            n_estimators=100,
            max_depth=5,
            min_samples_leaf=10,
            max_features="sqrt",
            random_state=42 + fold,
            n_jobs=-1,
        )
        rf.fit(X_train, y_train)

        pred = rf.predict(X_test)
        acc = accuracy_score(y_test, pred)
        cv_scores.append(acc)
        all_importances.append(rf.feature_importances_)

    # Fit final model on all data
    final_rf = RandomForestClassifier(
        n_estimators=200,
        max_depth=5,
        min_samples_leaf=10,
        max_features="sqrt",
        random_state=42,
        n_jobs=-1,
    )
    final_rf.fit(X, y)

    # Average feature importances
    avg_importance = np.mean(all_importances, axis=0) if all_importances else final_rf.feature_importances_
    importance_dict = dict(zip(X.columns, avg_importance))

    return final_rf, cv_scores, importance_dict


# ── 5. Bet Sizing ───────────────────────────────────────────────────

def bet_size_from_probability(prob: pd.Series, discretize: bool = True) -> pd.Series:
    """
    Map meta-label probability to bet size (De Prado AFML Ch. 10).
    size = 2 * Phi(Z(p)) - 1, simplified to a sigmoid-like mapping.

    prob > 0.5 → positive size (trade the signal)
    prob < 0.5 → zero size (skip the signal)
    """
    # Simple mapping: (prob - 0.5) * 2, clipped to [0, 1]
    size = (prob - 0.5).clip(0, 0.5) * 2

    if discretize:
        # Discretize to levels: 0, 0.25, 0.5, 0.75, 1.0
        size = (size * 4).round() / 4

    return size


# ── 6. Full Pipeline ────────────────────────────────────────────────

def run_ml_pipeline(
    df: pd.DataFrame,
    base_signal: pd.Series,
    symbol: str,
    fracdiff_d: float = 0.4,
    pt_mult: float = 2.0,
    sl_mult: float = 1.0,
    max_hold: int = 20,
) -> dict:
    """
    Run the full De Prado pipeline for one instrument.

    Returns dict with:
        enhanced_signal, model, cv_scores, feature_importance, labels
    """
    close = df["close"]
    atr = _atr(df, 20)

    # Step 1: Triple barrier labels
    labels_df = triple_barrier_labels(close, base_signal, atr, pt_mult, sl_mult, max_hold)

    if labels_df.empty or len(labels_df) < 50:
        return {"enhanced_signal": base_signal, "model": None, "cv_scores": [],
                "feature_importance": {}, "labels": labels_df, "status": "insufficient_labels"}

    # Convert labels to binary (1 = profitable, 0 = not)
    binary_labels = pd.Series(index=labels_df["entry_date"], dtype=int)
    binary_labels[:] = (labels_df["label"].values == 1).astype(int)

    # Step 2: Build features
    features = build_features(df, d=fracdiff_d)

    # Step 3: Train meta-label model
    model, cv_scores, importance = train_meta_label_model(
        features, binary_labels, n_splits=5, purge_window=max_hold, embargo=5,
    )

    if model is None:
        return {"enhanced_signal": base_signal, "model": None, "cv_scores": [],
                "feature_importance": {}, "labels": labels_df, "status": "training_failed"}

    # Step 4: Generate predictions on full dataset
    X_full = features.dropna()
    if len(X_full) < 10:
        return {"enhanced_signal": base_signal, "model": model, "cv_scores": cv_scores,
                "feature_importance": importance, "labels": labels_df, "status": "no_features"}

    try:
        proba = model.predict_proba(X_full)[:, 1]
    except Exception:
        proba = np.full(len(X_full), 0.5)

    prob_series = pd.Series(proba, index=X_full.index)

    # Step 5: Bet sizing
    bet_sizes = bet_size_from_probability(prob_series)

    # Step 6: Enhanced signal = base_signal * bet_size
    enhanced = base_signal.copy()
    for date in bet_sizes.index:
        if date in enhanced.index:
            enhanced.loc[date] = base_signal.loc[date] * bet_sizes.loc[date]

    return {
        "enhanced_signal": enhanced,
        "model": model,
        "cv_scores": cv_scores,
        "feature_importance": importance,
        "labels": labels_df,
        "prob_series": prob_series,
        "bet_sizes": bet_sizes,
        "status": "success",
    }


# ── 7. Feature Importance (MDA) ─────────────────────────────────────

def compute_mda(model, X: pd.DataFrame, y: pd.Series, n_repeats: int = 5) -> dict:
    """
    Mean Decrease Accuracy (permutation importance).
    Shuffle each feature and measure accuracy drop.
    """
    base_acc = accuracy_score(y, model.predict(X))
    importances = {}

    for col in X.columns:
        drops = []
        for _ in range(n_repeats):
            X_perm = X.copy()
            X_perm[col] = np.random.permutation(X_perm[col].values)
            perm_acc = accuracy_score(y, model.predict(X_perm))
            drops.append(base_acc - perm_acc)
        importances[col] = np.mean(drops)

    return importances
