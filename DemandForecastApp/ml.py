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

    # บังคับเป็น string + trim ช่องว่าง
    s = out[col].astype(str).str.strip()

    # ลอง parse แบบ dayfirst ก่อน
    dt = pd.to_datetime(s, errors="coerce", dayfirst=True)

    # ถ้ายัง NaT เยอะ ลอง format ที่พบบ่อย
    if dt.notna().sum() == 0:
        dt = pd.to_datetime(s, errors="coerce", format="%d/%m/%Y")
    if dt.notna().sum() == 0:
        dt = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
    if dt.notna().sum() == 0:
        dt = pd.to_datetime(s, errors="coerce", infer_datetime_format=True)

    out[col] = dt
    return out





def make_features(df: pd.DataFrame, cfg: Config) -> Tuple[pd.DataFrame, List[str], List[str]]:
    df = _ensure_datetime(df, cfg.date_col)
    if df[cfg.date_col].notna().sum() == 0:
        raise ValueError(f"All values in '{cfg.date_col}' failed to parse as datetime. "
                 f"Example raw values: {df[cfg.date_col].astype(str).head(5).tolist()}")


    df = df.sort_values([cfg.store_col, cfg.sku_col, cfg.date_col]).copy()

    # calendar features (SAFE)
    df["dow"] = df[cfg.date_col].dt.dayofweek.astype("Int64")
    df["month"] = df[cfg.date_col].dt.month.astype("Int64")
    df["weekofyear"] = df[cfg.date_col].dt.isocalendar().week.astype("Int64")
    df["is_weekend"] = (df["dow"] >= 5).fillna(False).astype(int)

    grp = df.groupby([cfg.store_col, cfg.sku_col], sort=False)

    # lag features
    for l in cfg.lags:
        df[f"lag_{l}"] = grp[cfg.target_col].shift(l)

    # rolling features (shift 1 to avoid leakage) - ใช้ transform
    for w in cfg.roll_windows:
        df[f"rmean_{w}"] = grp[cfg.target_col].transform(lambda s: s.shift(1).rolling(w).mean())
        df[f"rstd_{w}"]  = grp[cfg.target_col].transform(lambda s: s.shift(1).rolling(w).std())

    # optional exogenous (ถ้าคอลัมน์มี NA เยอะ จะไม่ทำให้ทั้งแถวหายแล้ว)
    extra_cols = []
    if cfg.promo_col and cfg.promo_col in df.columns:
        extra_cols.append(cfg.promo_col)
        df[cfg.promo_col] = pd.to_numeric(df[cfg.promo_col], errors="coerce").fillna(0)

    if cfg.price_col and cfg.price_col in df.columns:
        extra_cols.append(cfg.price_col)
        df[cfg.price_col] = pd.to_numeric(df[cfg.price_col], errors="coerce")
        # เติมด้วย median ต่อ SKU/Store ถ้ามี ไม่งั้นเติม median ทั้งชุด
        df[cfg.price_col] = df.groupby([cfg.store_col, cfg.sku_col])[cfg.price_col].transform(
            lambda s: s.fillna(s.median())
        )
        df[cfg.price_col] = df[cfg.price_col].fillna(df[cfg.price_col].median())

    # target (horizon=1 => y = sales ของวันถัดไป)
    df["y"] = grp[cfg.target_col].shift(-cfg.horizon)

    feature_cols = [
        cfg.store_col, cfg.sku_col,
        "dow", "month", "weekofyear", "is_weekend",
        *[f"lag_{l}" for l in cfg.lags],
        *[f"rmean_{w}" for w in cfg.roll_windows],
        *[f"rstd_{w}" for w in cfg.roll_windows],
        *extra_cols
    ]

    cat_cols = [cfg.store_col, cfg.sku_col, "dow", "month"]

    # ✅ dropna เฉพาะที่ “จำเป็น” ต่อการ train/predict
    required = [cfg.date_col, cfg.target_col, "y"] + feature_cols
    required = [c for c in required if c in df.columns]

    df_feat = df.dropna(subset=required).copy()

    if df_feat.empty:
        warmup = max(max(cfg.lags), max(cfg.roll_windows)) + cfg.horizon + 1
    # เช็คจำนวนวันต่อ (store,sku) แบบเร็ว ๆ
        tmp = df[[cfg.store_col, cfg.sku_col, cfg.date_col]].dropna().copy()
        tmp["__date__"] = pd.to_datetime(tmp[cfg.date_col], errors="coerce", dayfirst=True)
        counts = tmp.dropna(subset=["__date__"]).groupby([cfg.store_col, cfg.sku_col])["__date__"].nunique()
        max_days = int(counts.max()) if len(counts) else 0

    raise ValueError(
        "No rows left after feature generation (df_feat is empty). "
        f"Likely not enough history per (store, sku) to build lags/rolling + target.\n"
        f"Need at least ~{warmup} unique days per series, but max found is {max_days}.\n"
        "Fix options:\n"
        "1) Provide more historical dates per store+sku, OR\n"
        "2) Reduce lags/roll_windows in Config (e.g., lags=(1,7), roll_windows=(7,))."
    )

    

    return df_feat, feature_cols, cat_cols


