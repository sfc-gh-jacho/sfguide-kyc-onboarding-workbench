"""Cortex AI calls (live mode) with captured or template fallbacks (sample mode)."""

from __future__ import annotations

import json
import os
import tempfile

import pandas as pd
import streamlit as st

from kyc import documents, source

MODEL = "llama3.3-70b"
STAGE = "@KYC_DEMO_DB.KYC.DOC_STAGE"
EXTRACT_FORMAT = {
    "surname": "What is the surname?",
    "given_names": "What are the given names?",
    "date_of_birth": "What is the date of birth?",
    "document_number": "What is the document number?",
    "expiry_date": "What is the date of expiry?",
    "document_type": "What type of identity document is this?",
}


def case_facts(m: dict, aid: str) -> str:
    """The facts the summary may use. The model is told to use nothing else."""
    c = m["CASES"].set_index("APPLICANT_ID").loc[aid]
    a = m["APPLICATIONS"].set_index("APPLICANT_ID").loc[aid]
    al = m["ALERTS"][m["ALERTS"].APPLICANT_ID == aid]
    f = m["FACTORS"][m["FACTORS"].APPLICANT_ID == aid].sort_values("BASE_POINTS", ascending=False)
    lines = [
        f"Applicant {aid}, {a.APPLICANT_TYPE.lower()}, applying for {a.PRODUCT.replace('_', ' ').lower()} via {a.CHANNEL.lower()}.",
        f"Occupation: {a.OCCUPATION}. Source of funds: {a.SOURCE_OF_FUNDS}. Expected monthly volume: ${a.EXPECTED_MONTHLY_VOLUME:,.0f}.",
        f"Residence country {a.RESIDENCE_COUNTRY}, nationality {a.NATIONALITY}.",
        f"Risk score {int(c.RISK_SCORE)} ({c.RISK_RATING}).",
        "Alerts: " + ("; ".join(f"{r.ALERT_LABEL}: {r.DETAIL}" for r in al.itertuples()) or "none") + ".",
        "Top risk factors: " + ("; ".join(f"{r.FACTOR} (+{r.BASE_POINTS})" for r in f.head(5).itertuples()) or "none") + ".",
    ]
    return "\n".join(lines)


def _prompt(facts: str) -> str:
    return ("You are assisting a bank KYC analyst. Using ONLY the facts below, write a case summary in 4 short bullet "
            "points: who the applicant is, what was found, the key risk drivers, and the recommended next step "
            "(approve, request enhanced due diligence, or escalate for decline). Respond with only the four bullets, no "
            "introduction. Do not invent facts, names or numbers. "
            "This is synthetic data for a demonstration.\n\nFACTS:\n" + facts)


def template_summary(facts: str) -> str:
    return "\n".join(f"- {line}" for line in facts.splitlines())


def case_summary(m: dict, aid: str) -> tuple[str | None, str]:
    """Returns (text, kind) for the current mode without calling the model."""
    if source.is_live():
        return st.session_state.get(f"ai_summary_{aid}"), "live"
    cap = source.captured_ai()["case_summaries"].get(aid)
    if cap:
        return cap["text"], "captured"
    return template_summary(case_facts(m, aid)), "template"


def run_case_summary(m: dict, aid: str) -> str:
    df = source._conn().query(
        "SELECT AI_COMPLETE(?, ?, {'temperature': 0, 'max_tokens': 300})::STRING AS S",
        params=[MODEL, _prompt(case_facts(m, aid))], ttl=0)
    text = df.iloc[0, 0]
    st.session_state[f"ai_summary_{aid}"] = text
    return text


def extraction(aid: str) -> tuple[dict | None, str]:
    if source.is_live():
        return st.session_state.get(f"ai_extract_{aid}"), "live"
    cap = source.captured_ai()["extractions"].get(aid)
    return (cap, "captured") if cap else (None, "none")


def run_extraction(aid: str, doc: dict, country_label: str) -> dict:
    """Upload the rendered document to a stage, then call AI_EXTRACT on it."""
    img = documents.render(doc, country_label)
    path = os.path.join(tempfile.mkdtemp(), f"{aid}.png")
    img.save(path)
    cur = source._conn().cursor()
    cur.execute(f"PUT 'file://{path}' {STAGE} AUTO_COMPRESS = FALSE OVERWRITE = TRUE")
    cur.execute(f"SELECT AI_EXTRACT(file => TO_FILE('{STAGE}', ?), responseFormat => PARSE_JSON(?))::STRING",
                (f"{aid}.png", json.dumps(EXTRACT_FORMAT)))
    result = json.loads(cur.fetchone()[0]).get("response", {})
    st.session_state[f"ai_extract_{aid}"] = result
    return result


def compare(doc: dict, app: pd.Series, extracted: dict | None) -> pd.DataFrame:
    rows = [
        ("Surname", app.LAST_NAME, doc["DOC_LAST_NAME"], (extracted or {}).get("surname")),
        ("Given names", app.FIRST_NAME, doc["DOC_FIRST_NAME"], (extracted or {}).get("given_names")),
        ("Date of birth", str(app.DATE_OF_BIRTH), str(doc["DOC_DATE_OF_BIRTH"]), (extracted or {}).get("date_of_birth")),
        ("Document number", "", doc["DOC_NUMBER"], (extracted or {}).get("document_number")),
        ("Date of expiry", "", str(doc["EXPIRY_DATE"]), (extracted or {}).get("expiry_date")),
    ]
    df = pd.DataFrame(rows, columns=["Field", "Application", "Document record", "AI_EXTRACT read"])
    df["Match"] = [
        None if not r[1] else str(r[1]).strip().lower() == str(r[2]).strip().lower() for r in rows]
    return df
