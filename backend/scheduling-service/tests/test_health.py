from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_whoami():
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok"}
    body = client.get("/whoami").json()
    assert body["service"] == "scheduling-service" and body["instance"]
