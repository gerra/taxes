import csv

from engine.runner import convert_bank_csv, merge_csv_files, parse_any_date


def _write(path, rows):
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(rows)


def _read(path):
    with open(path, newline="") as f:
        return list(csv.reader(f))


def test_parse_dates():
    for raw in ("2025-01-31", "31/01/2025", "31 Jan 2025", "31.01.2025", "2025-01-31T10:00:00"):
        assert parse_any_date(raw).isoformat() == "2025-01-31"


def test_merge_dedupes_across_files_keeps_dupes_within(tmp_path):
    header = ["Date", "Action", "Symbol"]
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    # same row twice in one file = two real transactions
    _write(a, [header, ["01/02/2024", "Buy", "X"], ["01/02/2024", "Buy", "X"]])
    # overlap chunk repeats one of them once — must not add a third copy
    _write(b, [header, ["01/02/2024", "Buy", "X"], ["05/03/2024", "Sell", "X"]])
    out = tmp_path / "out.csv"
    merge_csv_files([str(a), str(b)], str(out), ("Date", "Action"))
    rows = _read(out)
    assert rows[0] == header
    assert rows[1:].count(["01/02/2024", "Buy", "X"]) == 2
    assert rows[1:].count(["05/03/2024", "Sell", "X"]) == 1


def test_merge_skips_preamble(tmp_path):
    a = tmp_path / "a.csv"
    _write(
        a,
        [
            ["Transactions for account XXX as of 01/01/2025"],
            ["Date", "Action", "Symbol"],
            ["01/02/2024", "Buy", "X"],
        ],
    )
    out = tmp_path / "out.csv"
    merge_csv_files([str(a)], str(out), ("Date", "Action"))
    rows = _read(out)
    assert rows[0] == ["Date", "Action", "Symbol"]
    assert len(rows) == 2


def test_merge_pair_rows(tmp_path):
    header = ["Date", "Symbol", "FairMarketValuePrice"]
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    rec1 = [["2024/01/05", "GOOG", ""], ["", "", "140.5"]]
    rec2 = [["2024/02/05", "GOOG", ""], ["", "", "150.0"]]
    _write(a, [header, *rec1])
    _write(b, [header, *rec1, *rec2])
    out = tmp_path / "out.csv"
    merge_csv_files([str(a), str(b)], str(out), ("Date", "Symbol"), pair_rows=True)
    rows = _read(out)
    assert len(rows) == 5  # header + 2 records x 2 rows
    assert rows[1:3] == rec1 and rows[3:5] == rec2


def test_convert_bank_csv(tmp_path):
    src = tmp_path / "bank.csv"
    _write(
        src,
        [
            ["Date", "Description", "Amount"],
            ["31/05/2025", "Gross interest", "1.23"],
            ["01/06/2025", "Groceries", "-50.00"],
            ["30/06/2025", "Gross interest", "1,024.50"],
        ],
    )
    mapping = {
        "date_col": "Date",
        "amount_col": "Amount",
        "desc_col": "Description",
        "include_contains": "interest",
    }
    rows = convert_bank_csv(str(src), mapping)
    assert rows == [
        ["2025-05-31", "INTEREST", "", "1", "1.23", "0", "GBP"],
        ["2025-06-30", "INTEREST", "", "1", "1024.50", "0", "GBP"],
    ]


def test_merge_drops_footer_rows(tmp_path):
    a = tmp_path / "a.csv"
    _write(
        a,
        [
            ["Date", "Action", "Symbol"],
            ["01/02/2024", "Buy", "X"],
            ["Transactions Total", "", ""],
        ],
    )
    out = tmp_path / "out.csv"
    merge_csv_files([str(a)], str(out), ("Date", "Action"))
    rows = _read(out)
    assert len(rows) == 2
    assert rows[1] == ["01/02/2024", "Buy", "X"]


def test_fork_version_is_commit_or_version():
    from engine.runner import fork_version

    v = fork_version()
    assert v and v != "unknown"
