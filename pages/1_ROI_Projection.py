import streamlit as st
import pandas as pd
import sys, os

# Make the shared engine importable when Streamlit runs from any cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from valuation_core import get_inputs, compute_valuation, npv, irr, build_cashflows

st.set_page_config(page_title="ROI Projection", layout="wide")


def money(x):
    return f"HKD {x:,.0f}"


def main():
    st.markdown("""
        <style>
        .stMetric { text-align: center; }
        </style>
    """, unsafe_allow_html=True)

    st.title("ROI Projection")
    st.caption("Financial projection interlinked with the Residual Land Valuation page — "
               "change an input there and this page updates automatically.")

    # ---------- Linked figures from Page 1 (or defaults) ----------
    inputs = get_inputs(st.session_state)
    res = st.session_state.get("valuation_results")
    if res is None:
        res = compute_valuation(inputs)

    land_premium   = res["land_price"]         # Estimated land premium (= the bid price input)
    const_cost     = res["const_cost"]         # Estimated construction cost
    prof_fee       = res["prof_fee"]           # Professional fees
    sm_fee         = res["sm_fee"]             # Sales & marketing fees
    bank_interest  = res["bank_interest"]      # Land + construction interest
    flats_proceeds = res["gdv"]                # Sales proceeds from flats
    land_loan      = res["land_loan_amount"]
    const_loan     = res["const_loan_amount"]

    linked = "valuation_results" in st.session_state
    if linked:
        st.success("🔗 Linked to the Residual Valuation page — figures are live.")
    else:
        st.warning("You haven't opened the Residual Valuation page yet in this session, "
                   "so this page is using its default inputs. It will sync automatically "
                   "once you visit Page 1.")

    results_container = st.container()
    st.divider()

    # ---------- Page-specific inputs ----------
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.subheader("Additional Revenue")
        carpark_proceeds = st.number_input(
            "Sales proceeds from carpark (HKD)", min_value=0.0,
            value=st.session_state.get("carpark_proceeds", 0.0),
            step=1_000_000.0, format="%.0f", key="carpark_proceeds_input")
        st.session_state["carpark_proceeds"] = carpark_proceeds
    with col_b:
        st.subheader("Additional Costs")
        other_costs = st.number_input(
            "Other costs (HKD)", min_value=0.0,
            value=st.session_state.get("other_costs", 0.0),
            step=1_000_000.0, format="%.0f", key="other_costs_input")
        st.session_state["other_costs"] = other_costs
    with col_c:
        st.subheader("Discounting")
        discount_rate_pct = st.number_input(
            "Discount rate for NPV (% p.a.)", min_value=0.0, max_value=30.0,
            value=float(inputs["interest"]), step=0.1, format="%.1f",
            key="discount_rate_input")
        st.caption("Defaults to the financing interest rate from Page 1.")

    st.caption("ℹ️ Sales proceeds from flats and the land premium (your bid price) "
               "are taken directly from Page 1. Developer's profit is not listed as a "
               "cost because it IS the result — the gross profit below equals the "
               "implied developer's profit shown on Page 1.")

    # ---------- ROI calculations ----------
    total_dev_cost = (land_premium + const_cost + bank_interest
                      + sm_fee + prof_fee + other_costs)
    total_proceeds = flats_proceeds + carpark_proceeds
    profit = total_proceeds - total_dev_cost
    return_on_cost = profit / total_dev_cost if total_dev_cost > 0 else None

    # Equity actually injected = total cost not covered by bank debt
    debt = land_loan + const_loan
    equity = total_dev_cost - debt
    roe = profit / equity if equity > 0 else None

    # Cash-flow timeline for NPV / IRR
    construction_years = inputs["const_loan_period"]
    cashflows = build_cashflows(
        land_premium=land_premium,
        other_costs=other_costs,
        const_cost=const_cost,
        prof_fee=prof_fee,
        sm_fee=sm_fee,
        bank_interest=bank_interest,
        total_sales_proceeds=total_proceeds,
        construction_years=construction_years,
    )
    project_npv = npv(discount_rate_pct / 100, cashflows)
    project_irr = irr(cashflows)

    # ---------- Financial projection (top of page, per the Word file) ----------
    with results_container:
        st.subheader("Financial Projection")
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Projected NPV", money(project_npv),
                      delta=f"@ {discount_rate_pct:.1f}% p.a.")
        with m2:
            st.metric("Projected IRR",
                      f"{project_irr * 100:,.2f}%" if project_irr is not None else "n/a")
        with m3:
            st.metric("Return on Cost",
                      f"{return_on_cost * 100:,.2f}%" if return_on_cost is not None else "n/a")
        with m4:
            st.metric("ROE (on equity injected)",
                      f"{roe * 100:,.2f}%" if roe is not None else "n/a")

    st.divider()

    # ---------- ROE projection tables (layout per the Word file) ----------
    st.subheader("ROE Projection")
    t1, t2 = st.columns(2)

    with t1:
        st.markdown("#### Development Cost")
        cost_rows = [
            ("Estimated land premium", land_premium, True),
            ("Estimated construction cost", const_cost, True),
            ("Bank loan interest", bank_interest, True),
            ("Sales & marketing fees", sm_fee, True),
            ("Professional fees", prof_fee, True),
            ("Other costs", other_costs, False),
        ]
        df_costs = pd.DataFrame(
            [(label, money(val), "🔗 Page 1" if from_p1 else "This page")
             for label, val, from_p1 in cost_rows]
            + [("**Total development cost**", f"**{money(total_dev_cost)}**", "")],
            columns=["Item", "Amount", "Source"])
        st.dataframe(df_costs, use_container_width=True, hide_index=True)

    with t2:
        st.markdown("#### Sales Proceeds")
        df_proceeds = pd.DataFrame(
            [("Sales proceeds from flats", money(flats_proceeds), "🔗 Page 1 (GDV)"),
             ("Sales proceeds from carpark", money(carpark_proceeds), "This page"),
             ("**Total sales proceeds**", f"**{money(total_proceeds)}**", "")],
            columns=["Item", "Amount", "Source"])
        st.dataframe(df_proceeds, use_container_width=True, hide_index=True)

        st.markdown("#### Return Summary")
        df_ret = pd.DataFrame(
            [("Gross profit", money(profit)),
             ("Return on cost", f"{return_on_cost * 100:,.2f}%" if return_on_cost is not None else "n/a"),
             ("Equity injected (after bank debt)", money(equity)),
             ("ROE (on equity injected)", f"{roe * 100:,.2f}%" if roe is not None else "n/a")],
            columns=["Metric", "Value"])
        st.dataframe(df_ret, use_container_width=True, hide_index=True)

    # ---------- Cash-flow detail behind NPV / IRR ----------
    st.divider()
    with st.expander("🔍 View Cash-Flow Timeline (basis for NPV & IRR)"):
        df_cf = pd.DataFrame(
            [(f"Year {t:g}", amt) for t, amt in cashflows],
            columns=["Timing", "Net Cash Flow (HKD)"])
        df_cf["Net Cash Flow (HKD)"] = df_cf["Net Cash Flow (HKD)"].round(0)
        st.dataframe(df_cf, use_container_width=True, hide_index=True)
        st.bar_chart(df_cf.set_index("Timing"))
        st.caption("Convention: land premium + other costs at t=0; construction cost and "
                   "professional fees spread evenly over the construction period; "
                   "S&M, bank interest and all sales proceeds at completion "
                   f"(year {construction_years:g}).")

    # ---------- CSV export ----------
    export = {
        "Item": ["Estimated land premium", "Estimated construction cost", "Bank loan interest",
                 "Sales & marketing fees", "Professional fees", "Other costs",
                 "Total development cost", "Sales proceeds from flats",
                 "Sales proceeds from carpark", "Total sales proceeds",
                 "Gross profit", "Return on cost (%)", "Equity injected",
                 "ROE (%)", "Discount rate (%)", "Projected NPV", "Projected IRR (%)"],
        "Value": [land_premium, const_cost, bank_interest, sm_fee, prof_fee, other_costs,
                  total_dev_cost, flats_proceeds, carpark_proceeds, total_proceeds,
                  profit,
                  return_on_cost * 100 if return_on_cost is not None else None,
                  equity,
                  roe * 100 if roe is not None else None,
                  discount_rate_pct, project_npv,
                  project_irr * 100 if project_irr is not None else None],
    }
    st.download_button("📥 Download ROI Projection CSV",
                       data=pd.DataFrame(export).to_csv(index=False).encode("utf-8"),
                       file_name="roi_projection.csv", mime="text/csv")


if __name__ == "__main__":
    main()
