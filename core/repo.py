"""All SQL for the taxes app lives here. Blueprints and services call these
functions; nothing else touches the database."""

import json
import sqlite3
from typing import Any

from core import auth
from core.db import get_conn

# ── Users / access ─────────────────────────────────────────────────────────────


def is_email_allowed(email: str) -> bool:
    email = email.lower()
    if auth.ADMIN_EMAIL and email == auth.ADMIN_EMAIL.lower():
        return True
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT 1 FROM allowed_emails WHERE lower(email) = ?", (email,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_or_create_user(email: str, name: str) -> dict | None:
    """Return the user row for email, creating it if allowed. None if not allowed."""
    if not is_email_allowed(email):
        return None
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE lower(email) = lower(?)", (email,)).fetchone()
        if row:
            return dict(row)
        cur = conn.execute("INSERT INTO users (email, name) VALUES (?, ?)", (email, name))
        conn.commit()
        return dict(conn.execute("SELECT * FROM users WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()


def get_user(user_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── Accounts ───────────────────────────────────────────────────────────────────

ACCOUNT_TYPES = ("schwab_individual", "schwab_awards", "freetrade_gia", "bank_generic", "raw_csv")


def list_accounts(user_id: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_account(user_id: int, account_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_account(user_id: int, type_: str, name: str, first_activity_date: str | None) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO accounts (user_id, type, name, first_activity_date) VALUES (?, ?, ?, ?)",
            (user_id, type_, name, first_activity_date),
        )
        conn.commit()
        return dict(
            conn.execute("SELECT * FROM accounts WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    finally:
        conn.close()


def update_account(user_id: int, account_id: int, name: str, first_activity_date: str | None):
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE accounts SET name = ?, first_activity_date = ? WHERE id = ? AND user_id = ?",
            (name, first_activity_date, account_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_account(user_id: int, account_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "DELETE FROM documents WHERE account_id = ? AND user_id = ?", (account_id, user_id)
        )
        conn.execute("DELETE FROM column_mappings WHERE account_id = ?", (account_id,))
        conn.execute("DELETE FROM accounts WHERE id = ? AND user_id = ?", (account_id, user_id))
        conn.commit()
    finally:
        conn.close()


# ── Documents ──────────────────────────────────────────────────────────────────


def list_documents(user_id: int, account_id: int | None = None) -> list[dict]:
    conn = get_conn()
    try:
        if account_id is None:
            rows = conn.execute(
                "SELECT * FROM documents WHERE user_id = ? ORDER BY account_id, date_min",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM documents WHERE user_id = ? AND account_id = ? ORDER BY date_min",
                (user_id, account_id),
            ).fetchall()
        docs = [dict(r) for r in rows]
        for d in docs:
            d["warnings"] = json.loads(d["warnings"])
        return docs
    finally:
        conn.close()


def get_document(user_id: int, doc_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["warnings"] = json.loads(d["warnings"])
        return d
    finally:
        conn.close()


def create_document(
    user_id: int,
    account_id: int,
    filename: str,
    sha256: str,
    size: int,
    tx_count: int,
    date_min: str | None,
    date_max: str | None,
    warnings: list[str],
    source: str = "upload",
) -> dict | None:
    """Insert a document row. Returns None if an identical file already exists."""
    conn = get_conn()
    try:
        try:
            cur = conn.execute(
                """INSERT INTO documents
                   (user_id, account_id, filename, sha256, size, tx_count,
                    date_min, date_max, warnings, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    account_id,
                    filename,
                    sha256,
                    size,
                    tx_count,
                    date_min,
                    date_max,
                    json.dumps(warnings),
                    source,
                ),
            )
        except sqlite3.IntegrityError:
            return None  # same file already uploaded for this account
        conn.commit()
        return get_document(user_id, cur.lastrowid)
    finally:
        conn.close()


def delete_document(user_id: int, doc_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM documents WHERE id = ? AND user_id = ?", (doc_id, user_id))
        conn.commit()
    finally:
        conn.close()


# ── Calc runs ──────────────────────────────────────────────────────────────────


def find_calc_run(user_id: int, tax_year: int, input_hash: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT * FROM calc_runs
               WHERE user_id = ? AND tax_year = ? AND input_hash = ? AND status IN ('ok', 'running', 'pending')
               ORDER BY id DESC LIMIT 1""",
            (user_id, tax_year, input_hash),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_calc_run(user_id: int, tax_year: int, input_hash: str) -> dict:
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO calc_runs (user_id, tax_year, input_hash) VALUES (?, ?, ?)",
            (user_id, tax_year, input_hash),
        )
        conn.commit()
        return dict(
            conn.execute("SELECT * FROM calc_runs WHERE id = ?", (cur.lastrowid,)).fetchone()
        )
    finally:
        conn.close()


def get_calc_run(user_id: int, run_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM calc_runs WHERE id = ? AND user_id = ?", (run_id, user_id)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def latest_ok_run(user_id: int, tax_year: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT * FROM calc_runs WHERE user_id = ? AND tax_year = ? AND status = 'ok'
               ORDER BY id DESC LIMIT 1""",
            (user_id, tax_year),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_calc_run_status(run_id: int, status: str, **fields: Any) -> None:
    allowed = {"bundle", "error", "pdf_path"}
    sets = ["status = ?"]
    vals: list[Any] = [status]
    for k, v in fields.items():
        if k not in allowed:
            raise ValueError(f"unexpected calc_run field {k}")
        sets.append(f"{k} = ?")
        vals.append(v)
    if status in ("ok", "error"):
        sets.append("finished_at = datetime('now')")
    vals.append(run_id)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE calc_runs SET {', '.join(sets)} WHERE id = ?", vals)
        conn.commit()
    finally:
        conn.close()


# ── Spin-offs / column mappings / planner inputs ───────────────────────────────


def list_spin_offs(user_id: int) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM spin_offs WHERE user_id = ?", (user_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def upsert_spin_off(user_id: int, dst: str, src: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO spin_offs (user_id, dst, src) VALUES (?, ?, ?)
               ON CONFLICT (user_id, dst) DO UPDATE SET src = excluded.src""",
            (user_id, dst, src),
        )
        conn.commit()
    finally:
        conn.close()


def get_column_mapping(account_id: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT mapping FROM column_mappings WHERE account_id = ?", (account_id,)
        ).fetchone()
        return json.loads(row["mapping"]) if row else None
    finally:
        conn.close()


def set_column_mapping(account_id: int, mapping: dict) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO column_mappings (account_id, mapping) VALUES (?, ?)
               ON CONFLICT (account_id) DO UPDATE SET mapping = excluded.mapping""",
            (account_id, json.dumps(mapping)),
        )
        conn.commit()
    finally:
        conn.close()


def get_planner_inputs(user_id: int, tax_year: int) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT data FROM planner_inputs WHERE user_id = ? AND tax_year = ?",
            (user_id, tax_year),
        ).fetchone()
        return json.loads(row["data"]) if row else None
    finally:
        conn.close()


def set_planner_inputs(user_id: int, tax_year: int, data: dict) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO planner_inputs (user_id, tax_year, data) VALUES (?, ?, ?)
               ON CONFLICT (user_id, tax_year) DO UPDATE SET data = excluded.data""",
            (user_id, tax_year, json.dumps(data)),
        )
        conn.commit()
    finally:
        conn.close()
