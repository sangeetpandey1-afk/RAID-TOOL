-- =====================================================================
-- RAID MANAGEMENT SYSTEM — SQLite Schema (Phase 1)
-- 15 tables covering consumers, cases, payments, notices, audit
-- All TEXT timestamps stored as ISO-8601 (sqlite "datetime('now')")
-- =====================================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ---------- 1. CONSUMER MASTER -----------------------------------------
CREATE TABLE IF NOT EXISTS consumers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account_number  TEXT UNIQUE NOT NULL,
    name            TEXT,
    father_name     TEXT,
    address         TEXT,
    village         TEXT,
    landmark        TEXT,
    post_office     TEXT,
    pin_code        TEXT,
    tehsil          TEXT,
    district        TEXT,
    mobile          TEXT,
    load_value      REAL,
    load_unit       TEXT,
    supply_type     TEXT,
    category        TEXT,
    sub_substation  TEXT,
    connection_status TEXT,
    div_code        TEXT,
    sc_number       TEXT,
    raw_payload     TEXT,             -- JSON of all original columns (for traceability)
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_consumers_name      ON consumers(name);
CREATE INDEX IF NOT EXISTS idx_consumers_father    ON consumers(father_name);
CREATE INDEX IF NOT EXISTS idx_consumers_village   ON consumers(village);
CREATE INDEX IF NOT EXISTS idx_consumers_div       ON consumers(div_code);
CREATE INDEX IF NOT EXISTS idx_consumers_sc        ON consumers(sc_number);
CREATE INDEX IF NOT EXISTS idx_consumers_mobile    ON consumers(mobile);

