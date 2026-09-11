"""
Shared valuation engine for the Residual Land Valuation Streamlit app.

Model direction (v2): the LAND BID PRICE is an input; the model solves for
the implied DEVELOPER'S PROFIT (amount and % of GDV).

This module is deliberately free of any Streamlit imports so that:
  1. Page 1 (Bid Feasibility) and Page 2 (ROI Projection) use the
     EXACT same maths, and
  2. Page 2 can recompute baseline figures from session_state (or from
     DEFAULTS when the user lands on it directly without visiting Page 1).
"""

# ---------- Default inputs (identical to Page 1 defaults) ----------
DEFAULTS = {
    "gfa": 500_000,
    "efficiency": 90.0,
    "asp": 20_000,
    "const_cost": 5_000,          # unit construction cost $/sf GFA
    "prof_fee": 4,                # %
    "sm_fee": 6,                  # %
    "bid_price": 2_800_000_000,   # land bid (HKD) — implies ~25% profit at defaults
    "interest": 5.0,              # %
    "land_loan_period": 5.0,      # years
    "const_loan_period": 4.0,     # years
    "land_ltv_pct": 80,           # %
    "const_ltv_pct": 100,         # %
}


def get_inputs(session_state=None):
    """Return the input dict, preferring live session_state values.

    Falls back to DEFAULTS for any key not yet in session_state (e.g. when
    the user opens Page 2 before touching Page 1).
    """
    inputs = dict(DEFAULTS)
    if session_state is not None:
        for key in inputs:
            val = session_state.get(key)
            if val is not None:
                inputs[key] = val
    return inputs


def compute_valuation(inputs):
    """Run the bid-price feasibility valuation. Returns a dict of figures.

    Given:  GDV, costs, financing terms and a land bid price
    Solve:  developer's profit = GDV - all costs (incl. land bid & interest)
    """
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

    # 1. Areas and Revenue
    sfa = gfa * (efficiency_pct / 100)
    gdv = sfa * asp

    # 2. Hard & Soft Costs
    const_cost = unit_const_cost * gfa
    prof_fee = const_cost * (prof_fee_pct / 100)
    sm_fee = gdv * (sm_fee_pct / 100)

    # 3. Finance
    interest_rate = interest_rate_pct / 100
    land_loan_ratio = land_ltv_pct / 100
    const_loan_ratio = const_ltv_pct / 100

    const_loan_amount = const_cost * const_loan_ratio
    const_interest = const_loan_amount * 0.5 * interest_rate * const_loan_period

    land_loan_amount = bid_price * land_loan_ratio
    land_interest = land_loan_amount * 1.0 * interest_rate * land_loan_period

    # 4. All-in development cost (before developer's profit)
    total_costs = (bid_price + const_cost + prof_fee + sm_fee
                   + const_interest + land_interest)

    # 5. Implied developer's profit (the variable being solved for)
    dev_profit = gdv - total_costs
    dev_profit_pct = (dev_profit / gdv * 100) if gdv > 0 else 0.0

    accommodation_value = bid_price / gfa if gfa > 0 else 0

    return {
        "sfa": sfa,
        "gdv": gdv,
        "const_cost": const_cost,
        "prof_fee": prof_fee,
        "sm_fee": sm_fee,
        "dev_profit": dev_profit,
        "dev_profit_pct": dev_profit_pct,
        "const_interest": const_interest,
        "land_interest": land_interest,
        "bank_interest": const_interest + land_interest,
        "land_price": bid_price,
        "total_costs": total_costs,
        "accommodation_value": accommodation_value,
        "land_loan_amount": land_loan_amount,
        "const_loan_amount": const_loan_amount,
    }


# ---------- Generic finance helpers (used by the ROI page) ----------

def npv(rate, cashflows):
    """NPV of [(time_years, amount), ...] discounted at `rate`."""
    return sum(amount / (1 + rate) ** t for t, amount in cashflows)


def irr(cashflows, low=-0.95, high=10.0, tol=1e-7, max_iter=200):
    """IRR of [(time_years, amount), ...] via bisection.

    Returns None when no sign change exists in the search bracket.
    """
    f_low = npv(low, cashflows)
    f_high = npv(high, cashflows)
    if f_low * f_high > 0:
        return None
    for _ in range(max_iter):
        mid = (low + high) / 2
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid < 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return (low + high) / 2


def build_cashflows(land_premium, other_costs, const_cost, prof_fee,
                    sm_fee, bank_interest, total_sales_proceeds,
                    construction_years):
    """Assemble the project cash-flow timeline.

    Timing convention (simple annual phasing):
      t = 0                 land premium + other costs paid up-front
      end of each year      construction cost + professional fees spread
                            evenly over the construction period
      completion (t = C)    S&M fees, bank loan interest and all sales
                            proceeds
    """
    import math

    C = max(construction_years, 0.0)
    flows = [(0.0, -(land_premium + other_costs))]

    build_cost = const_cost + prof_fee
    if C > 0:
        n_full_years = int(math.floor(C))
        frac = C - n_full_years
        n_tranches = n_full_years + (1 if frac > 1e-9 else 0)
        per_tranche = build_cost / n_tranches
        for i in range(1, n_full_years + 1):
            flows.append((float(i), -per_tranche))
        if frac > 1e-9:
            flows.append((C, -per_tranche))
    else:
        # No construction period: everything happens at t = 0
        flows.append((0.0, -build_cost))

    completion = C if C > 0 else 0.0
    flows.append((completion, -(sm_fee + bank_interest)))
    flows.append((completion, total_sales_proceeds))

    # Merge flows that share the same timestamp
    merged = {}
    for t, amt in flows:
        merged[round(t, 6)] = merged.get(round(t, 6), 0.0) + amt
    return sorted(merged.items())
