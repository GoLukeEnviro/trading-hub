# R5A image provenance and recovery contract — 2026-09-09

Issue: #723 (maintenance child of #699)

## Incident and present classification

Docker panicked on 2026-09-07 19:34:54 UTC with `fatal error: concurrent map iteration and map write`.
After Docker restarted, the five canonical containers remained stopped. The bounded
`r5a_compose_up` action was invoked on 2026-09-09 and Compose recreated all five
containers because their recorded Compose image identities no longer matched the
locally resolved mutable build tags. That action did not build or pull an image.

The recovered fleet is 5/5 running and healthy, with restart count 0, OOMKilled
false, four `dry_run=true` configurations, and preserved named volumes. It remains
`RUNNING_CANDIDATE`; its canonical provenance is unproven. Hermes production remains
0.19.0. No Hermes readiness or cutover was run.

## Read-only forensic result

Previous container image objects are absent from the Docker image store, so their
bit-identical reconstruction or ancestry proof is impossible.

| Workload | Previous image ID | Running candidate image ID |
|---|---|---|
| FreqForge | `sha256:8f8bf1e6b726...` | `sha256:c1318af57f8b6ffb34ae09d86320ec06648a17ac319e2d2d0883d45e4e9cf712` |
| Canary | `sha256:9fe8f1254f97...` | `sha256:246b577e69fcece8bfe2ecf45465d80c0b2df2f6424a620a22e8f719fd8464a0` |
| Regime Hybrid | `sha256:80df56d81ee7...` | `sha256:f9fcdf187897cbdaa09726a597ec52a3803dcdcf7c163ac16aae00878293ba2b` |
| Webserver | `sha256:6eed82ddb8e7...` | `sha256:0f8642bb306254967a538a79635964bd0e8e99f20eeb73d4274b7259b71167ad` |
| Rainbow | `sha256:2dad039f7173...` | `sha256:553dbfc682c9a2bb77711f9d778b549c12a9464a64e8c62a05638087cbc47f5b` |

All four candidate Freqtrade images have identical complete 12-layer RootFS lists.
Their runtime entrypoint hashes equal repository `freqtrade/entrypoint.sh`:
`7e1890ed32c9211f13475853cb5a5c15ac9c44db0f9676f50d5d7d82d48a6880`.
The candidate image metadata declares user `ftuser`; Compose overrides the running
containers to `10000:10000`. The new canonical image contract requires the numeric
identity in both places and therefore does not accept these candidate images.
Mounted configs, strategy directories, and shared code match clean repository commit
`069274c21c90e154cae51618fa2d874c1534ac57`; all four configs remain dry-run.
The pinned upstream base is
`sha256:87aa5c6d65359b34e9d99a0bb260a38c0efe0315253811e6f48c2afe8f278a6a`,
but its local image object is absent, so candidate ancestry cannot be independently
bound to that digest.

The immutable Rainbow checkout is clean at
`6e850c8f8ba1d8a0ad45250f130280e4171c001d`, and its Dockerfile hash matches the
existing source lock (`faa2e3d8c351dc50adc4af21093811587c2f49caaa8827e138fee8c0d0796405`).
The running candidate image does not match the recorded Rainbow image/config
digests and has image user `rainbow`, not `10000:10000`. Classification:
`RAINBOW_PROVENANCE_MISMATCH`.

## Root cause

The prior executor mapped `r5a_compose_up` directly to `docker compose ... up -d`.
It had no canonical image lock, no local tag-to-full-image-ID check, and no recovery
mode distinct from reconciliation. The old and current containers carried the same
Compose configuration hashes, but their Compose image labels differed from the
local tag targets. Compose therefore selected recreate when asked to perform `up`.

## Remediation contract

- Four Freqtrade services share one immutable image tag; Rainbow has a separate
  immutable tag. No canonical `latest` identity exists.
- `ops/hermes/hermestrader-dryrun-images.lock.json` is fail-closed while
  `status=baseline_pending`; it cannot authorize start or deploy until full image
  IDs are attested and status becomes `locked`.
- `r5a_compose_start_existing` verifies the exact existing five-container set,
  container image ID and immutable tag, local tag resolution, image user and
  provenance labels, read-only config mounts, and `dry_run=true`, then invokes only
  `docker compose start`.
- `r5a_compose_up` is now deployment-only. It validates locked local images plus
  the rendered Compose service/tag/config contract, then invokes `up -d --no-build
  --pull never`.
- Ordinary `r5a_compose_build` fails closed. The separate
  `r5a_build_canonical_baseline` ceremony accepts no caller-selected path, image tag,
  or service; it validates clean immutable sources and builds exactly one Freqtrade
  and one Rainbow image with provenance labels.
