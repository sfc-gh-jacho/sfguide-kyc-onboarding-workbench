"""Where the data comes from: in-app sample data or live Snowflake tables.

Sample mode needs no account and is the only mode in the browser (stlite).
Live mode reads KYC_DEMO_DB.KYC, built by sql/kyc_setup.sql and loaded from
the same generator, so both modes show the same applicants.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

from kyc import data, logic

IN_BROWSER = sys.platform == "emscripten"
DB = "KYC_DEMO_DB.KYC"
TABLES = ["COUNTRIES", "APPLICATIONS", "CORE_BANKING", "IDV_RESULTS", "DEVICE_SIGNALS",
          "DOCUMENTS", "BENEFICIAL_OWNERS", "WATCHLIST", "DECISIONS"]
ROOT = Path(__file__).resolve().parents[1]


def _conn():
    return st.connection("snowflake")


@st.cache_data(ttl=300, show_spinner=False)
def live_status() -> str:
    """'unavailable', 'empty' (tables exist but no rows) or 'ready'."""
    if IN_BROWSER or os.getenv("KYC_SAMPLE_ONLY"):
        return "unavailable"
    try:
        n = _conn().query(f"SELECT COUNT(*) AS N FROM {DB}.APPLICATIONS", ttl=0).iloc[0, 0]
    except Exception:
        return "unavailable"
    return "ready" if n else "empty"


def mode() -> str:
    return st.session_state.get("mode", "sample")


def is_live() -> bool:
    return mode() == "live"


@st.cache_data(show_spinner="Generating synthetic data...")
def _sample_tables() -> dict[str, pd.DataFrame]:
    return data.generate()


@st.cache_data(ttl=600, show_spinner="Reading from Snowflake...")
def _live_tables() -> dict[str, pd.DataFrame]:
    out = {}
    for t in TABLES:
        df = _conn().query(f"SELECT * FROM {DB}.{t}", ttl=0)
        for c in df.columns:
            if c in ("DATE_OF_BIRTH", "DOC_DATE_OF_BIRTH", "EXPIRY_DATE", "CUSTOMER_SINCE", "ENTRY_DATE_OF_BIRTH"):
                df[c] = pd.to_datetime(df[c]).dt.date
        out[t] = df
    return out


def tables() -> dict[str, pd.DataFrame]:
    t = {k: v.copy() for k, v in (_live_tables() if is_live() else _sample_tables()).items()}
    extra = st.session_state.get("new_decisions", [])
    if extra and not is_live():
        t["DECISIONS"] = pd.concat([t["DECISIONS"], pd.DataFrame(extra)], ignore_index=True)
    return t


@st.cache_data(show_spinner=False)
def _sample_hits(threshold: int) -> pd.DataFrame:
    t = _sample_tables()
    out = []
    for a in t["APPLICATIONS"].itertuples():
        for w in t["WATCHLIST"].itertuples():
            s = logic.jaro_winkler(a.LEGAL_NAME, w.ENTRY_NAME)
            if s >= threshold:
                out.append({"APPLICANT_ID": a.APPLICANT_ID, "ENTRY_ID": w.ENTRY_ID, "NAME_SCORE": s})
    return pd.DataFrame(out, columns=["APPLICANT_ID", "ENTRY_ID", "NAME_SCORE"])


@st.cache_data(ttl=600, show_spinner="Screening in Snowflake...")
def _live_hits(threshold: int) -> pd.DataFrame:
    return _conn().query(
        f"""SELECT a.APPLICANT_ID, w.ENTRY_ID,
                   JAROWINKLER_SIMILARITY(a.LEGAL_NAME, w.ENTRY_NAME) AS NAME_SCORE
            FROM {DB}.APPLICATIONS a CROSS JOIN {DB}.WATCHLIST w
            WHERE JAROWINKLER_SIMILARITY(a.LEGAL_NAME, w.ENTRY_NAME) >= ?""",
        params=[threshold], ttl=0)


def screening_hits(t: dict, threshold: int = logic.NAME_MATCH_THRESHOLD) -> pd.DataFrame:
    raw = _live_hits(threshold) if is_live() else _sample_hits(threshold)
    return logic.enrich_hits(raw, t["APPLICATIONS"], t["WATCHLIST"])


def weights() -> dict[str, float]:
    return st.session_state.get("weights", {f: 1.0 for f in logic.FACTOR_FAMILIES})


def model(threshold: int = logic.NAME_MATCH_THRESHOLD, w: dict | None = None) -> dict:
    """Everything a page needs, computed once per rerun."""
    t = tables()
    hits = screening_hits(t, threshold)
    alerts = logic.build_alerts(t, hits)
    factors = logic.risk_factors(t, alerts)
    scores = logic.score(factors, w or weights(), t["APPLICATIONS"].APPLICANT_ID)
    cases = logic.case_status(t["APPLICATIONS"], scores, alerts, t["DECISIONS"])
    return {**t, "HITS": hits, "ALERTS": alerts, "FACTORS": factors, "SCORES": scores, "CASES": cases}


# ── Writes: audit events and decisions ──

def record(applicant_id: str, actor: str, action: str, detail: str, decision: str | None = None) -> None:
    now = dt.datetime.now().replace(microsecond=0)
    st.session_state.setdefault("audit", []).insert(
        0, {"EVENT_TS": now, "APPLICANT_ID": applicant_id, "ACTOR": actor, "ACTION": action, "DETAIL": detail,
            "WRITTEN_TO": "Snowflake" if is_live() else "This browser session"})
    if decision and not is_live():
        st.session_state.setdefault("new_decisions", []).append(
            {"APPLICANT_ID": applicant_id, "DECISION": decision, "DECIDED_BY": actor, "RATIONALE": detail, "DECIDED_AT": pd.Timestamp(now)})
    if is_live():
        cur = _conn().cursor()
        cur.execute(f"INSERT INTO {DB}.AUDIT_EVENTS (EVENT_TS, APPLICANT_ID, ACTOR, ACTION, DETAIL) VALUES (?, ?, ?, ?, ?)",
                    (now, applicant_id, actor, action, detail))
        if decision:
            cur.execute(f"INSERT INTO {DB}.DECISIONS (APPLICANT_ID, DECISION, DECIDED_BY, RATIONALE, DECIDED_AT) VALUES (?, ?, ?, ?, ?)",
                        (applicant_id, decision, actor, detail, now))
            _live_tables.clear()


def live_audit() -> pd.DataFrame:
    return _conn().query(f"SELECT * FROM {DB}.AUDIT_EVENTS ORDER BY EVENT_TS DESC LIMIT 50", ttl=0)


def load_into_snowflake() -> dict[str, int]:
    """Load the synthetic tables into the empty tables created by sql/kyc_setup.sql."""
    from snowflake.connector.pandas_tools import write_pandas

    raw = _conn().raw_connection
    counts = {}
    for name, df in data.generate().items():
        df = df.copy()
        for c in df.columns:
            if df[c].dtype == object and df[c].map(lambda v: isinstance(v, dt.date) and not isinstance(v, dt.datetime)).any():
                df[c] = pd.to_datetime(df[c]).dt.date
        write_pandas(raw, df, name, database="KYC_DEMO_DB", schema="KYC", auto_create_table=False, overwrite=False, use_logical_type=True)
        counts[name] = len(df)
    live_status.clear()
    _live_tables.clear()
    return counts


# ── Captured AI output (from a real live run, shown in sample mode) ──

@st.cache_data(show_spinner=False)
def captured_ai() -> dict:
    p = ROOT / "data" / "captured_ai.json"
    return json.loads(p.read_text()) if p.exists() else {"case_summaries": {}, "extractions": {}}
