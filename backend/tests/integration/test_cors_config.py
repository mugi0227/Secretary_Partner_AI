from fastapi.testclient import TestClient

from main import app


def test_cors_allows_loopback_vite_origin_for_local_auth() -> None:
    client = TestClient(app)

    response = client.options(
        "/api/auth/register",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
