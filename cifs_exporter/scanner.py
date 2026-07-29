"""Parcours du partage CIFS et mise à jour de l'état persistant."""

from __future__ import annotations

import fnmatch
import logging
import os
import time
from dataclasses import dataclass

from .config import Config
from .state_db import FileStat, StateDB

logger = logging.getLogger(__name__)


@dataclass
class ScanResult:
    scan_time: float
    duration_seconds: float
    files_seen: int
    files_deleted: int
    errors: int


def _is_excluded(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def run_scan(config: Config, db: StateDB) -> ScanResult:
    start = time.time()
    files_seen = 0
    errors = 0

    for root, dirnames, filenames in os.walk(config.cifs_path, followlinks=config.follow_symlinks):
        if config.exclude_globs:
            dirnames[:] = [d for d in dirnames if not _is_excluded(d, config.exclude_globs)]

        for filename in filenames:
            if config.exclude_globs and _is_excluded(filename, config.exclude_globs):
                continue

            path = os.path.join(root, filename)
            try:
                st = os.stat(path, follow_symlinks=config.follow_symlinks)
            except OSError as exc:
                errors += 1
                logger.warning("Impossible de lire %s: %s", path, exc)
                continue

            db.upsert_seen(
                FileStat(path=path, size_bytes=st.st_size, mtime=st.st_mtime, atime=st.st_atime),
                scan_time=start,
            )
            files_seen += 1

    files_deleted = db.mark_missing_as_deleted(start)
    db.set_meta("last_scan_time", str(start))
    db.commit()

    duration = time.time() - start
    logger.info(
        "Scan terminé: %d fichiers vus, %d marqués supprimés, %d erreurs, %.1fs",
        files_seen, files_deleted, errors, duration,
    )
    return ScanResult(
        scan_time=start,
        duration_seconds=duration,
        files_seen=files_seen,
        files_deleted=files_deleted,
        errors=errors,
    )
