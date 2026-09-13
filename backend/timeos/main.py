"""TimeOS API entrypoint (Phase 0 skeleton).

Additional routers are wired in as their phases land:
  Phase 3  -> timeos.api.devices, timeos.api.ingest
  Phase 4  -> timeos.api.days
  Phase 6  -> timeos.api.goals, timeos.api.feedback
  Phase 7  -> timeos.api.privacy
  Phase 8  -> timeos.api.insights
"""

from fastapi import FastAPI

from timeos.api.health import router as health_router

app = FastAPI(title="TimeOS API", version="0.1.0")

app.include_router(health_router)
