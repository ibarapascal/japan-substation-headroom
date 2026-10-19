# Japan transformer-level hourly loading and capacity tables: harmonized derived dataset

Code and derived tables built from two disclosures that each of Japan's ten general
transmission and distribution operators publishes on its own website under the national
guideline on grid information disclosure (系統情報の公表の考え方):

1. **Hourly transformer loading results** (地点別需要・系統潮流実績, transformer sheet): measured
   power flow on the secondary side of substation transformers, one value per hour and per
   transformer (or per transformer group / secondary bus, depending on the operator), published
   once a year per fiscal year (April to March).
2. **Transformer capacity tables** (予想潮流・空容量一覧, transformer sheet): per substation and
   voltage level, the number of transformer units, rated capacity (100% x units), operating
   capacity, forecast flow and published available capacity. The published available capacity is
   computed for connecting generation (reverse-flow direction).

The pipeline downloads the published files, parses the operator-specific layouts into one
harmonized hourly long table and one capacity table, computes bank-year and substation-year
statistics, and joins the substation-year statistics to the capacity tables to reconstruct
load-direction headroom under two definitions:

- `headroom_naive_mw = operating_mw - peak_mw`
- `headroom_n1_mw = (units - 1) / units * rated_mw - peak_mw` (only when `units >= 2`)

where `peak_mw` is the coincident annual peak of the substation (banks summed hour by hour).

The repository has three further parts, each documented in its own section below:

- **TEPCO capacity history, 2019-2025**: the per-area capacity lists that TEPCO Power Grid
  published until 2025, parsed from copies held by the Internet Archive into one long table.
- **Data center site register**: data center sites in Japan, identified from facility-level
  emission reports of the national reporting system (EEGS) and from public announcements, with
  type, status, stated capacity and representative coordinates.
- **Voluntary siting guides and disclosure inventory** (`guides/`): factual items (site names,
  places, voltages, stated capacity bands, edition dates, URLs) coded from the voluntary
  demand-side siting guides of the ten operators (Chubu as counts per voltage and capacity band),
  and a per-operator inventory of the items published under the grid information disclosure
  guideline.

## Sources

The source files are **not redistributed** in this repository. Each retrieval writes
`manifest.csv` with the URL, local file name, size, SHA-256 and retrieval time of every file, so a
retrieval can be checked against the files used for a published build. Source files remain
subject to the publishers' terms of use (see "Sources and third-party terms").

`data/manifest.csv` is the manifest of the retrieval used for the released build (230 rows):
220 files downloaded from the operators' pages on 2026-10-19, 6 archived TEPCO zips from the
Internet Archive (`tepco_history/wayback/`), 3 earlier copies of TEPCO files
(`tepco_history/copy_202607/`, byte-identical to the 2026-10-19 downloads of the same files and
therefore skipped by the build; they are not needed for a rebuild), and one row recording that
Chubu publishes no capacity file. The `note` column keeps the link text and section heading of
each file on the operator's page.

| Operator id | Publisher | Entry page(s) used for link resolution |
|---|---|---|
| hokkaido | Hokkaido Electric Power Network | https://www.hepco.co.jp/network/con_service/public_document/bid_info.html |
| tohoku | Tohoku Electric Power Network | https://nw.tohoku-epco.co.jp/consignment/system/demand/ ; https://nw.tohoku-epco.co.jp/consignment/system/announcement/ |
| tepco | TEPCO Power Grid | https://www.tepco.co.jp/pg/consignment/system/ |
| chubu | Chubu Electric Power Grid | https://powergrid.chuden.co.jp/goannai/hatsuden_kouri/takuso_kyokyu/rule/ |
| hokuriku | Hokuriku Electric Power Transmission & Distribution | https://www.rikuden.co.jp/nw_notification/U_154seiyaku.html |
| kansai | Kansai Transmission and Distribution | https://www.kansai-td.co.jp/consignment/disclosure/distribution-equipment/index.html |
| chugoku | Chugoku Electric Power Transmission & Distribution | https://www.energia.co.jp/nw/service/retailer/keitou/access/ |
| shikoku | Shikoku Electric Power Transmission & Distribution | https://www.yonden.co.jp/nw/line_access/data.html |
| kyushu | Kyushu Electric Power Transmission and Distribution | https://www.kyuden.co.jp/td/service/wheeling/disclosure.html |
| okinawa | Okinawa Electric Power | https://www.okiden.co.jp/business-support/service/juyo-and-sohaiden/ (and its sub-pages `jisseki1/`, `local-jisseki/`) |

