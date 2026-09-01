"""Broker registry wiring: every account type the app offers must have export
instructions, a place in the document set the engine builds, and a cgt-calc flag
to be passed under. A broker added to only some of those is silently useless."""

import os

import pytest
from cgt_calc.args_parser import create_parser

from core import coverage, repo
from engine import runner, worker

FIXTURES = os.path.join(os.path.dirname(__file__), "data", "brokers")

# Types the engine feeds through something other than a per-type file: the
# Schwab awards export chooses between two flags by file extension, and the two
# generic formats are concatenated into one raw CSV.
_SPECIAL_TYPES = {"schwab_awards", "bank_generic", "raw_csv"}


def test_every_account_type_reaches_the_engine():
    routed = set(runner._MERGED_CSV) | set(runner._DIR_BROKERS) | set(runner._SINGLE_FILE)
    assert routed | _SPECIAL_TYPES == set(repo.ACCOUNT_TYPES)


def test_every_account_type_has_export_instructions():
    assert set(repo.ACCOUNT_TYPES) == set(coverage.INSTRUCTIONS)


def test_every_document_set_key_has_a_cgt_calc_flag():
    keys = (
        {k for k, _n, _p in runner._MERGED_CSV.values()}
        | set(runner._DIR_BROKERS.values())
        | set(runner._SINGLE_FILE.values())
        | {"schwab_award", "schwab_equity_award_json", "raw"}
    )
    assert keys <= set(worker.FILE_FLAGS)


def test_every_flag_is_one_cgt_calc_accepts():
    """The fork owns these names; a rename there must fail here, not in a run."""
    known = set()
    for action in create_parser()._actions:
        known.update(action.option_strings)
    assert set(worker.FILE_FLAGS.values()) <= known


def test_the_ui_labels_every_account_type():
    """The type dropdown is built from TYPE_LABELS, so a type missing there can
    be created by the API but never by a person."""
    source = os.path.join(
        os.path.dirname(__file__), "..", "web", "src", "views", "DocumentsView.tsx"
    )
    with open(source) as f:
        labels = f.read().split("const TYPE_LABELS", 1)[1].split("}", 1)[0]
    for type_ in repo.ACCOUNT_TYPES:
        assert f"{type_}:" in labels, f"{type_} has no UI label"


# ── Directory brokers: filenames are meaning, not decoration ───────────────────


def _account(user_id, type_, name="Acc"):
    return repo.create_account(user_id, type_, name, None)


def _upload(user_id, account, filename, body=None):
    import hashlib

    from core import crypto, paths

    body = body if body is not None else filename.encode()
    doc = repo.create_document(
        user_id,
        account["id"],
        filename,
        hashlib.sha256(body).hexdigest(),
        len(body),
        1,
        None,
        None,
        [],
    )
    dest = paths.doc_path(account["id"], doc["id"])
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(crypto.encrypt(body))
    return doc


@pytest.fixture
def broker_user():
    """A user of this file's own, so building a document set here sees only the
    accounts the test made."""
    repo.approve_email("brokers@example.com", "Brokers")
    user = repo.get_or_create_user("brokers@example.com", "Brokers")
    for account in repo.list_accounts(user["id"]):
        repo.delete_account(user["id"], account["id"])
    return user


def test_directory_broker_keeps_original_filenames(broker_user, tmp_path):
    account = _account(broker_user["id"], "morgan_stanley_awards", "MS")
    _upload(broker_user["id"], account, "Releases Report.csv")
    _upload(broker_user["id"], account, "Withdrawals Report.csv")

    files, warnings = runner.build_document_set(broker_user["id"], str(tmp_path))

    assert warnings == []
    assert sorted(os.listdir(files["mssb_dir"])) == [
        "Releases Report.csv",
        "Withdrawals Report.csv",
    ]


