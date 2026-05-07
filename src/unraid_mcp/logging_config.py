"""Logging setup for the Unraid MCP server.

Logs always go to stderr because stdio transport reserves stdout for MCP
protocol traffic; any byte on stdout that isn't a JSON-RPC frame corrupts
the channel. The default formatter emits a single-line JSON object per
record so logs are machine-parseable when the server runs under a
supervisor or container runtime.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

_DEFAULT_LEVEL = "INFO"
_PLAIN_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_RECORD_PASSTHROUGH = frozenset({"exc_info", "stack_info", "exc_text"})


class JSONFormatter(logging.Formatter):
    """Minimal one-line-per-record JSON formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(*, level: str | None = None, plain: bool | None = None) -> None:
    """Install a stderr handler on the root logger. Idempotent.

    Args:
        level: Override the log level. Falls back to ``UNRAID_LOG_LEVEL`` env
            var, then ``INFO``.
        plain: If True, use a human-readable format instead of JSON. Falls
            back to ``UNRAID_LOG_FORMAT=plain`` when unset.
    """
    resolved_level = (level or os.environ.get("UNRAID_LOG_LEVEL") or _DEFAULT_LEVEL).upper()
    use_plain = plain if plain is not None else os.environ.get("UNRAID_LOG_FORMAT") == "plain"

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_PLAIN_FORMAT) if use_plain else JSONFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, "_unraid_mcp_handler", False):
            root.removeHandler(existing)
    handler._unraid_mcp_handler = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(resolved_level)
