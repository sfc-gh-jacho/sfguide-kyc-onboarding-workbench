/*
================================================================================
 KYC ONBOARDING WORKBENCH - LIVE SNOWFLAKE MODE SETUP
 Creates everything the Streamlit app needs in live mode:
 - KYC_DEMO_DB.KYC with empty tables (the app loads synthetic data into them)
 - Masking and row access policies, attached before any data arrives
 - An internal stage for identity documents (Cortex AI_EXTRACT)
 - A SQL screening view using JAROWINKLER_SIMILARITY
 - Roles for the four audiences in the governance screen

 This script creates its own objects and changes nothing that already exists.
 The cleanup block at the end removes everything.

 ALL DATA IS SYNTHETIC. Nothing in this script or the app uses real people,
 documents, watchlists or jurisdictions.
================================================================================
*/

-- [step:setup]
-- ============================================================================
-- STEP 1: SETUP
-- ============================================================================

-- Choose the role that runs the guide:
--   'ACCOUNTADMIN' - simplest, for sandbox accounts
--   'KYC_DEMO_ROLE' - least privilege; create it once with the block below
SET demo_role = 'ACCOUNTADMIN';

-- OPTIONAL: least-privilege role. An administrator runs this ONCE, then set
-- demo_role = 'KYC_DEMO_ROLE' above.
-- USE ROLE ACCOUNTADMIN;
-- CREATE ROLE IF NOT EXISTS KYC_DEMO_ROLE COMMENT = 'Runs the KYC onboarding workbench';
-- GRANT CREATE DATABASE  ON ACCOUNT TO ROLE KYC_DEMO_ROLE;            -- demo database
-- GRANT CREATE WAREHOUSE ON ACCOUNT TO ROLE KYC_DEMO_ROLE;            -- XSMALL demo warehouse
-- GRANT CREATE ROLE      ON ACCOUNT TO ROLE KYC_DEMO_ROLE;            -- the four audience roles
-- GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE KYC_DEMO_ROLE;    -- AI_EXTRACT and AI_COMPLETE
-- GRANT USAGE ON COMPUTE POOL <YOUR_COMPUTE_POOL> TO ROLE KYC_DEMO_ROLE;            -- Streamlit container runtime
-- GRANT USAGE ON INTEGRATION <YOUR_PYPI_INTEGRATION> TO ROLE KYC_DEMO_ROLE;         -- installs pinned packages
-- GRANT ROLE KYC_DEMO_ROLE TO ROLE SYSADMIN;                          -- admins keep control of what it creates
-- SET my_user = CURRENT_USER();
-- GRANT ROLE KYC_DEMO_ROLE TO USER IDENTIFIER($my_user);

USE ROLE IDENTIFIER($demo_role);

CREATE WAREHOUSE IF NOT EXISTS KYC_WH
    WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
USE WAREHOUSE KYC_WH;

CREATE OR REPLACE DATABASE KYC_DEMO_DB;
CREATE SCHEMA IF NOT EXISTS KYC_DEMO_DB.KYC;
USE SCHEMA KYC_DEMO_DB.KYC;

