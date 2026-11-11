import pandas as pd
import streamlit as st

from kyc import source, ui

m = source.model()

st.markdown("Who can see what is enforced on the data, not in each application. Switch roles to see how the same "
            "applicant records appear to each team, then review the audit trail of every action.")

role = st.segmented_control("View as", ui.ROLES, default="KYC analyst", required=True, key="gov_role")
open_ids = m["CASES"].loc[m["CASES"].STATUS.isin(["Alert review", "Analyst review"]), "APPLICANT_ID"]
a = m["APPLICATIONS"][m["APPLICATIONS"].APPLICANT_ID.isin(open_ids)].merge(
    m["DOCUMENTS"][["APPLICANT_ID", "DOC_NUMBER"]], on="APPLICANT_ID", how="left")
if role == "Relationship manager":
    st.info("Relationship managers see only customers in their own book. A row access policy filters the others out; "
            "here, the book is the online channel.", icon=":material/filter_alt:")
    a = a[a.CHANNEL == "ONLINE"]
view = pd.DataFrame({
    "ID": a.APPLICANT_ID, "Applicant": a.LEGAL_NAME,
    "Tax ID": [ui.mask(v, "tax_id", role) for v in a.TAX_ID],
    "Date of birth": [ui.mask(v, "dob", role) for v in a.DATE_OF_BIRTH],
    "Document no.": [ui.mask(v, "doc_number", role) for v in a.DOC_NUMBER],
    "Email": [ui.mask(v, "email", role) for v in a.EMAIL],
})
st.dataframe(view, hide_index=True, alt=f"Open-case applicant records as seen by the {role} role")
st.caption("This switcher simulates each role so you can compare views. In Snowflake, the masking and row access "
           "policies in sql/kyc_setup.sql evaluate the querying role automatically.")

rules = pd.DataFrame([
    ("Tax ID", "Last 4 digits", "Full", "Last 4 digits", "Hidden"),
    ("Date of birth", "Year only", "Full", "Year only", "Hidden"),
    ("Document number", "Last 3 digits", "Full", "Hidden", "Hidden"),
    ("Email", "Full", "Full", "Domain only", "Full"),
    ("Rows", "All", "All", "All", "Own book only"),
], columns=["Data", *ui.ROLES])
with st.expander("Policy summary", icon=":material/policy:"):
    st.table(rules, hide_index=True, alt="What each role can see")

st.subheader("Audit trail")
if source.is_live():
    trail = source.live_audit()
    st.caption("Read from KYC_DEMO_DB.KYC.AUDIT_EVENTS.")
else:
    trail = pd.DataFrame(st.session_state.get("audit", []))
    st.caption("Actions recorded in this browser session. In live mode they are written to a Snowflake table.")
if trail.empty:
    st.caption("No actions yet. Triage a screening hit or record a decision, then come back.")
else:
    st.dataframe(trail, hide_index=True, alt="Audit trail of analyst actions")

st.subheader("Data lineage")
st.markdown("""```mermaid
flowchart LR
  A[Applications] --> J((Joined case view))
  B[Core banking] --> J
  C[Identity vendor] --> J
  D[Device signals] --> J
  W[Watchlist] --> S[Screening hits]
  A --> S
  S --> J
  J --> R[Risk scores]
  R --> Q[Analyst queue]
  Q --> X[Decisions and audit events]
```""")

if source.is_live():
    with st.expander("Policies attached in this account", icon=":material/ac_unit:"):
        st.dataframe(source._conn().query(
            "SELECT REF_ENTITY_NAME AS TABLE_NAME, REF_COLUMN_NAME AS COLUMN_NAME, POLICY_NAME, POLICY_KIND "
            "FROM TABLE(KYC_DEMO_DB.INFORMATION_SCHEMA.POLICY_REFERENCES(REF_ENTITY_NAME => 'KYC_DEMO_DB.KYC.APPLICATIONS', "
            "REF_ENTITY_DOMAIN => 'table'))", ttl=0), hide_index=True, alt="Policies attached to the applications table")

ui.snowflake_callout(
    "governance that travels with the data",
    "Masking and row access policies follow the table into every tool, from this app to notebooks and BI. Access "
    "History records which user read which columns, and object tags classify sensitive fields once for the whole account.",
)
