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

from core import crypto, estimator, paths, repo

_log = logging.getLogger(__name__)

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKER_TIMEOUT = 240  # seconds; below gunicorn's 300s

# Bump when the worker/bundle shape changes so cached runs are recomputed.
ENGINE_VERSION = 5

RAW_HEADER = ["date", "action", "symbol", "quantity", "price", "fees", "currency"]

# Attached to any run whose cash-balance check was waived. core.notices matches
# it into the "balance" notice, so the report always says the check was skipped.
BALANCE_CHECK_WAIVED_WARNING = (
    "Cash balance didn't reconcile — you ran this calculation without the balance "
    "check, so missing deposits/withdrawals went unflagged. Figures are correct as "
    "long as every buy/sell/dividend row is present."
)

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
        result = json.load(f)
    if result.get("ok"):
        if proc.stderr:
            _log.debug("worker (%s) stderr: %s", job.get("mode"), proc.stderr[-2000:])
    else:
        err = result.get("error") or {}
        _log.warning(
            "worker (%s, %s) failed: %s: %s%s",
            job.get("mode"),
            job.get("account_type") or job.get("tax_year"),
            err.get("type"),
            err.get("message"),
            f" — transaction {json.dumps(err['transaction'])}" if err.get("transaction") else "",
        )
        if proc.stderr:
            _log.warning("worker stderr tail: %s", proc.stderr[-2000:])
    return result


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

# Brokers whose export chunks merge into one CSV before the parser sees them:
# account type -> (worker file key, output name, header probes).
_MERGED_CSV = {
    "schwab_individual": ("schwab", "schwab.csv", ("Date", "Action", "Symbol")),
    "freetrade_gia": ("freetrade", "freetrade.csv", ("Title", "Type", "Timestamp")),
    "interactive_brokers": (
        "interactive_brokers",
        "interactive_brokers.csv",
        ("Date", "Transaction Type", "Net Amount"),
    ),
}

# Brokers cgt-calc reads as a directory rather than a file, because one account
# needs several files that are not all the same format. Filenames are preserved
# there: Morgan Stanley and Sharesight recognise each report by its name, and HL
# matches a trade to its contract note by the reference its filename starts with.
_DIR_BROKERS = {
    "hl_fund_share": "hl_dir",
    "morgan_stanley_awards": "mssb_dir",
    "sharesight": "sharesight_dir",
    "trading212_invest": "trading212_dir",
}

# Exports that are one whole-account file and cannot be merged with another —
# a Vanguard worksheet holds two differently-shaped tables, so concatenating two
# of them produces a file no parser can read. Newest upload wins.
_SINGLE_FILE = {"vanguard_gia": "vanguard"}


def _decrypt_doc_to(doc: dict, dest: str) -> str:
    src = paths.doc_path(doc["account_id"], doc["id"])
    with open(src, "rb") as f:
        data = crypto.decrypt(f.read())
    with open(dest, "wb") as f:
        f.write(data)
    return dest


def _decrypt_doc(doc: dict, dest_dir: str) -> str:
    return _decrypt_doc_to(
        doc, os.path.join(dest_dir, f"{doc['id']}_{os.path.basename(doc['filename'])}")
    )


def _newest_first_by_name(entries: list[tuple[dict, dict]]) -> tuple[list[dict], list[str]]:
    """One document per filename, the newest upload winning, plus the filenames
    it displaced. Names carry meaning in a broker directory, so two documents
    cannot both be called `Releases Report.csv`."""
    chosen: dict[str, dict] = {}
    displaced: list[str] = []
    for _account, doc in sorted(entries, key=lambda e: e[1]["id"]):
        name = os.path.basename(doc["filename"])
        if name.lower() in chosen:
            displaced.append(name)
        chosen[name.lower()] = doc
    return list(chosen.values()), sorted(set(displaced))


def build_document_set(user_id: int, work_dir: str) -> tuple[dict, list[str]]:
    """Decrypt every account's documents into what its parser expects: one merged
    CSV, a directory of reports under their own filenames, or a single file.

    Returns ({file_key: path}, warnings) — the keys are engine.worker.FILE_FLAGS."""
    src_dir = os.path.join(work_dir, "src")
    os.makedirs(src_dir, exist_ok=True)
    files: dict[str, str] = {}
    warnings: list[str] = []
    raw_rows: list[list[str]] = []

    by_type: dict[str, list[tuple[dict, dict]]] = {}
    for account in repo.list_accounts(user_id):
        for doc in repo.list_documents(user_id, account["id"]):
            by_type.setdefault(account["type"], []).append((account, doc))

    for type_, (file_key, out_name, probes) in _MERGED_CSV.items():
        entries = by_type.get(type_, [])
        if entries:
            paths_ = [_decrypt_doc(doc, src_dir) for _, doc in entries]
            out = os.path.join(work_dir, out_name)
            merge_csv_files(paths_, out, probes)
            files[file_key] = out

    for type_, file_key in _DIR_BROKERS.items():
        entries = by_type.get(type_, [])
        if not entries:
            continue
        out_dir = os.path.join(work_dir, file_key)
        os.makedirs(out_dir, exist_ok=True)
        docs, displaced = _newest_first_by_name(entries)
        for doc in docs:
            _decrypt_doc_to(doc, os.path.join(out_dir, os.path.basename(doc["filename"])))
        if displaced:
            warnings.append(
                f"{entries[0][0]['name']}: {', '.join(displaced)} uploaded more than once "
                "— only the newest of each name is used, because this broker's reports are "
                "told apart by their filenames."
            )
        files[file_key] = out_dir

    for type_, file_key in _SINGLE_FILE.items():
        entries = by_type.get(type_, [])
        if not entries:
            continue
        docs = sorted((doc for _, doc in entries), key=lambda d: d["id"])
        if len(docs) > 1:
            warnings.append(
                f"{entries[0][0]['name']}: {len(docs)} files uploaded; using the newest "
                f"({docs[-1]['filename']}). This export is one whole-account worksheet, "
                "so exports cannot be stitched together — re-export the full history."
            )
        files[file_key] = _decrypt_doc(docs[-1], src_dir)

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