-- [step:tables]
-- ============================================================================
-- STEP 2: TABLES (empty; the app's About page loads the synthetic data)
-- ============================================================================

CREATE OR REPLACE TABLE COUNTRIES (COUNTRY_CODE VARCHAR, COUNTRY_RISK VARCHAR);

CREATE OR REPLACE TABLE APPLICATIONS (
    APPLICANT_ID VARCHAR, APPLICANT_TYPE VARCHAR, FIRST_NAME VARCHAR, LAST_NAME VARCHAR, LEGAL_NAME VARCHAR,
    DATE_OF_BIRTH DATE, NATIONALITY VARCHAR, RESIDENCE_COUNTRY VARCHAR, OCCUPATION VARCHAR, PRODUCT VARCHAR,
    CHANNEL VARCHAR, SOURCE_OF_FUNDS VARCHAR, EXPECTED_MONTHLY_VOLUME NUMBER(12, 0), TAX_ID VARCHAR,
    EMAIL VARCHAR, PHONE VARCHAR, APPLIED_AT TIMESTAMP_NTZ);

CREATE OR REPLACE TABLE CORE_BANKING (APPLICANT_ID VARCHAR, EXISTING_CUSTOMER BOOLEAN, CUSTOMER_SINCE DATE, PRIOR_SAR_FLAG BOOLEAN);
CREATE OR REPLACE TABLE IDV_RESULTS (APPLICANT_ID VARCHAR, IDV_RESULT VARCHAR, IDV_SCORE NUMBER(3, 0), VENDOR VARCHAR);
CREATE OR REPLACE TABLE DEVICE_SIGNALS (APPLICANT_ID VARCHAR, DEVICE_RISK VARCHAR, IP_COUNTRY VARCHAR, VPN_DETECTED BOOLEAN);

CREATE OR REPLACE TABLE DOCUMENTS (
    APPLICANT_ID VARCHAR, DOC_TYPE VARCHAR, DOC_NUMBER VARCHAR, DOC_FIRST_NAME VARCHAR, DOC_LAST_NAME VARCHAR,
    DOC_DATE_OF_BIRTH DATE, ISSUING_COUNTRY VARCHAR, EXPIRY_DATE DATE);

CREATE OR REPLACE TABLE BENEFICIAL_OWNERS (
    APPLICANT_ID VARCHAR, OWNER_NAME VARCHAR, OWNER_TYPE VARCHAR, OWNERSHIP_PCT NUMBER(5, 0), OWNER_COUNTRY VARCHAR, UBO_DISCLOSED BOOLEAN);

CREATE OR REPLACE TABLE WATCHLIST (
    ENTRY_ID VARCHAR, LIST_TYPE VARCHAR, ENTRY_NAME VARCHAR, ENTRY_DATE_OF_BIRTH DATE, ENTRY_COUNTRY VARCHAR, DETAIL VARCHAR);

CREATE OR REPLACE TABLE DECISIONS (APPLICANT_ID VARCHAR, DECISION VARCHAR, DECIDED_BY VARCHAR, RATIONALE VARCHAR, DECIDED_AT TIMESTAMP_NTZ);
CREATE OR REPLACE TABLE AUDIT_EVENTS (EVENT_TS TIMESTAMP_NTZ, APPLICANT_ID VARCHAR, ACTOR VARCHAR, ACTION VARCHAR, DETAIL VARCHAR);

-- Identity documents for Cortex AI_EXTRACT
CREATE OR REPLACE STAGE DOC_STAGE DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- [step:roles]
-- ============================================================================
-- STEP 3: ROLES FOR EACH AUDIENCE
-- ============================================================================

CREATE ROLE IF NOT EXISTS KYC_ANALYST;
CREATE ROLE IF NOT EXISTS KYC_SENIOR_REVIEWER;
CREATE ROLE IF NOT EXISTS KYC_AUDITOR;
CREATE ROLE IF NOT EXISTS KYC_RELATIONSHIP_MGR;
GRANT ROLE KYC_ANALYST          TO ROLE IDENTIFIER($demo_role);
GRANT ROLE KYC_SENIOR_REVIEWER  TO ROLE IDENTIFIER($demo_role);
GRANT ROLE KYC_AUDITOR          TO ROLE IDENTIFIER($demo_role);
GRANT ROLE KYC_RELATIONSHIP_MGR TO ROLE IDENTIFIER($demo_role);

-- [step:policies]
-- ============================================================================
-- STEP 4: MASKING AND ROW ACCESS POLICIES
-- ============================================================================
-- The role that owns the data (the one running this script, and the app's
-- owner role) sees full values. The audience roles see what the governance
-- screen shows.

CREATE OR REPLACE MASKING POLICY kyc_mask_tax_id AS (val STRING) RETURNS STRING ->
    CASE
        WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'KYC_DEMO_ROLE', 'KYC_SENIOR_REVIEWER') THEN val
        WHEN CURRENT_ROLE() IN ('KYC_ANALYST', 'KYC_AUDITOR') THEN '***-**-' || RIGHT(val, 4)
        ELSE '***-**-****'
    END;

