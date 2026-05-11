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



@api_router.get("/notifications", response_model=List[Notification])
async def list_notifications(space_id: Optional[str] = None, unread_only: bool = False, user: User = Depends(get_current_user)):
    q: Dict[str, Any] = {"user_id": user.user_id}
    if space_id:
        q["space_id"] = space_id
    if unread_only:
        q["read"] = False
    docs = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [Notification(**d) for d in docs]


@api_router.post("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user: User = Depends(get_current_user)):
    n = await db.notifications.find_one({"notification_id": notification_id, "user_id": user.user_id}, {"_id": 0})
    if not n:
        raise HTTPException(404, "Notification not found")
    await db.notifications.update_one({"notification_id": notification_id}, {"$set": {"read": True}})
    return {"ok": True}


@api_router.post("/notifications/read_all")
async def mark_all_notifications_read(space_id: Optional[str] = None, user: User = Depends(get_current_user)):
    q: Dict[str, Any] = {"user_id": user.user_id, "read": False}
    if space_id:
        q["space_id"] = space_id
    await db.notifications.update_many(q, {"$set": {"read": True}})
    return {"ok": True}
