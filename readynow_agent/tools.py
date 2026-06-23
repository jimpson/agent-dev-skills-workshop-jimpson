"""External data tools for the ReadyNow! agent.

All tools return plain JSON-serializable structures and never raise to the model;
on failure they return a structured ``{"status": "error", ...}`` payload so the
agent can tell the user honestly that data is unavailable rather than guessing.
"""

import logging
from typing import Dict, List, Optional

import requests

from . import config
from .logging_config import EVENT_ERROR, audit

_NWS_HEADERS = {"User-Agent": "readynow-fema-agent (workshop@example.com)"}
_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"


def _error(message: str, **fields) -> Dict:
    audit(EVENT_ERROR, message, level=logging.ERROR, **fields)
    return {"status": "error", "error_message": message}


def get_lat_long(place: str) -> Dict:
    """Convert a place name or address to latitude and longitude.

    Args:
        place (str): A place name or address, e.g. "Boulder, CO".

    Returns:
        Dict: {"status": "ok", "lat": float, "lon": float, "formatted_address": str}
        or {"status": "error", "error_message": str} if it cannot be resolved.
    """

    try:
        resp = requests.get(
            _GEOCODE_URL,
            params={"address": place, "key": config.maps_api_key()},
            timeout=10,
        ).json()
    except Exception as exc:
        return _error(f"Geocoding request failed: {exc}", tool_name="get_lat_long")

    if resp.get("status") != "OK" or not resp.get("results"):
        return _error(
            f"Could not resolve location: {place!r}", tool_name="get_lat_long"
        )

    result = resp["results"][0]
    loc = result["geometry"]["location"]
    return {
        "status": "ok",
        "lat": loc["lat"],
        "lon": loc["lng"],
        "formatted_address": result.get("formatted_address", place),
    }


def get_extended_weather_forecast(lat: float, lon: float) -> Dict:
    """Fetch the extended weather forecast from the US National Weather Service.

    Args:
        lat (float): Latitude of the location (e.g., 39.7392).
        lon (float): Longitude of the location (e.g., -104.9903).

    Returns:
        Dict: {"status": "ok", "periods": List[Dict]} where each period has
        name/temperature/wind/forecast, or {"status": "error", ...} on failure.
        The NWS API only covers United States locations.
    """

    try:
        points = requests.get(
            f"https://api.weather.gov/points/{lat},{lon}",
            headers=_NWS_HEADERS,
            timeout=10,
        ).json()
        forecast_url = points["properties"]["forecast"]
        periods = requests.get(forecast_url, headers=_NWS_HEADERS, timeout=10).json()
    except Exception as exc:
        return _error(
            f"NWS forecast request failed: {exc}",
            tool_name="get_extended_weather_forecast",
        )

    parsed: List[Dict[str, str]] = [
        {
            "name": p["name"],
            "temperature": f'{p["temperature"]} {p["temperatureUnit"]}',
            "wind": f'{p["windSpeed"]} {p["windDirection"]}',
            "forecast": p["detailedForecast"],
        }
        for p in periods.get("properties", {}).get("periods", [])
    ]
    if not parsed:
        return _error(
            "No forecast data returned (location may be outside the US).",
            tool_name="get_extended_weather_forecast",
        )
    return {"status": "ok", "periods": parsed, "source": "US National Weather Service"}


def get_active_weather_alerts(lat: float, lon: float) -> Dict:
    """Fetch active NWS weather alerts (warnings, watches, advisories) for a point.

    Args:
        lat (float): Latitude of the location.
        lon (float): Longitude of the location.

    Returns:
        Dict: {"status": "ok", "alerts": List[Dict]} with event/severity/urgency/
        headline/instruction per active alert (empty list if none are active),
        or {"status": "error", ...} on failure.
    """

    try:
        data = requests.get(
            "https://api.weather.gov/alerts/active",
            headers=_NWS_HEADERS,
            params={"point": f"{lat},{lon}"},
            timeout=10,
        ).json()
    except Exception as exc:
        return _error(
            f"NWS alerts request failed: {exc}", tool_name="get_active_weather_alerts"
        )

    alerts = [
        {
            "event": f["properties"].get("event"),
            "severity": f["properties"].get("severity"),
            "urgency": f["properties"].get("urgency"),
            "headline": f["properties"].get("headline"),
            "instruction": f["properties"].get("instruction"),
        }
        for f in data.get("features", [])
    ]
    return {
        "status": "ok",
        "alerts": alerts,
        "source": "US National Weather Service",
    }


def get_evacuation_routes(origin: str, destination: str) -> Dict:
    """Get driving directions toward safety using the Google Maps Directions API.

    Args:
        origin (str): Starting place or address (the user's current location).
        destination (str): A safe destination, e.g. a shelter, city, or address.

    Returns:
        Dict: {"status": "ok", "summary": str, "distance": str, "duration": str,
        "steps": List[str]} or {"status": "error", ...} if no route is found.
    """

    try:
        resp = requests.get(
            _DIRECTIONS_URL,
            params={
                "origin": origin,
                "destination": destination,
                "mode": "driving",
                "alternatives": "false",
                "key": config.maps_api_key(),
            },
            timeout=10,
        ).json()
    except Exception as exc:
        return _error(
            f"Directions request failed: {exc}", tool_name="get_evacuation_routes"
        )

    if resp.get("status") != "OK" or not resp.get("routes"):
        return _error(
            f"No route found from {origin!r} to {destination!r} "
            f"(status: {resp.get('status')}).",
            tool_name="get_evacuation_routes",
        )

    route = resp["routes"][0]
    leg = route["legs"][0]
    steps = [
        requests.utils.unquote(
            s["html_instructions"]
            .replace("<b>", "")
            .replace("</b>", "")
            .replace('<div style="font-size:0.9em">', " - ")
            .replace("</div>", "")
        )
        for s in leg.get("steps", [])
    ]
    return {
        "status": "ok",
        "summary": route.get("summary", ""),
        "distance": leg.get("distance", {}).get("text", ""),
        "duration": leg.get("duration", {}).get("text", ""),
        "start_address": leg.get("start_address", origin),
        "end_address": leg.get("end_address", destination),
        "steps": steps,
        "source": "Google Maps Directions API",
    }
