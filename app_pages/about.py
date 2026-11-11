import streamlit as st

from kyc import source

st.markdown(
    "This is an illustrative example of an end-to-end know-your-customer (KYC) onboarding workflow on Snowflake. "
    "Everything in it is synthetic: applicants, documents, vendor results and watchlist entries are generated, "
    "countries are coded (CTRY_A to CTRY_L) so no real jurisdiction is labeled high risk, and emails use example.com."
)

c1, c2 = st.columns(2)
with c1:
    with st.container(border=True, height="stretch"):
        st.subheader("Sample data mode", icon=":material/science:")
        st.markdown("- Runs with no Snowflake account, including entirely in your browser\n"
                    "- AI outputs are **captured from a real Snowflake Cortex run** and labeled as such, or are "
                    "template text where nothing was captured\n"
                    "- Decisions and triage outcomes stay in your browser session")
with c2:
    with st.container(border=True, height="stretch"):
        st.subheader("Live Snowflake mode", icon=":material/ac_unit:")
        st.markdown("- Reads tables in `KYC_DEMO_DB.KYC` built by `sql/kyc_setup.sql`\n"
                    "- Screening runs `JAROWINKLER_SIMILARITY` in SQL\n"
                    "- Calls Cortex `AI_EXTRACT` and `AI_COMPLETE` live\n"
                    "- Writes decisions and audit events to Snowflake tables")

status = source.live_status()
if status == "empty":
    st.subheader("Load the synthetic data into Snowflake")
    st.markdown("The setup script created empty tables with their policies attached. Load the same synthetic data "
                "this app generates so both modes show identical applicants.")
    if st.button("Load synthetic data", type="primary", icon=":material/upload:"):
        with st.spinner("Writing tables..."):
            counts = source.load_into_snowflake()
        st.success("Loaded: " + ", ".join(f"{k} {v:,}" for k, v in counts.items()), icon=":material/check_circle:")
        st.session_state.mode = "live"
        st.rerun()
elif status == "ready":
    st.success("Connected to Snowflake, and the synthetic data is loaded.", icon=":material/check_circle:")

st.subheader("Run it in your own account")
st.markdown("1. Run `sql/kyc_setup.sql` in a Snowsight worksheet (Enterprise Edition for masking and row access policies).\n"
            "2. Deploy the app with `snow streamlit deploy --replace` (see the README).\n"
            "3. Open the app, go to this page and select **Load synthetic data**.\n"
            "4. When you're done, run the cleanup block at the end of the script.")

st.subheader("Learn more")
with st.container(horizontal=True):
    st.link_button("AI_EXTRACT", "https://docs.snowflake.com/en/sql-reference/functions/ai_extract", icon=":material/open_in_new:")
    st.link_button("AI_COMPLETE", "https://docs.snowflake.com/en/sql-reference/functions/ai_complete", icon=":material/open_in_new:")
    st.link_button("Masking policies", "https://docs.snowflake.com/en/user-guide/security-column-ddm-intro", icon=":material/open_in_new:")
    st.link_button("Streamlit in Snowflake", "https://docs.snowflake.com/en/developer-guide/streamlit/about-streamlit", icon=":material/open_in_new:")

st.caption("Illustrative example provided as-is. Not an official Snowflake product, not supported by Snowflake "
           "Support, and not regulatory or compliance advice. Rules, thresholds and scores are simplified for demonstration.")
