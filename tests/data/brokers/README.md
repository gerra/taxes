# Broker export fixtures

Sanitised example exports, one per broker the app accepts, used to check that an
upload validates through the real cgt-calc parser (see
`tests/test_engine_integration.py`).

The CSVs are copies of the fork's own published examples
(github.com/gerra/capital-gains-calculator, `tests/<broker>/data/`), so they move
with the parsers they exercise — refresh them from there after a fork upgrade
that changes a format.

The two HL contract notes are synthetic PDFs generated for these tests, matching
the layout the fork's own HL tests build. No file here contains real account
data.
