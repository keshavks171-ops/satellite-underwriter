"""Streamlit quote UI — Phase 4.

A full satellite-insurance quote in pure Python:
  • a quote form (altitude, area, duration, value),
  • a premium breakdown card with the annual rate, and
  • three charts: debris density vs altitude, the loss-distribution histogram,
    and the premium-vs-altitude curve ("where is it cheapest to fly?").

Run with:  streamlit run src/app/streamlit_app.py
"""

import sys
from pathlib import Path

# When launched via `streamlit run`, only the script's directory is on the path,
# so add the repo root to make `from src...` imports work.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.ingest import catalog
from src.model import density
from src.model.collision import DEFAULT_V_REL_KM_S, LNT_MULTIPLIER
from src.model.pricing import DEFAULT_RISK_LOAD_K, generate_quote

# Fix the Monte Carlo seed so the quote is stable across Streamlit reruns (every
# widget change reruns the script). At 10k trials the noise is tiny regardless.
SEED = 42

st.set_page_config(page_title="Underwrite a Satellite", page_icon="🛰️", layout="wide")


# --- Cached data + heavy compute ---------------------------------------------

@st.cache_data(show_spinner="Fetching live debris catalog from CelesTrak…")
def get_profile():
    """Load the catalog (24h cached on disk) and build the density profile once."""
    df = catalog.load_catalog()
    profile = density.build_density_profile(df["altitude_km"])
    return profile, len(df)


@st.cache_data(show_spinner="Computing premium-vs-altitude curve…")
def get_premium_curve(area_m2, duration_years, insured_value, risk_load_k,
                      lnt_multiplier, v_rel_low, v_rel_high, _profile):
    """Premium at every altitude shell, holding the satellite fixed.

    `_profile` is underscore-prefixed so Streamlit doesn't try to hash it; the
    cache key is the satellite/assumption inputs, which is what actually changes
    the curve.
    """
    rows = []
    for _, shell in _profile.iterrows():
        q = generate_quote(
            shell["density_per_km3"], area_m2, duration_years, insured_value,
            risk_load_k=risk_load_k, lnt_multiplier=lnt_multiplier,
            v_rel_low=v_rel_low, v_rel_high=v_rel_high, seed=SEED,
        )
        rows.append({
            "altitude_km": shell["shell_center_km"],
            "annual_rate_pct": q.breakdown.annual_rate * 100,
            "premium": q.breakdown.premium,
        })
    return pd.DataFrame(rows)


# --- Header ------------------------------------------------------------------

st.title("🛰️ Underwrite a Satellite")
st.caption(
    "Insurance pricing for spacecraft, from real orbital-debris collision risk. "
    "Built for the NASA × Hack Club Stardance Challenge."
)

profile, n_objects = get_profile()


# --- Sidebar: the quote form -------------------------------------------------

st.sidebar.header("Your satellite")
altitude = st.sidebar.slider("Altitude (km)", 200, 2000, 550, step=5)
area = st.sidebar.number_input(
    "Cross-sectional area (m²)", min_value=0.1, max_value=100.0, value=2.0, step=0.5
)
duration = st.sidebar.slider("Mission duration (years)", 1, 15, 5)
value = st.sidebar.number_input(
    "Insured value ($)", min_value=100_000, max_value=2_000_000_000,
    value=10_000_000, step=1_000_000,
)

with st.sidebar.expander("Advanced assumptions"):
    lnt = st.slider(
        "Lethal non-trackable factor", 1.0, 20.0, float(LNT_MULTIPLIER), step=0.5,
        help="Scales tracked debris up to include 1–10 cm lethal fragments (NASA ODPO).",
    )
    v_rel_low, v_rel_high = st.slider(
        "Relative impact velocity range (km/s)", 5.0, 15.0, (8.0, 12.0), step=0.5,
        help=f"Average LEO impact speed is ~{DEFAULT_V_REL_KM_S:.0f} km/s.",
    )
    risk_k = st.slider(
        "Risk-load factor k", 0.0, 1.0, float(DEFAULT_RISK_LOAD_K), step=0.05,
        help="Charges k standard deviations of the loss distribution (std-dev principle).",
    )

st.sidebar.caption(f"Catalog: {n_objects:,} tracked objects (CelesTrak, 24h cache).")


# --- Compute the quote -------------------------------------------------------

base_density = density.density_at_altitude(profile, altitude)
quote = generate_quote(
    base_density, area, duration, value,
    risk_load_k=risk_k, lnt_multiplier=lnt,
    v_rel_low=v_rel_low, v_rel_high=v_rel_high, seed=SEED,
)
b = quote.breakdown
s = quote.simulation