File links are resolved from the anchors of these pages at retrieval time (several operators use
opaque or changing file names). All fiscal years linked from the pages are retrieved. For TEPCO,
fiscal years no longer linked from the page (FY2018-2021, FY2023 154 kV group) are taken from
copies held by the Internet Archive; `python -m fetch archive` downloads them (see
"Reproducing") and their Wayback URLs are recorded in the manifest.
Chubu Electric Power Grid publishes no capacity file (the information is only available in an
interactive map); the manifest records this as `not_published_as_file`.

## Repository layout

```
fetch/        downloader: entry pages -> link rules -> files + manifest.csv
parse/        one module per operator + shared helpers
  common.py     decoding, missing-value tokens, numbers, voltages, timestamps
  names.py      substation_key normalisation
  wide.py       generic parser for the common hourly layout
  capacity.py   generic parser for the capacity template
  tables.py     CSV / XLSX / XLS / zip member enumeration
  <operator>.py operator-specific rules (see each module docstring)
derive/       stats.py (bank-year, substation-year), headroom.py (join + headroom)
pipeline/     python -m pipeline build (one-command build), longtable.py (long-table writer),
              history.py, sites.py, compare.py (python -m pipeline compare: rebuild vs released tables)
tests/        pytest suite; fixtures/ holds short excerpts (first lines) of published files
guides/       hand-coded voluntary siting guides and per-operator disclosure inventory (see guides/README.md)
sites/        hand-curated inputs of the data center site register
data/         released derived tables from the build of 2026-10-19 and its manifest (see "Released data")
```

## Reproducing

Python 3.9 or later. `requirements.txt` gives minimum versions; `requirements-tested.txt` lists
the versions with which the test suite passed (Python 3.9.6, numpy 2.0.2, pyarrow 21.0.0,
openpyxl 3.1.5, xlrd 2.0.2, pytest 8.4.2). `pipeline history` also needs `pdftotext`
(poppler-utils). Run the commands from the repository root; `raw/` and `build/` are the
default input and output directories used below (both are ignored by git).

```
pip install -r requirements.txt
python -m fetch download --out raw/20261019            # all operators; idempotent
python -m fetch archive --out raw/20261019             # archived TEPCO zips -> raw/20261019/tepco_history/wayback/
python -m pipeline build --raw raw/20261019 --out build/
python -m fetch history --out raw/history              # TEPCO capacity history (section below)
python -m pipeline history --raw raw/history --out build/
python -m fetch eegs --out raw/eegs                    # data center site register (section below)
python -m pipeline sites --eegs raw/eegs --out build/
python -m pytest -q tests
python -m pipeline compare --built build/ --released data/
```

`fetch download` waits at least 2 seconds between requests, sends a browser User-Agent, and skips
files that already exist with the SHA-256 recorded in the manifest (`--refresh` forces
re-download). `fetch list` prints the resolved links without downloading.

`fetch archive` downloads the six archived TEPCO hourly loading zips listed in
`fetch/archive.py` from the Internet Archive (unmodified captures, at least 5 seconds between
requests), checks them against the SHA-256 in `data/manifest.csv`, and registers them in the
retrieval's manifest. The files are:

| Local file (`tepco_history/wayback/`) | Wayback URL |
|---|---|
| `tyouryuuzisseki_20190817.zip` | https://web.archive.org/web/20190817044620/https://www.tepco.co.jp/pg/consignment/system/pdf/tyouryuuzisseki.zip |
| `tyouryuuzisseki_20220420.zip` | https://web.archive.org/web/20220420084636/https://www.tepco.co.jp/pg/consignment/system/pdf/tyouryuuzisseki.zip |
| `tyouryuuzisseki2020_20220420.zip` | https://web.archive.org/web/20220420084550/https://www.tepco.co.jp/pg/consignment/system/pdf/tyouryuuzisseki2020.zip |
| `tyouryuuzisseki2021_20240209.zip` | https://web.archive.org/web/20240209033737/https://www.tepco.co.jp/pg/consignment/system/pdf/tyouryuuzisseki2021_0805.zip |
| `66kVtide_etc_20220119.zip` | https://web.archive.org/web/20220119140622/https://www.tepco.co.jp/pg/consignment/system/pdf/66kVtide_etc.zip |
| `tyouryu_154kV_20250118.zip` | https://web.archive.org/web/20250118093740/https://www.tepco.co.jp/pg/consignment/system/pdf/tyouryu_154kV.zip |

Files obtained in another way can be placed in `raw/20261019/tepco_history/` and registered
with `python -m fetch ingest-archive --out raw/20261019`.

`pipeline build` processes one file at a time and one (operator, fiscal year) at a time for the
statistics; identical files (same SHA-256) are processed once. Intermediate per-year arrays are
written to `OUT/_work/` and removed at the end (`--keep-work` keeps them).

