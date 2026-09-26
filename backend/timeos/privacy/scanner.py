"""§20.2's third enforcement layer: "content scanning". Scans every string value in a payload for
shapes that indicate a leak slipped through the schema/allowlist layers regardless of which field
it's in — this is deliberately field-agnostic (the whole point of defence in depth is not trusting
"this field is supposed to be safe").

Pure functions, no DB, no imports beyond the standard library — importable from `timeos.ai` under
§20.2's structural isolation contract.
"""

from __future__ import annotations

import math
import re
from collections import Counter

MAX_FREE_TEXT = 500

_URL_SCHEME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://")
_DOMAIN_RE = re.compile(r"\b[a-zA-Z0-9-]+\.(?:com|org|net|io|dev|co|app|gov|edu)\b", re.IGNORECASE)
_LONG_DIGIT_RUN_RE = re.compile(r"\d{7,}")
_PATH_SEPARATOR_RE = re.compile(r"[/\\]")
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/_=\-]{32,}")

HIGH_ENTROPY_MIN_LENGTH = 32
HIGH_ENTROPY_THRESHOLD = 3.5


def _shannon_entropy(token: str) -> float:
    counts = Counter(token)
    length = len(token)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def scan_string(value: str) -> list[str]:
    """Returns every violation class `value` trips, or `[]` if it's clean. Multiple classes can
    fire on the same string (e.g. a URL is also a path-separator hit) — that's intentional; the
    caller only needs to know whether the list is empty, not pick one reason."""
    violations: list[str] = []

    if len(value) > MAX_FREE_TEXT:
        violations.append("too_long")
    if _URL_SCHEME_RE.search(value) or _DOMAIN_RE.search(value):
        violations.append("url")
    if "@" in value:
        violations.append("email_shaped")
    if _LONG_DIGIT_RUN_RE.search(value):
        violations.append("long_digit_run")
    if _PATH_SEPARATOR_RE.search(value):
        violations.append("path_separator")
    for token in _TOKEN_RE.findall(value):
        if _shannon_entropy(token) > HIGH_ENTROPY_THRESHOLD:
            violations.append("high_entropy_token")
            break

    return violations


def scan_all_strings(node: object) -> dict[str, list[str]]:
    """Walks an arbitrary JSON-shaped structure (dict/list/scalar — what `AIContext.model_dump()`
    produces) and returns {dotted_path: [violation classes]} for every string leaf that fails
    `scan_string`. An empty dict means the whole payload is clean."""
    findings: dict[str, list[str]] = {}
    _walk(node, "", findings)
    return findings


def _walk(node: object, path: str, findings: dict[str, list[str]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            _walk(value, f"{path}.{key}" if path else str(key), findings)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk(item, f"{path}[{index}]", findings)
    elif isinstance(node, str):
        violations = scan_string(node)
        if violations:
            findings[path] = violations