def test_directory_broker_uses_the_newest_of_a_repeated_filename(broker_user, tmp_path):
    account = _account(broker_user["id"], "sharesight", "SS")
    _upload(broker_user["id"], account, "All Trades Report.csv", b"first\n")
    _upload(broker_user["id"], account, "All Trades Report.csv", b"second\n")

    files, warnings = runner.build_document_set(broker_user["id"], str(tmp_path))

    with open(os.path.join(files["sharesight_dir"], "All Trades Report.csv"), "rb") as f:
        assert f.read() == b"second\n"
    assert "All Trades Report.csv" in warnings[0]


def test_vanguard_uses_the_newest_worksheet_rather_than_merging(broker_user, tmp_path):
    account = _account(broker_user["id"], "vanguard_gia", "V")
    _upload(broker_user["id"], account, "old.csv", b"old\n")
    _upload(broker_user["id"], account, "new.csv", b"new\n")

    files, warnings = runner.build_document_set(broker_user["id"], str(tmp_path))

    with open(files["vanguard"], "rb") as f:
        assert f.read() == b"new\n"
    assert "new.csv" in warnings[0]


def test_document_filenames_are_part_of_the_calculation_inputs(broker_user):
    """Two directory reports can hold identical bytes and mean different things,
    so a rename has to invalidate a cached run."""
    account = _account(broker_user["id"], "sharesight", "SS")
    _upload(broker_user["id"], account, "All Trades Report.csv", b"same\n")

    docs = runner.input_material(broker_user["id"], 2024)["docs"]

    assert docs == [[account["id"], docs[0][1], "All Trades Report.csv"]]


# ── Hargreaves Lansdown: a trade and its contract note are separate uploads ────


def _hl_docs(missing, filenames):
    warning = (
        coverage.HL_MISSING_NOTES_PREFIX + ", ".join(missing) + coverage.HL_MISSING_NOTES_SUFFIX
    )
    docs = [{"filename": "summary.csv", "warnings": [warning, "something else"]}]
    docs += [{"filename": n, "warnings": []} for n in filenames]
    return docs


def test_hl_warning_keeps_references_whose_note_is_still_missing():
    docs = _hl_docs(["B302087054", "S302087055"], ["B302087054_BOUGHT.pdf"])

    coverage.refresh_hl_warnings(docs)

    assert docs[0]["warnings"][0].startswith(coverage.HL_MISSING_NOTES_PREFIX + "S302087055 —")
    assert docs[0]["warnings"][1] == "something else"


def test_hl_warning_clears_once_every_note_is_uploaded():
    docs = _hl_docs(["B302087054", "S302087055"], ["b302087054_bought.PDF", "S302087055_SOLD.pdf"])

    coverage.refresh_hl_warnings(docs)

    assert docs[0]["warnings"] == ["something else"]


def test_a_pdf_named_after_another_trade_does_not_clear_the_warning():
    docs = _hl_docs(["B302087054"], ["B302087054999_BOUGHT.pdf", "B302087054.csv"])

    coverage.refresh_hl_warnings(docs)

    assert "B302087054" in docs[0]["warnings"][0]


# ── Upload filenames ──────────────────────────────────────────────────────────


def test_upload_keeps_the_name_the_parser_reads(auth_client, monkeypatch):
    """A directory broker's report is recognised by its name, spaces and all, so
    the upload path must not slugify it — but must not keep a path either."""
    import io

    from blueprints import documents

    account = auth_client.post(
        "/api/accounts", json={"type": "morgan_stanley_awards", "name": "MS"}
    ).get_json()
    seen = {}

    def record(_account, path):
        seen["name"] = os.path.basename(path)
        return {"ok": True, "tx_count": 1}

    monkeypatch.setattr(documents.runner, "validate_upload", record)
    try:
        resp = auth_client.post(
            f"/api/accounts/{account['id']}/documents",
            data={
                "file": (
                    io.BytesIO(b"Vest Date,Order Number\n"),
                    "C:\\reports\\Releases Report.csv",
                )
            },
            content_type="multipart/form-data",
        )
    finally:
        auth_client.delete(f"/api/accounts/{account['id']}")

    assert resp.status_code == 201
    assert seen["name"] == "Releases Report.csv"
    assert resp.get_json()["filename"] == "Releases Report.csv"