### Run time, memory and download volume

| Stage | Measured | Notes |
|---|---|---|
| `pipeline build` (all operators, all fiscal years) | about 3 min, peak memory about 2 GB | single thread, 12-core desktop |
| `pipeline history` (133 PDFs) | about 10 s, peak resident memory about 60 MB | laptop |
| `pipeline sites` | about 1 s, peak resident memory about 55 MB | |

The download stages were not timed. Estimates from the request intervals and the file sizes in
the manifests: `fetch download` makes about 230 requests (entry pages and 220 files, about
350 MB) at 2 s or more apart, so at least about 8 minutes plus transfer time; `fetch archive`
fetches 6 files (about 155 MB) at 5 s or more apart; `fetch history` fetches 133 files (about
160 MB) at 5 s or more apart, so at least about 11 minutes plus transfer time; `fetch eegs`
fetches 3 files.

Constraints on running stages in parallel:

- Do not run two `pipeline build` processes on the same output directory at the same time; they
  share `OUT/_work/` and overwrite each other's tables.
- Run `pipeline build` once for all operators. `--operators` builds a subset, but each run
  rewrites `capacity/`, `stats/`, `headroom/headroom_reconstructed.csv` and
  `headroom/join_report.csv` with that subset only, so building operators in batches into one
  output directory leaves only the last batch.
- `pipeline history` and `pipeline sites` write to their own subdirectories (`history/`,
  `sites/`) and can run alongside `pipeline build`.

### Hand-coded inputs

`guides/` and `sites/` are inputs coded by hand from the sources they cite; no script generates
them. Their coding rules are in `guides/README.md` (siting guides and disclosure inventory) and in
"Data center site register" below together with `derive/dc_sites.py` (classification rules,
keyword and operator lists).

## Outputs

| Path | Content | In `data/` |
|---|---|---|
| `capacity/capacity_table.csv` (+ `.parquet`) | harmonized capacity tables | CSV only |
| `stats/substation_year_stats.csv` (+ `.parquet`) | substation x secondary voltage x fiscal year statistics | CSV only |
| `stats/bank_year_stats.csv` | column (bank) x fiscal year statistics | yes |
| `stats/column_duplicates.csv` | columns published by more than one file, overlaps and conflicts | not included |
| `headroom/headroom_reconstructed.csv` (+ `.parquet`) | join of substation-year statistics to capacity, headroom | CSV only |
| `headroom/join_report.csv` | join outcome counts and match rates per operator and fiscal year | yes |
| `headroom/unmatched_keys.csv` | load groups of the latest fiscal year without a capacity match | yes |
| `load_long/<operator>.parquet` | hourly long table | not included (re-creatable from the sources) |
| `logs/` | per-table parse report, per-file status, build log | not included |

### load_long (hourly long table)

| Field | Description |
|---|---|
| operator | operator id |
| source_file | file path within the retrieval, `!member` for zip members, `#sheet` for workbook sheets |
| substation_raw | substation name as published (NFKC-normalised) |
| substation_key | join key (see below); `#<bank>` when the column has no usable name |
| bank | published column identifier (transformer No / abbreviation / bank label) |
| v1_kv, v2_kv | primary / secondary voltage as published, kV, text ('6.6', '110/66', '22-13.8'); TEPCO: v1_kv is the voltage group of the file (66, 154; empty for the bulk system), v2_kv empty |
| ts_local | start of the hourly interval, Japan Standard Time (no time zone stored) |
| mw | MW, positive from the primary to the secondary side; empty when missing |
| flag | ok / zero / negative / missing / marked (value published with an asterisk) |

### capacity_table

| Field | Description |
|---|---|
| operator, substation_raw, substation_key | as above |
| v1_kv, v2_kv | primary / secondary voltage (blank where the publisher leaves it blank) |
| category | secondary-voltage class: distribution_6kV (< 7 kV), subtransmission_7_33kV, transmission_44kV_plus, voltage_unpublished |
| publisher_class | class label given by the publisher (TEPCO only, e.g. 配電用変電所, 154kV, 基幹 275kV) |
| units | number of transformer units |
| rated_mw | 設備容量 (100% x units), MW |
| operating_mw | 運用容量値, MW |
| forecast_flow_mw | 予想潮流, MW (generation-direction study value; mostly empty for 6.6 kV) |
| available_mw_published | published available capacity for the equipment itself (当該設備), MW |
| n1_note | N-1 電制 applicability text as published |
| source_file, as_of | source file and publication date stated in the file (or YYYY-MM from the file name) |

### substation_year_stats

One row per operator x substation_key x secondary voltage x fiscal year (for TEPCO and other
columns without a secondary voltage: per primary-voltage group).

