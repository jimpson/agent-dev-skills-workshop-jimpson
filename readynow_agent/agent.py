"""ReadyNow! - FEMA Emergency Preparedness multi-agent system.

Architecture:
  Coordinator_Root (pro)
    - specialists (flash, used as tools so the root keeps control):
        Weather_Agent, News_Search_Agent, Evacuation_Routes_Agent, Preparedness_QA_Agent
    - Response_Validation_Pipeline (pro, Sequential): Critic -> Refiner
  The root gathers facts from specialists, drafts an answer, runs it through the
  validation pipeline (validate + refine), then returns the refined answer.
"""

from google.adk.agents import Agent, SequentialAgent
from google.adk.tools import agent_tool, google_search
from google.adk.tools.tool_context import ToolContext
from vertexai.preview.reasoning_engines import AdkApp

from . import config
from .callbacks import (
    log_model_response,
    log_tool_call,
    log_tool_result,
    root_before_model,
    specialist_before_model,
    weather_before_model,
)
from .tools import (
    get_active_weather_alerts,
    get_evacuation_routes,
    get_extended_weather_forecast,
    get_lat_long,
)

_GROUNDING_RULES = (
    "Only state facts returned by your tools. Never invent data, numbers, routes, "
    "or alerts. If a tool returns an error or no data, say so plainly. Always name "
    "your source (US National Weather Service, Google Maps, or web search)."
)

weather_agent = Agent(
    name="Weather_Agent",
    model=config.GEMINI_FLASH,
    description="Provides US weather forecasts and active NWS alerts for a location.",
    instruction=(
        "You are the weather specialist for ReadyNow!. Given a place, call "
        "get_lat_long, then get_extended_weather_forecast and "
        "get_active_weather_alerts. Summarize current conditions and clearly call "
        "out any active warnings, watches, or advisories with their instructions. "
        f"{_GROUNDING_RULES}"
    ),
    tools=[get_lat_long, get_extended_weather_forecast, get_active_weather_alerts],
    generate_content_config=config.GROUNDED_CONFIG,
    before_model_callback=weather_before_model,
    after_model_callback=log_model_response,
    before_tool_callback=log_tool_call,
    after_tool_callback=log_tool_result,
)

news_search_agent = Agent(
    name="News_Search_Agent",
    model=config.GEMINI_FLASH,
    description="Finds real-time news and disaster alerts using Google Search.",
    instruction=(
        "You are the news and real-time alerts specialist for ReadyNow!. Use "
        "Google Search to find current, authoritative information about disasters, "
        "emergencies, and official guidance. Prefer official sources (FEMA, NWS, "
        "local government). Summarize concisely and cite the sources you used. "
        f"{_GROUNDING_RULES}"
    ),
    tools=[google_search],
    generate_content_config=config.GROUNDED_CONFIG,
    before_model_callback=specialist_before_model,
    after_model_callback=log_model_response,
)

routes_agent = Agent(
    name="Evacuation_Routes_Agent",
    model=config.GEMINI_FLASH,
    description="Provides driving routes toward safety using the Google Maps API.",
    instruction=(
        "You are the evacuation routing specialist for ReadyNow!. Given a current "
        "location and a safe destination (a shelter, city, or address), call "
        "get_evacuation_routes to produce clear driving directions, distance, and "
        "estimated time. If the destination is unclear, ask the user to name a safe "
        "place to head toward. "
        f"{_GROUNDING_RULES}"
    ),
    tools=[get_lat_long, get_evacuation_routes],
    generate_content_config=config.GROUNDED_CONFIG,
    before_model_callback=specialist_before_model,
    after_model_callback=log_model_response,
    before_tool_callback=log_tool_call,
    after_tool_callback=log_tool_result,
)

preparedness_agent = Agent(
    name="Preparedness_QA_Agent",
    model=config.GEMINI_FLASH,
    description="Answers emergency preparedness and safety questions, grounded in search.",
    instruction=(
        "You are the emergency preparedness specialist for ReadyNow!. Answer "
        "questions about staying safe before, during, and after disasters (kits, "
        "plans, sheltering, evacuation readiness). Use Google Search to ground your "
        "answers in authoritative guidance (FEMA Ready.gov, NWS, Red Cross) and "
        "cite sources. Keep advice practical and easy to follow. "
        f"{_GROUNDING_RULES}"
    ),
    tools=[google_search],
    generate_content_config=config.GROUNDED_CONFIG,
    before_model_callback=specialist_before_model,
    after_model_callback=log_model_response,
)

