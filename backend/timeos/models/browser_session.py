"""docs/TIMEOS_ENGINEERING_SPEC.md §13, §11.2, §11.4, §38 Phase 9: browser_sessions.

Deliberately a SEPARATE table from `app_sessions`, not `app_sessions` rows keyed by a domain
string — a domain and an Android package are different provenance, and Phase 9's own arbitration
algorithm (`timeos.analytics.browser_arbitration`) needs to operate ONLY on browser-sourced
intervals, which is far cleaner as its own table+query than filtering `app_sessions` by a
heuristic "does this app_key look like a domain" check. Rows here are the ARBITRATED result
(post `timeos.analytics.browser_arbitration.arbitrate_browser_sessions`) — `device_id` records
which browser actually won that interval, and `browser_family` is denormalized onto the row
(rather than requiring a join through `devices`) because per-browser breakdown and the System
Health page's collector diagnostics are exactly the queries that want it directly (§11.4:
"`browser_family` is retained on `browser_sessions` so per-browser breakdown is available").

Not yet wired into `device_coverage`/`activities`/`daily_metrics` (§14.3's merge) — that
integration, including full multi-device union, is Phase 10's explicit job ("Unified Cross-Device
Timeline"), matching how Phase 4's pipeline already flags true multi-device union as deferred
until there's a real scenario to validate it against.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from timeos.models.base import Base


class BrowserSession(Base):
    __tablename__ = "browser_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    browser_family: Mapped[str] = mapped_column(String(20), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    start_ts: Mapped[datetime] = mapped_column(nullable=False)
    end_ts: Mapped[datetime] = mapped_column(nullable=False)
    duration_s: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
