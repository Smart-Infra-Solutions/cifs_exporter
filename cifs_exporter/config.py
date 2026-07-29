"""Configuration chargée depuis les variables d'environnement."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigError(Exception):
    pass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} doit être un entier, reçu: {raw!r}") from exc


def _env_globs(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    return tuple(p.strip() for p in raw.split(",") if p.strip())


@dataclass(frozen=True)
class Config:
    cifs_path: str
    state_db_path: str
    report_dir: str
    scan_interval_seconds: int
    stale_days: int
    metrics_port: int
    exclude_globs: tuple[str, ...] = field(default_factory=tuple)
    follow_symlinks: bool = False
    run_once: bool = False
    log_level: str = "INFO"

    @property
    def stale_seconds(self) -> float:
        return self.stale_days * 86400

    @classmethod
    def from_env(cls) -> "Config":
        cifs_path = os.environ.get("CIFS_PATH")
        if not cifs_path:
            raise ConfigError("CIFS_PATH est obligatoire (chemin du partage CIFS déjà monté)")
        if not os.path.isdir(cifs_path):
            raise ConfigError(f"CIFS_PATH n'est pas un répertoire existant: {cifs_path!r}")

        state_db_path = os.environ.get("STATE_DB_PATH", "/data/state/state.db")
        report_dir = os.environ.get("REPORT_DIR", "/data/state")

        return cls(
            cifs_path=cifs_path,
            state_db_path=state_db_path,
            report_dir=report_dir,
            scan_interval_seconds=_env_int("SCAN_INTERVAL_SECONDS", 86400),
            stale_days=_env_int("STALE_DAYS", 90),
            metrics_port=_env_int("METRICS_PORT", 9877),
            exclude_globs=_env_globs("EXCLUDE_GLOBS"),
            follow_symlinks=_env_bool("FOLLOW_SYMLINKS", False),
            run_once=_env_bool("RUN_ONCE", False),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
