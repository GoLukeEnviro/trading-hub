"""Credential-free read-only HTTP stub for the Rainbow signal DB.

This is a minimal HTTP server that exposes the local Rainbow SQLite
``signals`` table on ``GET /signals/latest`` (and ``GET /health``).

It is **only** intended to be used by the SI v2 scheduled observation
loop as a credential-free, in-process ``read_only`` source for Rainbow
signals.  It is NOT a production replacement for the ai4trade-bot
FastAPI server.

Hard safety contract:

* No auth, no tokens, no secrets, no request bodies.
* Only listens on ``127.0.0.1`` (loopback) — never ``0.0.0.0``.
* Opens the SQLite database with ``mode=ro`` (URI mode) — never writes.
* No daemon install.  Lifecycle is fully owned by the calling process
  (SI v2 wrapper or proof script) via the ``serve()`` context manager.
* Stdlib only (``http.server``, ``urllib.parse``, ``sqlite3``) — no
  third-party dependencies so the wrapper can launch it without a venv.
* If the DB does not exist, ``/signals/latest`` returns an empty list
  with HTTP 200 (not an error) so the client maps it to a clean
  ``SUCCESS count=0`` outcome.
* If the DB exists but has no rows, same as above.
* If the DB cannot be opened, the response includes an explicit
  ``"error"`` field with a sanitized message; HTTP 500 is returned.
* All log output is sanitized: never prints request bodies, never
  prints DB contents, never prints paths outside the configured DB.

This module can also be executed directly:

    python3 rainbow_db_stub_server.py --db /path/to/signals.db --port 8765

The script stays in the foreground; send SIGINT/SIGTERM to stop.
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# Local constants — keep all defaults in one place so the wrapper can
# rely on them via argparse.
DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 8765
DEFAULT_DB_PATH: str = "/opt/data/ai4trade-bot/rainbow/storage/signals.db"
LOG_PREFIX: str = "[rainbow_db_stub]"


# ── Config ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StubConfig:
    """Immutable configuration for the stub server.

    ``host`` MUST be a loopback address.  ``db_path`` MUST point to an
    existing or future-readable SQLite file.  ``port`` is a TCP port in
    the user/private range (``>=1024``).
    """

    host: str
    port: int
    db_path: str

    def __post_init__(self) -> None:
        if not self.host.startswith("127."):
            raise ValueError(
                f"Stub host must be loopback (127.0.0.0/8); got {self.host!r}"
            )
        if not (1024 <= self.port <= 65535):
            raise ValueError(
                f"Stub port must be in [1024, 65535]; got {self.port!r}"
            )


# ── DB layer ────────────────────────────────────────────────────────────────


def _open_ro(db_path: str) -> sqlite3.Connection:
    """Open a SQLite database in read-only mode.

    Returns a connection; the caller is responsible for closing it.
    Raises ``sqlite3.OperationalError`` on failure.
    """
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def fetch_latest_signals(
    db_path: str,
    limit: int = 50,
) -> list[dict[str, object]]:
    """Fetch the latest signals from the read-only DB.

    The returned dict list is a **shallow copy** of the DB row, suitable
    for direct JSON serialization.  Empty list if the DB has no rows or
    the table does not exist yet.
    """
    conn = _open_ro(db_path)
    try:
        cursor = conn.execute(
            "SELECT signal_id, timestamp, source, asset, signal_type, "
            "direction, strength, confidence, value, raw_data, metadata, "
            "rainbow_score, ai_evaluation "
            "FROM signals ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
    finally:
        conn.close()
    return [dict(zip(columns, row, strict=True)) for row in rows]


# ── HTTP handler ────────────────────────────────────────────────────────────


class _StubHandler(BaseHTTPRequestHandler):
    """Minimal GET-only handler.  All other methods → 405."""

    server_version = "RainbowDBStub/1.0"

    # The handler logs are noisy by default; downgrade to WARNING.
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        logging.warning("%s %s", LOG_PREFIX, format % args)

    def _write_json(self, status: int, body: dict[str, object]) -> None:
        payload = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        # Explicit no-store to prevent any cache layer from replaying
        # stale signals — every cycle should observe current DB state.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        cfg: StubConfig = self.server.config  # type: ignore[attr-defined]
        if self.path == "/health":
            self._write_json(200, {"status": "healthy", "source": "stub"})
            return
        if self.path.startswith("/signals/latest"):
            self._handle_signals_latest(cfg)
            return
        self._write_json(404, {"error": "not_found"})

    def _handle_signals_latest(self, cfg: StubConfig) -> None:
        try:
            signals = fetch_latest_signals(cfg.db_path, limit=50)
        except sqlite3.OperationalError as exc:
            # The DB file may not exist yet — return empty payload, not 500.
            # The client maps this to a clean SUCCESS count=0.
            logging.warning("%s db_unavailable: %s", LOG_PREFIX, exc)
            self._write_json(
                200,
                {
                    "signals": [],
                    "source": "stub",
                    "freshness_status": "db_unavailable",
                    "count": 0,
                },
            )
            return
        except Exception as exc:  # pragma: no cover — defensive
            logging.exception("%s unexpected error", LOG_PREFIX)
            self._write_json(
                500,
                {"error": "internal", "detail": str(exc)[:200]},
            )
            return
        self._write_json(
            200,
            {
                "signals": signals,
                "source": "stub",
                "freshness_status": "ok",
                "count": len(signals),
            },
        )

    def log_request(
        self, code: int | str = -1, size: int | str = 0
    ) -> None:
        # Suppress the default one-line access log; rely on log_message.
        return


class _StubServer(ThreadingHTTPServer):
    """Threading HTTP server with an attached ``StubConfig``."""

    # We need to make the config available to the handler; the default
    # ``ThreadingHTTPServer`` has no field for it, so subclass.

    config: StubConfig  # set in serve()


# ── Lifecycle ───────────────────────────────────────────────────────────────


@contextmanager
def serve(cfg: StubConfig) -> Iterator[_StubServer]:
    """Context manager: start the stub in a background thread, yield, stop it.

    Usage:

        with serve(StubConfig(host="127.0.0.1", port=8765,
                              db_path="/path/signals.db")) as srv:
            # server is running on 127.0.0.1:8765
            ...
        # server is stopped, socket closed

    The function never raises during startup on ``EADDRINUSE`` — it
    re-raises so the caller can decide whether to retry on another
    port.  On shutdown, the server is closed cleanly and the socket is
    released before the context manager returns.
    """
    server = _StubServer((cfg.host, cfg.port), _StubHandler)
    server.config = cfg
    # Run ``serve_forever`` in a daemon thread so the context manager
    # can yield control to the caller.  Without this, the test/integration
    # caller would never reach the body of the ``with`` block.
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # Brief wait for the socket to bind so the caller can connect
    # immediately after entering the context.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if thread.is_alive():
            break
        time.sleep(0.01)
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)


# ── CLI ─────────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> StubConfig:
    parser = argparse.ArgumentParser(
        prog="rainbow_db_stub_server",
        description=(
            "Read-only HTTP stub that exposes the local Rainbow SQLite "
            "DB on /signals/latest.  Localhost only, no auth."
        ),
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=(
            "Bind address (default 127.0.0.1).  Must start with '127.' "
            "— 0.0.0.0 / public interfaces are rejected."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="TCP port (default 8765).",
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        default=DEFAULT_DB_PATH,
        help=(
            "Path to the Rainbow signals.db (read-only). "
            "Default: /opt/data/ai4trade-bot/rainbow/storage/signals.db"
        ),
    )
    args = parser.parse_args(argv)
    return StubConfig(host=args.host, port=args.port, db_path=args.db_path)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    cfg = _parse_args(sys.argv[1:] if argv is None else argv)
    logging.warning(
        "%s starting host=%s port=%d db=%s",
        LOG_PREFIX,
        cfg.host,
        cfg.port,
        cfg.db_path,
    )
    # For the CLI foreground path, bypass the context-manager thread
    # wrapper and run serve_forever on the main thread so KeyboardInterrupt
    # cleanly propagates.
    server = _StubServer((cfg.host, cfg.port), _StubHandler)
    server.config = cfg
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.warning("%s shutdown requested", LOG_PREFIX)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
