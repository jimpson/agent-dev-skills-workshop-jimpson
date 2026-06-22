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
- **LiteLLM** - model abstraction layer
- External tools: Google Maps Geocoding API and the US National Weather Service API

## Challenges

Each notebook builds on the previous one, layering in new agentic concepts.

| Notebook | Focus |
| --- | --- |
| `challenge1_weather_agent.ipynb` | A single ADK agent that answers weather questions using custom tools (geocoding + forecast lookup). |
| `challenge2_weather_agent.ipynb` | Adds Model Armor safety checks, callbacks (before/after model and tool calls), and logging. |
| `challenge3_weather_agent.ipynb` | Composes the weather capabilities into a multi-agent workflow. |
| `challenge4_agent_workflow.ipynb` | Orchestrates multiple specialized agents (producer, screenwriter loop, script compiler, budget) into a sequential production pipeline coordinated by a root agent. |

## Key Concepts Covered

- Defining agents and equipping them with custom Python tools
- Grounding agent responses in live external data
- Safety and guardrails with Model Armor
- Lifecycle callbacks and logging for observability
- Multi-agent orchestration: loop agents, sequential pipelines, and root coordinators
- Shared session state across agents

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
