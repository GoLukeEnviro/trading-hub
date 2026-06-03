# Trading Dashboard Surface Audit — 2026-06-03

## Purpose
This note records the current state of `dashboard.py` after the recent dashboard consolidation. The dashboard is a read-only, server-side rendered Flask app; it should stay compact and prioritise high-signal operational data over decorative or redundant widgets.

## Current surface
- File: `/home/hermes/projects/trading/dashboard.py`
- Start command: `python3 dashboard.py`
- Default port: `5000`
- Rendering model: Flask + `render_template_string`, with fresh reads on every request and no client cache or websocket layer.

The main panels currently cover:
- Header with last render timestamp
- Fleet KPI row
- Current AI signal card from `ai-hedge-fund-crypto`
- Bot table for the four dry-run bots
- System status with container list, observation-report check, and a compact RiskGuard line

## Important data sources
- Bot SQLite files under `/freqtrade/user_data/`
- Hermes signal JSON under `/app/output/latest/hermes_signal.json`
- Observation report JSON under `/app/output/latest/observation_report.json`
- Container inventory via `docker ps`
- Read-only container file access via `docker exec` when the dashboard container cannot mount paths directly

## Design notes
- Keep the surface dark, calm, and compact.
- Prefer consistent card sizing and table widths over dense, mixed-density blocks.
- The dashboard is an operator view, not an analysis notebook; only panels that add real operational value should stay on the main surface.
- If a new panel does not clearly improve operator awareness, it belongs in docs or a separate audit note instead of the primary dashboard.

## Failure handling
- Missing files, invalid JSON, empty DBs, and stopped containers should render as `N/A`, `Offline`, `idle`, or `problem`.
- No tracebacks should reach the browser; the dashboard should degrade gracefully.
- Stale shadow logs and absent observation reports should be shown explicitly rather than hidden.

## Related docs
- `../../README.md`
- `../README.md`
- `trading-dashboard-external-access-20260602.md`
