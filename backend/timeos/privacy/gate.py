"""§20.1's boundary, drawn in code: "raw_events -> analytics -> aggregates -> PrivacyGate ->
AIContext -> LLM ... no path around this." Nothing downstream of this module (i.e. `timeos.ai`,
once it exists) ever sees a payload that hasn't passed through `enforce_privacy_gate` first.

Combines §20.2's three independent layers on every call:
  1. structural isolation — enforced elsewhere, by the import-linter contract, not by this code;
  2. allowlist walk (`timeos.privacy.allowlist`) over the plain serialized dict;
  3. content scan (`timeos.privacy.scanner`) over every string leaf.
Either of (2) or (3) finding anything aborts the whole payload — partial redaction is not on offer
here; a context that fails is a context the caller must fix upstream, not patch around.

Every call writes a `privacy_audit_events` row (§20.5), success or failure — DB access is fine
here (only `timeos.ai` is barred from it), and this module sits BEFORE that boundary, not inside it.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from timeos.privacy.allowlist import ALLOWLIST_VERSION, find_disallowed_keys
from timeos.privacy.audit import record_privacy_audit_event
from timeos.privacy.scanner import scan_all_strings
from timeos.schemas.ai_context import AIContext


class PrivacyViolation(Exception):
    """Raised when a payload fails the allowlist walk and/or the content scan. `violations` maps
    each offending dotted path to the reason(s) it was rejected, for logging/debugging — never
    shown to the end user as-is, since the point of the gate is that its own failure mode must not
    leak the very content it caught."""

    def __init__(self, violations: dict[str, list[str] | str]) -> None:
        self.violations = violations
        super().__init__(f"privacy gate rejected {len(violations)} field(s)")


def _count_all_keys(node: object) -> int:
    count = 0
    if isinstance(node, dict):
        count += len(node)
        for value in node.values():
            count += _count_all_keys(value)
    elif isinstance(node, list):
        for item in node:
            count += _count_all_keys(item)
    return count


def _canonical_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


async def enforce_privacy_gate(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    context: AIContext,
    actor: str,
    ai_share_app_names: bool,
) -> dict:
    """Validates `context` and, on success, returns its plain-dict serialization — the exact
    shape that's safe to hand to an LLM or render on the Privacy preview page. Raises
    `PrivacyViolation` on any failure. Always writes an audit row first, both on success and
    failure, so the audit log is authoritative even when the caller doesn't handle the exception
    perfectly."""
    payload = context.model_dump(mode="json")

    disallowed = find_disallowed_keys(payload)
    scan_findings = scan_all_strings(payload)
    rejected_fields: dict[str, list[str] | str] = {**disallowed, **scan_findings}

    outcome = "rejected" if rejected_fields else "allowed"
    payload_sha256 = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    await record_privacy_audit_event(
        db,
        user_id=user_id,
        actor=actor,
        allowlist_version=ALLOWLIST_VERSION,
        ai_share_app_names=ai_share_app_names,
        field_count=_count_all_keys(payload),
        outcome=outcome,
        rejected_fields=sorted(rejected_fields.keys()),
        payload_sha256=payload_sha256,
    )

    if rejected_fields:
        raise PrivacyViolation(rejected_fields)

    return payload
