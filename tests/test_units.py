"""Unit tests for ReadyNow! tools and safety logic with all externals mocked.

These cover the pure parsing/decision logic so they run without network access,
GCP credentials, or live APIs. Run with: pytest tests/
"""

import types as pytypes

import pytest

from readynow_agent import config, safety, tools


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _fake_maps_key(monkeypatch):
    monkeypatch.setattr(config, "maps_api_key", lambda: "test-key")


def _patch_requests(monkeypatch, module, payload):
    monkeypatch.setattr(module, "requests", pytypes.SimpleNamespace(
        get=lambda *a, **k: _FakeResponse(payload),
        utils=__import__("requests").utils,
    ))


# --- tools.get_lat_long ---

def test_get_lat_long_success(monkeypatch):
    payload = {
        "status": "OK",
        "results": [
            {
                "geometry": {"location": {"lat": 40.015, "lng": -105.27}},
                "formatted_address": "Boulder, CO, USA",
            }
        ],
    }
    _patch_requests(monkeypatch, tools, payload)
    result = tools.get_lat_long("Boulder, CO")
    assert result["status"] == "ok"
    assert result["lat"] == 40.015
    assert result["lon"] == -105.27


def test_get_lat_long_not_found(monkeypatch):
    _patch_requests(monkeypatch, tools, {"status": "ZERO_RESULTS", "results": []})
    assert tools.get_lat_long("nowhere")["status"] == "error"


# --- tools.get_extended_weather_forecast ---

def test_get_extended_weather_forecast(monkeypatch):
    points = {"properties": {"forecast": "https://api.weather.gov/x/forecast"}}
    forecast = {
        "properties": {
            "periods": [
                {
                    "name": "Tonight",
                    "temperature": 45,
                    "temperatureUnit": "F",
                    "windSpeed": "10 mph",
                    "windDirection": "NW",
                    "detailedForecast": "Clear.",
                }
            ]
        }
    }
    responses = iter([_FakeResponse(points), _FakeResponse(forecast)])
    monkeypatch.setattr(tools.requests, "get", lambda *a, **k: next(responses))
    result = tools.get_extended_weather_forecast(40.0, -105.0)
    assert result["status"] == "ok"
    assert result["periods"][0]["temperature"] == "45 F"


# --- tools.get_active_weather_alerts ---

def test_get_active_weather_alerts(monkeypatch):
    payload = {
        "features": [
            {
                "properties": {
                    "event": "Winter Storm Warning",
                    "severity": "Severe",
                    "urgency": "Expected",
                    "headline": "Heavy snow",
                    "instruction": "Avoid travel.",
                }
            }
        ]
    }
    monkeypatch.setattr(tools.requests, "get", lambda *a, **k: _FakeResponse(payload))
    result = tools.get_active_weather_alerts(40.0, -105.0)
    assert result["status"] == "ok"
    assert result["alerts"][0]["event"] == "Winter Storm Warning"


# --- tools.get_evacuation_routes ---

def test_get_evacuation_routes(monkeypatch):
    payload = {
        "status": "OK",
        "routes": [
            {
                "summary": "I-4 W",
                "legs": [
                    {
                        "distance": {"text": "85 mi"},
                        "duration": {"text": "1 hour 30 mins"},
                        "start_address": "Tampa, FL",
                        "end_address": "Orlando, FL",
                        "steps": [{"html_instructions": "Head <b>east</b> on Main St"}],
                    }
                ],
            }
        ],
    }
    monkeypatch.setattr(tools.requests, "get", lambda *a, **k: _FakeResponse(payload))
    result = tools.get_evacuation_routes("Tampa, FL", "Orlando, FL")
    assert result["status"] == "ok"
    assert result["distance"] == "85 mi"
    assert "east" in result["steps"][0]


def test_get_evacuation_routes_no_route(monkeypatch):
    monkeypatch.setattr(
        tools.requests, "get", lambda *a, **k: _FakeResponse({"status": "NOT_FOUND", "routes": []})
    )
    assert tools.get_evacuation_routes("a", "b")["status"] == "error"


# --- safety.is_us_location ---

@pytest.mark.parametrize(
    "short_name,expected", [("US", True), ("GB", False)]
)
def test_is_us_location(monkeypatch, short_name, expected):
    payload = {
        "status": "OK",
        "results": [
            {"address_components": [{"types": ["country"], "short_name": short_name}]}
        ],
    }
    monkeypatch.setattr(safety.requests, "get", lambda *a, **k: _FakeResponse(payload))
    assert safety.is_us_location("somewhere") is expected


# --- safety.model_armor_flags_prompt ---

def test_model_armor_flags_prompt_match(monkeypatch):
    from google.cloud import modelarmor_v1

    fake_result = pytypes.SimpleNamespace(
        sanitization_result=pytypes.SimpleNamespace(
            filter_match_state=modelarmor_v1.FilterMatchState.MATCH_FOUND
        )
    )
    fake_client = pytypes.SimpleNamespace(
        sanitize_user_prompt=lambda request: fake_result
    )
    monkeypatch.setattr(safety, "_model_armor_client", lambda: fake_client)
    monkeypatch.setattr(config, "project_id", lambda: "test-project")
    assert safety.model_armor_flags_prompt("malicious") is True


def test_model_armor_fail_open(monkeypatch):
    def _boom():
        raise RuntimeError("service down")

    monkeypatch.setattr(safety, "_model_armor_client", _boom)
    assert safety.model_armor_flags_prompt("anything") is False


# --- safety.is_on_mission ---

@pytest.mark.parametrize(
    "verdict,expected", [("ON", True), ("OFF", False), ("MAYBE", None)]
)
def test_is_on_mission(monkeypatch, verdict, expected):
    fake_client = pytypes.SimpleNamespace(
        models=pytypes.SimpleNamespace(
            generate_content=lambda **k: pytypes.SimpleNamespace(text=verdict)
        )
    )
    monkeypatch.setattr(safety, "_genai", lambda: fake_client)
    assert safety.is_on_mission("question") is expected
