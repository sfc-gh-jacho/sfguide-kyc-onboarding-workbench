import altair as alt
import pandas as pd
import streamlit as st

from kyc import logic, source, ui

base = source.model(w={f: 1.0 for f in logic.FACTOR_FAMILIES})
st.markdown("Each applicant's score is the sum of named, weighted factors, so any analyst or examiner can see exactly "
            "why a customer is rated low, medium or high. Change the weights to see the effect across the whole book.")

with st.expander("Factor weights (what-if)", icon=":material/tune:", expanded=False):
    with st.form("weights_form", border=False):
        cols = st.columns(3)
        new = {}
        for i, fam in enumerate(logic.FACTOR_FAMILIES):
            new[fam] = cols[i % 3].slider(fam, 0.0, 2.0, source.weights()[fam], 0.25, key=f"w_{fam}")
        with st.container(horizontal=True):
            apply = st.form_submit_button("Apply weights", type="primary")
            reset = st.form_submit_button("Reset to 1.0")
    if apply:
        st.session_state.weights = new
    if reset:
        st.session_state.weights = {f: 1.0 for f in logic.FACTOR_FAMILIES}
        for f in logic.FACTOR_FAMILIES:
            st.session_state.pop(f"w_{f}", None)
        st.rerun()

m = source.model()
cases = m["CASES"]
ordered = cases.sort_values("RISK_SCORE", ascending=False)
aid = ui.applicant_picker(ordered, "Applicant (highest risk first)", key="risk_picker")
c = cases.set_index("APPLICANT_ID").loc[aid]

left, right = st.columns([2, 3])
with left:
    with st.container(border=True, height="stretch"):
        st.metric("Risk score", int(c.RISK_SCORE), help="0 to 100. Low below 25, medium 25 to 49, high 50 and above.")
        ui.rating_badge(c.RISK_RATING, c.RISK_SCORE)
        st.caption(f"{c.LEGAL_NAME} · {c.PRODUCT.replace('_', ' ').lower()} · status: {c.STATUS.lower()}")
with right:
    with st.container(border=True):
        f = m["FACTORS"][m["FACTORS"].APPLICANT_ID == aid].copy()
        w = source.weights()
        f["POINTS"] = f.BASE_POINTS * f.FAMILY.map(w)
        if f.empty:
            st.caption("No risk factors apply to this applicant.")
        else:
            st.altair_chart(alt.Chart(f).mark_bar().encode(
                x=alt.X("POINTS:Q", title="Points"), y=alt.Y("FACTOR:N", sort="-x", title=None, axis=alt.Axis(labelLimit=300, labelOverlap=False)),
                color=alt.Color("FAMILY:N", title="Family"), tooltip=["FAMILY", "FACTOR", "BASE_POINTS", "POINTS"],
            ).properties(height=max(120, 44 * len(f))), alt=f"Risk factor contributions for {aid}")

st.subheader("Effect on the whole book")
mix = pd.DataFrame({
    "Rating": ["LOW", "MEDIUM", "HIGH"],
    "Default weights": base["SCORES"].RISK_RATING.value_counts().reindex(["LOW", "MEDIUM", "HIGH"], fill_value=0).values,
    "Current weights": m["SCORES"].RISK_RATING.value_counts().reindex(["LOW", "MEDIUM", "HIGH"], fill_value=0).values,
})
moved = base["SCORES"].merge(m["SCORES"], on="APPLICANT_ID", suffixes=("_DEFAULT", "_NOW"))
moved = moved[moved.RISK_RATING_DEFAULT != moved.RISK_RATING_NOW]
c1, c2 = st.columns([2, 3])
c1.dataframe(mix, hide_index=True, alt="Applicants per rating under default and current weights")
if moved.empty:
    c2.caption("No applicant changes rating under the current weights.")
else:
    c2.dataframe(moved.merge(cases[["APPLICANT_ID", "LEGAL_NAME"]]), hide_index=True, alt="Applicants whose rating changed",
                 column_config={"APPLICANT_ID": "ID", "LEGAL_NAME": "Applicant", "RISK_SCORE_DEFAULT": "Score before",
                                "RISK_RATING_DEFAULT": "Rating before", "RISK_SCORE_NOW": "Score now", "RISK_RATING_NOW": "Rating now"})

ui.snowflake_callout(
    "transparent scoring on governed data",
    "The factors come from governed tables, and every point is traceable to a source record. Deployed for real, the "
    "same logic can run as a SQL view or Dynamic Table so the whole book is re-scored on Snowflake compute as data "
    "changes. In this example the what-if runs in the app.",
)
