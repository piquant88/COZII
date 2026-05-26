"""Unified Purchase Session API (Phase C).

A purchase session represents a single shopping trip — one merchant, one date,
one total — that fans out into four coordinated side-effects:

  1. Inventory : each line item increments the matching inventory item
                 (creates it if missing & create_item=True).
  2. Audit     : an item_audit_log row is written for every inventory
                 change with source="purchase_session" + source_id=session_id.
  3. Shopping  : shopping_requests referenced via source_request_ids are
                 marked status="purchased".
  4. Activity  : a single record_activity entry is emitted (not one per
                 item), which fires the real-time Socket.IO event.

The intent is to avoid duplicate "finance group" / "shopping group" /
"inventory purchase group" systems — there is ONE model that everything
points at.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, Depends
from pydantic import BaseModel

from core import (
    app, api_router, db, logger,
    now_utc, gen_id,
    get_current_user, assert_space_member, assert_can_edit_category_items,
    record_activity, emit_space_event,
)
from models import (
    PurchaseSession,
    PurchaseSessionItem,
    CreatePurchaseSessionRequest,
    UpdatePurchaseSessionRequest,
    User,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _today_iso() -> str:
    return now_utc().date().isoformat()


async def _resolve_or_create_item(
    space_id: str,
    category_id: Optional[str],
    name: str,
    user_id: str,
    initial_qty: float = 0.0,
    unit: Optional[str] = None,
) -> Dict[str, Any]:
    """Find an inventory item by (space, optional category, name) — case
    insensitive — and create it if missing. Returns the canonical item doc."""
    q = {
        "space_id": space_id,
        "name": {"$regex": f"^{re.escape(name.strip())}$", "$options": "i"},
    }
    if category_id:
        q["category_id"] = category_id
    existing = await db.items.find_one(q, {"_id": 0})
    if existing:
        return existing
    # Create a new inventory item
    if not category_id:
        # Use the first category in the space as a fallback.
        first_cat = await db.categories.find_one({"space_id": space_id}, {"_id": 0, "category_id": 1})
        if not first_cat:
            raise HTTPException(status_code=400, detail="No category to attach new item to")
        category_id = first_cat["category_id"]
    doc = {
        "item_id": gen_id("item"),
        "space_id": space_id,
        "category_id": category_id,
        "name": name.strip(),
        "quantity": float(initial_qty or 0),
        "unit": unit,
        "status": "good" if (initial_qty or 0) > 0 else "low",
        "fields": {},
        "photo_base64": None,
        "image_url": None,
        "low_threshold": 1,
        "expiry_date": None,
        "purchase_date": _today_iso(),
        "price": None,
        "notes": None,
        "created_by": user_id,
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.items.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def _apply_session_to_inventory(
    session_id: str,
    space_id: str,
    items: List[PurchaseSessionItem],
    user: User,
) -> List[PurchaseSessionItem]:
    """For each item line, increment inventory + write audit row.
    Returns the items list with `item_id` + `inventory_applied` populated."""
    applied: List[PurchaseSessionItem] = []
    for idx, line in enumerate(items):
        # Skip lines with zero quantity (just notes)
        if not line.quantity or float(line.quantity) <= 0:
            applied.append(line.model_copy(update={
                "line_id": line.line_id or f"line_{idx}",
                "inventory_applied": False,
            }))
            continue

        try:
            if line.item_id:
                item = await db.items.find_one({"item_id": line.item_id}, {"_id": 0})
                if not item:
                    raise HTTPException(404, f"Item {line.item_id} not found")
            elif line.create_item:
                item = await _resolve_or_create_item(
                    space_id=space_id,
                    category_id=line.category_id,
                    name=line.name,
                    user_id=user.user_id,
                    initial_qty=0,
                    unit=line.unit,
                )
            else:
                applied.append(line.model_copy(update={
                    "line_id": line.line_id or f"line_{idx}",
                    "inventory_applied": False,
                }))
                continue

            # Permission gate: respect existing staff_can_edit on category
            try:
                await assert_can_edit_category_items(space_id, item.get("category_id"), user.user_id)
            except HTTPException:
                # Skip silently — the session still records the line, just no
                # inventory mutation for this user/category combo.
                applied.append(line.model_copy(update={
                    "line_id": line.line_id or f"line_{idx}",
                    "item_id": item["item_id"],
                    "inventory_applied": False,
                }))
                continue

            prev_qty = float(item.get("quantity") or 0)
            new_qty = prev_qty + float(line.quantity)
            # Auto status
            new_status = item.get("status") or "good"
            if new_qty == 0:
                new_status = "finished"
            elif new_qty < (item.get("low_threshold") or 0):
                new_status = "low"
            else:
                if new_status in ("finished", "low"):
                    new_status = "good"

            update_set: Dict[str, Any] = {
                "quantity": new_qty,
                "status": new_status,
                "updated_at": now_utc(),
            }
            # Record last paid price if line carries it
            if line.unit_price is not None:
                update_set["price"] = float(line.unit_price)
            if line.unit and not item.get("unit"):
                update_set["unit"] = line.unit

            await db.items.update_one(
                {"item_id": item["item_id"]},
                {"$set": update_set},
            )

            # Audit row
            await db.item_audit_log.insert_one({
                "audit_id": gen_id("aud"),
                "item_id": item["item_id"],
                "space_id": space_id,
                "category_id": item.get("category_id"),
                "item_name": item.get("name"),
                "user_id": user.user_id,
                "user_name": user.name or user.email or user.user_id,
                "action": "incremented",
                "delta": float(line.quantity),
                "prev_qty": prev_qty,
                "new_qty": new_qty,
                "unit": item.get("unit") or line.unit,
                "note": None,
                "source": "purchase_session",
                "source_id": session_id,
                "created_at": now_utc(),
            })

            applied.append(line.model_copy(update={
                "line_id": line.line_id or f"line_{idx}",
                "item_id": item["item_id"],
                "category_id": item.get("category_id"),
                "unit": item.get("unit") or line.unit,
                "inventory_applied": True,
            }))
        except HTTPException:
            raise
        except Exception as e:
            logger.exception(f"purchase_session item apply failed line={idx} session={session_id}")
            applied.append(line.model_copy(update={
                "line_id": line.line_id or f"line_{idx}",
                "inventory_applied": False,
            }))
    return applied


async def _mark_requests_purchased(space_id: str, request_ids: List[str], session_id: str, user: User):
    if not request_ids:
        return
    await db.shopping_requests.update_many(
        {"space_id": space_id, "request_id": {"$in": request_ids}},
        {"$set": {
            "status": "purchased",
            "purchased_by": user.user_id,
            "purchased_at": now_utc(),
            "purchased_via_session_id": session_id,
        }},
    )


async def _rollback_inventory(session: Dict[str, Any], user: User):
    """Best-effort: undo inventory increments and remove audit rows for a deleted session."""
    items = session.get("items") or []
    for line in items:
        if not line.get("inventory_applied"):
            continue
        item_id = line.get("item_id")
        qty = float(line.get("quantity") or 0)
        if not item_id or qty <= 0:
            continue
        item = await db.items.find_one({"item_id": item_id}, {"_id": 0, "quantity": 1, "low_threshold": 1, "status": 1})
        if not item:
            continue
        prev = float(item.get("quantity") or 0)
        next_qty = max(0.0, prev - qty)
        new_status = item.get("status") or "good"
        if next_qty == 0:
            new_status = "finished"
        elif next_qty < (item.get("low_threshold") or 0):
            new_status = "low"
        await db.items.update_one(
            {"item_id": item_id},
            {"$set": {"quantity": next_qty, "status": new_status, "updated_at": now_utc()}},
        )
    # Remove audit rows tied to this session
    try:
        await db.item_audit_log.delete_many({"source": "purchase_session", "source_id": session["session_id"]})
    except Exception as e:
        logger.warning(f"audit cleanup for {session.get('session_id')} failed: {e}")
    # Reopen any shopping requests that were marked purchased via this session
    try:
        await db.shopping_requests.update_many(
            {"purchased_via_session_id": session["session_id"]},
            {"$set": {"status": "approved", "purchased_by": None, "purchased_at": None,
                      "purchased_via_session_id": None}},
        )
    except Exception:
        pass


# Need re import for _resolve_or_create_item case-insensitive lookup
import re


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@api_router.post("/purchase-sessions", response_model=PurchaseSession)
async def create_purchase_session(body: CreatePurchaseSessionRequest, user: User = Depends(get_current_user)):
    space = await assert_space_member(body.space_id, user.user_id)
    if not (body.merchant or "").strip():
        raise HTTPException(400, "Merchant is required")
    session_id = gen_id("ps")
    currency = body.currency or (space.get("currency") if isinstance(space, dict) else None) or "USD"
    purchase_date = body.purchase_date or _today_iso()
    source = body.source or "manual"
    source_request_ids = body.source_request_ids or []
    paid_by = body.paid_by or user.user_id

    try:
        applied_items = await _apply_session_to_inventory(session_id, body.space_id, body.items or [], user)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"create_purchase_session inventory side-effect failed")
        raise HTTPException(400, f"Could not apply session to inventory: {e}")

    # Compute total if missing
    if body.total is None:
        try:
            total = sum(
                float(it.total_price if it.total_price is not None
                      else (it.unit_price or 0) * (it.quantity or 0))
                for it in applied_items
            )
        except Exception:
            total = 0.0
    else:
        total = float(body.total or 0)

    doc = {
        "session_id": session_id,
        "space_id": body.space_id,
        "merchant": body.merchant.strip(),
        "purchase_date": purchase_date,
        "total": total,
        "currency": currency,
        "receipt_image_base64": body.receipt_image_base64,
        "receipt_raw": body.receipt_raw,
        "source": source,
        "source_request_ids": source_request_ids,
        "items": [it.model_dump() for it in applied_items],
        "paid_by": paid_by,
        "notes": body.notes,
        "created_by": user.user_id,
        "created_at": now_utc(),
        "updated_at": None,
    }
    await db.purchase_sessions.insert_one(doc)

    # Side-effect: mark shopping requests as purchased
    try:
        await _mark_requests_purchased(body.space_id, source_request_ids, session_id, user)
    except Exception as e:
        logger.warning(f"purchase_session request-link failed: {e}")

    # Activity feed (one entry per session)
    try:
        await record_activity(
            body.space_id, user,
            f"created purchase session {body.merchant} — {currency} {total:,.0f}",
            "purchase_session", session_id, body.merchant,
        )
    except Exception:
        pass

    doc.pop("_id", None)
    return PurchaseSession(**doc)


@api_router.get("/purchase-sessions", response_model=List[PurchaseSession])
async def list_purchase_sessions(
    space_id: str,
    limit: int = 50,
    user: User = Depends(get_current_user),
):
    await assert_space_member(space_id, user.user_id)
    rows = await db.purchase_sessions.find(
        {"space_id": space_id}, {"_id": 0},
    ).sort("created_at", -1).limit(max(1, min(200, int(limit or 50)))).to_list(200)
    return [PurchaseSession(**r) for r in rows]


@api_router.get("/purchase-sessions/{session_id}", response_model=PurchaseSession)
async def get_purchase_session(session_id: str, user: User = Depends(get_current_user)):
    doc = await db.purchase_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Purchase session not found")
    await assert_space_member(doc["space_id"], user.user_id)
    return PurchaseSession(**doc)


@api_router.patch("/purchase-sessions/{session_id}", response_model=PurchaseSession)
async def update_purchase_session(
    session_id: str,
    body: UpdatePurchaseSessionRequest,
    user: User = Depends(get_current_user),
):
    doc = await db.purchase_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Purchase session not found")
    await assert_space_member(doc["space_id"], user.user_id)
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return PurchaseSession(**doc)
    updates["updated_at"] = now_utc()
    await db.purchase_sessions.update_one({"session_id": session_id}, {"$set": updates})
    new_doc = await db.purchase_sessions.find_one({"session_id": session_id}, {"_id": 0})
    return PurchaseSession(**new_doc)


@api_router.delete("/purchase-sessions/{session_id}")
async def delete_purchase_session(session_id: str, user: User = Depends(get_current_user)):
    """Best-effort rollback: remove inventory increments + audit rows + reopen
    linked shopping requests, then delete the session itself."""
    doc = await db.purchase_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Purchase session not found")
    space = await assert_space_member(doc["space_id"], user.user_id)
    # Only owner of space OR original creator can delete
    is_owner = isinstance(space, dict) and space.get("owner_id") == user.user_id
    if not is_owner and doc.get("created_by") != user.user_id:
        raise HTTPException(403, "Only the owner or original creator can delete a purchase session")
    await _rollback_inventory(doc, user)
    await db.purchase_sessions.delete_one({"session_id": session_id})
    try:
        await record_activity(
            doc["space_id"], user,
            f"deleted purchase session {doc.get('merchant', '')}",
            "purchase_session", session_id, doc.get("merchant", ""),
        )
    except Exception:
        pass
    return {"ok": True}
