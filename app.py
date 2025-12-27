import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from catboost import CatBoostRegressor
from ml import Config, train_catboost, forecast_next_n


st.set_page_config(page_title="Grocery Demand Forecast (CatBoost)", layout="wide")
st.title("🛒 Grocery Demand Forecast App (CatBoost)")

st.write("อัปโหลดข้อมูลยอดขาย → Train CatBoost → Forecast ต่อไปอีก N วัน")

# -----------------------------
# Sidebar: Upload + Column mapping
# -----------------------------
st.sidebar.header("1) Upload CSV")
uploaded = st.sidebar.file_uploader("Upload CSV file", type=["csv"])

st.sidebar.header("2) Column Mapping")
date_col = st.sidebar.text_input("date column", value="date")
store_col = st.sidebar.text_input("store_id column", value="store_id")
sku_col = st.sidebar.text_input("sku_id column", value="sku_id")
target_col = st.sidebar.text_input("sales column", value="sales")
promo_col = st.sidebar.text_input("promo column (optional)", value="promo")
price_col = st.sidebar.text_input("price column (optional)", value="price")

st.sidebar.header("3) Train/Val Split")
train_end = st.sidebar.text_input("Train end date (YYYY-MM-DD)", value="2025-10-31")
val_end = st.sidebar.text_input("Val end date (YYYY-MM-DD)", value="2025-11-30")

st.sidebar.header("4) Model Settings")
iterations = st.sidebar.number_input("iterations", min_value=200, max_value=5000, value=2000, step=100)
depth = st.sidebar.number_input("depth", min_value=4, max_value=12, value=8, step=1)
learning_rate = st.sidebar.number_input("learning_rate", min_value=0.001, max_value=0.5, value=0.05, step=0.01, format="%.3f")

st.sidebar.header("5) Forecast Settings")
n_days = st.sidebar.number_input("forecast days", min_value=1, max_value=60, value=14, step=1)

# -----------------------------
# Session state
# -----------------------------
if "model" not in st.session_state:
    st.session_state.model = None
if "model_info" not in st.session_state:
    st.session_state.model_info = None
if "df" not in st.session_state:
    st.session_state.df = None


def load_data(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    return df


if uploaded is None:
    st.info("อัปโหลด CSV ก่อน แล้วค่อย Train/Forecast")
    st.stop()

df = load_data(uploaded)
st.session_state.df = df

st.subheader("Preview Data")
st.dataframe(df.head(50), use_container_width=True)

# Validate columns
required = [date_col, store_col, sku_col, target_col]
missing = [c for c in required if c not in df.columns]
if missing:
    st.error(f"Missing required columns: {missing}")
    st.stop()

# Optional columns if exist
promo_col_use = promo_col if promo_col in df.columns and promo_col.strip() != "" else None
price_col_use = price_col if price_col in df.columns and price_col.strip() != "" else None

cfg = Config(
    date_col=date_col,
    store_col=store_col,
    sku_col=sku_col,
    target_col=target_col,
    promo_col=promo_col_use,
    price_col=price_col_use,
    horizon=1,
    iterations=int(iterations),
    depth=int(depth),
    learning_rate=float(learning_rate),
)

# -----------------------------
# Train button
# -----------------------------
colA, colB, colC = st.columns([1,1,1])

with colA:
    if st.button("🚀 Train CatBoost", type="primary"):
        with st.spinner("Training..."):
            model, info = train_catboost(df, cfg, train_end=train_end, val_end=val_end)
            st.session_state.model = model
            st.session_state.model_info = info
        st.success("Training complete!")

with colB:
    if st.button("💾 Save model to model.cbm"):
        if st.session_state.model is None:
            st.warning("Train model ก่อน")
        else:
            st.session_state.model.save_model("model.cbm")
            st.success("Saved: model.cbm")

with colC:
    if st.button("📦 Load model from model.cbm"):
        try:
            m = CatBoostRegressor()
            m.load_model("model.cbm")
            st.session_state.model = m
            st.success("Loaded model.cbm (note: feature list comes from last training config)")
        except Exception as e:
            st.error(f"Load failed: {e}")

# Show training info
if st.session_state.model_info:
    st.subheader("Training Info")
    st.json(st.session_state.model_info)

# Need model and feature cols for forecasting
if st.session_state.model is None or st.session_state.model_info is None:
    st.warning("กด Train ก่อนเพื่อ Forecast (หรือ Load model แล้ว Train อย่างน้อยครั้งนึงเพื่อรู้ feature list)")
    st.stop()

feature_cols = st.session_state.model_info["feature_cols"]
cat_cols = st.session_state.model_info["cat_cols"]
model = st.session_state.model

# -----------------------------
# Choose series
# -----------------------------
st.subheader("Select Store / SKU")
store_values = df[store_col].dropna().unique().tolist()
sku_values = df[sku_col].dropna().unique().tolist()

sel_store = st.selectbox("Store", store_values, index=0)
# filter SKU options by store for convenience
df_store = df[df[store_col] == sel_store]
sku_values2 = df_store[sku_col].dropna().unique().tolist()
sel_sku = st.selectbox("SKU", sku_values2 if len(sku_values2) else sku_values, index=0)

# Plot history
hist = df_store[df_store[sku_col] == sel_sku].copy()
hist[date_col] = pd.to_datetime(hist[date_col])
hist = hist.sort_values(date_col)

st.subheader("History")
fig = plt.figure()
plt.plot(hist[date_col], hist[target_col])
plt.xlabel("date")
plt.ylabel("sales")
st.pyplot(fig)

# -----------------------------
# Forecast
# -----------------------------
if st.button("📈 Forecast", type="primary"):
    try:
        fc = forecast_next_n(
            df=df,
            cfg=cfg,
            model=model,
            feature_cols=feature_cols,
            cat_cols=cat_cols,
            store_id=sel_store,
            sku_id=sel_sku,
            n_days=int(n_days),
        )

        st.subheader("Forecast Result")
        st.dataframe(fc, use_container_width=True)

        # plot
        fig2 = plt.figure()
        plt.plot(hist[date_col], hist[target_col], label="actual")
        plt.plot(fc["date"], fc["forecast"], label="forecast")
        plt.xlabel("date")
        plt.ylabel("sales")
        plt.legend()
        st.pyplot(fig2)

        # download
        csv_bytes = fc.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download forecast.csv",
            data=csv_bytes,
            file_name="forecast.csv",
            mime="text/csv",
        )
    except Exception as e:
        st.error(f"Forecast failed: {e}")
        st.info("ทิป: ถ้า error บอกว่า history ไม่พอ ให้เลือก SKU/Store ที่มีข้อมูลยาวขึ้น หรือเพิ่มข้อมูลย้อนหลัง")
