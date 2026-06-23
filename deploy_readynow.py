"""Deploy the ReadyNow! agent to Agent Platform (Agent Engine).

Version parity (lesson from Challenge 5): the deployed runtime must use the SAME
package versions as the build/Colab environment, or imports drift and the agent
fails at runtime. We read the installed versions here via importlib.metadata and
pin every deployed requirement to match. The notebook imports
``pinned_requirements()`` instead of re-listing versions, so there is a single
source of truth and no drift.

Usage (from the repo root, after setting env + vertexai.init):
    import deploy_readynow
    remote_agent = deploy_readynow.deploy()
    print(remote_agent.resource_name)
"""

import importlib.metadata as _md
import os
from typing import List

# Packages whose versions are pinned to the build environment for parity.
# gradio is intentionally excluded: the UI runs in the notebook/build env, not
# inside the deployed Agent Engine runtime.
_PINNED = {
    "google-adk": "google-adk",
    "google-cloud-aiplatform[adk,agent_engines]": "google-cloud-aiplatform",
    "requests": "requests",
    "google-cloud-modelarmor": "google-cloud-modelarmor",
    "google-cloud-logging": "google-cloud-logging",
}


def pinned_requirements() -> List[str]:
    """Return deployed requirements pinned to the installed build-env versions."""

    pinned = []
    for spec, dist in _PINNED.items():
        try:
            pinned.append(f"{spec}=={_md.version(dist)}")
        except _md.PackageNotFoundError:
            # Not installed locally (e.g. extra not resolvable by name): ship unpinned.
            pinned.append(spec)
    return pinned


def deploy(display_name: str = "ReadyNow! Emergency Assistant"):
    """Create the remote Agent Engine deployment and return the remote agent."""

    from vertexai import agent_engines

    from readynow_agent.agent import app

    requirements = pinned_requirements()
    print("Pinning deployed runtime to:")
    for req in requirements:
        print(f"  {req}")

    env_vars = {
        "MAPS_API_KEY": os.environ["MAPS_API_KEY"],
        "MA_TEMPLATE_ID": os.environ.get("MA_TEMPLATE_ID", "readynow-armor"),
        "GOOGLE_GENAI_USE_VERTEXAI": "True",
        "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
    }

    # Do NOT pass GOOGLE_CLOUD_PROJECT / GOOGLE_CLOUD_LOCATION (reserved by Agent Engine).
    remote_agent = agent_engines.create(
        app,
        display_name=display_name,
        requirements=requirements,
        extra_packages=["readynow_agent"],
        env_vars=env_vars,
    )
    print("Deployed:", remote_agent.resource_name)
    return remote_agent


if __name__ == "__main__":
    deploy()
