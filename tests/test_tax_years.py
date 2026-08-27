from datetime import date

import pytest

from core import tax_years


def test_tax_year_of_boundaries():
    assert tax_years.tax_year_of(date(2025, 4, 5)) == 2024
    assert tax_years.tax_year_of(date(2025, 4, 6)) == 2025
    assert tax_years.tax_year_of(date(2025, 12, 31)) == 2025
    assert tax_years.tax_year_of(date(2026, 1, 1)) == 2025


def test_configured_years_contiguous_and_current():
    years = tax_years.configured_years()
    assert years == list(range(years[0], years[-1] + 1))
    assert tax_years.tax_year_of(date.today()) in years


# ── The audited figures ───────────────────────────────────────────────────────
#
# Spot-checks on the values the year table was audited against gov.uk for, so a
# careless edit to the table shows up here rather than in a bill. The full list
# of sources is in each year's `sources` tuple.


def test_the_additional_rate_threshold_moved_on_6_april_2023():
    """£150,000 in 2022/23; £125,140 from 2023/24 onwards. These being the same
    figure is what made a 2022/23 bill £129 too big and the taxpayer look like
    an additional rate payer — see tests/test_filed_returns.py."""
    assert tax_years.YEARS[2022]["higher_rate_limit"] == 150000
    for year in (2023, 2024, 2025, 2026):
        assert tax_years.YEARS[year]["higher_rate_limit"] == 125140


def test_dividend_allowance_by_year():
    assert [tax_years.YEARS[y]["dividend_allowance"] for y in (2022, 2023, 2024, 2025, 2026)] == [
        2000,
        1000,
        500,
        500,
        500,
    ]


def test_dividend_rates_rise_2pp_in_2026_27():
    """Budget 2025: the ordinary and upper rates go up 2 points from 6 Apr 2026,
    the additional rate stays where it is."""
    for year in (2022, 2023, 2024, 2025):
        assert tax_years.YEARS[year]["dividend_rates"] == {
            "basic": 0.0875,
            "higher": 0.3375,
            "additional": 0.3935,
        }
    assert tax_years.YEARS[2026]["dividend_rates"] == {
        "basic": 0.1075,
        "higher": 0.3575,
        "additional": 0.3935,
    }


def test_cgt_annual_exempt_amount_by_year():
    assert [tax_years.YEARS[y]["cgt_allowance"] for y in (2022, 2023, 2024, 2025, 2026)] == [
        12300,
        6000,
        3000,
        3000,
        3000,
    ]


def test_every_year_records_a_govuk_source():
    for year in tax_years.YEARS.values():
        assert year["sources"]
        assert all(s.startswith("https://www.gov.uk/") for s in year["sources"])


# ── Bands: the one place a threshold is compared against an amount ────────────


def test_band_at_uses_the_years_own_thresholds():
    """£130,000 of taxable income is higher rate in 2022/23 and additional rate
    in 2023/24 — the same figure, two different bands, one year apart."""
    assert tax_years.bands_for(tax_years.YEARS[2022]).band_at(130000) == tax_years.HIGHER
    assert tax_years.bands_for(tax_years.YEARS[2023]).band_at(130000) == tax_years.ADDITIONAL


def test_psa_and_dividend_rate_follow_the_band():
    bands = tax_years.bands_for(tax_years.YEARS[2023])
    for income, band, psa, dividend in (
        (30000, tax_years.BASIC, 1000, 0.0875),
        (60000, tax_years.HIGHER, 500, 0.3375),
        (200000, tax_years.ADDITIONAL, 0, 0.3935),
    ):
        assert bands.band_at(income) == band
        assert float(bands.psa(band)) == psa
        assert float(bands.dividend_rate(band)) == dividend


def test_cgt_has_two_rates_not_three():
    """A gain above the basic rate band is charged at the higher rate whether
    the taxpayer is higher or additional rate."""
    bands = tax_years.bands_for(tax_years.YEARS[2024])
    assert float(bands.cgt_rate(tax_years.BASIC)) == 0.18
    assert float(bands.cgt_rate(tax_years.HIGHER)) == 0.24
    assert float(bands.cgt_rate(tax_years.ADDITIONAL)) == 0.24
    assert float(bands.cgt_rate(tax_years.HIGHER, residential=True)) == 0.24


def test_pension_and_gift_aid_widen_both_bands():
    plain = tax_years.bands_for(tax_years.YEARS[2023])
    extended = tax_years.bands_for(tax_years.YEARS[2023], 10000)
    assert extended.basic_limit == plain.basic_limit + 10000
    assert extended.higher_limit == plain.higher_limit + 10000
    # £130,000 of taxable income drops back into the higher band on a £10,000
    # gross contribution.
    assert extended.band_at(130000) == tax_years.HIGHER


