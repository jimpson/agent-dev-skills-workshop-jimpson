"""Lifecycle callbacks: full-coverage audit logging plus input validation.

Coverage:
  * before_model  - log the user prompt; run Model Armor + (optionally) mission
                    and US-location validation; block by returning an LlmResponse.
  * after_model   - log the model response; Model Armor screens the output.
  * before_tool   - log every tool invocation and its arguments.
  * after_tool    - log every tool result.
"""

import logging
from typing import Any, Dict, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from . import safety
from .logging_config import (
    EVENT_LOCATION_REFUSAL,
    EVENT_MISSION_REFUSAL,
    EVENT_MODEL_RESPONSE,
    EVENT_SAFETY_BLOCK,
    EVENT_TOOL_CALL,
    EVENT_TOOL_RESULT,
    EVENT_USER_PROMPT,
    audit,
)

_LOCATION_REFUSAL = (
    "I'm sorry, but ReadyNow! provides emergency and weather assistance only for "
    "locations within the United States."
)
_MISSION_REFUSAL = (
    "I'm ReadyNow!, an emergency preparedness assistant. I can help with severe "
    "weather, disaster alerts, evacuation routes, and safety information. I can't "
    "help with that request, but I'm here for anything related to staying safe."
)
_SAFETY_REFUSAL = (
    "Your request was blocked by our safety filters. Please rephrase and try again."
)
_RESPONSE_WITHHELD = "That response was withheld by our safety filters."


def _ctx_ids(callback_context: CallbackContext) -> Dict[str, Any]:
    ids: Dict[str, Any] = {
        "agent_name": getattr(callback_context, "agent_name", None),
        "session_id": getattr(callback_context, "invocation_id", None),
    }
    inv = getattr(callback_context, "_invocation_context", None)
    if inv is not None:
        ids["user_id"] = getattr(inv, "user_id", None)
        session = getattr(inv, "session", None)
        if session is not None:
            ids["session_id"] = getattr(session, "id", ids["session_id"])
    return ids


def _last_user_text(llm_request: LlmRequest) -> Optional[str]:
    if not llm_request.contents:
        return None
    for content in reversed(llm_request.contents):
        if content.role == "user" and content.parts:
            for part in content.parts:
                if getattr(part, "text", None):
                    return part.text.strip()
    return None


def _refuse(message: str) -> LlmResponse:
    return LlmResponse(content=safety.refuse(message))


def log_user_prompt(callback_context: CallbackContext, llm_request: LlmRequest) -> None:
    text = _last_user_text(llm_request)
    if text:
        audit(EVENT_USER_PROMPT, text, **_ctx_ids(callback_context))


def validate_security(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    text = _last_user_text(llm_request)
    if text and safety.model_armor_flags_prompt(text):
        audit(
            EVENT_SAFETY_BLOCK,
            "Prompt blocked by Model Armor",
            level=logging.WARNING,
            **_ctx_ids(callback_context),
        )
        return _refuse(_SAFETY_REFUSAL)
    return None


def validate_mission(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    text = _last_user_text(llm_request)
    if text and safety.is_on_mission(text) is False:
        audit(
            EVENT_MISSION_REFUSAL,
            "Request refused as off-mission",
            level=logging.WARNING,
            **_ctx_ids(callback_context),
        )
        return _refuse(_MISSION_REFUSAL)
    return None


def validate_us_location(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    text = _last_user_text(llm_request)
    if text and safety.is_us_location(text) is False:
        audit(
            EVENT_LOCATION_REFUSAL,
            "Request refused as non-US location",
            level=logging.WARNING,
            **_ctx_ids(callback_context),
        )
        return _refuse(_LOCATION_REFUSAL)
    return None


def log_model_response(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> Optional[LlmResponse]:
    if llm_response.content and llm_response.content.parts:
        txt = llm_response.content.parts[0].text
        if txt:
            audit(EVENT_MODEL_RESPONSE, txt.strip(), **_ctx_ids(callback_context))
            if safety.model_armor_flags_response(txt):
                audit(
                    EVENT_SAFETY_BLOCK,
                    "Response withheld by Model Armor",
                    level=logging.WARNING,
                    **_ctx_ids(callback_context),
                )
                return _refuse(_RESPONSE_WITHHELD)
    return None


def log_tool_call(
    tool: BaseTool, args: Dict[str, Any], tool_context: ToolContext
) -> Optional[Dict]:
    audit(
        EVENT_TOOL_CALL,
        f"Calling tool {tool.name}",
        agent_name=getattr(tool_context, "agent_name", None),
        session_id=getattr(tool_context, "invocation_id", None),
        tool_name=tool.name,
        args=args,
    )
    return None


def log_tool_result(
    tool: BaseTool,
    args: Dict[str, Any],
    tool_context: ToolContext,
    tool_response: Dict,
) -> Optional[Dict]:
    audit(
        EVENT_TOOL_RESULT,
        f"Tool {tool.name} returned",
        agent_name=getattr(tool_context, "agent_name", None),
        session_id=getattr(tool_context, "invocation_id", None),
        tool_name=tool.name,
        result=tool_response,
    )
    return None


# --- Composed before_model chains (run validation in order, log first) ---

def root_before_model(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    log_user_prompt(callback_context, llm_request)
    blocked = validate_security(callback_context, llm_request)
    if blocked is not None:
        return blocked
    return validate_mission(callback_context, llm_request)


def weather_before_model(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    log_user_prompt(callback_context, llm_request)
    blocked = validate_security(callback_context, llm_request)
    if blocked is not None:
        return blocked
    return validate_us_location(callback_context, llm_request)


def specialist_before_model(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    log_user_prompt(callback_context, llm_request)
    return validate_security(callback_context, llm_request)