def time_split(df_feat: pd.DataFrame, cfg: Config, train_end: str, val_end: str):
    # parse input dates (รองรับ dayfirst)
    train_end_dt = pd.to_datetime(train_end, errors="coerce", dayfirst=True)
    val_end_dt   = pd.to_datetime(val_end, errors="coerce", dayfirst=True)

    if pd.isna(train_end_dt) or pd.isna(val_end_dt):
        raise ValueError(f"Invalid train_end/val_end. Got train_end={train_end} val_end={val_end}")

    # data date range
    min_dt = df_feat[cfg.date_col].min()
    max_dt = df_feat[cfg.date_col].max()

    if pd.isna(min_dt) or pd.isna(max_dt):
        raise ValueError(
            f"Date parsing failed: df_feat[{cfg.date_col}] range is NaT -> NaT. "
            f"Check date column name + date format."
        )

    # enforce ordering
    if not (min_dt < train_end_dt < val_end_dt <= max_dt):
        warmup = max(max(cfg.lags), max(cfg.roll_windows)) + cfg.horizon + 2
        uniq_dates = pd.Series(df_feat[cfg.date_col].sort_values().unique())

        if len(uniq_dates) > warmup + 5:
            start_i = warmup
            end_i = len(uniq_dates) - 1
            train_i = start_i + int((end_i - start_i) * 0.8)
            train_end_dt = pd.to_datetime(uniq_dates.iloc[train_i])
            val_end_dt   = pd.to_datetime(uniq_dates.iloc[end_i])
        else:
            train_end_dt = min_dt
            val_end_dt   = max_dt


        raise ValueError(
            f"Your split dates are out of range.\n"
            f"Data range: {min_dt.date()} -> {max_dt.date()}\n"
            f"Given: train_end={train_end_dt.date()}, val_end={val_end_dt.date()}\n"
            f"Suggested: train_end={suggested_train.date()}, val_end={suggested_val.date()}\n"
            f"Tip: choose min_date < train_end < val_end <= max_date."
        )

    train = df_feat[df_feat[cfg.date_col] <= train_end_dt].copy()
    val   = df_feat[(df_feat[cfg.date_col] > train_end_dt) & (df_feat[cfg.date_col] <= val_end_dt)].copy()

    if len(train) == 0 or len(val) == 0:
        raise ValueError(
            f"Split empty after filtering.\n"
            f"Data range: {min_dt.date()} -> {max_dt.date()}\n"
            f"Given: train_end={train_end_dt.date()}, val_end={val_end_dt.date()}\n"
            f"Rows: train={len(train)}, val={len(val)}\n"
            f"Tip: move train_end earlier and val_end later (but still within range)."
        )

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
