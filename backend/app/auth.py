"""Explicit local-demo reviewer authentication. No SSO or agent self-approval."""

import hashlib
import hmac
import secrets

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, SecretStr

from app.config import get_settings
from app.errors import ApiError
from app.runtime import database

router = APIRouter(prefix="/auth")
_sessions: dict[str, str] = {}


def check_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin not in {"http://localhost:3000", "http://127.0.0.1:3000"}:
        raise ApiError(403, "ORIGIN_NOT_ALLOWED", "Use the local Operations Console")


def reviewer(request: Request) -> dict:
    check_origin(request)
    settings = get_settings()
    expected = settings.demo_reviewer_token.get_secret_value()
    token = request.headers.get("x-reviewer-token", "")
    session = request.cookies.get("proofstep_reviewer", "")
    identity = _sessions.get(hashlib.sha256(session.encode()).hexdigest()) if session else None
    if not settings.demo_mode or not expected or expected.startswith("change-me"):
        raise ApiError(
            403, "REVIEWER_NOT_CONFIGURED", "Configure local demo reviewer authentication"
        )
    if identity != settings.demo_reviewer_id and not (
        token and hmac.compare_digest(token, expected)
    ):
        raise ApiError(401, "REVIEWER_AUTH_FAILED", "Sign in with the local demo reviewer token")
    policy = database().policies.find_one({"policyId": "settlement-amendment", "synthetic": True})
    authorized = (
        policy
        and policy.get("enabled", True)
        and any(
            r["reviewerId"] == settings.demo_reviewer_id and r["role"] == policy["requiredRole"]
            for r in policy.get("reviewers", [])
        )
    )
    if not authorized:
        raise ApiError(403, "REVIEWER_NOT_AUTHORIZED", "Reviewer lacks the policy's required role")
    return {
        "reviewerId": settings.demo_reviewer_id,
        "role": policy["requiredRole"],
        "authMethod": "DEMO_TOKEN",
    }


class LoginBody(BaseModel):
    token: SecretStr


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    check_origin(request)
    settings = get_settings()
    expected = settings.demo_reviewer_token.get_secret_value()
    if (
        not settings.demo_mode
        or not expected
        or expected.startswith("change-me")
        or not hmac.compare_digest(body.token.get_secret_value(), expected)
    ):
        raise ApiError(401, "REVIEWER_AUTH_FAILED", "Invalid local demo reviewer token")
    session = secrets.token_urlsafe(32)
    _sessions[hashlib.sha256(session.encode()).hexdigest()] = settings.demo_reviewer_id
    response.set_cookie(
        "proofstep_reviewer",
        session,
        httponly=True,
        samesite="strict",
        max_age=8 * 3600,
        path="/api",
    )
    return {"reviewerId": settings.demo_reviewer_id, "authMethod": "DEMO_TOKEN"}


@router.get("/session")
def session(request: Request):
    return reviewer(request)
