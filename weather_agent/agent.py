import logging
import os
import sys
from typing import Dict, List, Optional

import requests
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools import agent_tool, google_search
from google.cloud import modelarmor_v1
from google.genai import types
from vertexai.preview.reasoning_engines import AdkApp

MA_LOCATION = "us-central1"
GEMINI_MODEL = "gemini-2.5-flash"

_ma_client_instance = None


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Run the notebook config cell before importing weather_agent."
        )
    return value


def _project_id() -> str:
    return _require_env("GOOGLE_CLOUD_PROJECT")


def _maps_api_key() -> str:
    return _require_env("MAPS_API_KEY")


def _ma_template() -> str:
    template_id = os.environ.get("MA_TEMPLATE_ID", "weather-agent-armor")
    return f"projects/{_project_id()}/locations/{MA_LOCATION}/templates/{template_id}"


def _ma_client() -> modelarmor_v1.ModelArmorClient:
    global _ma_client_instance
    if _ma_client_instance is None:
        _ma_client_instance = modelarmor_v1.ModelArmorClient(
            transport="rest",
            client_options={"api_endpoint": f"modelarmor.{MA_LOCATION}.rep.googleapis.com"},
        )
    return _ma_client_instance


def get_lat_long(place: str) -> Optional[Dict[str, float]]:
    """Convert a place name to latitude and longitude using the Google Maps Geocoding API.

    Args:
        place (str): A place name or address, e.g. "Denver, CO".

    Returns:
        Optional[Dict[str, float]]: {"lat": float, "lon": float}, or None if not found.
    """

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    resp = requests.get(url, params={"address": place, "key": _maps_api_key()}, timeout=10)
    data = resp.json()

    if data.get("status") != "OK" or not data.get("results"):
        return None

    loc = data["results"][0]["geometry"]["location"]
    print({"lat": loc["lat"], "lon": loc["lng"]})
    return {"lat": loc["lat"], "lon": loc["lng"]}


def get_extended_weather_forecast(lat: float, lon: float) -> Optional[List[Dict[str, str]]]:
    """Fetch the extended weather forecast from the US National Weather Service API.

    Args:
        lat (float): Latitude of the location (e.g., 38.8977).
        lon (float): Longitude of the location (e.g., -77.0365).

    Returns:
        Optional[List[Dict[str, str]]]: A list of forecast period dicts,
        or None if data is unavailable or an error occurs.
    """

    headers = {"User-Agent": "adk-weather-agent (workshop@example.com)"}

    try:
        points = requests.get(
            f"https://api.weather.gov/points/{lat},{lon}", headers=headers, timeout=10
        ).json()
        forecast_url = points["properties"]["forecast"]
        periods = requests.get(forecast_url, headers=headers, timeout=10).json()

        return [
            {
                "name": p["name"],
                "temperature": f'{p["temperature"]} {p["temperatureUnit"]}',
                "wind": f'{p["windSpeed"]} {p["windDirection"]}',
                "forecast": p["detailedForecast"],
            }
            for p in periods["properties"]["periods"]
        ]
    except Exception:
        return None


def model_armor_flags_prompt(text: str) -> bool:
    """Return True if Model Armor flags the user prompt as unsafe."""

    try:
        resp = _ma_client().sanitize_user_prompt(
            request=modelarmor_v1.SanitizeUserPromptRequest(
                name=_ma_template(),
                user_prompt_data=modelarmor_v1.DataItem(text=text),
            )
        )
        return resp.sanitization_result.filter_match_state == modelarmor_v1.FilterMatchState.MATCH_FOUND
    except Exception as e:
        print(f"[Model Armor] prompt check skipped: {e}")
        return False


def model_armor_flags_response(text: str) -> bool:
    """Return True if Model Armor flags the model response as unsafe."""

    try:
        resp = _ma_client().sanitize_model_response(
            request=modelarmor_v1.SanitizeModelResponseRequest(
                name=_ma_template(),
                model_response_data=modelarmor_v1.DataItem(text=text),
            )
        )
        return resp.sanitization_result.filter_match_state == modelarmor_v1.FilterMatchState.MATCH_FOUND
    except Exception as e:
        print(f"[Model Armor] response check skipped: {e}")
        return False


class ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\033[36m",
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[41m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"


logger = logging.getLogger("weather_agent")
logger.setLevel(logging.INFO)
logger.propagate = False
logger.handlers.clear()
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColorFormatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)


def is_us_location(text: str) -> Optional[bool]:
    """Use the Geocoding API to decide if text refers to a US location.
    Returns True (US), False (non-US), or None if no location could be resolved.
    """

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": text, "key": _maps_api_key()},
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
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=message)]))


def log_user_prompt(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:
    text = _last_user_text(llm_request)
    if text:
        logger.info("[%s] USER >> %s", callback_context.agent_name, text)
    return None


def validate_security(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:
    text = _last_user_text(llm_request)
    if text and model_armor_flags_prompt(text):
        logger.warning("[%s] BLOCKED (Model Armor) >> %s", callback_context.agent_name, text)
        return _refuse("Your request was blocked by our safety filters. Please rephrase and try again.")
    return None


def validate_us_location(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:
    text = _last_user_text(llm_request)
    if text and is_us_location(text) is False:
        logger.warning("[%s] BLOCKED (non-US) >> %s", callback_context.agent_name, text)
        return _refuse("I'm sorry, but I can only provide weather assistance for locations within the United States.")
    return None


def log_model_response(callback_context: CallbackContext, llm_response: LlmResponse) -> Optional[LlmResponse]:
    if llm_response.content and llm_response.content.parts:
        txt = llm_response.content.parts[0].text
        if txt:
            logger.info("[%s] MODEL >> %s", callback_context.agent_name, txt.strip())
            if model_armor_flags_response(txt):
                logger.warning("[%s] RESPONSE flagged by Model Armor", callback_context.agent_name)
                return _refuse("The response was withheld by our safety filters.")
    return None


def root_before_model(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:
    log_user_prompt(callback_context, llm_request)
    return validate_security(callback_context, llm_request)


def weather_before_model(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:
    log_user_prompt(callback_context, llm_request)
    return validate_us_location(callback_context, llm_request)


def search_before_model(callback_context: CallbackContext, llm_request: LlmRequest) -> Optional[LlmResponse]:
    log_user_prompt(callback_context, llm_request)
    return None


WEATHER_AGENT_INSTRUCTIONS = """You are Mitch, a friendly US weather assistant.
When a user names a place, call get_lat_long to get coordinates, then call
get_extended_weather_forecast to get the forecast. Summarize current conditions
and call out any alerts (storms, extreme heat/cold, high winds). The NWS API only
covers the United States; if a location is outside the US, say so politely."""

weather_agent = Agent(
    name="Weather_Agent",
    model=GEMINI_MODEL,
    description="Provides current US weather forecasts and alerts for a city or location.",
    instruction=WEATHER_AGENT_INSTRUCTIONS,
    tools=[get_lat_long, get_extended_weather_forecast],
    before_model_callback=weather_before_model,
    after_model_callback=log_model_response,
)

search_agent = Agent(
    name="Search_Agent",
    model=GEMINI_MODEL,
    description="Answers general knowledge questions using Google Search.",
    instruction="You are a research assistant. Use Google Search to answer general questions accurately and concisely.",
    tools=[google_search],
    before_model_callback=search_before_model,
    after_model_callback=log_model_response,
)

root_agent = Agent(
    name="Coordinator_Agent",
    model=GEMINI_MODEL,
    description="Coordinates weather and general-knowledge requests.",
    instruction="""You are a coordinator that routes each user request to the right specialist.
- If the request is about weather, forecasts, temperature, rain, snow, storms, wind, or conditions
  for a place, transfer to 'Weather_Agent'.
- For any other general-knowledge question, call the 'Search_Agent' tool to answer it.
- Do not answer weather or general questions yourself; always delegate.""",
    tools=[agent_tool.AgentTool(agent=search_agent)],
    sub_agents=[weather_agent],
    before_model_callback=root_before_model,
    after_model_callback=log_model_response,
)

app = AdkApp(agent=root_agent, enable_tracing=True)
