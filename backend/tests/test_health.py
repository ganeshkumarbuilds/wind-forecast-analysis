from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_successful_response() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200


def test_health_response_structure() -> None:
    response = client.get("/api/v1/health")

    assert response.json() == {"status": "ok"}


def test_root_returns_application_name_and_version() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"name": "WindScope API", "version": "1.0.0"}


def test_unknown_route_returns_structured_not_found() -> None:
    response = client.get("/api/v1/not-a-route")

    assert response.status_code == 404
    assert response.json() == {
        "code": "http_404",
        "message": "Not Found",
    }
