# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A container that scans a CIFS share (already mounted on the host — this project
never mounts CIFS itself) and determines which files are actually **used**
(accessed) vs **stale** (unused for a long time), to help clean up a large
share. It exposes Prometheus metrics for Grafana and writes a CSV/JSON report.
The container is read-only: it never deletes, moves, or modifies anything on
the share.

## Commands

Local run (no Docker needed — point `CIFS_PATH` at any local directory):

```bash
pip install -r requirements.txt
CIFS_PATH=./some-dir RUN_ONCE=true python -m cifs_exporter.main
curl http://localhost:9877/metrics
```

Docker:

```bash
docker compose -f docker-compose.example.yml up -d --build
```

CI (`.woodpecker/docker-publish.yml`) builds and pushes the image to Docker Hub as
`smartinfrasolutions/cifs_exporter` on push to `main` (tag `latest`) and on
`v*` tags (`auto_tag`, versioned tags + `latest`). Uses the `docker_token`
Woodpecker secret as the Docker Hub password for the `smartinfrasolutions`
account.

There is no test suite yet — verify changes by running two successive
`RUN_ONCE=true` scans against a local test directory and inspecting
`REPORT_DIR/report.csv` / `summary.json` (see git history for the manual
verification steps used when this was built).

## Architecture

Pipeline, one module per stage, wired together in `scheduler.py` /
`main.py`:

```
config.py   -> Config.from_env(), fails fast if CIFS_PATH is missing/invalid
state_db.py -> SQLite persistence (StateDB) — the source of truth across scans
scanner.py  -> os.walk(CIFS_PATH), stats each file, calls db.upsert_seen()
metrics.py  -> refresh_metrics(): recomputes Prometheus gauges from StateDB
report.py   -> write_report(): writes report.csv + summary.json from StateDB
scheduler.py-> run_once() / run_forever(): scan -> metrics -> report -> sleep
main.py     -> loads Config, starts prometheus_client HTTP server, dispatches
               to run_once (RUN_ONCE=true) or run_forever
```

**Core idea — usage detection needs history, not a snapshot.** A single scan
of a share only shows current atime; it can't tell you if a file is "used".
`state_db.StateDB` keeps one row per file (`first_seen`, `last_atime`,
`last_used_at`, `last_scan_time`). On every scan, `upsert_seen()` only
advances `last_used_at` when the newly observed `atime` is greater than the
previously recorded `last_atime` — that's the signal a real access happened
since the last scan. Files not seen in the current scan get soft-deleted
(`status='deleted'`, kept for history, not purged) rather than removed from
the table.

**Classification is a strict 3-way partition — must stay in sync in two
places.** A file is:
- `unknown` if `now - first_seen <= STALE_DAYS` (not enough tracking history yet
  to judge it — avoids flagging recently-added files as stale)
- otherwise `stale` if `now - last_used_at > STALE_DAYS`
- otherwise `used`

This exact precedence (unknown checked first) is implemented independently in
two places that must agree: `report.py:_classify()` (per-file, for the CSV)
and `state_db.py:StateDB.aggregate_counts()` (the SQL CASE expressions behind
the Prometheus gauges). They were briefly inconsistent during development
(aggregate counts weren't mutually exclusive with `unknown`) — if you touch
the classification rule, update both and check `used + stale + unknown ==
total`.

**Config is env-var only** (`config.py`), no config files. `CIFS_PATH` is the
only required variable; everything else has a default. `STATE_DB_PATH` must
live outside the CIFS share (on a separate persistent volume) since the share
is treated as read-only.

## Known limitation to keep in mind

The whole approach depends on the source share/server actually updating
atime. `noatime` on the client mount, or Windows' "last access time" tracking
being disabled (the default since Vista/Server 2008), makes every file look
permanently unused. This is a fundamental limitation of the design, not a bug
— see the README's "⚠️ Limite importante" section before changing the
detection logic.
