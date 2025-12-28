from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor


@dataclass
class Config:
    date_col: str = "date"
    store_col: str = "store_id"
    sku_col: str = "sku_id"
    target_col: str = "sales"
    promo_col: Optional[str] = None
    price_col: Optional[str] = None

    # feature params
    lags: Tuple[int, ...] = (1, 7, 14, 28)
    roll_windows: Tuple[int, ...] = (7, 14, 28)

    # train params  👇
    horizon: int = 1
    iterations: int = 1000      # 🔥 เปลี่ยนตรงนี้
    depth: int = 8
    learning_rate: float = 0.05
    random_seed: int = 42



def _ensure_datetime(df: pd.DataFrame, col: str) -> pd.DataFrame:
    out = df.copy()
    out[col] = pd.to_datetime(out[col], errors="coerce")
    return out




def make_features(df: pd.DataFrame, cfg: Config) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """
    Returns:
      - df_feat: dataframe with features + y (shifted) and cleaned NA
      - feature_cols: list of feature column names
      - cat_cols: list of categorical feature names for CatBoost
    """
    df = _ensure_datetime(df, cfg.date_col)
    df = df.sort_values([cfg.store_col, cfg.sku_col, cfg.date_col]).copy()

    # calendar features (SAFE)
    df["dow"] = df[cfg.date_col].dt.dayofweek.astype("Int64")
    df["month"] = df[cfg.date_col].dt.month.astype("Int64")
    df["weekofyear"] = df[cfg.date_col].dt.isocalendar().week.astype("Int64")

    # ถ้า dow เป็น <NA> จะได้ is_weekend เป็น <NA> ด้วย -> เติม 0 ก่อน
    df["is_weekend"] = (df["dow"] >= 5).fillna(False).astype(int)


    grp = df.groupby([cfg.store_col, cfg.sku_col], sort=False)

    # lag features
    for l in cfg.lags:
        df[f"lag_{l}"] = grp[cfg.target_col].shift(l)

    # rolling features (shift 1 to avoid leakage)
    shifted = grp[cfg.target_col].shift(1)
    for w in cfg.roll_windows:
        df[f"rmean_{w}"] = shifted.rolling(w).mean().reset_index(level=[0, 1], drop=True)
        df[f"rstd_{w}"] = shifted.rolling(w).std().reset_index(level=[0, 1], drop=True)

    # optional exogenous
    extra_cols = []
    if cfg.promo_col and cfg.promo_col in df.columns:
        extra_cols.append(cfg.promo_col)
    if cfg.price_col and cfg.price_col in df.columns:
        extra_cols.append(cfg.price_col)

    # target
    df["y"] = grp[cfg.target_col].shift(-cfg.horizon)

    # drop rows with NA from lag/rolling/target
    df_feat = df.dropna().copy()

    feature_cols = [
        cfg.store_col, cfg.sku_col,
        "dow", "month", "weekofyear", "is_weekend",
        *[f"lag_{l}" for l in cfg.lags],
        *[f"rmean_{w}" for w in cfg.roll_windows],
        *[f"rstd_{w}" for w in cfg.roll_windows],
        *extra_cols
    ]

    cat_cols = [cfg.store_col, cfg.sku_col, "dow", "month"]  # weekofyear optional
    return df_feat, feature_cols, cat_cols


