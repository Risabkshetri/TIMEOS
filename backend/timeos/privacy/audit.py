"""§20.5: the `privacy_audit_events` writer. This module (unlike everything else under
`timeos.privacy`) touches the DB — that's fine, only `timeos.ai` is barred from data-layer access
(§20.2's structural isolation contract names `timeos.ai`, not `timeos.privacy`), and the audit
write has to happen on the same side of the gate as the data it's describing.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from timeos.models.privacy_audit_event import PrivacyAuditEvent


async def record_privacy_audit_event(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    actor: str,
    allowlist_version: str,
    ai_share_app_names: bool,
    field_count: int,
    outcome: str,
    rejected_fields: list[str],
    payload_sha256: str,
) -> PrivacyAuditEvent:
    row = PrivacyAuditEvent(
        user_id=user_id,
        actor=actor,
        allowlist_version=allowlist_version,
        ai_share_app_names=ai_share_app_names,
        field_count=field_count,
        outcome=outcome,
        rejected_fields=rejected_fields,
        payload_sha256=payload_sha256,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row