def input_material(user_id: int, tax_year: int, balance_check: bool = True) -> dict:
    """Everything a calculation's result depends on, as plain data.

    Hashed, it is the cache key. Stored beside the run, it is what lets a later
    "these figures are out of date" name what changed, rather than assert it
    from a hash comparison nobody can check.

    Every value here is JSON-native — lists, not tuples — so that what comes
    back out of the database compares equal to what goes in. A tuple survives
    `json.dumps` for hashing (it serialises identically to a list, so cache keys
    are unaffected) but never survives the round trip, which would make every
    stored run differ from every live one and mark it permanently out of date."""
    return {
        "tax_year": tax_year,
        "fork": fork_version(),
        "engine": ENGINE_VERSION,
        # A run with the cash-balance check waived is a different calculation,
        # so it must not be served from (or overwrite) a checked run's cache.
        # It is a run option, not an input: core.status ignores it when asking
        # whether the documents have moved.
        "balance_check": balance_check,
        # The filename is part of the input, not just a label: the directory
        # parsers pick a report's format by its name and match HL contract notes
        # by it, so the same bytes under another name are a different run.
        "docs": sorted(
            [d["account_id"], d["sha256"], d["filename"]] for d in repo.list_documents(user_id)
        ),
        "spin_offs": sorted([r["dst"], r["src"]] for r in repo.list_spin_offs(user_id)),
        "exempt": sorted(r["name"] for r in repo.list_exempt_securities(user_id)),
        "interest_funds": sorted(estimator.KNOWN_INTEREST_FUNDS),
        "mappings": sorted(
            [a["id"], json.dumps(repo.get_column_mapping(a["id"]), sort_keys=True)]
            for a in repo.list_accounts(user_id)
            if a["type"] == "bank_generic"
        ),
    }


def hash_material(material: dict) -> str:
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()


def compute_input_hash(user_id: int, tax_year: int, balance_check: bool = True) -> str:
    return hash_material(input_material(user_id, tax_year, balance_check))


# ── Public API ─────────────────────────────────────────────────────────────────


def validate_upload(account: dict, file_path: str) -> dict:
    """Parse-validate an uploaded file for an account. For bank_generic, the
    stored column mapping is applied first; without one, returns needs_mapping
    plus a CSV preview so the UI can offer the mapper."""
    work_dir = os.path.join(paths.TMP_DIR, f"validate_{uuid.uuid4().hex}")
    os.makedirs(work_dir, exist_ok=True)
    try:
        target = file_path
        if account["type"] in _DIR_BROKERS:
            # These parsers read a file in the context of its siblings — an HL
            # Transaction Summary takes each trade's ticker, quantity and price
            # from the contract note beside it — so validate the upload amongst
            # the documents the account already holds, under its own filename.
            sibling_dir = os.path.join(work_dir, "dir")
            os.makedirs(sibling_dir, exist_ok=True)
            for doc in repo.list_documents(account["user_id"], account["id"]):
                _decrypt_doc_to(doc, os.path.join(sibling_dir, os.path.basename(doc["filename"])))
            target = os.path.join(sibling_dir, os.path.basename(file_path))
            shutil.copyfile(file_path, target)
        elif account["type"] == "bank_generic":
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


def run_calculation(
    user_id: int, tax_year: int, force: bool = False, balance_check: bool = True
) -> dict:
    """Run (or return the cached) calculation for a tax year. Synchronous.

    balance_check=False waives cgt-calc's cash-reconciliation check. It is never
    inferred: partial exports and genuinely missing trades fail it the same way,
    and only the user knows which they have, so the failure is reported and the
    waiver is an explicit choice made in the UI."""
    material = input_material(user_id, tax_year, balance_check)
    input_hash = hash_material(material)
    if not force:
        existing = repo.find_calc_run(user_id, tax_year, input_hash)
        if existing and existing["status"] == "ok":
            return existing

    run = repo.create_calc_run(user_id, tax_year, input_hash, json.dumps(material))
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
            # Gilts/T-bills the worker also detects by name; this list is the
            # user's additions (ticker or ISIN) for anything it cannot see.
            "exempt_securities": [r["name"] for r in repo.list_exempt_securities(user_id)],
            # Funds whose distributions are interest, not dividends (the >60%
            # bond test). Curated in core.estimator; the report flags offshore
            # funds that are not on it so the status can be checked by hand.
            "interest_fund_tickers": sorted(estimator.KNOWN_INTEREST_FUNDS),
            "exchange_rates_file": paths.EXCHANGE_RATES_FILE,
            "isin_translation_file": os.path.join(paths.CACHE_DIR, "isin_translation.csv"),
            "work_dir": work_dir,
            "pdf_path": pdf_path,
            "balance_check": balance_check,
        }
        if not balance_check:
            set_warnings.append(BALANCE_CHECK_WAIVED_WARNING)
        repo.set_calc_run_status(run["id"], "running")
        result = _run_worker(job, work_dir)
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
