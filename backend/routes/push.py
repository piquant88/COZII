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
)
# Pydantic models are re-exported through `models` for convenience.
from models import *  # noqa: F401,F403
import models as _m  # noqa: F401  (typed access if needed)



@api_router.post("/users/push-token")
async def register_push_token(body: RegisterPushTokenRequest, user: User = Depends(get_current_user)):
    if not body.token or not isinstance(body.token, str):
        raise HTTPException(400, "Invalid token")
    now = now_utc()
    doc = {
        "token": body.token,
        "user_id": user.user_id,
        "platform": (body.platform or "").lower() or None,
        "device_name": body.device_name or None,
        "active": True,
        "updated_at": now,
    }
    # Upsert by (token) — a token belongs to exactly one user/device.
    await db.push_tokens.update_one(
        {"token": body.token},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {"ok": True}


@api_router.delete("/users/push-token")
async def deregister_push_token(token: str, user: User = Depends(get_current_user)):
    if not token:
        raise HTTPException(400, "Missing token")
    res = await db.push_tokens.update_one(
        {"token": token, "user_id": user.user_id},
        {"$set": {"active": False, "deactivated_at": now_utc()}},
    )
    return {"ok": True, "matched": res.matched_count}


@api_router.get("/users/notification-prefs")
async def get_notification_prefs(user: User = Depends(get_current_user)):
    prefs = await _get_user_notification_prefs(user.user_id)
    return prefs


@api_router.put("/users/notification-prefs")
async def update_notification_prefs(body: NotificationPrefsRequest, user: User = Depends(get_current_user)):
    current = await _get_user_notification_prefs(user.user_id)
    next_prefs = dict(current)
    if body.daily_digest is not None:
        next_prefs["daily_digest"] = bool(body.daily_digest)
    if body.important_alerts is not None:
        next_prefs["important_alerts"] = bool(body.important_alerts)
    await db.users.update_one(
        {"user_id": user.user_id},
        {"$set": {"notification_prefs": next_prefs, "notification_prefs_updated_at": now_utc()}},
    )
    return next_prefs


@api_router.post("/users/push-test")
async def push_test(user: User = Depends(get_current_user)):
    """Manual smoke-test endpoint: sends a notification to the calling user."""
    sent = await send_expo_push(
        user_id=user.user_id,
        title="Cozii test notification",
        body="If you can read this on your phone, push is working.",
        data={"screen": "/shopping-list"},
        kind="important_alerts",
    )
    return {"sent": sent}
