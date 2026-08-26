from datetime import date

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
