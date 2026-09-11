import streamlit as st
import pandas as pd
import json
from pathlib import Path

from valuation_core import get_inputs, compute_valuation

# ---------- Configuration ----------
st.set_page_config(page_title="Land Bid Feasibility", layout="wide")

# ---------- Project Persistence (Save / Load) ----------
PROJECTS_FILE = Path(__file__).parent / "saved_projects.json"

# Every input widget key this page controls (must match the keys below)
INPUT_KEYS = [
    "gfa", "efficiency", "asp",
    "bid_price", "const_cost", "prof_fee", "sm_fee",
    "interest", "land_loan_period", "const_loan_period",
    "land_ltv_pct", "const_ltv_pct",
]
# Keys whose text boxes use 2-decimal float formatting
FLOAT_KEYS = {"efficiency", "interest", "land_loan_period", "const_loan_period"}


def load_projects():
    """Read all saved bidding projects from disk."""
    if PROJECTS_FILE.exists():
        try:
            data = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_projects(projects):
    """Write all bidding projects to disk."""
    PROJECTS_FILE.write_text(json.dumps(projects, indent=2), encoding="utf-8")


def apply_project_to_state(project_inputs):
    """Push a saved project's values into session_state.
    Must run BEFORE any widget using these keys is created."""
    for k in INPUT_KEYS:
        if k in project_inputs and project_inputs[k] is not None:
            v = project_inputs[k]
            st.session_state[k] = v
            if k in FLOAT_KEYS:
                st.session_state[f"{k}_txt"] = f"{v:,.2f}"
            else:
                st.session_state[f"{k}_txt"] = f"{int(v):,}"

# --- Custom Helper Function for Synced Slider & TEXT Box (With Commas!) ---
def sync_slider_input(label, min_val, max_val, default_val, step, key, is_float=False):
    # 1. Initialize states safely (Catching None values)
    if st.session_state.get(key) is None:
        st.session_state[key] = default_val

    if st.session_state.get(f"{key}_txt") is None:
        if is_float:
            st.session_state[f"{key}_txt"] = f"{default_val:,.2f}"
        else:
            st.session_state[f"{key}_txt"] = f"{default_val:,}"

    # 2. Callback: Slider to Text Box
    def update_from_slider():
        val = st.session_state.get(key, default_val)
        if val is None: val = default_val
        if is_float:
            st.session_state[f"{key}_txt"] = f"{val:,.2f}"
        else:
            st.session_state[f"{key}_txt"] = f"{int(val):,}"

    # 3. Callback: Text Box to Slider
    def update_from_txt():
        raw_str = st.session_state.get(f"{key}_txt", "")

        # SAFETY NET 1: If the user deleted everything, reset to default instantly
        if not raw_str or str(raw_str).strip() == "":
            st.session_state[key] = default_val
            st.session_state[f"{key}_txt"] = f"{default_val:,.2f}" if is_float else f"{default_val:,}"
            return

        # Remove commas so python can read it as a number
        clean_str = str(raw_str).replace(",", "").replace(" ", "")

        try:
            val = float(clean_str) if is_float else int(clean_str)
            val = max(min_val, min(val, max_val))  # Enforce limits
            st.session_state[key] = val

            # Reformat the text box so it instantly looks pretty again
            if is_float:
                st.session_state[f"{key}_txt"] = f"{val:,.2f}"
            else:
                st.session_state[f"{key}_txt"] = f"{int(val):,}"
        except ValueError:
            # SAFETY NET 2: Revert to last known safe number if they typed letters
            val = st.session_state.get(key, default_val)
            if val is None: val = default_val
            if is_float:
                st.session_state[f"{key}_txt"] = f"{val:,.2f}"
            else:
                st.session_state[f"{key}_txt"] = f"{int(val):,}"

    st.markdown(f"<span style='font-size: 14px; font-weight: 600;'>{label}</span>", unsafe_allow_html=True)
    col_slide, col_box = st.columns([3, 1])

    with col_slide:
        st.slider(
            label, min_value=min_val, max_value=max_val, step=step,
            key=key, on_change=update_from_slider, label_visibility="collapsed"
        )
    with col_box:
        st.text_input(
            label, key=f"{key}_txt", on_change=update_from_txt, label_visibility="collapsed"
        )

    # 4. Safely return the final value, guaranteeing it is NEVER None
    final_val = st.session_state.get(key)
    if final_val is None:
        final_val = default_val
    return final_val


