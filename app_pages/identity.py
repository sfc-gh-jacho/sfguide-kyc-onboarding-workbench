import streamlit as st

from kyc import ai, documents, source, ui

m = source.model()
docs = m["DOCUMENTS"].set_index("APPLICANT_ID")
cases = m["CASES"]
with_docs = cases[cases.APPLICANT_ID.isin(docs.index)]
flagged = set(m["ALERTS"].loc[m["ALERTS"].FAMILY == "Identity", "APPLICANT_ID"])
ordered = with_docs.assign(F=with_docs.APPLICANT_ID.isin(flagged)).sort_values(["F", "APPLIED_AT"], ascending=False)

st.markdown("The applicant's identity document is read by AI and compared field by field with the application and "
            "the identity vendor's result. Mismatches and expired documents raise alerts automatically.")

if st.session_state.applicant_id not in set(docs.index):
    st.session_state.applicant_id = "A00007"
aid = ui.applicant_picker(ordered, "Applicant (identity issues listed first)", key="identity_picker")
doc = docs.loc[aid].to_dict()
app = m["APPLICATIONS"].set_index("APPLICANT_ID").loc[aid]
risk = dict(zip(m["COUNTRIES"].COUNTRY_CODE, m["COUNTRIES"].COUNTRY_RISK))

left, right = st.columns([5, 6])
with left:
    st.image(documents.render(doc, doc["ISSUING_COUNTRY"]),
             caption="Synthetic identity document generated for this example. Not a real document format.",
             alt=f"Synthetic {doc['DOC_TYPE'].replace('_', ' ').lower()} for applicant {aid}")
with right:
    extracted, kind = ai.extraction(aid)
    with st.container(horizontal=True, vertical_alignment="center"):
        st.subheader("Document check", width="content", anchor=False)
        if kind in ("live", "captured") and extracted:
            ui.ai_label(kind)
    if source.is_live():
        if st.button("Read document with Cortex AI_EXTRACT", icon=":material/auto_awesome:", type="primary"):
            with st.spinner("Uploading to a stage and calling AI_EXTRACT..."):
                extracted = ai.run_extraction(aid, doc, doc["ISSUING_COUNTRY"])
    elif not extracted:
        st.caption("No captured AI_EXTRACT output for this applicant. The table compares the document record directly. "
                   "Switch to live Snowflake mode to read any document with Cortex.")
    cmp = ai.compare(doc, app, extracted)
    if not extracted:
        cmp = cmp.drop(columns=["AI_EXTRACT read"])
    st.dataframe(cmp, hide_index=True, alt="Field comparison between application, document and AI extraction",
                 column_config={"Match": st.column_config.CheckboxColumn("Match", help="Document matches the application")})

    al = m["ALERTS"][(m["ALERTS"].APPLICANT_ID == aid) & (m["ALERTS"].FAMILY == "Identity")]
    if al.empty:
        st.success("Document is valid and matches the application.", icon=":material/check_circle:")
    for r in al.itertuples():
        st.warning(r.DETAIL, title=r.ALERT_LABEL, icon=":material/warning:")
    v = m["IDV_RESULTS"].set_index("APPLICANT_ID").loc[aid]
    st.caption(f"Identity vendor: {v.IDV_RESULT} (score {int(v.IDV_SCORE)}). Issuing country {doc['ISSUING_COUNTRY']} "
               f"is rated {risk[doc['ISSUING_COUNTRY']].lower()} risk.")

ui.snowflake_callout(
    "Cortex AI_EXTRACT",
    "AI_EXTRACT reads named fields from images and PDFs on a Snowflake stage with one SQL function, so documents are "
    "processed where they are stored. In live mode this page uploads the rendered card to a stage and calls it; in "
    "sample mode it shows output captured from a real run.",
)
