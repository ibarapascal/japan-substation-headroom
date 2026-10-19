# guides/ — Voluntary demand-side siting guides and grid-disclosure inventory (Japan, 10 TSOs)

Retrieval date for all sources: 2026-10-19 (JST), unless a row states an archived capture (Internet Archive Wayback Machine) or an earlier retrieval (2026-07-10).

## Files

| File | Rows | Unit of observation |
|---|---|---|
| `siting_guides_sites.csv` | 472 | one site (substation, transmission-line section, area, municipality or candidate industrial site) in one edition of one TSO's voluntary demand-side siting guide (nine TSOs; Chubu is in `chubu_band_counts.csv`) |
| `chubu_band_counts.csv` | 8 | Chubu EPCO PG only: one source view × voltage × capacity band, with the number of transmission-line entries |
| `siting_guides_coding.csv` | 10 | one TSO (current guide, as of retrieval) |
| `disclosure_inventory.csv` | 10 | one TSO (mandatory grid-information disclosure under METI's 系統情報の公表の考え方) |

Rows per operator and edition in `siting_guides_sites.csv`:

| operator | edition_date | rows |
|---|---|---|
| TEPCO PG | 2025-10-10 / 2025-12-17 / 2026-02-16 / 2026-08-31 | 12 / 7 / 7 / 5 |
| Kansai T&D | 2024-04 / 2025-06 / 2026-05 / 2026-08 | 54 / 56 / 56 / 41 (2026-05 and 2026-08 include 13 rows each from the 77 kV table) |
| Tohoku EPCO NW | 2026-02 | 15 |
| Hokuriku EPCO T&D | undated web page | 27 |
| Chugoku EPCO NW | 2025-11 | 40 |
| Kyushu EPCO T&D | 2026-03 | 56 |
| Hokkaido EPCO NW | 2025-12 | 29 |
| Chubu EPCO PG | 2026-05 | 0 (511 line entries, published as 8 count rows in `chubu_band_counts.csv`) |
| Shikoku EPCO T&D | 2026-05-27 / 2026-07-22 / 2026-10-15 | 5 / 17 / 17 |
| Okinawa EPCO | 2025-03 | 28 |

## Sources

| Operator | Guide (Japanese title) | URL |
|---|---|---|
| Hokkaido EPCO NW | でんきとつながる地図（HELLO NEW HOKKAIDO MAP） | https://hello.hepco.co.jp/map/ (data: `/wp-content/uploads/geojson/generated/lines_all.json`, manifest version 20260917_114503) |
| Tohoku EPCO NW | ウェルカムゾーン（大規模需要への供給候補地点）に関するご案内 | https://nw.tohoku-epco.co.jp/danchi/pdf/energy_resource.pdf |
| TEPCO PG | 大規模供給ポテンシャルマップ | https://www.tepco.co.jp/pg/consignment/zonemap/pdf/potentialmap.pdf |
| Chubu EPCO PG | 中部地方のウェルカムゾーンマップ（Tableau Public） | https://powergrid.chuden.co.jp/youchi/ (CSV export of views `_17743472567510/sheet0` and `_17743166838720/sheet3`) |
| Hokuriku EPCO T&D | 北陸地域の企業用地およびウェルカムゾーン | https://www.rikuden.co.jp/nw_youchi/ |
| Kansai T&D | 供給可能エリアマップ | https://www.kansai-td.co.jp/consignment/welcome-zone-map/pdf/area_map.pdf |
| Chugoku EPCO NW | ウェルカムゾーンマップ（供給余力マップ） | https://www.energia.co.jp/nw/service/supply/zonemap/yoryoku/ |
| Shikoku EPCO T&D | ウェルカムゾーンマップ | https://www.yonden.co.jp/nw/industrial_area/index.html |
| Kyushu EPCO T&D | ウェルカムゾーンマップ 供給余力マップ（系統用変電所） | https://www.kyuden.co.jp/td/application/firm-location/capacity-map.html |
| Okinawa EPCO | ウェルカムゾーンマップ（主な工業用地における電力供給工事について／電力供給余力マップ） | https://www.okiden.co.jp/business-support/service/welcome_zonemap/index.html |

Earlier editions were taken from Internet Archive captures of the same URLs (capture dates are given in `notes`). The aggregator page of the Transmission and Distribution Grid Council (https://www.tdgc.jp/areainfo/zonemap/) lists the same ten entry points.

Disclosure inventory sources are the TSO pages in `disclosure_inventory.entry_url`.

## `siting_guides_sites.csv` — fields and coding rules

| Field | Rule |
|---|---|
| `operator` | TSO short English name. |
| `guide_title_ja` / `guide_title_en` | Title as printed by the TSO; English is a descriptive translation. |
| `edition_date` | As-of date printed in the document (作成日 or 時点), at the finest resolution printed (YYYY-MM or YYYY-MM-DD). Where a page carries no date, the value is `undated web page (retrieved 2026-10-19)`. PDF creation dates and capture dates are in `notes`. |
| `url` | Stable URL of the guide (the same URL serves successive editions). |
| `site_name_raw` | Site name as printed (substation 変電所, line 線, area, municipality or letter-coded candidate site). |
| `municipality`, `prefecture` | Parsed from the printed address when one is given; left blank otherwise (Hokkaido, Hokuriku and Kyushu rows, and the Kansai 77 kV table, print no address). Hokkaido rows carry a coordinate centroid in `notes`. |
| `voltage_kv` | Supply or equipment voltage as printed. Kansai detail pages are coded 77 (the guide states a standard voltage of 70 kV for contracts ≥10 MW). |
| `capacity_band_or_mw` | Capacity wording as printed (Japanese), e.g. `50MW以上`, `供給余力 173MW`, `10〜20万kWの空容量あり`. Blank where the guide gives no per-site value. |
| `capacity_mw_low`, `capacity_mw_high` | Numeric bounds in MW derived from `capacity_band_or_mw`. Single stated values fill both bounds. Open-ended thresholds (`…以上`, `…を超える`) fill only `low`. `…未満` without a lower bound fills only `high`. 万kW is converted at 1万kW = 10 MW. |
| `lead_time_note` | Lead time as stated by the guide, paraphrased in English. |
| `listed_since` | Earliest edition in which the site was observed, with the evidence type. `(earliest edition seen)` means the site is present in the oldest edition examined, so the true first listing may be earlier. Blank where only one edition was examined. |
| `notes` | `site_type=…`, location text, source capture, reading method, and site-specific caveats. |

Reading methods by operator:

- Text extraction (`pdftotext -layout`): TEPCO, Tohoku, Kansai, Okinawa municipality names, Chugoku station list.
- Public data files: Hokkaido GeoJSON (`N_OrdCur` coded values, mapped to display bands with the site's own JavaScript function `getRankOfMv`); Chubu Tableau CSV export (one entry per line name × voltage × band, aggregated from geometry rows; published here as counts only, see `chubu_band_counts.csv`).
- Colour reading: Chugoku station PDFs (overlay colour of the rendered page, checked visually); Kyushu regional map images (marker colour, visual); Okinawa municipality map (fill colour, visual). These rows state the method in `notes`.
- HTML text: Hokuriku facility pages; Shikoku candidate-site tables.

Judgement cases:

- Hokkaido: the public GeoJSON gives `N_OrdCur` values 100, 300 and 500 for 29 bulk-line sections; all 66/33/22 kV sections carry 0 and are displayed as "inquiry required" in the map. Rows record the displayed band and the coded value.
- Kansai 2025-06 edition includes four Fukui areas named by town, not by substation; they are coded `site_type=area`.
- Kansai entries `供給余力：30MW未満` (Kameoka, Sonobe areas) are coded high=30, low blank.
- Kansai 77 kV table (`マップ余力以上の大規模開発について`): `ー` means no 77 kV facilities at present; bounds left blank.
- Shikoku: margin bands are colour-coded for every substation and line on the schematic; per-site rows list the letter-coded candidate industrial sites only, with capacity blank.
- Chugoku station PDF with three stations (水島火力／水島／玉島) and two-station PDFs were coded per station from the labelled circles.

## `chubu_band_counts.csv` — fields

Chubu EPCO PG asks users to contact it before secondary use of its map data. Until permission for reuse is obtained, the line-level entries (line names, line numbers, coordinates and geometry counts) are not published; this file gives the number of entries per source view, voltage and capacity band.

| Field | Rule |
|---|---|
| `operator`, `guide_title_ja`, `guide_title_en`, `edition_date`, `url`, `listed_since` | As in `siting_guides_sites.csv`. |
| `source_view` | Tableau Public view whose CSV export was read. |
| `voltage_kv` | Line voltage as published. |
| `capacity_band_or_mw`, `capacity_mw_low`, `capacity_mw_high` | Band wording as published and its bounds in MW. |
| `n_line_entries` | Number of entries (transmission line name × voltage × band) in the view with this voltage and band. |
| `notes` | Aggregation statement, workbook publication date, and statements printed in the view's notes sheet. |

## `siting_guides_coding.csv` — fields and coding rules

| Field | Rule |
|---|---|
| `has_voluntary_guide` | `yes` if the TSO publishes a demand-side (load connection) siting guide or map with per-site or per-area capacity information. |
| `guide_format` | Delivery format(s) as observed. |
| `numeric_depth` | `exact MW`: per-site values stated at 1 MW resolution or finer, not restricted to a fixed set of tiers. `band`: ranges, open-ended thresholds, or values drawn from a small fixed tier set (e.g. 5/10/30万kW; 50/200/300 MW). `none`: no capacity figure. |
| `n_sites` | Count in the current edition, with the unit of observation. |
| `update_frequency` | As stated by the TSO; otherwise `not stated` plus the observed edition dates. |
| `disclaimers` | One representative caveat of the guide, paraphrased in English (the original wording is in the guide at `url`). |
| `edition_dates_seen` | Editions observed directly or via Internet Archive. |

## `disclosure_inventory.csv` — fields and coding rules

| Field | Rule |
|---|---|
| `transformer_table_published` | Whether a substation/transformer table of the 予想潮流等一覧表 type is published, and in which formats. |
| `transformer_table_fields` | Fields present: `units` (台数), `rated` (設備容量), `operating` (運用容量値), `forecast_flow` (予想潮流), `available` (空容量, own equipment and upstream-considered). |
| `available_capacity_direction_note` | English paraphrase of the TSO's statement on the direction (generation / reverse flow, or load / forward flow) to which the published available capacity refers, with where it is printed; where none was found on the entry page, a note saying so and naming related columns of the table. |
| `hourly_flow_files` | Whether hourly measured flow files (地点別需要・系統潮流実績) are published. |
| `hourly_flow_granularity` | System level (kikan = bulk system; local = local system) and equipment type (lines, transformers, distribution transformers). |
| `hourly_flow_latest_fy` / `hourly_flow_earliest_fy_online` | Fiscal years (April–March) available on the current page. |
| `forecast_table_update_stamp` | Update date printed in the forecast CSV or page. |
| `update_frequency` | As stated, or inferred from file stamps (marked `about`). |

## Terms of use of sources

Several guides carry notices prohibiting reproduction (e.g. the TEPCO, Kansai and Chugoku PDFs), and Chubu asks users to contact it before secondary use of its map data. The files here record factual items (names, places, voltages, stated capacities, dates) extracted from those sources, with URLs for verification; sentences of the sources are paraphrased in English rather than quoted. Chubu is published as counts only (see `chubu_band_counts.csv`).

These CSV files are coded by hand from the sources listed above; no script in this repository generates them.