| Field | Description |
|---|---|
| fiscal_year | April of `fiscal_year` to March of `fiscal_year + 1` |
| v2_kv / v1_kv | secondary voltage of the group / primary voltages of its banks (';'-separated) |
| n_banks, n_banks_reporting | columns in the group / columns with at least one value in the year |
| hours_in_year, valid_hours | 8760 or 8784 / hours where every reporting column has a value |
| peak_mw, peak_ts_local | coincident annual maximum of the summed series and its hour |
| p99_mw, p95_mw | percentiles of the summed series over valid hours (linear interpolation) |
| zero_hours, negative_hours | valid hours where the summed series is 0 / below 0 |
| bank_zero_hours, bank_negative_hours | column-hours equal to 0 / below 0, summed over the group |
| n_source_files | number of files contributing to the group |

`bank_year_stats` gives the same quantities per column (valid / missing / zero / negative hours,
max with timestamp, min, mean, p99, p95).

### headroom_reconstructed

Fields of the substation-year row (`peak_mw`, `peak_ts_local`, `valid_hours`, ...) plus
`join_status`, `n_capacity_rows`, `capacity_category`, `units`, `rated_mw`, `operating_mw`,
`n1_capacity_mw` (= (units - 1) / units x rated_mw), `headroom_naive_mw`, `headroom_n1_mw`,
`n1_note` (`single_unit` when units < 2, `aggregated_rows` when several capacity rows were
summed, `units_or_rated_missing`) and `capacity_as_of`. Headroom is computed for every fiscal
year against the single capacity snapshot of the retrieval.

## Method notes

- **Timestamps.** Some operators label hours 01:00 ... 24:00 (or next-day 00:00); others 00:00 ...
  23:00. A table whose first hour is 01:00 is treated as hour-ending and shifted back one hour, so
  `ts_local` is always the interval start. The convention detected for each table is in
  `logs/parse_report.csv`.
- **Missing values.** "-", "ー", "－", "―", "‐", "欠測", "＊", "*" and empty cells are read as
  missing. Values with a leading asterisk (e.g. `*185`) are kept and flagged `marked`.
- **Numbers.** Thousands separators are removed. In capacity files where an unquoted thousands
  separator splits one number over two cells, the cells are re-merged using the text column
  運用容量制約要因 (and the N-1 applicability column) as alignment anchors.
- **TEPCO columns.** Element columns of transmission lines are dropped. Columns that publish the
  sum of several banks (e.g. `1・2・3B`) are dropped when the individual banks are also published,
  and kept otherwise.
- **Repeated columns.** The same column published in several files is merged hour by hour (first
  file wins, later files fill gaps); overlaps and conflicting values are listed in
  `column_duplicates.csv`.
- **substation_key.** NFKC; whitespace removed; bracketed annotations removed (including the
  "(変)" marker); voltage annotations such as "66/22kV" removed; trailing 変電所, 開閉所, 変換所,
  SS, S/S and 配変N号 removed; ヶ/ヵ/が folded to ケ and の to ノ; ASCII upper-cased.
  Columns without a name, or whose name equals the column number, get `#<bank>` and are not joined.
- **Records printed on several lines.** Some capacity files print one transformer group on two
  lines (one carrying the forecast flow, the next the available capacity) or list it under two grid
  sections. Records from one file with the same substation_key, primary and secondary voltage,
  number of units, rated capacity and operating capacity are merged into one record (empty fields
  filled from the later record) before the join; the build log reports the number merged.
- **Join.** Same operator and same substation_key. Groups with a secondary voltage are joined to
  all capacity rows of the key with the same secondary voltage (6, 6.6 and 6.9 kV are one class)
  and those rows are summed; rows with identical voltages, units, rated and operating capacity (one
  group listed in two regional files) are counted once. Groups without a secondary voltage are joined on the primary-voltage
  group (TEPCO: the 66 kV group also takes rows whose voltage is left blank by the publisher, the
  bulk group takes 500 and 275 kV rows). Outcomes per operator and fiscal year are written to
  `join_report.csv` by every build; `match_rate_named` is matched groups over groups with a name.

## Known limitations

- The definition of operating capacity (運用容量値) differs between operators: for some it is
  below the rated capacity by an N-1 or thermal margin, for others it equals the rated capacity.
- The N-1 definition assumes units of equal rating; when several capacity rows are summed
  (`aggregated_rows`) it is applied to the totals.
- Loading values are net flows: distributed generation downstream reduces them and can make them
  negative. TEPCO states that some distribution transformers record 0 instead of the reverse flow;
  zero hours are reported, not corrected.
