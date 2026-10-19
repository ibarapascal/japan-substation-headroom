"""Streaming writer for the harmonised hourly long table, one file per operator.

Columns: operator, source_file, substation_raw, substation_key, bank, v1_kv, v2_kv, ts_local,
mw, flag. Parquet (pyarrow) when available, otherwise gzip CSV. Each parsed table is appended as
it is produced, in column chunks, so memory stays bounded by one table.

flag values:
  ok        finite value, > 0
  zero      value == 0
  negative  value < 0 (flow from the secondary to the primary side)
  missing   no value published for the hour (missing-value token or empty cell)
  marked    value published with an asterisk mark (meaning not documented by the publisher)
"""
from __future__ import annotations

import csv
import gzip
import os
from typing import List, Optional

import numpy as np

try:  # optional
    import pyarrow as pa
    import pyarrow.parquet as pq
except Exception:  # pragma: no cover - exercised only without pyarrow
    pa = None
    pq = None

LONG_FIELDS = ["operator", "source_file", "substation_raw", "substation_key", "bank", "v1_kv",
               "v2_kv", "ts_local", "mw", "flag"]
FLAGS = ["ok", "zero", "negative", "missing", "marked"]
CHUNK_ROWS = 1_000_000


def flags_for(values: np.ndarray, marked: Optional[np.ndarray]) -> np.ndarray:
    """int8 codes into FLAGS, same shape as values."""
    f = np.zeros(values.shape, dtype=np.int8)
    with np.errstate(invalid="ignore"):
        f[values == 0] = 1
        f[values < 0] = 2
    f[np.isnan(values)] = 3
    if marked is not None:
        f[marked & ~np.isnan(values)] = 4
    return f


class LongWriter:
    def __init__(self, path_base: str, fmt: str = "auto"):
        if fmt == "auto":
            fmt = "parquet" if pa is not None else "csv"
        if fmt == "parquet" and pa is None:
            raise RuntimeError("pyarrow is not installed; use --format csv")
        self.fmt = fmt
        self.path = path_base + (".parquet" if fmt == "parquet" else ".csv.gz")
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self.rows = 0
        self._pq = None
        self._csv = None
        self._fh = None
        if fmt == "parquet":
            self.schema = pa.schema([
                ("operator", pa.string()), ("source_file", pa.string()),
                ("substation_raw", pa.string()), ("substation_key", pa.string()),
                ("bank", pa.string()), ("v1_kv", pa.string()), ("v2_kv", pa.string()),
                ("ts_local", pa.timestamp("s")), ("mw", pa.float64()), ("flag", pa.string()),
            ])
            self._pq = pq.ParquetWriter(self.path, self.schema, compression="zstd")
        else:
            self._fh = gzip.open(self.path, "wt", newline="", encoding="utf-8")
            self._csv = csv.writer(self._fh)
            self._csv.writerow(LONG_FIELDS)

    def write(self, operator: str, source_file: str, raw: List[str], keys: List[str],
              banks: List[str], v1: List[str], v2: List[str], ts: np.ndarray,
              values: np.ndarray, marked: Optional[np.ndarray]) -> None:
        """values: (n_ts, n_cols). Rows are written column by column (one series after another)."""
        n_ts, n_cols = values.shape
        if n_ts == 0 or n_cols == 0:
            return
        flags = flags_for(values, marked)
        per_chunk = max(1, CHUNK_ROWS // n_ts)
        for c0 in range(0, n_cols, per_chunk):
            c1 = min(n_cols, c0 + per_chunk)
            m = c1 - c0
            col_idx = np.repeat(np.arange(c0, c1), n_ts)
            mw = values[:, c0:c1].T.reshape(-1)
            fl = flags[:, c0:c1].T.reshape(-1)
            if self.fmt == "parquet":
                def dict_col(vals: List[str]) -> "pa.Array":
                    local = pa.array(vals[c0:c1], type=pa.string())
                    idx = pa.array((col_idx - c0).astype(np.int32))
                    return pa.DictionaryArray.from_arrays(idx, local).cast(pa.string())
                n = m * n_ts
                table = pa.table({
                    "operator": pa.array([operator] * n, type=pa.string()),
                    "source_file": pa.array([source_file] * n, type=pa.string()),
                    "substation_raw": dict_col(raw),
                    "substation_key": dict_col(keys),
                    "bank": dict_col(banks),
                    "v1_kv": dict_col(v1),
                    "v2_kv": dict_col(v2),
                    "ts_local": pa.array(np.tile(ts, m), type=pa.timestamp("s")),
                    "mw": pa.array(mw, type=pa.float64(), from_pandas=True),
                    "flag": pa.DictionaryArray.from_arrays(
                        pa.array(fl), pa.array(FLAGS)).cast(pa.string()),
                }, schema=self.schema)
                self._pq.write_table(table)
            else:
                ts_txt = np.datetime_as_string(ts, unit="m")
                for k in range(m):
                    j = c0 + k
                    for i in range(n_ts):
                        v = values[i, j]
                        self._csv.writerow([operator, source_file, raw[j], keys[j], banks[j],
                                            v1[j], v2[j], ts_txt[i].replace("T", " "),
                                            "" if np.isnan(v) else repr(float(v)),
                                            FLAGS[flags[i, j]]])
            self.rows += m * n_ts

    def close(self) -> None:
        if self._pq is not None:
            self._pq.close()
        if self._fh is not None:
            self._fh.close()
