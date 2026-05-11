"""Core singletons + helpers for the Cozii backend.

Contains: FastAPI app, APIRouter, MongoDB client, Socket.IO server &
handlers, push-notification helpers, security/auth utilities, generic
id/time helpers, and the get_current_user dependency.

Everything that route handlers depend on lives here. Pydantic models
live in models.py — imported lazily where needed to avoid circular deps.
"""
from __future__ import annotations

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, status
from fastapi.security import HTTPBearer
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import secrets
import string
import uuid
import bcrypt
import httpx
import asyncio
import json
import re
import socketio
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, model_validator
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta


# =========================
# Product image search (best-effort, no API key)
# =========================
import httpx as _httpx_for_img  # safe alias


# =========================
# Export household report (CSV + PDF)
# =========================
import io
import csv as _csv
from fastapi.responses import StreamingResponse, Response


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="Cozii API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =========================
# Socket.IO server setup
# =========================
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    ping_interval=25,
    ping_timeout=60,
)

# In-memory bookkeeping: sid -> {"user_id":..., "spaces": [...]}
_sio_sessions: Dict[str, Dict[str, Any]] = {}


async def _resolve_user_from_token(token: str) -> Optional[Dict[str, Any]]:
    """Look up an active session by token, return its user document. Lightweight, no FastAPI request."""
    if not token:
        return None
    try:
        sess = await db.user_sessions.find_one({"session_token": token, "expires_at": {"$gt": now_utc()}}, {"_id": 0})
        if not sess:
            return None
        u = await db.users.find_one({"user_id": sess["user_id"]}, {"_id": 0, "password_hash": 0})
        return u
    except Exception as e:
        logger.warning(f"socket auth failed: {e}")
        return None


async def _user_space_ids(user_id: str) -> List[str]:
    """Return the list of space_ids this user belongs to (member or owner)."""
    try:
        cur = db.family_spaces.find({"$or": [{"owner_id": user_id}, {"member_ids": user_id}]}, {"_id": 0, "space_id": 1})
        return [d["space_id"] async for d in cur]
    except Exception as e:
        logger.warning(f"could not list user spaces: {e}")
        return []


@sio.event
async def connect(sid: str, environ: Dict[str, Any], auth: Optional[Dict[str, Any]] = None):
    token = None
    if auth and isinstance(auth, dict):
        token = auth.get("token") or auth.get("Authorization")
    if not token:
        # also accept ?token=... query string
        qs = environ.get("QUERY_STRING") or ""
        for kv in qs.split("&"):
            if kv.startswith("token="):
                token = kv.split("=", 1)[1]
                break
    user = await _resolve_user_from_token(token or "")
    if not user:
        logger.info(f"socket {sid} rejected (no/invalid token)")
        raise socketio.exceptions.ConnectionRefusedError("Unauthorized")
    space_ids = await _user_space_ids(user["user_id"])
    for sid_room in space_ids:
        await sio.enter_room(sid, f"space:{sid_room}")
    # Also a personal room so we can target the user directly
    await sio.enter_room(sid, f"user:{user['user_id']}")
    _sio_sessions[sid] = {"user_id": user["user_id"], "spaces": space_ids}
    logger.info(f"socket connect {sid} user={user['user_id']} spaces={space_ids}")
    # Send a hello so the client can confirm rooms
    await sio.emit("hello", {"user_id": user["user_id"], "spaces": space_ids}, to=sid)


@sio.event
async def disconnect(sid: str):
    sess = _sio_sessions.pop(sid, None)
    logger.info(f"socket disconnect {sid} (had={sess is not None})")


@sio.event
async def join_room(sid: str, data: Dict[str, Any]):
    """Allow the client to (re)join a space room (e.g. after switching spaces)."""
    if not isinstance(data, dict):
        return {"ok": False, "error": "bad payload"}
    space_id = data.get("space_id") or data.get("room_id")
    if not space_id:
        return {"ok": False, "error": "missing space_id"}
    sess = _sio_sessions.get(sid)
    if not sess:
        return {"ok": False, "error": "unauthorized"}
    # Validate membership
    if space_id not in sess["spaces"]:
        # Re-fetch in case a new space was just joined
        latest = await _user_space_ids(sess["user_id"])
        sess["spaces"] = latest
        if space_id not in latest:
            return {"ok": False, "error": "not a member of this space"}
    await sio.enter_room(sid, f"space:{space_id}")
    return {"ok": True, "joined": space_id}


