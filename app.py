import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import date

st.set_page_config(
    page_title="Supply Chain Stockout Risk Pipeline",
    page_icon="📦",
    layout="wide"
)

st.title("📦 Supply Chain Stockout Risk Pipeline")
st.caption("Interactive simulation of daily demand, inventory, purchase orders, and supplier disruption risk.")

st.markdown(
    """
    This demo simulates a year of operations across **40 SKUs × 4 warehouses × 10 suppliers**,
    including a **supplier disruption event** and stockout-risk analytics.
    """
)

st.sidebar.header("Simulation Controls")
seed = st.sidebar.number_input("Random Seed", min_value=1, max_value=99999, value=42, step=1)
days = st.sidebar.slider("Simulation Horizon (days)", min_value=30, max_value=730, value=365, step=5)
n_skus = st.sidebar.slider("Number of SKUs", min_value=5, max_value=100, value=40, step=5)
n_wh = st.sidebar.slider("Warehouses", min_value=1, max_value=10, value=4, step=1)
n_sup = st.sidebar.slider("Suppliers", min_value=2, max_value=25, value=10, step=1)
service_level_target = st.sidebar.slider("Service Level Target", 0.80, 0.999, 0.95, 0.001)
base_lead = st.sidebar.slider("Base Lead Time (days)", 1, 30, 7, 1)

st.sidebar.markdown("---")
st.sidebar.subheader("Disruption Event")
enable_disruption = st.sidebar.toggle("Enable Supplier Disruption", value=True)
disruption_day = st.sidebar.slider("Disruption Start Day", min_value=1, max_value=days, value=min(180, days), step=1)
disruption_len = st.sidebar.slider("Disruption Length (days)", min_value=1, max_value=90, value=21, step=1)
disruption_severity = st.sidebar.slider("Severity (supply capacity drop)", min_value=0.1, max_value=1.0, value=0.6, step=0.05)
affected_supplier_idx = st.sidebar.slider("Affected Supplier Index", min_value=1, max_value=n_sup, value=min(3, n_sup), step=1)

run = st.sidebar.button("🚀 Run Simulation", type="primary")

def simulate(seed, days, n_skus, n_wh, n_sup, base_lead, service_level_target,
             enable_disruption, disruption_day, disruption_len, disruption_severity, affected_supplier_idx):
    rng = np.random.default_rng(seed)

    skus = [f"SKU-{i:03d}" for i in range(1, n_skus + 1)]
    warehouses = [f"WH-{i}" for i in range(1, n_wh + 1)]
    suppliers = [f"SUP-{i:02d}" for i in range(1, n_sup + 1)]
    affected_supplier = suppliers[affected_supplier_idx - 1]

    avg_daily_demand = rng.integers(8, 80, size=n_skus)
    demand_volatility = rng.uniform(0.15, 0.6, size=n_skus)
    unit_cost = rng.uniform(5, 200, size=n_skus)
    lead_time = rng.integers(max(1, base_lead - 3), base_lead + 8, size=n_skus)
    primary_supplier = rng.choice(suppliers, size=n_skus)

    records = []
    po_records = []

    index = pd.MultiIndex.from_product([skus, warehouses], names=["sku", "warehouse"])
    state = pd.DataFrame(index=index).reset_index()
    state["on_hand"] = np.maximum(30, rng.normal(200, 60, size=len(state))).astype(int)
    state["backorder"] = 0
    state["in_transit"] = 0

    sku_df = pd.DataFrame({
        "sku": skus,
        "avg_daily_demand": avg_daily_demand,
        "demand_volatility": demand_volatility,
        "unit_cost": unit_cost,
        "lead_time": lead_time,
        "supplier": primary_supplier
    })
    z = 1.65 if service_level_target <= 0.95 else 2.05
    sku_df["safety_stock"] = (z * sku_df["demand_volatility"] * sku_df["avg_daily_demand"] * np.sqrt(sku_df["lead_time"])).astype(int)
    sku_df["reorder_point"] = (sku_df["avg_daily_demand"] * sku_df["lead_time"] + sku_df["safety_stock"]).astype(int)
    sku_df["order_qty"] = (sku_df["avg_daily_demand"] * 14).astype(int)

    open_pos = []

    for d in range(1, days + 1):
        still_open = []
        for po in open_pos:
            if po["eta_day"] == d:
                mask = (state["sku"] == po["sku"]) & (state["warehouse"] == po["warehouse"])
                state.loc[mask, "on_hand"] += po["qty"]
                state.loc[mask, "in_transit"] -= po["qty"]
                po["received"] = 1
            else:
                still_open.append(po)
        open_pos = still_open

        for i, row in state.iterrows():
            sku = row["sku"]
            wh = row["warehouse"]
            m = sku_df[sku_df["sku"] == sku].iloc[0]

            mean = m["avg_daily_demand"]
            sd = max(1, int(mean * m["demand_volatility"]))
            demand = max(0, int(rng.normal(mean, sd)))

            on_hand = int(state.at[i, "on_hand"])
            fulfilled = min(on_hand, demand)
            stockout = int(demand > on_hand)
            lost_sales = max(0, demand - on_hand)

            state.at[i, "on_hand"] = on_hand - fulfilled
            state.at[i, "backorder"] += lost_sales

            inv_position = state.at[i, "on_hand"] + state.at[i, "in_transit"] - state.at[i, "backorder"]

            if inv_position <= int(m["reorder_point"]):
                qty = int(m["order_qty"])
                supplier = m["supplier"]
                lt = int(m["lead_time"])

                disrupted = (
                    enable_disruption
                    and supplier == affected_supplier
                    and disruption_day <= d < disruption_day + disruption_len
                )
                if disrupted:
                    qty = int(qty * (1.0 - disruption_severity))
                    lt = int(np.ceil(lt * 1.8))

                qty = max(0, qty)
                eta = d + max(1, lt)

                if qty > 0:
                    open_pos.append({
                        "day": d,
                        "eta_day": eta,
                        "sku": sku,
                        "warehouse": wh,
                        "supplier": supplier,
                        "qty": qty,
                        "received": 0,
                        "disrupted": int(disrupted)
                    })
                    state.at[i, "in_transit"] += qty

                    po_records.append({
                        "day": d,
                        "eta_day": eta,
                        "sku": sku,
                        "warehouse": wh,
                        "supplier": supplier,
                        "qty": qty,
                        "disrupted": int(disrupted)
                    })

            records.append({
                "day": d,
                "sku": sku,
                "warehouse": wh,
                "supplier": m["supplier"],
                "demand": demand,
                "fulfilled": fulfilled,
                "lost_sales": lost_sales,
                "stockout": stockout,
                "on_hand_end": int(state.at[i, "on_hand"]),
                "in_transit": int(state.at[i, "in_transit"]),
                "backorder": int(state.at[i, "backorder"]),
                "inventory_value": float(state.at[i, "on_hand"] * m["unit_cost"])
            })

    df = pd.DataFrame(records)
    po_df = pd.DataFrame(po_records) if len(po_records) else pd.DataFrame(
        columns=["day", "eta_day", "sku", "warehouse", "supplier", "qty", "disrupted"]
    )

    total_demand = df["demand"].sum()
    total_fulfilled = df["fulfilled"].sum()
    fill_rate = (total_fulfilled / total_demand) if total_demand > 0 else 0
    stockout_days = df[df["stockout"] == 1].shape[0]
    total_lost_sales = df["lost_sales"].sum()
    avg_inventory_value = df.groupby("day")["inventory_value"].sum().mean()

    kpis = {
        "Total Demand": int(total_demand),
        "Total Fulfilled": int(total_fulfilled),
        "Fill Rate": float(fill_rate),
        "Stockout Incidents": int(stockout_days),
        "Lost Sales Units": int(total_lost_sales),
        "Avg Daily Inventory Value": float(avg_inventory_value),
        "Affected Supplier": affected_supplier if enable_disruption else "None"
    }

    return df, po_df, kpis


