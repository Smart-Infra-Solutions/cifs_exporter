"""Génération du rapport de ménage (CSV détaillé + résumé JSON)."""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timezone

from .state_db import StateDB


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _classify(now: float, first_seen: float, last_used_at: float, stale_seconds: float) -> str:
    if (now - first_seen) <= stale_seconds:
        return "unknown"
    if (now - last_used_at) > stale_seconds:
        return "stale"
    return "used"


def write_report(db: StateDB, report_dir: str, stale_days: int, stale_seconds: float) -> str:
    os.makedirs(report_dir, exist_ok=True)
    now = time.time()

    csv_path = os.path.join(report_dir, "report.csv")
    counts = {"used": 0, "stale": 0, "unknown": 0}
    total_bytes = 0
    stale_bytes = 0

    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "path", "size_bytes", "first_seen_iso", "last_atime_iso", "last_used_at_iso",
            "days_since_last_use", "first_seen_days_ago", "status",
        ])
        for path, size_bytes, first_seen, last_atime, last_used_at in db.iter_active_files():
            status = _classify(now, first_seen, last_used_at, stale_seconds)
            counts[status] += 1
            total_bytes += size_bytes
            if status == "stale":
                stale_bytes += size_bytes

            writer.writerow([
                path,
                size_bytes,
                _iso(first_seen),
                _iso(last_atime),
                _iso(last_used_at),
                round((now - last_used_at) / 86400, 1),
                round((now - first_seen) / 86400, 1),
                status,
            ])

    summary_path = os.path.join(report_dir, "summary.json")
    summary = {
        "generated_at": _iso(now),
        "stale_days_threshold": stale_days,
        "files_total": sum(counts.values()),
        "files_used": counts["used"],
        "files_stale": counts["stale"],
        "files_unknown": counts["unknown"],
        "bytes_total": total_bytes,
        "bytes_stale_recoverable": stale_bytes,
    }
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    return csv_path