- Measured flows do not include load that is contracted but not yet connected.
- Most operators publish integer MW; small transformers are therefore coarse.
- Publishers merge flows of dedicated lines and single-unit generator lines into nearby
  substations, aggregate some results per secondary bus (Shikoku, Kansai), omit facilities
  supplying critical infrastructure, and revise past results without notice.
- Coverage differs by operator: Hokkaido publishes 187 kV and above plus local interconnecting
  transformers only; Chugoku and Kyushu do not publish distribution transformers; TEPCO's 66 kV
  group includes 66/6.6 kV distribution banks; Okinawa publishes all distribution transformers.
- Capacity tables are a snapshot at retrieval time, while loading results cover past fiscal years.
- Chubu publishes no capacity file; its loading statistics have no headroom.
- Chubu FY2018-2022 workbooks publish column numbers only; names and voltages are taken from later
  workbooks by (sheet level, number). Okinawa FY2019-2023 workbooks publish no voltages; they are
  taken from later files by substation name.
- Name-based matching can fail on spelling variants not covered by the normalisation and cannot
  separate two substations with the same name within one operator.
- No coordinates are included.

## TEPCO capacity history (archived capacity lists, 2019-2025)

### Source

Until 2025 TEPCO Power Grid published one capacity list per area (運用容量一覧表, file
`akiyouryou_<area>.pdf`) at `https://www.tepco.co.jp/pg/consignment/system/pdf_new/`. The 14 areas
are `kikan` (bulk system, 275 kV and above) and `chiba`, `fukushima`, `gunma`, `ibaraki`,
`kanagawa`, `nagano`, `niigata`, `saitama`, `shizuoka`, `tama`, `tochigi`, `tokyo23`, `yamanashi`.
The files are no longer linked from the operator's site; this dataset uses the copies held by the
Internet Archive. `fetch/tepco_history_snapshots.csv` lists the 133 captures used (2019-07-26 to
2025-08-10; one row per distinct file content per area) with size and SHA-256. The capture
timestamp is part of the local file name (`akiyouryou_<area>_<YYYYMMDDhhmmss>.pdf`), from which
the Wayback URL is rebuilt. The PDFs are not redistributed.

Each file lists, per voltage class, lines (送電線) and substation transformers (変電所) with rated
capacity (100% x units), operating capacity (運用容量値), the binding constraint, the published
available capacity for the equipment itself (当該設備) and including upstream equipment (上位系考慮),
and N-1 generation-tripping applicability; area files also list every distribution substation
area (配電用変電所エリア) with the same columns. This format has no forecast-flow column.

### Reproducing

Requires `pdftotext` (poppler-utils) on the PATH.

```
python -m fetch history --out raw/history          # 133 captures, at least 5 s between requests
python -m pipeline history --raw raw/history --out build/
```

The captures (file name, size, SHA-256) are listed in `fetch/tepco_history_snapshots.csv`;
`fetch history` reports any download whose SHA-256 differs from that list.

`pipeline history` reads the PDFs one at a time through `pdftotext -layout` and keeps only the
summary columns in memory. A full run (133 files, about 160 MB of PDFs) took about 10 s with a
peak resident memory of about 60 MB on a laptop.

### Outputs (`build/history/`)

| Path | Content |
|---|---|
| `tepco_capacity_history.csv` | long table, one row per capture x published table row |
| `tepco_capacity_history_files.csv` | download index: file name, area, capture timestamp, original and Wayback URL, bytes, SHA-256, parse status and row counts |
| `distribution_area_summary.csv` | per area and capture: distribution substation areas, areas with zero available capacity, median available capacity |

`tepco_capacity_history` fields:

| Field | Description |
|---|---|
| snapshot_date | date of the Internet Archive capture (from the capture timestamp) |
| capture_timestamp | capture timestamp, YYYYMMDDhhmmss (UTC) |
| area | area id of the file (see above) |
| area_label | area label printed in the table header (blank for `kikan`) |
| as_of | document date printed in the file (資料作成日) |
| data_basis_date | date of the grid state the figures are based on (... 時点), when printed |
| table_type | `line`, `substation`, `distribution_area` |
| voltage_class | row voltage class as published (`500kV`, `275kV`, `154kV`, `66kV`, `22kV`) or `distribution_area` |
| row_no | number of the row (line / transformer No, or distribution area number) |
| name | equipment name as published (NFKC); some 22 kV substations are published under a number only |
| name_key | `substation_key(name)` (see Method notes above) |
| v1_kv, v2_kv | primary / secondary voltage of substation rows (`6.6以下` is written `6.6`) |
| line_kv | voltage of line rows |
| units | number of transformer units (substations) or circuits (lines) |
| rated_mw | 設備容量 (100% x units or circuits), MW |
| operating_mw | 運用容量値, MW |
| constraint | constraint of the operating capacity as published (熱容量, ...) |
| forecast_flow_mw | always empty: not published in this format (kept for alignment with `capacity_table`) |
| available_mw_published | published available capacity of the equipment itself (当該設備), MW, generation direction |
| available_upper_mw | published available capacity including upstream equipment (上位系等考慮), MW |
| n1_applicable | N-1 generation tripping applicability (可 / 不可), footnote marks removed |
| n1_mw | N-1 applicable amount, MW |
| parse_mode | `positional` or `anchor` (see below) |
| source_file | capture file name |

