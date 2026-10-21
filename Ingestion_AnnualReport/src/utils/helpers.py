"""Batch helpers and application logging."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterable, Sequence


def _batched(items: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def configure_logging(log_file: Path) -> None:
    """Configure console and bounded file logs once at the application boundary."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3),
        ],
    )
