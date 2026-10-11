import secrets
from collections.abc import Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.services.providers import PriceProvider, get_provider

bearer = HTTPBearer(auto_error=False)


def require_admin(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    """Protects write routes. Expects `Authorization: Bearer <ADMIN_TOKEN>`."""
    expected = get_settings().admin_token
    if not expected:
        # Fail closed: with no token configured, nobody can write.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ADMIN_TOKEN is not configured")
    # compare_digest takes the same time whether the first or last character differs,
    # so response timing can't be used to guess the token.
    if creds is None or not secrets.compare_digest(creds.credentials, expected):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid or missing admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def price_provider() -> Iterator[PriceProvider]:
    with get_provider() as provider:
        yield provider