critic_agent = Agent(
    name="Critic_Agent",
    model=config.GEMINI_PRO,
    description="Validates a draft emergency response for grounding, completeness, and clarity.",
    instruction=(
        "You are a meticulous reviewer of emergency-response drafts. Review the "
        "draft answer provided to you and produce a short, bulleted critique that "
        "flags: (1) any claim that appears speculative or not clearly supported by "
        "cited data, (2) missing critical safety information, (3) unclear or "
        "jargon-heavy wording, and (4) whether a 'call 911 for life-threatening "
        "emergencies' disclaimer is present. If the draft is already excellent, say "
        "so. Output ONLY the critique."
    ),
    generate_content_config=config.GROUNDED_CONFIG,
    after_model_callback=log_model_response,
    output_key="critique",
)

refiner_agent = Agent(
    name="Refiner_Agent",
    model=config.GEMINI_PRO,
    description="Rewrites the draft into a clear, safe, well-structured final answer.",
    instruction=(
        "You are an expert emergency communications editor. Using the draft answer "
        "and the critique above, rewrite the response so it is accurate, complete, "
        "and written in plain language a stressed person can follow quickly. Remove "
        "or hedge any claim the critique flagged as unsupported. Keep cited sources. "
        "End with: 'For life-threatening emergencies, call 911.' Output ONLY the "
        "final answer."
    ),
    generate_content_config=config.GROUNDED_CONFIG,
    after_model_callback=log_model_response,
    output_key="final_response",
)

response_validation_pipeline = SequentialAgent(
    name="Response_Validation_Pipeline",
    description="Validates then refines a draft answer (Critic -> Refiner).",
    sub_agents=[critic_agent, refiner_agent],
)


def get_final_response(tool_context: ToolContext) -> dict:
    """Retrieve the validated, refined final answer from session state.

    Returns:
        dict: {"final_response": str} the refined answer produced by the pipeline.
    """

    return {"final_response": tool_context.state.get("final_response", "")}


root_agent = Agent(
    name="Coordinator_Root",
    model=config.GEMINI_PRO,
    description=(
        "ReadyNow!, FEMA's emergency preparedness assistant. Coordinates weather, "
        "news, evacuation routing, and preparedness specialists, then validates and "
        "refines every answer."
    ),
    instruction="""You are ReadyNow!, FEMA's emergency preparedness assistant. Your mission is to
help people stay safe during disasters with real-time weather and news alerts,
evacuation routes, and preparedness guidance.

Follow this workflow for every user request:
1. If the user is greeting you or asking what you can do, briefly explain your
   capabilities (weather/alerts, real-time news, evacuation routes, preparedness
   guidance) and invite their question. Do NOT call tools in this case.
2. Otherwise, gather the facts you need by calling the appropriate specialist tools:
   - 'Weather_Agent' for forecasts and active weather alerts for a place.
   - 'News_Search_Agent' for real-time news and official disaster updates.
   - 'Evacuation_Routes_Agent' for driving routes toward a safe destination.
   - 'Preparedness_QA_Agent' for safety/preparedness questions.
   You may call more than one specialist when a request spans topics.
3. Compose a DRAFT answer using ONLY the information the specialists returned. Never
   invent facts. Name your sources.
4. Call 'Response_Validation_Pipeline', passing your full draft answer, to validate
   and refine it.
5. Call 'get_final_response' to retrieve the refined answer.
6. Return the refined final answer to the user, verbatim.

Always be calm, clear, and reassuring.""",
    tools=[
        agent_tool.AgentTool(agent=weather_agent),
        agent_tool.AgentTool(agent=news_search_agent),
        agent_tool.AgentTool(agent=routes_agent),
        agent_tool.AgentTool(agent=preparedness_agent),
        agent_tool.AgentTool(agent=response_validation_pipeline),
        get_final_response,
    ],
    generate_content_config=config.GROUNDED_CONFIG,
    before_model_callback=root_before_model,
    after_model_callback=log_model_response,
    before_tool_callback=log_tool_call,
    after_tool_callback=log_tool_result,
)

app = AdkApp(agent=root_agent, enable_tracing=True)