def time_split(df_feat: pd.DataFrame, cfg: Config, train_end: str, val_end: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    train: date <= train_end
    val:   train_end < date <= val_end
    """
    train_end_dt = pd.to_datetime(train_end)
    val_end_dt = pd.to_datetime(val_end)

    train = df_feat[df_feat[cfg.date_col] <= train_end_dt].copy()
    val = df_feat[(df_feat[cfg.date_col] > train_end_dt) & (df_feat[cfg.date_col] <= val_end_dt)].copy()

    if len(train) == 0 or len(val) == 0:
        raise ValueError("Split resulted in empty train/val. Check dates and data range.")

    return train, val


def train_catboost(
    df: pd.DataFrame,
    cfg: Config,
    train_end: str,
    val_end: str,
) -> Tuple[CatBoostRegressor, dict]:
    df_feat, feature_cols, cat_cols = make_features(df, cfg)
    train_df, val_df = time_split(df_feat, cfg, train_end=train_end, val_end=val_end)

    X_train, y_train = train_df[feature_cols], train_df["y"]
    X_val, y_val = val_df[feature_cols], val_df["y"]

    model = CatBoostRegressor(
    iterations=cfg.iterations,        # = 1000
    learning_rate=cfg.learning_rate,  # = 0.05
    depth=cfg.depth,                  # = 8
    loss_function="RMSE",
    eval_metric="RMSE",               # 🔥 เพิ่ม
    random_seed=cfg.random_seed,      # = 42
    verbose=200,
)

    model.fit(
        X_train, y_train,
        cat_features=[feature_cols.index(c) for c in cat_cols if c in feature_cols],
        eval_set=(X_val, y_val),
        use_best_model=True
    )

    # quick metrics
    val_pred = model.predict(X_val)
    rmse = float(np.sqrt(np.mean((val_pred - y_val.values) ** 2)))
    mae = float(np.mean(np.abs(val_pred - y_val.values)))

    info = {
        "rows_train": int(len(train_df)),
        "rows_val": int(len(val_df)),
        "rmse_val": rmse,
        "mae_val": mae,
        "feature_cols": feature_cols,
        "cat_cols": cat_cols,
        "train_end": train_end,
        "val_end": val_end,
    }
    return model, info


def _build_last_state(df: pd.DataFrame, cfg: Config, store_id, sku_id) -> pd.DataFrame:
    """Return the latest rows for a specific series to generate future features iteratively."""
    sdf = df[(df[cfg.store_col] == store_id) & (df[cfg.sku_col] == sku_id)].copy()
    sdf = _ensure_datetime(sdf, cfg.date_col).sort_values(cfg.date_col)
    if len(sdf) < max(cfg.lags) + max(cfg.roll_windows) + 5:
        raise ValueError("Not enough history for this SKU/Store to forecast. Need more rows.")
    return sdf


def forecast_next_n(
    df: pd.DataFrame,
    cfg: Config,
    model: CatBoostRegressor,
    feature_cols: List[str],
    cat_cols: List[str],
    store_id,
    sku_id,
    n_days: int = 14,
) -> pd.DataFrame:
    """
    Iterative one-step forecasting for next n days.
    Assumes model trained for horizon=1.
    """
    if cfg.horizon != 1:
        raise ValueError("This simple iterative forecast expects cfg.horizon=1")

    sdf = _build_last_state(df, cfg, store_id, sku_id)

    # Keep only needed columns
    base_cols = [cfg.date_col, cfg.store_col, cfg.sku_col, cfg.target_col]
    if cfg.promo_col and cfg.promo_col in df.columns:
        base_cols.append(cfg.promo_col)
    if cfg.price_col and cfg.price_col in df.columns:
        base_cols.append(cfg.price_col)

    sdf = sdf[base_cols].copy()

    last_date = sdf[cfg.date_col].max()
    preds = []

    # We will append predicted "sales" as if it happened (for lags/rolling)
    for step in range(1, n_days + 1):
        future_date = last_date + pd.Timedelta(days=step)

        # Create a temp frame including a placeholder row for the future date
        tmp = pd.concat(
            [sdf, pd.DataFrame([{
                cfg.date_col: future_date,
                cfg.store_col: store_id,
                cfg.sku_col: sku_id,
                cfg.target_col: np.nan,  # unknown
                **({cfg.promo_col: 0} if cfg.promo_col and cfg.promo_col in sdf.columns else {}),
                **({cfg.price_col: sdf[cfg.price_col].iloc[-1]} if cfg.price_col and cfg.price_col in sdf.columns else {}),
            }])],
            ignore_index=True
        )

        # Build features for all rows and take the last row only
        df_feat, _, _ = make_features(tmp, cfg)  # will dropna, so future row won't appear
        # Trick: compute features manually for the future row
        # We'll compute directly from sdf (history) to avoid dropna removal.

        # Calendar
        dow = int(pd.to_datetime(future_date).dayofweek)
        month = int(pd.to_datetime(future_date).month)
        weekofyear = int(pd.to_datetime(future_date).isocalendar().week)
        is_weekend = int(dow >= 5)

        # Lags from latest known/predicted sales history
        sales_hist = sdf[cfg.target_col].astype(float).values

        feat = {
            cfg.store_col: store_id,
            cfg.sku_col: sku_id,
            "dow": dow,
            "month": month,
            "weekofyear": weekofyear,
            "is_weekend": is_weekend,
        }

        for l in cfg.lags:
            feat[f"lag_{l}"] = float(sales_hist[-l])

        for w in cfg.roll_windows:
            window = sales_hist[-w:]
            feat[f"rmean_{w}"] = float(np.mean(window))
            feat[f"rstd_{w}"] = float(np.std(window, ddof=1)) if len(window) > 1 else 0.0

        if cfg.promo_col and cfg.promo_col in sdf.columns:
            feat[cfg.promo_col] = 0  # default future promo = 0 (ปรับได้ในแอป)
        if cfg.price_col and cfg.price_col in sdf.columns:
            feat[cfg.price_col] = float(sdf[cfg.price_col].iloc[-1])

        X_one = pd.DataFrame([feat])[feature_cols]
        yhat = float(model.predict(X_one)[0])

        preds.append({"date": future_date, "forecast": max(0.0, yhat)})

        # append predicted as new "sales" point for next iteration
        sdf = pd.concat(
            [sdf, pd.DataFrame([{
                cfg.date_col: future_date,
                cfg.store_col: store_id,
                cfg.sku_col: sku_id,
                cfg.target_col: max(0.0, yhat),
                **({cfg.promo_col: 0} if cfg.promo_col and cfg.promo_col in sdf.columns else {}),
                **({cfg.price_col: sdf[cfg.price_col].iloc[-1]} if cfg.price_col and cfg.price_col in sdf.columns else {}),
            }])],
            ignore_index=True
        )

    return pd.DataFrame(preds)
