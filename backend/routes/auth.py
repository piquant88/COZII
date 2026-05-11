"""Auto-generated route module — split from server.py."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Tuple
from fastapi import HTTPException, Depends, Request, Response
from pydantic import BaseModel, Field
import asyncio
import json
import re
import os
import logging
import secrets
import string
import uuid
import httpx

from core import (
    app, api_router, db, sio, logger, client,
    now_utc, ensure_aware, hash_password, verify_password,
    gen_id, gen_invite_code, gen_session_token,
    get_current_user, record_activity, assert_space_member,
    is_space_owner, get_staff_record, assert_can_edit_category_items,
    emit_space_event, emit_user_event, notify_user, send_expo_push,
    SESSION_DURATION_DAYS,
)
# Pydantic models are re-exported through `models` for convenience.
from models import *  # noqa: F401,F403
import models as _m  # noqa: F401  (typed access if needed)



# =========================
# Auth routes
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


@api_router.post("/auth/google-session", response_model=AuthResponse)
async def google_session(body: GoogleSessionRequest, response: Response):
    async with httpx.AsyncClient(timeout=15) as hclient:
        r = await hclient.get(EMERGENT_AUTH_URL, headers={"X-Session-ID": body.session_id})
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid session ID")
    data = r.json()
    email = data.get("email", "").lower().strip()
    name = data.get("name") or email.split("@")[0]
    picture = data.get("picture")
    emergent_token = data.get("session_token")
    if not email:
        raise HTTPException(status_code=400, detail="Invalid auth data")

    existing = await db.users.find_one({"email": email}, {"_id": 0})
    if existing:
        user_id = existing["user_id"]
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {"name": name, "picture": picture, "auth_provider": existing.get("auth_provider", "google")}},
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

    token = emergent_token or gen_session_token()
    await db.user_sessions.insert_one({
        "session_token": token,
        "user_id": user_id,
        "expires_at": now_utc() + timedelta(days=SESSION_DURATION_DAYS),
        "created_at": now_utc(),
    })

    # Also set httpOnly cookie for web flow
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=SESSION_DURATION_DAYS * 24 * 3600,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )
    user_doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    return AuthResponse(token=token, user=User(**user_doc))


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
