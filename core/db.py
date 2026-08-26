"""SQLite connection + schema. Idempotent migrations run at startup (fintrack pattern).

All SQL that touches business tables lives in core/repo.py — this module only
owns the connection factory and schema.
"""

import logging
import sqlite3

from core import paths

_log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS allowed_emails (
    email TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS accounts (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id              INTEGER NOT NULL REFERENCES users(id),
    type                 TEXT NOT NULL,  -- schwab_individual|schwab_awards|freetrade_gia|bank_generic|raw_csv
    name                 TEXT NOT NULL,
    first_activity_date  TEXT,           -- ISO date; start of required coverage
    created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    account_id   INTEGER NOT NULL REFERENCES accounts(id),
    filename     TEXT NOT NULL,
    sha256       TEXT NOT NULL,
    size         INTEGER NOT NULL,
    tx_count     INTEGER NOT NULL DEFAULT 0,
    date_min     TEXT,               -- ISO date of earliest transaction in the file
    date_max     TEXT,               -- ISO date of latest transaction
    warnings     TEXT NOT NULL DEFAULT '[]',  -- JSON list from parse validation
    source       TEXT NOT NULL DEFAULT 'upload',  -- upload|connector
    uploaded_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (account_id, sha256)
);

CREATE TABLE IF NOT EXISTS calc_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id),
    tax_year     INTEGER NOT NULL,
    input_hash   TEXT NOT NULL,      -- hash of document set + fork version
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending|running|ok|error
    bundle       TEXT,               -- ReportBundle JSON when status=ok
    error        TEXT,
    pdf_path     TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT
);

CREATE TABLE IF NOT EXISTS spin_offs (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users(id),
    dst      TEXT NOT NULL,  -- spun-off ticker
    src      TEXT NOT NULL,  -- source ticker
    UNIQUE (user_id, dst)
);

CREATE TABLE IF NOT EXISTS column_mappings (
    account_id  INTEGER PRIMARY KEY REFERENCES accounts(id),
    mapping     TEXT NOT NULL  -- JSON: {date, description, amount, currency, interest_match}
);

CREATE TABLE IF NOT EXISTS notice_resolutions (
    user_id        INTEGER NOT NULL REFERENCES users(id),
    key            TEXT NOT NULL,     -- stable notice key, e.g. amount_adjusted__META__2025-02-25
    note           TEXT NOT NULL DEFAULT '',
    data           TEXT NOT NULL DEFAULT '{}',  -- JSON: e.g. {"withholding": "10966.96"}
    evidence_name  TEXT,              -- original filename of the attached proof (encrypted on disk)
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS planner_inputs (
    user_id   INTEGER NOT NULL REFERENCES users(id),
    tax_year  INTEGER NOT NULL,
    data      TEXT NOT NULL,  -- JSON of the inputs form
    PRIMARY KEY (user_id, tax_year)
);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(paths.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_db() -> None:
    """Create data dirs and any missing tables. Safe to run on every startup."""
    paths.ensure_dirs()
    conn = get_conn()
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    _log.info("database ready at %s", paths.DB_PATH)
