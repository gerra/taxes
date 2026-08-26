"""Web-side engine orchestration: document-set assembly, worker subprocess
management, run caching. Never imports cgt_calc (that happens only inside the
worker subprocess — see engine/worker.py)."""

import csv
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import uuid
from collections import Counter
from datetime import date, datetime

from core import crypto, paths, repo

_log = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER_TIMEOUT = 240  # seconds; below gunicorn's 300s

RAW_HEADER = ["date", "action", "symbol", "quantity", "price", "fees", "currency"]

_DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d %b %Y", "%d.%m.%Y", "%m/%d/%Y"]


def fork_version() -> str:
    """Identify the installed cgt-calc fork for cache keys. The package version is
    a constant, so prefer the git commit recorded at install time."""
    try:
        import json
        from importlib.metadata import distribution

        dist = distribution("cgt-calc")
        direct = dist.read_text("direct_url.json")
        if direct:
            commit = json.loads(direct).get("vcs_info", {}).get("commit_id")
            if commit:
                return commit
        return dist.version
    except Exception:  # pragma: no cover
        return "unknown"


# ── Worker subprocess ──────────────────────────────────────────────────────────


def _run_worker(job: dict, work_dir: str) -> dict:
    job_path = os.path.join(work_dir, "job.json")
    result_path = os.path.join(work_dir, "result.json")
    with open(job_path, "w") as f:
        json.dump(job, f)
    proc = subprocess.run(
        [sys.executable, "-m", "engine.worker", job_path, result_path],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=WORKER_TIMEOUT,
    )
    if not os.path.exists(result_path):
        _log.error("worker produced no result (rc=%s): %s", proc.returncode, proc.stderr[-2000:])
        return {
            "ok": False,
            "error": {"type": "worker_crash", "message": (proc.stderr or "worker crashed")[-2000:]},
        }
    with open(result_path) as f:
        return json.load(f)


# ── Bank CSV → raw conversion ─────────────────────────────────────────────────


def parse_any_date(value: str) -> date:
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    # ISO datetime like 2025-01-31T12:00:00
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        raise ValueError(f"Unrecognised date: {value!r}") from None


def csv_preview(path: str, limit: int = 5) -> dict:
    """Headers + a few rows, for the column-mapping UI."""
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        rows = []
        for row in reader:
            rows.append(row)
            if len(rows) > limit:
                break
    if not rows:
        return {"headers": [], "sample": []}
    return {"headers": rows[0], "sample": rows[1:]}


def convert_bank_csv(path: str, mapping: dict) -> list[list[str]]:
    """Convert a bank statement CSV into cgt-calc raw INTEREST rows using the
    stored column mapping: {date_col, amount_col, desc_col?, currency_col?,
    currency?, include_contains?}."""
    rows: list[list[str]] = []
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for r in reader:
            desc = r.get(mapping.get("desc_col") or "") or ""
            needle = (mapping.get("include_contains") or "").lower()
            if needle and needle not in desc.lower():
                continue
            raw_amount = (r.get(mapping["amount_col"]) or "").replace(",", "").strip()
            if not raw_amount:
                continue
            day = parse_any_date(r.get(mapping["date_col"]) or "")
            currency = (
                (r.get(mapping.get("currency_col") or "") or "").strip()
                or mapping.get("currency")
                or "GBP"
            )
            rows.append([day.isoformat(), "INTEREST", "", "1", raw_amount, "0", currency])
    return rows


# ── CSV chunk merging ──────────────────────────────────────────────────────────


def _read_rows(path: str) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        return [row for row in csv.reader(f) if any(cell.strip() for cell in row)]


def _find_header(rows: list[list[str]], probes: tuple[str, ...]) -> int:
    for i, row in enumerate(rows):
        cells = {c.strip().lower() for c in row}
        if all(p.lower() in cells for p in probes):
            return i
    return 0


# Broker export footer rows that aren't transactions (e.g. Schwab's summary line)
_FOOTER_LABELS = {"transactions total", "total"}


