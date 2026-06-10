# Phase M.2 — Command Allowlist

## Phase M2-1: Repository Context

| ID | Command | Timeout | Purpose |
|---|---|---|---|
| A-01 | `pwd` | 5s | Working directory |
| A-02 | `git branch --show-current` | 5s | Branch verification |
| A-03 | `git rev-parse HEAD` | 5s | HEAD verification |
| A-04 | `git status --short --untracked-files=all` | 5s | Tree cleanliness |

## Phase M2-2: Container Discovery

| ID | Command | Timeout | Purpose |
|---|---|---|---|
| B-01 | `docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'` | 10s | List running containers |
| B-02 | `docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'` | 10s | List all containers |

## Phase M2-3: Container Metadata

| ID | Command | Timeout | Purpose |
|---|---|---|---|
| C-01 | `docker inspect --format '{{json .State}}' CONTAINER_NAME` | 10s | Read-only state inspection |
| C-02 | `docker inspect --format '{{json .Config.Labels}}' CONTAINER_NAME` | 10s | Read-only label inspection |

## Phase M2-4: Bounded Log Review

| ID | Command | Timeout | Purpose |
|---|---|---|---|
| D-01 | `docker logs --since 6h --tail 1000 CONTAINER_NAME 2>&1` | 15s | Bounded log tail |
