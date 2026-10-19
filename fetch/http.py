"""Polite HTTP client: browser User-Agent, global minimum interval between requests, retries.

Standard library only so the downloader runs on a bare Python 3.9+.
"""
from __future__ import annotations

import hashlib
import os
import time
import urllib.error
import urllib.request
from typing import Optional, Tuple

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
MIN_INTERVAL_S = 2.0
_last_request = [0.0]


def _wait_turn(min_interval: float) -> None:
    gap = time.monotonic() - _last_request[0]
    if gap < min_interval:
        time.sleep(min_interval - gap)
    _last_request[0] = time.monotonic()


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en;q=0.8",
        },
    )


def get_bytes(url: str, retries: int = 3, timeout: int = 120,
              min_interval: float = MIN_INTERVAL_S) -> Tuple[int, bytes, str]:
    """Return (http_status, body, final_url). Raises the last error after retries."""
    err: Optional[Exception] = None
    for attempt in range(retries):
        _wait_turn(min_interval)
        try:
            with urllib.request.urlopen(_request(url), timeout=timeout) as r:
                return r.status, r.read(), r.geturl()
        except urllib.error.HTTPError as e:
            if e.code in (404, 410):
                return e.code, b"", url
            err = e
        except Exception as e:  # network errors, timeouts
            err = e
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} attempts: {url}: {err}")


def download_to(url: str, dest: str, retries: int = 3, timeout: int = 600,
                min_interval: float = MIN_INTERVAL_S) -> Tuple[int, int, str]:
    """Stream url to dest atomically. Return (http_status, bytes, sha256). Non-200 leaves no file."""
    err: Optional[Exception] = None
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    for attempt in range(retries):
        _wait_turn(min_interval)
        try:
            with urllib.request.urlopen(_request(url), timeout=timeout) as r:
                h = hashlib.sha256()
                n = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        h.update(chunk)
                        n += len(chunk)
                os.replace(tmp, dest)
                return r.status, n, h.hexdigest()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return e.code, 0, ""
            err = e
        except Exception as e:
            err = e
        if os.path.exists(tmp):
            os.remove(tmp)
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"download failed after {retries} attempts: {url}: {err}")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