async def emit_space_event(space_id: str, kind: str, action: str, payload: Optional[Dict[str, Any]] = None):
    """Broadcast a small change-notification to every member of the space.
    Frontend uses this to re-fetch the relevant resource."""
    try:
        await sio.emit(
            "space.event",
            {"space_id": space_id, "kind": kind, "action": action, "payload": payload or {}, "ts": now_utc().isoformat()},
            room=f"space:{space_id}",
        )
    except Exception as e:
        logger.warning(f"emit_space_event failed: {e}")


async def emit_user_event(user_id: str, kind: str, action: str, payload: Optional[Dict[str, Any]] = None):
    """Broadcast a change to a specific user (across all of their devices)."""
    try:
        await sio.emit(
            "user.event",
            {"user_id": user_id, "kind": kind, "action": action, "payload": payload or {}, "ts": now_utc().isoformat()},
            room=f"user:{user_id}",
        )
    except Exception as e:
        logger.warning(f"emit_user_event failed: {e}")


# =========================
# Expo Push Notification helpers
# =========================
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# Default user notification preferences. Daily digest is the only "scheduled"
# kind; everything else (assignments, contracts, payroll, ...) is treated as
# an important alert.
DEFAULT_NOTIFICATION_PREFS: Dict[str, bool] = {
    "daily_digest": True,
    "important_alerts": True,
}


def _classify_notification_kind(kind: str) -> str:
    """Return either 'daily_digest' or 'important_alerts'."""
    if (kind or "").lower() == "daily_digest":
        return "daily_digest"
    return "important_alerts"


async def _get_user_notification_prefs(user_id: str) -> Dict[str, bool]:
    try:
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "notification_prefs": 1})
        prefs = (u or {}).get("notification_prefs") or {}
        return {**DEFAULT_NOTIFICATION_PREFS, **prefs}
    except Exception:
        return dict(DEFAULT_NOTIFICATION_PREFS)


async def _get_user_push_tokens(user_id: str) -> List[str]:
    try:
        cur = db.push_tokens.find({"user_id": user_id, "active": True}, {"_id": 0, "token": 1})
        return [d["token"] async for d in cur if d.get("token")]
    except Exception as e:
        logger.warning(f"_get_user_push_tokens failed: {e}")
        return []


async def send_expo_push(
    user_id: str,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
    kind: str = "important_alerts",
) -> bool:
    """Send a push notification via the Expo Push Service.
    Respects user preferences. Silently no-ops when there are no tokens or
    when the relevant preference is disabled. Returns True if at least one
    request was dispatched.
    """
    try:
        category = _classify_notification_kind(kind)
        prefs = await _get_user_notification_prefs(user_id)
        if not prefs.get(category, True):
            return False
        tokens = await _get_user_push_tokens(user_id)
        if not tokens:
            return False
        payload_data = {**(data or {}), "kind": kind, "category": category}
        messages = [
            {
                "to": t,
                "title": title or "Cozii",
                "body": body or "",
                "sound": "default",
                "priority": "high",
                "channelId": "default",
                "data": payload_data,
            }
            for t in tokens
        ]
        async with httpx.AsyncClient(timeout=15) as client:
            # Expo accepts batches of up to 100; we usually have few tokens per user.
            for i in range(0, len(messages), 100):
                batch = messages[i:i + 100]
                try:
                    resp = await client.post(
                        EXPO_PUSH_URL,
                        json=batch,
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            "Accept-Encoding": "gzip, deflate",
                        },
                    )
                    if resp.status_code >= 400:
                        logger.warning(f"expo push http {resp.status_code}: {resp.text[:200]}")
                        continue
                    out = resp.json() or {}
                    receipts = out.get("data") or []
                    # Deactivate tokens that are reported as not registered
                    for tok, rcpt in zip([m["to"] for m in batch], receipts):
                        if isinstance(rcpt, dict) and rcpt.get("status") == "error":
                            err = (rcpt.get("details") or {}).get("error") or rcpt.get("message") or ""
                            if "DeviceNotRegistered" in str(err) or "InvalidCredentials" in str(err):
                                try:
                                    await db.push_tokens.update_many(
                                        {"token": tok}, {"$set": {"active": False, "deactivated_at": now_utc()}}
                                    )
                                except Exception:
                                    pass
                except Exception as e:
                    logger.warning(f"expo push send failed: {e}")
        return True
    except Exception as e:
        logger.warning(f"send_expo_push outer failure: {e}")
        return False


