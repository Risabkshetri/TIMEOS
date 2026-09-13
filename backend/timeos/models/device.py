"""docs/TIMEOS_ENGINEERING_SPEC.md §13: devices.

`id` is the CLIENT-generated device id (see android/app/DeviceId.kt), accepted as-is at enroll
time rather than server-assigned — every event a device has ever collected locally already
carries this id in its payload, so re-assigning a new server id would orphan that history.

Scope separation (§28): a device's token can only call ingest/sync endpoints — see
timeos/api/deps.py's get_current_device. It is never sufficient to read data back.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)  # android | desktop | browser
    browser_family: Mapped[str | None] = mapped_column(String(20), nullable=True)

    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    token_created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    token_rotated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # The token in force immediately before the current one, honored for 24h after rotation
    # (§28) so a client that hasn't yet received the new token isn't locked out mid-rotation.
    previous_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    previous_token_expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_seq: Mapped[int] = mapped_column(BigInteger, server_default="0", nullable=False)

    app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    capability_level: Mapped[str | None] = mapped_column(String(30), nullable=True)

    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
