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
# Family Spaces
# =========================
@api_router.post("/spaces", response_model=FamilySpace)
async def create_space(body: CreateSpaceRequest, user: User = Depends(get_current_user)):
    stype = (body.space_type or "roommates").lower().strip()
    if stype not in ("roommates", "household"):
        stype = "roommates"
    space = {
        "space_id": gen_id("space"),
        "name": body.name.strip(),
        "owner_id": user.user_id,
        "member_ids": [user.user_id],
        "invite_code": gen_invite_code(),
        "currency": (body.currency or "USD").upper().strip()[:6] or "USD",
        "space_type": stype,
        "created_at": now_utc(),
    }
    await db.family_spaces.insert_one(space)
    # Seed a starter set of categories
    starter_categories = [
        {"name": "Food & Pantry", "icon": "Refrigerator", "tint": "mint",
         "fields": [
             {"key": "expiry_date", "label": "Expiry", "type": "date"},
             {"key": "quantity", "label": "Quantity", "type": "number"},
         ]},
        {"name": "Skincare", "icon": "Sparkles", "tint": "lavender",
         "fields": [
             {"key": "expiry_date", "label": "Expiry", "type": "date"},
             {"key": "opened_date", "label": "Opened", "type": "date"},
         ]},
        {"name": "Closet", "icon": "Shirt", "tint": "peach",
         "fields": [{"key": "notes", "label": "Notes", "type": "text"}]},
        {"name": "Toiletries", "icon": "Bath", "tint": "yellow",
         "fields": [{"key": "quantity", "label": "Quantity", "type": "number"}]},
        {"name": "Cleaning", "icon": "Wind", "tint": "sage",
         "fields": [{"key": "quantity", "label": "Quantity", "type": "number"}]},
    ]
    for c in starter_categories:
        await db.categories.insert_one({
            "category_id": gen_id("cat"),
            "space_id": space["space_id"],
            "name": c["name"],
            "icon": c["icon"],
            "tint": c["tint"],
            "fields": c["fields"],
            "created_by": user.user_id,
            "created_at": now_utc(),
        })

    space_out = await db.family_spaces.find_one({"space_id": space["space_id"]}, {"_id": 0})
    return FamilySpace(**space_out)


@api_router.get("/spaces", response_model=List[FamilySpace])
async def list_spaces(user: User = Depends(get_current_user)):
    docs = await db.family_spaces.find({"member_ids": user.user_id}, {"_id": 0}).to_list(100)
    return [FamilySpace(**d) for d in docs]


@api_router.post("/spaces/join", response_model=FamilySpace)
async def join_space(body: JoinSpaceRequest, user: User = Depends(get_current_user)):
    code = body.invite_code.upper().strip()
    space = await db.family_spaces.find_one({"invite_code": code}, {"_id": 0})
    if not space:
        raise HTTPException(status_code=404, detail="Invalid invite code")
    if user.user_id in space["member_ids"]:
        return FamilySpace(**space)
    await db.family_spaces.update_one(
        {"space_id": space["space_id"]},
        {"$addToSet": {"member_ids": user.user_id}},
    )
    space = await db.family_spaces.find_one({"space_id": space["space_id"]}, {"_id": 0})
    await record_activity(space["space_id"], user, "joined", "space", space["space_id"], space["name"])
    return FamilySpace(**space)


@api_router.get("/spaces/{space_id}/members", response_model=List[User])
async def space_members(space_id: str, user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    members = await db.users.find(
        {"user_id": {"$in": space["member_ids"]}},
        {"_id": 0, "password_hash": 0},
    ).to_list(100)
    return [User(**m) for m in members]


@api_router.patch("/spaces/{space_id}", response_model=FamilySpace)
async def update_space(space_id: str, body: UpdateSpaceRequest, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    updates: Dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.currency is not None:
        cur = (body.currency or "USD").upper().strip()[:6]
        updates["currency"] = cur or "USD"
    if body.space_type is not None:
        st = body.space_type.lower().strip()
        if st in ("roommates", "household"):
            updates["space_type"] = st
    if updates:
        await db.family_spaces.update_one({"space_id": space_id}, {"$set": updates})
    out = await db.family_spaces.find_one({"space_id": space_id}, {"_id": 0})
    if "currency" not in out:
        out["currency"] = "USD"
    if "space_type" not in out:
        out["space_type"] = "roommates"
    return FamilySpace(**out)


@api_router.get("/spaces/{space_id}/my_role")
async def my_role(space_id: str, user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    is_owner = space.get("owner_id") == user.user_id
    staff = await db.staff_members.find_one({"space_id": space_id, "user_id": user.user_id}, {"_id": 0})
    if staff:
        return {"role": "staff", "staff_id": staff["staff_id"], "permissions": {**DEFAULT_STAFF_PERMS, **(staff.get("permissions") or {})}}
    return {"role": "owner" if is_owner else "member", "staff_id": None, "permissions": {}}


@api_router.patch("/spaces/{space_id}/digest-prefs")
async def update_digest_prefs(space_id: str, body: DigestPrefRequest, user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    if space.get("owner_id") != user.user_id:
        raise HTTPException(403, "Only the household owner can change digest preferences")
    updates: Dict[str, Any] = {}
    if body.daily_digest_enabled is not None:
        updates["daily_digest_enabled"] = bool(body.daily_digest_enabled)
    if body.daily_digest_utc_hour is not None:
        h = max(0, min(23, int(body.daily_digest_utc_hour)))
        updates["daily_digest_utc_hour"] = h
    if updates:
        await db.family_spaces.update_one({"space_id": space_id}, {"$set": updates})
    out = await db.family_spaces.find_one({"space_id": space_id}, {"_id": 0})
    return {
        "daily_digest_enabled": out.get("daily_digest_enabled", True),
        "daily_digest_utc_hour": out.get("daily_digest_utc_hour", 1),
    }
