"""§28: a device token can only call ingest/sync endpoints — never read data back. Phase 3 adds
no read endpoints yet, so this test asserts the exact, reviewable set of routes that accept a
device token today. Adding any new device-scoped route means updating this set deliberately —
the same guardrail philosophy as test_privacy_isolation.py's AI/data-layer boundary.
"""

from timeos.api.deps import enforce_ingest_rate_limit, get_current_device
from timeos.main import app

EXPECTED_DEVICE_SCOPED_PATHS = {
    "/v1/ingest/batch",
    "/v1/sync/state",
    "/v1/devices/token/rotate",
}


def _iter_leaf_routes(routes):
    """FastAPI (0.141+) represents each app.include_router() call as an internal
    `_IncludedRouter` wrapper (no `path`, no `routes`) around the original APIRouter, reachable
    via `.original_router.routes` — this descends through that to reach the actual APIRoute
    endpoints with a `path` and `dependant`."""
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _iter_leaf_routes(original_router.routes)
        elif hasattr(route, "path"):
            yield route


def _depends_on_device_auth(route) -> bool:
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return False
    if dependant.call in (get_current_device, enforce_ingest_rate_limit):
        return True
    targets = (get_current_device, enforce_ingest_rate_limit)
    return any(dep.call in targets for dep in dependant.dependencies)


def test_device_token_dependency_is_scoped_to_the_expected_routes():
    device_scoped_paths = {
        route.path for route in _iter_leaf_routes(app.routes) if _depends_on_device_auth(route)
    }
    assert device_scoped_paths == EXPECTED_DEVICE_SCOPED_PATHS


def test_enroll_route_does_not_require_device_auth():
    enroll_route = next(
        r for r in _iter_leaf_routes(app.routes) if r.path == "/v1/devices/enroll"
    )
    assert not _depends_on_device_auth(enroll_route)
