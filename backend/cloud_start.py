"""Single-instance deployment with a persistent SQLite volume."""
import os
from .app import create_app
from .config import Settings
from .models import User
from .seed import seed
from .qr_demo import ensure_qr_demo, DEMO_BATCH_ID
from fastapi.testclient import TestClient

def initialize():
    settings = Settings()
    app = create_app(settings)
    if settings.demo_mode:
        with app.state.sessions() as db:
            empty = db.query(User).first() is None
            credentials = seed(db) if empty else None
        if credentials:
            ensure_qr_demo(app, credentials)
        else:
            with TestClient(app) as client:
                response = client.get("/api/public/batches/" + DEMO_BATCH_ID)
                if response.status_code != 200 or response.json().get("status") != "VERIFIED":
                    raise RuntimeError("Existing demo database failed verification; refusing to overwrite it")
    app.state.engine.dispose()

if __name__ == "__main__":
    initialize()
    os.execvp("uvicorn", ["uvicorn", "backend.app:create_app", "--factory", "--host", "0.0.0.0", "--port", os.getenv("PORT", "8000"), "--workers", "1"])
