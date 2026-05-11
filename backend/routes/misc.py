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



# =========================
# Activity / Recent
# =========================
@api_router.get("/activity", response_model=List[ActivityItem])
async def activity_feed(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    docs = await db.activities.find({"space_id": space_id}, {"_id": 0}).sort("timestamp", -1).to_list(30)
    return [ActivityItem(**d) for d in docs]


# =========================
# Stats (summary for home screen)
# =========================
@api_router.get("/stats")
async def space_stats(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    total_items = await db.items.count_documents({"space_id": space_id, "status": {"$ne": "finished"}})
    low_items = await db.items.count_documents({"space_id": space_id, "status": "low"})

    today = now_utc().date()
    soon_threshold = (now_utc() + timedelta(days=7)).isoformat()
    today_iso = today.isoformat()
    expiring = await db.items.count_documents({
        "space_id": space_id,
        "status": {"$ne": "finished"},
        "expiry_date": {"$gte": today_iso, "$lte": soon_threshold},
    })

    first_of_month = datetime(now_utc().year, now_utc().month, 1, tzinfo=timezone.utc)
    pipeline = [
        {"$match": {"space_id": space_id, "created_at": {"$gte": first_of_month}, "price": {"$ne": None}}},
        {"$group": {"_id": None, "total": {"$sum": "$price"}}},
    ]
    cursor = db.items.aggregate(pipeline)
    total_spent = 0.0
    async for row in cursor:
        total_spent = row.get("total", 0.0) or 0.0

    return {
        "total_items": total_items,
        "low_items": low_items,
        "expiring_soon": expiring,
        "spent_this_month": total_spent,
    }


# =========================
# Health
# =========================
@api_router.get("/")
async def root():
    return {"message": "Cozii API running"}
