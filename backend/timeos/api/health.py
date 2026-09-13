"""Liveness/readiness endpoints. See docs/TIMEOS_ENGINEERING_SPEC.md §29 (Deployment)."""

from fastapi import APIRouter, Response

from timeos.db import check_ready

router = APIRouter(prefix="/v1/health", tags=["health"])


@router.get("/live")
async def live() -> dict:
    """Process is up. Never checks the database — that's /ready's job."""
    return {"status": "live"}


@router.get("/ready")
async def ready(response: Response) -> dict:
    """Database reachable. Docker Compose healthchecks and the deploy script poll this."""
    ok = await check_ready()
    if not ok:
        response.status_code = 503
        return {"status": "not_ready"}
    return {"status": "ready"}
