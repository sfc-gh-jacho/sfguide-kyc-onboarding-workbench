# KYC Onboarding Workbench

**Owner:** Janet Cho · **Last reviewed:** November 2026 · **License:** [Apache 2.0](LICENSE)

An interactive Streamlit workbench that follows each new customer through an end-to-end know-your-customer (KYC) onboarding workflow on Snowflake:

1. **Onboarding intake:** applications joined with core banking, identity-vendor and device data
2. **Identity and documents:** Cortex `AI_EXTRACT` reads the ID document; mismatches and expiry raise alerts
3. **Risk assessment:** an explainable, factor-based score with what-if weights
4. **Screening alerts:** sanctions, PEP and adverse-media fuzzy matching with `JAROWINKLER_SIMILARITY`
5. **Analyst decision:** a Cortex `AI_COMPLETE` case summary, a required rationale, and an audit trail

There are also **governance** (role-based masking and row access) and **about** pages.

- **Landing page:** https://sfc-gh-jacho.github.io/sfguide-kyc-onboarding-workbench/
- **Try it in your browser (no account):** https://sfc-gh-jacho.github.io/sfguide-kyc-onboarding-workbench/try/

## Two modes, one codebase

| | Sample data mode | Live Snowflake mode |
|---|---|---|
| Where | Your browser (stlite), or `streamlit run` on a laptop | Streamlit in Snowflake, in your account |
| Data | Generated in the app, deterministic | Same data, loaded into `KYC_DEMO_DB.KYC` |
| Screening | Python Jaro-Winkler (same scores as SQL) | `JAROWINKLER_SIMILARITY` in SQL |
| AI | **Captured** output from a real Cortex run, labeled; template text elsewhere, labeled | Live `AI_EXTRACT` and `AI_COMPLETE` |
| Governance | View-as switcher simulates each role | Masking and row access policies on the tables |
| Decisions | Kept in the browser session | Written to `DECISIONS` and `AUDIT_EVENTS` |

The app chooses its mode automatically. It switches to live mode when it can reach the `KYC_DEMO_DB.KYC` tables, and a sidebar switch lets you go back to sample data.

## Try it locally (no account)

```bash
git clone https://github.com/sfc-gh-jacho/sfguide-kyc-onboarding-workbench.git
cd sfguide-kyc-onboarding-workbench
python3 -m venv .venv && source .venv/bin/activate
pip install "streamlit==1.65.0" pillow
KYC_SAMPLE_ONLY=1 streamlit run streamlit_app.py
```

`KYC_SAMPLE_ONLY=1` stops the app from trying to connect to Snowflake.

## Run it live in your Snowflake account

### Prerequisites

- **Enterprise Edition or higher** for masking and row access policies
- **Cortex AI functions** in your region (`AI_EXTRACT`, and `AI_COMPLETE` with `llama3.3-70b`). Enable cross-region inference or change `MODEL` in `kyc/ai.py` if the model isn't available.
- **A compute pool** for Streamlit's container runtime (`SHOW PARAMETERS LIKE 'DEFAULT_STREAMLIT_COMPUTE_POOL' IN ACCOUNT`)
- **An external access integration for PyPI**, because `pyproject.toml` pins Streamlit 1.65.0 to match the in-browser version
- **Snowflake CLI 3.14 or later**
- **Tested with:** Snowflake CLI 3.31, Streamlit 1.65.0, stlite 1.12.2, and the `SYSTEM$ST_CONTAINER_RUNTIME_PY3_11` runtime on an AWS Enterprise Edition account

### Steps

1. **Run the setup script.** Run [`sql/kyc_setup.sql`](sql/kyc_setup.sql) Steps 1–6 in a Snowsight worksheet. They create `KYC_DEMO_DB.KYC`, the `KYC_WH` warehouse (XSMALL, 60-second auto-suspend), empty tables with policies attached, a document stage, a SQL screening view, and four audience roles.
2. **Set your account names.** In `snowflake.yml`, set `compute_pool` and `external_access_integrations` to the names in your account.
3. **Deploy the app.**
   ```bash
   snow streamlit deploy kyc_workbench --replace
   ```
4. **Load the data.** Open the app, go to **About this example**, and select **Load synthetic data**. This writes the same generated data the sample mode uses.
5. **Check the policies.** Optionally, run Step 7 of the script to see each audience role's view.
6. **Clean up.** When you're done, uncomment and run Step 8. Dropping `KYC_DEMO_DB` also removes the Streamlit app.

### Least-privilege option (no ACCOUNTADMIN)

The script starts with `SET demo_role = 'ACCOUNTADMIN';`. To run without ACCOUNTADMIN, an administrator runs the commented block at the top of Step 1 once:

```sql
USE ROLE ACCOUNTADMIN;
CREATE ROLE IF NOT EXISTS KYC_DEMO_ROLE;
GRANT CREATE DATABASE  ON ACCOUNT TO ROLE KYC_DEMO_ROLE;
GRANT CREATE WAREHOUSE ON ACCOUNT TO ROLE KYC_DEMO_ROLE;
GRANT CREATE ROLE      ON ACCOUNT TO ROLE KYC_DEMO_ROLE;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE KYC_DEMO_ROLE;
GRANT USAGE ON COMPUTE POOL <YOUR_COMPUTE_POOL> TO ROLE KYC_DEMO_ROLE;
GRANT USAGE ON INTEGRATION <YOUR_PYPI_INTEGRATION> TO ROLE KYC_DEMO_ROLE;
GRANT ROLE KYC_DEMO_ROLE TO ROLE SYSADMIN;
GRANT ROLE KYC_DEMO_ROLE TO USER <YOUR_USER>;
```