Masked cells (`-`, `‑`, `※`, ...) and cells left blank by the publisher (equipment marked ◇,
non-disclosed) are empty.

### Method notes

- Each table row is one text line of `pdftotext -layout`. Section headers set the voltage class;
  the column header (送電線名 / 変電所名) sets the table type. A row is recognised by the voltage
  class token followed by the row number (`154kV 1 ...`), or, in distribution area tables, by the
  area number after the area label. The area label may wrap onto the previous line; it is not
  needed to read the row.
- Cells after the name are read in published order (`positional`). When that reading fails the
  checks (capacities numeric or masked, constraint cell not numeric), the row is read around the
  constraint cell (`anchor`): available capacities after it, the cells before it assigned from
  the left, so capacities left blank by the publisher stay empty. In the published build 22,682
  rows were read, 6 of them in anchor mode, none skipped.
- A row number printed without a space before the name (`146長作線`) is split.
- To follow one piece of equipment over time, use `area`, `table_type`, `voltage_class`,
  `name_key` and, for substations, `v1_kv`/`v2_kv`; `row_no` is renumbered between editions, and
  one substation can have several rows (one per transformer group).

### Known limitations

- 19 of the 133 captures (all from 2021-12-05, 2024-04-12, 2024-04-17 and 2024-11-03) are served
  by the Internet Archive truncated at exactly 1,048,576 bytes. They cannot be read and are
  listed with status `unreadable`. 114 captures are parsed.
- Capture density is irregular: 4 to 18 captures per area, mostly yearly in 2019-2022 and more
  frequent in 2024-2025. The capture date can lag the document date (`as_of`) by weeks.
- `fukushima`, `nagano`, `niigata` and `shizuoka` cover only the part of the prefecture served by
  TEPCO, as stated in their labels.
- Available capacity is the generation-direction value. From fiscal 2023 non-firm connection
  applies, so zero available capacity does not mean that generation cannot connect.
- Names that wrap onto two text lines keep only the part printed on the row line. Remarks
  (備考) and the output-control columns added in later editions are not extracted.

## Data center site register

### Sources

1. **EEGS facility-level emission reports** (温室効果ガス排出量算定・報告・公表制度, Ministry of the
   Environment): facility list with company, facility name, industry, municipality and reported
   emissions, FY2021-FY2023, national download
   `https://eegs.env.go.jp/ghg-santeikohyo-result/search/download?repYear=<FY>&prefectureCode=000000&emitterType=office`.
   The files are not redistributed.
2. **Public announcements** for sites that do not appear in EEGS (new, planned, or below the
   reporting threshold) and for disclosed capacities of EEGS sites: operator press releases and
   web pages, municipal and ministry documents, and freely accessible news articles, compiled in
   July 2026 (`sites/curated_sites.csv`, `sites/eegs_site_facts.csv`). Facts available only
   from subscription news services or from secondary aggregators without a primary source are
   not included.
3. **Municipality representative points** from the address search of the Geospatial Information
   Authority of Japan (`sites/municipality_points.csv`).

### Reproducing

```
python -m fetch eegs --out raw/eegs                 # national_office_<FY>.zip, FY2021-FY2023
python -m pipeline sites --eegs raw/eegs --out build/
```

`fetch eegs` saves one zip per fiscal year (`national_office_2021.zip` ... `_2023.zip`) and logs
the HTTP status, size and SHA-256 of each; it writes no manifest. No download index of the EEGS
files used for the released register is included. If the publisher has changed the published
reports since the release, a new download differs from the one used, and the differences show up
in `pipeline compare` for `sites/data_center_sites.csv`.

A full run takes about 1 s with a peak resident memory of about 55 MB.

### Classification rules (`derive/dc_sites.py`)

