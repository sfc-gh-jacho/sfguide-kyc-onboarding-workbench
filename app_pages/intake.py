import pandas as pd
import streamlit as st

from kyc import source, ui

m = source.model()
cases = m["CASES"].sort_values("APPLIED_AT", ascending=False)

st.markdown("New applications arrive from online, mobile and branch channels. Each one is joined with what the bank "
            "already knows and what its identity and device vendors report, before any analyst looks at it.")

with st.container(horizontal=True, vertical_alignment="bottom"):
    statuses = st.pills("Status", sorted(cases.STATUS.unique()), selection_mode="multi", key="intake_status")
    channel = st.segmented_control("Channel", ["ONLINE", "MOBILE", "BRANCH"], selection_mode="multi", key="intake_channel",
                                   format_func=str.title)
q = cases
if statuses:
    q = q[q.STATUS.isin(statuses)]
if channel:
    q = q[q.CHANNEL.isin(channel)]

st.caption(f"{len(q):,} applications. Select a row to see every source joined for that applicant.")
event = st.dataframe(
    q[["APPLICANT_ID", "LEGAL_NAME", "APPLICANT_TYPE", "PRODUCT", "CHANNEL", "APPLIED_AT", "STATUS", "RISK_RATING", "OPEN_ALERTS"]],
    hide_index=True, height=320, on_select="rerun", selection_mode="single-row", key="intake_table",
    alt="Application queue with status and risk",
    column_config={"APPLICANT_ID": "ID", "LEGAL_NAME": "Applicant", "APPLICANT_TYPE": "Type", "PRODUCT": "Product",
                   "CHANNEL": "Channel", "APPLIED_AT": st.column_config.DatetimeColumn("Applied", format="MMM D, h:mm a"),
                   "STATUS": "Status", "RISK_RATING": "Risk", "OPEN_ALERTS": "Alerts"},
)
if event.selection.rows:
    st.session_state.applicant_id = q.iloc[event.selection.rows[0]].APPLICANT_ID
aid = st.session_state.applicant_id
if aid not in set(cases.APPLICANT_ID):
    aid = st.session_state.applicant_id = cases.iloc[0].APPLICANT_ID

app = m["APPLICATIONS"].set_index("APPLICANT_ID").loc[aid]
case = cases.set_index("APPLICANT_ID").loc[aid]
with st.container(border=True):
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader(f"{aid} · {app.LEGAL_NAME}", width="content", anchor=False)
        st.badge(case.STATUS, color=ui.STATUS_COLOR[case.STATUS])
        ui.rating_badge(case.RISK_RATING, case.RISK_SCORE)
    tabs = st.tabs([":material/description: Application", ":material/account_balance: Core banking",
                    ":material/fingerprint: Identity vendor", ":material/devices: Device signals"])

    def kv(rows):
        st.table(pd.DataFrame(rows, columns=["Field", "Value"]).astype(str), hide_header=True, hide_index=True,
                 alt="Field and value pairs for the selected applicant")

    with tabs[0]:
        kv([("Type", app.APPLICANT_TYPE.title()), ("Product", app.PRODUCT.replace("_", " ").title()),
            ("Channel", app.CHANNEL.title()), ("Occupation", app.OCCUPATION), ("Source of funds", app.SOURCE_OF_FUNDS),
            ("Expected monthly volume", f"${app.EXPECTED_MONTHLY_VOLUME:,.0f}"),
            ("Residence / nationality", f"{app.RESIDENCE_COUNTRY} / {app.NATIONALITY}"), ("Email", app.EMAIL)])
    with tabs[1]:
        cb = m["CORE_BANKING"].set_index("APPLICANT_ID").loc[aid]
        kv([("Existing customer", "Yes" if cb.EXISTING_CUSTOMER else "No"),
            ("Customer since", cb.CUSTOMER_SINCE or "n/a"), ("Prior suspicious-activity report", "Yes" if cb.PRIOR_SAR_FLAG else "No")])
    with tabs[2]:
        v = m["IDV_RESULTS"].set_index("APPLICANT_ID").loc[aid]
        kv([("Vendor", v.VENDOR), ("Result", v.IDV_RESULT), ("Match score", "n/a" if pd.isna(v.IDV_SCORE) else int(v.IDV_SCORE))])
    with tabs[3]:
        d = m["DEVICE_SIGNALS"].set_index("APPLICANT_ID").loc[aid]
        kv([("Device risk", d.DEVICE_RISK), ("Session country", d.IP_COUNTRY or "n/a (branch)"), ("VPN detected", "Yes" if d.VPN_DETECTED else "No")])

ui.snowflake_callout(
    "secure data integration",
    "Vendor results like these can be shared into Snowflake with Secure Data Sharing or subscribed to from "
    "Snowflake Marketplace, and operational systems can be streamed in with connectors such as Openflow. The "
    "data is joined in place rather than copied between systems. In this example all four sources are synthetic tables.",
)
