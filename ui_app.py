"""Lightweight Gradio chat UI for the ReadyNow! agent.

Connects to a deployed Agent Engine instance (by resource name) when provided,
otherwise falls back to the local ``AdkApp`` for development. ``launch_ui`` starts
the UI with ``share=True`` so a public ``*.gradio.live`` link is printed for quick
demos.

Note: Gradio share links are temporary (~72h) and route through Gradio's
infrastructure - convenient for a POC demo, not a hardened production endpoint.
For production, host the UI on Cloud Run behind your own auth.
"""

from typing import Any, Optional


def _extract_text(event: Any) -> Optional[str]:
    if isinstance(event, dict):
        content = event.get("content") or {}
        parts = content.get("parts") if isinstance(content, dict) else None
        parts = parts or event.get("parts", [])
    else:
        content = getattr(event, "content", None)
        parts = getattr(content, "parts", None) or getattr(event, "parts", [])
    for part in parts or []:
        text = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
        if text:
            return text
    return None


def _load_agent(remote_resource_name: Optional[str]):
    if remote_resource_name:
        from vertexai import agent_engines

        return agent_engines.get(remote_resource_name)
    from readynow_agent.agent import app

    return app


def launch_ui(
    remote_resource_name: Optional[str] = None,
    user_id: str = "readynow-ui-user",
    share: bool = True,
):
    """Launch the ReadyNow! chat UI and return the Gradio Blocks/ChatInterface."""

    import gradio as gr

    agent = _load_agent(remote_resource_name)
    session = agent.create_session(user_id=user_id)
    session_id = session["id"] if isinstance(session, dict) else session.id

    def respond(message: str, history) -> str:
        last_text = None
        for event in agent.stream_query(
            user_id=user_id, session_id=session_id, message=message
        ):
            text = _extract_text(event)
            if text:
                last_text = text
        return last_text or "(No response received. Check the Agent Engine logs.)"

    chat = gr.ChatInterface(
        fn=respond,
        type="messages",
        title="ReadyNow! - Emergency Preparedness Assistant",
        description=(
            "Real-time weather and disaster alerts, evacuation routes, and safety "
            "guidance for locations in the United States. For life-threatening "
            "emergencies, call 911."
        ),
        examples=[
            "What's the weather and any active alerts for Boulder, CO?",
            "I'm in Tampa, FL and need to evacuate to Orlando. What's the route?",
            "What should be in an emergency go-bag?",
        ],
    )
    chat.launch(share=share)
    return chat


if __name__ == "__main__":
    launch_ui()
