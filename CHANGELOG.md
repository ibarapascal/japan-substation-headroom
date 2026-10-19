# Changelog

## 0.1.0 — 2026-10-20

First release.

Contents:

- Code to download the hourly transformer loading results and transformer capacity tables of
  Japan's ten general transmission and distribution operators, parse them into harmonized
  tables, compute bank-year and substation-year statistics, and reconstruct load-direction
  headroom (`fetch/`, `parse/`, `derive/`, `pipeline/`).
- Released tables of the build of 2026-10-19 (`data/`): capacity tables (7,130 rows),
  substation-year statistics (8,855 rows), bank-year statistics (13,766 rows), headroom
  reconstruction (8,855 rows), join report and unmatched keys, and the retrieval manifest of the
  files used (230 rows).
- TEPCO capacity history 2019-2025 from 133 Internet Archive captures (`data/history/`;
  22,682 rows from the 114 readable captures).
- Data center site register (`data/sites/`; 184 sites).
- Coded voluntary siting guides and per-operator disclosure inventory (`guides/`); Chubu as
  counts per voltage and capacity band.
- `python -m fetch archive` (download of the archived TEPCO hourly loading zips) and
  `python -m pipeline compare` (comparison of a rebuild with the released tables).

Verified:

- The test suite passes (118 tests, Python 3.9.6).
- `python -m pipeline compare --built data --released data` returns 0 (10 tables, no differing
  rows or cells).
