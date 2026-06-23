# Challenge 6 - Project ReadyNow! (FEMA Emergency Preparedness)

The capstone: a hardened, code-first FEMA Emergency Preparedness assistant.
A coordinator delegates to specialist agents, then validates and refines every
answer, with strict safety and full audit logging built in. Agent logic lives in
the `readynow_agent/` package; the notebook only orchestrates sync, deploy, and UI
launch.

[Back to the main README](../../readme.md) -
[Architecture deep-dive](../../docs/readynow_architecture.md)

## Solution architecture

### ReadyNow! agent flow

![ReadyNow! emergency preparedness agent flow](challenge6_agent_flow.png)

The second **solution architecture** diagram of the series. The
`Coordinator_Root` (`gemini-2.5-pro`) guards every input (Model Armor strict +
mission-scope + US-location checks), delegates to flash-tier specialists
(`Weather_Agent`, `News_Search_Agent`, `Routes_Agent`, `Preparedness_QA`), drafts a
grounded answer, then runs a `Response_Validation_Pipeline` where a `Critic_Agent`
checks grounding/completeness/clarity and a `Refiner_Agent` rewrites a clear, safe
`final_response`. Off-mission or unsafe requests get a polite refusal. Every
interaction is logged to Google Cloud Logging at all stages (USER_PROMPT,
TOOL_CALL, TOOL_RESULT, MODEL_RESPONSE, SAFETY_BLOCK, MISSION_REFUSAL, ERROR).

## Deployment

### Deployed agent on Agent Runtime

![ReadyNow! deployed on Agent Runtime](agent-deployment.png)

The `ReadyNow! Emergency Assistant` running on Agent Runtime, deployed via
`deploy_readynow.py` with version-pinned requirements to avoid build-vs-runtime
mismatches.

### Deployed-agent test bed

![Test bed against the deployed agent](test-bed-deployed-agent.png)

The `test_deployed.py` smoke test calls `ask_remote` against the live agent with
several prompts - weather/alerts, evacuation routing, go-bag, and a prompt-injection
attempt - streaming `Coordinator_Root` events and the validated final answer.

## Gradio chat UI

### Landing screen

![ReadyNow! Gradio UI landing screen](agent-ui-gradio.png)

The lightweight Gradio `ChatInterface` (`ui_app.py`) wired to the deployed agent,
launched with a public share link, with example emergency prompts.

### Sample response

![ReadyNow! Gradio UI evacuation response](agent-ui-gradio-response.png)

A live response to "I'm in Tampa, FL and need to evacuate to Orlando. What's the
route?" - leading with official sources (FL511, FDEM), evacuation prep, and the
standard driving route, with safety caveats.

## Grounded responses (notebook runs)

### Weather and active alerts

![Boulder CO conditions and alerts](conditions.png)

Safety information for Boulder, CO grounded in live US National Weather Service
data: an Air Quality (smoke) alert and severe thunderstorm risk, each with concrete
"what to do" guidance.

### Wildfire status

![California wildfire conditions](conditons-fire.png)

A wildfire-conditions answer with a live California Wildfire Status snapshot
attributed to CAL FIRE, plus guidance on official alert sources and personal safety.

### Evacuation route

![Tampa to Orlando evacuation directions](directions.png)

A grounded evacuation route (Tampa to Orlando via I-4 East, ~85 miles) with
emergency caveats and a reminder to follow official instructions.

### Emergency go-bag

![Emergency go-bag checklist](go-bag.png)

A preparedness checklist grounded in Ready.gov and American Red Cross guidance,
organized into survival basics, health/hygiene, and tools/safety.
