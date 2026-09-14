"""docs/TIMEOS_ENGINEERING_SPEC.md §13: users.

A single row exists for the personal-use owner. password_hash/email stay nullable until Phase 5
builds real dashboard session auth — carrying the column now avoids a later migration that would
need to backfill a NOT NULL column on a live table.

`password_changed_at` isn't in the spec's compact §13 listing — added for Phase 5's session auth
(§28: "revoke the device first, then rotate the dashboard password" implies rotating the password
invalidates outstanding sessions). timeos.security.sessions signs a session token's issued-at
time; any token issued before this timestamp is rejected, which is what makes a password rotation
actually revoke every existing session without needing a server-side session store to clear.
"""

import uuid
from datetime import datetime

from sqlalchemy import SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), server_default="UTC", nullable=False)
    day_start_hour: Mapped[int] = mapped_column(SmallInteger, server_default="4", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    password_changed_at: Mapped[datetime | None] = mapped_column(nullable=True)
