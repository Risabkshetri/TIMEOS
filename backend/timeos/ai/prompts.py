"""§22's LLM Safety Rules, turned into the actual prompt text. Pure string construction — no DB,
no provider-specific code — from a context dict that has already passed
`timeos.privacy.gate.enforce_privacy_gate` (the caller's responsibility; this module has no way to
check that itself, since it has no gate access here — it only ever sees what it's handed).
"""

from __future__ import annotations

import json

from timeos.ai.provider import Message

PROMPT_VERSION = "1.0"

SYSTEM_PROMPT = """You are a time-usage analyst reviewing one day's already-computed, anonymised \
statistics for a single person. You are not a coach, therapist, or doctor.

Rules you must follow exactly:
1. You may use ONLY the numbers given to you in the context below. Never compute, estimate, or \
guess a number that isn't already present in the context. If you cite a number, it must be one \
you were given, verbatim.
2. Every claim you make about a pattern, cause, or behaviour must be labelled with an \
epistemic_status: FACT (a directly measured value, stated as-is), INFERENCE (a reasonable \
interpretation of measured values), or HYPOTHESIS (a plausible but unverifiable guess about \
motivation or cause). Default to INFERENCE or HYPOTHESIS — almost nothing about WHY a person did \
something is a FACT.
3. Never use medical, psychiatric, or diagnostic language (e.g. words like "disorder", \
"addiction", "ADHD", "depression", "anxiety", "diagnosis", "clinical", "pathological", \
"syndrome"). You are not qualified to make such an assessment and must not imply one.
4. Do not moralise or issue verdicts. Report findings the way an analyst reports findings, not \
the way a coach delivers a lecture. Never use words like "should have", "failed to", "bad habit", \
or similar judgemental framing.
5. If coverage_ratio is below 0.6 or unknown_ratio is above 0.3, say so explicitly in your \
summary before anything else, and keep every confidence value at or below 0.7.
6. Every insight's evidence.fields must list the exact dotted paths (e.g. \
"focus.context_switches", "categories[0].minutes") in the context you used to support that \
insight, and evidence.values must restate the exact numbers you read at those paths.
7. Respond with ONLY a single JSON object matching the schema below. No markdown, no code fences, \
no commentary before or after the JSON."""


def build_analysis_messages(context: dict, output_schema: dict) -> list[Message]:
    user_content = (
        "Here is today's context:\n\n"
        f"{json.dumps(context, indent=2)}\n\n"
        "Respond with a single JSON object matching exactly this schema "
        "(required fields, types, and array-length limits all apply):\n\n"
        f"{json.dumps(output_schema, indent=2)}"
    )
    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=user_content),
    ]


def build_repair_messages(
    context: dict, output_schema: dict, previous_output: str, validation_errors: str
) -> list[Message]:
    """§22.3: "Invalid → one repair attempt with the validation errors appended." A fresh prompt,
    not a conversation continuation — keeps the retry deterministic and independent of whatever
    the first attempt's (possibly malformed) output looked like as a chat turn."""
    messages = build_analysis_messages(context, output_schema)
    repair_notice = Message(
        role="user",
        content=(
            "Your previous response did not validate against the schema. "
            f"Previous response:\n{previous_output}\n\n"
            f"Validation errors:\n{validation_errors}\n\n"
            "Respond again with a corrected single JSON object matching the schema exactly. "
            "No markdown, no code fences, no commentary."
        ),
    )
    return [*messages, repair_notice]
