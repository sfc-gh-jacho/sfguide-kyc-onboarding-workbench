import streamlit as st

from kyc import source

st.set_page_config(page_title="KYC onboarding workbench", page_icon=":material/verified_user:", layout="wide")

if "mode" not in st.session_state:
    st.session_state.mode = "live" if source.live_status() == "ready" else "sample"
st.session_state.setdefault("applicant_id", "A00019")

page = st.navigation(
    {
        "": [st.Page("app_pages/overview.py", title="Overview", icon=":material/dashboard:", default=True)],
        "Workflow": [
            st.Page("app_pages/intake.py", title="1 · Onboarding intake", icon=":material/move_to_inbox:"),
            st.Page("app_pages/identity.py", title="2 · Identity and documents", icon=":material/badge:"),
            st.Page("app_pages/risk.py", title="3 · Risk assessment", icon=":material/speed:"),
            st.Page("app_pages/screening.py", title="4 · Screening alerts", icon=":material/notifications_active:"),
            st.Page("app_pages/decision.py", title="5 · Analyst decision", icon=":material/gavel:"),
        ],
        "Trust": [
            st.Page("app_pages/governance.py", title="Governance and audit", icon=":material/shield_lock:"),
            st.Page("app_pages/about.py", title="About this example", icon=":material/info:"),
        ],
    }
)

with st.sidebar:
    st.markdown("**KYC onboarding workbench**")
    status = source.live_status()
    if status == "unavailable":
        st.badge("Sample data mode", icon=":material/science:", color="blue")
        st.caption("No Snowflake account needed.")
        if source.IN_BROWSER:
            st.caption("Running entirely in your browser. Nothing you do here leaves this page.")
    else:
        choice = st.segmented_control("Data source", ["Sample data", "Live Snowflake"],
                                      default="Live Snowflake" if source.is_live() else "Sample data", required=True)
        st.session_state.mode = "live" if choice == "Live Snowflake" else "sample"
        if status == "empty" and source.is_live():
            st.warning("The Snowflake tables are empty. Load the synthetic data on the About page.", icon=":material/warning:")
            st.session_state.mode = "sample"
    st.caption("All applicants, documents and watchlist entries are synthetic. Not compliance advice.")

with st.container(horizontal=True, vertical_alignment="center"):
    st.title(page.title, icon=page.icon, width="content", anchor=False)
    st.space("small")
    if source.is_live():
        st.badge("Live Snowflake data", icon=":material/ac_unit:", color="blue")
    else:
        st.badge("Sample data mode", icon=":material/science:", color="gray")
    st.badge("Synthetic data", icon=":material/lab_profile:", color="orange")

page.run()