- **Status of an EEGS facility**, from the published company and facility name and the industry:
  - *excluded*: the name matches a non-data-center facility type (hospital, power plant,
    transmitter or satellite station, R&D, head office, branch or sales office, factory,
    substation, ...), or the name contains "DC" while the industry is wholesale, retail, road
    freight, food manufacturing or warehousing (distribution center);
  - *confirmed*: the company is on the list of data-center businesses (`OPERATORS_DC`), or the
    facility name contains a data-center keyword (データセンター, データセンタ, クラウドセンタ,
    コロケーション, DC/IDC as a word, テレハウス);
  - *suspected*: an ambiguous facility name (システムセンター, ネットワークセンター, 情報センター,
    コンピュータセンター, TC/NC, ...) of a company with mixed businesses (`OPERATORS_MIXED`), or
    an ambiguous name in a data-center-adjacent industry (internet services,
    telecommunications, information services, broadcasting, media production);
  - otherwise excluded.
- Facilities are keyed by reporting company code and facility; a facility keeps the highest
  status of any year and its latest name, industry and municipality. Facilities of one company
  whose names, with spaces, bracketed text and legal-form words removed, are equal or contained
  in one another are merged.
- Suspected facilities that the operator itself presents as data centers are confirmed
  (`sites/eegs_overrides.csv`, with the page used). One of them (`brand_pattern`) is confirmed
  because sister facilities of the same name pattern are presented as data centers.
- **Type** (`hyperscale_cloud`, `colo_metro`, `telecom_enterprise`, `ai_campus`): from the company
  name (`TYPE_RULES`), overridden per reporting company by `sites/eegs_operator_facts.csv`;
  facilities matching no rule are `telecom_enterprise`. Announcement rows carry their type in
  `sites/curated_sites.csv`. `ai_campus` is used for GPU- or AI-oriented sites announced from
  2024 on.

### Output (`build/sites/data_center_sites.csv`)

| Field | Description |
|---|---|
| site_id | `eegs-<hash>` (company code and facility) or `pub-<hash>` (site name); stable across builds |
| site_name | facility name as reported to EEGS (NFKC), or the announced site name |
| operator | reporting company (EEGS) or announcing company |
| operator_group | brand or group of the operator where it differs from the legal entity |
| prefecture, municipality | location as reported; EEGS reports designated cities without the ward |
| type, type_basis | site type; basis `operator_rule`, `operator_fact`, `default`, `curated` |
| status | `confirmed` or `suspected` |
| identification_basis | `eegs_operator_list`, `eegs_name_keyword`, `eegs_ambiguous_name`, `eegs+operator_disclosure`, `eegs+brand_pattern`, `public_announcement` |
| capacity_mw | a single capacity figure stated by the source, MW; empty when only ranges, lower bounds, MVA, racks or floor area are stated |
| capacity_basis | `it` (IT load), `grid` (receiving capacity), `unspecified` |
| capacity_note | phases, ranges and other capacity statements of the source |
| timeline | construction and operation dates as stated by the source |
| eegs_emitter_code | 特定排出者コード of the reporting company (EEGS rows) |
| eegs_industry | industry as reported |
| eegs_co2_t_fy2021, _fy2022, _fy2023 | reported emissions, t-CO2 (empty when not reported that year) |
| lat, lon, coord_precision | representative point; `municipality` (municipal office), `district` (part of a municipality) or `address` |
| possible_duplicate_of | site_id of an earlier EEGS row with the same normalised facility name in the same municipality (reports under a former company name or spelling variant) |
| source_type | `eegs`, `operator_disclosure`, `news_release`, `news`, `government` (';'-separated) |
| source_ref | EEGS facility page, page URLs, or publisher domain or name where no page URL was recorded |

### Reliability

The published build has 184 sites: 147 from EEGS (121 confirmed, 26 suspected) and 37 from
announcements (32 confirmed, 5 suspected).

- Of the 121 confirmed EEGS sites, 67 rest on the operator list and 44 on a data-center keyword in
  the facility name; 10 were raised from suspected by an operator disclosure (one of them by name
  pattern only).
- All 26 suspected EEGS sites are inferred from the facility name only (ambiguous names such as
  ネットワークセンター of telecommunications and IT companies); they may be network buildings or
  offices rather than data centers.
- Type is an operator-level heuristic, not checked site by site: 61 EEGS sites take the type of
  their reporting company, 74 a company-name rule, and 12 the default `telecom_enterprise`. The
  `telecom_enterprise` class mixes large data centers and smaller in-house computer rooms.
- 4 pairs of EEGS rows are flagged in `possible_duplicate_of` and kept.

### Known limitations

- EEGS covers only facilities above the reporting threshold (energy use of 1,500 kL crude-oil
  equivalent per year, roughly 0.5 MW average electricity demand); smaller data centers and edge
  sites are absent, and the register is biased to large sites.
- Reported emissions depend on the electricity procured (renewable contracts lower them); they are
  a lower bound of energy use and do not rank sites by size.
