"""Safety and input-validation layer for the ReadyNow! agent.

Three independent guards, each logged:
  * Model Armor (strict)  - blocks unsafe prompts and responses.
  * Mission scoping       - refuses requests outside the emergency mission.
  * US-location check     - the NWS data source only covers the United States.

Design choice: Model Armor service errors fail OPEN (the request proceeds) but
are logged at ERROR. For a life-safety assistant, availability is prioritized
over hard-failing when the safety service itself is unreachable; the audit trail
still captures the gap so it can be alerted on.
"""

import logging
from typing import Optional

import requests
from google.cloud import modelarmor_v1
from google.genai import types

from . import config
from .logging_config import EVENT_ERROR, audit

_ma_client = None
_genai_client = None

MISSION_DESCRIPTION = (
    "emergency preparedness, disasters, severe weather, evacuation routes, "
    "shelter and safety information, and related real-time alerts"
)


def _model_armor_client() -> modelarmor_v1.ModelArmorClient:
    global _ma_client
    if _ma_client is None:
        _ma_client = modelarmor_v1.ModelArmorClient(
            transport="rest",
            client_options={
                "api_endpoint": f"modelarmor.{config.MA_LOCATION}.rep.googleapis.com"
            },
        )
    return _ma_client


def _genai():
    global _genai_client
    if _genai_client is None:
        from google import genai

        _genai_client = genai.Client()
    return _genai_client


def _is_match(sanitization_result, stage: str) -> bool:
    matched = (
        sanitization_result.filter_match_state
        == modelarmor_v1.FilterMatchState.MATCH_FOUND
    )
    if matched:
        # Record which filter(s) matched to make false positives diagnosable.
        try:
            detail = str(sanitization_result.filter_results)[:1000]
        except Exception:
            detail = "<unavailable>"
        audit(
            EVENT_ERROR,
            f"Model Armor matched on {stage}",
            level=logging.WARNING,
            fields={"filter_results": detail},
        )
    return matched


def model_armor_flags_prompt(text: str) -> bool:
    """Return True if Model Armor flags the user prompt as unsafe (fail-open)."""

    try:
        resp = _model_armor_client().sanitize_user_prompt(
            request=modelarmor_v1.SanitizeUserPromptRequest(
                name=config.ma_template_path(),
                user_prompt_data=modelarmor_v1.DataItem(text=text),
            )
        )
        return _is_match(resp.sanitization_result, "prompt")
    except Exception as exc:
        audit(
            EVENT_ERROR,
            "Model Armor prompt check failed (failing open)",
            level=logging.ERROR,
            fields={"reason": str(exc)},
        )
        return False


def model_armor_flags_response(text: str) -> bool:
    """Return True if Model Armor flags the model response as unsafe (fail-open)."""

    try:
        resp = _model_armor_client().sanitize_model_response(
            request=modelarmor_v1.SanitizeModelResponseRequest(
                name=config.ma_template_path(),
                model_response_data=modelarmor_v1.DataItem(text=text),
            )
        )
        return _is_match(resp.sanitization_result, "response")
    except Exception as exc:
        audit(
            EVENT_ERROR,
            "Model Armor response check failed (failing open)",
            level=logging.ERROR,
            fields={"reason": str(exc)},
        )
        return False


def is_us_location(text: str) -> Optional[bool]:
    """Return True if text resolves to a US location, False if non-US, None if unknown."""

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": text, "key": config.maps_api_key()},
            timeout=10,
        ).json()
        if resp.get("status") != "OK" or not resp.get("results"):
            return None
        for comp in resp["results"][0]["address_components"]:
            if "country" in comp["types"]:
                return comp["short_name"] == "US"
        return None
    except Exception:
        return None


def is_on_mission(text: str) -> Optional[bool]:
    """Classify whether a request is within the ReadyNow! mission.

    Returns True (on-mission), False (off-mission), or None if classification
    could not be performed (in which case callers should fail open).
    """

    prompt = (
        "You are a strict request classifier for an emergency preparedness "
        "assistant whose mission is: "
        f"{MISSION_DESCRIPTION}.\n"
        "Greetings and questions about what the assistant can do are ON-mission.\n"
        "Reply with exactly one word: ON or OFF.\n\n"
        f"Request: {text}"
    )
    try:
        resp = _genai().models.generate_content(
            model=config.GEMINI_FLASH,
            contents=prompt,
            config=config.DETERMINISTIC_CONFIG,
        )
        verdict = (resp.text or "").strip().upper()
        if verdict.startswith("ON"):
            return True
        if verdict.startswith("OFF"):
            return False
        return None
    except Exception as exc:
        audit(
            EVENT_ERROR,
            "Mission classifier failed (failing open)",
            level=logging.ERROR,
            fields={"reason": str(exc)},
        )
        return None


def refuse(message: str) -> types.Content:
    """Build a model-role refusal Content payload."""

    return types.Content(role="model", parts=[types.Part(text=message)])
