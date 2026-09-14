"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §14.3: device_coverage — the "honesty engine"'s storage.

The spec calls for a GiST exclusion constraint (`EXCLUDE USING gist (device_id WITH =,
tstzrange(start_ts,end_ts) WITH &&)`) so the database itself refuses to let two overlapping
coverage intervals exist for the same device — coverage intervals are a partition of time, and an
overlap would mean double-counting `coverage_ratio`. That constraint needs the `btree_gist`
extension and can't be expressed as a SQLAlchemy column/table arg, so it's added by hand in the
migration (see the Phase 4 migration's upgrade()).
"""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from timeos.models.base import Base


class DeviceCoverage(Base):
    __tablename__ = "device_coverage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_ts: Mapped[datetime] = mapped_column(nullable=False)
    end_ts: Mapped[datetime] = mapped_column(nullable=False)
    # TRACKED|IDLE|UNOBSERVED|DEVICE_OFFLINE
    state: Mapped[str] = mapped_column(String(20), nullable=False)
