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
import json
import re
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any
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
class User(BaseModel):
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


class FamilySpace(BaseModel):
    space_id: str
    name: str
    owner_id: str
    member_ids: List[str]
    invite_code: str
    created_at: datetime


class CreateSpaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class JoinSpaceRequest(BaseModel):
    invite_code: str


class CategoryField(BaseModel):
    key: str
    label: str
    type: str  # text | number | date | price


class Category(BaseModel):
    category_id: str
    space_id: str
    name: str
    icon: str
    tint: str  # color tint key
    fields: List[CategoryField]
    created_by: str
    created_at: datetime


class CreateCategoryRequest(BaseModel):
    space_id: str
    name: str = Field(min_length=1, max_length=40)
    icon: str = "Box"
    tint: str = "mint"
    fields: List[CategoryField] = []


class UpdateCategoryRequest(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    tint: Optional[str] = None
    fields: Optional[List[CategoryField]] = None


class Item(BaseModel):
    item_id: str
    space_id: str
    category_id: str
    name: str
    photo_base64: Optional[str] = None
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
    updated_at: datetime


class CreateItemRequest(BaseModel):
    space_id: str
    category_id: str
    name: str = Field(min_length=1, max_length=80)
    photo_base64: Optional[str] = None
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
    status: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    price: Optional[float] = None
    purchase_date: Optional[str] = None
    expiry_date: Optional[str] = None
    notes: Optional[str] = None
    fields: Optional[Dict[str, Any]] = None
    category_id: Optional[str] = None


class ActivityItem(BaseModel):
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
    space = {
        "space_id": gen_id("space"),
        "name": body.name.strip(),
        "owner_id": user.user_id,
        "member_ids": [user.user_id],
        "invite_code": gen_invite_code(),
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
    docs.sort(key=lambda d: d["created_at"])
    return [Category(**d) for d in docs]


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


class ScannedItem(BaseModel):
    name: str
    quantity: float = 1
    price: Optional[float] = None
    category_hint: Optional[str] = None


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
        "You are a helpful assistant that extracts shopping items from receipt or product images. "
        "Return STRICT JSON only, no prose, in this schema: "
        '{"items":[{"name":"string","quantity":number,"price":number_or_null,"category_hint":"food|skincare|toiletries|closet|cleaning|other"}]}. '
        "Skip tax, subtotal, total, fees, change, tip, payment type, and store name. "
        "Use lowercase category_hint values. If price is unclear, set it to null. Quantity defaults to 1."
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

    try:
        parsed = json.loads(json_text)
    except Exception:
        raise HTTPException(status_code=502, detail="AI returned unparseable response")

    items_raw = parsed.get("items", []) if isinstance(parsed, dict) else []
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
        items.append(ScannedItem(name=name, quantity=qty, price=price, category_hint=hint))

    return ScanReceiptResponse(items=items, raw=text[:2000])


class BulkCreateItemsRequest(BaseModel):
    space_id: str
    category_id: str  # Default category
    per_item_category: Dict[str, str] = {}  # index -> category_id override
    items: List[ScannedItem]
    purchase_date: Optional[str] = None
    receipt_photo_base64: Optional[str] = None


@api_router.post("/items/bulk", response_model=List[Item])
async def bulk_create_items(body: BulkCreateItemsRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    # Load categories owned by this space to validate ids
    cat_docs = await db.categories.find({"space_id": body.space_id}, {"_id": 0, "category_id": 1}).to_list(200)
    valid_cat_ids = {c["category_id"] for c in cat_docs}
    if body.category_id not in valid_cat_ids:
        raise HTTPException(status_code=400, detail="Invalid default category")

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
            "photo_base64": body.receipt_photo_base64,
            "status": "available",
            "quantity": it.quantity,
            "unit": None,
            "price": it.price,
            "purchase_date": body.purchase_date,
            "expiry_date": None,
            "notes": None,
            "fields": {},
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
