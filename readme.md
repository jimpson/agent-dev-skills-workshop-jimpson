# Google Agentic AI Challenge Lab Series

This repository contains my solutions to a Google challenge lab series focused on
building agentic AI applications. The challenges progressively introduce the core
concepts of agent development, from a single tool-using agent to orchestrated
multi-agent workflows.

## Tech Stack

- **Google Agent Development Kit (ADK)** - the agent framework used throughout
- **Vertex AI / Gemini** - the models powering the agents (e.g. `gemini-2.5-flash`)
- **Google Cloud Agent Engines** - runtime for deploying and running agents
- **Model Armor** - safety guardrails for agent inputs and outputs
- **Google Cloud Logging** - structured audit trail for ReadyNow! (Challenge 6)
- **Gradio** - lightweight chat UI for the deployed ReadyNow! agent
- **LiteLLM** - model abstraction layer
- External tools: Google Maps Geocoding/Directions APIs and the US National Weather Service API

## Challenges

Each notebook builds on the previous one, layering in new agentic concepts.

| Notebook | Focus |
| --- | --- |
| `challenge1_weather_agent.ipynb` | A single ADK agent that answers weather questions using custom tools (geocoding + forecast lookup). |
| `challenge2_weather_agent.ipynb` | Adds Model Armor safety checks, callbacks (before/after model and tool calls), and logging. |
| `challenge3_weather_agent.ipynb` | Composes the weather capabilities into a multi-agent workflow. |
| `challenge4_agent_workflow.ipynb` | Orchestrates multiple specialized agents (producer, screenwriter loop, script compiler, budget) into a sequential production pipeline coordinated by a root agent. |
| `challenge5_weather_agent.ipynb` | Deploys the challenge 3 multi-agent weather system to Agent Platform via `agent_engines.create()`. Agent logic lives in the `weather_agent/` package. |
| `challenge6_readynow.ipynb` | Project ReadyNow! - a hardened FEMA Emergency Preparedness assistant. A thin notebook that syncs the repo, deploys the `readynow_agent/` package to Agent Platform, and launches a Gradio chat UI. All agent logic is code-first in `readynow_agent/`. |

## Deployable Agent Package

Challenge 5 uses a modular layout so the agent can be tested locally and deployed without cloudpickle fragility:

```text
weather_agent/
├── __init__.py
├── agent.py
├── requirements.txt
└── .env.example
```

The notebook imports `root_agent` and `app` from `weather_agent`, tests locally with `AdkApp`, then deploys with `extra_packages=["weather_agent"]`.

## Challenge 6: Project ReadyNow! (FEMA)

The capstone case study is a hardened, production-minded FEMA Emergency
Preparedness assistant. Agent logic is fully code-first in the `readynow_agent/`
package; the notebook only orchestrates sync, deploy, and UI launch.

```text
readynow_agent/
├── __init__.py
├── config.py            # env handling, model tiers, low-temp generation config
├── logging_config.py    # structured Cloud Logging + audit() helper
├── tools.py             # geocoding, NWS forecast + active alerts, Maps routes
├── safety.py            # Model Armor (strict), mission scope, US-location checks
├── callbacks.py         # before/after model + tool logging and validation
├── agent.py             # specialists, Critic+Refiner pipeline, root coordinator
├── requirements.txt
└── .env.example

create_armor_template.py # codifies the strict readynow-armor Model Armor template
deploy_readynow.py       # agent_engines.create() with version-pinned requirements
run_local_demo.py        # local scenario tests (the rubric's test code)
test_deployed.py         # smoke test against the deployed Agent Engine
ui_app.py                # lightweight Gradio chat UI with a public share link
tests/test_units.py      # unit tests for tools + safety (externals mocked)
docs/readynow_architecture.md  # architecture diagram + design
```

Highlights: tiered models (pro for orchestration/validation, flash for
specialists), strict Model Armor on every agent input and output, a Critic +
Refiner validation pipeline to suppress hallucinations, structured audit logging
at all lifecycle stages, and deploy-time version pinning to avoid build-vs-runtime
mismatches. See `docs/readynow_architecture.md` for details.

## Key Concepts Covered

- Defining agents and equipping them with custom Python tools
- Grounding agent responses in live external data
- Safety and guardrails with Model Armor
- Lifecycle callbacks and logging for observability
- Multi-agent orchestration: loop agents, sequential pipelines, and root coordinators
- Shared session state across agents
- Agent deployment to Agent Platform with `agent_engines.create()`

## Running the Notebooks

These notebooks are designed to run in an environment with access to Google Cloud
and Vertex AI (such as Colab Enterprise or a Vertex AI Workbench instance). Each
notebook:

1. Installs the required packages and restarts the kernel.
2. Reads the active project from the `GOOGLE_CLOUD_PROJECT` environment variable.
3. Initializes Vertex AI in the `us-central1` region.
4. Defines the agents and tools, then runs them against sample prompts.

> Note: API keys and project identifiers should be supplied through your own
> environment and credentials rather than committed to source control.
