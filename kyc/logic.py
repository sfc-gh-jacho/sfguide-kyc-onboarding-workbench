"""Screening, alerts, explainable risk scoring and case status.

The same rules run in both modes. In live Snowflake mode the screening step
uses JAROWINKLER_SIMILARITY in SQL (see sql/kyc_setup.sql); jaro_winkler()
below is a Python port used in sample-data mode.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from kyc.data import AS_OF

NAME_MATCH_THRESHOLD = 85

FACTOR_FAMILIES = ["Geography", "Product and activity", "Screening", "Identity", "Ownership", "Device"]

ALERT_INFO = {
    "SANCTIONS_MATCH": ("Sanctions match", "Screening", "red"),
    "SANCTIONS_POSSIBLE": ("Possible sanctions match", "Screening", "orange"),
    "PEP_MATCH": ("Politically exposed person", "Screening", "orange"),
    "ADVERSE_MEDIA": ("Adverse media", "Screening", "orange"),
    "DOC_EXPIRED": ("Expired identity document", "Identity", "orange"),
    "DOC_NAME_MISMATCH": ("Document name mismatch", "Identity", "orange"),
    "IDV_MISMATCH": ("Identity vendor mismatch", "Identity", "orange"),
    "OWNERSHIP_OPAQUE": ("Undisclosed beneficial owner", "Ownership", "red"),
    "HIGH_RISK_GEOGRAPHY": ("High-risk geography", "Geography", "orange"),
}


def jaro_winkler(a: str, b: str) -> int:
    """Jaro-Winkler similarity on a 0-100 scale, case-insensitive."""
    a, b = (a or "").lower(), (b or "").lower()
    if not a or not b:
        return 0
    if a == b:
        return 100
    window = max(max(len(a), len(b)) // 2 - 1, 0)
    a_flags, b_flags = [False] * len(a), [False] * len(b)
    matches = 0
    for i, ch in enumerate(a):
        for j in range(max(0, i - window), min(len(b), i + window + 1)):
            if not b_flags[j] and b[j] == ch:
                a_flags[i] = b_flags[j] = True
                matches += 1
                break
    if not matches:
        return 0
    a_m = [c for c, f in zip(a, a_flags) if f]
    b_m = [c for c, f in zip(b, b_flags) if f]
    transpositions = sum(x != y for x, y in zip(a_m, b_m)) / 2
    jaro = (matches / len(a) + matches / len(b) + (matches - transpositions) / matches) / 3
    prefix = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        prefix += 1
    return int(round((jaro + prefix * 0.1 * (1 - jaro)) * 100))


def screen(apps: pd.DataFrame, watchlist: pd.DataFrame) -> pd.DataFrame:
    """Compare every applicant legal name with every watchlist entry."""
    out = []
    for app in apps.itertuples():
        for w in watchlist.itertuples():
            score = jaro_winkler(app.LEGAL_NAME, w.ENTRY_NAME)
            if score >= NAME_MATCH_THRESHOLD:
                out.append({"APPLICANT_ID": app.APPLICANT_ID, "ENTRY_ID": w.ENTRY_ID, "NAME_SCORE": score})
    return pd.DataFrame(out, columns=["APPLICANT_ID", "ENTRY_ID", "NAME_SCORE"])


def enrich_hits(hits: pd.DataFrame, apps: pd.DataFrame, watchlist: pd.DataFrame) -> pd.DataFrame:
    """Add the corroborating fields an analyst compares: date of birth and country."""
    if hits.empty:
        return hits.assign(LIST_TYPE=[], DOB_MATCH=[], COUNTRY_MATCH=[], STRENGTH=[])
    h = hits.merge(apps[["APPLICANT_ID", "LEGAL_NAME", "DATE_OF_BIRTH", "NATIONALITY", "RESIDENCE_COUNTRY"]], on="APPLICANT_ID")
    h = h.merge(watchlist, on="ENTRY_ID")
    h["DOB_MATCH"] = pd.to_datetime(h.DATE_OF_BIRTH) == pd.to_datetime(h.ENTRY_DATE_OF_BIRTH)
    h["COUNTRY_MATCH"] = (h.NATIONALITY == h.ENTRY_COUNTRY) | (h.RESIDENCE_COUNTRY == h.ENTRY_COUNTRY)
    h["STRENGTH"] = "POSSIBLE"
    h.loc[(h.NAME_SCORE >= 95) & h.DOB_MATCH, "STRENGTH"] = "STRONG"
    return h


def build_alerts(t: dict[str, pd.DataFrame], hits: pd.DataFrame) -> pd.DataFrame:
    apps, docs, idv, owners, dev = t["APPLICATIONS"], t["DOCUMENTS"], t["IDV_RESULTS"], t["BENEFICIAL_OWNERS"], t["DEVICE_SIGNALS"]
    high = set(t["COUNTRIES"].loc[t["COUNTRIES"].COUNTRY_RISK == "HIGH", "COUNTRY_CODE"])
    rows = []
    for h in hits.itertuples():
        if h.LIST_TYPE == "SANCTIONS":
            code = "SANCTIONS_MATCH" if h.STRENGTH == "STRONG" else "SANCTIONS_POSSIBLE"
        elif h.LIST_TYPE == "PEP":
            code = "PEP_MATCH"
        else:
            code = "ADVERSE_MEDIA"
        rows.append((h.APPLICANT_ID, code, f"{h.ENTRY_NAME} ({h.ENTRY_ID}), name similarity {h.NAME_SCORE}"))
    expiry = pd.to_datetime(docs.EXPIRY_DATE).dt.date
    for d in docs[expiry < AS_OF].itertuples():
        rows.append((d.APPLICANT_ID, "DOC_EXPIRED", f"{d.DOC_TYPE.replace('_', ' ').title()} expired {d.EXPIRY_DATE}"))
    m = docs.merge(apps[["APPLICANT_ID", "FIRST_NAME", "LAST_NAME"]], on="APPLICANT_ID")
    for d in m[(m.DOC_FIRST_NAME != m.FIRST_NAME) | (m.DOC_LAST_NAME != m.LAST_NAME)].itertuples():
        rows.append((d.APPLICANT_ID, "DOC_NAME_MISMATCH", f"Document shows {d.DOC_FIRST_NAME} {d.DOC_LAST_NAME}; application shows {d.FIRST_NAME} {d.LAST_NAME}"))
    for r in idv[idv.IDV_RESULT == "MISMATCH"].itertuples():
        rows.append((r.APPLICANT_ID, "IDV_MISMATCH", f"Vendor result MISMATCH, score {int(r.IDV_SCORE)}"))
    for aid, g in owners[~owners.UBO_DISCLOSED.astype(bool)].groupby("APPLICANT_ID"):
        rows.append((aid, "OWNERSHIP_OPAQUE", f"{int(g.OWNERSHIP_PCT.sum())}% held by entities without a disclosed beneficial owner"))
    geo = apps[apps.RESIDENCE_COUNTRY.isin(high) | apps.NATIONALITY.isin(high)]
    for a in geo.itertuples():
        rows.append((a.APPLICANT_ID, "HIGH_RISK_GEOGRAPHY", f"Residence {a.RESIDENCE_COUNTRY}, nationality {a.NATIONALITY}"))
    for a in owners[owners.OWNER_COUNTRY.isin(high)].drop_duplicates("APPLICANT_ID").itertuples():
        rows.append((a.APPLICANT_ID, "HIGH_RISK_GEOGRAPHY", f"Owner domiciled in {a.OWNER_COUNTRY}"))
    for d in dev[dev.IP_COUNTRY.isin(high)].itertuples():
        rows.append((d.APPLICANT_ID, "HIGH_RISK_GEOGRAPHY", f"Session from {d.IP_COUNTRY}" + (" via VPN" if d.VPN_DETECTED else "")))
    al = pd.DataFrame(rows, columns=["APPLICANT_ID", "ALERT_TYPE", "DETAIL"])
    al = al.drop_duplicates(["APPLICANT_ID", "ALERT_TYPE"]).reset_index(drop=True)
    al["ALERT_LABEL"] = al.ALERT_TYPE.map(lambda c: ALERT_INFO[c][0])
    al["FAMILY"] = al.ALERT_TYPE.map(lambda c: ALERT_INFO[c][1])
    return al


def risk_factors(t: dict[str, pd.DataFrame], alerts: pd.DataFrame) -> pd.DataFrame:
    """One row per applicant and contributing factor, with base points."""
    apps, dev = t["APPLICATIONS"], t["DEVICE_SIGNALS"]
    risk = dict(zip(t["COUNTRIES"].COUNTRY_CODE, t["COUNTRIES"].COUNTRY_RISK))
    geo_pts = {"LOW": 0, "MEDIUM": 10, "HIGH": 30}
    rows = []
    for a in apps.itertuples():
        r = risk[a.RESIDENCE_COUNTRY]
        if geo_pts[r]:
            rows.append((a.APPLICANT_ID, "Geography", f"Residence in {r.lower()}-risk country", geo_pts[r]))
        if a.NATIONALITY != a.RESIDENCE_COUNTRY and risk[a.NATIONALITY] == "HIGH":
            rows.append((a.APPLICANT_ID, "Geography", "Nationality of high-risk country", 10))
        prod = {"WIRE_SERVICES": 15, "WEALTH": 10, "BUSINESS_ACCOUNT": 10}.get(a.PRODUCT)
        if prod:
            rows.append((a.APPLICANT_ID, "Product and activity", f"Product: {a.PRODUCT.replace('_', ' ').lower()}", prod))
        if a.EXPECTED_MONTHLY_VOLUME >= 100_000:
            rows.append((a.APPLICANT_ID, "Product and activity", "Expected volume of $100K+ a month", 15))
        elif a.EXPECTED_MONTHLY_VOLUME >= 40_000:
            rows.append((a.APPLICANT_ID, "Product and activity", "Expected volume of $40K+ a month", 8))
        if "cash" in a.SOURCE_OF_FUNDS.lower():
            rows.append((a.APPLICANT_ID, "Product and activity", "Cash-intensive source of funds", 15))
    pts = {"SANCTIONS_MATCH": 60, "SANCTIONS_POSSIBLE": 25, "PEP_MATCH": 30, "ADVERSE_MEDIA": 20,
           "DOC_EXPIRED": 20, "DOC_NAME_MISMATCH": 15, "IDV_MISMATCH": 10, "OWNERSHIP_OPAQUE": 30}
    for al in alerts[alerts.ALERT_TYPE.isin(pts)].itertuples():
        rows.append((al.APPLICANT_ID, al.FAMILY, al.ALERT_LABEL, pts[al.ALERT_TYPE]))
    for d in dev[dev.DEVICE_RISK == "HIGH"].itertuples():
        rows.append((d.APPLICANT_ID, "Device", "High-risk device or VPN session", 10))
    return pd.DataFrame(rows, columns=["APPLICANT_ID", "FAMILY", "FACTOR", "BASE_POINTS"])


def score(factors: pd.DataFrame, weights: dict[str, float], applicant_ids) -> pd.DataFrame:
    f = factors.assign(POINTS=factors.BASE_POINTS * factors.FAMILY.map(weights).fillna(1.0))
    s = f.groupby("APPLICANT_ID").POINTS.sum().reindex(applicant_ids, fill_value=0).clip(upper=100).round()
    out = s.rename("RISK_SCORE").reset_index().rename(columns={"index": "APPLICANT_ID"})
    out["RISK_RATING"] = pd.cut(out.RISK_SCORE, [-1, 24, 49, 101], labels=["LOW", "MEDIUM", "HIGH"]).astype(str)
    return out


def case_status(apps: pd.DataFrame, scores: pd.DataFrame, alerts: pd.DataFrame, decisions: pd.DataFrame) -> pd.DataFrame:
    """Where each application sits in the workflow today."""
    c = apps[["APPLICANT_ID", "LEGAL_NAME", "APPLICANT_TYPE", "PRODUCT", "CHANNEL", "APPLIED_AT"]].merge(scores, on="APPLICANT_ID")
    n_alerts = alerts.groupby("APPLICANT_ID").size()
    c["OPEN_ALERTS"] = c.APPLICANT_ID.map(n_alerts).fillna(0).astype(int)
    last = decisions.sort_values("DECIDED_AT").groupby("APPLICANT_ID").tail(1).set_index("APPLICANT_ID") if len(decisions) else pd.DataFrame()
    status = []
    for r in c.itertuples():
        if r.APPLICANT_ID in last.index:
            d = last.loc[r.APPLICANT_ID, "DECISION"]
            status.append({"APPROVED": "Approved", "DECLINED": "Declined", "EDD_REQUESTED": "Enhanced due diligence"}[d])
        elif r.OPEN_ALERTS:
            status.append("Alert review")
        elif r.RISK_RATING == "LOW":
            status.append("Auto-cleared")
        else:
            status.append("Analyst review")
    c["STATUS"] = status
    c["AGE_HOURS"] = ((pd.Timestamp(dt.datetime.combine(AS_OF, dt.time(18))) - pd.to_datetime(c.APPLIED_AT)).dt.total_seconds() / 3600).round(1)
    return c
