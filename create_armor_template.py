"""Create (or update) the strict Model Armor template used by ReadyNow!.

Codifying the policy in source makes the safety posture reproducible across
environments instead of relying on console clicks. The template enables:
  * RAI hate-speech and sexually-explicit filters at LOW_AND_ABOVE (strict)
  * RAI harassment at MEDIUM_AND_ABOVE - urgent/distressed emergency phrasing
    false-positives at LOW (a plain "evacuate to Orlando" request was flagged)
  * The RAI "dangerous content" filter at HIGH only - ReadyNow! is an
    emergency/evacuation assistant whose entire domain is danger, so a low
    threshold here blocks legitimate requests. HIGH still catches egregious
    content (weapons, self-harm how-tos).
  * Prompt-injection and jailbreak detection (the real security threat) - strict
  * Malicious-URI detection - strict
  * Sensitive-data (PII/SDP) protection - strict

Usage:
    python create_armor_template.py

Reads GOOGLE_CLOUD_PROJECT and MA_TEMPLATE_ID (default "readynow-armor") from the
environment. The template is created in us-central1 to match the agent config.
Re-run this script to update an existing template after tuning the policy.
"""

import os
import sys

from google.api_core.exceptions import Conflict
from google.cloud import modelarmor_v1

LOCATION = "us-central1"


def build_strict_template() -> modelarmor_v1.Template:
    low = modelarmor_v1.DetectionConfidenceLevel.LOW_AND_ABOVE
    medium = modelarmor_v1.DetectionConfidenceLevel.MEDIUM_AND_ABOVE
    high = modelarmor_v1.DetectionConfidenceLevel.HIGH

    # Per-filter confidence, tuned for an emergency assistant:
    #  * DANGEROUS -> HIGH: the domain is inherently about danger, so LOW blocks
    #    legitimate requests ("what's the evacuation route?").
    #  * HARASSMENT -> MEDIUM_AND_ABOVE: urgent, distressed emergency phrasing
    #    false-positives at LOW (e.g. "I need to evacuate" was flagged), so require
    #    at least medium confidence.
    #  * HATE_SPEECH / SEXUALLY_EXPLICIT -> LOW: off-mission and unlikely to false
    #    positive on emergency content, so keep strict.
    rai_confidence = {
        modelarmor_v1.RaiFilterType.HATE_SPEECH: low,
        modelarmor_v1.RaiFilterType.HARASSMENT: medium,
        modelarmor_v1.RaiFilterType.SEXUALLY_EXPLICIT: low,
        modelarmor_v1.RaiFilterType.DANGEROUS: high,
    }
    rai = modelarmor_v1.RaiFilterSettings(
        rai_filters=[
            modelarmor_v1.RaiFilterSettings.RaiFilter(
                filter_type=ft, confidence_level=level
            )
            for ft, level in rai_confidence.items()
        ]
    )

    pi_jailbreak = modelarmor_v1.PiAndJailbreakFilterSettings(
        filter_enforcement=modelarmor_v1.PiAndJailbreakFilterSettings.PiAndJailbreakFilterEnforcement.ENABLED,
        confidence_level=low,
    )

    malicious_uri = modelarmor_v1.MaliciousUriFilterSettings(
        filter_enforcement=modelarmor_v1.MaliciousUriFilterSettings.MaliciousUriFilterEnforcement.ENABLED,
    )

    sdp = modelarmor_v1.SdpFilterSettings(
        basic_config=modelarmor_v1.SdpBasicConfig(
            filter_enforcement=modelarmor_v1.SdpBasicConfig.SdpBasicConfigEnforcement.ENABLED,
        )
    )

    return modelarmor_v1.Template(
        filter_config=modelarmor_v1.FilterConfig(
            rai_settings=rai,
            pi_and_jailbreak_filter_settings=pi_jailbreak,
            malicious_uri_filter_settings=malicious_uri,
            sdp_settings=sdp,
        )
    )


def main() -> int:
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project:
        print("GOOGLE_CLOUD_PROJECT is not set.", file=sys.stderr)
        return 1
    template_id = os.environ.get("MA_TEMPLATE_ID", "readynow-armor").strip()

    client = modelarmor_v1.ModelArmorClient(
        transport="rest",
        client_options={"api_endpoint": f"modelarmor.{LOCATION}.rep.googleapis.com"},
    )
    parent = f"projects/{project}/locations/{LOCATION}"
    template_name = f"{parent}/templates/{template_id}"

    def _create():
        return client.create_template(
            request=modelarmor_v1.CreateTemplateRequest(
                parent=parent,
                template_id=template_id,
                template=build_strict_template(),
            )
        )

    try:
        created = _create()
        print(f"Created Model Armor template: {created.name}")
    except Conflict:
        # REST transport raises Conflict (HTTP 409); AlreadyExists is its gRPC
        # subclass. Delete then recreate so the tuned policy fully replaces the old.
        print(f"Template already exists, deleting: {template_name}")
        client.delete_template(
            request=modelarmor_v1.DeleteTemplateRequest(name=template_name)
        )
        created = _create()
        print(f"Recreated Model Armor template: {created.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