if run:
    with st.spinner("Running simulation..."):
        df, po_df, kpis = simulate(
            seed, days, n_skus, n_wh, n_sup, base_lead, service_level_target,
            enable_disruption, disruption_day, disruption_len, disruption_severity, affected_supplier_idx
        )

    st.success("Simulation complete ✅")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fill Rate", f"{kpis['Fill Rate']:.2%}")
    c2.metric("Stockout Incidents", f"{kpis['Stockout Incidents']:,}")
    c3.metric("Lost Sales Units", f"{kpis['Lost Sales Units']:,}")
    c4.metric("Avg Daily Inventory Value", f"${kpis['Avg Daily Inventory Value']:,.0f}")

    c5, c6 = st.columns(2)
    c5.info(f"**Affected Supplier:** {kpis['Affected Supplier']}")
    c6.info(f"**Total Demand:** {kpis['Total Demand']:,} | **Total Fulfilled:** {kpis['Total Fulfilled']:,}")

    daily = df.groupby("day", as_index=False).agg(
        demand=("demand", "sum"),
        fulfilled=("fulfilled", "sum"),
        lost_sales=("lost_sales", "sum"),
        inventory_value=("inventory_value", "sum"),
        stockout=("stockout", "sum")
    )

    st.subheader("Demand vs Fulfillment")
    fig1 = px.line(daily, x="day", y=["demand", "fulfilled", "lost_sales"], template="plotly_white")
    if enable_disruption:
        fig1.add_vrect(x0=disruption_day, x1=min(days, disruption_day + disruption_len), fillcolor="red", opacity=0.15, line_width=0)
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("Inventory Value Over Time")
    fig2 = px.area(daily, x="day", y="inventory_value", template="plotly_white")
    if enable_disruption:
        fig2.add_vrect(x0=disruption_day, x1=min(days, disruption_day + disruption_len), fillcolor="red", opacity=0.15, line_width=0)
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Top 15 SKUs by Lost Sales")
    top_skus = df.groupby("sku", as_index=False)["lost_sales"].sum().sort_values("lost_sales", ascending=False).head(15)
    fig3 = px.bar(top_skus, x="sku", y="lost_sales", template="plotly_white")
    st.plotly_chart(fig3, use_container_width=True)

    st.subheader("Warehouse Risk Heatmap")
    wh_risk = df.groupby(["warehouse", "sku"], as_index=False)["stockout"].sum()
    pivot = wh_risk.pivot(index="warehouse", columns="sku", values="stockout").fillna(0)
    fig4 = px.imshow(pivot, aspect="auto", color_continuous_scale="Reds")
    st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Purchase Orders")
    if len(po_df):
        st.dataframe(po_df.sort_values(["day", "sku", "warehouse"]), use_container_width=True, height=300)
    else:
        st.warning("No purchase orders generated with current parameters.")

    st.subheader("Raw Simulation Data")
    st.dataframe(df, use_container_width=True, height=350)

    st.download_button(
        "⬇️ Download simulation data (CSV)",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"supply_chain_simulation_{date.today().isoformat()}.csv",
        mime="text/csv"
    )

    st.download_button(
        "⬇️ Download purchase orders (CSV)",
        data=po_df.to_csv(index=False).encode("utf-8"),
        file_name=f"purchase_orders_{date.today().isoformat()}.csv",
        mime="text/csv"
    )

else:
    st.info("Set parameters in the sidebar and click **Run Simulation**.")