- FY2019-FY2020 are not available in the current EEGS system.
- Announced capacities use different bases (IT load, receiving capacity, campus totals, phases);
  compare only within one `capacity_basis`.
- Announcement facts reflect the state at compilation (July 2026); planned dates change.
- Most coordinates are municipal representative points, not site locations.

## Released data

`data/` holds the derived tables of the build run on 2026-10-19 from the files retrieved on that
day. They can be regenerated with the commands in "Reproducing"; values may differ after operators
revise published files.

| Path | Content |
|---|---|
| `data/stats/substation_year_stats.csv` | substation-year coincident peak, p99, p95, valid hours, zero and negative hours |
| `data/stats/bank_year_stats.csv` | bank-year statistics of each published transformer column |
| `data/capacity/capacity_table.csv` | harmonised transformer capacity tables (as published, after merging split records) |
| `data/headroom/headroom_reconstructed.csv` | join of substation-year statistics with capacity rows; headroom under the two definitions above |
| `data/headroom/join_report.csv`, `unmatched_keys.csv` | join outcomes per operator and fiscal year |
| `data/history/` | TEPCO capacity history 2019-2025 (see the section below) |
| `data/sites/data_center_sites.csv` | data center site register (see the section below) |
| `data/manifest.csv` | retrieval manifest of the files used for the build (see "Sources") |

The hourly long tables are not included because of their size; `pipeline build` writes them to
`build/load_long/`. `stats/column_duplicates.csv`, the Parquet copies and `logs/` are not included.

The capacity tables (`data/capacity/`) and the TEPCO capacity history (`data/history/`) are
structured extractions of figures published by the operators (values as published, in a common
layout). The other tables are computed from the published files.

## Comparing a rebuild with the released data

```
python -m pipeline compare --built build/ --released data/
```

Every CSV table under `data/` is matched with the file of the same relative path under `build/`
(`data/manifest.csv` is not compared). Rows are aligned on each table's key columns (listed in
`pipeline/compare.py`, e.g. operator, fiscal year, substation key and voltages for
`substation_year_stats.csv`); rows sharing a key are paired in sorted order. Two cells are equal
when their text is identical or when both are numbers that differ by at most 1e-6 absolute or
1e-9 relative. For each table the tool prints the rows only in the release (missing), the rows
only in the rebuild (extra), and the numbers of paired rows and cells that differ, with the first
few differences (`--max-show`). Tables written by the build but not released (`column_duplicates`,
`logs/`) are listed and skipped. A released table missing from the rebuild (for example when only
`pipeline build` was run) is listed and skipped; `--strict` counts it as a difference.

Exit status 0 means that every compared table agrees; 1 means that differences were found.
Differences are expected when operators have revised or replaced published files since
2026-10-19: compare the SHA-256 values of the new retrieval's `manifest.csv` with
`data/manifest.csv` to find the files that changed.

## Sources and third-party terms

- **Transmission and distribution operators, disclosure files** (the ten publishers listed under
  "Sources"): the downloaded files are not redistributed; `data/manifest.csv` lists them with URL,
  size and SHA-256. They remain subject to each publisher's terms of use.
- **Transmission and distribution operators, voluntary siting guides** (`guides/README.md`): the
  guide documents and pages are not redistributed; `guides/` records factual items with the URL
  of each guide. They remain subject to each publisher's terms of use; for Chubu only counts per
  voltage and capacity band are published (see `guides/README.md`).
- **EEGS** (温室効果ガス排出量算定・報告・公表制度, Ministry of the Environment): facility-level
  emission reports used for the data center site register; not redistributed; subject to the
  publisher's terms of use.
- **Geospatial Information Authority of Japan, address search**: source of the municipality
  representative points in `sites/municipality_points.csv`; subject to the publisher's terms of
  use.
- **Internet Archive (Wayback Machine)**: archived copies of TEPCO files no longer linked from
  the operator's site (hourly loading zips and the capacity lists of 2019-2025); not
  redistributed; the capture URLs are in `data/manifest.csv` and
  `data/history/tepco_capacity_history_files.csv`.
- **Public announcements** (operator press releases and web pages, municipal and ministry
  documents, news articles) cited in `sites/`: only facts are recorded, with the page URL or the
  publisher.

## Citation and licence

See `CITATION.cff`. Code: MIT (`LICENSE`). Data tables (`data/`, `guides/*.csv`, `sites/*.csv`,
`fetch/tepco_history_snapshots.csv`): CC BY 4.0 (`LICENSE-DATA`).

`tests/fixtures/` holds short excerpts of published source files, used only by the tests. They are
not covered by CC BY 4.0 or MIT; rights remain with the respective publishers.