def main():
    # --- Apply a queued project Load FIRST (before any widget is created) ---
    if st.session_state.get("_pending_koad"):
        apply_project_to_state(st.session_state.pop("_pending_load"))

    # --- Custom CSS for layout spacing ---
    st.markdown("""
        <style>
        .stMetric { text-align: center; }
        hr { margin-top: 10px !important; margin-bottom: 20px !important; }
        </style>
    """, unsafe_allow_html=True)

    # --- Header ---
    st.title("Land Valuation Model: Bid Price Feasibility")
    st.caption("Based on the HKIS Residual Method of Valuation — enter your land bid "
               "and the model solves for the implied developer's profit. "
               "Results feed the ROI Projection page.")

    results_container = st.container()
    st.divider()

    # --- Inputs Layout ---
    col_revenue, col_costs, col_finance = st.columns(3)

    with col_revenue:
        st.subheader("Scale & Revenue")
        sync_slider_input("Total GFA (sq ft)", 0, 1_000_000, 500_000, 100_000, "gfa")
        sync_slider_input("Efficiency (%)", 0.0, 100.0, 90.0, 0.1, "efficiency", is_float=True)
        sync_slider_input("Average Selling Price ($/sf SFA)", 0, 100_000, 20000, 100, "asp")

    with col_costs:
        st.subheader("Development Costs")
        sync_slider_input("Land Bid Price (HKD)", 0, 10_000_000_000, 2_800_000_000,
                          100_000_000, "bid_price")
        sync_slider_input("Construction Cost ($/sf GFA)", 0, 20_000, 5000, 100, "const_cost")
        sync_slider_input("Professional Fees (%)", 0, 15, 4, 1, "prof_fee")
        sync_slider_input("Sales & Marketing (%)", 0, 15, 6, 1, "sm_fee")

    with col_finance:
        st.subheader("Financing")
        sync_slider_input("Interest Rate (%)", 0.0, 15.0, 5.0, 0.1, "interest", is_float=True)

        st.markdown("<br>", unsafe_allow_html=True)  # visual spacing

        # Split Loan Periods
        sync_slider_input("Interest Period for Land (Years)", 0.0, 10.0, 5.0, 0.5,
                          "land_loan_period", is_float=True)
        sync_slider_input("Interest Period for Construction (Years)", 0.0, 10.0, 4.0, 0.5,
                          "const_loan_period", is_float=True)

        st.markdown("<br>", unsafe_allow_html=True)  # visual spacing

        # Updated LTV terminology
        sync_slider_input("Loan-to-Value for Land (%)", 0, 100, 80, 1, "land_ltv_pct")
        sync_slider_input("Loan-to-Value for Construction (%)", 0, 100, 100, 1, "const_ltv_pct")

    # --- Shared Calculation (same engine the ROI page uses) ---
    inputs = get_inputs(st.session_state)
    res = compute_valuation(inputs)

    # --- Sidebar: Bidding Projects (Save / Load / Delete) ---
    with st.sidebar:
        st.header("📁 Bidding Projects")
        projects = load_projects()

        #1) Save current inputs under a project name
        save_name = st.text_input("Project name", key="save_project_name", placeholder="e.g. KT Site")

        if st.button("💾 Save current project", use_container_width=True):
            name = save_name.strip()
            if not name:
                st.warning("Enter a project name first.")
            else:
                projects[name] = {k: inputs.get(k) for k in INPUT_KEYS}
                save_projects(projects)
                st.success(f"Saved"{name}".")

        st.divider()

        #2) Load or delete a saved project
        if projects:
            selected = st.selectbox("Saved projects", list(projects.key()), key="selected_project")
            load_col, del_col = st.columns(2)
            with load_col:
                if st.button("📂 Load", use_continer_width=True):
                    st.session_state["_pending_load"]=projects[selected]
                    st.rerun()
            with del_col:
                if st.button("🗑 Delete", use_container_width=True):
                    del projects[selected]
                    save_projects(projects)
                    st.rerun()
        else: 
            st.info("No saved project yet.")

    # Unpack for display
    gfa = inputs["gfa"]
    efficiency_pct = inputs["efficiency"]
    asp = inputs["asp"]
    unit_const_cost = inputs["const_cost"]
    prof_fee_pct = inputs["prof_fee"]
    sm_fee_pct = inputs["sm_fee"]
    bid_price = inputs["bid_price"]
    interest_rate_pct = inputs["interest"]
    land_loan_period = inputs["land_loan_period"]
    const_loan_period = inputs["const_loan_period"]
    land_ltv_pct = inputs["land_ltv_pct"]
    const_ltv_pct = inputs["const_ltv_pct"]

    sfa = res["sfa"]
    gdv = res["gdv"]
    const_cost = res["const_cost"]
    prof_fee = res["prof_fee"]
    sm_fee = res["sm_fee"]
    dev_profit = res["dev_profit"]
    dev_profit_pct = res["dev_profit_pct"]
    const_interest = res["const_interest"]
    land_interest = res["land_interest"]
    total_costs = res["total_costs"]
    accommodation_value = res["accommodation_value"]

    # --- Publish results so the ROI Projection page stays in sync ---
    st.session_state["valuation_results"] = res
    st.session_state["valuation_inputs"] = inputs

    # --- CSV Export Setup ---
    export_data = {
        "Total GFA (sq ft)": [gfa],
        "Efficiency (%)": [efficiency_pct],
        "Average Selling Price ($/sf SFA)": [asp],
        "Land Bid Price (HKD)": [bid_price],
        "Construction Cost ($/sf GFA)": [unit_const_cost],
        "Professional Fees (%)": [prof_fee_pct],
        "Sales & Marketing (%)": [sm_fee_pct],
        "Interest Rate (%)": [interest_rate_pct],
        "Interest Period for Land (Years)": [land_loan_period],
        "Interest Period for Construction (Years)": [const_loan_period],
        "Loan-to-Value for Land (%)": [land_ltv_pct],
        "Loan-to-Value for Construction (%)": [const_ltv_pct],
        "Gross Development Value (HKD)": [gdv],
        "Total Development Costs (HKD)": [total_costs],
        "Developer's Profit (HKD)": [dev_profit],
        "Developer's Profit (% of GDV)": [dev_profit_pct],
        "Land Price per sf GFA (HKD)": [accommodation_value]
    }

    df_export = pd.DataFrame(export_data)
    csv_file = df_export.to_csv(index=False).encode('utf-8')

    # --- Fill the Top Container with our Results & Download Button ---
    with results_container:
        header_col, btn_col = st.columns([4, 1])
        with header_col:
            st.subheader("Feasibility Results")
        with btn_col:
            st.write("")  # Spacing to align button
            st.download_button(
                label="📥 Download CSV",
                data=csv_file,
                file_name="bid_feasibility_model.csv",
                mime="text/csv",
                use_container_width=True
            )

        # Back to 3 columns so the numbers don't truncate
        res_col1, res_col2, res_col3 = st.columns(3)

        with res_col1:
            st.metric(label="Gross Development Value", value=f"HKD {gdv:,.0f}")
        with res_col2:
            st.metric(label="Total Development Costs", value=f"HKD {total_costs:,.0f}",
                      delta="incl. land bid & interest", delta_color="off")
        with res_col3:
            # Stack the values vertically — profit is the variable being solved for
            st.metric(label="Implied Developer's Profit", value=f"HKD {dev_profit:,.0f}",
                      delta=f"{dev_profit_pct:,.1f}% of GDV",
                      delta_color="normal" if dev_profit >= 0 else "inverse")
            st.write("")  # small gap
            st.metric(label="Land Price per sf GFA", value=f"HKD {accommodation_value:,.0f}/sf")


        st.write("")  # Adds a small visual gap
        with st.expander("🔍 View Calculation Breakdown"):
            st.write("### Constituent Components")
            st.markdown("---")

            exp_col1, exp_col2 = st.columns(2)

            with exp_col1:
                st.markdown("#### Gross Development Value (GDV)")
                st.markdown(f"""
                        * **Total GFA:** {gfa:,.0f} sq ft
                        * **Efficiency:** {efficiency_pct:,.2f}%
                        * **Saleable Floor Area (SFA):** {sfa:,.0f} sq ft
                        * **Average Selling Price (ASP):** HKD {asp:,.0f} / sf

                        **Total GDV = HKD {gdv:,.0f}**
                        """)

            with exp_col2:
                st.markdown("#### Total Development Costs")
                st.markdown(f"""
                        * **Land Bid Price:** HKD {bid_price:,.0f}
                        * **Construction Cost:** HKD {const_cost:,.0f}
                        * **Professional Fees:** HKD {prof_fee:,.0f}
                        * **Sales & Marketing:** HKD {sm_fee:,.0f}
                        * **Construction Interest:** HKD {const_interest:,.0f}
                        * **Land Interest:** HKD {land_interest:,.0f}

                        **Total Costs = HKD {total_costs:,.0f}**

                        ---

                        **Implied Developer's Profit = GDV − Total Costs
                        = HKD {dev_profit:,.0f} ({dev_profit_pct:,.1f}% of GDV)**
                        """)

        st.info("💡 Head to the **ROI Projection** page in the sidebar — "
                "it reads these same figures automatically.", icon="↗️")

if __name__ == "__main__":
    main()
