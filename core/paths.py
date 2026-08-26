"""Central filesystem paths for the taxes app.

Data lives outside the code tree so backups, deploys, and dev/prod splits stay
clean. All paths are resolved once at import from env vars (with dev defaults).

Env vars:
    TAXES_DATA_DIR   Root for all persistent data. Default: <repo>/data
    TAXES_DB_PATH    Override SQLite path.         Default: <DATA_DIR>/taxes.db

Layout under DATA_DIR:
    taxes.db
    docs/<account_id>/<doc_id>.enc   Fernet-encrypted uploaded originals
    runs/<run_id>/                   calc outputs (bundle.json, calculations.pdf)
    cache/exchange_rates.csv         shared HMRC monthly-rate cache
    tmp/                             per-run scratch (pdflatex cwd)
"""

import os

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.environ.get("TAXES_DATA_DIR") or os.path.join(_REPO_ROOT, "data")
DB_PATH = os.environ.get("TAXES_DB_PATH") or os.path.join(DATA_DIR, "taxes.db")
DOCS_DIR = os.path.join(DATA_DIR, "docs")
EVIDENCE_DIR = os.path.join(DATA_DIR, "evidence")
RUNS_DIR = os.path.join(DATA_DIR, "runs")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
TMP_DIR = os.path.join(DATA_DIR, "tmp")

EXCHANGE_RATES_FILE = os.path.join(CACHE_DIR, "exchange_rates.csv")


def doc_path(account_id: int, doc_id: int) -> str:
    return os.path.join(DOCS_DIR, str(account_id), f"{doc_id}.enc")


def run_dir(run_id: int) -> str:
    return os.path.join(RUNS_DIR, str(run_id))


def evidence_path(user_id: int, key: str) -> str:
    return os.path.join(EVIDENCE_DIR, str(user_id), f"{key}.enc")


def ensure_dirs() -> None:
    for d in (DATA_DIR, DOCS_DIR, EVIDENCE_DIR, RUNS_DIR, CACHE_DIR, TMP_DIR):
        os.makedirs(d, exist_ok=True)