-- A masking policy returns the column's own type, so "year only" becomes January 1 of that year
CREATE OR REPLACE MASKING POLICY kyc_mask_dob AS (val DATE) RETURNS DATE ->
    CASE
        WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'KYC_DEMO_ROLE', 'KYC_SENIOR_REVIEWER') THEN val
        WHEN CURRENT_ROLE() IN ('KYC_ANALYST', 'KYC_AUDITOR') THEN DATE_FROM_PARTS(YEAR(val), 1, 1)
        ELSE NULL
    END;

CREATE OR REPLACE MASKING POLICY kyc_mask_doc_number AS (val STRING) RETURNS STRING ->
    CASE
        WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'KYC_DEMO_ROLE', 'KYC_SENIOR_REVIEWER') THEN val
        WHEN CURRENT_ROLE() = 'KYC_ANALYST' THEN '*****' || RIGHT(val, 3)
        ELSE '********'
    END;

CREATE OR REPLACE MASKING POLICY kyc_mask_email AS (val STRING) RETURNS STRING ->
    CASE
        WHEN CURRENT_ROLE() IN ('ACCOUNTADMIN', 'KYC_DEMO_ROLE', 'KYC_SENIOR_REVIEWER', 'KYC_ANALYST', 'KYC_RELATIONSHIP_MGR') THEN val
        ELSE '****@' || SPLIT_PART(val, '@', 2)
    END;

-- Relationship managers see only their book (here: the online channel)
CREATE OR REPLACE ROW ACCESS POLICY kyc_book_policy AS (channel_val VARCHAR) RETURNS BOOLEAN ->
    CURRENT_ROLE() <> 'KYC_RELATIONSHIP_MGR' OR channel_val = 'ONLINE';

ALTER TABLE APPLICATIONS MODIFY COLUMN TAX_ID        SET MASKING POLICY kyc_mask_tax_id;
ALTER TABLE APPLICATIONS MODIFY COLUMN DATE_OF_BIRTH SET MASKING POLICY kyc_mask_dob;
ALTER TABLE APPLICATIONS MODIFY COLUMN EMAIL         SET MASKING POLICY kyc_mask_email;
ALTER TABLE DOCUMENTS    MODIFY COLUMN DOC_NUMBER    SET MASKING POLICY kyc_mask_doc_number;
ALTER TABLE APPLICATIONS ADD ROW ACCESS POLICY kyc_book_policy ON (CHANNEL);

-- [step:screening]
-- ============================================================================
-- STEP 5: SQL SCREENING VIEW
-- ============================================================================
-- The app runs the same comparison with its own threshold. This view gives
-- SQL users the default (85) result directly.

CREATE OR REPLACE VIEW SCREENING_HITS AS
SELECT a.APPLICANT_ID, a.LEGAL_NAME, w.ENTRY_ID, w.ENTRY_NAME, w.LIST_TYPE,
       JAROWINKLER_SIMILARITY(a.LEGAL_NAME, w.ENTRY_NAME)  AS NAME_SCORE,
       (a.DATE_OF_BIRTH = w.ENTRY_DATE_OF_BIRTH)           AS DOB_MATCH,
       (w.ENTRY_COUNTRY IN (a.NATIONALITY, a.RESIDENCE_COUNTRY)) AS COUNTRY_MATCH
FROM APPLICATIONS a
CROSS JOIN WATCHLIST w
WHERE JAROWINKLER_SIMILARITY(a.LEGAL_NAME, w.ENTRY_NAME) >= 85;

-- [step:grants]
-- ============================================================================
-- STEP 6: READ ACCESS FOR THE AUDIENCE ROLES
-- ============================================================================

