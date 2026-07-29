"""Point d'entrée du conteneur."""

from __future__ import annotations

import logging
import os
import sys

from prometheus_client import start_http_server

from .config import Config, ConfigError
from .scheduler import run_forever, run_once
from .state_db import StateDB


def main() -> int:
    try:
        config = Config.from_env()
    except ConfigError as exc:
        logging.basicConfig(level="ERROR")
        logging.getLogger(__name__).error("Configuration invalide: %s", exc)
        return 1

    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    os.makedirs(os.path.dirname(config.state_db_path) or ".", exist_ok=True)
    db = StateDB(config.state_db_path)

    start_http_server(config.metrics_port)
    logger.info(
        "cifs_exporter démarré: cifs_path=%s metrics_port=%d scan_interval=%ds stale_days=%d run_once=%s",
        config.cifs_path, config.metrics_port, config.scan_interval_seconds,
        config.stale_days, config.run_once,
    )

    if config.run_once:
        run_once(config, db)
    else:
        run_forever(config, db)

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