async def notify_user(user_id: str, space_id: str, kind: str, title: str, body: str = "", data: Optional[Dict[str, Any]] = None) -> str:
    """Centralised helper: insert a notification AND broadcast it via socket.io.
    Returns the new notification_id."""
    nid = gen_id("ntf") if 'gen_id' in globals() else f"ntf_{uuid.uuid4().hex[:16]}"
    doc = {
        "notification_id": nid,
        "user_id": user_id,
        "space_id": space_id,
        "kind": kind,
        "title": title,
        "body": body,
        "data": data or {},
        "read": False,
        "created_at": now_utc(),
    }
    try:
        await db.notifications.insert_one(doc)
    except Exception as e:
        logger.warning(f"notify_user insert failed: {e}")
    # Fire-and-forget realtime event
    try:
        await emit_user_event(user_id, "notification", "created", {"notification_id": nid, "kind": kind, "title": title, "data": data or {}, "space_id": space_id})
    except Exception as e:
        logger.warning(f"notify_user emit failed: {e}")
    # Fire-and-forget native push (does not block, swallows its own errors)
    try:
        push_data = {**(data or {}), "notification_id": nid, "space_id": space_id}
        asyncio.create_task(send_expo_push(user_id, title, body, push_data, kind))
    except Exception as e:
        logger.warning(f"notify_user push schedule failed: {e}")
    return nid



SESSION_DURATION_DAYS = 7
EMERGENT_AUTH_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
AI_SCAN_MODEL_PROVIDER = os.environ.get("AI_SCAN_PROVIDER", "openai")
AI_SCAN_MODEL_NAME = os.environ.get("AI_SCAN_MODEL", "gpt-4o")


# =========================
# Utility helpers
# =========================
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware(dt: datetime) -> datetime:
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def gen_invite_code() -> str:
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def gen_session_token() -> str:
    return secrets.token_urlsafe(32)


# =========================
# Auth dependency
# =========================
async def get_current_user(request: Request) -> User:
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    if not token:
        token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    expires_at = ensure_aware(session["expires_at"])
    if expires_at < now_utc():
        raise HTTPException(status_code=401, detail="Session expired")

    user_doc = await db.users.find_one({"user_id": session["user_id"]}, {"_id": 0, "password_hash": 0})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found")
    from models import User as _User  # local import to avoid circular dependency
    return _User(**user_doc)


async def record_activity(space_id: str, user: User, action: str, entity: str, entity_id: str, entity_name: str):
    doc = {
        "activity_id": gen_id("act"),
        "space_id": space_id,
        "user_id": user.user_id,
        "user_name": user.name,
        "action": action,
        "entity": entity,
        "entity_id": entity_id,
        "entity_name": entity_name,
        "timestamp": now_utc(),
    }
    await db.activities.insert_one(doc)
    # Realtime: every space member listens for `space.event` and refreshes the
    # relevant data when something changes. `entity` is the resource kind
    # (item, category, task, shopping, payment, attendance, ...).
    try:
        await emit_space_event(space_id, entity, action, {"entity_id": entity_id, "entity_name": entity_name, "by": user.user_id})
    except Exception as e:
        logger.warning(f"record_activity emit failed: {e}")


async def assert_space_member(space_id: str, user_id: str) -> dict:
    space = await db.family_spaces.find_one({"space_id": space_id}, {"_id": 0})
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    if user_id not in space["member_ids"]:
        raise HTTPException(status_code=403, detail="Not a member of this space")
    return space


async def is_space_owner(space_id: str, user_id: str) -> bool:
    sp = await db.family_spaces.find_one({"space_id": space_id, "owner_id": user_id}, {"_id": 0, "owner_id": 1})
    return sp is not None