-- ---------- 2. HISTORICAL CASES (ALL DATA.xlsx) ------------------------
CREATE TABLE IF NOT EXISTS historical_cases (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    div_no           TEXT,
    name             TEXT,
    father_name      TEXT,
    village          TEXT,
    account_id       TEXT,
    case_date        TEXT,            -- ISO date
    assessment_amount REAL,
    fir_number       TEXT,
    section          TEXT,            -- "dhara"
    raw_payload      TEXT,
    source           TEXT DEFAULT 'historical',
    imported_at      TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_hist_account  ON historical_cases(account_id);
CREATE INDEX IF NOT EXISTS idx_hist_name     ON historical_cases(name);
CREATE INDEX IF NOT EXISTS idx_hist_father   ON historical_cases(father_name);
CREATE INDEX IF NOT EXISTS idx_hist_village  ON historical_cases(village);
CREATE INDEX IF NOT EXISTS idx_hist_date     ON historical_cases(case_date);

-- ---------- 3. CURRENT (ACTIVE) CASES (raid excell 25-26) --------------
CREATE TABLE IF NOT EXISTS current_cases (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    online_no         TEXT,
    div_no            TEXT,
    name              TEXT,
    father_name       TEXT,
    village           TEXT,
    connection_no     TEXT,
    inspection_date   TEXT,
    section           TEXT,
    total_assessment  REAL,
    notice_status     TEXT,
    payment_status    TEXT,
    raw_payload       TEXT,
    imported_at       TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_current_online ON current_cases(online_no) WHERE online_no IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_current_div     ON current_cases(div_no);
CREATE INDEX IF NOT EXISTS idx_current_name    ON current_cases(name);
CREATE INDEX IF NOT EXISTS idx_current_account ON current_cases(connection_no);

-- ---------- 4. DEVICE MASTER -------------------------------------------
CREATE TABLE IF NOT EXISTS device_master (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_name     TEXT UNIQUE NOT NULL,
    category        TEXT,
    default_load    REAL,            -- Watts
    default_factor  REAL DEFAULT 1.0,
    default_hours   REAL DEFAULT 8,
    default_days    INTEGER DEFAULT 365,
    unit            TEXT DEFAULT 'Nos',
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_device_category ON device_master(category);

-- ---------- 5. RATE MASTER (slab_rates.xlsx) ---------------------------
CREATE TABLE IF NOT EXISTS rate_master (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    category        TEXT NOT NULL,
    slab_start      INTEGER,
    slab_end        INTEGER,           -- NULL = unlimited
    rate_per_unit   REAL,
    fixed_charge    REAL,
    duty_percent    REAL,
    condition       TEXT,
    effective_date  TEXT,
    end_date        TEXT,
    status          TEXT DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_rate_category  ON rate_master(category);
CREATE INDEX IF NOT EXISTS idx_rate_effective ON rate_master(effective_date);

-- ---------- 6. ACCOUNT MAPPING (old <-> new) ---------------------------
CREATE TABLE IF NOT EXISTS account_mapping (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    old_account     TEXT,
    new_account     TEXT,
    sc_number       TEXT,
    consumer_name   TEXT,
    father_name     TEXT,
    village         TEXT,
    effective_date  TEXT,
    status          TEXT DEFAULT 'active',
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mapping_old ON account_mapping(old_account);
CREATE INDEX IF NOT EXISTS idx_mapping_new ON account_mapping(new_account);
CREATE INDEX IF NOT EXISTS idx_mapping_sc  ON account_mapping(sc_number);

-- ---------- 7. OFFENSE SUMMARY (cache for quick lookup) ----------------
CREATE TABLE IF NOT EXISTS offense_summary (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    consumer_key        TEXT UNIQUE NOT NULL,   -- account or hash(name|father|village)
    total_offenses      INTEGER DEFAULT 0,
    first_offense_date  TEXT,
    last_offense_date   TEXT,
    total_assessment    REAL DEFAULT 0,
    updated_at          TEXT DEFAULT (datetime('now'))
);

-- ---------- 8. RAID CASES (the live cases users create) ----------------
CREATE TABLE IF NOT EXISTS raid_cases (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id            TEXT UNIQUE NOT NULL,
    online_no          TEXT,
    consumer_id        INTEGER,
    account_number     TEXT,            -- denormalised for fast search
    inspection_date    TEXT,
    section            TEXT,            -- 135 / 138 / 126 / Other
    section_other      TEXT,            -- when section = Other
    checking_type      TEXT,            -- Regular / Vigilance / Other
    je_name            TEXT,
    sub_substation     TEXT,
    td_date            TEXT,
    connected_load_kw  REAL,
    user_name          TEXT,            -- consumer-of-record (may differ from registered)
    user_father        TEXT,
    user_address       TEXT,
    devices_json       TEXT,            -- JSON array: [{name,L,F,H,D,units},...]
    less_unit          REAL,            -- consumed units to subtract (optional)
    multiplier         REAL DEFAULT 2,
    offense_count      INTEGER DEFAULT 1,
    assessment_json    TEXT,            -- full breakdown JSON
    total_assessment   REAL,
    compounding_amount REAL,
    fir_number         TEXT,
    checking_report_number TEXT,             -- Inspection / "Checking Report" reference
    case_status        TEXT DEFAULT 'open',  -- open|noticed|paid|closed|appealed
    created_by         TEXT,
    created_at         TEXT DEFAULT (datetime('now')),
    updated_at         TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(consumer_id) REFERENCES consumers(id)
);
CREATE INDEX IF NOT EXISTS idx_case_account   ON raid_cases(account_number);
CREATE INDEX IF NOT EXISTS idx_case_online    ON raid_cases(online_no);
CREATE INDEX IF NOT EXISTS idx_case_inspect   ON raid_cases(inspection_date);
CREATE INDEX IF NOT EXISTS idx_case_status    ON raid_cases(case_status);
CREATE INDEX IF NOT EXISTS idx_case_section   ON raid_cases(section);
CREATE INDEX IF NOT EXISTS idx_case_check_report ON raid_cases(checking_report_number);

-- ---------- 9. PAYMENTS ------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         TEXT NOT NULL,
    payment_type    TEXT,            -- full|partial|installment
    component       TEXT,            -- assessment|compounding|shaman|admin
    amount          REAL NOT NULL,
    payment_date    TEXT,
    receipt_number  TEXT,
    payment_method  TEXT,            -- cash|cheque|online|dd
    remarks         TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(case_id) REFERENCES raid_cases(case_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_pay_case     ON payments(case_id);
CREATE INDEX IF NOT EXISTS idx_pay_date     ON payments(payment_date);
CREATE INDEX IF NOT EXISTS idx_pay_receipt  ON payments(receipt_number);

-- ---------- 10. INQUIRIES ----------------------------------------------
CREATE TABLE IF NOT EXISTS inquiries (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id             TEXT NOT NULL,
    caller_name         TEXT,
    mobile_number       TEXT,
    relationship        TEXT,        -- self|relative|advocate|other
    amount_quoted       REAL,
    inquiry_date        TEXT DEFAULT (datetime('now')),
    remarks             TEXT,
    follow_up_required  INTEGER DEFAULT 0,
    FOREIGN KEY(case_id) REFERENCES raid_cases(case_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_inq_case   ON inquiries(case_id);
CREATE INDEX IF NOT EXISTS idx_inq_mobile ON inquiries(mobile_number);

-- ---------- 11. NOTICES ------------------------------------------------
CREATE TABLE IF NOT EXISTS notices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         TEXT NOT NULL,
    notice_type     TEXT NOT NULL,   -- provisional|section3|section5|thanedari|envelope|deposit_slip|noc
    notice_number   TEXT,
    dispatch_date   TEXT,
    due_date        TEXT,
    amount          REAL,
    status          TEXT DEFAULT 'pending',  -- pending|dispatched|responded|overdue
    document_path   TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(case_id) REFERENCES raid_cases(case_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_notice_case ON notices(case_id);
CREATE INDEX IF NOT EXISTS idx_notice_type ON notices(notice_type);
CREATE INDEX IF NOT EXISTS idx_notice_due  ON notices(due_date);

-- ---------- 12. DOCUMENTS (uploads + generated) ------------------------
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id         TEXT NOT NULL,
    document_type   TEXT NOT NULL,   -- inspection|provisional|sec3|sec5|appeal|photo|correspondence|generated
    document_name   TEXT,
    file_path       TEXT,
    file_size       INTEGER,
    mime_type       TEXT,
    uploaded_by     TEXT,
    version         INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'active',
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(case_id) REFERENCES raid_cases(case_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_doc_case ON documents(case_id);
CREATE INDEX IF NOT EXISTS idx_doc_type ON documents(document_type);

-- ---------- 13. SYSTEM CONFIG (key-value) ------------------------------
CREATE TABLE IF NOT EXISTS system_config (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    config_key   TEXT UNIQUE NOT NULL,
    config_value TEXT,
    description  TEXT,
    updated_at   TEXT DEFAULT (datetime('now'))
);

-- ---------- 14. CASE REVISIONS (post-appeal edits) ---------------------
CREATE TABLE IF NOT EXISTS case_revisions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id               TEXT NOT NULL,
    revision_number       INTEGER DEFAULT 1,
    revision_reason       TEXT,    -- appeal|error_correction|rate_update
    original_assessment   REAL,
    revised_assessment    REAL,
    revised_by            TEXT,
    revised_at            TEXT DEFAULT (datetime('now')),
    approval_status       TEXT DEFAULT 'pending',
    approved_by           TEXT,
    approved_at           TEXT,
    revision_details      TEXT,    -- JSON diff
    FOREIGN KEY(case_id) REFERENCES raid_cases(case_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_rev_case ON case_revisions(case_id);

-- ---------- 15. APPEALS ------------------------------------------------
CREATE TABLE IF NOT EXISTS appeals (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id               TEXT NOT NULL,
    appeal_date           TEXT,
    appellant_name        TEXT,
    appellant_relation    TEXT,
    appeal_reason         TEXT,
    supporting_documents  TEXT,    -- JSON array
    appeal_status         TEXT DEFAULT 'received',
    review_date           TEXT,
    review_comments       TEXT,
    revision_triggered    INTEGER DEFAULT 0,
    FOREIGN KEY(case_id) REFERENCES raid_cases(case_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_appeal_case ON appeals(case_id);

-- ---------- 16. AUDIT LOG ----------------------------------------------
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_name   TEXT,
    action      TEXT,
    table_name  TEXT,
    record_id   TEXT,
    old_values  TEXT,            -- JSON
    new_values  TEXT,            -- JSON
    ip_address  TEXT,
    timestamp   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_table  ON audit_log(table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_time   ON audit_log(timestamp);
