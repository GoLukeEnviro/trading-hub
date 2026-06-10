"""Test-only stub server for the ai4trade REST API boundary.

Provides a lightweight HTTP server that mimics a future ai4trade-bot
Rainbow API endpoint. Binds to 127.0.0.1:0 (random port) and supports
deterministic data seeding.

HARD SAFETY:
  - Binds ONLY to 127.0.0.1 (localhost)
  - Test-only — no production entry point
  - No ai4trade-bot imports or source copying
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

from si_v2.integrations.ai4trade.rest_models import (
    HealthResponse,
    OutcomeResponse,
    RiskGateRequest,
    RiskGateResponse,
    SignalResponse,
)

HEALTH_DATA = HealthResponse(status="ok", version="0.1.0", signal_count=42)


class _StubRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the stub server."""

    # Shared state set by the server instance
    signals: dict[str, SignalResponse]
    signals_list: list[SignalResponse]
    outcomes: dict[str, OutcomeResponse]

    def log_request(self, code: int | str | None = None, size: int | str | None = None) -> None:
        pass  # Suppress output during tests

    # noinspection PyPep8Naming
    def do_GET(self) -> None:
        parsed = self.path.split("?")
        path = parsed[0]
        query = parsed[1] if len(parsed) > 1 else ""

        if path == "/health":
            self._send_json(200, HEALTH_DATA.model_dump(mode="json"))
        elif path == "/signals/latest":
            asset = self._parse_query_param(query, "asset")
            if not asset:
                self._send_json(400, {"error": "Missing asset query parameter", "detail": None})
                return
            matching = [s for s in self.signals_list if s.asset == asset]
            self._send_json(
                200,
                [s.model_dump(mode="json") for s in (matching or [_default_signal(asset)])],
            )
        elif path.startswith("/signals/"):
            signal_id = path[len("/signals/") :]
            signal = self.signals.get(signal_id)
            if signal is not None:
                self._send_json(200, signal.model_dump(mode="json"))
            else:
                self._send_json(404, {"error": "Signal not found", "detail": f"signal_id={signal_id}"})
        elif path.startswith("/outcomes/"):
            signal_id = path[len("/outcomes/") :]
            outcome = self.outcomes.get(signal_id)
            if outcome is not None:
                self._send_json(200, outcome.model_dump(mode="json"))
            else:
                self._send_json(404, {"error": "Outcome not found", "detail": f"signal_id={signal_id}"})
        else:
            self._send_json(404, {"error": "Not found", "detail": f"path={path}"})

    # noinspection PyPep8Naming
    def do_POST(self) -> None:
        if self.path == "/risk/evaluate":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(400, {"error": "Invalid JSON", "detail": None})
                return
            try:
                req = RiskGateRequest(**data)
            except Exception as exc:
                self._send_json(400, {"error": "Invalid request", "detail": str(exc)})
                return
            passed = req.signal.confidence >= 0.3 and req.signal.risk_score < 0.7 and req.signal.dry_run_only
            resp = RiskGateResponse(
                passed=passed,
                reason="passed" if passed else "risk gate rejected signal",
            )
            self._send_json(200, resp.model_dump(mode="json"))
        else:
            self._send_json(404, {"error": "Not found", "detail": f"path={self.path}"})

    def _send_json(self, status: int, data: object) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @staticmethod
    def _parse_query_param(query: str, name: str) -> str | None:
        for part in query.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                if k == name:
                    return v
        return None


def _default_signal(asset: str) -> SignalResponse:
    from datetime import UTC

    return SignalResponse(
        asset=asset,
        signal_id="default-hold",
        direction="hold",
        confidence=0.5,
        risk_score=0.0,
        source="stub",
        reason="no signal from upstream",
        created_at=datetime.now(UTC),
        dry_run_only=True,
        can_execute=False,
    )


class Ai4tradeStubServer:
    """Lightweight stub HTTP server for the ai4trade REST API.

    Binds to 127.0.0.1 on a random port. Supports context manager usage
    for clean shutdown. Deterministic data can be seeded via constructor.

    Usage:
        with Ai4tradeStubServer() as server:
            url = f"http://127.0.0.1:{server.port}"
            # ... make requests ...
    """

    def __init__(self) -> None:
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port: int = 0

    @property
    def port(self) -> int:
        """The port the server is bound to (0 if not started)."""
        return self._port

    @property
    def base_url(self) -> str:
        """The base URL for the running server."""
        return f"http://127.0.0.1:{self._port}"

    def seed_signals(self, signals: list[SignalResponse]) -> None:
        """Seed deterministic signal data into the handler."""
        _StubRequestHandler.signals = {s.signal_id: s for s in signals}
        _StubRequestHandler.signals_list = list(signals)

    def seed_outcomes(self, outcomes: list[OutcomeResponse]) -> None:
        """Seed deterministic outcome data into the handler."""
        _StubRequestHandler.outcomes = {o.signal_id: o for o in outcomes}

    def start(self) -> None:
        """Start the server on 127.0.0.1:0 (random port)."""
        # Initialize handler state before any requests arrive
        _StubRequestHandler.signals = {}
        _StubRequestHandler.signals_list = []
        _StubRequestHandler.outcomes = {}

        # Seed default test data
        now = datetime.now(UTC)
        self.seed_signals(
            [
                SignalResponse(
                    asset="BTC/USDT",
                    signal_id="sig-001",
                    direction="buy",
                    confidence=0.75,
                    risk_score=0.2,
                    source="rainbow",
                    reason="Strong momentum signal",
                    created_at=now,
                    dry_run_only=True,
                    can_execute=False,
                ),
                SignalResponse(
                    asset="ETH/USDT",
                    signal_id="sig-002",
                    direction="sell",
                    confidence=0.6,
                    risk_score=0.4,
                    source="rainbow",
                    reason="Overbought condition",
                    created_at=now,
                    dry_run_only=True,
                    can_execute=False,
                ),
            ]
        )
        self.seed_outcomes(
            [
                OutcomeResponse(
                    signal_id="sig-001",
                    asset="BTC/USDT",
                    direction="buy",
                    outcome_label="win",
                    outcome_score=0.8,
                    emitted_at=now,
                    evaluated_at=now,
                    entry_price=50000.0,
                    outcome_price=52000.0,
                    price_change_pct=4.0,
                    reason="profitable",
                ),
            ]
        )

        # Bind to a random port on 127.0.0.1
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        self._port = sock.getsockname()[1]
        sock.close()

        self._server = HTTPServer(("127.0.0.1", self._port), _StubRequestHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the server gracefully."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    @contextmanager
    def running(self) -> Generator[Ai4tradeStubServer, None, None]:
        """Context manager that starts the server and stops it on exit."""
        self.start()
        try:
            yield self
        finally:
            self.stop()

    def __enter__(self) -> Ai4tradeStubServer:
        self.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()


__all__ = ["Ai4tradeStubServer"]
