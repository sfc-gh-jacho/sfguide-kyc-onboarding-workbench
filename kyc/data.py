"""Deterministic synthetic KYC data.

Every name, identifier, country and document here is generated. Countries are
coded (CTRY_A ... CTRY_L) so no real jurisdiction is labeled high risk, and
watchlist names come from an invented pool that the applicant pool never uses,
so only the planted cases below can raise screening alerts.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

AS_OF = dt.date(2026, 11, 10)
SEED = 2026
N_APPLICANTS = 500

COUNTRIES = pd.DataFrame(
    {
        "COUNTRY_CODE": [f"CTRY_{c}" for c in "ABCDEFGHIJKL"],
        "COUNTRY_RISK": ["LOW"] * 6 + ["MEDIUM"] * 3 + ["HIGH"] * 3,
    }
)

FIRST = ["Avery", "Blake", "Casey", "Devon", "Emerson", "Finley", "Harper", "Jordan", "Kendall", "Logan",
         "Morgan", "Parker", "Quinn", "Reese", "Rowan", "Sawyer", "Skyler", "Taylor", "Tatum", "Wren",
         "Ari", "Bailey", "Cameron", "Dakota", "Elliot", "Hayden", "Jamie", "Kai", "Lane", "Micah"]
LAST = ["Alder", "Birch", "Calloway", "Dunmore", "Ellison", "Fairbanks", "Garrow", "Hollis", "Ingram", "Jessup",
        "Keating", "Lockhart", "Marlow", "Northcott", "Oakley", "Pemberton", "Quill", "Radford", "Sterling", "Thorne",
        "Ashby", "Brookes", "Carver", "Dalton", "Everly", "Fenwick", "Hartley", "Langford", "Whitmore", "Yardley"]
# Invented watchlist pool: none of these appear in the applicant pool
# Background entries use first and last names that no planted case uses
WL_FIRST = ["Yorrin", "Zebulon", "Idris", "Mirek", "Ansel", "Davor", "Ludovik", "Saverin"]
WL_LAST = ["Yrsenko", "Talmorin", "Zelkovar", "Brannoch", "Castellune", "Drummaine", "Ostrovane", "Kelderic"]
BUSINESS_WORDS = ["Harbor", "Summit", "Meridian", "Cedar", "Beacon", "Granite", "Riverstone", "Lumen", "Copper", "Fieldcrest"]
BUSINESS_SUFFIX = ["Logistics LLC", "Consulting Ltd", "Foods Inc", "Design Co", "Partners LLC", "Supply Ltd"]
OCCUPATIONS = ["Software engineer", "Teacher", "Nurse", "Accountant", "Retail manager", "Architect", "Pharmacist",
               "Marketing manager", "Electrician", "Graduate student", "Retired", "Small business owner"]
PRODUCTS = ["CHECKING", "SAVINGS", "WEALTH", "WIRE_SERVICES"]
CHANNELS = ["ONLINE", "MOBILE", "BRANCH"]
FUNDS = ["Salary", "Savings", "Pension", "Business income", "Investments"]

# The stories each screen tells. Applicant IDs are stable across runs.
PLANTED = {
    "A00007": "Expired identity document",
    "A00012": "Name on document does not match application",
    "A00019": "Confirmed sanctions match",
    "A00023": "Sanctions near-match that is a false positive",
    "A00031": "Politically exposed person (PEP)",
    "A00044": "Business with opaque ownership chain",
    "A00052": "High-risk geography with high expected volume",
    "A00060": "Adverse media hit",
}


def _pick(rng, seq, n=None):
    return rng.choice(seq, size=n) if n else seq[rng.integers(len(seq))]


def generate() -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    ids = [f"A{n:05d}" for n in range(1, N_APPLICANTS + 1)]
    is_business = rng.random(N_APPLICANTS) < 0.08
    for pid in ["A00007", "A00012", "A00019", "A00023", "A00031", "A00052", "A00060"]:
        is_business[int(pid[1:]) - 1] = False
    is_business[43] = True  # A00044

    # Background residences: mostly low-risk, some medium, never high
    res = rng.choice([f"CTRY_{c}" for c in "ABCDEFGHI"], N_APPLICANTS, p=[.22, .2, .16, .12, .1, .08, .05, .04, .03])
    days_ago = rng.integers(0, 30, N_APPLICANTS)
    rows = []
    for i, aid in enumerate(ids):
        first, last = _pick(rng, FIRST), _pick(rng, LAST)
        product = rng.choice(PRODUCTS, p=[.45, .3, .15, .1])
        volume = int(rng.choice([2_000, 5_000, 8_000, 12_000, 20_000, 35_000], p=[.25, .3, .2, .12, .09, .04]))
        rows.append({
            "APPLICANT_ID": aid,
            "APPLICANT_TYPE": "BUSINESS" if is_business[i] else "INDIVIDUAL",
            "FIRST_NAME": None if is_business[i] else first,
            "LAST_NAME": None if is_business[i] else last,
            "LEGAL_NAME": f"{_pick(rng, BUSINESS_WORDS)} {_pick(rng, BUSINESS_SUFFIX)}" if is_business[i] else f"{first} {last}",
            "DATE_OF_BIRTH": None if is_business[i] else AS_OF - dt.timedelta(days=int(rng.integers(20 * 365, 75 * 365))),
            "NATIONALITY": res[i],
            "RESIDENCE_COUNTRY": res[i],
            "OCCUPATION": "Business" if is_business[i] else _pick(rng, OCCUPATIONS),
            "PRODUCT": "BUSINESS_ACCOUNT" if is_business[i] else product,
            "CHANNEL": rng.choice(CHANNELS, p=[.5, .35, .15]),
            "SOURCE_OF_FUNDS": "Business income" if is_business[i] else _pick(rng, FUNDS),
            "EXPECTED_MONTHLY_VOLUME": volume * (3 if is_business[i] else 1),
            "TAX_ID": f"9{rng.integers(10, 99)}-{rng.integers(10, 99)}-{rng.integers(1000, 9999)}",
            "EMAIL": f"{(first + '.' + last).lower()}{i + 1}@example.com",
            "PHONE": f"555-01{rng.integers(0, 100):02d}",
            "APPLIED_AT": dt.datetime.combine(AS_OF - dt.timedelta(days=int(days_ago[i])), dt.time(9)) + dt.timedelta(minutes=int(rng.integers(0, 540))),
        })
    app = pd.DataFrame(rows).set_index("APPLICANT_ID")

    def plant(aid, days=1, **kw):
        for k, v in kw.items():
            app.loc[aid, k] = v
        app.loc[aid, "APPLIED_AT"] = dt.datetime.combine(AS_OF - dt.timedelta(days=days), dt.time(10, 15))

    plant("A00007", 2, FIRST_NAME="Harper", LAST_NAME="Langford", LEGAL_NAME="Harper Langford", RESIDENCE_COUNTRY="CTRY_B", NATIONALITY="CTRY_B")
    plant("A00012", 1, FIRST_NAME="Jamie", LAST_NAME="Hollis", LEGAL_NAME="Jamie Hollis", RESIDENCE_COUNTRY="CTRY_A", NATIONALITY="CTRY_A")
    plant("A00019", 1, FIRST_NAME="Orvel", LAST_NAME="Vantorre", LEGAL_NAME="Orvel Vantorre", DATE_OF_BIRTH=dt.date(1971, 3, 9),
          NATIONALITY="CTRY_K", RESIDENCE_COUNTRY="CTRY_C", PRODUCT="WIRE_SERVICES", OCCUPATION="Import/export trader",
          SOURCE_OF_FUNDS="Business income", EXPECTED_MONTHLY_VOLUME=60_000)
    plant("A00023", 3, FIRST_NAME="Kasimer", LAST_NAME="Quistad", LEGAL_NAME="Kasimer Quistad", DATE_OF_BIRTH=dt.date(1994, 6, 21),
          NATIONALITY="CTRY_B", RESIDENCE_COUNTRY="CTRY_B", PRODUCT="CHECKING", OCCUPATION="Graduate student", EXPECTED_MONTHLY_VOLUME=2_000)
    plant("A00031", 2, FIRST_NAME="Teodric", LAST_NAME="Orvekk", LEGAL_NAME="Teodric Orvekk", DATE_OF_BIRTH=dt.date(1966, 11, 2),
          NATIONALITY="CTRY_H", RESIDENCE_COUNTRY="CTRY_H", PRODUCT="WEALTH", OCCUPATION="Deputy minister of infrastructure",
          SOURCE_OF_FUNDS="Salary and family assets", EXPECTED_MONTHLY_VOLUME=45_000)
    plant("A00044", 1, LEGAL_NAME="Northgate Holdings Ltd", RESIDENCE_COUNTRY="CTRY_D", NATIONALITY="CTRY_D",
          SOURCE_OF_FUNDS="Business income", EXPECTED_MONTHLY_VOLUME=150_000, PRODUCT="BUSINESS_ACCOUNT")
    plant("A00052", 0, FIRST_NAME="Dakota", LAST_NAME="Fenwick", LEGAL_NAME="Dakota Fenwick", RESIDENCE_COUNTRY="CTRY_J", NATIONALITY="CTRY_J",
          PRODUCT="WIRE_SERVICES", OCCUPATION="Small business owner", SOURCE_OF_FUNDS="Cash business", EXPECTED_MONTHLY_VOLUME=180_000)
    plant("A00060", 2, FIRST_NAME="Valen", LAST_NAME="Ulbrecht", LEGAL_NAME="Valen Ulbrecht", DATE_OF_BIRTH=dt.date(1979, 8, 30),
          NATIONALITY="CTRY_E", RESIDENCE_COUNTRY="CTRY_E", PRODUCT="WEALTH", OCCUPATION="Investment manager", EXPECTED_MONTHLY_VOLUME=30_000)
    for aid in ["A00007", "A00012", "A00019", "A00023", "A00031", "A00052", "A00060"]:
        f, l = app.loc[aid, "FIRST_NAME"], app.loc[aid, "LAST_NAME"]
        app.loc[aid, "EMAIL"] = f"{f}.{l}{int(aid[1:])}@example.com".lower()
    app = app.reset_index()

    # Keep planted names unique: re-draw any background applicant who shares one
    planted_names = set(app.loc[app.APPLICANT_ID.isin(PLANTED), "LEGAL_NAME"])
    clash = ~app.APPLICANT_ID.isin(PLANTED) & app.LEGAL_NAME.isin(planted_names) & (app.APPLICANT_TYPE == "INDIVIDUAL")
    for i in app.index[clash]:
        new_last = LAST[(LAST.index(app.at[i, "LAST_NAME"]) + 7) % len(LAST)]
        app.loc[i, ["LAST_NAME", "LEGAL_NAME"]] = [new_last, f"{app.at[i, 'FIRST_NAME']} {new_last}"]
        app.loc[i, "EMAIL"] = f"{app.at[i, 'FIRST_NAME']}.{new_last}{int(app.at[i, 'APPLICANT_ID'][1:])}@example.com".lower()

    # Core banking: is this an existing customer?
    core = pd.DataFrame({
        "APPLICANT_ID": app.APPLICANT_ID,
        "EXISTING_CUSTOMER": rng.random(N_APPLICANTS) < 0.3,
        "CUSTOMER_SINCE": [AS_OF.replace(year=AS_OF.year - int(y)) for y in rng.integers(1, 15, N_APPLICANTS)],
        "PRIOR_SAR_FLAG": False,
    })
    core.loc[~core.EXISTING_CUSTOMER, "CUSTOMER_SINCE"] = None

    # Identity verification vendor result
    idv = pd.DataFrame({
        "APPLICANT_ID": app.APPLICANT_ID,
        "IDV_RESULT": "VERIFIED",
        "IDV_SCORE": rng.integers(88, 100, N_APPLICANTS),
        "VENDOR": "Synthetic IDV Co.",
    })
    idv.loc[idv.APPLICANT_ID == "A00012", ["IDV_RESULT", "IDV_SCORE"]] = ["MISMATCH", 61]
    idv.loc[app.APPLICANT_TYPE == "BUSINESS", ["IDV_RESULT", "IDV_SCORE"]] = ["NOT_APPLICABLE", None]

    # Device and session signals
    dev = pd.DataFrame({
        "APPLICANT_ID": app.APPLICANT_ID,
        "DEVICE_RISK": "LOW",
        "IP_COUNTRY": app.RESIDENCE_COUNTRY,
        "VPN_DETECTED": False,
    })
    dev.loc[dev.APPLICANT_ID == "A00052", ["DEVICE_RISK", "IP_COUNTRY", "VPN_DETECTED"]] = ["HIGH", "CTRY_L", True]
    dev.loc[app.CHANNEL == "BRANCH", ["DEVICE_RISK", "IP_COUNTRY"]] = ["NOT_APPLICABLE", None]

    # Identity documents for individuals: the document normally matches the application
    ind = app[app.APPLICANT_TYPE == "INDIVIDUAL"]
    docs = pd.DataFrame({
        "APPLICANT_ID": ind.APPLICANT_ID.values,
        "DOC_TYPE": rng.choice(["PASSPORT", "DRIVERS_LICENSE", "NATIONAL_ID"], len(ind), p=[.5, .35, .15]),
        "DOC_NUMBER": [f"X{rng.integers(10_000_000, 99_999_999)}" for _ in range(len(ind))],
        "DOC_FIRST_NAME": ind.FIRST_NAME.values,
        "DOC_LAST_NAME": ind.LAST_NAME.values,
        "DOC_DATE_OF_BIRTH": ind.DATE_OF_BIRTH.values,
        "ISSUING_COUNTRY": ind.NATIONALITY.values,
        "EXPIRY_DATE": [AS_OF + dt.timedelta(days=int(d)) for d in rng.integers(200, 3000, len(ind))],
    })
    docs.loc[docs.APPLICANT_ID == "A00007", ["DOC_TYPE", "EXPIRY_DATE"]] = ["PASSPORT", dt.date(2025, 8, 14)]
    docs.loc[docs.APPLICANT_ID == "A00012", ["DOC_TYPE", "DOC_LAST_NAME"]] = ["DRIVERS_LICENSE", "Hollister"]

    # Beneficial owners for businesses: background businesses are fully transparent
    owners = []
    for aid in app.loc[app.APPLICANT_TYPE == "BUSINESS", "APPLICANT_ID"]:
        if aid == "A00044":
            continue
        a, b = _pick(rng, FIRST), _pick(rng, LAST)
        pct = int(rng.choice([51, 60, 75, 100]))
        owners.append({"APPLICANT_ID": aid, "OWNER_NAME": f"{a} {b}", "OWNER_TYPE": "INDIVIDUAL",
                       "OWNERSHIP_PCT": pct, "OWNER_COUNTRY": "CTRY_A", "UBO_DISCLOSED": True})
        if pct < 100:
            c, d = _pick(rng, FIRST), _pick(rng, LAST)
            owners.append({"APPLICANT_ID": aid, "OWNER_NAME": f"{c} {d}", "OWNER_TYPE": "INDIVIDUAL",
                           "OWNERSHIP_PCT": 100 - pct, "OWNER_COUNTRY": "CTRY_A", "UBO_DISCLOSED": True})
    owners += [
        {"APPLICANT_ID": "A00044", "OWNER_NAME": "Calder Trust Services", "OWNER_TYPE": "TRUST",
         "OWNERSHIP_PCT": 60, "OWNER_COUNTRY": "CTRY_K", "UBO_DISCLOSED": False},
        {"APPLICANT_ID": "A00044", "OWNER_NAME": "Westmere Nominees Ltd", "OWNER_TYPE": "COMPANY",
         "OWNERSHIP_PCT": 30, "OWNER_COUNTRY": "CTRY_L", "UBO_DISCLOSED": False},
        {"APPLICANT_ID": "A00044", "OWNER_NAME": "Morgan Pemberton", "OWNER_TYPE": "INDIVIDUAL",
         "OWNERSHIP_PCT": 10, "OWNER_COUNTRY": "CTRY_D", "UBO_DISCLOSED": True},
    ]
    owners = pd.DataFrame(owners)

    # Watchlist: invented entries, plus the four planted ones
    wl = []
    for k in range(40):
        wl.append({"LIST_TYPE": ["SANCTIONS", "PEP", "ADVERSE_MEDIA"][k % 3],
                   "ENTRY_NAME": f"{WL_FIRST[k % 8]} {WL_LAST[(k // 8 + k) % 8]}",
                   "ENTRY_DATE_OF_BIRTH": dt.date(1950 + k % 40, 1 + k % 12, 1 + k % 27),
                   "ENTRY_COUNTRY": f"CTRY_{'JKL'[k % 3]}", "DETAIL": "Synthetic watchlist entry"})
    wl += [
        {"LIST_TYPE": "SANCTIONS", "ENTRY_NAME": "Orvel Vantorre", "ENTRY_DATE_OF_BIRTH": dt.date(1971, 3, 9),
         "ENTRY_COUNTRY": "CTRY_K", "DETAIL": "Asset freeze: procurement network (synthetic)"},
        {"LIST_TYPE": "SANCTIONS", "ENTRY_NAME": "Kasimir Quistadt", "ENTRY_DATE_OF_BIRTH": dt.date(1958, 1, 4),
         "ENTRY_COUNTRY": "CTRY_L", "DETAIL": "Travel ban and asset freeze (synthetic)"},
        {"LIST_TYPE": "PEP", "ENTRY_NAME": "Teodric Orvekk", "ENTRY_DATE_OF_BIRTH": dt.date(1966, 11, 2),
         "ENTRY_COUNTRY": "CTRY_H", "DETAIL": "Deputy minister of infrastructure, appointed 2023 (synthetic)"},
        {"LIST_TYPE": "ADVERSE_MEDIA", "ENTRY_NAME": "Valen Ulbrecht", "ENTRY_DATE_OF_BIRTH": dt.date(1979, 8, 30),
         "ENTRY_COUNTRY": "CTRY_E", "DETAIL": "Named in a 2025 investment-fraud civil complaint (synthetic news)"},
    ]
    wl = pd.DataFrame(wl)
    wl = wl.drop_duplicates("ENTRY_NAME").reset_index(drop=True)
    wl.insert(0, "ENTRY_ID", [f"W{n:04d}" for n in range(1, len(wl) + 1)])

    # Decision history for applications older than 7 days (planted cases stay open)
    hist = []
    old = app[(pd.to_datetime(app.APPLIED_AT).dt.date <= AS_OF - dt.timedelta(days=7)) & ~app.APPLICANT_ID.isin(PLANTED)]
    for _, r in old.iterrows():
        hours = float(rng.choice([0.1, 2, 6, 20, 40], p=[.55, .15, .12, .12, .06]))
        hist.append({"APPLICANT_ID": r.APPLICANT_ID, "DECISION": "APPROVED" if rng.random() > 0.03 else "DECLINED",
                     "DECIDED_BY": "Auto-clear" if hours < 1 else f"Analyst {int(rng.integers(1, 4))}",
                     "RATIONALE": "Low risk, no alerts" if hours < 1 else "Reviewed; risk factors explained by documentation",
                     "DECIDED_AT": pd.Timestamp(r.APPLIED_AT) + pd.Timedelta(hours=hours)})
    hist = pd.DataFrame(hist)

    return {"COUNTRIES": COUNTRIES.copy(), "APPLICATIONS": app, "CORE_BANKING": core, "IDV_RESULTS": idv,
            "DEVICE_SIGNALS": dev, "DOCUMENTS": docs, "BENEFICIAL_OWNERS": owners, "WATCHLIST": wl, "DECISIONS": hist}