GRANT USAGE ON WAREHOUSE KYC_WH TO ROLE KYC_ANALYST;
GRANT USAGE ON WAREHOUSE KYC_WH TO ROLE KYC_SENIOR_REVIEWER;
GRANT USAGE ON WAREHOUSE KYC_WH TO ROLE KYC_AUDITOR;
GRANT USAGE ON WAREHOUSE KYC_WH TO ROLE KYC_RELATIONSHIP_MGR;
GRANT USAGE ON DATABASE KYC_DEMO_DB TO ROLE KYC_ANALYST;
GRANT USAGE ON DATABASE KYC_DEMO_DB TO ROLE KYC_SENIOR_REVIEWER;
GRANT USAGE ON DATABASE KYC_DEMO_DB TO ROLE KYC_AUDITOR;
GRANT USAGE ON DATABASE KYC_DEMO_DB TO ROLE KYC_RELATIONSHIP_MGR;
GRANT USAGE ON SCHEMA KYC_DEMO_DB.KYC TO ROLE KYC_ANALYST;
GRANT USAGE ON SCHEMA KYC_DEMO_DB.KYC TO ROLE KYC_SENIOR_REVIEWER;
GRANT USAGE ON SCHEMA KYC_DEMO_DB.KYC TO ROLE KYC_AUDITOR;
GRANT USAGE ON SCHEMA KYC_DEMO_DB.KYC TO ROLE KYC_RELATIONSHIP_MGR;
GRANT SELECT ON ALL TABLES IN SCHEMA KYC_DEMO_DB.KYC TO ROLE KYC_ANALYST;
GRANT SELECT ON ALL TABLES IN SCHEMA KYC_DEMO_DB.KYC TO ROLE KYC_SENIOR_REVIEWER;
GRANT SELECT ON ALL TABLES IN SCHEMA KYC_DEMO_DB.KYC TO ROLE KYC_AUDITOR;
GRANT SELECT ON TABLE APPLICATIONS TO ROLE KYC_RELATIONSHIP_MGR;

-- [step:verify]
-- ============================================================================
-- STEP 7: VERIFY THE POLICIES (run after loading data from the app)
-- ============================================================================
-- Each test role relies only on its own grants
USE SECONDARY ROLES NONE;

USE ROLE KYC_ANALYST;
SELECT 'KYC_ANALYST' AS role, APPLICANT_ID, TAX_ID, DATE_OF_BIRTH, EMAIL FROM KYC_DEMO_DB.KYC.APPLICATIONS WHERE APPLICANT_ID = 'A00019';
USE ROLE KYC_AUDITOR;
SELECT 'KYC_AUDITOR' AS role, APPLICANT_ID, TAX_ID, DATE_OF_BIRTH, EMAIL FROM KYC_DEMO_DB.KYC.APPLICATIONS WHERE APPLICANT_ID = 'A00019';
USE ROLE KYC_SENIOR_REVIEWER;
SELECT 'KYC_SENIOR_REVIEWER' AS role, APPLICANT_ID, TAX_ID, DATE_OF_BIRTH, EMAIL FROM KYC_DEMO_DB.KYC.APPLICATIONS WHERE APPLICANT_ID = 'A00019';
USE ROLE KYC_RELATIONSHIP_MGR;
SELECT 'KYC_RELATIONSHIP_MGR' AS role, COUNT(*) AS rows_visible FROM KYC_DEMO_DB.KYC.APPLICATIONS;
USE ROLE IDENTIFIER($demo_role);
SELECT * FROM KYC_DEMO_DB.KYC.SCREENING_HITS ORDER BY NAME_SCORE DESC;

-- [step:cleanup]
-- ============================================================================
-- STEP 8: CLEANUP (Optional - uncomment to remove everything)
-- ============================================================================

-- USE ROLE IDENTIFIER($demo_role);
-- USE SECONDARY ROLES ALL;               -- restore your usual setting if you use it
-- DROP DATABASE IF EXISTS KYC_DEMO_DB;    -- tables, stage, view, policies and the Streamlit app
-- DROP WAREHOUSE IF EXISTS KYC_WH;
-- DROP ROLE IF EXISTS KYC_ANALYST;
-- DROP ROLE IF EXISTS KYC_SENIOR_REVIEWER;
-- DROP ROLE IF EXISTS KYC_AUDITOR;
-- DROP ROLE IF EXISTS KYC_RELATIONSHIP_MGR;
-- UNSET demo_role;
-- If you created the least-privilege role, an administrator removes it:
-- USE ROLE ACCOUNTADMIN;
-- DROP ROLE IF EXISTS KYC_DEMO_ROLE;
