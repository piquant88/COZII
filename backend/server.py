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
# Pydantic Models
# =========================
class TZAware(BaseModel):
    """Base model that converts naive datetimes (from MongoDB) into UTC-aware ones."""
    @model_validator(mode='before')
    @classmethod
    def _ensure_tz_aware(cls, data):
        if isinstance(data, dict):
            for k, v in list(data.items()):
                if isinstance(v, datetime) and v.tzinfo is None:
                    data[k] = v.replace(tzinfo=timezone.utc)
        return data


class User(TZAware):
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    created_at: datetime
    auth_provider: str = "email"  # email | google


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionRequest(BaseModel):
    session_id: str


class AuthResponse(BaseModel):
    token: str
    user: User


class FamilySpace(TZAware):
    space_id: str
    name: str
    owner_id: str
    member_ids: List[str]
    invite_code: str
    currency: str = "USD"
    space_type: str = "roommates"
    created_at: datetime


class CreateSpaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    currency: str = "USD"
    space_type: str = "roommates"


class UpdateSpaceRequest(BaseModel):
    name: Optional[str] = None
    currency: Optional[str] = None
    space_type: Optional[str] = None


class JoinSpaceRequest(BaseModel):
    invite_code: str


class CategoryField(BaseModel):
    key: str
    label: str
    type: str  # text | number | date | price | select
    options: List[str] = []  # for select type


class Category(TZAware):
    category_id: str
    space_id: str
    name: str
    icon: str
    tint: str  # color tint key
    fields: List[CategoryField]
    shared_with: List[str] = []  # user_ids that split costs in this category; empty = not shared
    created_by: str
    created_at: datetime


class CreateCategoryRequest(BaseModel):
    space_id: str
    name: str = Field(min_length=1, max_length=40)
    icon: str = "Box"
    tint: str = "mint"
    fields: List[CategoryField] = []
    shared_with: List[str] = []