async def get_staff_record(space_id: str, user_id: str) -> Optional[dict]:
    return await db.staff_members.find_one({"space_id": space_id, "user_id": user_id}, {"_id": 0})


async def assert_can_edit_category_items(space_id: str, category_id: str, user_id: str):
    """Owner: always allowed. Regular non-staff space members: also allowed
    (existing behaviour). Staff: must have `edit_inventory` permission AND the
    category must have `staff_can_edit=True`. Raises 403 otherwise."""
    if await is_space_owner(space_id, user_id):
        return
    staff = await get_staff_record(space_id, user_id)
    if not staff:
        # Not staff and not owner — regular family member, no gating.
        return
    cat = await db.categories.find_one({"category_id": category_id, "space_id": space_id}, {"_id": 0})
    if not cat:
        raise HTTPException(404, "Category not found")
    if not cat.get("staff_can_edit"):
        raise HTTPException(403, "Staff cannot edit items in this category. Ask the owner to enable it.")
    perms = {**DEFAULT_STAFF_PERMS, **(staff.get("permissions") or {})}
    if not perms.get("edit_inventory"):
        raise HTTPException(403, "You don't have permission to edit inventory.")


def _extract_json_block(text: str) -> str:
    # Remove code fences if present
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    # Try to find a JSON object in plain text
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return m.group(0)
    return text

