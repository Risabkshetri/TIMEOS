"""Records detected gaps in a device's seq sequence (§12.3 step 4, §31 seq_gaps_total metric).

A gap means the device's local store lost events it once had (pruned, DB corruption, or a batch
the client never resent) — recorded for observability, never silently ignored.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from timeos.models.base import Base


class SeqGap(Base):
    __tablename__ = "seq_gaps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expected_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_seq_from: Mapped[int] = mapped_column(BigInteger, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
