from __future__ import annotations

import logging
import sys

from . import config


def setup_logging(level: str | None = None) -> None:
    log_level = level or config.LOG_LEVEL
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(config.LOG_FORMAT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)
