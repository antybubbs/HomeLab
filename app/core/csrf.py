import secrets
from fastapi import HTTPException, Request, status

CSRF_SESSION_KEY = "csrf_token"


def csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def csrf_context(request: Request) -> dict[str, str]:
    return {"csrf_token": csrf_token(request)}


def validate_csrf_token(request: Request, submitted_token: str | None) -> None:
    expected_token = request.session.get(CSRF_SESSION_KEY)
    if not expected_token or not submitted_token or not secrets.compare_digest(expected_token, submitted_token):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid form token")
