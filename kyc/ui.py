"""Shared UI pieces: the mode banner, Snowflake callouts, pickers, masking."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from kyc import source

STATUS_COLOR = {"Alert review": "red", "Analyst review": "orange", "Enhanced due diligence": "violet",
                "Auto-cleared": "green", "Approved": "green", "Declined": "gray"}
RATING_COLOR = {"LOW": "green", "MEDIUM": "orange", "HIGH": "red"}


def snowflake_callout(title: str, body: str) -> None:
    """Names the Snowflake capability behind the screen."""
    with st.container(border=True):
        st.markdown(f":blue[:material/ac_unit:] **Powered by Snowflake: {title}**")
        st.caption(body)


def ai_label(kind: str) -> None:
    """kind: 'live', 'captured' or 'template'."""
    if kind == "live":
        st.badge("Live Cortex AI output", icon=":material/auto_awesome:", color="violet")
    elif kind == "captured":
        st.badge("Captured AI output from a real Snowflake Cortex run", icon=":material/history:", color="gray")
    else:
        st.badge("Template text, not AI-generated", icon=":material/text_snippet:", color="gray")


def rating_badge(rating: str, score) -> None:
    st.badge(f"{rating.title()} risk · {int(score)}", color=RATING_COLOR[rating])


def applicant_picker(cases: pd.DataFrame, label: str = "Applicant", key: str = "picker") -> str:
    """A selector that remembers the applicant across pages."""
    ids = list(cases.APPLICANT_ID)
    names = dict(zip(cases.APPLICANT_ID, cases.LEGAL_NAME))
    current = st.session_state.get("applicant_id")
    if current not in ids:
        current = ids[0]

    def _sync():
        st.session_state.applicant_id = st.session_state[key]

    st.selectbox(label, ids, index=ids.index(current), key=key, on_change=_sync,
                 format_func=lambda i: f"{i} · {names[i]}")
    st.session_state.applicant_id = st.session_state[key]
    return st.session_state[key]


# ── View-as masking. Mirrors the masking policies in sql/kyc_setup.sql ──

ROLES = ["KYC analyst", "Senior reviewer", "Auditor", "Relationship manager"]


def mask(value, kind: str, role: str):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    v = str(value)
    if role == "Senior reviewer":
        return v
    if kind == "tax_id":
        return f"***-**-{v[-4:]}" if role in ("KYC analyst", "Auditor") else "***-**-****"
    if kind == "dob":
        return f"{v[:4]}-**-**" if role in ("KYC analyst", "Auditor") else "****-**-**"
    if kind == "doc_number":
        return f"*****{v[-3:]}" if role == "KYC analyst" else "********"
    if kind == "email":
        return v if role in ("KYC analyst", "Relationship manager") else "****@" + v.split("@")[-1]
    return v
