"""docs/TIMEOS_ENGINEERING_SPEC.md §13/§12.3: the server-side idempotency ledger.

One row per batch this server has ever accepted. The whole idempotent-replay algorithm hinges on
this: `INSERT ... ON CONFLICT (batch_id) DO NOTHING` — zero rows affected means this batch_id was
already processed, so the stored `response` is replayed verbatim rather than reprocessing.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class SyncBatch(Base):
    __tablename__ = "sync_batches"

    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    received_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    seq_from: Mapped[int] = mapped_column(BigInteger, nullable=False)
    seq_to: Mapped[int] = mapped_column(BigInteger, nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # accepted | rejected
