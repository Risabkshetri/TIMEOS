"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §15.3: activity_categories.

Two-level, user-extensible taxonomy stored as DATA, not code, so the user can rename or add
categories without a deploy. System categories (`is_system=True`: Idle, Unobserved, Offline,
Unknown) are seeded by migration and must never be deleted or renamed — the pipeline assumes they
always exist.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from timeos.models.base import Base


class ActivityCategory(Base):
    __tablename__ = "activity_categories"
    # Lets system-category seeding (timeos/jobs/seed_categories.py) use ON CONFLICT DO NOTHING
    # per user, so it's idempotent and safe to call on every startup like ensure_partitions().
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_activity_categories_user_id_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_categories.id", ondelete="SET NULL"), nullable=True
    )
    is_system: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    # A soft prior on how the user tends to feel about time in this category — NOT a moral
    # judgement (§15: "No app is intrinsically good or bad"). Nullable: most categories start
    # with no prior at all until the user or the pipeline has evidence.
    default_valence: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