# --- Premium card ------------------------------------------------------------

st.subheader("Quote")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Annual premium", f"${b.premium:,.0f}")
c2.metric("Annual rate", f"{b.annual_rate * 100:.3f}%", help="% of insured value per year")
c3.metric("Collision probability", f"{s.mean_probability:.2e}", help="over the full mission")
c4.metric("P99 loss (VaR)", f"${s.loss_p99:,.0f}", help="99th-percentile loss")

breakdown_df = pd.DataFrame({
    "Component": [
        "Expected loss (pure premium)",
        f"Risk load (k={risk_k:g} · σ)",
        "Expense load (15%)",
        "Premium",
    ],
    "Amount ($)": [b.expected_loss, b.risk_load, b.expense_load, b.premium],
})
st.dataframe(
    breakdown_df.style.format({"Amount ($)": "${:,.2f}"}),
    hide_index=True, use_container_width=True,
)


# --- Charts ------------------------------------------------------------------

tab1, tab2, tab3 = st.tabs(
    ["Debris density vs altitude", "Loss distribution", "Premium vs altitude"]
)

with tab1:
    fig = go.Figure()
    fig.add_scatter(
        x=profile["shell_center_km"], y=profile["density_per_km3"],
        mode="lines", line=dict(color="#1f77b4"), name="debris density",
    )
    fig.add_vline(
        x=altitude, line_dash="dash", line_color="crimson",
        annotation_text="your satellite", annotation_position="top",
    )
    fig.update_yaxes(type="log", title="objects / km³ (log scale)")
    fig.update_xaxes(title="altitude (km)")
    fig.update_layout(height=420, margin=dict(t=30))
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Peaks reveal real structure: the Starlink shell (~550 km), sun-sync + "
        "2009 Iridium/Cosmos collision debris (~800 km), and an upper band "
        "(~1500 km). Log scale so all three are visible."
    )

with tab2:
    fig2 = go.Figure()
    fig2.add_histogram(x=s.losses, nbinsx=60, marker_color="#2ca02c")
    fig2.add_vline(
        x=s.loss_p95, line_dash="dash", line_color="orange",
        annotation_text="P95", annotation_position="top",
    )
    fig2.add_vline(
        x=s.loss_p99, line_dash="dot", line_color="crimson",
        annotation_text="P99", annotation_position="top",
    )
    fig2.update_xaxes(title="loss ($)")
    fig2.update_yaxes(title=f"trials (of {s.n_trials:,})")
    fig2.update_layout(height=420, margin=dict(t=30))
    st.plotly_chart(fig2, use_container_width=True)
    st.caption(
        "10,000 Monte Carlo trials sampling debris density, impact velocity, and "
        "area. P95/P99 are Value-at-Risk tail metrics — the loss won't exceed "
        "them with 95% / 99% confidence."
    )

with tab3:
    curve = get_premium_curve(
        area, duration, value, risk_k, lnt, v_rel_low, v_rel_high, profile
    )
    cheapest = curve.loc[curve["annual_rate_pct"].idxmin()]
    fig3 = go.Figure()
    fig3.add_scatter(
        x=curve["altitude_km"], y=curve["annual_rate_pct"],
        mode="lines", line=dict(color="#9467bd"), name="annual rate",
    )
    fig3.add_vline(
        x=altitude, line_dash="dash", line_color="crimson",
        annotation_text="your altitude", annotation_position="top",
    )
    fig3.add_scatter(
        x=[cheapest["altitude_km"]], y=[cheapest["annual_rate_pct"]],
        mode="markers", marker=dict(color="green", size=12, symbol="star"),
        name=f"cheapest (~{cheapest['altitude_km']:.0f} km)",
    )
    fig3.update_yaxes(title="annual rate (% of value / year)")
    fig3.update_xaxes(title="altitude (km)")
    fig3.update_layout(height=420, margin=dict(t=30))
    st.plotly_chart(fig3, use_container_width=True)
    st.caption(
        f"Where is it cheapest to fly? For this satellite the lowest rate is near "
        f"**{cheapest['altitude_km']:.0f} km** — debris-empty altitudes are far "
        f"cheaper to insure than the crowded ~550 / ~800 km shells."
    )


st.divider()
st.caption(
    "Data: CelesTrak GP catalog + NASA ODPO. Debris-collision risk only — not a "
    "full launch/operations policy. See METHODOLOGY.md for the math and limits."
)
