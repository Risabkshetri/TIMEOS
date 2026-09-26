"""GET /v1/privacy/audit, GET /v1/privacy/preview/{date} — §12.2, §20.5, §38 Phase 7 output "the
Privacy dashboard page". The preview endpoint is the Definition of Done's own test: "the preview
endpoint shows a payload the owner is comfortable sending to a third party" — it runs the REAL
builder and the REAL gate, not a mocked or hand-curated example.
"""

import hashlib
import json
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from timeos.api.deps import get_current_user, get_db
from timeos.jobs.build_ai_context import build_ai_context_for_day
from timeos.models.privacy_audit_event import PrivacyAuditEvent
from timeos.models.user import User
from timeos.privacy.gate import PrivacyViolation, enforce_privacy_gate
from timeos.schemas.privacy import PrivacyAuditEventOut, PrivacyPreviewResponse

router = APIRouter(prefix="/v1/privacy", tags=["privacy"])

AUDIT_LIST_LIMIT = 200


@router.get("/audit", response_model=list[PrivacyAuditEventOut])
async def list_privacy_audit_events(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PrivacyAuditEventOut]:
    rows = (
        (
            await db.execute(
                select(PrivacyAuditEvent)
                .where(PrivacyAuditEvent.user_id == user.id)
                .order_by(PrivacyAuditEvent.occurred_at.desc())
                .limit(AUDIT_LIST_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    return [
        PrivacyAuditEventOut(
            id=row.id,
            occurred_at=row.occurred_at,
            actor=row.actor,
            allowlist_version=row.allowlist_version,
            ai_share_app_names=row.ai_share_app_names,
            field_count=row.field_count,
            outcome=row.outcome,
            rejected_fields=row.rejected_fields,
            payload_sha256=row.payload_sha256,
        )
        for row in rows
    ]


@router.get("/preview/{local_date}", response_model=PrivacyPreviewResponse)
async def preview_privacy_payload(
    local_date: date_type,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PrivacyPreviewResponse:
    context = await build_ai_context_for_day(db, user, local_date)
    ai_share_app_names = bool(user.settings.get("ai_share_app_names", False))

    try:
        payload = await enforce_privacy_gate(
            db,
            user_id=user.id,
            context=context,
            actor="privacy_preview",
            ai_share_app_names=ai_share_app_names,
        )
    except PrivacyViolation as exc:
        # The gate itself is what must never leak the content it caught — this 500 deliberately
        # carries no detail about which fields failed (that's why it's logged, not returned).
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "the privacy gate rejected this day's context — see /v1/privacy/audit",
        ) from exc

    payload_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return PrivacyPreviewResponse(
        date=local_date.isoformat(), context=payload, payload_sha256=payload_sha256
    )
