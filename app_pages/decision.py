import streamlit as st

from kyc import ai, source, ui

m = source.model()
cases = m["CASES"]
queue = cases[cases.STATUS.isin(["Alert review", "Analyst review"])].sort_values(["OPEN_ALERTS", "RISK_SCORE"], ascending=False)

st.markdown("The analyst sees the whole case in one place: alerts, risk drivers, and a draft summary. They record a "
            "decision with a rationale, and every action lands in an audit trail.")

if queue.empty:
    st.success("No open cases. Every application has a decision.", icon=":material/task_alt:")
    st.stop()

aid = ui.applicant_picker(queue, f"Open case ({len(queue)} in queue)", key="decision_picker")
c = cases.set_index("APPLICANT_ID").loc[aid]
app = m["APPLICATIONS"].set_index("APPLICANT_ID").loc[aid]
alerts = m["ALERTS"][m["ALERTS"].APPLICANT_ID == aid]

with st.container(horizontal=True):
    st.metric("Risk score", int(c.RISK_SCORE), border=True)
    st.metric("Open alerts", len(alerts), border=True)
    st.metric("Product", app.PRODUCT.replace("_", " ").title(), border=True)
    st.metric("Hours in queue", f"{c.AGE_HOURS:.0f}", border=True)

left, right = st.columns([3, 2])
with left:
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.subheader("Case summary", width="content", anchor=False)
            text, kind = ai.case_summary(m, aid)
            if text:
                ui.ai_label(kind)
        if source.is_live():
            if st.button("Draft summary with Cortex AI_COMPLETE", icon=":material/auto_awesome:", type="primary"):
                with st.spinner("Calling AI_COMPLETE..."):
                    text = ai.run_case_summary(m, aid)
            if not text:
                st.caption("Click to draft a summary from this case's facts. The model is told to use only those facts.")
        if text:
            st.markdown(text)
        with st.expander("Facts given to the model", icon=":material/fact_check:"):
            st.code(ai.case_facts(m, aid), language=None, wrap_lines=True)
with right:
    with st.container(border=True):
        st.subheader("Alerts")
        if alerts.empty:
            st.caption("No alerts. Under review because of the risk rating.")
        for r in alerts.itertuples():
            st.markdown(f":orange[:material/warning:] **{r.ALERT_LABEL}**  \n{r.DETAIL}")
    if app.APPLICANT_TYPE == "BUSINESS":
        with st.container(border=True):
            st.subheader("Ownership")
            st.dataframe(m["BENEFICIAL_OWNERS"][m["BENEFICIAL_OWNERS"].APPLICANT_ID == aid].drop(columns="APPLICANT_ID"),
                         hide_index=True, alt="Beneficial owners",
                         column_config={"UBO_DISCLOSED": st.column_config.CheckboxColumn("Beneficial owner disclosed")})

with st.container(border=True):
    st.subheader("Decision")
    with st.form(f"decide_{aid}", border=False):
        c1, c2 = st.columns([3, 2], vertical_alignment="bottom")
        choice = c1.segmented_control("Outcome", ["Approve", "Request enhanced due diligence", "Decline"], key=f"d_{aid}")
        analyst = c2.selectbox("Analyst", ["Analyst 1", "Analyst 2", "Senior reviewer"], key=f"a_{aid}")
        rationale = st.text_area("Rationale (required)", key=f"r_{aid}", height=90,
                                 placeholder="What did you check, and why is this the right outcome?")
        if st.form_submit_button("Record decision", type="primary", icon=":material/gavel:"):
            if not choice:
                st.error("Choose an outcome.", icon=":material/error:")
            elif len(rationale.strip()) < 15:
                st.error("Write a rationale of at least 15 characters. Examiners read these.", icon=":material/error:")
            else:
                code = {"Approve": "APPROVED", "Request enhanced due diligence": "EDD_REQUESTED", "Decline": "DECLINED"}[choice]
                st.session_state.analyst = analyst
                source.record(aid, analyst, f"Decision: {choice}", rationale.strip(), decision=code)
                st.toast(f"{aid}: {choice} recorded", icon=":material/check:")
                st.rerun()

ui.snowflake_callout(
    "Cortex AI_COMPLETE",
    "The summary is drafted by a large language model running inside Snowflake, grounded only in the case facts shown "
    "above. The analyst always makes the decision. In live mode decisions are written to a Snowflake table; in sample "
    "mode they stay in this browser session.",
)
