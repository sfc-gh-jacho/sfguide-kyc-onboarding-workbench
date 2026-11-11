import pandas as pd
import streamlit as st

from kyc import logic, source, ui

st.markdown("Every applicant is screened against sanctions, politically-exposed-person (PEP) and adverse-media lists "
            "with fuzzy name matching. Analysts confirm true matches and clear false positives, with corroborating "
            "fields shown side by side.")

threshold = st.slider("Name similarity threshold", 70, 100, logic.NAME_MATCH_THRESHOLD, 1,
                      help="Lower thresholds catch more spelling variants but create more false positives.")
m = source.model(threshold=threshold)
hits = m["HITS"].sort_values("NAME_SCORE", ascending=False)
st.caption(f"{len(hits)} potential matches at a threshold of {threshold}, from "
           f"{len(m['APPLICATIONS']):,} applicants × {len(m['WATCHLIST'])} watchlist entries "
           f"({len(m['APPLICATIONS']) * len(m['WATCHLIST']):,} comparisons).")

if hits.empty:
    st.info("No potential matches at this threshold.", icon=":material/info:")
    st.stop()

event = st.dataframe(
    hits[["APPLICANT_ID", "LEGAL_NAME", "ENTRY_NAME", "LIST_TYPE", "NAME_SCORE", "DOB_MATCH", "COUNTRY_MATCH", "STRENGTH"]],
    hide_index=True, on_select="rerun", selection_mode="single-row", key="hits_table", alt="Screening hits",
    column_config={"APPLICANT_ID": "ID", "LEGAL_NAME": "Applicant", "ENTRY_NAME": "Watchlist entry", "LIST_TYPE": "List",
                   "NAME_SCORE": st.column_config.ProgressColumn("Name similarity", min_value=0, max_value=100, format="%d"),
                   "DOB_MATCH": st.column_config.CheckboxColumn("Birth date"), "COUNTRY_MATCH": st.column_config.CheckboxColumn("Country"),
                   "STRENGTH": "Strength"},
)
row = hits.iloc[event.selection.rows[0]] if event.selection.rows else hits.iloc[0]
st.session_state.applicant_id = row.APPLICANT_ID

with st.container(border=True):
    st.subheader(f"{row.LEGAL_NAME} vs. {row.ENTRY_NAME}")
    cmp = pd.DataFrame([
        ("Name", row.LEGAL_NAME, row.ENTRY_NAME, f"{row.NAME_SCORE} / 100"),
        ("Date of birth", str(row.DATE_OF_BIRTH), str(row.ENTRY_DATE_OF_BIRTH), "Match" if row.DOB_MATCH else "Different"),
        ("Country", f"{row.NATIONALITY} / {row.RESIDENCE_COUNTRY}", row.ENTRY_COUNTRY, "Match" if row.COUNTRY_MATCH else "Different"),
        ("List", "", f"{row.LIST_TYPE.replace('_', ' ').title()}: {row.DETAIL}", ""),
    ], columns=["Field", "Applicant", "Watchlist entry", "Result"])
    st.table(cmp, hide_index=True, alt="Applicant and watchlist entry compared field by field")
    key = f"triage_{row.APPLICANT_ID}_{row.ENTRY_ID}"
    with st.form(f"form_{key}", border=False):
        c1, c2 = st.columns([2, 3], vertical_alignment="bottom")
        outcome = c1.segmented_control("Outcome", ["Confirm match", "False positive", "Escalate"], key=f"o_{key}")
        note = c2.text_input("Note", placeholder="e.g. birth date and nationality differ", key=f"n_{key}")
        if st.form_submit_button("Record outcome", type="primary"):
            if not outcome:
                st.error("Choose an outcome first.", icon=":material/error:")
            else:
                source.record(row.APPLICANT_ID, st.session_state.get("analyst", "Analyst 1"), f"Screening: {outcome}",
                              f"{row.ENTRY_ID} {row.ENTRY_NAME} ({row.LIST_TYPE}), score {row.NAME_SCORE}. {note}".strip())
                st.session_state[key] = outcome
                st.toast(f"Recorded: {outcome}", icon=":material/check:")
    if st.session_state.get(key):
        st.caption(f"Recorded this session: {st.session_state[key]}")

ui.snowflake_callout(
    "fuzzy matching at scale",
    "In live mode the screening runs as SQL: JAROWINKLER_SIMILARITY across every applicant and watchlist pair, on a "
    "warehouse you can resize for a full-book rescreen. Watchlists from data providers can be shared in or subscribed "
    "to on Snowflake Marketplace. This list is synthetic.",
)
