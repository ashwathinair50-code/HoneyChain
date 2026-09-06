from collections import defaultdict, deque
import time, asyncio, threading
from .scheduler import lifespan
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from .config import Settings
from .database import Base, connect
from . import models
from .auth import get_db, current_user, token
from .security import verify_password, hash_password


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


def create_app(settings=None):
    settings = settings or Settings()
    settings.validate_deployment()
    if len(settings.jwt_secret) < 32:
        raise RuntimeError(
            "Set JWT_SECRET to at least 32 random characters in .env; see README"
        )
    engine, sessions = connect(settings.database_url)
    Base.metadata.create_all(engine)
    app = FastAPI(title="HoneyChain API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessions = sessions
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[x.strip().rstrip("/") for x in settings.cors_origins.split(",")],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-Device-Key"],
    )
    app.state.write_lock = threading.Lock()

    @app.middleware("http")
    async def serialize_local_requests(request, call_next):
        length = request.headers.get("content-length", "0")
        if not length.isdigit() or int(length) > 300000:
            return JSONResponse(
                status_code=413, content={"error": {"message": "Request too large"}}
            )
        await asyncio.to_thread(app.state.write_lock.acquire)
        try:
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "same-origin"
            response.headers["X-Frame-Options"] = "DENY"
            return response
        finally:
            app.state.write_lock.release()

    attempts = defaultdict(deque)
    dummy = hash_password("dummy-authentication-comparison")

    @app.exception_handler(HTTPException)
    async def error(request, exc):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.status_code, "message": exc.detail}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        details = [
            {
                "field": ".".join(str(x) for x in e["loc"]),
                "message": e["msg"],
                "type": e["type"],
            }
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": 422,
                    "message": "Validation failed",
                    "details": details,
                }
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_conflict(request, exc):
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": 409,
                    "message": "Conflicting record; reload and retry",
                }
            },
        )

    @app.exception_handler(OperationalError)
    async def write_conflict(request, exc):
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": 503,
                    "message": "Database temporarily unavailable; retry the same operation",
                }
            },
        )

    @app.post("/api/auth/login")
    def login(body: Login, request: Request, db=Depends(get_db)):
        key = request.client.host if request.client else "unknown"
        queue = attempts[key]
        cutoff = time.monotonic() - 60
        while queue and queue[0] < cutoff:
            queue.popleft()
        if len(queue) >= 30:
            raise HTTPException(429, "Too many login attempts; wait one minute")
        queue.append(time.monotonic())
        user = db.scalar(
            select(models.User).where(models.User.username == body.username)
        )
        demo = db.get(models.DemoAccount, body.username) if settings.demo_mode else None
        if demo:
            user = db.get(models.User, demo.user_id)
        valid = verify_password(body.password, demo.password_hash if demo else (user.password_hash if user else dummy))
        if not user or not user.active or not valid:
            raise HTTPException(401, "Invalid credentials")
        return {
            "access_token": token(user, settings),
            "token_type": "bearer",
            "expires_in": settings.token_minutes * 60,
            "user": user_view(user),
        }

    @app.get("/api/auth/me")
    def me(user=Depends(current_user)):
        return user_view(user)

    @app.get("/api/health")
    def health(db=Depends(get_db)):
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "service": "HoneyChain",
            "intelligence": "EXPLAINABLE RULE-BASED DECISION SUPPORT",
        }

    from .telemetry_api import router

    app.include_router(router)
    from .telemetry_engine import evaluate

    app.state.evaluate = evaluate
    from .kvic_api import router as kvic_router

    app.include_router(kvic_router)
    from .batch_api import router as batch_router

    app.include_router(batch_router)
    from .lab_api import router as lab_router

    app.include_router(lab_router)
    from .release_api import router as release_router

    app.include_router(release_router)
    from fastapi.responses import FileResponse
    from .config import ROOT

    @app.get('/api/config')
    def public_config():
        if not settings.demo_mode: return {'demo_mode': False}
        from .demo_accounts import public_accounts
        return {'demo_mode': True, 'demo_accounts': public_accounts(), 'demo_batch_id': 'HC-MH-NAS-2026-00184'}

    @app.get('/verify', include_in_schema=False)
    @app.get("/", include_in_schema=False)
    def frontend():
        return FileResponse(ROOT / "frontend" / "index.html")

    return app


def user_view(user):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "display_name": user.display_name,
    }