def merge_csv_files(
    src_paths: list[str], out_path: str, probes: tuple[str, ...], pair_rows: bool = False
) -> None:
    """Merge export chunks into one CSV: header from the first file, data rows
    deduplicated across files but not within a file (a row repeated N times in
    one file is a real repeated transaction — keep max count seen in any one
    file). pair_rows treats consecutive row pairs as one record (Schwab awards).
    Footer summary rows (e.g. Schwab's "Transactions Total") are dropped."""
    header: list[str] | None = None
    order: list[tuple] = []
    counts: dict[tuple, int] = {}
    for p in src_paths:
        rows = _read_rows(p)
        if not rows:
            continue
        h_idx = _find_header(rows, probes)
        if header is None:
            header = rows[h_idx]
        data = [r for r in rows[h_idx + 1 :] if r[0].strip().lower() not in _FOOTER_LABELS]
        if pair_rows:
            units = [tuple(map(tuple, data[i : i + 2])) for i in range(0, len(data) - 1, 2)]
        else:
            units = [tuple(r) for r in data]
        file_counts = Counter(units)
        for unit, n in file_counts.items():
            if unit not in counts:
                counts[unit] = n
                order.append(unit)
            else:
                counts[unit] = max(counts[unit], n)
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        if header:
            writer.writerow(header)
        for unit in order:
            for _ in range(counts[unit]):
                if pair_rows:
                    for row in unit:
                        writer.writerow(list(row))
                else:
                    writer.writerow(list(unit))


# ── Document sets ──────────────────────────────────────────────────────────────

_PROBES = {
    "schwab_individual": ("Date", "Action", "Symbol"),
    "freetrade_gia": ("Title", "Type", "Timestamp"),
}


def _decrypt_doc(doc: dict, dest_dir: str) -> str:
    src = paths.doc_path(doc["account_id"], doc["id"])
    with open(src, "rb") as f:
        data = crypto.decrypt(f.read())
    dest = os.path.join(dest_dir, f"{doc['id']}_{os.path.basename(doc['filename'])}")
    with open(dest, "wb") as f:
        f.write(data)
    return dest


