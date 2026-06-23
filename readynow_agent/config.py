"""Centralized configuration for the ReadyNow! emergency preparedness agent.

Environment values are read lazily so the package can be imported before the
notebook/deploy config cell has populated the environment, then validated at the
point of use. Agent Engine injects GOOGLE_CLOUD_* at deploy time.
"""

import os

from google.genai import types

GEMINI_PRO = "gemini-2.5-pro"
GEMINI_FLASH = "gemini-2.5-flash"

MA_LOCATION = "us-central1"
DEFAULT_MA_TEMPLATE_ID = "readynow-armor"

# Low temperature reduces variance and hallucination for an emergency assistant.
GROUNDED_CONFIG = types.GenerateContentConfig(temperature=0.1, top_p=0.85)
DETERMINISTIC_CONFIG = types.GenerateContentConfig(temperature=0.0, top_p=0.7)


def require_env(name: str) -> str:
    """Return a required environment variable or raise a clear error."""

    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Run the deploy/notebook config cell (or export it) "
            "before using the ReadyNow! agent."
        )
    return value


def project_id() -> str:
    return require_env("GOOGLE_CLOUD_PROJECT")


def maps_api_key() -> str:
    return require_env("MAPS_API_KEY")


def ma_template_id() -> str:
    return os.environ.get("MA_TEMPLATE_ID", DEFAULT_MA_TEMPLATE_ID).strip() or DEFAULT_MA_TEMPLATE_ID


def ma_template_path() -> str:
    return f"projects/{project_id()}/locations/{MA_LOCATION}/templates/{ma_template_id()}"


def log_level() -> str:
    return os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO"
