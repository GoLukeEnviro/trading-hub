"""Contract test for the SI-v2 ↔ container API reachability path.

Regression guard for the reachability defect found on the target host:

The bot configs set ``api_server.listen_ip_address = 127.0.0.1``. That is the
correct *containment* default, but a container-internal loopback listener is
**unreachable through a published port** — verified empirically: with the
container listening on 127.0.0.1, a host ``curl`` to the published port returns
000; with the container listening on 0.0.0.0, it returns 200.

At the same time the SI-v2 active cycle runs natively on the host, not inside
the compose network, so the previous Docker DNS base URLs
(``trading-freqtrade-<role>-1``) can never resolve there.

Both halves must hold together, and the safety property that matters — the API
is not exposed beyond the host — is preserved by the loopback port mapping,
not by the in-container listener address:

1. every published port is bound to 127.0.0.1 only (never 0.0.0.0), and
2. every freqtrade service that publishes a port sets the in-container listen
   address override, so the published port actually serves.

Removing (2) silently re-breaks SI-v2 telemetry while the container healthcheck
stays green, which is exactly why this is asserted here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ROOT / "docker-compose.hermestrader-dryrun.yml"
REGISTRY = ROOT / "self_improvement_v2" / "config" / "freqtrade_bots.readonly.json"

LISTEN_OVERRIDE = "FREQTRADE__API_SERVER__LISTEN_IP_ADDRESS=0.0.0.0"


@pytest.fixture(scope="module")
def services() -> dict[str, dict[str, object]]:
    with COMPOSE.open() as handle:
        return yaml.safe_load(handle)["services"]


def _published_ports(service: dict[str, object]) -> list[str]:
    return [str(p) for p in (service.get("ports") or [])]


def _has_loopback_publish(service: dict[str, object]) -> bool:
    return any("127.0.0.1" in p for p in _published_ports(service))


def test_services_that_publish_a_port_override_the_listen_address(
    services: dict[str, dict[str, object]],
) -> None:
    """A published port only serves if the container listens beyond loopback."""
    checked = 0
    for name, service in services.items():
        if not _has_loopback_publish(service):
            continue
        checked += 1
        env = [str(e) for e in (service.get("environment") or [])]
        assert LISTEN_OVERRIDE in env, (
            f"{name}: publishes a loopback port but does not set {LISTEN_OVERRIDE}. "
            "The container-internal 127.0.0.1 listener is unreachable through a "
            "published port, so the advertised endpoint would serve nothing."
        )
    assert checked >= 4, f"expected at least 4 port-publishing services, saw {checked}"


def test_published_ports_never_bind_all_host_interfaces(
    services: dict[str, dict[str, object]],
) -> None:
    """Safety: the override must not widen host-side exposure."""
    for name, service in services.items():
        for port in _published_ports(service):
            assert not port.startswith("0.0.0.0"), f"{name}: must not bind 0.0.0.0: {port}"
            assert "127.0.0.1" in port, f"{name}: ports must bind loopback only: {port}"


def test_registry_endpoints_match_published_loopback_ports(
    services: dict[str, dict[str, object]],
) -> None:
    """The SI-v2 registry must name endpoints the compose actually publishes.

    This is the join between the two halves: a registry entry pointing at a
    port no service publishes (or at a Docker DNS name) can never be reached
    from the host-native cycle.
    """
    import json
    from urllib.parse import urlparse

    with REGISTRY.open() as handle:
        registry = json.load(handle)

    published = set()
    for service in services.values():
        for port in _published_ports(service):
            published.add(port.split(":")[-2] if port.count(":") == 2 else port)

    for bot in registry["bots"]:
        parsed = urlparse(bot["base_url"])
        assert parsed.hostname == "127.0.0.1", (
            f"{bot['bot_id']}: host-native SI-v2 cannot resolve Docker DNS names "
            f"({bot['base_url']})"
        )
        assert str(parsed.port) in published or (parsed.port == 8087 and not bot.get("enabled")), (
            f"{bot['bot_id']}: base_url port {parsed.port} is not published by any "
            f"compose service (published: {sorted(published)})"
        )