def build_document_set(user_id: int, work_dir: str) -> tuple[dict, list[str]]:
    """Decrypt + merge every account's documents into per-flag input files.

    Returns ({file_key: path}, warnings)."""
    src_dir = os.path.join(work_dir, "src")
    os.makedirs(src_dir, exist_ok=True)
    files: dict[str, str] = {}
    warnings: list[str] = []
    raw_rows: list[list[str]] = []

    by_type: dict[str, list[tuple[dict, dict]]] = {}
    for account in repo.list_accounts(user_id):
        for doc in repo.list_documents(user_id, account["id"]):
            by_type.setdefault(account["type"], []).append((account, doc))

    for type_, probe_key, out_name, pair in (
        ("schwab_individual", "schwab", "schwab.csv", False),
        ("freetrade_gia", "freetrade", "freetrade.csv", False),
    ):
        entries = by_type.get(type_, [])
        if entries:
            paths_ = [_decrypt_doc(doc, src_dir) for _, doc in entries]
            out = os.path.join(work_dir, out_name)
            merge_csv_files(paths_, out, _PROBES[type_], pair_rows=pair)
            files[probe_key] = out

    awards = by_type.get("schwab_awards", [])
    if awards:
        json_docs = [d for _, d in awards if d["filename"].lower().endswith(".json")]
        csv_docs = [d for _, d in awards if not d["filename"].lower().endswith(".json")]
        if json_docs:
            if len(json_docs) > 1 or csv_docs:
                warnings.append(
                    "Multiple equity-award documents found; using the newest JSON only "
                    "— prefer a single CSV export covering everything."
                )
            files["schwab_equity_award_json"] = _decrypt_doc(json_docs[-1], src_dir)
        else:
            out = os.path.join(work_dir, "schwab_awards.csv")
            merge_csv_files(
                [_decrypt_doc(d, src_dir) for d in csv_docs],
                out,
                ("Date", "Symbol"),
                pair_rows=True,
            )
            files["schwab_award"] = out

    for _account, doc in by_type.get("raw_csv", []):
        rows = _read_rows(_decrypt_doc(doc, src_dir))
        if rows and [c.strip().lower() for c in rows[0]] == RAW_HEADER:
            rows = rows[1:]
        raw_rows.extend(rows)

    for account, doc in by_type.get("bank_generic", []):
        mapping = repo.get_column_mapping(account["id"])
        if not mapping:
            warnings.append(f"{account['name']}: no column mapping set — skipped")
            continue
        raw_rows.extend(convert_bank_csv(_decrypt_doc(doc, src_dir), mapping))

    if raw_rows:
        raw_rows = [list(u) for u in dict.fromkeys(tuple(r) for r in raw_rows)]
        raw_rows.sort(key=lambda r: r[0])
        out = os.path.join(work_dir, "raw.csv")
        with open(out, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(RAW_HEADER)
            writer.writerows(raw_rows)
        files["raw"] = out

    return files, warnings


def compute_input_hash(user_id: int, tax_year: int) -> str:
    material = {
        "tax_year": tax_year,
        "fork": fork_version(),
        "docs": sorted((d["account_id"], d["sha256"]) for d in repo.list_documents(user_id)),
        "spin_offs": sorted((r["dst"], r["src"]) for r in repo.list_spin_offs(user_id)),
        "mappings": sorted(
            (a["id"], json.dumps(repo.get_column_mapping(a["id"]), sort_keys=True))
            for a in repo.list_accounts(user_id)
            if a["type"] == "bank_generic"
        ),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


# ── Public API ─────────────────────────────────────────────────────────────────


def validate_upload(account: dict, file_path: str) -> dict:
    """Parse-validate an uploaded file for an account. For bank_generic, the
    stored column mapping is applied first; without one, returns needs_mapping
    plus a CSV preview so the UI can offer the mapper."""
    work_dir = os.path.join(paths.TMP_DIR, f"validate_{uuid.uuid4().hex}")
    os.makedirs(work_dir, exist_ok=True)
    try:
        target = file_path
        if account["type"] == "bank_generic":
            mapping = repo.get_column_mapping(account["id"])
            if not mapping:
                return {"ok": False, "needs_mapping": True, **csv_preview(file_path)}
            try:
                rows = convert_bank_csv(file_path, mapping)
            except (ValueError, KeyError) as e:
                return {"ok": False, "error": {"type": "mapping", "message": str(e)}}
            target = os.path.join(work_dir, "converted.csv")
            with open(target, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(RAW_HEADER)
                writer.writerows(rows)
        job = {"mode": "validate", "account_type": account["type"], "file": target}
        return _run_worker(job, work_dir)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"type": "timeout", "message": "Validation timed out"}}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def run_calculation(user_id: int, tax_year: int, force: bool = False) -> dict:
    """Run (or return the cached) calculation for a tax year. Synchronous."""
    input_hash = compute_input_hash(user_id, tax_year)
    if not force:
        existing = repo.find_calc_run(user_id, tax_year, input_hash)
        if existing and existing["status"] == "ok":
            return existing

    run = repo.create_calc_run(user_id, tax_year, input_hash)
    work_dir = os.path.join(paths.TMP_DIR, f"run_{run['id']}")
    os.makedirs(work_dir, exist_ok=True)
    try:
        files, set_warnings = build_document_set(user_id, work_dir)
        if not files:
            repo.set_calc_run_status(
                run["id"],
                "error",
                error=json.dumps({"type": "no_documents", "message": "No documents uploaded yet"}),
            )
            return repo.get_calc_run(user_id, run["id"])

        out_dir = paths.run_dir(run["id"])
        os.makedirs(out_dir, exist_ok=True)
        pdf_path = os.path.join(out_dir, "calculations.pdf")
        job = {
            "mode": "calculate",
            "tax_year": tax_year,
            "files": files,
            "spin_offs": {r["dst"]: r["src"] for r in repo.list_spin_offs(user_id)},
            "exchange_rates_file": paths.EXCHANGE_RATES_FILE,
            "isin_translation_file": os.path.join(paths.CACHE_DIR, "isin_translation.csv"),
            "work_dir": work_dir,
            "pdf_path": pdf_path,
            "balance_check": True,
        }
        repo.set_calc_run_status(run["id"], "running")
        result = _run_worker(job, work_dir)
        if (
            not result.get("ok")
            and "balance" in str(result.get("error", {}).get("message", "")).lower()
        ):
            # Cash-balance reconciliation failed — usually deposits/withdrawals
            # missing from partial exports (Freetrade windows). Gains/dividends
            # are unaffected if all trades are present, so retry without it and
            # surface a warning instead of failing the run.
            job["balance_check"] = False
            retry = _run_worker(job, work_dir)
            if retry.get("ok"):
                set_warnings.append(
                    "Cash balance didn't reconcile — some deposits/withdrawals are "
                    "missing from your documents. The calculation ran without the "
                    "balance check; figures are correct as long as every buy/sell/"
                    "dividend row is present."
                )
                result = retry
        if result.get("ok"):
            bundle = result["bundle"]
            bundle["warnings"] = set_warnings + bundle.get("warnings", [])
            repo.set_calc_run_status(
                run["id"],
                "ok",
                bundle=json.dumps(bundle),
                pdf_path=pdf_path if result.get("pdf_rendered") else None,
            )
        else:
            repo.set_calc_run_status(run["id"], "error", error=json.dumps(result["error"]))
    except subprocess.TimeoutExpired:
        repo.set_calc_run_status(
            run["id"],
            "error",
            error=json.dumps({"type": "timeout", "message": "Calculation timed out"}),
        )
    except Exception as e:  # noqa: BLE001 — surface anything unexpected on the run row
        _log.exception("calculation failed")
        repo.set_calc_run_status(
            run["id"], "error", error=json.dumps({"type": "internal", "message": str(e)})
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    return repo.get_calc_run(user_id, run["id"])
