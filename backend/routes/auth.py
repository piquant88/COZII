"""Auth routes — Cozii-owned, no Emergent dependencies."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode, quote
import secrets
import logging

import httpx
import jwt as pyjwt
from fastapi import HTTPException, Depends, Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse

from core import (
    app, api_router, db, logger,
    now_utc, hash_password, verify_password,
    gen_id, gen_session_token,
    get_current_user,
    SESSION_DURATION_DAYS,
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_OAUTH_REDIRECT_URI,
    GOOGLE_AUTH_ENDPOINT, GOOGLE_TOKEN_ENDPOINT, GOOGLE_USERINFO_ENDPOINT,
)
# Pydantic models are re-exported through `models` for convenience.
from models import *  # noqa: F401,F403


# =========================
# Email / password
# =========================
@api_router.post("/auth/register", response_model=AuthResponse)
async def register(body: RegisterRequest):
    email = body.email.lower().strip()
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    user_id = gen_id("user")
    user_doc = {
        "user_id": user_id,
        "email": email,
        "name": body.name.strip(),
        "picture": None,
        "password_hash": hash_password(body.password),
        "auth_provider": "email",
        "created_at": now_utc(),
    }
    await db.users.insert_one(user_doc)

    token = gen_session_token()
    await db.user_sessions.insert_one({
        "session_token": token,
        "user_id": user_id,
        "expires_at": now_utc() + timedelta(days=SESSION_DURATION_DAYS),
        "created_at": now_utc(),
    })
    user_public = {k: v for k, v in user_doc.items() if k != "password_hash"}
    return AuthResponse(token=token, user=User(**user_public))


@api_router.post("/auth/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    email = body.email.lower().strip()
    user_doc = await db.users.find_one({"email": email}, {"_id": 0})
    if not user_doc or not user_doc.get("password_hash"):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, user_doc["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = gen_session_token()
    await db.user_sessions.insert_one({
        "session_token": token,
        "user_id": user_doc["user_id"],
        "expires_at": now_utc() + timedelta(days=SESSION_DURATION_DAYS),
        "created_at": now_utc(),
    })
    user_public = {k: v for k, v in user_doc.items() if k != "password_hash"}
    return AuthResponse(token=token, user=User(**user_public))


# =========================
# Google OAuth (Cozii-owned)
#
# Flow:
#   1. Client opens GET /auth/google/start?redirect=<deeplink>
#      We stash {state -> redirect} and 302 to Google.
#   2. Google calls back GET /auth/google/callback?code=...&state=...
#      We exchange code for an id_token + userinfo, upsert the Cozii user,
#      create a Cozii session, stash a SHORT one-shot ticket
#      {short_id -> session_token}, then 302 to <deeplink>#session_id=<short_id>.
#   3. Client calls POST /api/auth/google-session { session_id: <short_id> }
#      We redeem the ticket (single-use) and return {token, user}.
# =========================

OAUTH_STATE_TTL_MIN = 10
OAUTH_TICKET_TTL_MIN = 5


def _safe_redirect(target: Optional[str]) -> str:
    """Only allow custom-scheme deep links or known Cozii origins."""
    if not target:
        return "cozii://auth-callback"
    t = target.strip()
    allowed_prefixes = (
        "cozii://",
        "exp://",                                 # Expo Go dev
        "https://cozii.onrender.com",             # web origin (prod)
        "http://localhost",                        # local dev
    )
    if any(t.startswith(p) for p in allowed_prefixes):
        return t
    return "cozii://auth-callback"


#@app.get("/auth/google/start")
@api_router.get("/auth/google/start")
async def google_oauth_start(redirect: Optional[str] = None):
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return HTMLResponse(
            "<h3>Google sign-in not configured</h3>"
            "<p>GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing on the server.</p>",
            status_code=503,
        )

    deeplink = _safe_redirect(redirect)
    state = secrets.token_urlsafe(24)
    await db.oauth_states.insert_one({
        "state": state,
        "redirect": deeplink,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(minutes=OAUTH_STATE_TTL_MIN),
    })

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
        "include_granted_scopes": "true",
    }
    url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


def _bounce_with_error(deeplink: str, msg: str) -> RedirectResponse:
    sep = "&" if "?" in deeplink else "?"
    return RedirectResponse(f"{deeplink}{sep}auth_error={quote(msg)}", status_code=302)


#@app.get("/auth/google/callback")
@api_router.get("/auth/google/callback")
async def google_oauth_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    # Look up state first so we always know where to redirect on errors.
    record = None
    if state:
        record = await db.oauth_states.find_one({"state": state}, {"_id": 0})
        # one-shot
        await db.oauth_states.delete_one({"state": state})

    deeplink = _safe_redirect(record.get("redirect") if record else None)

    if error:
        return _bounce_with_error(deeplink, error)
    if not record:
        return _bounce_with_error(deeplink, "invalid_or_expired_state")
    if not code:
        return _bounce_with_error(deeplink, "missing_code")

    # Expire stale states defensively
    exp = record.get("expires_at")
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now_utc():
            return _bounce_with_error(deeplink, "state_expired")

    # ----- Exchange code for tokens -----
    try:
        async with httpx.AsyncClient(timeout=15) as hc:
            tok_res = await hc.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": GOOGLE_CLIENT_ID,
                    "client_secret": GOOGLE_CLIENT_SECRET,
                    "redirect_uri": GOOGLE_OAUTH_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
    except Exception as e:
        logger.exception("Google token exchange network error")
        return _bounce_with_error(deeplink, f"token_exchange_network_error:{e}")

    if tok_res.status_code != 200:
        logger.warning(f"Google token exchange failed: {tok_res.status_code} {tok_res.text[:200]}")
        return _bounce_with_error(deeplink, f"token_exchange_failed_{tok_res.status_code}")

    tok = tok_res.json() or {}
    id_token = tok.get("id_token")
    access_token = tok.get("access_token")

    # ----- Get profile (prefer id_token, fall back to userinfo) -----
    profile: Dict[str, Any] = {}
    if id_token:
        try:
            # Signature already verified by Google in this code-grant flow over HTTPS;
            # we just decode the payload claims.
            profile = pyjwt.decode(id_token, options={"verify_signature": False}) or {}
        except Exception:
            profile = {}
    if not profile.get("email") and access_token:
        try:
            async with httpx.AsyncClient(timeout=10) as hc:
                ui = await hc.get(
                    GOOGLE_USERINFO_ENDPOINT,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if ui.status_code == 200:
                profile = ui.json() or {}
        except Exception:
            logger.exception("Google userinfo lookup failed")

    email = (profile.get("email") or "").lower().strip()
    if not email:
        return _bounce_with_error(deeplink, "no_email_from_google")

    name = (profile.get("name") or email.split("@")[0]).strip()
    picture = profile.get("picture")

    # ----- Upsert user -----
    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "name": name,
                "picture": picture,
                "auth_provider": existing.get("auth_provider") or "google",
            }},
        )
    else:
        user_id = gen_id("user")
        await db.users.insert_one({
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "auth_provider": "google",
            "created_at": now_utc(),
        })

    # ----- Create Cozii session -----
    session_token = gen_session_token()
    await db.user_sessions.insert_one({
        "session_token": session_token,
        "user_id": user_id,
        "expires_at": now_utc() + timedelta(days=SESSION_DURATION_DAYS),
        "created_at": now_utc(),
    })

    # ----- Mint one-shot ticket the client redeems via /api/auth/google-session -----
    short_id = secrets.token_urlsafe(24)
    await db.oauth_pending_sessions.insert_one({
        "short_id": short_id,
        "session_token": session_token,
        "user_id": user_id,
        "created_at": now_utc(),
        "expires_at": now_utc() + timedelta(minutes=OAUTH_TICKET_TTL_MIN),
        "redeemed": False,
    })

    # ----- Redirect back to the app -----
    sep = "#"  # fragment so token never hits server logs / Referer headers
    final_url = f"{deeplink}{sep}session_id={short_id}"
    return RedirectResponse(final_url, status_code=302)


@api_router.post("/auth/google-session", response_model=AuthResponse)
async def google_session(body: GoogleSessionRequest, response: Response):
    """Redeem the one-shot ticket minted by /auth/google/callback.

    No external network calls. The session_token was already created in the
    callback; we just look it up and return it to the client.
    """
    if not body.session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")

    ticket = await db.oauth_pending_sessions.find_one(
        {"short_id": body.session_id}, {"_id": 0},
    )
    if not ticket:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    if ticket.get("redeemed"):
        raise HTTPException(status_code=401, detail="Session already redeemed")

    exp = ticket.get("expires_at")
    if isinstance(exp, datetime):
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now_utc():
            raise HTTPException(status_code=401, detail="Session expired")

    # Mark redeemed (single-use)
    await db.oauth_pending_sessions.update_one(
        {"short_id": body.session_id},
        {"$set": {"redeemed": True, "redeemed_at": now_utc()}},
    )

    user_doc = await db.users.find_one(
        {"user_id": ticket["user_id"]}, {"_id": 0, "password_hash": 0},
    )
    if not user_doc:
        raise HTTPException(status_code=404, detail="User missing for session")

    token = ticket["session_token"]
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=SESSION_DURATION_DAYS * 24 * 3600,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )
    return AuthResponse(token=token, user=User(**user_doc))


# =========================
# Session lifecycle
# =========================
@api_router.get("/auth/me", response_model=User)
async def me(user: User = Depends(get_current_user)):
    return user


@api_router.post("/auth/logout")
async def logout(request: Request, response: Response):
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get("session_token")
    if token:
        await db.user_sessions.delete_one({"session_token": token})
    response.delete_cookie("session_token", path="/")
    return {"success": True}