Then set `demo_role = 'KYC_DEMO_ROLE'` and deploy with that role. The live Snowflake path was tested as ACCOUNTADMIN; the least-privilege grants follow the documented requirements but weren't run end to end for this app.

## What gets created

| Object | Name |
|---|---|
| Database and schema | `KYC_DEMO_DB.KYC` |
| Warehouse | `KYC_WH` (XSMALL, 60-second auto-suspend) |
| Tables | `APPLICATIONS` (500), `CORE_BANKING`, `IDV_RESULTS`, `DEVICE_SIGNALS`, `DOCUMENTS` (464), `BENEFICIAL_OWNERS`, `WATCHLIST` (44), `COUNTRIES`, `DECISIONS`, `AUDIT_EVENTS` |
| Stage and view | `DOC_STAGE` (identity documents for `AI_EXTRACT`), `SCREENING_HITS` |
| Policies | `kyc_mask_tax_id`, `kyc_mask_dob`, `kyc_mask_doc_number`, `kyc_mask_email`, `kyc_book_policy` |
| Roles | `KYC_ANALYST`, `KYC_SENIOR_REVIEWER`, `KYC_AUDITOR`, `KYC_RELATIONSHIP_MGR` |
| Streamlit app | `KYC_ONBOARDING_WORKBENCH` |

## Cost and time

- **Time:**
  - About 10 minutes to click through in your browser
  - About 20 minutes to set up live mode
- **Compute:**
  - Setup and the data load run on an XSMALL warehouse for well under a minute.
  - Each Cortex call takes a few seconds and uses a few thousand tokens. Capturing the sample-mode AI output took 8 summaries and 8 extractions.
  - The Streamlit container uses its compute pool while the app is open.
- **Validation:** tested on November 11, 2026 on an Enterprise Edition account (AWS):
  - Setup script ran, and the data loaded from the app.
  - Policies were verified for each role.
  - SQL screening scores matched the Python scores exactly.
  - Live `AI_EXTRACT` read all five fields correctly on all 8 captured documents.
  - Live decision and audit writes succeeded.
  - The app deployed to Streamlit in Snowflake and `SHOW STREAMLITS` confirmed it.
  - All eight pages ran headlessly with no exceptions, and the in-browser build loaded in about 12 seconds.

## Known limitations

- **Planted cases, not detection performance.** Eight applicants are planted to show each alert type, and background data was generated so it can't trip a rule (the closest background name scores 79 against the threshold of 85). On real data these rules will produce false positives and need tuning.
- **AI output varies.** Captured summaries come from one run of `llama3.3-70b` at temperature 0, and live runs may word things differently. Applicants without captured output show labeled template text in sample mode.
- **Role switching is simulated in the app.** Streamlit in Snowflake runs with the owner's rights, so the governance page's view-as switcher applies the same rules in Python. The policies themselves were verified in SQL with each role (Step 7).
- **Decisions in sample mode aren't saved.** They last only as long as your browser tab.
- **The browser version uses a CDN.** stlite and Pyodide load from jsDelivr, because the runtime is over 100 MB and impractical to bundle. The landing page itself loads no third-party resources.
- **The first browser load is slow.** Expect 10 to 40 seconds while Python loads; later visits are faster.
- **Risk scoring runs in the app.** For production scale, move the scoring into a SQL view or Dynamic Table.

## Customize with Cortex Code

[Cortex Code](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code) can adapt this workbench to your environment. Open the repo folder in Cortex Code and try prompts like:

- "Explain this workbench's data model and map it to my onboarding, identity-vendor and screening tables without changing any objects."
- "Replace the synthetic watchlist with my licensed list's table, keep the threshold configurable, and show me the false-positive rate at 80, 85 and 90 before I pick one."
- "Move the risk scoring into a SQL view, then a Dynamic Table, and update the app to read it. Propose least-privilege grants for the analyst role first."

Ask it to review the plan with you before it creates or changes any objects in your account.

## Repository layout

```
LICENSE                     Apache License 2.0
index.html, styles.css,     GitHub Pages landing page (no third-party requests)
  script.js
try/index.html              In-browser version (stlite)
docs/images/                Screenshots of the running app
streamlit_app.py            App entry point and navigation
app_pages/                  One file per screen
kyc/data.py                 Deterministic synthetic data generator
kyc/logic.py                Screening, alerts, risk scoring, case status
kyc/source.py               Sample vs live data, Snowflake reads and writes
kyc/ai.py                   Cortex AI_EXTRACT and AI_COMPLETE, captured fallbacks
kyc/documents.py            Renders synthetic identity documents
kyc/ui.py                   Shared UI and view-as masking rules
data/captured_ai.json       AI output captured from a real live run
sql/kyc_setup.sql           Live-mode setup, policy checks and cleanup
snowflake.yml               Streamlit in Snowflake manifest
pyproject.toml              Pinned dependencies for live mode
.streamlit/config.toml      Snowflake theme
static/                     Inter and JetBrains Mono fonts (SIL Open Font License)
```

## License

Licensed under the [Apache License, Version 2.0](LICENSE). The bundled Inter and JetBrains Mono fonts are under the SIL Open Font License.

## Disclaimer

This is an illustrative example provided as-is. It is not an official Snowflake product and is not supported by Snowflake Support. It is not regulatory or compliance advice.

Everything in it is synthetic:
- Applicants, documents, vendor results and watchlist entries are generated.
- Countries are coded (`CTRY_A`–`CTRY_L`), so no real jurisdiction is labeled high risk.
- Emails use the reserved `@example.com` domain, tax IDs start with 9, and phone numbers use the fictional 555-01xx range.
- Identity cards use a generic layout marked **SYNTHETIC SAMPLE**.

Rules, thresholds and scores are simplified for demonstration. The repository contains no credentials, account identifiers or connection details. Review and test before any production use.
