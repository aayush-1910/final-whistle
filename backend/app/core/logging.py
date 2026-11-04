"""
Logging setup.  LOG_FORMAT=json (production) writes one JSON object per line,
which hosting dashboards can search and filter; anything else gives readable
text for local use.  Secrets are never logged: connection settings and keys
are not passed to log calls anywhere in the app.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

_STANDARD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD and not key.startswith("_"):
                out[key] = value
        if record.exc_info:
            out["exception"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging(level: str | None = None, fmt: str | None = None) -> None:
    level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    fmt = (fmt or os.getenv("LOG_FORMAT") or "text").lower()
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Quiet chatty libraries.
    for noisy in ("httpx", "httpcore", "psycopg.pool"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, root.level))
