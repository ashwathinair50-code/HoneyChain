import pytest
from backend.config import Settings
from backend.app import create_app
from fastapi.testclient import TestClient

def test_production_origin_guard():
    for value in ["http://localhost:8000", "https://127.0.0.1", "https://v0.app", "*"]:
        with pytest.raises(RuntimeError):
            Settings(environment="production", public_url=value, cors_origins=value).validate_deployment()
    Settings(environment="production", public_url="https://honey.example.org", cors_origins="https://honey.example.org").validate_deployment()

def test_cors_allowed_and_unrelated_origin(env):
    app, client, _ = env
    good=app.state.settings.cors_origins.split(",")[0]
    headers={"Origin":good,"Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"authorization,content-type"}
    response=client.options("/api/auth/login",headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == good
    headers["Origin"]="https://unrelated.example.org"
    response=client.options("/api/auth/login",headers=headers)
    assert "access-control-allow-origin" not in response.headers
