from fastapi.testclient import TestClient

from timeos.main import app

client = TestClient(app)


def test_live():
    resp = client.get("/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "live"}
