"""Métriques Prometheus exposées pour Grafana."""

from __future__ import annotations

import time

from prometheus_client import Counter, Gauge

from .scanner import ScanResult
from .state_db import StateDB

SCAN_TIMESTAMP = Gauge(
    "cifs_exporter_scan_timestamp_seconds", "Timestamp Unix du dernier scan terminé"
)
SCAN_DURATION = Gauge(
    "cifs_exporter_scan_duration_seconds", "Durée du dernier scan en secondes"
)
SCAN_ERRORS = Counter(
    "cifs_exporter_scan_errors_total", "Nombre cumulé d'erreurs de lecture de fichiers"
)

FILES_TOTAL = Gauge("cifs_exporter_files_total", "Nombre total de fichiers actifs suivis")
FILES_USED = Gauge(
    "cifs_exporter_files_used", "Fichiers accédés récemment (dans la fenêtre STALE_DAYS)"
)
FILES_STALE = Gauge(
    "cifs_exporter_files_stale", "Fichiers candidats au nettoyage (inactifs depuis STALE_DAYS)"
)
FILES_UNKNOWN = Gauge(
    "cifs_exporter_files_unknown", "Fichiers sans historique suffisant pour être classés"
)

BYTES_TOTAL = Gauge("cifs_exporter_bytes_total", "Octets totaux suivis")
BYTES_STALE = Gauge("cifs_exporter_bytes_stale", "Octets potentiellement récupérables")


def refresh_metrics(db: StateDB, scan_result: ScanResult, stale_seconds: float) -> dict:
    SCAN_TIMESTAMP.set(scan_result.scan_time)
    SCAN_DURATION.set(scan_result.duration_seconds)
    SCAN_ERRORS.inc(scan_result.errors)

    counts = db.aggregate_counts(now=time.time(), stale_seconds=stale_seconds)
    FILES_TOTAL.set(counts["total"])
    FILES_USED.set(counts["used"])
    FILES_STALE.set(counts["stale"])
    FILES_UNKNOWN.set(counts["unknown"])
    BYTES_TOTAL.set(counts["total_bytes"])
    BYTES_STALE.set(counts["stale_bytes"])
    return counts