async def _search_product_image(query: str) -> Optional[str]:
    """Best-effort fetch of a product image URL using DuckDuckGo. Returns None if anything goes wrong."""
    if not query or len(query.strip()) < 2:
        return None
    q = query.strip()
    try:
        async with _httpx_for_img.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            # 1) Get vqd token
            r1 = await client.post(
                "https://duckduckgo.com/",
                data={"q": q},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            m = re.search(r'vqd=["\']?(\d-[\d-]+)', r1.text)
            if not m:
                return None
            vqd = m.group(1)
            # 2) Search images
            r2 = await client.get(
                "https://duckduckgo.com/i.js",
                params={"q": q, "o": "json", "vqd": vqd, "f": ",,,", "p": "1"},
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://duckduckgo.com/"},
            )
            if r2.status_code != 200:
                return None
            data = r2.json()
            results = data.get("results") or []
            # Prefer Bing-hosted thumbnails (tse*.mm.bing.net) — they don't require Referer headers
            # and load reliably in mobile apps. Only fall back to the original image URL.
            for it in results[:10]:
                thumb = it.get("thumbnail")
                if thumb and thumb.startswith("http"):
                    return thumb
            for it in results[:10]:
                img = it.get("image")
                if img and img.startswith("http"):
                    return img
            return None
    except Exception as e:
        logger.debug("product image search failed for %r: %s", q, e)
        return None


def _compute_bill_state(bill: dict) -> dict:
    """Compute next_due_date and is_paid_current_period."""
    today = now_utc().date()
    freq = bill.get("frequency", "monthly")
    due_day = int(bill.get("due_day", 1))
    last_paid = bill.get("last_paid_date")
    last_paid_d = None
    if last_paid:
        try: last_paid_d = datetime.fromisoformat(last_paid).date()
        except Exception: last_paid_d = None

    if freq == "monthly":
        # Next due is the due_day in the current month, or next month if past
        try:
            this_month_due = today.replace(day=min(due_day, 28))
        except Exception:
            this_month_due = today
        if today > this_month_due:
            next_year = today.year + (1 if today.month == 12 else 0)
            next_month = 1 if today.month == 12 else today.month + 1
            try:
                next_due = today.replace(year=next_year, month=next_month, day=min(due_day, 28))
            except Exception:
                next_due = this_month_due
        else:
            next_due = this_month_due
        # Paid for the current period if last_paid_date >= start of current period
        period_start = this_month_due.replace(day=1)
        is_paid = last_paid_d is not None and last_paid_d >= period_start
    elif freq == "weekly":
        # Next due: next occurrence of due_day-of-week (0=Mon..6=Sun)
        days_ahead = (due_day - today.weekday()) % 7
        next_due = today + timedelta(days=days_ahead if days_ahead > 0 else 7)
        is_paid = last_paid_d is not None and last_paid_d >= today - timedelta(days=7)
    elif freq == "yearly":
        try:
            this_year_due = today.replace(month=1, day=min(due_day, 28))
        except Exception:
            this_year_due = today
        next_due = this_year_due if today <= this_year_due else this_year_due.replace(year=today.year + 1)
        is_paid = last_paid_d is not None and last_paid_d.year == today.year
    else:  # once
        next_due = today
        is_paid = last_paid_d is not None

    bill["next_due_date"] = next_due.isoformat()
    bill["is_paid_current_period"] = is_paid
    return bill


# =========================
# Finance Report (rich) + Raw data export
# =========================
def _period_range(period: str) -> Tuple[datetime, datetime, str]:
    now = now_utc()
    label = "All time"
    if period == "this_month":
        start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        end = now
        label = start.strftime("%B %Y")
    elif period == "last_month":
        if now.month == 1:
            start = datetime(now.year - 1, 12, 1, tzinfo=timezone.utc)
            end = datetime(now.year, 1, 1, tzinfo=timezone.utc)
        else:
            start = datetime(now.year, now.month - 1, 1, tzinfo=timezone.utc)
            end = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        label = start.strftime("%B %Y")
    elif period == "last_3_months":
        m = now.month - 3
        y = now.year
        while m <= 0:
            m += 12; y -= 1
        start = datetime(y, m, 1, tzinfo=timezone.utc)
        end = now
        label = f"{start.strftime('%b %Y')} – {now.strftime('%b %Y')}"
    elif period == "ytd":
        start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
        end = now
        label = f"Year-to-date {now.year}"
    else:  # all
        start = datetime(1970, 1, 1, tzinfo=timezone.utc)
        end = now
        label = "All time"
    return start, end, label


# =========================
# Household Phase 1 — Roles, Family members, Staff, Handbook
# =========================
DEFAULT_HOUSEHOLD_ROLES = [
    {"key": "owner",     "name": "Owner",     "icon": "Star",    "color": "peach",    "category": "family", "is_default": True},
    {"key": "spouse",    "name": "Spouse",    "icon": "Heart",   "color": "pink",     "category": "family", "is_default": True},
    {"key": "child",     "name": "Child",     "icon": "Apple",   "color": "yellow",   "category": "family", "is_default": True},
    {"key": "parent",    "name": "Parent",    "icon": "BookOpen","color": "lavender", "category": "family", "is_default": True},
    {"key": "maid",      "name": "Maid",      "icon": "Sparkles","color": "sage",     "category": "staff",  "is_default": True},
    {"key": "driver",    "name": "Driver",    "icon": "ArrowRight","color": "blue",   "category": "staff",  "is_default": True},
    {"key": "nanny",     "name": "Nanny",     "icon": "Heart",   "color": "pink",     "category": "staff",  "is_default": True},
    {"key": "cook",      "name": "Cook",      "icon": "Refrigerator","color": "peach","category": "staff",  "is_default": True},
    {"key": "gardener",  "name": "Gardener",  "icon": "Droplet", "color": "mint",     "category": "staff",  "is_default": True},
    {"key": "security",  "name": "Security",  "icon": "Lock",    "color": "lavender", "category": "staff",  "is_default": True},
]


async def _ensure_default_roles(space_id: str):
    existing = await db.household_roles.count_documents({"space_id": space_id})
    if existing > 0:
        return
    docs = []
    for r in DEFAULT_HOUSEHOLD_ROLES:
        docs.append({
            "role_id": gen_id("role"),
            "space_id": space_id,
            "key": r["key"],
            "name": r["name"],
            "icon": r["icon"],
            "color": r["color"],
            "category": r["category"],
            "is_default": True,
            "perms": {},
            "created_at": now_utc(),
        })
    if docs:
        await db.household_roles.insert_many(docs)


async def _attach_role_name(doc: Dict[str, Any]) -> Dict[str, Any]:
    rid = doc.get("role_id")
    if rid:
        r = await db.household_roles.find_one({"role_id": rid}, {"_id": 0, "name": 1})
        doc["role_name"] = r["name"] if r else None
    else:
        doc["role_name"] = None
    return doc


DEFAULT_STAFF_PERMS = {
    "view_tasks": True,
    "log_attendance": True,
    "request_shopping": True,
    "view_handbook": True,
    "view_wage_amount": True,
    "view_other_staff": False,
    "view_family": False,
    "view_finance": False,
    "view_inventory": False,
    "view_inventory_prices": True,  # only matters when view_inventory is also True
    "edit_inventory": False,  # global gate; per-category control via categories.staff_can_edit
}


def _gen_staff_invite_code() -> str:
    return secrets.token_hex(3).upper()


async def _ensure_wages_category(space_id: str, user_id: str) -> str:
    cat = await db.categories.find_one({"space_id": space_id, "name": "Staff wages"}, {"_id": 0})
    if cat:
        # backfill legacy docs missing created_by
        if not cat.get("created_by"):
            await db.categories.update_one({"category_id": cat["category_id"]}, {"$set": {"created_by": user_id}})
        return cat["category_id"]
    doc = {
        "category_id": gen_id("cat"),
        "space_id": space_id,
        "name": "Staff wages",
        "icon": "Wallet",
        "tint": "peach",
        "fields": [],
        "shared_with": [],
        "created_by": user_id,
        "created_at": now_utc(),
    }
    await db.categories.insert_one(doc)
    return doc["category_id"]


def _task_due_on(task: Dict[str, Any], date_str: str) -> bool:
    """Check if a task template is due on a specific date (YYYY-MM-DD)."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return False
    if not task.get("active", True):
        return False
    rec = task.get("recurrence", "daily")
    if rec == "daily":
        return True
    if rec == "weekly":
        wds = task.get("weekdays") or []
        return d.weekday() in wds
    if rec == "monthly":
        day = task.get("monthly_day") or 1
        # If month doesn't have that day, fall back to last day
        import calendar
        last = calendar.monthrange(d.year, d.month)[1]
        target = min(day, last)
        return d.day == target
    if rec == "once":
        return (task.get("once_date") or "") == date_str
    return False


async def _create_notification(space_id: str, user_id: Optional[str], kind: str, title: str, body: str = "", data: Optional[Dict[str, Any]] = None):
    if not user_id:
        return
    doc = {
        "notification_id": gen_id("ntf"),
        "space_id": space_id,
        "user_id": user_id,
        "kind": kind,
        "title": title,
        "body": body or "",
        "data": data or {},
        "read": False,
        "created_at": now_utc(),
    }
    await db.notifications.insert_one(doc)


# =========================
# Inventory Alerts: low stock, finished, expiring, expired
# Plus 1-tap "Add to shopping list" bulk converter.
# =========================
def _parse_iso_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, datetime):
        return s if s.tzinfo else s.replace(tzinfo=timezone.utc)
    try:
        # Accept yyyy-mm-dd or full ISO
        if len(s) == 10:
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            return None


# =========================
# Contract Templates + e-Sign
# =========================
def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip") or request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    try:
        return request.client.host if request.client else "unknown"
    except Exception:
        return "unknown"


CONTRACT_TEMPLATES: List[Dict[str, Any]] = [
    {
        "kind": "nda",
        "title": "Non-Disclosure Agreement",
        "icon": "Shield",
        "summary": "Keeps household information, photos, schedules and family details strictly confidential.",
        "default_variables": {
            "household_name": "{{household_name}}",
            "staff_name": "{{staff_name}}",
            "start_date": "{{start_date}}",
            "city": "{{city}}",
        },
        "body": (
            "NON-DISCLOSURE AGREEMENT\n\n"
            "This Non-Disclosure Agreement (\"Agreement\") is entered into on {{start_date}} by and between "
            "{{household_name}} (the \"Household\") and {{staff_name}} (the \"Employee\"), residing in {{city}}.\n\n"
            "1. CONFIDENTIAL INFORMATION\n"
            "The Employee agrees to keep strictly confidential all information about the Household, its "
            "members, children, schedules, finances, addresses, security arrangements, photos, videos, "
            "guests, medical or personal matters that may come to the Employee's knowledge during their "
            "employment.\n\n"
            "2. NO DISCLOSURE\n"
            "The Employee shall not share, post, publish, forward or discuss any such information with any "
            "third party — including on social media — during or after employment.\n\n"
            "3. RETURN OF MATERIALS\n"
            "Upon end of employment the Employee shall return all keys, devices, documents and copies of "
            "any household-related materials.\n\n"
            "4. DURATION\n"
            "This obligation of confidentiality shall continue in force indefinitely after the end of "
            "employment.\n\n"
            "5. ACKNOWLEDGEMENT\n"
            "By signing below, the Employee acknowledges they have read, understood and accepted these "
            "terms freely and without coercion."
        ),
    },
    {
        "kind": "employment",
        "title": "Employment Agreement",
        "icon": "FileText",
        "summary": "Standard household employment terms — wages, hours, days off, probation.",
        "default_variables": {
            "household_name": "{{household_name}}",
            "staff_name": "{{staff_name}}",
            "role": "{{role}}",
            "start_date": "{{start_date}}",
            "monthly_wage": "{{monthly_wage}}",
            "currency": "{{currency}}",
            "pay_cycle": "monthly",
            "off_day": "{{off_day}}",
            "working_hours": "{{working_hours}}",
            "probation_months": "1",
            "city": "{{city}}",
        },
        "body": (
            "HOUSEHOLD EMPLOYMENT AGREEMENT\n\n"
            "Made on {{start_date}} between {{household_name}} (the \"Employer\") and {{staff_name}} "
            "(the \"Employee\") for the position of {{role}} at the Employer's residence in {{city}}.\n\n"
            "1. POSITION AND DUTIES\n"
            "The Employee is engaged as {{role}} and will perform the duties reasonably assigned by the "
            "Employer, with diligence, care, honesty and respect.\n\n"
            "2. START DATE & PROBATION\n"
            "Employment begins on {{start_date}}. The first {{probation_months}} month(s) shall be a "
            "probation period during which either party may end employment with 7 days' written notice.\n\n"
            "3. WORKING HOURS & DAYS OFF\n"
            "Working hours: {{working_hours}}. Weekly day off: {{off_day}}. Public holidays as agreed "
            "verbally between Employer and Employee.\n\n"
            "4. WAGES\n"
            "The Employee shall be paid {{monthly_wage}} {{currency}} per {{pay_cycle}}, payable on or "
            "around the same date each cycle. Wages will be recorded inside the Cozii household app and the "
            "Employee will receive a digital receipt for each payment.\n\n"
            "5. CONDUCT\n"
            "The Employee shall behave respectfully toward all members of the Household, keep their work "
            "area clean, and report any breakage, accident or concern promptly.\n\n"
            "6. CONFIDENTIALITY\n"
            "The Employee shall keep all household information strictly private (see Non-Disclosure "
            "Agreement, if signed separately).\n\n"
            "7. END OF EMPLOYMENT\n"
            "After probation, either side may end employment with 30 days' written notice, or immediately "
            "in case of serious misconduct, dishonesty or breach of confidentiality.\n\n"
            "8. ACKNOWLEDGEMENT\n"
            "Both parties confirm by signing below that they have read, understood and freely accept these "
            "terms."
        ),
    },
    {
        "kind": "confidentiality",
        "title": "Confidentiality & Privacy Pledge",
        "icon": "Lock",
        "summary": "Lighter pledge focused on family privacy, photos, social media and guests.",
        "default_variables": {
            "household_name": "{{household_name}}",
            "staff_name": "{{staff_name}}",
            "start_date": "{{start_date}}",
        },
        "body": (
            "CONFIDENTIALITY & PRIVACY PLEDGE\n\n"
            "I, {{staff_name}}, joining the {{household_name}} household on {{start_date}}, pledge:\n\n"
            "• I will not take, share, post or forward any photos or videos of any member of the household, "
            "their children, their guests, the home interior, or any documents — on any platform — at any "
            "time.\n\n"
            "• I will not discuss the family's whereabouts, travel plans, schedule, finances, medical "
            "matters or personal life with anyone outside the household.\n\n"
            "• I will treat all keys, alarm codes, passwords and access cards as private property of the "
            "household and never share them.\n\n"
            "• I understand that breaking this pledge is grounds for immediate dismissal and may result in "
            "legal action.\n\n"
            "I sign below freely, having read and understood this pledge."
        ),
    },
    {
        "kind": "blank",
        "title": "Blank Custom Agreement",
        "icon": "Edit3",
        "summary": "Start from scratch — write your own custom terms.",
        "default_variables": {},
        "body": "",
    },
]


def _render_contract_body(body: str, variables: Dict[str, Any]) -> str:
    """Replace {{key}} with values from `variables`. Missing keys stay as-is."""
    if not body:
        return body
    out = body
    for k, v in (variables or {}).items():
        try:
            out = out.replace("{{" + str(k) + "}}", str(v) if v is not None else "")
        except Exception:
            continue
    return out


app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# Daily morning digest: low-stock / expiry summary notification
# Runs as an async background task started at app startup. Every hour it
# checks each household space and, if (a) the space's configured digest hour
# matches the current local hour, (b) digest is enabled, and (c) we haven't
# already sent today, it pushes a one-line summary notification to the owner.
# =========================
async def _compute_alerts_for_space(space_id: str, days_threshold: int = 7) -> Dict[str, int]:
    items = await db.items.find({"space_id": space_id}, {"_id": 0, "status": 1, "expiry_date": 1}).to_list(5000)
    today = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    threshold = today + timedelta(days=days_threshold)
    low = 0; finished = 0; expiring = 0; expired = 0
    for it in items:
        st = (it.get("status") or "").lower()
        if st == "low": low += 1
        elif st == "finished": finished += 1
        exp = _parse_iso_date(it.get("expiry_date"))
        if exp:
            if exp < today: expired += 1
            elif exp <= threshold: expiring += 1
    return {"low": low, "finished": finished, "expiring": expiring, "expired": expired,
            "total": low + finished + expiring + expired}


async def _send_digest_for_space(space: Dict[str, Any]) -> bool:
    """Send the digest notification if there are alerts. Returns True if sent."""
    counts = await _compute_alerts_for_space(space["space_id"])
    if counts["total"] == 0:
        return False
    owner_id = space.get("owner_id")
    if not owner_id:
        return False
    parts: List[str] = []
    if counts["low"]: parts.append(f"{counts['low']} low-stock")
    if counts["finished"]: parts.append(f"{counts['finished']} finished")
    if counts["expiring"]: parts.append(f"{counts['expiring']} expiring soon")
    if counts["expired"]: parts.append(f"{counts['expired']} expired")
    summary = " · ".join(parts)
    title = f"Good morning! {counts['total']} item{'s' if counts['total'] != 1 else ''} need attention"
    body = f"{summary}. Tap to open the shopping list."
    await notify_user(
        user_id=owner_id,
        space_id=space["space_id"],
        kind="daily_digest",
        title=title,
        body=body,
        data={"counts": counts, "screen": "/shopping-list"},
    )
    return True


async def _daily_digest_loop():
    """Background loop: every hour, check each household space and send digest if due."""
    await asyncio.sleep(30)  # wait a bit for app to be ready
    while True:
        try:
            now = now_utc()
            current_utc_hour = now.hour
            # Find household spaces with digest enabled. Default = enabled at hour 1 UTC ≈ 8am Jakarta (UTC+7).
            cursor = db.family_spaces.find(
                {"$or": [{"space_type": "household"}, {"space_type": {"$exists": False}}]},
                {"_id": 0},
            )
            async for space in cursor:
                try:
                    if space.get("daily_digest_enabled") is False:
                        continue
                    target_hour = int(space.get("daily_digest_utc_hour", 1))  # default 1 UTC = 08:00 WIB
                    if current_utc_hour != target_hour:
                        continue
                    today_key = now.date().isoformat()
                    last_sent = space.get("last_digest_date")
                    if last_sent == today_key:
                        continue
                    sent = await _send_digest_for_space(space)
                    # Always mark date so we don't recompute every minute even if no alerts
                    await db.family_spaces.update_one(
                        {"space_id": space["space_id"]},
                        {"$set": {"last_digest_date": today_key}},
                    )
                    if sent:
                        logger.info(f"[digest] sent for space={space['space_id']}")
                except Exception as e:
                    logger.warning(f"[digest] error for space={space.get('space_id')}: {e}")
        except Exception as e:
            logger.warning(f"[digest] outer loop error: {e}")
        # Sleep for ~1 hour, but check every 5 minutes near the boundary so we don't miss
        await asyncio.sleep(300)