- The Freqtrade image declares numeric `USER 10000:10000`.

## Deliberate two-step baseline transition

This PR does not bless the running candidate or fabricate missing image IDs. After
merge and green CI, the bounded baseline action builds from the exact merged
trading-hub checkout and immutable Rainbow checkout. A follow-up lock update records
both complete Docker image IDs and the exact trading-hub source commit, changes the
lock to `locked`, and aligns Compose immutable tags. Only then may the five
containers be recreated with named volumes preserved and the full R5A parity matrix
run. Fresh Hermes readiness remains prohibited until provenance and parity pass.

## Safety invariants

No `down -v`, volume prune, Docker prune, DB deletion, credential mutation,
strategy/config mutation, `dry_run=false`, live-trading authority, Hermes restart,
Hermes state migration, or Hermes cutover is part of this remediation PR.

## Controlled post-merge baseline attestation

PR #724 merged as `5bcb50fc81862969180fbc7f154ef719118925af` after Main Gate,
governance consistency, and offline smoke passed. The bounded baseline action then
built two images without touching containers or volumes. Runtime audit request
`h3b-452fe772a398` completed ALLOWED/0 in 38,924 ms.

| Runtime | Immutable tag | Full image/config digest |
|---|---|---|
| Freqtrade shared ×4 | `hermestrader/freqtrade-r5a:r7a-5bcb50fc8186-7ca1e4f9b150` | `sha256:aa4ab78532d996b0d3ac7b034819918e2085495dd1368399705b208d331bd380` |
| Rainbow | `hermestrader/rainbow-r5a:6e850c8f8ba1-faa2e3d8c351` | `sha256:7e2fab4a87790a1aadebed29b2688ec4c45a80ed9763e69f0d3d285093cc5db0` |

Both local RepoDigests equal their full image/config digest. Image users are numeric
`10000:10000`; Freqtrade provenance labels bind the merged source commit, pinned
base digest, Dockerfile hash, and entrypoint hash; Rainbow labels bind the immutable
source commit and Dockerfile hash.

The specialized extension installer exposed a pre-existing completeness defect on
first post-merge installation: it omitted `legacy.py`, so the executor failed its
live import. No fleet process changed. The generic completeness-checked installer
immediately restored a healthy executor from the same merge commit. The follow-up
lock PR adds `legacy.py` and `__main__.py` to the specialized installer and adds a
regression test requiring it to deploy every runtime package module.

## Canonical deployment and parity result

PR #725 merged the complete lock as `cf7cb34a13734cef16cae2333b5f51a5c9314125`.
PR #726 added the bounded post-action health wait and merged as
`d900154e441f5e119e97ebac7edade95404cea77`. All required CI checks passed on
both PRs. The corrected executor extension installed successfully with zero
restarts.

Locked deployment audit `53fb7ab6-c630-4ed0-ade9-072da19811f6` completed
ALLOWED/0 in 19,433 ms. Its only Compose mutation was `up -d --no-build --pull
never`; no image build/pull, `down`, volume removal, or prune occurred.

| Parity criterion | Result |
|---|---|
| exact fleet | PASS — five expected containers; Rebel absent |
| locked image identity | PASS — Freqtrade ×4 `sha256:aa4ab785...`; Rainbow `sha256:7e2fab4a...` |
| runtime health | PASS — 5/5 running and healthy across repeated 30-second cycles |
| restart/OOM | PASS — all RestartCount 0; all OOMKilled false |
| dry-run | PASS — 4/4 Freqtrade configs `dry_run=true` |
| strategies | PASS — FreqForge/Canary `FreqForge_Override`; Regime `RegimeSwitchingHybrid_v7_v04_Integration`; webserver command correct |
| bind mounts | PASS — config, strategy, shared, and Rainbow config binds read-only |
| DB/WAL ownership | PASS — Freqtrade and Rainbow DB/WAL files `10000:10000` |
| Rainbow | PASS — `/health` healthy/read_only; ingest and webhook writes rejected HTTP 405 |
| persistent volumes | PASS — the same eight named volumes remain; original creation timestamps retained |
| live authority | PASS — only dry-run databases/configurations; no live-trading authority introduced |

The fresh Change-C readiness record was created at 2026-09-09 19:00:34 UTC,
not reused from September 1. It reports backup restore, lock, staging, migration
probe, rollback, and trading fleet gates PASS; `CUTOVER_READY=YES` and
`CUTOVER_EXECUTED=NO`. Production remains Hermes Agent 0.19.0, with gateway and
dashboard active and zero restarts.

Final classification: `READY_FOR_HERMES_A2_IMPLEMENTATION`.
