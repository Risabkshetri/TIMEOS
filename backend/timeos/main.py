"""TimeOS API entrypoint.

Additional routers are wired in as their phases land:
  Phase 3  -> timeos.api.devices, timeos.api.ingest   (done)
  Phase 4  -> timeos.api.days
  Phase 6  -> timeos.api.goals, timeos.api.feedback
  Phase 7  -> timeos.api.privacy
  Phase 8  -> timeos.api.insights
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import select

from timeos.api.devices import router as devices_router
from timeos.api.gzip_request import GZipRequestMiddleware
from timeos.api.health import router as health_router
from timeos.api.ingest import router as ingest_router
from timeos.db import async_session_factory, engine
from timeos.jobs.partitions import ensure_partitions
from timeos.jobs.seed_categories import ensure_system_categories
from timeos.models.user import User


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with engine.begin() as conn:
        await ensure_partitions(conn)
    async with async_session_factory() as session:
        user_ids = (await session.execute(select(User.id))).scalars().all()
        for user_id in user_ids:
            await ensure_system_categories(session, user_id)
    yield


app = FastAPI(title="TimeOS API", version="0.3.0", lifespan=lifespan)
app.add_middleware(GZipRequestMiddleware)

app.include_router(health_router)
app.include_router(devices_router)
app.include_router(ingest_router)
