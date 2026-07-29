"""Boucle périodique : scan -> métriques -> rapport -> pause."""

from __future__ import annotations

import logging
import time

from .config import Config
from .metrics import refresh_metrics
from .report import write_report
from .scanner import run_scan
from .state_db import StateDB

logger = logging.getLogger(__name__)


def run_once(config: Config, db: StateDB) -> None:
    scan_result = run_scan(config, db)
    counts = refresh_metrics(db, scan_result, config.stale_seconds)
    write_report(db, config.report_dir, config.stale_days, config.stale_seconds)
    logger.info(
        "Résumé: total=%d used=%d stale=%d unknown=%d bytes_stale=%d",
        counts["total"], counts["used"], counts["stale"], counts["unknown"],
        counts["stale_bytes"],
    )


def run_forever(config: Config, db: StateDB) -> None:
    while True:
        try:
            run_once(config, db)
        except Exception:
            logger.exception("Échec du cycle de scan, nouvelle tentative après la pause habituelle")
        time.sleep(config.scan_interval_seconds)
