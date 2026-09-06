from datetime import timedelta
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .database import now
from .models import User, Device
from .security import verify_key

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request):
    with request.app.state.sessions() as db:
        yield db


def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db=Depends(get_db),
):
    if not credentials:
        raise HTTPException(401, "Authentication required")
    try:
        data = jwt.decode(
            credentials.credentials,
            request.app.state.settings.jwt_secret,
            algorithms=["HS256"],
            issuer="honeychain",
            audience="honeychain-web",
            options={"require": ["exp", "sub", "iat", "iss", "aud", "ver"]},
        )
        user = db.get(User, data["sub"])
        if not user or not user.active or user.token_version != data["ver"]:
            raise ValueError()
        return user
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Invalid or expired token")


def roles(*allowed):
    def dependency(user=Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, "Role not permitted")
        return user

    return dependency


def token(user, settings):
    return jwt.encode(
        {
            "sub": user.id,
            "ver": user.token_version,
            "iat": now(),
            "exp": now() + timedelta(minutes=settings.token_minutes),
            "iss": "honeychain",
            "aud": "honeychain-web",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def device_auth(db, device_id, key):
    device = db.get(Device, device_id)
    if (
        not device
        or not device.active
        or not key
        or not verify_key(key, device.key_hash)
    ):
        raise HTTPException(401, "Invalid device credentials")
    return device
