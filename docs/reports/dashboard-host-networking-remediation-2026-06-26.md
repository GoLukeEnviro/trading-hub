# Dashboard Host Networking Remediation — 2026-06-26

## Status: GREEN

**Operation Level:** L1 (targeted runtime restart)

**Timestamp:** 2026-06-26T05:12:00Z

**Repo:** `main` @ `2df12cc` (origin/main in sync)

**Predecessor:** `docs/reports/dashboard-health-diagnostic-2026-06-26.md` (YELLOW / PORT_BIND_MISMATCH)

---

## Summary

Dashboard host port reachability was restored via a targeted `docker compose restart trading-dashboard`. The container was already healthy inside, but the host-level Docker port forwarding for `127.0.0.1:5000` was not active. After restart, the DNAT rule was recreated and the host serves HTTP 200.

---

## Initial Symptom

Host `127.0.0.1:5000` returned **connection refused** at ~04:02 UTC on 2026-06-26.

Evidence from predecessor diagnostic:
- Container-internal Flask: HTTP 200 (healthy)
- Host `/proc/net/tcp`: port 5000 (hex 0x1388) not found
- iptables DOCKER chain: no rule for port 5000
- `docker-proxy` binary: not found in diagnostic environment

Classification: `PORT_BIND_MISMATCH`

---

## Container-Internal Health (pre-fix)

| Check | Result |
|---|---|
| Flask process | Running (Werkzeug 3.1.8, Python 3.13.13) |
| Listening on `0.0.0.0:5000` | Yes |
| Listening on `127.0.0.1:5000` | Yes |
| Listening on `172.26.0.14:5000` | Yes (hermes-net) |
| HTTP GET `http://127.0.0.1:5000/` | 200 OK, 13740 bytes |

Container was healthy throughout. No crashes, no errors, no restarts needed internally.

---

## Action Taken

**Targeted restart of `trading-dashboard` only.**

```bash
docker compose restart trading-dashboard
```

- Scope: single service, no global stack impact
- No compose file edits
- No daemon restart
- No network changes
- No config mutations

---

## Post-Restart Verification (05:01-05:12 UTC)

| Check | Pre-Restart | Post-Restart |
|---|---|---|
| Container status | Up 2 weeks | Up (restarted 05:01) |
| Host `127.0.0.1:5000` | Connection refused | **HTTP 200** |
| Host Tailscale `100.65.117.122:5000` | — | 400 (expected, no virtual host) |
| `/proc/net/tcp` port 5000 | Not found | **Found** (3 entries) |
| iptables DNAT rule | Missing | **Present**: `127.0.0.1:5000 -> 172.26.0.14:5000` |
| nftables DOCKER chain | Missing | **Present** with ACCEPT rule |
| Container-internal HTTP | 200 OK | 200 OK |
| `ss -ltnp` on port 5000 | No listener | dockerd + Tailscale listening |

---

## Docker Networking Configuration

### daemon.json

```json
{
  "icc": false,
  "userland-proxy": false,
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

With `userland-proxy: false`, Docker uses iptables/nftables DNAT for port forwarding instead of the docker-proxy userland process. This is the expected and correct configuration.

### Port Mapping (compose)

```yaml
ports:
  - mode: ingress
    host_ip: 127.0.0.1
    target: 5000
    published: "5000"
    protocol: tcp
```

### Active iptables DNAT Rule

```
-A DOCKER -d 127.0.0.1/32 -p tcp -m tcp --dport 5000 -j DNAT --to-destination 172.26.0.14:5000
```

### nftables Filter Chain

```
ip daddr 172.26.0.14 iifname != "br-29cdf9b8814c" oifname "br-29cdf9b8814c" tcp dport 5000 counter packets 0 bytes 0 accept
```

### Tailscale Listener

Tailscale binds to `100.65.117.122:5000` and `[fd7a:115c:a1e0::5a34:757a]:5000`. This is independent of Docker's `127.0.0.1:5000` binding and does not conflict.

---

## Root Cause Hypothesis

The Docker DNAT rule for port 5000 was lost due to transient Docker networking drift. Probable triggers:

1. Docker daemon or network namespace event removed the iptables/nftables rule
2. Container remained running (2+ weeks uptime) but the host forwarding path was stale
3. `docker compose restart` caused Docker to re-evaluate the port mapping and recreate the DNAT rule
4. Verification delay between restart and final confirmation explained the initial "did not fix" observation

The dashboard Flask process itself was never unhealthy — only the host-level forwarding was broken.

---

## SI-v2 Impact

**None.**

- SI-v2 loop: GREEN (scheduler, 4 bots, ShadowProposals)
- Dashboard is observability-only — not on any critical path
- No trading configs, strategies, signals, or cron jobs were touched
- Mutation counters remain 0

---

## Forbidden Changes — Compliance

| Constraint | Status |
|---|---|
| No SI-v2 runtime changes | Complied |
| No Freqtrade bot changes | Complied |
| No trading config changes | Complied |
| No strategy changes | Complied |
| No cron/guardian changes | Complied |
| No secrets exposed | Complied |
| No .env changes | Complied |
| No docker-compose.yml edits | Complied |
| No Docker daemon restart | Complied |
| No live trading activation | Complied |
| No ShadowProposal application | Complied |
| No global docker compose restart | Complied |
| No docker system prune | Complied |

---

## Runtime Mutations Performed

| Action | Scope | Justification |
|---|---|---|
| `docker compose restart trading-dashboard` | Single service | Restore host port forwarding |

No other mutations.

---

## Final Dashboard Status

| Metric | Value |
|---|---|
| Host HTTP `127.0.0.1:5000` | **200 OK** |
| Response size | 13740 bytes |
| Server | Werkzeug/3.1.8 Python/3.13.13 |
| Container state | Running |
| Container uptime since restart | ~11 minutes |
| Host port binding | Active (iptables DNAT) |

---

## Recommendations

### Keep as-is

- `userland-proxy: false` is correct for this setup. DNAT/iptables is the expected forwarding path.
- No Docker daemon restart required.

### Optional future improvements (not implemented now)

1. **Dashboard host-port health check**: Add a periodic verification that `curl http://127.0.0.1:5000/` returns HTTP 200, with alerting on failure. Could be integrated into the existing `container_watchdog.sh` or `trading-guardian`. Not urgent — the issue was transient.

2. **DNAT rule monitoring**: Periodic check that `iptables -t nat -S DOCKER | grep 5000` returns a rule. Would catch future Docker networking drift early.

3. **Compose depends_on review**: Dashboard depends on `docker-proxy` service, but with `userland-proxy: false`, the docker-proxy process is not used for port forwarding. The dependency may be for Docker API access (DOCKER_HOST=tcp://docker-proxy:2375) rather than port forwarding. Worth verifying but not blocking.

---

## Verification Command

To confirm dashboard reachability at any time:

```bash
curl -sS -o /dev/null -w "dashboard_host=%{http_code}\n" --max-time 5 http://127.0.0.1:5000/
```

Expected: `dashboard_host=200`

---

## Files Changed

None. This is a documentation-only record of a runtime remediation.

---

## Safety Confirmation

- Only targeted dashboard service was restarted
- No SI-v2 loop services affected
- No Freqtrade bots affected
- No configs, strategies, secrets, or cron jobs touched
- No compose file edits
- Host HTTP 200 confirmed after remediation
