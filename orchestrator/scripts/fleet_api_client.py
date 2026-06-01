#!/usr/bin/env python3
"""
fleet_api_client.py — Shared REST client for Freqtrade bot APIs.

Provides retry logic with exponential backoff for 429/5xx responses,
Retry-After header support, and jitter to prevent thundering herd.

Usage:
    from fleet_api_client import freqtrade_api_get, INTER_BOT_DELAY

    result = freqtrade_api_get("127.0.0.1", 8086, "/api/v1/ping")
"""

from __future__ import annotations

import random
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.2
MAX_BACKOFF_SECONDS = 10.0
INTER_BOT_DELAY = 0.3
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}
DEFAULT_TIMEOUT = 10


def _log(msg: str) -> None:
    print(f"[fleet_api] {msg}", file=sys.stderr)


def api_call_with_retry(
    url: str,
    *,
    method: str = "GET",
    headers: dict | None = None,
    data: bytes | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = MAX_RETRIES,
    base_backoff: float = BASE_BACKOFF_SECONDS,
) -> tuple[int | None, str | None]:
    """Make an HTTP request with exponential backoff retry on 429/5xx.

    Returns (status_code, response_text) or (None, None) on total failure.
    On 429, respects Retry-After header if present.
    """
    for attempt in range(max_retries):
        try:
            req = Request(url, data=data, headers=headers or {}, method=method)
            resp = urlopen(req, timeout=timeout)
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, body

        except HTTPError as e:
            if e.code in RETRYABLE_STATUS_CODES:
                if attempt < max_retries - 1:
                    # Respect Retry-After on 429
                    delay = base_backoff * (2 ** attempt) + random.uniform(0, 0.5)
                    if e.code == 429:
                        retry_after = e.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = max(float(retry_after), delay)
                            except ValueError:
                                pass
                    delay = min(delay, MAX_BACKOFF_SECONDS)
                    _log(f"{url}: {e.code}, retry {attempt + 1}/{max_retries} in {delay:.1f}s")
                    time.sleep(delay)
                    continue
            # Non-retryable or final attempt
            body = None
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            return e.code, body

        except (URLError, OSError, TimeoutError) as e:
            # Connection refused / no route — not a rate-limit issue, don't retry
            return None, None

    return None, None


def freqtrade_api_get(
    host: str,
    port: int,
    endpoint: str,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = MAX_RETRIES,
) -> str | None:
    """GET request to a Freqtrade bot API with retry.

    Returns response text on success, None on failure.
    """
    url = f"http://{host}:{port}{endpoint}"
    status, body = api_call_with_retry(url, timeout=timeout, max_retries=max_retries)
    if status == 200 and body is not None:
        return body
    return None
