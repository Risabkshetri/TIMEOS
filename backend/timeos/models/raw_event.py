"""docs/TIMEOS_ENGINEERING_SPEC.md §13: raw_events — the append-only, private telemetry store.

Partitioned by month on ts_utc (§13, §29). Postgres requires a partitioned table's primary key to
include the partition column, hence the composite (id, ts_utc) key rather than id alone — this is
harmless for idempotency: id (event_id) is a deterministic hash that already encodes its own
timestamp (see android EventMapper.deriveEventId), so a duplicate (id, ts_utc) pair only ever
occurs when the exact same client event is re-submitted.

Alembic's autogenerate does correctly emit `PARTITION BY RANGE (ts_utc)` from this model's
`postgresql_partition_by` table arg — but it does NOT create any child partitions, and a
partitioned table with zero partitions rejects every insert. The initial partitions are created
by hand-written SQL in the migration; ongoing partitions are ensured at API startup by
timeos/jobs/partitions.py.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class RawEvent(Base):
    __tablename__ = "raw_events"
    __table_args__ = {
        "postgresql_partition_by": "RANGE (ts_utc)",
    }

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    ts_utc: Mapped[datetime] = mapped_column(primary_key=True)

    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tz_offset_min: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    tz_id: Mapped[str] = mapped_column(String(64), nullable=False)
    uptime_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    clock_suspect: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    schema_v: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
