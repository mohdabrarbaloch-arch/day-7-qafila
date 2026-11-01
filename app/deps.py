"""Shared FastAPI dependencies: current user, role gates, rate limiting."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import Role, User
from .security import decode_access_token

settings = get_settings()
bearer = HTTPBearer(auto_error=False)

_ROLE_RANK = {Role.viewer: 0, Role.operator: 1, Role.admin: 2}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
    except Exception:  # noqa: BLE001 - any decode failure is a 401
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists."
        )
    return user


def require_role(minimum: Role):
    """Dependency factory: 403 unless the caller's role is at least `minimum`."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if _ROLE_RANK[user.role] < _ROLE_RANK[minimum]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires '{minimum.value}' role or higher.",
            )
        return user

    return _guard


class RateLimiter:
    """Fixed-window limiter, in-process.

    Honest limitation: state is per-worker, so N uvicorn workers allow N times
    the configured rate. Fine for a single container; swap for Redis when you
    scale out. Documented in docs/usage.md rather than hidden.
    """

    def __init__(self, limit_per_minute: int) -> None:
        self.limit = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = time.monotonic()
        window = self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self.limit:
            retry_after = max(1, int(60 - (now - window[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit of {self.limit}/min exceeded.",
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)


limiter = RateLimiter(settings.rate_limit_per_minute)


def rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    limiter.check(client)
