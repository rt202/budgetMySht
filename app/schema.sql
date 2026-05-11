-- SimpleFIN Budget App schema (SQLite dialect).
-- The Postgres equivalent lives in schema_pg.sql; runtime queries in
-- app/ingestion.py and app/budgets.py are written to work on both.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    org_name TEXT,
    org_domain TEXT,
    name TEXT,
    currency TEXT,
    balance REAL,
    available_balance REAL,
    balance_date TEXT,
    last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS account_balance_overrides (
    account_id TEXT PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
    balance REAL NOT NULL,
    note TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    transactions_imported INTEGER NOT NULL DEFAULT 0,
    transactions_updated INTEGER NOT NULL DEFAULT 0,
    accounts_seen INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS transactions_raw (
    sync_run_id INTEGER NOT NULL REFERENCES sync_runs(id) ON DELETE CASCADE,
    account_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sync_run_id, account_id, transaction_id)
);

CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    posted_at TEXT NOT NULL,
    transacted_at TEXT,
    amount REAL NOT NULL,
    description TEXT,
    payee TEXT,
    memo TEXT,
    pending INTEGER NOT NULL DEFAULT 0,
    auto_category TEXT,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_transactions_account_posted
    ON transactions(account_id, posted_at);

CREATE INDEX IF NOT EXISTS idx_transactions_posted
    ON transactions(posted_at);

CREATE TABLE IF NOT EXISTS categories (
    name TEXT PRIMARY KEY,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_income INTEGER NOT NULL DEFAULT 0,
    is_archived INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transaction_overrides (
    transaction_id TEXT PRIMARY KEY REFERENCES transactions(id) ON DELETE CASCADE,
    category TEXT REFERENCES categories(name) ON UPDATE CASCADE ON DELETE SET NULL,
    note TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS classification_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,
    category TEXT NOT NULL REFERENCES categories(name) ON UPDATE CASCADE ON DELETE CASCADE,
    match_field TEXT NOT NULL DEFAULT 'description',
    priority INTEGER NOT NULL DEFAULT 100,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rules_priority
    ON classification_rules(priority);

CREATE TABLE IF NOT EXISTS budgets (
    category TEXT NOT NULL REFERENCES categories(name) ON UPDATE CASCADE ON DELETE CASCADE,
    month TEXT NOT NULL,
    amount REAL NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (category, month)
);

DROP VIEW IF EXISTS v_transactions_classified;
CREATE VIEW v_transactions_classified AS
SELECT
    t.id AS transaction_id,
    t.account_id,
    a.name AS account_name,
    t.posted_at,
    t.transacted_at,
    t.amount,
    t.description,
    t.payee,
    t.memo,
    t.pending,
    COALESCE(o.category, t.auto_category) AS category,
    o.note AS note
FROM transactions t
LEFT JOIN transaction_overrides o ON o.transaction_id = t.id
LEFT JOIN accounts a ON a.id = t.account_id;

DROP VIEW IF EXISTS v_account_effective_balance;
CREATE VIEW v_account_effective_balance AS
SELECT
    a.id AS account_id,
    a.org_name,
    a.name,
    a.currency,
    COALESCE(o.balance, a.balance) AS balance,
    a.available_balance,
    a.balance_date,
    a.last_synced_at,
    o.balance AS override_balance,
    o.note AS override_note,
    o.updated_at AS override_updated_at
FROM accounts a
LEFT JOIN account_balance_overrides o ON o.account_id = a.id;
