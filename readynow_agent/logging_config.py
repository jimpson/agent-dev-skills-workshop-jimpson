"""Structured, multi-level audit logging for the ReadyNow! agent.

Logs are emitted to Google Cloud Logging when available (so a real FEMA
deployment has a durable audit trail), and always to stdout for local runs and
Agent Engine console output. Every record carries structured context
(session/user/agent/event_type) so interactions can be traced end to end.
"""

import json
import logging
import sys
from typing import Any, Optional

from . import config

LOGGER_NAME = "readynow"

# Canonical audit event types emitted across the agent lifecycle.
EVENT_USER_PROMPT = "USER_PROMPT"
EVENT_MODEL_RESPONSE = "MODEL_RESPONSE"
EVENT_TOOL_CALL = "TOOL_CALL"
EVENT_TOOL_RESULT = "TOOL_RESULT"
EVENT_SAFETY_BLOCK = "SAFETY_BLOCK"
EVENT_MISSION_REFUSAL = "MISSION_REFUSAL"
EVENT_LOCATION_REFUSAL = "LOCATION_REFUSAL"
EVENT_ERROR = "ERROR"


class _StdoutJsonFormatter(logging.Formatter):
    """Render records as single-line JSON for readable, greppable stdout logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record),
            "severity": record.levelname,
            "event_type": getattr(record, "event_type", None),
            "message": record.getMessage(),
        }
        for key in ("session_id", "user_id", "agent_name", "tool_name", "fields"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, default=str)


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(config.log_level())
    logger.propagate = False

    if logger.handlers:
        return logger

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(_StdoutJsonFormatter())
    logger.addHandler(stdout_handler)

    # Attach Cloud Logging when the library and credentials are available.
    try:
        import google.cloud.logging
        from google.cloud.logging.handlers import StructuredLogHandler

        google.cloud.logging.Client()  # validates credentials/project
        logger.addHandler(StructuredLogHandler())
        logger.info(
            "Cloud Logging enabled",
            extra={"event_type": "STARTUP", "agent_name": "readynow"},
        )
    except Exception as exc:  # pragma: no cover - depends on runtime env
        logger.warning(
            "Cloud Logging unavailable; using stdout only",
            extra={"event_type": "STARTUP", "fields": {"reason": str(exc)}},
        )

    return logger


logger = _build_logger()


def audit(
    event_type: str,
    message: str,
    *,
    level: int = logging.INFO,
    agent_name: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    **fields: Any,
) -> None:
    """Emit a structured audit event at the requested level."""

    logger.log(
        level,
        message,
        extra={
            "event_type": event_type,
            "agent_name": agent_name,
            "session_id": session_id,
            "user_id": user_id,
            "tool_name": tool_name,
            "fields": fields or None,
        },
    )
