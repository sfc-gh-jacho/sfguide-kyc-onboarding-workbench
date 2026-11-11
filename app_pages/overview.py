import altair as alt
import pandas as pd
import streamlit as st

from kyc import source, ui

m = source.model()
cases = m["CASES"]
recent = cases[pd.to_datetime(cases.APPLIED_AT) >= pd.to_datetime(cases.APPLIED_AT).max() - pd.Timedelta(days=7)]

st.markdown(
    "A fictional bank onboards about 500 new customers a month. This workbench follows each application from "
    "intake through identity checks, risk scoring and screening to an analyst's decision, on one governed copy of the data."
)

open_cases = cases[cases.STATUS.isin(["Alert review", "Analyst review"])]
auto = (cases.STATUS == "Auto-cleared").sum()
decided = m["DECISIONS"]
manual = decided[decided.DECIDED_BY != "Auto-clear"]
auto_rate = ((decided.DECIDED_BY == "Auto-clear").sum() + auto) / max(len(decided) + auto, 1)

with st.container(horizontal=True):
    st.metric("Applications, last 30 days", f"{len(cases):,}", border=True)
    st.metric("Cleared without manual review", f"{auto_rate:.0%}", border=True,
              help="Low-risk applications with no alerts, in this synthetic data set")
    st.metric("Open cases", len(open_cases), border=True)
    st.metric("Open alerts", int(open_cases.OPEN_ALERTS.sum()), border=True)
    st.metric("High risk, open", int((open_cases.RISK_RATING == "HIGH").sum()), border=True)

left, right = st.columns([3, 2])
with left:
    with st.container(border=True):
        st.subheader("Applications by status")
        daily = cases.assign(DAY=pd.to_datetime(cases.APPLIED_AT).dt.date).groupby(["DAY", "STATUS"]).size().rename("APPLICATIONS").reset_index()
        order = ["Auto-cleared", "Approved", "Analyst review", "Alert review", "Enhanced due diligence", "Declined"]
        chart = alt.Chart(daily).mark_bar().encode(
            x=alt.X("DAY:T", title=None),
            y=alt.Y("APPLICATIONS:Q", title="Applications"),
            color=alt.Color("STATUS:N", sort=order, title=None,
                            scale=alt.Scale(domain=order, range=["#36B37E", "#29B5E8", "#FF8B00", "#DE350B", "#6554C0", "#7A869A"])),
            tooltip=["DAY:T", "STATUS:N", "APPLICATIONS:Q"],
        ).properties(height=280)
        st.altair_chart(chart, alt="Daily applications stacked by workflow status")
with right:
    with st.container(border=True):
        st.subheader("Open work queue")
        q = open_cases.sort_values(["OPEN_ALERTS", "RISK_SCORE"], ascending=False)[
            ["APPLICANT_ID", "LEGAL_NAME", "STATUS", "RISK_RATING", "OPEN_ALERTS"]]
        st.dataframe(q, hide_index=True, height=280, alt="Open cases sorted by alerts and risk",
                     column_config={"APPLICANT_ID": st.column_config.TextColumn("ID", width="small"), "LEGAL_NAME": "Applicant",
                                    "STATUS": "Status", "RISK_RATING": st.column_config.TextColumn("Risk", width="small"),
                                    "OPEN_ALERTS": st.column_config.NumberColumn("Alerts", width="small")})

c1, c2 = st.columns(2)
with c1:
    with st.container(border=True):
        st.subheader("Alerts by type")
        a = m["ALERTS"].groupby("ALERT_LABEL").size().rename("ALERTS").reset_index()
        bars = alt.Chart(a).encode(
            x=alt.X("ALERTS:Q", title="Alerts", axis=alt.Axis(tickMinStep=1)),
            y=alt.Y("ALERT_LABEL:N", sort="-x", title=None, axis=alt.Axis(labelLimit=240)),
            tooltip=["ALERT_LABEL", "ALERTS"])
        st.altair_chart((bars.mark_bar(color="#29B5E8") + bars.mark_text(align="left", dx=4, color="#11567F").encode(text="ALERTS:Q"))
                        .properties(height=34 * len(a) + 20), alt="Alert counts by alert type")
with c2:
    with st.container(border=True):
        st.subheader("Risk rating mix")
        r = cases.groupby("RISK_RATING").size().reindex(["LOW", "MEDIUM", "HIGH"], fill_value=0).rename("APPLICANTS").reset_index()
        rb = alt.Chart(r).encode(
            y=alt.Y("RISK_RATING:N", sort=["LOW", "MEDIUM", "HIGH"], title=None),
            x=alt.X("APPLICANTS:Q", title="Applicants", scale=alt.Scale(type="symlog")),
            tooltip=["RISK_RATING", "APPLICANTS"])
        st.altair_chart((rb.mark_bar().encode(color=alt.Color("RISK_RATING:N", legend=None, scale=alt.Scale(
                            domain=["LOW", "MEDIUM", "HIGH"], range=["#36B37E", "#FF8B00", "#DE350B"])))
                         + rb.mark_text(align="left", dx=4, color="#11567F").encode(text="APPLICANTS:Q"))
                        .properties(height=150), alt="Applicants by risk rating")
        st.caption("Log scale, so the small medium and high groups stay visible.")

st.caption(
    f"Eight applications are planted to show the workflow end to end: {', '.join(sorted(source.data.PLANTED))}. "
    "Counts describe this synthetic data set only and are not performance claims."
)

c1, c2, c3 = st.columns(3)
with c1:
    ui.snowflake_callout("one governed copy", "Applications, core banking, identity-vendor and device data sit side by side in "
                         "Snowflake, so every team works from the same records without exporting extracts.")
with c2:
    ui.snowflake_callout("scalable analytics", "Screening compares every applicant with every watchlist entry using "
                         "JAROWINKLER_SIMILARITY in SQL, on a warehouse that suspends itself when idle.")
with c3:
    ui.snowflake_callout("AI next to the data", "Cortex AI_EXTRACT reads identity documents and AI_COMPLETE drafts case "
                         "summaries without the data leaving Snowflake.")