def test_personal_allowance_taper():
    bands = tax_years.bands_for(tax_years.YEARS[2023])
    assert bands.personal_allowance(99000) == 12570
    assert bands.personal_allowance(110000) == 7570
    assert bands.personal_allowance(125140) == 0
    assert bands.personal_allowance(200000) == 0
    assert bands.in_pa_taper(110000)
    assert not bands.in_pa_taper(99000)
    assert not bands.in_pa_taper(130000)


# ── The self-check ────────────────────────────────────────────────────────────


def _broken(monkeypatch, tax_year, **changes):
    """Run the self-check against a copy of the table with `changes` applied."""
    years = {y: dict(v) for y, v in tax_years.YEARS.items()}
    years[tax_year].update(changes)
    monkeypatch.setattr(tax_years, "YEARS", years)
    with pytest.raises(tax_years.TaxTableError) as exc:
        tax_years._self_check()
    return str(exc.value)


def test_the_table_as_shipped_passes_its_own_check():
    tax_years._self_check()


def test_a_negative_allowance_is_caught(monkeypatch):
    assert "negative" in _broken(monkeypatch, 2024, cgt_allowance=-1)


def test_an_allowance_that_tapers_past_the_additional_rate_is_caught(monkeypatch):
    """The taper must be over by the time 45% starts, or the year charges the
    additional rate inside the 60% zone."""
    message = _broken(monkeypatch, 2024, higher_rate_limit=120000)
    assert "still tapers" in message


def test_a_taper_end_that_is_not_the_arithmetic_is_caught(monkeypatch):
    assert "runs out at" in _broken(monkeypatch, 2024, pa_taper_end=130000)


def test_rates_that_fall_as_the_band_rises_are_caught(monkeypatch):
    message = _broken(
        monkeypatch, 2024, dividend_rates={"basic": 0.40, "higher": 0.10, "additional": 0.05}
    )
    assert "rates fall as the band rises" in message


def test_a_cgt_rate_change_outside_the_year_leaves_a_gap(monkeypatch):
    """The rate periods have to tile the tax year: every disposal date in it
    falls in exactly one period, or a gain is charged twice or not at all."""
    message = _broken(
        monkeypatch,
        2024,
        cgt_mid_year_change={"date": "2026-10-30", "rates_before": {"basic": 0.1, "higher": 0.2}},
    )
    assert "falls outside the tax year" in message


def test_cgt_rate_periods_cover_every_year_exactly(monkeypatch):
    for tax_year, year in tax_years.YEARS.items():
        periods = tax_years.cgt_rate_periods(year)
        assert periods[0]["start"] == tax_years.tax_year_start(tax_year)
        assert periods[-1]["end"] == tax_years.tax_year_end(tax_year)
        for before, after in zip(periods, periods[1:], strict=False):
            assert (after["start"] - before["end"]).days == 1


def test_2024_25_has_two_cgt_rate_periods():
    periods = tax_years.cgt_rate_periods(tax_years.YEARS[2024])
    assert len(periods) == 2
    assert periods[0]["shares"] == {"basic": 0.10, "higher": 0.20}
    assert periods[1]["shares"] == {"basic": 0.18, "higher": 0.24}
    assert periods[0]["end"] == date(2024, 10, 29)
    assert periods[1]["start"] == date(2024, 10, 30)


# ── The parameter table the UI shows ──────────────────────────────────────────


def test_parameters_are_built_from_the_table_itself():
    groups = tax_years.parameters(2022)
    rows = {r["label"]: r["value"] for g in groups for r in g["rows"]}
    assert rows["Additional rate above"] == 150000
    assert rows["Dividend allowance"] == 2000
    assert rows["Annual exempt amount"] == 12300
    assert rows["Dividend rates (basic / higher / additional)"] == "8.75% / 33.75% / 39.35%"
    assert all(g["source"].startswith("https://www.gov.uk/") for g in groups)


def test_parameters_show_both_cgt_rate_periods_in_a_split_year():
    labels = [r["label"] for g in tax_years.parameters(2024) for r in g["rows"]]
    assert any("6 Apr 2024 – 29 Oct 2024" in x for x in labels)
    assert any("30 Oct 2024 – 5 Apr 2025" in x for x in labels)


def test_parameters_for_an_unknown_year():
    assert tax_years.parameters(1999) is None