class UpdateCategoryRequest(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    tint: Optional[str] = None
    fields: Optional[List[CategoryField]] = None
    shared_with: Optional[List[str]] = None


class Item(TZAware):
    item_id: str
    space_id: str
    category_id: str
    name: str
    photo_base64: Optional[str] = None  # uploaded photo override (still supported)
    image_url: Optional[str] = None  # auto-fetched product image URL (preferred for display)
    receipt_base64: Optional[str] = None  # original receipt/proof file (image base64)
    event_tag: Optional[str] = None  # free-text tag for grouping (e.g. "Birthday June 8")
    status: str = "available"  # available | low | finished
    quantity: float = 1
    unit: Optional[str] = None
    price: Optional[float] = None
    purchase_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    fields: Dict[str, Any] = {}
    created_by: str
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class CreateItemRequest(BaseModel):
    space_id: str
    category_id: str
    name: str = Field(min_length=1, max_length=80)
    photo_base64: Optional[str] = None
    image_url: Optional[str] = None
    receipt_base64: Optional[str] = None
    event_tag: Optional[str] = None
    status: str = "available"
    quantity: float = 1
    unit: Optional[str] = None
    price: Optional[float] = None
    purchase_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    fields: Dict[str, Any] = {}


class UpdateItemRequest(BaseModel):
    name: Optional[str] = None
    photo_base64: Optional[str] = None
    image_url: Optional[str] = None
    receipt_base64: Optional[str] = None
    event_tag: Optional[str] = None
    status: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    purchase_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None
    category_id: Optional[str] = None


class ActivityItem(TZAware):
    activity_id: str
    space_id: str
    user_id: str
    user_name: str
    action: str  # added | updated | finished | deleted
    entity: str  # item | category
    entity_id: str
    entity_name: str
    timestamp: datetime


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
    return User(**user_doc)


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


async def assert_space_member(space_id: str, user_id: str) -> dict:
    space = await db.family_spaces.find_one({"space_id": space_id}, {"_id": 0})
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    if user_id not in space["member_ids"]:
        raise HTTPException(status_code=403, detail="Not a member of this space")
    return space


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


# =========================
# Categories
# =========================
@api_router.post("/categories", response_model=Category)
async def create_category(body: CreateCategoryRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    doc = {
        "category_id": gen_id("cat"),
        "space_id": body.space_id,
        "name": body.name.strip(),
        "icon": body.icon,
        "tint": body.tint,
        "fields": [f.dict() for f in body.fields],
        "shared_with": body.shared_with,
        "created_by": user.user_id,
        "created_at": now_utc(),
    }
    await db.categories.insert_one(doc)
    out = await db.categories.find_one({"category_id": doc["category_id"]}, {"_id": 0})
    await record_activity(body.space_id, user, "added", "category", out["category_id"], out["name"])
    return Category(**out)


@api_router.get("/categories", response_model=List[Category])
async def list_categories(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    docs = await db.categories.find({"space_id": space_id}, {"_id": 0}).to_list(200)
    # Filter: shared_with empty = visible to all; non-empty = only those members
    accessible = [
        d for d in docs
        if not d.get("shared_with") or user.user_id in d.get("shared_with", [])
    ]
    accessible.sort(key=lambda d: d["created_at"])
    # Backfill legacy docs missing `created_by` (e.g. auto-created "Staff wages" category before fix)
    missing = [d for d in accessible if not d.get("created_by")]
    if missing:
        owner_id = None
        sp = await db.family_spaces.find_one({"space_id": space_id}, {"_id": 0, "owner_id": 1})
        if sp:
            owner_id = sp.get("owner_id")
        for d in missing:
            d["created_by"] = owner_id or user.user_id
        await db.categories.update_many(
            {"space_id": space_id, "category_id": {"$in": [d["category_id"] for d in missing]}, "created_by": {"$in": [None, ""]}},
            {"$set": {"created_by": owner_id or user.user_id}},
        )
    return [Category(**d) for d in accessible]


@api_router.patch("/categories/{category_id}", response_model=Category)
async def update_category(category_id: str, body: UpdateCategoryRequest, user: User = Depends(get_current_user)):
    cat = await db.categories.find_one({"category_id": category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    await assert_space_member(cat["space_id"], user.user_id)
    updates: Dict[str, Any] = {}
    if body.name is not None:
        updates["name"] = body.name.strip()
    if body.icon is not None:
        updates["icon"] = body.icon
    if body.tint is not None:
        updates["tint"] = body.tint
    if body.fields is not None:
        updates["fields"] = [f.dict() for f in body.fields]
    if body.shared_with is not None:
        updates["shared_with"] = body.shared_with
    if updates:
        await db.categories.update_one({"category_id": category_id}, {"$set": updates})
    out = await db.categories.find_one({"category_id": category_id}, {"_id": 0})
    return Category(**out)


@api_router.delete("/categories/{category_id}")
async def delete_category(category_id: str, user: User = Depends(get_current_user)):
    cat = await db.categories.find_one({"category_id": category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    await assert_space_member(cat["space_id"], user.user_id)
    await db.categories.delete_one({"category_id": category_id})
    await db.items.delete_many({"category_id": category_id})
    return {"success": True}


# =========================
# Items
# =========================
@api_router.post("/items", response_model=Item)
async def create_item(body: CreateItemRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    cat = await db.categories.find_one({"category_id": body.category_id}, {"_id": 0})
    if not cat or cat["space_id"] != body.space_id:
        raise HTTPException(status_code=400, detail="Invalid category")
    doc = {
        "item_id": gen_id("item"),
        "space_id": body.space_id,
        "category_id": body.category_id,
        "name": body.name.strip(),
        "photo_base64": body.photo_base64,
        "image_url": body.image_url,
        "receipt_base64": body.receipt_base64,
        "event_tag": body.event_tag,
        "status": body.status,
        "quantity": body.quantity,
        "unit": body.unit,
        "price": body.price,
        "purchase_date": body.purchase_date,
        "expiry_date": body.expiry_date,
        "notes": body.notes,
        "fields": body.fields,
        "created_by": user.user_id,
        "created_by_name": user.name,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.items.insert_one(doc)
    out = await db.items.find_one({"item_id": doc["item_id"]}, {"_id": 0})
    await record_activity(body.space_id, user, "added", "item", out["item_id"], out["name"])
    return Item(**out)


@api_router.get("/items", response_model=List[Item])
async def list_items(
    space_id: str,
    category_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    await assert_space_member(space_id, user.user_id)
    query: Dict[str, Any] = {"space_id": space_id}
    if category_id:
        query["category_id"] = category_id
    if status_filter:
        query["status"] = status_filter
    docs = await db.items.find(query, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return [Item(**d) for d in docs]


@api_router.get("/items/{item_id}", response_model=Item)
async def get_item(item_id: str, user: User = Depends(get_current_user)):
    doc = await db.items.find_one({"item_id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Item not found")
    await assert_space_member(doc["space_id"], user.user_id)
    return Item(**doc)


@api_router.patch("/items/{item_id}", response_model=Item)
async def update_item(item_id: str, body: UpdateItemRequest, user: User = Depends(get_current_user)):
    doc = await db.items.find_one({"item_id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Item not found")
    await assert_space_member(doc["space_id"], user.user_id)

    updates: Dict[str, Any] = {"updated_at": now_utc()}
    payload = body.dict(exclude_unset=True)
    for k, v in payload.items():
        updates[k] = v

    if "name" in updates and isinstance(updates["name"], str):
        updates["name"] = updates["name"].strip()

    await db.items.update_one({"item_id": item_id}, {"$set": updates})
    out = await db.items.find_one({"item_id": item_id}, {"_id": 0})

    action = "finished" if body.status == "finished" else "updated"
    await record_activity(out["space_id"], user, action, "item", out["item_id"], out["name"])
    return Item(**out)


@api_router.delete("/items/{item_id}")
async def delete_item(item_id: str, user: User = Depends(get_current_user)):
    doc = await db.items.find_one({"item_id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Item not found")
    await assert_space_member(doc["space_id"], user.user_id)
    await db.items.delete_one({"item_id": item_id})
    await record_activity(doc["space_id"], user, "deleted", "item", item_id, doc["name"])
    return {"success": True}


# =========================
# AI Receipt Scan
# =========================
class ScanReceiptRequest(BaseModel):
    image_base64: str  # data URI or raw base64
    target_fields: List[CategoryField] = []  # optional: when scanning into a specific category, fill these


class ScannedItem(BaseModel):
    name: str
    quantity: float = 1
    price: Optional[float] = None
    category_hint: Optional[str] = None
    fields: Dict[str, Any] = {}


class ScanReceiptResponse(BaseModel):
    items: List[ScannedItem]
    raw: Optional[str] = None


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


# =========================
# Product image search (best-effort, no API key)
# =========================
import httpx as _httpx_for_img  # safe alias

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


@api_router.post("/ai/scan-receipt", response_model=ScanReceiptResponse)
async def scan_receipt(body: ScanReceiptRequest, user: User = Depends(get_current_user)):
    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="AI key not configured")

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"AI library not available: {e}")

    raw = body.image_base64 or ""
    # Strip data URI prefix if present
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]

    if not raw:
        raise HTTPException(status_code=400, detail="No image provided")

    system_message = (
        "You are a helpful assistant that extracts shopping or transaction info from images. "
        "Return STRICT JSON only, no prose, no markdown, in this exact schema: "
        '{"items":[{"name":"string","quantity":number,"price":number_or_null,"category_hint":"food|skincare|toiletries|closet|cleaning|electronics|services|other","fields":{}}]}. '
        "\n\nThe image may be one of: \n"
        "  (A) A typical store receipt with multiple line items → extract each line as a separate item. \n"
        "  (B) A bank transfer / payment proof / e-wallet screenshot → return ONE item with name like 'Transfer to <recipient>' or 'Payment to <merchant>' and price = total amount. category_hint='services' or 'other'. \n"
        "  (C) A product photo (one item only) → return ONE item with the product name and price if visible. \n"
        "  (D) A handwritten list / note → extract each line as a separate item. \n"
        "\nIMPORTANT: \n"
        "- ALWAYS return at least 1 item if anything is readable. \n"
        "- Skip subtotal/tax/total/fees/change/tip lines; instead use them only as price if the doc is a single transaction. \n"
        "- Use lowercase category_hint values. \n"
        "- If price is unclear, set it to null. Quantity defaults to 1. \n"
        "- For bank transfers, the 'name' must mention what kind of transaction (e.g. 'Transfer to Windi A.O.', 'Top-up GoPay', 'Bill payment PLN'). \n"
        "- Currency in the image may not be USD; ignore the currency symbol and just put the number. \n"
        "- The 'fields' object must contain extra structured details for each item."
    )

    if body.target_fields:
        # Build instruction for AI to also fill in per-category fields
        field_instructions = []
        for f in body.target_fields:
            if f.type == "select" and f.options:
                opts = " | ".join(f.options)
                field_instructions.append(f'  - "{f.key}" (label "{f.label}"): pick exactly one of [{opts}] that best matches this item, or null if uncertain')
            elif f.type == "date":
                field_instructions.append(f'  - "{f.key}" (label "{f.label}"): an ISO date string YYYY-MM-DD if visible, else null')
            elif f.type in ("number", "price"):
                field_instructions.append(f'  - "{f.key}" (label "{f.label}"): a number if visible, else null')
            else:
                field_instructions.append(f'  - "{f.key}" (label "{f.label}"): a short string if visible, else null')
        if field_instructions:
            system_message += (
                " For each detected item, also fill the 'fields' object with these keys (keep keys exact, lowercase): \n"
                + "\n".join(field_instructions)
            )

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"scan_{user.user_id}_{uuid.uuid4().hex[:8]}",
        system_message=system_message,
    ).with_model(AI_SCAN_MODEL_PROVIDER, AI_SCAN_MODEL_NAME)

    message = UserMessage(
        text="Extract each line item from this image as JSON following the schema.",
        file_contents=[ImageContent(image_base64=raw)],
    )

    try:
        response = await chat.send_message(message)
    except Exception as e:
        logger.exception("AI scan failed")
        msg = str(e).lower()
        if 'budget' in msg or 'quota' in msg or '429' in msg:
            raise HTTPException(status_code=402, detail="AI quota reached. Please top up your Emergent LLM key or try again later.")
        raise HTTPException(status_code=502, detail=f"AI scan failed: {e}")

    text = response if isinstance(response, str) else str(response)
    json_text = _extract_json_block(text)

    parsed = None
    try:
        parsed = json.loads(json_text)
    except Exception:
        # Retry: one more LLM call asking it to return ONLY JSON, very strict
        try:
            retry_chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"scan_retry_{user.user_id}_{uuid.uuid4().hex[:6]}",
                system_message=(
                    "You convert receipt-like text to STRICT JSON. "
                    'Output ONLY the JSON object: {"items":[{"name":"string","quantity":number,"price":number_or_null,"category_hint":"string","fields":{}}]}. '
                    "No markdown, no commentary. If the input is a transfer/payment, return one item describing it."
                ),
            ).with_model(AI_SCAN_MODEL_PROVIDER, AI_SCAN_MODEL_NAME)
            r2 = await retry_chat.send_message(UserMessage(text=f"Convert this OCR/text to JSON (strict): {text[:1500]}"))
            parsed = json.loads(_extract_json_block(r2 if isinstance(r2, str) else str(r2)))
        except Exception:
            parsed = None

    items_raw = (parsed.get("items", []) if isinstance(parsed, dict) else []) if parsed else []
    items: List[ScannedItem] = []
    for it in items_raw:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        try:
            qty = float(it.get("quantity") or 1)
        except Exception:
            qty = 1.0
        price = it.get("price")
        try:
            price = float(price) if price is not None else None
        except Exception:
            price = None
        hint = it.get("category_hint")
        if hint is not None:
            hint = str(hint).lower().strip() or None
        fields = it.get("fields") or {}
        if not isinstance(fields, dict):
            fields = {}
        items.append(ScannedItem(name=name, quantity=qty, price=price, category_hint=hint, fields=fields))

    # Fallback: if AI returned nothing useful, try to infer at least an amount from raw text
    if not items:
        # Try to find a number in the text (e.g. "97.000" or "97,000.00") for the price
        amount_match = re.search(r"(\d{1,3}(?:[\.,]\d{3})+(?:[\.,]\d{2})?|\d+[\.,]\d{2})", text or "")
        price_val: Optional[float] = None
        if amount_match:
            raw_n = amount_match.group(1)
            # Heuristic: if it has multiple dots/commas, treat dots/commas as thousand sep
            stripped = raw_n.replace(".", "").replace(",", "") if raw_n.count(".") + raw_n.count(",") >= 2 else raw_n.replace(",", ".")
            try:
                price_val = float(stripped)
            except Exception:
                price_val = None
        items.append(ScannedItem(
            name="Transaction (please rename)",
            quantity=1,
            price=price_val,
            category_hint="other",
            fields={"_raw": (text or "")[:200]},
        ))

    return ScanReceiptResponse(items=items, raw=text[:2000])


class BulkCreateItemsRequest(BaseModel):
    space_id: str
    category_id: str  # Default category
    per_item_category: Dict[str, str] = {}  # index -> category_id override
    items: List[ScannedItem]
    purchase_date: Optional[str] = None
    receipt_photo_base64: Optional[str] = None  # original receipt (kept as proof, not display)
    event_tag: Optional[str] = None  # e.g. "Birthday June 8"
    auto_fetch_images: bool = True  # auto-search the web for product images


@api_router.post("/items/bulk", response_model=List[Item])
async def bulk_create_items(body: BulkCreateItemsRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    cat_docs = await db.categories.find({"space_id": body.space_id}, {"_id": 0, "category_id": 1}).to_list(200)
    valid_cat_ids = {c["category_id"] for c in cat_docs}
    if body.category_id not in valid_cat_ids:
        raise HTTPException(status_code=400, detail="Invalid default category")

    # Best-effort fetch product images in parallel for each item
    image_urls: List[Optional[str]] = [None] * len(body.items)
    if body.auto_fetch_images and body.items:
        async def _fetch_for(idx: int, name: str):
            try:
                image_urls[idx] = await _search_product_image(name)
            except Exception:
                image_urls[idx] = None
        await asyncio.gather(*[_fetch_for(i, it.name) for i, it in enumerate(body.items)])

    created: List[dict] = []
    for idx, it in enumerate(body.items):
        cid = body.per_item_category.get(str(idx), body.category_id)
        if cid not in valid_cat_ids:
            cid = body.category_id
        doc = {
            "item_id": gen_id("item"),
            "space_id": body.space_id,
            "category_id": cid,
            "name": it.name.strip(),
            "photo_base64": None,
            "image_url": image_urls[idx],
            "receipt_base64": body.receipt_photo_base64,
            "event_tag": body.event_tag,
            "status": "available",
            "quantity": it.quantity,
            "unit": None,
            "price": it.price,
            "purchase_date": body.purchase_date,
            "expiry_date": None,
            "notes": None,
            "fields": it.fields or {},
            "created_by": user.user_id,
            "created_by_name": user.name,
            "created_at": now_utc(),
            "updated_at": now_utc(),
        }
        await db.items.insert_one(doc)
        out = await db.items.find_one({"item_id": doc["item_id"]}, {"_id": 0})
        created.append(out)
        await record_activity(body.space_id, user, "added", "item", out["item_id"], out["name"])

    return [Item(**d) for d in created]


# Manual product-image refetch endpoint for an item
class RefreshImageRequest(BaseModel):
    query: Optional[str] = None  # override search query


@api_router.post("/items/{item_id}/refresh-image", response_model=Item)
async def refresh_item_image(item_id: str, body: RefreshImageRequest, user: User = Depends(get_current_user)):
    doc = await db.items.find_one({"item_id": item_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Item not found")
    await assert_space_member(doc["space_id"], user.user_id)
    q = (body.query or doc.get("name") or "").strip()
    url = await _search_product_image(q)
    if not url:
        raise HTTPException(404, "No image found for this query. Try a more specific name (e.g. brand + model).")
    await db.items.update_one({"item_id": item_id}, {"$set": {"image_url": url, "photo_base64": None, "updated_at": now_utc()}})
    out = await db.items.find_one({"item_id": item_id}, {"_id": 0})
    return Item(**out)


# Public lightweight search endpoint (used during item edit)
@api_router.get("/products/image-search")
async def product_image_search(q: str, user: User = Depends(get_current_user)):
    url = await _search_product_image(q)
    return {"query": q, "image_url": url}


# =========================
# Settlements / Splits
# =========================
class Settlement(TZAware):
    settlement_id: str
    space_id: str
    from_user_id: str
    to_user_id: str
    from_name: str
    to_name: str
    amount: float
    note: Optional[str] = None
    evidence_photo_base64: Optional[str] = None
    created_at: datetime


class CreateSettlementRequest(BaseModel):
    space_id: str
    to_user_id: str
    amount: float
    note: Optional[str] = None
    evidence_photo_base64: Optional[str] = None


@api_router.post("/settlements", response_model=Settlement)
async def create_settlement(body: CreateSettlementRequest, user: User = Depends(get_current_user)):
    space = await assert_space_member(body.space_id, user.user_id)
    if body.to_user_id not in space["member_ids"]:
        raise HTTPException(status_code=400, detail="Recipient must be a member of this space")
    if body.to_user_id == user.user_id:
        raise HTTPException(status_code=400, detail="Cannot pay yourself")
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    to_user_doc = await db.users.find_one({"user_id": body.to_user_id}, {"_id": 0, "name": 1})
    to_name = to_user_doc["name"] if to_user_doc else "Unknown"

    doc = {
        "settlement_id": gen_id("settle"),
        "space_id": body.space_id,
        "from_user_id": user.user_id,
        "to_user_id": body.to_user_id,
        "from_name": user.name,
        "to_name": to_name,
        "amount": round(body.amount, 2),
        "note": body.note,
        "evidence_photo_base64": body.evidence_photo_base64,
        "created_at": now_utc(),
    }
    await db.settlements.insert_one(doc)
    out = await db.settlements.find_one({"settlement_id": doc["settlement_id"]}, {"_id": 0})
    await record_activity(body.space_id, user, "paid", "settlement", out["settlement_id"], f"{user.name} → {to_name}")
    return Settlement(**out)


@api_router.get("/settlements", response_model=List[Settlement])
async def list_settlements(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    docs = await db.settlements.find({"space_id": space_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [Settlement(**d) for d in docs]


@api_router.delete("/settlements/{settlement_id}")
async def delete_settlement(settlement_id: str, user: User = Depends(get_current_user)):
    doc = await db.settlements.find_one({"settlement_id": settlement_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Settlement not found")
    if doc["from_user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Only the payer can delete this settlement")
    await db.settlements.delete_one({"settlement_id": settlement_id})
    return {"success": True}


@api_router.get("/balances")
async def get_balances(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)

    # 1. All shared categories (have 2+ members in shared_with)
    cat_docs = await db.categories.find({"space_id": space_id}, {"_id": 0}).to_list(500)
    cat_share_map: Dict[str, List[str]] = {}
    for c in cat_docs:
        sw = c.get("shared_with") or []
        if len(sw) >= 2:
            cat_share_map[c["category_id"]] = sw

    # 2. All priced items in those categories
    items = []
    if cat_share_map:
        items = await db.items.find({
            "space_id": space_id,
            "category_id": {"$in": list(cat_share_map.keys())},
            "price": {"$ne": None, "$gt": 0},
        }, {"_id": 0}).to_list(5000)

    # 3. Pairwise debts: (debtor, creditor) -> amount
    pair_debts: Dict[Tuple[str, str], float] = {}
    for it in items:
        members = cat_share_map[it["category_id"]]
        payer = it.get("created_by")
        if payer not in members:
            continue
        share = it["price"] / len(members)
        for m in members:
            if m == payer:
                continue
            key = (m, payer)
            pair_debts[key] = pair_debts.get(key, 0) + share

    # 4. Subtract settlements
    settlements = await db.settlements.find({"space_id": space_id}, {"_id": 0}).to_list(2000)
    for s in settlements:
        key = (s["from_user_id"], s["to_user_id"])
        if key in pair_debts:
            pair_debts[key] = max(0.0, pair_debts[key] - s["amount"])

    # 5. Net out reverse pairs
    nets: Dict[Tuple[str, str], float] = {}
    seen: set = set()
    for (debtor, creditor), amount in pair_debts.items():
        if (debtor, creditor) in seen:
            continue
        rev = pair_debts.get((creditor, debtor), 0.0)
        net = amount - rev
        seen.add((debtor, creditor))
        seen.add((creditor, debtor))
        if net > 0.01:
            nets[(debtor, creditor)] = net
        elif net < -0.01:
            nets[(creditor, debtor)] = -net

    # 6. Names
    uids = set()
    for (a, b) in nets.keys():
        uids.add(a); uids.add(b)
    users_docs = await db.users.find({"user_id": {"$in": list(uids)}}, {"_id": 0}).to_list(100) if uids else []
    name_map = {u["user_id"]: u["name"] for u in users_docs}

    you_owe: List[dict] = []
    owed_to_you: List[dict] = []
    others: List[dict] = []
    for (debtor, creditor), amount in nets.items():
        entry = {
            "from_user_id": debtor,
            "from_name": name_map.get(debtor, "Someone"),
            "to_user_id": creditor,
            "to_name": name_map.get(creditor, "Someone"),
            "amount": round(amount, 2),
        }
        if debtor == user.user_id:
            you_owe.append(entry)
        elif creditor == user.user_id:
            owed_to_you.append(entry)
        else:
            others.append(entry)

    total_you_owe = round(sum(e["amount"] for e in you_owe), 2)
    total_owed_to_you = round(sum(e["amount"] for e in owed_to_you), 2)

    return {
        "you_owe": you_owe,
        "owed_to_you": owed_to_you,
        "others": others,
        "total_you_owe": total_you_owe,
        "total_owed_to_you": total_owed_to_you,
        "net": round(total_owed_to_you - total_you_owe, 2),
        "shared_categories_count": len(cat_share_map),
    }


@api_router.get("/balance-details")
async def get_balance_details(space_id: str, with_user_id: str, user: User = Depends(get_current_user)):
    """Detailed breakdown of items contributing to balance between current user and another."""
    space = await assert_space_member(space_id, user.user_id)
    if with_user_id not in space["member_ids"]:
        raise HTTPException(status_code=400, detail="Other user not in this space")

    cat_docs = await db.categories.find({"space_id": space_id}, {"_id": 0}).to_list(500)
    cat_share_map = {c["category_id"]: c.get("shared_with") or [] for c in cat_docs if len(c.get("shared_with") or []) >= 2}
    cat_name_map = {c["category_id"]: c["name"] for c in cat_docs}

    # Items where both me and other user are in the split group, paid by either
    relevant_cats = [cid for cid, members in cat_share_map.items() if user.user_id in members and with_user_id in members]
    items = []
    if relevant_cats:
        items = await db.items.find({
            "space_id": space_id,
            "category_id": {"$in": relevant_cats},
            "price": {"$ne": None, "$gt": 0},
            "created_by": {"$in": [user.user_id, with_user_id]},
        }, {"_id": 0}).sort("created_at", -1).to_list(2000)

    breakdown = []
    for it in items:
        members = cat_share_map[it["category_id"]]
        share = it["price"] / len(members)
        if it["created_by"] == user.user_id:
            # Other user owes me their share
            breakdown.append({
                "item_id": it["item_id"],
                "name": it["name"],
                "category_name": cat_name_map.get(it["category_id"], "?"),
                "category_id": it["category_id"],
                "price": it["price"],
                "share_each": round(share, 2),
                "split_count": len(members),
                "paid_by": user.user_id,
                "paid_by_name": user.name,
                "direction": "they_owe_you",
                "amount": round(share, 2),
                "created_at": it["created_at"].isoformat() if hasattr(it["created_at"], "isoformat") else it["created_at"],
                "photo_base64": it.get("photo_base64"),
            })
        else:
            other_name = next((m["name"] for m in await db.users.find({"user_id": with_user_id}, {"_id": 0}).to_list(1)), "Them")
            breakdown.append({
                "item_id": it["item_id"],
                "name": it["name"],
                "category_name": cat_name_map.get(it["category_id"], "?"),
                "category_id": it["category_id"],
                "price": it["price"],
                "share_each": round(share, 2),
                "split_count": len(members),
                "paid_by": with_user_id,
                "paid_by_name": other_name,
                "direction": "you_owe_them",
                "amount": round(share, 2),
                "created_at": it["created_at"].isoformat() if hasattr(it["created_at"], "isoformat") else it["created_at"],
                "photo_base64": it.get("photo_base64"),
            })

    settlements = await db.settlements.find({
        "space_id": space_id,
        "$or": [
            {"from_user_id": user.user_id, "to_user_id": with_user_id},
            {"from_user_id": with_user_id, "to_user_id": user.user_id},
        ],
    }, {"_id": 0}).sort("created_at", -1).to_list(500)

    return {"breakdown": breakdown, "settlements": [Settlement(**s).model_dump(mode='json') for s in settlements]}


# =========================
# Recurring Bills
# =========================
class Bill(TZAware):
    bill_id: str
    space_id: str
    name: str
    amount: float
    frequency: str  # monthly | weekly | yearly | once
    due_day: int  # day of month (1-31) for monthly, weekday (0-6) for weekly
    category_id: Optional[str] = None
    shared_with: List[str] = []
    created_by: str
    notes: Optional[str] = None
    icon: str = "Receipt"
    last_paid_date: Optional[str] = None  # ISO date string
    next_due_date: Optional[str] = None
    is_paid_current_period: bool = False
    created_at: datetime


class CreateBillRequest(BaseModel):
    space_id: str
    name: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0)
    frequency: str = "monthly"
    due_day: int = 1
    category_id: Optional[str] = None
    shared_with: List[str] = []
    notes: Optional[str] = None
    icon: str = "Receipt"


class UpdateBillRequest(BaseModel):
    name: Optional[str] = None
    amount: Optional[float] = None
    frequency: Optional[str] = None
    due_day: Optional[int] = None
    category_id: Optional[str] = None
    shared_with: Optional[List[str]] = None
    notes: Optional[str] = None
    icon: Optional[str] = None


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


@api_router.post("/bills", response_model=Bill)
async def create_bill(body: CreateBillRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    doc = {
        "bill_id": gen_id("bill"),
        "space_id": body.space_id,
        "name": body.name.strip(),
        "amount": body.amount,
        "frequency": body.frequency,
        "due_day": body.due_day,
        "category_id": body.category_id,
        "shared_with": body.shared_with,
        "created_by": user.user_id,
        "notes": body.notes,
        "icon": body.icon,
        "last_paid_date": None,
        "created_at": now_utc(),
    }
    await db.bills.insert_one(doc)
    out = await db.bills.find_one({"bill_id": doc["bill_id"]}, {"_id": 0})
    return Bill(**_compute_bill_state(out))


@api_router.get("/bills", response_model=List[Bill])
async def list_bills(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    docs = await db.bills.find({"space_id": space_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return [Bill(**_compute_bill_state(d)) for d in docs]


@api_router.patch("/bills/{bill_id}", response_model=Bill)
async def update_bill(bill_id: str, body: UpdateBillRequest, user: User = Depends(get_current_user)):
    doc = await db.bills.find_one({"bill_id": bill_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Bill not found")
    await assert_space_member(doc["space_id"], user.user_id)
    payload = body.dict(exclude_unset=True)
    if payload:
        await db.bills.update_one({"bill_id": bill_id}, {"$set": payload})
    out = await db.bills.find_one({"bill_id": bill_id}, {"_id": 0})
    return Bill(**_compute_bill_state(out))


@api_router.post("/bills/{bill_id}/pay", response_model=Bill)
async def pay_bill(bill_id: str, user: User = Depends(get_current_user)):
    doc = await db.bills.find_one({"bill_id": bill_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Bill not found")
    await assert_space_member(doc["space_id"], user.user_id)
    today_iso = now_utc().date().isoformat()
    await db.bills.update_one({"bill_id": bill_id}, {"$set": {"last_paid_date": today_iso}})
    # Auto-create an item in the bill's category if set, so it shows in finance & splits
    if doc.get("category_id"):
        cat = await db.categories.find_one({"category_id": doc["category_id"]}, {"_id": 0})
        if cat and cat["space_id"] == doc["space_id"]:
            await db.items.insert_one({
                "item_id": gen_id("item"),
                "space_id": doc["space_id"],
                "category_id": doc["category_id"],
                "name": f"{doc['name']} ({today_iso})",
                "photo_base64": None,
                "status": "available",
                "quantity": 1,
                "unit": None,
                "price": doc["amount"],
                "purchase_date": today_iso,
                "expiry_date": None,
                "notes": "Recurring bill payment",
                "fields": {},
                "created_by": user.user_id,
                "created_by_name": user.name,
                "created_at": now_utc(),
                "updated_at": now_utc(),
            })
    out = await db.bills.find_one({"bill_id": bill_id}, {"_id": 0})
    await record_activity(doc["space_id"], user, "paid", "bill", out["bill_id"], out["name"])
    return Bill(**_compute_bill_state(out))


@api_router.delete("/bills/{bill_id}")
async def delete_bill(bill_id: str, user: User = Depends(get_current_user)):
    doc = await db.bills.find_one({"bill_id": bill_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Bill not found")
    await assert_space_member(doc["space_id"], user.user_id)
    await db.bills.delete_one({"bill_id": bill_id})
    return {"success": True}


# =========================
# Roommate Agreement
# =========================
class AgreementSignature(BaseModel):
    user_id: str
    user_name: str
    signed_at: datetime


class Agreement(TZAware):
    space_id: str
    text: str
    sections: List[Dict[str, Any]] = []  # [{title, body}]
    signatures: List[AgreementSignature] = []
    updated_at: Optional[datetime] = None
    updated_by: str


class SaveAgreementRequest(BaseModel):
    text: str = ""
    sections: List[Dict[str, Any]] = []


@api_router.get("/agreement", response_model=Optional[Agreement])
async def get_agreement(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    doc = await db.agreements.find_one({"space_id": space_id}, {"_id": 0})
    return Agreement(**doc) if doc else None


@api_router.put("/agreement", response_model=Agreement)
async def save_agreement(body: SaveAgreementRequest, space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    doc = {
        "space_id": space_id,
        "text": body.text,
        "sections": body.sections,
        "signatures": [],  # reset on edit
        "updated_at": now_utc(),
        "updated_by": user.user_id,
    }
    await db.agreements.update_one({"space_id": space_id}, {"$set": doc}, upsert=True)
    out = await db.agreements.find_one({"space_id": space_id}, {"_id": 0})
    return Agreement(**out)


@api_router.post("/agreement/sign", response_model=Agreement)
async def sign_agreement(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    doc = await db.agreements.find_one({"space_id": space_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="No agreement to sign")
    sigs = [s for s in doc.get("signatures", []) if s["user_id"] != user.user_id]
    sigs.append({"user_id": user.user_id, "user_name": user.name, "signed_at": now_utc()})
    await db.agreements.update_one({"space_id": space_id}, {"$set": {"signatures": sigs}})
    out = await db.agreements.find_one({"space_id": space_id}, {"_id": 0})
    return Agreement(**out)


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


@api_router.get("/reports/finance")
async def finance_report(space_id: str, period: str = "this_month", user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    currency = space.get("currency", "USD")
    start, end, label = _period_range(period)

    # Items with prices in window
    items = await db.items.find({
        "space_id": space_id,
        "created_at": {"$gte": start, "$lt": end} if period != "all" else {"$lte": end},
        "price": {"$ne": None, "$gt": 0},
    }, {"_id": 0}).to_list(20000)

    cats = await db.categories.find({"space_id": space_id}, {"_id": 0}).to_list(500)
    cat_name = {c["category_id"]: c["name"] for c in cats}
    cat_tint = {c["category_id"]: c.get("tint", "mint") for c in cats}

    members = await db.users.find({"user_id": {"$in": space["member_ids"]}}, {"_id": 0, "password_hash": 0}).to_list(100)
    member_name = {m["user_id"]: m["name"] for m in members}

    total = sum(float(it["price"]) for it in items)
    count = len(items)
    avg_per_item = (total / count) if count else 0
    largest = max((float(it["price"]) for it in items), default=0)
    smallest = min((float(it["price"]) for it in items), default=0)

    # By category
    by_cat: Dict[str, Dict[str, Any]] = {}
    for it in items:
        cid = it["category_id"]
        d = by_cat.setdefault(cid, {"category_id": cid, "name": cat_name.get(cid, "?"), "tint": cat_tint.get(cid, "mint"), "total": 0.0, "count": 0})
        d["total"] += float(it["price"]); d["count"] += 1
    by_cat_list = sorted(by_cat.values(), key=lambda d: d["total"], reverse=True)
    for d in by_cat_list:
        d["pct"] = round((d["total"] / total) * 100, 1) if total else 0
        d["total"] = round(d["total"], 2)

    # By member (who paid)
    by_mem: Dict[str, Dict[str, Any]] = {}
    for it in items:
        mid = it.get("created_by")
        d = by_mem.setdefault(mid, {"user_id": mid, "name": member_name.get(mid, "Someone"), "total": 0.0, "count": 0})
        d["total"] += float(it["price"]); d["count"] += 1
    by_mem_list = sorted(by_mem.values(), key=lambda d: d["total"], reverse=True)
    for d in by_mem_list:
        d["pct"] = round((d["total"] / total) * 100, 1) if total else 0
        d["total"] = round(d["total"], 2)

    # Daily trend (date -> total) only for periods <= 6 months
    daily: Dict[str, float] = {}
    for it in items:
        d = it.get("created_at")
        if isinstance(d, datetime):
            key = d.date().isoformat()
        else:
            try: key = datetime.fromisoformat(str(d)).date().isoformat()
            except Exception: continue
        daily[key] = daily.get(key, 0) + float(it["price"])
    daily_list = [{"date": k, "total": round(v, 2)} for k, v in sorted(daily.items())]

    # Monthly trend (last 12 months relative to end)
    monthly: Dict[str, float] = {}
    for it in items:
        d = it.get("created_at")
        if not isinstance(d, datetime): continue
        key = d.strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + float(it["price"])
    monthly_list = [{"month": k, "total": round(v, 2)} for k, v in sorted(monthly.items())]

    # Top items
    items_sorted = sorted(items, key=lambda it: float(it["price"]), reverse=True)
    top_items = [{
        "item_id": it["item_id"],
        "name": it["name"],
        "category_name": cat_name.get(it["category_id"], "?"),
        "price": round(float(it["price"]), 2),
        "purchased_by": member_name.get(it.get("created_by"), "Someone"),
        "created_at": it["created_at"].isoformat() if isinstance(it["created_at"], datetime) else str(it["created_at"]),
    } for it in items_sorted[:20]]

    # All items (raw data for sheets export)
    all_items_raw = [{
        "item_id": it["item_id"],
        "name": it["name"],
        "category_name": cat_name.get(it["category_id"], "?"),
        "price": round(float(it["price"]), 2),
        "quantity": it.get("quantity") or 1,
        "purchased_by": member_name.get(it.get("created_by"), "Someone"),
        "purchase_date": it.get("purchase_date") or "",
        "expiry_date": it.get("expiry_date") or "",
        "status": it.get("status", "available"),
        "created_at": it["created_at"].isoformat() if isinstance(it["created_at"], datetime) else str(it["created_at"]),
    } for it in items_sorted]

    # Bills in window (all visible)
    bill_docs = await db.bills.find({"space_id": space_id}, {"_id": 0}).to_list(500)
    bills_out = []
    for b in bill_docs:
        b = _compute_bill_state(b)
        bills_out.append({
            "bill_id": b["bill_id"],
            "name": b["name"],
            "amount": round(float(b["amount"]), 2),
            "frequency": b["frequency"],
            "due_day": b["due_day"],
            "is_paid_current_period": b["is_paid_current_period"],
            "next_due_date": b.get("next_due_date"),
            "last_paid_date": b.get("last_paid_date"),
            "category_name": cat_name.get(b.get("category_id"), "") if b.get("category_id") else "",
        })

    # Settlements in window
    settle_docs = await db.settlements.find({
        "space_id": space_id,
        "created_at": {"$gte": start, "$lt": end} if period != "all" else {"$lte": end},
    }, {"_id": 0}).sort("created_at", -1).to_list(500)
    settle_out = [{
        "settlement_id": s["settlement_id"],
        "from_name": s["from_name"],
        "to_name": s["to_name"],
        "amount": round(float(s["amount"]), 2),
        "note": s.get("note") or "",
        "created_at": s["created_at"].isoformat() if isinstance(s["created_at"], datetime) else str(s["created_at"]),
    } for s in settle_docs]

    # Insights (plain English)
    insights: List[str] = []
    if count == 0:
        insights.append("No spending logged in this period yet. Start scanning receipts or adding items with prices to unlock insights.")
    else:
        insights.append(f"You logged {count} purchases totalling {total:.2f} {currency}.")
        if by_cat_list:
            top = by_cat_list[0]
            insights.append(f"{top['name']} was your top category at {top['pct']}% of spend.")
        if by_mem_list and len(by_mem_list) > 1:
            top_m = by_mem_list[0]
            insights.append(f"{top_m['name']} paid the most ({top_m['pct']}%). Use the Splits view to see what's owed.")
        if avg_per_item > 0:
            insights.append(f"Average item price was {avg_per_item:.2f} {currency}.")
        # Compare to previous equivalent period
        if period in ("this_month",):
            prev_start = (start.replace(year=start.year - 1, month=12, day=1)
                          if start.month == 1 else start.replace(month=start.month - 1))
            prev_total = 0.0
            async for r in db.items.aggregate([
                {"$match": {"space_id": space_id, "created_at": {"$gte": prev_start, "$lt": start}, "price": {"$ne": None, "$gt": 0}}},
                {"$group": {"_id": None, "total": {"$sum": "$price"}}},
            ]):
                prev_total = float(r.get("total") or 0)
            if prev_total > 0:
                delta = total - prev_total
                pct = (delta / prev_total) * 100
                if abs(pct) >= 5:
                    direction = "up" if delta > 0 else "down"
                    insights.append(f"Spending is {direction} {abs(pct):.0f}% vs last month ({prev_total:.2f} {currency}).")

    return {
        "period_key": period,
        "period_label": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "currency": currency,
        "totals": {
            "total": round(total, 2),
            "count": count,
            "avg_per_item": round(avg_per_item, 2),
            "largest": round(largest, 2),
            "smallest": round(smallest, 2),
        },
        "by_category": by_cat_list,
        "by_member": by_mem_list,
        "daily": daily_list,
        "monthly": monthly_list,
        "top_items": top_items,
        "all_items": all_items_raw,
        "bills": bills_out,
        "settlements": settle_out,
        "insights": insights,
    }


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


class HouseholdRole(BaseModel):
    role_id: str
    space_id: str
    key: str
    name: str
    icon: str = "User"
    color: str = "mint"
    category: str = "family"  # 'family' | 'staff'
    is_default: bool = False
    perms: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class CreateRoleRequest(BaseModel):
    space_id: str
    name: str
    icon: str = "User"
    color: str = "mint"
    category: str = "family"
    perms: Dict[str, Any] = Field(default_factory=dict)


class UpdateRoleRequest(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    category: Optional[str] = None
    perms: Optional[Dict[str, Any]] = None


class FamilyMember(BaseModel):
    member_id: str
    space_id: str
    name: str
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    photo_base64: Optional[str] = None
    age: Optional[int] = None
    birthday: Optional[str] = None
    school: Optional[str] = None
    allergies: Optional[str] = None
    medical_notes: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class CreateFamilyMemberRequest(BaseModel):
    space_id: str
    name: str
    role_id: Optional[str] = None
    photo_base64: Optional[str] = None
    age: Optional[int] = None
    birthday: Optional[str] = None
    school: Optional[str] = None
    allergies: Optional[str] = None
    medical_notes: Optional[str] = None
    notes: Optional[str] = None


class UpdateFamilyMemberRequest(BaseModel):
    name: Optional[str] = None
    role_id: Optional[str] = None
    photo_base64: Optional[str] = None
    age: Optional[int] = None
    birthday: Optional[str] = None
    school: Optional[str] = None
    allergies: Optional[str] = None
    medical_notes: Optional[str] = None
    notes: Optional[str] = None


class StaffMember(BaseModel):
    staff_id: str
    space_id: str
    name: str
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    photo_base64: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    id_number: Optional[str] = None
    salary: Optional[float] = None
    pay_cycle: str = "monthly"  # monthly | weekly | daily
    salary_currency: Optional[str] = None
    off_day: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    active: bool = True
    notes: Optional[str] = None
    user_id: Optional[str] = None  # set when staff signs up to the app
    invite_code: Optional[str] = None
    permissions: Dict[str, bool] = Field(default_factory=dict)
    requires_wage_confirmation: bool = False  # if True, staff must confirm receipt of payment
    created_at: datetime


class CreateStaffRequest(BaseModel):
    space_id: str
    name: str
    role_id: Optional[str] = None
    photo_base64: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    id_number: Optional[str] = None
    salary: Optional[float] = None
    pay_cycle: str = "monthly"
    salary_currency: Optional[str] = None
    off_day: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    active: bool = True
    notes: Optional[str] = None
    requires_wage_confirmation: bool = False


class UpdateStaffRequest(BaseModel):
    name: Optional[str] = None
    role_id: Optional[str] = None
    photo_base64: Optional[str] = None
    phone: Optional[str] = None
    emergency_contact: Optional[str] = None
    id_number: Optional[str] = None
    salary: Optional[float] = None
    pay_cycle: Optional[str] = None
    salary_currency: Optional[str] = None
    off_day: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    active: Optional[bool] = None
    notes: Optional[str] = None
    requires_wage_confirmation: Optional[bool] = None


class HandbookEntry(BaseModel):
    entry_id: str
    space_id: str
    title: str
    body: str
    icon: str = "BookOpen"
    color: str = "mint"
    photo_base64: Optional[str] = None
    sort: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


class CreateHandbookEntryRequest(BaseModel):
    space_id: str
    title: str
    body: str
    icon: str = "BookOpen"
    color: str = "mint"
    photo_base64: Optional[str] = None
    sort: int = 0


class UpdateHandbookEntryRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    photo_base64: Optional[str] = None
    sort: Optional[int] = None


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


# ----- Roles -----
@api_router.get("/household/roles", response_model=List[HouseholdRole])
async def list_roles(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    await _ensure_default_roles(space_id)
    docs = await db.household_roles.find({"space_id": space_id}, {"_id": 0}).sort("created_at", 1).to_list(200)
    return [HouseholdRole(**d) for d in docs]


@api_router.post("/household/roles", response_model=HouseholdRole)
async def create_role(body: CreateRoleRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    cat = body.category if body.category in ("family", "staff") else "family"
    doc = {
        "role_id": gen_id("role"),
        "space_id": body.space_id,
        "key": body.name.lower().replace(" ", "_")[:20],
        "name": body.name.strip(),
        "icon": body.icon or "User",
        "color": body.color or "mint",
        "category": cat,
        "is_default": False,
        "perms": body.perms or {},
        "created_at": now_utc(),
    }
    await db.household_roles.insert_one(doc)
    doc.pop("_id", None)
    return HouseholdRole(**doc)


@api_router.patch("/household/roles/{role_id}", response_model=HouseholdRole)
async def update_role(role_id: str, body: UpdateRoleRequest, user: User = Depends(get_current_user)):
    role = await db.household_roles.find_one({"role_id": role_id}, {"_id": 0})
    if not role:
        raise HTTPException(404, "Role not found")
    await assert_space_member(role["space_id"], user.user_id)
    updates: Dict[str, Any] = {}
    for k in ("name", "icon", "color", "category", "perms"):
        v = getattr(body, k)
        if v is not None:
            updates[k] = v
    if updates:
        await db.household_roles.update_one({"role_id": role_id}, {"$set": updates})
    out = await db.household_roles.find_one({"role_id": role_id}, {"_id": 0})
    return HouseholdRole(**out)


@api_router.delete("/household/roles/{role_id}")
async def delete_role(role_id: str, user: User = Depends(get_current_user)):
    role = await db.household_roles.find_one({"role_id": role_id}, {"_id": 0})
    if not role:
        raise HTTPException(404, "Role not found")
    await assert_space_member(role["space_id"], user.user_id)
    if role.get("is_default"):
        raise HTTPException(400, "Default roles cannot be deleted; rename or hide instead.")
    # detach from family + staff
    await db.family_members.update_many({"role_id": role_id}, {"$set": {"role_id": None, "role_name": None}})
    await db.staff_members.update_many({"role_id": role_id}, {"$set": {"role_id": None, "role_name": None}})
    await db.household_roles.delete_one({"role_id": role_id})
    return {"ok": True}


async def _attach_role_name(doc: Dict[str, Any]) -> Dict[str, Any]:
    rid = doc.get("role_id")
    if rid:
        r = await db.household_roles.find_one({"role_id": rid}, {"_id": 0, "name": 1})
        doc["role_name"] = r["name"] if r else None
    else:
        doc["role_name"] = None
    return doc


# ----- Family members -----
@api_router.get("/household/family", response_model=List[FamilyMember])
async def list_family(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    docs = await db.family_members.find({"space_id": space_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    out = [await _attach_role_name(d) for d in docs]
    return [FamilyMember(**d) for d in out]


@api_router.post("/household/family", response_model=FamilyMember)
async def create_family_member(body: CreateFamilyMemberRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    doc = {
        "member_id": gen_id("fam"),
        "space_id": body.space_id,
        "name": body.name.strip(),
        "role_id": body.role_id,
        "photo_base64": body.photo_base64,
        "age": body.age,
        "birthday": body.birthday,
        "school": body.school,
        "allergies": body.allergies,
        "medical_notes": body.medical_notes,
        "notes": body.notes,
        "created_at": now_utc(),
    }
    await db.family_members.insert_one(doc)
    doc.pop("_id", None)
    await _attach_role_name(doc)
    return FamilyMember(**doc)


@api_router.patch("/household/family/{member_id}", response_model=FamilyMember)
async def update_family_member(member_id: str, body: UpdateFamilyMemberRequest, user: User = Depends(get_current_user)):
    fm = await db.family_members.find_one({"member_id": member_id}, {"_id": 0})
    if not fm:
        raise HTTPException(404, "Family member not found")
    await assert_space_member(fm["space_id"], user.user_id)
    updates: Dict[str, Any] = {}
    for k in ("name", "role_id", "photo_base64", "age", "birthday", "school", "allergies", "medical_notes", "notes"):
        v = getattr(body, k)
        if v is not None:
            updates[k] = v
    if updates:
        await db.family_members.update_one({"member_id": member_id}, {"$set": updates})
    out = await db.family_members.find_one({"member_id": member_id}, {"_id": 0})
    await _attach_role_name(out)
    return FamilyMember(**out)


@api_router.delete("/household/family/{member_id}")
async def delete_family_member(member_id: str, user: User = Depends(get_current_user)):
    fm = await db.family_members.find_one({"member_id": member_id}, {"_id": 0})
    if not fm:
        raise HTTPException(404, "Family member not found")
    await assert_space_member(fm["space_id"], user.user_id)
    await db.family_members.delete_one({"member_id": member_id})
    return {"ok": True}


# ----- Staff -----
@api_router.get("/household/staff", response_model=List[StaffMember])
async def list_staff(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    docs = await db.staff_members.find({"space_id": space_id}, {"_id": 0}).sort("created_at", 1).to_list(500)
    # Backfill legacy staff docs missing invite_code / active / permissions
    for d in docs:
        updates: Dict[str, Any] = {}
        if not d.get("invite_code"):
            d["invite_code"] = _gen_staff_invite_code()
            updates["invite_code"] = d["invite_code"]
        if "active" not in d:
            d["active"] = True
            updates["active"] = True
        if not d.get("permissions"):
            d["permissions"] = DEFAULT_STAFF_PERMS.copy()
            updates["permissions"] = d["permissions"]
        if updates:
            await db.staff_members.update_one({"staff_id": d["staff_id"]}, {"$set": updates})
    out = [await _attach_role_name(d) for d in docs]
    return [StaffMember(**d) for d in out]


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
}


class UpdateStaffPermissionsRequest(BaseModel):
    permissions: Dict[str, bool]


def _gen_staff_invite_code() -> str:
    return secrets.token_hex(3).upper()


@api_router.post("/household/staff", response_model=StaffMember)
async def create_staff(body: CreateStaffRequest, user: User = Depends(get_current_user)):
    space = await assert_space_member(body.space_id, user.user_id)
    doc = {
        "staff_id": gen_id("staff"),
        "space_id": body.space_id,
        "name": body.name.strip(),
        "role_id": body.role_id,
        "photo_base64": body.photo_base64,
        "phone": body.phone,
        "emergency_contact": body.emergency_contact,
        "id_number": body.id_number,
        "salary": body.salary,
        "pay_cycle": body.pay_cycle or "monthly",
        "salary_currency": body.salary_currency or (space.get("currency") if isinstance(space, dict) else None) or "USD",
        "off_day": body.off_day,
        "start_date": body.start_date,
        "end_date": body.end_date,
        "active": True if body.active is None else bool(body.active),
        "notes": body.notes,
        "requires_wage_confirmation": bool(body.requires_wage_confirmation),
        "user_id": None,
        "invite_code": _gen_staff_invite_code(),
        "permissions": DEFAULT_STAFF_PERMS.copy(),
        "created_at": now_utc(),
    }
    await db.staff_members.insert_one(doc)
    doc.pop("_id", None)
    await _attach_role_name(doc)
    return StaffMember(**doc)


@api_router.patch("/household/staff/{staff_id}/permissions", response_model=StaffMember)
async def update_staff_perms(staff_id: str, body: UpdateStaffPermissionsRequest, user: User = Depends(get_current_user)):
    s = await db.staff_members.find_one({"staff_id": staff_id}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Staff not found")
    await assert_space_member(s["space_id"], user.user_id)
    space = await db.family_spaces.find_one({"space_id": s["space_id"]}, {"_id": 0})
    if not space or space.get("owner_id") != user.user_id:
        raise HTTPException(403, "Only the space owner can change staff permissions")
    merged = {**DEFAULT_STAFF_PERMS, **(s.get("permissions") or {}), **(body.permissions or {})}
    await db.staff_members.update_one({"staff_id": staff_id}, {"$set": {"permissions": merged}})
    out = await db.staff_members.find_one({"staff_id": staff_id}, {"_id": 0})
    await _attach_role_name(out)
    return StaffMember(**out)


class JoinStaffRequest(BaseModel):
    invite_code: str


@api_router.post("/household/staff/join")
async def join_staff(body: JoinStaffRequest, user: User = Depends(get_current_user)):
    code = (body.invite_code or "").strip().upper()
    if not code:
        raise HTTPException(400, "Invite code required")
    s = await db.staff_members.find_one({"invite_code": code}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Invalid invite code")
    if s.get("user_id") and s["user_id"] != user.user_id:
        raise HTTPException(400, "This staff profile is already linked to another account")
    await db.staff_members.update_one({"staff_id": s["staff_id"]}, {"$set": {"user_id": user.user_id}})
    space = await db.family_spaces.find_one({"space_id": s["space_id"]}, {"_id": 0})
    if space and user.user_id not in (space.get("member_ids") or []):
        await db.family_spaces.update_one({"space_id": s["space_id"]}, {"$addToSet": {"member_ids": user.user_id}})
    # Retro-notify: send notifications for any pending contracts that were assigned
    # to this staff record BEFORE the user joined. Idempotent — only creates
    # notifications that don't already exist.
    try:
        pending = await db.contracts.find({
            "space_id": s["space_id"],
            "assigned_staff_id": s["staff_id"],
            "status": {"$ne": "void"},
            "staff_signature": None,
        }, {"_id": 0}).to_list(100)
        for c in pending:
            exists = await db.notifications.find_one({
                "user_id": user.user_id,
                "kind": "contract_assigned",
                "data.contract_id": c["contract_id"],
            })
            if exists:
                continue
            await notify_user(
                user_id=user.user_id,
                space_id=s["space_id"],
                kind="contract_assigned",
                title=f"Please review & sign: {c.get('title')}",
                body=f"An agreement ({c.get('template_kind')}) is waiting for your signature.",
                data={"contract_id": c["contract_id"]},
            )
    except Exception as e:
        logger.warning(f"Could not backfill contract notifications on staff join: {e}")
    # Realtime: tell the space "a new member just joined" so the owner refreshes the staff list
    await emit_space_event(s["space_id"], "staff", "joined", {"staff_id": s["staff_id"], "user_id": user.user_id})
    return {"ok": True, "space_id": s["space_id"], "staff_id": s["staff_id"]}


@api_router.get("/spaces/{space_id}/my_role")
async def my_role(space_id: str, user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    is_owner = space.get("owner_id") == user.user_id
    staff = await db.staff_members.find_one({"space_id": space_id, "user_id": user.user_id}, {"_id": 0})
    if staff:
        return {"role": "staff", "staff_id": staff["staff_id"], "permissions": {**DEFAULT_STAFF_PERMS, **(staff.get("permissions") or {})}}
    return {"role": "owner" if is_owner else "member", "staff_id": None, "permissions": {}}


# =========================
# Phase 3 — Payroll (wages as finance items)
# =========================
class StaffPayment(BaseModel):
    payment_id: str
    space_id: str
    staff_id: str
    staff_name: Optional[str] = None
    period: str
    gross: float
    advances: float = 0.0
    deductions: float = 0.0
    bonus: float = 0.0
    net: float
    currency: str = "USD"
    receipt_photo: Optional[str] = None
    notes: Optional[str] = None
    item_id: Optional[str] = None
    paid_at: datetime
    confirmed_at: Optional[datetime] = None
    confirmed_by_staff_id: Optional[str] = None
    requires_confirmation: bool = False


class ConfirmPaymentRequest(BaseModel):
    note: Optional[str] = None


class CreateStaffPaymentRequest(BaseModel):
    space_id: str
    staff_id: str
    period: Optional[str] = None
    gross: Optional[float] = None
    advances: float = 0.0
    deductions: float = 0.0
    bonus: float = 0.0
    receipt_photo: Optional[str] = None
    notes: Optional[str] = None


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


@api_router.get("/household/payroll", response_model=List[StaffPayment])
async def list_payroll(space_id: str, staff_id: Optional[str] = None, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    q: Dict[str, Any] = {"space_id": space_id}
    if staff_id:
        q["staff_id"] = staff_id
    docs = await db.staff_payments.find(q, {"_id": 0}).sort("paid_at", -1).to_list(2000)
    if docs:
        staff_ids = list({d["staff_id"] for d in docs})
        staff = await db.staff_members.find({"staff_id": {"$in": staff_ids}}, {"_id": 0}).to_list(500)
        name_by_id = {s["staff_id"]: s["name"] for s in staff}
        for d in docs:
            d["staff_name"] = name_by_id.get(d["staff_id"])
    return [StaffPayment(**d) for d in docs]


@api_router.post("/household/payroll", response_model=StaffPayment)
async def create_payroll(body: CreateStaffPaymentRequest, user: User = Depends(get_current_user)):
    space = await assert_space_member(body.space_id, user.user_id)
    staff = await db.staff_members.find_one({"staff_id": body.staff_id, "space_id": body.space_id}, {"_id": 0})
    if not staff:
        raise HTTPException(404, "Staff not found")
    gross = body.gross if body.gross is not None else float(staff.get("salary") or 0)
    net = gross + float(body.bonus or 0) - float(body.advances or 0) - float(body.deductions or 0)
    cycle = staff.get("pay_cycle", "monthly")
    today = datetime.now(timezone.utc)
    period = body.period
    if not period:
        if cycle == "monthly":
            period = today.strftime("%Y-%m")
        elif cycle == "weekly":
            period = today.strftime("%Y-W%V")
        else:
            period = today.strftime("%Y-%m-%d")
    cat_id = await _ensure_wages_category(body.space_id, user.user_id)
    item_doc = {
        "item_id": gen_id("item"),
        "space_id": body.space_id,
        "category_id": cat_id,
        "name": f"Salary — {staff['name']} ({period})",
        "price": round(net, 2),
        "quantity": 1,
        "status": "available",
        "purchase_date": today.strftime("%Y-%m-%d"),
        "expiry_date": None,
        "photo_base64": body.receipt_photo,
        "created_by": user.user_id,
        "created_at": today,
        "shared_with": [],
        "split_with": [],
        "fields": {},
    }
    await db.items.insert_one(item_doc)
    payment = {
        "payment_id": gen_id("pay"),
        "space_id": body.space_id,
        "staff_id": body.staff_id,
        "staff_name": staff["name"],
        "period": period,
        "gross": round(gross, 2),
        "advances": round(float(body.advances or 0), 2),
        "deductions": round(float(body.deductions or 0), 2),
        "bonus": round(float(body.bonus or 0), 2),
        "net": round(net, 2),
        "currency": staff.get("salary_currency") or space.get("currency") or "USD",
        "receipt_photo": body.receipt_photo,
        "notes": body.notes,
        "item_id": item_doc["item_id"],
        "paid_at": today,
        "requires_confirmation": bool(staff.get("requires_wage_confirmation")),
        "confirmed_at": None,
        "confirmed_by_staff_id": None,
    }
    await db.staff_payments.insert_one(payment)
    payment.pop("_id", None)
    # Notify the staff member (if linked)
    if staff.get("user_id"):
        confirm_blurb = "  Tap to confirm receipt." if payment["requires_confirmation"] else ""
        await _create_notification(
            space_id=body.space_id,
            user_id=staff["user_id"],
            kind="wage_paid",
            title=f"Wage received · {period}",
            body=f"{staff['name']}, your {cycle} pay of {payment['currency']} {payment['net']:.2f} was logged by the owner.{confirm_blurb}",
            data={"payment_id": payment["payment_id"], "period": period, "net": payment["net"], "currency": payment["currency"], "requires_confirmation": payment["requires_confirmation"]},
        )
    return StaffPayment(**payment)


@api_router.post("/household/payroll/{payment_id}/confirm", response_model=StaffPayment)
async def confirm_payroll(payment_id: str, body: ConfirmPaymentRequest, user: User = Depends(get_current_user)):
    p = await db.staff_payments.find_one({"payment_id": payment_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Payment not found")
    # Only the linked staff (or owner override) can confirm
    staff = await db.staff_members.find_one({"staff_id": p["staff_id"]}, {"_id": 0})
    if not staff:
        raise HTTPException(404, "Staff not found")
    if staff.get("user_id") != user.user_id:
        # Allow owner to also confirm on staff's behalf
        space = await db.family_spaces.find_one({"space_id": p["space_id"]}, {"_id": 0})
        if not space or space.get("owner_id") != user.user_id:
            raise HTTPException(403, "Only this staff member or the space owner can confirm")
    updates = {"confirmed_at": now_utc(), "confirmed_by_staff_id": staff["staff_id"]}
    if body.note:
        updates["notes"] = (p.get("notes") or "") + ("\n" if p.get("notes") else "") + f"[Confirmed] {body.note}"
    await db.staff_payments.update_one({"payment_id": payment_id}, {"$set": updates})
    out = await db.staff_payments.find_one({"payment_id": payment_id}, {"_id": 0})
    # Notify owner that confirmation happened
    space = await db.family_spaces.find_one({"space_id": p["space_id"]}, {"_id": 0})
    if space and staff.get("user_id") == user.user_id and space.get("owner_id") != user.user_id:
        await _create_notification(
            space_id=p["space_id"],
            user_id=space["owner_id"],
            kind="wage_confirmed",
            title=f"{staff['name']} confirmed receipt",
            body=f"{p['period']} · {p['currency']} {p['net']:.2f}",
            data={"payment_id": payment_id},
        )
    return StaffPayment(**out)


@api_router.delete("/household/payroll/{payment_id}")
async def delete_payroll(payment_id: str, user: User = Depends(get_current_user)):
    p = await db.staff_payments.find_one({"payment_id": payment_id}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Payment not found")
    await assert_space_member(p["space_id"], user.user_id)
    await db.staff_payments.delete_one({"payment_id": payment_id})
    if p.get("item_id"):
        await db.items.delete_one({"item_id": p["item_id"]})
    return {"ok": True}


@api_router.get("/household/staff/me")
async def staff_me(space_id: str, user: User = Depends(get_current_user)):
    s = await db.staff_members.find_one({"space_id": space_id, "user_id": user.user_id}, {"_id": 0})
    if not s:
        raise HTTPException(404, "You are not linked as staff in this space")
    await _attach_role_name(s)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tasks = await db.task_templates.find(
        {"space_id": space_id, "$or": [{"staff_id": s["staff_id"]}, {"role_id": s.get("role_id")}, {"staff_id": None, "role_id": None}]},
        {"_id": 0},
    ).to_list(500)
    comps = await db.task_completions.find({"space_id": space_id, "date": today_str}, {"_id": 0}).to_list(500)
    comp_by_task = {c["task_id"]: c for c in comps}
    today_tasks: List[Dict[str, Any]] = []
    for t in tasks:
        if _task_due_on(t, today_str):
            today_tasks.append({**t, "completed_today": t["task_id"] in comp_by_task, "completion": comp_by_task.get(t["task_id"])})
    att = await db.attendance_logs.find({"space_id": space_id, "staff_id": s["staff_id"]}, {"_id": 0}).sort("date", -1).to_list(60)
    perms = {**DEFAULT_STAFF_PERMS, **(s.get("permissions") or {})}
    payments: List[Dict[str, Any]] = []
    if perms.get("view_wage_amount"):
        payments = await db.staff_payments.find({"space_id": space_id, "staff_id": s["staff_id"]}, {"_id": 0}).sort("paid_at", -1).to_list(100)
    return {"staff": s, "permissions": perms, "today_tasks": today_tasks, "attendance": att, "payments": payments}


@api_router.patch("/household/staff/{staff_id}", response_model=StaffMember)
async def update_staff(staff_id: str, body: UpdateStaffRequest, user: User = Depends(get_current_user)):
    s = await db.staff_members.find_one({"staff_id": staff_id}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Staff member not found")
    await assert_space_member(s["space_id"], user.user_id)
    updates: Dict[str, Any] = {}
    for k in ("name", "role_id", "photo_base64", "phone", "emergency_contact", "id_number", "salary", "pay_cycle", "salary_currency", "off_day", "start_date", "end_date", "active", "notes"):
        v = getattr(body, k)
        if v is not None:
            updates[k] = v
    if updates:
        await db.staff_members.update_one({"staff_id": staff_id}, {"$set": updates})
    out = await db.staff_members.find_one({"staff_id": staff_id}, {"_id": 0})
    await _attach_role_name(out)
    return StaffMember(**out)


@api_router.delete("/household/staff/{staff_id}")
async def delete_staff(staff_id: str, user: User = Depends(get_current_user)):
    s = await db.staff_members.find_one({"staff_id": staff_id}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Staff member not found")
    await assert_space_member(s["space_id"], user.user_id)
    await db.staff_members.delete_one({"staff_id": staff_id})
    return {"ok": True}


# ----- Handbook -----
@api_router.get("/household/handbook", response_model=List[HandbookEntry])
async def list_handbook(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    docs = await db.handbook_entries.find({"space_id": space_id}, {"_id": 0}).sort([("sort", 1), ("created_at", 1)]).to_list(500)
    return [HandbookEntry(**d) for d in docs]


@api_router.post("/household/handbook", response_model=HandbookEntry)
async def create_handbook(body: CreateHandbookEntryRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    now = now_utc()
    doc = {
        "entry_id": gen_id("hb"),
        "space_id": body.space_id,
        "title": body.title.strip(),
        "body": body.body,
        "icon": body.icon or "BookOpen",
        "color": body.color or "mint",
        "photo_base64": body.photo_base64,
        "sort": body.sort or 0,
        "created_at": now,
        "updated_at": now,
    }
    await db.handbook_entries.insert_one(doc)
    doc.pop("_id", None)
    return HandbookEntry(**doc)


@api_router.patch("/household/handbook/{entry_id}", response_model=HandbookEntry)
async def update_handbook(entry_id: str, body: UpdateHandbookEntryRequest, user: User = Depends(get_current_user)):
    e = await db.handbook_entries.find_one({"entry_id": entry_id}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Handbook entry not found")
    await assert_space_member(e["space_id"], user.user_id)
    updates: Dict[str, Any] = {}
    for k in ("title", "body", "icon", "color", "photo_base64", "sort"):
        v = getattr(body, k)
        if v is not None:
            updates[k] = v
    if updates:
        updates["updated_at"] = now_utc()
        await db.handbook_entries.update_one({"entry_id": entry_id}, {"$set": updates})
    out = await db.handbook_entries.find_one({"entry_id": entry_id}, {"_id": 0})
    return HandbookEntry(**out)


@api_router.delete("/household/handbook/{entry_id}")
async def delete_handbook(entry_id: str, user: User = Depends(get_current_user)):
    e = await db.handbook_entries.find_one({"entry_id": entry_id}, {"_id": 0})
    if not e:
        raise HTTPException(404, "Handbook entry not found")
    await assert_space_member(e["space_id"], user.user_id)
    await db.handbook_entries.delete_one({"entry_id": entry_id})
    return {"ok": True}


# =========================
# Household Phase 2 — Tasks, Attendance, Shopping requests
# =========================
class TaskTemplate(BaseModel):
    task_id: str
    space_id: str
    title: str
    description: Optional[str] = None
    staff_id: Optional[str] = None
    role_id: Optional[str] = None
    recurrence: str = "daily"  # daily | weekly | monthly | once
    weekdays: List[int] = Field(default_factory=list)  # 0=Mon..6=Sun, used when recurrence=weekly
    monthly_day: Optional[int] = None  # used when recurrence=monthly
    once_date: Optional[str] = None  # YYYY-MM-DD, used when recurrence=once
    due_time: Optional[str] = None  # HH:MM
    requires_photo: bool = False
    active: bool = True
    created_at: datetime


class CreateTaskRequest(BaseModel):
    space_id: str
    title: str
    description: Optional[str] = None
    staff_id: Optional[str] = None
    role_id: Optional[str] = None
    recurrence: str = "daily"
    weekdays: List[int] = Field(default_factory=list)
    monthly_day: Optional[int] = None
    once_date: Optional[str] = None
    due_time: Optional[str] = None
    requires_photo: bool = False


class UpdateTaskRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    staff_id: Optional[str] = None
    role_id: Optional[str] = None
    recurrence: Optional[str] = None
    weekdays: Optional[List[int]] = None
    monthly_day: Optional[int] = None
    once_date: Optional[str] = None
    due_time: Optional[str] = None
    requires_photo: Optional[bool] = None
    active: Optional[bool] = None


class TaskCompletion(BaseModel):
    completion_id: str
    task_id: str
    space_id: str
    date: str  # YYYY-MM-DD
    completed_at: datetime
    completed_by: str
    completed_by_name: Optional[str] = None
    staff_id: Optional[str] = None
    photo_base64: Optional[str] = None
    notes: Optional[str] = None  # staff's own completion note
    owner_note: Optional[str] = None  # owner review/comment


class CompleteTaskRequest(BaseModel):
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today
    photo_base64: Optional[str] = None
    notes: Optional[str] = None


class AnnotateCompletionRequest(BaseModel):
    owner_note: str


class AttendanceLog(BaseModel):
    attendance_id: str
    space_id: str
    staff_id: str
    date: str
    status: str  # present | off | sick | leave | late
    notes: Optional[str] = None
    recorded_by: str
    created_at: datetime


class SetAttendanceRequest(BaseModel):
    space_id: str
    staff_id: str
    date: str
    status: str
    notes: Optional[str] = None


class ShoppingRequest(BaseModel):
    request_id: str
    space_id: str
    item_name: str
    quantity: Optional[str] = None
    note: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    urgency: str = "normal"  # low | normal | high
    status: str = "pending"  # pending | approved | purchased | rejected
    kind: str = "request"  # 'request' (asking for approval to buy) | 'reimbursement' (already bought, needs payback)
    estimated_price: Optional[float] = None
    actual_price: Optional[float] = None
    currency: Optional[str] = None
    photo_base64: Optional[str] = None
    requested_by: str
    requested_by_name: Optional[str] = None
    requested_by_staff_id: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    rejected_reason: Optional[str] = None
    purchased_by: Optional[str] = None
    purchased_at: Optional[datetime] = None
    fulfilled_at: Optional[datetime] = None
    created_at: datetime


class CreateShoppingRequest(BaseModel):
    space_id: str
    item_name: str
    quantity: Optional[str] = None
    note: Optional[str] = None
    category_id: Optional[str] = None
    urgency: str = "normal"
    requested_by_staff_id: Optional[str] = None
    estimated_price: Optional[float] = None
    photo_base64: Optional[str] = None
    kind: str = "request"  # 'request' | 'reimbursement'
    actual_price: Optional[float] = None  # for reimbursements (already spent)


class UpdateShoppingRequest(BaseModel):
    item_name: Optional[str] = None
    quantity: Optional[str] = None
    note: Optional[str] = None
    category_id: Optional[str] = None
    urgency: Optional[str] = None
    status: Optional[str] = None
    estimated_price: Optional[float] = None
    actual_price: Optional[float] = None
    photo_base64: Optional[str] = None
    rejected_reason: Optional[str] = None


class MarkPurchasedRequest(BaseModel):
    actual_price: Optional[float] = None
    note: Optional[str] = None


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


# ----- Task templates -----
@api_router.get("/household/tasks")
async def list_tasks(space_id: str, date: Optional[str] = None, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    tasks = await db.task_templates.find({"space_id": space_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Fetch completions for the target date
    comps = await db.task_completions.find({"space_id": space_id, "date": target_date}, {"_id": 0}).to_list(2000)
    comp_by_task = {c["task_id"]: c for c in comps}
    # Fetch staff names for display
    staff = await db.staff_members.find({"space_id": space_id}, {"_id": 0, "staff_id": 1, "name": 1, "role_id": 1, "photo_base64": 1}).to_list(500)
    staff_map = {s["staff_id"]: s for s in staff}
    roles = await db.household_roles.find({"space_id": space_id}, {"_id": 0}).to_list(200)
    role_map = {r["role_id"]: r for r in roles}

    out: List[Dict[str, Any]] = []
    for t in tasks:
        due_today = _task_due_on(t, target_date)
        staff_info = staff_map.get(t.get("staff_id")) if t.get("staff_id") else None
        role_info = role_map.get(t.get("role_id")) if t.get("role_id") else None
        comp = comp_by_task.get(t["task_id"])
        out.append({
            **t,
            "staff_name": staff_info["name"] if staff_info else None,
            "staff_photo": staff_info.get("photo_base64") if staff_info else None,
            "role_name": role_info["name"] if role_info else None,
            "role_color": role_info.get("color") if role_info else None,
            "due_today": due_today,
            "completed_today": comp is not None,
            "completion": comp,
        })
    return {"date": target_date, "tasks": out}


@api_router.post("/household/tasks", response_model=TaskTemplate)
async def create_task(body: CreateTaskRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    rec = body.recurrence if body.recurrence in ("daily", "weekly", "monthly", "once") else "daily"
    doc = {
        "task_id": gen_id("task"),
        "space_id": body.space_id,
        "title": body.title.strip(),
        "description": body.description,
        "staff_id": body.staff_id,
        "role_id": body.role_id,
        "recurrence": rec,
        "weekdays": body.weekdays or [],
        "monthly_day": body.monthly_day,
        "once_date": body.once_date,
        "due_time": body.due_time,
        "requires_photo": bool(body.requires_photo),
        "active": True,
        "created_at": now_utc(),
    }
    await db.task_templates.insert_one(doc)
    doc.pop("_id", None)
    # Notify assigned staff (if linked)
    if body.staff_id:
        st = await db.staff_members.find_one({"staff_id": body.staff_id}, {"_id": 0, "user_id": 1, "name": 1})
        if st and st.get("user_id"):
            when = "today" if rec in ("daily",) else (f"on {body.once_date}" if rec == "once" and body.once_date else rec)
            await _create_notification(
                space_id=body.space_id,
                user_id=st["user_id"],
                kind="task_assigned",
                title=f"New task: {doc['title']}",
                body=f"You've been assigned this task · {when}{(' · due ' + body.due_time) if body.due_time else ''}.",
                data={"task_id": doc["task_id"]},
            )
    return TaskTemplate(**doc)


# =========================
# Task Shortcuts & Quick-fire
# =========================
class TaskShortcut(BaseModel):
    shortcut_id: str
    space_id: str
    staff_id: Optional[str] = None  # None = shared across all staff
    title: str
    icon: Optional[str] = "Zap"
    created_at: datetime


class CreateTaskShortcutRequest(BaseModel):
    space_id: str
    staff_id: Optional[str] = None
    title: str
    icon: Optional[str] = "Zap"


class QuickTaskRequest(BaseModel):
    space_id: str
    staff_id: str
    title: str
    description: Optional[str] = None
    due_time: Optional[str] = None
    save_as_shortcut: bool = False


@api_router.get("/household/shortcuts", response_model=List[TaskShortcut])
async def list_task_shortcuts(space_id: str, staff_id: Optional[str] = None, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    q: Dict[str, Any] = {"space_id": space_id}
    if staff_id:
        q["$or"] = [{"staff_id": staff_id}, {"staff_id": None}]
    docs = await db.task_shortcuts.find(q, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [TaskShortcut(**d) for d in docs]


@api_router.post("/household/shortcuts", response_model=TaskShortcut)
async def create_task_shortcut(body: CreateTaskShortcutRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    if not body.title.strip():
        raise HTTPException(400, "Title required")
    doc = {
        "shortcut_id": gen_id("sc"),
        "space_id": body.space_id,
        "staff_id": body.staff_id,
        "title": body.title.strip(),
        "icon": body.icon or "Zap",
        "created_at": now_utc(),
    }
    await db.task_shortcuts.insert_one(doc)
    doc.pop("_id", None)
    return TaskShortcut(**doc)


@api_router.delete("/household/shortcuts/{shortcut_id}")
async def delete_task_shortcut(shortcut_id: str, user: User = Depends(get_current_user)):
    s = await db.task_shortcuts.find_one({"shortcut_id": shortcut_id}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Shortcut not found")
    await assert_space_member(s["space_id"], user.user_id)
    await db.task_shortcuts.delete_one({"shortcut_id": shortcut_id})
    return {"ok": True}


@api_router.post("/household/tasks/quick", response_model=TaskTemplate)
async def quick_task(body: QuickTaskRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    staff = await db.staff_members.find_one({"staff_id": body.staff_id, "space_id": body.space_id}, {"_id": 0})
    if not staff:
        raise HTTPException(404, "Staff not found")
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Title required")
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = {
        "task_id": gen_id("task"),
        "space_id": body.space_id,
        "title": title,
        "description": body.description,
        "staff_id": body.staff_id,
        "role_id": None,
        "recurrence": "once",
        "weekdays": [],
        "monthly_day": None,
        "once_date": today_str,
        "due_time": body.due_time,
        "requires_photo": False,
        "active": True,
        "created_at": now_utc(),
    }
    await db.task_templates.insert_one(doc)
    doc.pop("_id", None)
    # Save as shortcut for this staff
    if body.save_as_shortcut:
        existing = await db.task_shortcuts.find_one({"space_id": body.space_id, "staff_id": body.staff_id, "title": title}, {"_id": 0})
        if not existing:
            await db.task_shortcuts.insert_one({
                "shortcut_id": gen_id("sc"),
                "space_id": body.space_id,
                "staff_id": body.staff_id,
                "title": title,
                "icon": "Zap",
                "created_at": now_utc(),
            })
    # Notify staff if linked
    if staff.get("user_id"):
        await _create_notification(
            space_id=body.space_id,
            user_id=staff["user_id"],
            kind="task_assigned",
            title=f"Quick task: {title}",
            body=(body.description or f"{staff.get('name', 'You')}, a new quick task was just sent for today.") + (f" · due {body.due_time}" if body.due_time else ""),
            data={"task_id": doc["task_id"], "quick": True},
        )
    return TaskTemplate(**doc)


# Owner preview of any staff's home view
@api_router.get("/household/staff/{staff_id}/view")
async def preview_staff_view(staff_id: str, user: User = Depends(get_current_user)):
    s = await db.staff_members.find_one({"staff_id": staff_id}, {"_id": 0})
    if not s:
        raise HTTPException(404, "Staff not found")
    await assert_space_member(s["space_id"], user.user_id)
    await _attach_role_name(s)
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tasks = await db.task_templates.find(
        {"space_id": s["space_id"], "$or": [{"staff_id": s["staff_id"]}, {"role_id": s.get("role_id")}, {"staff_id": None, "role_id": None}]},
        {"_id": 0},
    ).to_list(500)
    comps = await db.task_completions.find({"space_id": s["space_id"], "date": today_str}, {"_id": 0}).to_list(500)
    comp_by_task = {c["task_id"]: c for c in comps}
    today_tasks: List[Dict[str, Any]] = []
    for t in tasks:
        if _task_due_on(t, today_str):
            today_tasks.append({**t, "completed_today": t["task_id"] in comp_by_task, "completion": comp_by_task.get(t["task_id"])})
    att = await db.attendance_logs.find({"space_id": s["space_id"], "staff_id": s["staff_id"]}, {"_id": 0}).sort("date", -1).to_list(60)
    perms = {**DEFAULT_STAFF_PERMS, **(s.get("permissions") or {})}
    payments: List[Dict[str, Any]] = []
    if perms.get("view_wage_amount"):
        payments = await db.staff_payments.find({"space_id": s["space_id"], "staff_id": s["staff_id"]}, {"_id": 0}).sort("paid_at", -1).to_list(100)
    return {"staff": s, "permissions": perms, "today_tasks": today_tasks, "attendance": att, "payments": payments, "preview": True}


@api_router.patch("/household/tasks/{task_id}", response_model=TaskTemplate)
async def update_task(task_id: str, body: UpdateTaskRequest, user: User = Depends(get_current_user)):
    t = await db.task_templates.find_one({"task_id": task_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Task not found")
    await assert_space_member(t["space_id"], user.user_id)
    updates: Dict[str, Any] = {}
    for k in ("title", "description", "staff_id", "role_id", "recurrence", "weekdays", "monthly_day", "once_date", "due_time", "requires_photo", "active"):
        v = getattr(body, k)
        if v is not None:
            updates[k] = v
    if updates:
        await db.task_templates.update_one({"task_id": task_id}, {"$set": updates})
    out = await db.task_templates.find_one({"task_id": task_id}, {"_id": 0})
    return TaskTemplate(**out)


@api_router.delete("/household/tasks/{task_id}")
async def delete_task(task_id: str, user: User = Depends(get_current_user)):
    t = await db.task_templates.find_one({"task_id": task_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Task not found")
    await assert_space_member(t["space_id"], user.user_id)
    await db.task_templates.delete_one({"task_id": task_id})
    # Don't delete historical completions — keep for records
    return {"ok": True}


class CompleteTaskRequest(BaseModel):
    date: Optional[str] = None
    photo_base64: Optional[str] = None
    notes: Optional[str] = None


@api_router.post("/household/tasks/{task_id}/complete")
async def complete_task(task_id: str, body: CompleteTaskRequest, user: User = Depends(get_current_user)):
    t = await db.task_templates.find_one({"task_id": task_id}, {"_id": 0})
    if not t:
        raise HTTPException(404, "Task not found")
    await assert_space_member(t["space_id"], user.user_id)
    date_str = body.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Toggle: if already completed today → delete; otherwise insert
    existing = await db.task_completions.find_one({"task_id": task_id, "date": date_str}, {"_id": 0})
    if existing:
        await db.task_completions.delete_one({"task_id": task_id, "date": date_str})
        return {"completed": False}
    # Enforce photo proof when task requires it
    if t.get("requires_photo") and not body.photo_base64:
        raise HTTPException(400, "This task requires a photo to mark complete")
    # Find the staff_id for the completer (if they are linked as staff)
    staff_id = None
    staff_name = None
    linked_staff = await db.staff_members.find_one({"space_id": t["space_id"], "user_id": user.user_id}, {"_id": 0})
    if linked_staff:
        staff_id = linked_staff["staff_id"]
        staff_name = linked_staff.get("name")
    doc = {
        "completion_id": gen_id("comp"),
        "task_id": task_id,
        "space_id": t["space_id"],
        "date": date_str,
        "completed_at": now_utc(),
        "completed_by": user.user_id,
        "completed_by_name": staff_name or user.name if hasattr(user, 'name') else staff_name,
        "staff_id": staff_id,
        "photo_base64": body.photo_base64,
        "notes": body.notes,
        "owner_note": None,
    }
    await db.task_completions.insert_one(doc)
    # Notify space members (owner) about completion
    space = await db.family_spaces.find_one({"space_id": t["space_id"]}, {"_id": 0})
    if space:
        for mid in [space["owner_id"]] + list(space.get("member_ids", []) or []):
            if mid == user.user_id:
                continue
            await _create_notification(
                space_id=t["space_id"],
                user_id=mid,
                kind="task_done",
                title=f"Task done: {t['title']}",
                body=f"{staff_name or 'Someone'} completed this task" + (f" · with photo" if body.photo_base64 else "") + (f" · \"{body.notes}\"" if body.notes else ""),
                data={"task_id": task_id, "completion_id": doc["completion_id"]},
            )
    return {"completed": True, "completion_id": doc["completion_id"]}


@api_router.patch("/household/completions/{completion_id}/annotate")
async def annotate_completion(completion_id: str, body: AnnotateCompletionRequest, user: User = Depends(get_current_user)):
    c = await db.task_completions.find_one({"completion_id": completion_id}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Completion not found")
    await assert_space_member(c["space_id"], user.user_id)
    await db.task_completions.update_one(
        {"completion_id": completion_id},
        {"$set": {"owner_note": body.owner_note}},
    )
    # Notify the staff who completed it
    if c.get("completed_by") and c["completed_by"] != user.user_id:
        await _create_notification(
            space_id=c["space_id"],
            user_id=c["completed_by"],
            kind="task_comment",
            title="Comment on your task",
            body=body.owner_note[:200],
            data={"task_id": c["task_id"], "completion_id": completion_id},
        )
    out = await db.task_completions.find_one({"completion_id": completion_id}, {"_id": 0})
    return out


@api_router.get("/household/completions")
async def list_completions(space_id: str, task_id: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    q: Dict[str, Any] = {"space_id": space_id}
    if task_id:
        q["task_id"] = task_id
    if date_from and date_to:
        q["date"] = {"$gte": date_from, "$lte": date_to}
    elif date_from:
        q["date"] = {"$gte": date_from}
    docs = await db.task_completions.find(q, {"_id": 0}).sort("completed_at", -1).to_list(500)
    return docs


# ----- Attendance -----
@api_router.get("/household/attendance")
async def list_attendance(space_id: str, date_from: Optional[str] = None, date_to: Optional[str] = None, staff_id: Optional[str] = None, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    q: Dict[str, Any] = {"space_id": space_id}
    if staff_id:
        q["staff_id"] = staff_id
    if date_from and date_to:
        q["date"] = {"$gte": date_from, "$lte": date_to}
    elif date_from:
        q["date"] = {"$gte": date_from}
    elif date_to:
        q["date"] = {"$lte": date_to}
    docs = await db.attendance_logs.find(q, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(2000)
    return docs


@api_router.post("/household/attendance", response_model=AttendanceLog)
async def set_attendance(body: SetAttendanceRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    if body.status not in ("present", "off", "sick", "leave", "late"):
        raise HTTPException(400, "Invalid status")
    # Upsert per (staff_id, date)
    existing = await db.attendance_logs.find_one({"space_id": body.space_id, "staff_id": body.staff_id, "date": body.date}, {"_id": 0})
    if existing:
        await db.attendance_logs.update_one(
            {"attendance_id": existing["attendance_id"]},
            {"$set": {"status": body.status, "notes": body.notes, "recorded_by": user.user_id, "created_at": now_utc()}},
        )
        out = await db.attendance_logs.find_one({"attendance_id": existing["attendance_id"]}, {"_id": 0})
        return AttendanceLog(**out)
    doc = {
        "attendance_id": gen_id("att"),
        "space_id": body.space_id,
        "staff_id": body.staff_id,
        "date": body.date,
        "status": body.status,
        "notes": body.notes,
        "recorded_by": user.user_id,
        "created_at": now_utc(),
    }
    await db.attendance_logs.insert_one(doc)
    doc.pop("_id", None)
    return AttendanceLog(**doc)


# ----- Shopping requests -----
@api_router.get("/household/shopping")
async def list_shopping(space_id: str, status: Optional[str] = None, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    q: Dict[str, Any] = {"space_id": space_id}
    if status:
        q["status"] = status
    docs = await db.shopping_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)
    # Enrich with names
    users = await db.users.find({"user_id": {"$in": list({d["requested_by"] for d in docs})}}, {"_id": 0, "password_hash": 0}).to_list(200)
    user_map = {u["user_id"]: u["name"] for u in users}
    staff = await db.staff_members.find({"space_id": space_id}, {"_id": 0}).to_list(500)
    staff_map = {s["staff_id"]: s for s in staff}
    cats = await db.categories.find({"space_id": space_id}, {"_id": 0}).to_list(500)
    cat_map = {c["category_id"]: c["name"] for c in cats}
    for d in docs:
        if d.get("requested_by_staff_id") and staff_map.get(d["requested_by_staff_id"]):
            d["requested_by_name"] = staff_map[d["requested_by_staff_id"]]["name"]
        else:
            d["requested_by_name"] = user_map.get(d["requested_by"], "Someone")
        d["category_name"] = cat_map.get(d.get("category_id")) if d.get("category_id") else None
    return docs


@api_router.post("/household/shopping", response_model=ShoppingRequest)
async def create_shopping(body: CreateShoppingRequest, user: User = Depends(get_current_user)):
    space = await assert_space_member(body.space_id, user.user_id)
    is_reimbursement = body.kind == "reimbursement"
    initial_status = "approved" if is_reimbursement else "pending"  # reimbursements come pre-approved (already spent), waiting for owner to confirm payback
    doc = {
        "request_id": gen_id("shop"),
        "space_id": body.space_id,
        "item_name": body.item_name.strip(),
        "quantity": body.quantity,
        "note": body.note,
        "category_id": body.category_id,
        "urgency": body.urgency if body.urgency in ("low", "normal", "high") else "normal",
        "status": initial_status,
        "kind": "reimbursement" if is_reimbursement else "request",
        "estimated_price": body.estimated_price,
        "actual_price": body.actual_price if is_reimbursement else None,
        "currency": (space.get("currency") if isinstance(space, dict) else None) or "USD",
        "photo_base64": body.photo_base64,
        "requested_by": user.user_id,
        "requested_by_staff_id": body.requested_by_staff_id,
        "approved_by": None,
        "approved_at": None,
        "rejected_reason": None,
        "purchased_by": None,
        "purchased_at": None,
        "fulfilled_at": None,
        "created_at": now_utc(),
    }
    await db.shopping_requests.insert_one(doc)
    doc.pop("_id", None)
    # Notify owner + members (but not the requester)
    if isinstance(space, dict):
        # Find requester display name
        who = "Someone"
        if body.requested_by_staff_id:
            st = await db.staff_members.find_one({"staff_id": body.requested_by_staff_id}, {"_id": 0, "name": 1})
            if st:
                who = st.get("name") or who
        else:
            u = await db.users.find_one({"user_id": user.user_id}, {"_id": 0, "name": 1})
            if u:
                who = u.get("name") or who
        price_blurb = ""
        if body.estimated_price:
            price_blurb = f" (est. {doc['currency']} {body.estimated_price:,.0f})"
        for mid in [space.get("owner_id")] + list(space.get("member_ids", []) or []):
            if not mid or mid == user.user_id:
                continue
            await _create_notification(
                space_id=body.space_id,
                user_id=mid,
                kind="shopping_request",
                title=f"Shopping request: {doc['item_name']}",
                body=f"{who} requested {doc['item_name']}{(' · ' + doc['quantity']) if doc.get('quantity') else ''}{price_blurb}",
                data={"request_id": doc["request_id"]},
            )
    return ShoppingRequest(**doc)


@api_router.patch("/household/shopping/{request_id}", response_model=ShoppingRequest)
async def update_shopping(request_id: str, body: UpdateShoppingRequest, user: User = Depends(get_current_user)):
    r = await db.shopping_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Request not found")
    await assert_space_member(r["space_id"], user.user_id)
    updates: Dict[str, Any] = {}
    for k in ("item_name", "quantity", "note", "category_id", "urgency", "status", "estimated_price", "actual_price", "photo_base64", "rejected_reason"):
        v = getattr(body, k)
        if v is not None:
            updates[k] = v
    prev_status = r.get("status")
    new_status = updates.get("status", prev_status)
    if new_status in ("approved", "rejected") and prev_status != new_status:
        updates["approved_by"] = user.user_id
        updates["approved_at"] = now_utc()
    if new_status == "purchased" and prev_status != "purchased":
        updates["purchased_by"] = user.user_id
        updates["purchased_at"] = now_utc()
        updates["fulfilled_at"] = now_utc()
    if updates:
        await db.shopping_requests.update_one({"request_id": request_id}, {"$set": updates})
    out = await db.shopping_requests.find_one({"request_id": request_id}, {"_id": 0})
    # Notify requester on status changes
    if new_status != prev_status and r.get("requested_by") and r["requested_by"] != user.user_id:
        await _create_notification(
            space_id=r["space_id"],
            user_id=r["requested_by"],
            kind="shopping_status",
            title=f"Shopping: {r['item_name']} · {new_status}",
            body=(body.rejected_reason or "") if new_status == "rejected" else ("Your request was " + new_status),
            data={"request_id": request_id, "status": new_status},
        )
    return ShoppingRequest(**out)


@api_router.post("/household/shopping/{request_id}/purchase", response_model=ShoppingRequest)
async def mark_shopping_purchased(request_id: str, body: MarkPurchasedRequest, user: User = Depends(get_current_user)):
    r = await db.shopping_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Request not found")
    await assert_space_member(r["space_id"], user.user_id)
    updates = {
        "status": "purchased",
        "purchased_by": user.user_id,
        "purchased_at": now_utc(),
        "fulfilled_at": now_utc(),
    }
    if body.actual_price is not None:
        updates["actual_price"] = body.actual_price
    if body.note:
        updates["note"] = (r.get("note") or "") + ("\n" if r.get("note") else "") + f"[Purchase] {body.note}"
    await db.shopping_requests.update_one({"request_id": request_id}, {"$set": updates})
    out = await db.shopping_requests.find_one({"request_id": request_id}, {"_id": 0})
    if r.get("requested_by") and r["requested_by"] != user.user_id:
        await _create_notification(
            space_id=r["space_id"],
            user_id=r["requested_by"],
            kind="shopping_status",
            title=f"Purchased: {r['item_name']}",
            body=(body.note or "The item has been purchased."),
            data={"request_id": request_id, "status": "purchased"},
        )
    return ShoppingRequest(**out)


# Count badges for household tabs (for owners/members)
@api_router.get("/household/counts")
async def household_counts(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Shopping pending
    shop_pending = await db.shopping_requests.count_documents({"space_id": space_id, "status": "pending"})
    shop_approved = await db.shopping_requests.count_documents({"space_id": space_id, "status": "approved"})
    # Tasks open (assigned today, not yet completed)
    task_docs = await db.task_templates.find({"space_id": space_id, "active": True}, {"_id": 0}).to_list(1000)
    comps_today = await db.task_completions.find({"space_id": space_id, "date": today}, {"_id": 0, "task_id": 1}).to_list(1000)
    completed_ids = {c["task_id"] for c in comps_today}
    tasks_open = 0
    for t in task_docs:
        if _task_due_on(t, today) and t["task_id"] not in completed_ids:
            tasks_open += 1
    return {
        "shopping_pending": shop_pending,
        "shopping_approved": shop_approved,
        "tasks_open_today": tasks_open,
    }


# =========================
# Documents vault
# =========================
class Document(BaseModel):
    document_id: str
    space_id: str
    name: str
    folder: Optional[str] = None  # e.g. "contracts", "ids", "insurance"
    mime: str = "image/jpeg"
    file_base64: Optional[str] = None  # base64 (image/pdf)
    note: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    size_kb: Optional[int] = None
    uploaded_by: str
    uploaded_by_name: Optional[str] = None
    created_at: datetime
    related_to: Optional[Dict[str, str]] = None  # {kind:'payment'|'item', id:..}


class CreateDocumentRequest(BaseModel):
    space_id: str
    name: str
    folder: Optional[str] = None
    mime: str = "image/jpeg"
    file_base64: str
    note: Optional[str] = None
    tags: List[str] = []
    related_to: Optional[Dict[str, str]] = None


class UpdateDocumentRequest(BaseModel):
    name: Optional[str] = None
    folder: Optional[str] = None
    note: Optional[str] = None
    tags: Optional[List[str]] = None


@api_router.get("/documents", response_model=List[Document])
async def list_documents(space_id: str, folder: Optional[str] = None, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    q: Dict[str, Any] = {"space_id": space_id}
    if folder:
        q["folder"] = folder
    docs = await db.documents.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Document(**d) for d in docs]


@api_router.post("/documents", response_model=Document)
async def create_document(body: CreateDocumentRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    if not body.file_base64:
        raise HTTPException(400, "file_base64 is required")
    raw = body.file_base64
    # Estimate size in KB
    payload = raw.split(",", 1)[1] if "," in raw and raw.startswith("data:") else raw
    size_kb = max(1, int(len(payload) * 3 / 4 / 1024))
    if size_kb > 8 * 1024:  # 8 MB hard cap
        raise HTTPException(413, "File too large (max ~8 MB). Please compress or split.")
    doc = {
        "document_id": gen_id("doc"),
        "space_id": body.space_id,
        "name": body.name.strip() or "Untitled",
        "folder": body.folder,
        "mime": body.mime or "image/jpeg",
        "file_base64": body.file_base64,
        "note": body.note,
        "tags": body.tags or [],
        "size_kb": size_kb,
        "uploaded_by": user.user_id,
        "uploaded_by_name": user.name,
        "created_at": now_utc(),
        "related_to": body.related_to,
    }
    await db.documents.insert_one(doc)
    doc.pop("_id", None)
    return Document(**doc)


@api_router.patch("/documents/{document_id}", response_model=Document)
async def update_document(document_id: str, body: UpdateDocumentRequest, user: User = Depends(get_current_user)):
    d = await db.documents.find_one({"document_id": document_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Document not found")
    await assert_space_member(d["space_id"], user.user_id)
    updates = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    if updates:
        await db.documents.update_one({"document_id": document_id}, {"$set": updates})
    out = await db.documents.find_one({"document_id": document_id}, {"_id": 0})
    return Document(**out)


@api_router.delete("/documents/{document_id}")
async def delete_document(document_id: str, user: User = Depends(get_current_user)):
    d = await db.documents.find_one({"document_id": document_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Document not found")
    await assert_space_member(d["space_id"], user.user_id)
    await db.documents.delete_one({"document_id": document_id})
    return {"ok": True}


@api_router.get("/documents/folders")
async def list_doc_folders(space_id: str, user: User = Depends(get_current_user)):
    await assert_space_member(space_id, user.user_id)
    pipeline = [{"$match": {"space_id": space_id, "folder": {"$ne": None}}}, {"$group": {"_id": "$folder", "count": {"$sum": 1}}}]
    folders = []
    async for r in db.documents.aggregate(pipeline):
        folders.append({"folder": r["_id"], "count": r["count"]})
    return folders


# =========================
# Export household report (CSV + PDF)
# =========================
import io
import csv as _csv
from fastapi.responses import StreamingResponse, Response


@api_router.get("/reports/household/export")
async def export_household_report(space_id: str, year: Optional[int] = None, month: Optional[int] = None, format: str = "csv", user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    fmt = (format or "csv").lower()
    if fmt not in ("csv", "pdf"):
        raise HTTPException(400, "format must be 'csv' or 'pdf'")
    now = now_utc()
    y = year or now.year
    m = month or now.month
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    end = datetime(y + 1, 1, 1, tzinfo=timezone.utc) if m == 12 else datetime(y, m + 1, 1, tzinfo=timezone.utc)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    currency = space.get("currency") or "USD"
    space_name = space.get("name") or "Household"
    period_label = start.strftime("%B %Y")

    # Pull raw rows
    items = await db.items.find({"space_id": space_id, "created_at": {"$gte": start, "$lt": end}}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    payments = await db.staff_payments.find({"space_id": space_id, "paid_at": {"$gte": start, "$lt": end}}, {"_id": 0}).sort("paid_at", 1).to_list(2000)
    shopping = await db.shopping_requests.find({"space_id": space_id, "created_at": {"$gte": start, "$lt": end}}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    attendance = await db.attendance_logs.find({"space_id": space_id, "date": {"$gte": start_str, "$lt": end_str}}, {"_id": 0}).sort("date", 1).to_list(10000)
    cat_map = {c["category_id"]: c.get("name") or "?" for c in await db.categories.find({"space_id": space_id}, {"_id": 0}).to_list(500)}
    staff_map = {s["staff_id"]: s.get("name") or "?" for s in await db.staff_members.find({"space_id": space_id}, {"_id": 0}).to_list(500)}

    if fmt == "csv":
        buf = io.StringIO()
        w = _csv.writer(buf)
        w.writerow([f"# {space_name} — Household report — {period_label}"])
        w.writerow([f"# Currency: {currency}", f"Generated: {now.strftime('%Y-%m-%d %H:%M UTC')}"])
        w.writerow([])
        # Spending
        w.writerow(["[ TRANSACTIONS / EXPENSES ]"])
        w.writerow(["Date", "Category", "Item", "Quantity", "Unit", "Price", "Event tag", "Added by", "Notes"])
        for it in items:
            w.writerow([
                (it.get("purchase_date") or it.get("created_at").strftime("%Y-%m-%d") if it.get("created_at") else ""),
                cat_map.get(it.get("category_id"), ""),
                it.get("name") or "",
                it.get("quantity") or "",
                it.get("unit") or "",
                it.get("price") or "",
                it.get("event_tag") or "",
                it.get("created_by_name") or "",
                (it.get("notes") or "").replace("\n", " "),
            ])
        w.writerow([])
        # Wages
        w.writerow(["[ STAFF WAGES PAID ]"])
        w.writerow(["Paid at", "Staff", "Period", "Gross", "Bonus", "Advances", "Deductions", "Net", "Currency", "Confirmed at", "Notes"])
        for p in payments:
            paid_at = p.get("paid_at"); paid_at_s = paid_at.strftime("%Y-%m-%d %H:%M") if paid_at else ""
            conf = p.get("confirmed_at"); conf_s = conf.strftime("%Y-%m-%d %H:%M") if conf else ""
            w.writerow([
                paid_at_s, p.get("staff_name") or staff_map.get(p["staff_id"], ""), p.get("period") or "",
                p.get("gross") or 0, p.get("bonus") or 0, p.get("advances") or 0,
                p.get("deductions") or 0, p.get("net") or 0, p.get("currency") or currency,
                conf_s, (p.get("notes") or "").replace("\n", " "),
            ])
        w.writerow([])
        # Shopping
        w.writerow(["[ SHOPPING & REIMBURSEMENT REQUESTS ]"])
        w.writerow(["Created", "Type", "Status", "Item", "Qty", "Requested by", "Estimated", "Actual paid", "Note"])
        for s in shopping:
            created = s.get("created_at"); created_s = created.strftime("%Y-%m-%d") if created else ""
            req_name = s.get("requested_by_name") or staff_map.get(s.get("requested_by_staff_id"), "")
            w.writerow([
                created_s, s.get("kind", "request"), s.get("status", ""), s.get("item_name", ""),
                s.get("quantity") or "", req_name, s.get("estimated_price") or "", s.get("actual_price") or "",
                (s.get("note") or "").replace("\n", " "),
            ])
        w.writerow([])
        # Attendance
        w.writerow(["[ ATTENDANCE LOGS ]"])
        w.writerow(["Date", "Staff", "Status", "Notes"])
        for a in attendance:
            w.writerow([
                a.get("date", ""), staff_map.get(a.get("staff_id"), ""), a.get("status", ""),
                (a.get("notes") or "").replace("\n", " "),
            ])
        buf.seek(0)
        filename = f"household-report-{y}-{m:02d}.csv"
        return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    # PDF — use reportlab
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors as rl_colors
    except ImportError:
        raise HTTPException(500, "reportlab not installed; please use format=csv")

    pdf_buf = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buf, pagesize=LETTER, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=20, spaceAfter=8)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, spaceBefore=14, spaceAfter=6, textColor=rl_colors.HexColor("#3D6F2A"))
    body = styles["Normal"]
    elems = []
    elems.append(Paragraph(f"<b>{space_name}</b> — Monthly report", title_style))
    elems.append(Paragraph(f"<font color='#888'>Period: {period_label} · Currency: {currency} · Generated {now.strftime('%Y-%m-%d %H:%M UTC')}</font>", body))
    elems.append(Spacer(1, 8))

    # Summary
    total_spent = sum((it.get("price") or 0) for it in items)
    total_wages = sum((p.get("net") or 0) for p in payments)
    elems.append(Paragraph("<b>Summary</b>", h2))
    sumtbl = Table([
        ["Total expenses (incl. wages)", f"{currency} {total_spent:,.2f}"],
        ["Staff wages paid", f"{currency} {total_wages:,.2f}"],
        ["Other household spend", f"{currency} {max(total_spent - total_wages, 0):,.2f}"],
        ["Number of transactions", str(len(items))],
        ["Shopping / reimbursement requests", str(len(shopping))],
    ], colWidths=[260, 260])
    sumtbl.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("BACKGROUND", (0, 0), (0, -1), rl_colors.HexColor("#F5F5F0"))]))
    elems.append(sumtbl)

    # Wages
    if payments:
        elems.append(Paragraph("<b>Staff wages paid</b>", h2))
        rows = [["Date", "Staff", "Period", "Net", "Confirmed"]]
        for p in payments:
            paid_at = p.get("paid_at"); paid_s = paid_at.strftime("%b %d") if paid_at else ""
            conf = "Yes" if p.get("confirmed_at") else ("Pending" if p.get("requires_confirmation") else "—")
            rows.append([paid_s, p.get("staff_name") or staff_map.get(p["staff_id"], ""), p.get("period") or "", f"{p.get('currency') or currency} {(p.get('net') or 0):,.0f}", conf])
        t = Table(rows, colWidths=[60, 130, 80, 110, 90])
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#3D6F2A")), ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white), ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.HexColor("#DDD")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#FAFAF8")])]))
        elems.append(t)

    # Shopping
    if shopping:
        elems.append(Paragraph("<b>Shopping & reimbursements</b>", h2))
        rows = [["Date", "Type", "Item", "Status", "Amount"]]
        for s in shopping:
            created = s.get("created_at"); created_s = created.strftime("%b %d") if created else ""
            amt = s.get("actual_price") or s.get("estimated_price") or 0
            rows.append([created_s, (s.get("kind") or "request").title(), s.get("item_name", "")[:30], s.get("status", "").title(), f"{currency} {amt:,.0f}"])
        t = Table(rows, colWidths=[55, 90, 180, 75, 90])
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#9B5A3F")), ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white), ("GRID", (0, 0), (-1, -1), 0.4, rl_colors.HexColor("#DDD")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#FAFAF8")])]))
        elems.append(t)

    # All transactions (raw)
    if items:
        elems.append(Paragraph("<b>All transactions</b>", h2))
        rows = [["Date", "Category", "Item", "Qty", "Price", "Tag"]]
        for it in items[:200]:  # cap to avoid huge PDFs
            d = (it.get("purchase_date") or (it.get("created_at").strftime("%Y-%m-%d") if it.get("created_at") else ""))
            rows.append([d, cat_map.get(it.get("category_id"), "")[:18], (it.get("name") or "")[:30], str(it.get("quantity") or 1), f"{currency} {(it.get('price') or 0):,.0f}", (it.get("event_tag") or "")[:14]])
        if len(items) > 200:
            rows.append([f"… and {len(items) - 200} more (CSV has all)", "", "", "", "", ""])
        t = Table(rows, colWidths=[60, 80, 170, 40, 90, 70])
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#1F4F88")), ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white), ("GRID", (0, 0), (-1, -1), 0.3, rl_colors.HexColor("#EEE")), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor("#FAFAF8")])]))
        elems.append(t)

    doc.build(elems)
    pdf_buf.seek(0)
    filename = f"household-report-{y}-{m:02d}.pdf"
    return Response(content=pdf_buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@api_router.delete("/household/shopping/{request_id}")
async def delete_shopping(request_id: str, user: User = Depends(get_current_user)):
    r = await db.shopping_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Request not found")
    await assert_space_member(r["space_id"], user.user_id)
    await db.shopping_requests.delete_one({"request_id": request_id})
    return {"ok": True}


# =========================
# Notifications (in-app)
# =========================
class Notification(BaseModel):
    notification_id: str
    space_id: str
    user_id: str
    kind: str  # 'wage_paid' | 'task_assigned' | 'info'
    title: str
    body: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    read: bool = False
    created_at: datetime


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


# =========================
# Household Report (Monthly summary for housewives)
# =========================
@api_router.get("/reports/household")
async def household_report(space_id: str, year: Optional[int] = None, month: Optional[int] = None, user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    now = now_utc()
    y = year or now.year
    m = month or now.month
    # month start/end
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    if m == 12:
        end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(y, m + 1, 1, tzinfo=timezone.utc)
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")
    currency = space.get("currency") or "USD"

    # --- Spending (items with price in window) ---
    # We use items as the finance ledger (as seen in /reports/finance + payroll logs).
    item_pipeline = [
        {"$match": {"space_id": space_id, "created_at": {"$gte": start, "$lt": end}, "price": {"$ne": None, "$gt": 0}}},
        {"$group": {"_id": "$category_id", "total": {"$sum": "$price"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]
    cat_totals = []
    async for row in db.items.aggregate(item_pipeline):
        cat_totals.append(row)
    total_spent = sum((c.get("total") or 0) for c in cat_totals)
    # attach category names
    cat_ids = [c["_id"] for c in cat_totals if c.get("_id")]
    cats = await db.categories.find({"category_id": {"$in": cat_ids}}, {"_id": 0}).to_list(200)
    cat_name = {c["category_id"]: c["name"] for c in cats}
    cat_icon = {c["category_id"]: c.get("icon") or "Package" for c in cats}
    cat_tint = {c["category_id"]: c.get("tint") or c.get("color") or "mint" for c in cats}
    top_categories = []
    for c in cat_totals[:5]:
        cid = c.get("_id")
        top_categories.append({
            "category_id": cid,
            "name": cat_name.get(cid, "Uncategorized"),
            "icon": cat_icon.get(cid, "Package"),
            "tint": cat_tint.get(cid, "mint"),
            "total": round(c.get("total") or 0, 2),
            "count": c.get("count") or 0,
        })

    # --- Staff summary ---
    # Show staff that were "active during this month" OR had any payment/attendance in the window.
    # A staff is active-during-window if: (start_date <= window_end) AND (end_date is null OR end_date >= window_start) AND active != false
    all_staff = await db.staff_members.find({"space_id": space_id}, {"_id": 0}).to_list(500)
    # Attendance in window
    att_docs = await db.attendance_logs.find({"space_id": space_id, "date": {"$gte": start_str, "$lt": end_str}}, {"_id": 0}).to_list(5000)
    att_by_staff: Dict[str, Dict[str, int]] = {}
    for a in att_docs:
        sid = a["staff_id"]; st = a["status"]
        att_by_staff.setdefault(sid, {"present": 0, "off": 0, "sick": 0, "leave": 0, "late": 0})
        att_by_staff[sid][st] = att_by_staff[sid].get(st, 0) + 1
    # Payments in window
    pay_docs = await db.staff_payments.find({"space_id": space_id, "paid_at": {"$gte": start, "$lt": end}}, {"_id": 0}).to_list(1000)
    paid_by_staff: Dict[str, float] = {}
    for p in pay_docs:
        paid_by_staff[p["staff_id"]] = paid_by_staff.get(p["staff_id"], 0) + float(p.get("net") or 0)
    total_wages = sum(paid_by_staff.values())

    def _in_window(s: Dict[str, Any]) -> bool:
        # Explicitly inactive → only include if they had activity in window
        active = s.get("active", True)
        sd = s.get("start_date")
        ed = s.get("end_date")
        had_activity = (s["staff_id"] in att_by_staff) or (s["staff_id"] in paid_by_staff)
        # Exclude staff with start_date after window end (hasn't started yet), unless they had activity
        if sd and sd >= end_str and not had_activity:
            return False
        # Exclude staff ended before window start, unless they had activity (historical)
        if ed and ed < start_str and not had_activity:
            return False
        # Inactive and no activity → hide
        if not active and not had_activity:
            return False
        return True

    staff_docs = [s for s in all_staff if _in_window(s)]

    # Task completions per staff in window
    task_ids = [t["task_id"] for t in await db.task_templates.find({"space_id": space_id}, {"_id": 0, "task_id": 1, "staff_id": 1, "role_id": 1}).to_list(2000)]
    task_owner = {t["task_id"]: t for t in await db.task_templates.find({"space_id": space_id}, {"_id": 0, "task_id": 1, "staff_id": 1, "role_id": 1}).to_list(2000)}
    comp_docs = await db.task_completions.find({"space_id": space_id, "date": {"$gte": start_str, "$lt": end_str}, "task_id": {"$in": task_ids}}, {"_id": 0}).to_list(5000)
    done_by_staff: Dict[str, int] = {}
    total_tasks_done = 0
    for c in comp_docs:
        total_tasks_done += 1
        # prefer completion staff_id, fall back to task owner
        sid = c.get("staff_id") or (task_owner.get(c["task_id"], {}) or {}).get("staff_id")
        if sid:
            done_by_staff[sid] = done_by_staff.get(sid, 0) + 1

    staff_summary = []
    for s in staff_docs:
        sid = s["staff_id"]
        att = att_by_staff.get(sid, {})
        staff_summary.append({
            "staff_id": sid,
            "name": s.get("name"),
            "photo_base64": s.get("photo_base64"),
            "role_id": s.get("role_id"),
            "active": s.get("active", True),
            "start_date": s.get("start_date"),
            "end_date": s.get("end_date"),
            "days_present": att.get("present", 0) + att.get("late", 0),
            "days_off": att.get("off", 0),
            "days_sick": att.get("sick", 0),
            "days_leave": att.get("leave", 0),
            "tasks_done": done_by_staff.get(sid, 0),
            "paid": round(paid_by_staff.get(sid, 0), 2),
            "salary": s.get("salary"),
            "pay_cycle": s.get("pay_cycle"),
        })

    # --- Shopping requests in window ---
    shop_docs = await db.shopping_requests.find({"space_id": space_id, "created_at": {"$gte": start, "$lt": end}}, {"_id": 0}).to_list(2000)
    shop_pending = sum(1 for r in shop_docs if r.get("status") == "pending")
    shop_approved = sum(1 for r in shop_docs if r.get("status") == "approved")
    shop_purchased = sum(1 for r in shop_docs if r.get("status") == "purchased")

    # --- Headline blurb for housewife ---
    month_name = start.strftime("%B %Y")
    return {
        "month": month_name,
        "year": y,
        "month_num": m,
        "currency": currency,
        "total_spent": round(total_spent, 2),
        "total_wages": round(total_wages, 2),
        "top_categories": top_categories,
        "staff": staff_summary,
        "shopping": {
            "total": len(shop_docs),
            "pending": shop_pending,
            "approved": shop_approved,
            "purchased": shop_purchased,
        },
        "tasks_done": total_tasks_done,
    }


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


class ContractSignature(BaseModel):
    role: str  # "owner" | "staff"
    user_id: str
    name: Optional[str] = None
    typed_name: Optional[str] = None
    drawing_base64: Optional[str] = None  # PNG/SVG base64 dataURL
    signed_at: datetime
    ip: Optional[str] = None
    user_agent: Optional[str] = None


class Contract(BaseModel):
    contract_id: str
    space_id: str
    template_kind: str  # nda | employment | confidentiality | blank | custom
    title: str
    body: str
    variables: Dict[str, Any] = Field(default_factory=dict)
    assigned_staff_id: Optional[str] = None
    assigned_staff_name: Optional[str] = None
    require_owner_signature: bool = True
    require_staff_signature: bool = True
    require_drawn_signature_owner: bool = False
    require_drawn_signature_staff: bool = False
    status: str = "pending"  # pending | signed | void
    owner_signature: Optional[ContractSignature] = None
    staff_signature: Optional[ContractSignature] = None
    created_by: str
    created_by_name: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class CreateContractRequest(BaseModel):
    space_id: str
    template_kind: str = "blank"
    title: str
    body: str
    variables: Dict[str, Any] = {}
    assigned_staff_id: Optional[str] = None
    require_owner_signature: bool = True
    require_staff_signature: bool = True
    require_drawn_signature_owner: bool = False
    require_drawn_signature_staff: bool = False


class UpdateContractRequest(BaseModel):
    title: Optional[str] = None
    body: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    assigned_staff_id: Optional[str] = None
    require_owner_signature: Optional[bool] = None
    require_staff_signature: Optional[bool] = None
    require_drawn_signature_owner: Optional[bool] = None
    require_drawn_signature_staff: Optional[bool] = None


class SignContractRequest(BaseModel):
    typed_name: Optional[str] = None
    drawing_base64: Optional[str] = None


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


@api_router.get("/contract-templates")
async def list_contract_templates(user: User = Depends(get_current_user)):
    return CONTRACT_TEMPLATES


@api_router.get("/contracts", response_model=List[Contract])
async def list_contracts(space_id: str, staff_id: Optional[str] = None, status: Optional[str] = None, user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    is_owner = space.get("owner_id") == user.user_id
    q: Dict[str, Any] = {"space_id": space_id}
    if staff_id:
        q["assigned_staff_id"] = staff_id
    if status:
        q["status"] = status
    if not is_owner:
        # Staff: only see contracts assigned to them
        my_staff = await db.staff_members.find_one({"space_id": space_id, "user_id": user.user_id}, {"_id": 0})
        if not my_staff:
            return []
        q["assigned_staff_id"] = my_staff["staff_id"]
    docs = await db.contracts.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return [Contract(**d) for d in docs]


@api_router.post("/contracts", response_model=Contract)
async def create_contract(body: CreateContractRequest, user: User = Depends(get_current_user)):
    space = await assert_space_member(body.space_id, user.user_id)
    if space.get("owner_id") != user.user_id:
        raise HTTPException(403, "Only the space owner can create contracts")
    title = (body.title or "").strip() or "Agreement"
    if not body.body or not body.body.strip():
        raise HTTPException(400, "body cannot be empty")
    assigned_staff_name = None
    if body.assigned_staff_id:
        sm = await db.staff_members.find_one({"staff_id": body.assigned_staff_id, "space_id": body.space_id}, {"_id": 0})
        if not sm:
            raise HTTPException(404, "Staff not found")
        assigned_staff_name = sm.get("name")
    doc = {
        "contract_id": gen_id("ctr"),
        "space_id": body.space_id,
        "template_kind": body.template_kind or "custom",
        "title": title,
        "body": body.body,
        "variables": body.variables or {},
        "assigned_staff_id": body.assigned_staff_id,
        "assigned_staff_name": assigned_staff_name,
        "require_owner_signature": bool(body.require_owner_signature),
        "require_staff_signature": bool(body.require_staff_signature),
        "require_drawn_signature_owner": bool(body.require_drawn_signature_owner),
        "require_drawn_signature_staff": bool(body.require_drawn_signature_staff),
        "status": "pending",
        "owner_signature": None,
        "staff_signature": None,
        "created_by": user.user_id,
        "created_by_name": user.name,
        "created_at": now_utc(),
        "updated_at": None,
    }
    await db.contracts.insert_one(doc)
    doc.pop("_id", None)
    # Notify the staff user if linked
    if body.assigned_staff_id:
        sm = await db.staff_members.find_one({"staff_id": body.assigned_staff_id}, {"_id": 0})
        if sm and sm.get("user_id"):
            await notify_user(
                user_id=sm["user_id"],
                space_id=body.space_id,
                kind="contract_assigned",
                title=f"Please review & sign: {title}",
                body=f"{user.name} has assigned a {doc['template_kind']} agreement for you to sign.",
                data={"contract_id": doc["contract_id"]},
            )
    # Realtime: tell every space member a contract was created (refresh the list)
    await emit_space_event(body.space_id, "contract", "created", {"contract_id": doc["contract_id"], "assigned_staff_id": body.assigned_staff_id})
    return Contract(**doc)


@api_router.get("/contracts/{contract_id}", response_model=Contract)
async def get_contract(contract_id: str, user: User = Depends(get_current_user)):
    d = await db.contracts.find_one({"contract_id": contract_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Contract not found")
    space = await assert_space_member(d["space_id"], user.user_id)
    is_owner = space.get("owner_id") == user.user_id
    if not is_owner:
        my_staff = await db.staff_members.find_one({"space_id": d["space_id"], "user_id": user.user_id}, {"_id": 0})
        if not my_staff or my_staff["staff_id"] != d.get("assigned_staff_id"):
            raise HTTPException(403, "Not authorized to view this contract")
    return Contract(**d)


@api_router.patch("/contracts/{contract_id}", response_model=Contract)
async def update_contract(contract_id: str, body: UpdateContractRequest, user: User = Depends(get_current_user)):
    d = await db.contracts.find_one({"contract_id": contract_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Contract not found")
    space = await assert_space_member(d["space_id"], user.user_id)
    if space.get("owner_id") != user.user_id:
        raise HTTPException(403, "Only the owner can edit contracts")
    updates_in = {k: v for k, v in body.dict(exclude_unset=True).items() if v is not None}
    has_owner_sig = bool(d.get("owner_signature"))
    has_staff_sig = bool(d.get("staff_signature"))
    # Once any party has signed, the legal text must not change. But reassigning
    # the staff or toggling whether staff signature is required is still allowed
    # (as long as the staff hasn't signed yet) so the owner can rescue a
    # mis-assigned contract without losing their own signature.
    if (has_owner_sig or has_staff_sig):
        text_fields = {"title", "body", "variables", "require_drawn_signature_owner", "require_drawn_signature_staff", "require_owner_signature"}
        bad = text_fields & set(updates_in.keys())
        if bad:
            raise HTTPException(400, f"Cannot edit {sorted(bad)} once a contract is signed. Void it and create a new one.")
        if has_staff_sig and ("assigned_staff_id" in updates_in or "require_staff_signature" in updates_in):
            raise HTTPException(400, "Cannot reassign a contract once the staff has signed. Void it first.")
    updates = updates_in
    if "assigned_staff_id" in updates and updates["assigned_staff_id"]:
        sm = await db.staff_members.find_one({"staff_id": updates["assigned_staff_id"], "space_id": d["space_id"]}, {"_id": 0})
        if not sm:
            raise HTTPException(404, "Staff not found")
        updates["assigned_staff_name"] = sm.get("name")
        # Notify the newly-assigned staff (if their user_id is linked)
        if sm.get("user_id"):
            try:
                exists = await db.notifications.find_one({
                    "user_id": sm["user_id"],
                    "kind": "contract_assigned",
                    "data.contract_id": contract_id,
                })
                if not exists:
                    await notify_user(
                        user_id=sm["user_id"],
                        space_id=d["space_id"],
                        kind="contract_assigned",
                        title=f"Please review & sign: {updates.get('title') or d.get('title')}",
                        body=f"{user.name} has assigned an agreement for you to sign.",
                        data={"contract_id": contract_id},
                    )
            except Exception as e:
                logger.warning(f"Could not notify reassigned staff: {e}")
    if updates:
        updates["updated_at"] = now_utc()
        await db.contracts.update_one({"contract_id": contract_id}, {"$set": updates})
    out = await db.contracts.find_one({"contract_id": contract_id}, {"_id": 0})
    await emit_space_event(d["space_id"], "contract", "updated", {"contract_id": contract_id})
    return Contract(**out)


@api_router.post("/contracts/{contract_id}/sign", response_model=Contract)
async def sign_contract(contract_id: str, body: SignContractRequest, request: Request, user: User = Depends(get_current_user)):
    d = await db.contracts.find_one({"contract_id": contract_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Contract not found")
    if d.get("status") == "void":
        raise HTTPException(400, "Contract has been voided")
    space = await assert_space_member(d["space_id"], user.user_id)
    is_owner = space.get("owner_id") == user.user_id
    role = "owner" if is_owner else "staff"

    if role == "staff":
        my_staff = await db.staff_members.find_one({"space_id": d["space_id"], "user_id": user.user_id}, {"_id": 0})
        if not my_staff or my_staff["staff_id"] != d.get("assigned_staff_id"):
            raise HTTPException(403, "This contract is not assigned to you")

    # Validate sig requirements
    require_drawn = bool(d.get(f"require_drawn_signature_{role}"))
    typed = (body.typed_name or "").strip()
    drawn = (body.drawing_base64 or "").strip()
    if require_drawn and not drawn:
        raise HTTPException(400, "A hand-drawn signature is required for this contract.")
    if not typed and not drawn:
        raise HTTPException(400, "Type your name or draw your signature to sign.")

    sig = {
        "role": role,
        "user_id": user.user_id,
        "name": user.name,
        "typed_name": typed or None,
        "drawing_base64": drawn or None,
        "signed_at": now_utc(),
        "ip": _client_ip(request),
        "user_agent": (request.headers.get("user-agent") or "")[:300],
    }
    field = "owner_signature" if role == "owner" else "staff_signature"
    update: Dict[str, Any] = {field: sig, "updated_at": now_utc()}

    # Check if both required signatures are present after this one
    other = d.get("staff_signature" if role == "owner" else "owner_signature")
    require_other = bool(d.get(f"require_{'staff' if role == 'owner' else 'owner'}_signature"))
    if (not require_other) or other:
        update["status"] = "signed"

    await db.contracts.update_one({"contract_id": contract_id}, {"$set": update})

    # Notify the other party if they still need to sign
    if update.get("status") != "signed":
        # If owner just signed, notify staff
        if role == "owner" and d.get("assigned_staff_id"):
            sm = await db.staff_members.find_one({"staff_id": d["assigned_staff_id"]}, {"_id": 0})
            if sm and sm.get("user_id"):
                await notify_user(
                    user_id=sm["user_id"],
                    space_id=d["space_id"],
                    kind="contract_owner_signed",
                    title=f"{user.name} signed: {d.get('title')}",
                    body="Your turn — open the contract to review and sign.",
                    data={"contract_id": contract_id},
                )
        # If staff just signed, notify owner
        if role == "staff":
            await notify_user(
                user_id=space.get("owner_id"),
                space_id=d["space_id"],
                kind="contract_staff_signed",
                title=f"{user.name} signed: {d.get('title')}",
                body="The staff member has signed the agreement.",
                data={"contract_id": contract_id},
            )
    else:
        # Fully signed — store a copy in Documents Vault as a record
        try:
            await db.documents.insert_one({
                "document_id": gen_id("doc"),
                "space_id": d["space_id"],
                "name": f"{d.get('title')} — signed {now_utc().strftime('%Y-%m-%d')}",
                "folder": "contracts",
                "mime": "application/contract+json",
                "file_base64": None,
                "note": f"Signed agreement (kind={d.get('template_kind')}). View in Contracts.",
                "tags": ["contract", d.get("template_kind") or "custom", "signed"],
                "size_kb": max(1, int(len(d.get("body") or "") / 1024)),
                "uploaded_by": user.user_id,
                "uploaded_by_name": user.name,
                "created_at": now_utc(),
                "related_to": {"kind": "contract", "id": contract_id},
            })
        except Exception as e:
            logger.warning(f"Could not archive contract to documents: {e}")

    out = await db.contracts.find_one({"contract_id": contract_id}, {"_id": 0})
    await emit_space_event(d["space_id"], "contract", "signed", {"contract_id": contract_id, "by": role, "status": out.get("status")})
    return Contract(**out)


@api_router.post("/contracts/{contract_id}/void", response_model=Contract)
async def void_contract(contract_id: str, user: User = Depends(get_current_user)):
    d = await db.contracts.find_one({"contract_id": contract_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Contract not found")
    space = await assert_space_member(d["space_id"], user.user_id)
    if space.get("owner_id") != user.user_id:
        raise HTTPException(403, "Only the owner can void contracts")
    await db.contracts.update_one({"contract_id": contract_id}, {"$set": {"status": "void", "updated_at": now_utc()}})
    out = await db.contracts.find_one({"contract_id": contract_id}, {"_id": 0})
    await emit_space_event(d["space_id"], "contract", "voided", {"contract_id": contract_id})
    return Contract(**out)


@api_router.delete("/contracts/{contract_id}")
async def delete_contract(contract_id: str, user: User = Depends(get_current_user)):
    d = await db.contracts.find_one({"contract_id": contract_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Contract not found")
    space = await assert_space_member(d["space_id"], user.user_id)
    if space.get("owner_id") != user.user_id:
        raise HTTPException(403, "Only the owner can delete contracts")
    await db.contracts.delete_one({"contract_id": contract_id})
    await emit_space_event(d["space_id"], "contract", "deleted", {"contract_id": contract_id})
    return {"ok": True}


@api_router.get("/contracts/{contract_id}/render")
async def render_contract(contract_id: str, user: User = Depends(get_current_user)):
    d = await db.contracts.find_one({"contract_id": contract_id}, {"_id": 0})
    if not d:
        raise HTTPException(404, "Contract not found")
    space = await assert_space_member(d["space_id"], user.user_id)
    is_owner = space.get("owner_id") == user.user_id
    if not is_owner:
        my_staff = await db.staff_members.find_one({"space_id": d["space_id"], "user_id": user.user_id}, {"_id": 0})
        if not my_staff or my_staff["staff_id"] != d.get("assigned_staff_id"):
            raise HTTPException(403, "Not authorized")
    rendered = _render_contract_body(d.get("body") or "", d.get("variables") or {})
    return {"title": d.get("title"), "rendered_body": rendered, "status": d.get("status"), "variables": d.get("variables") or {}}


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# =========================
# Wrap FastAPI with Socket.IO ASGI app
# Supervisor still runs `uvicorn server:app` — `app` is now the wrapped ASGI app.
# All FastAPI routes still go through `fastapi_app` underneath.
# =========================
fastapi_app = app
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app, socketio_path='/api/socket.io')

