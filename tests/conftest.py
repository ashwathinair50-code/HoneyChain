import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.config import Settings
from backend.seed import seed


@pytest.fixture
def env(tmp_path):
    app = create_app(
        Settings(
            database_url="sqlite:///" + str(tmp_path / "test.db"),
            jwt_secret="test-only-secret-that-is-at-least-32-characters",
        )
    )
    with app.state.sessions() as db:
        credentials = seed(db, "Test-only-password!")
    with TestClient(app) as client:
        yield app, client, credentials
    app.state.engine.dispose()


def login(client, name):
    response = client.post(
        "/api/auth/login", json={"username": name, "password": "Test-only-password!"}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}
