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
    _parse_iso_date, _send_digest_for_space, _search_product_image, _extract_json_block, _compute_alerts_for_space,
)
# Pydantic models are re-exported through `models` for convenience.
from models import *  # noqa: F401,F403
import models as _m  # noqa: F401  (typed access if needed)



# =========================
# Categories
# =========================
@api_router.post("/categories", response_model=Category)
async def create_category(body: CreateCategoryRequest, user: User = Depends(get_current_user)):
    space = await assert_space_member(body.space_id, user.user_id)
    # Only the owner can create categories. Staff editing is fine-grained per-category.
    if space.get("owner_id") != user.user_id:
        raise HTTPException(403, "Only the household owner can create categories.")
    doc = {
        "category_id": gen_id("cat"),
        "space_id": body.space_id,
        "name": body.name.strip(),
        "icon": body.icon,
        "tint": body.tint,
        "fields": [f.dict() for f in body.fields],
        "shared_with": body.shared_with,
        "staff_can_edit": bool(body.staff_can_edit),
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
    space = await assert_space_member(cat["space_id"], user.user_id)
    # Only owner can change category metadata (incl. the staff_can_edit toggle).
    if space.get("owner_id") != user.user_id:
        raise HTTPException(403, "Only the household owner can edit categories.")
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
    if body.staff_can_edit is not None:
        updates["staff_can_edit"] = bool(body.staff_can_edit)
    if updates:
        await db.categories.update_one({"category_id": category_id}, {"$set": updates})
    out = await db.categories.find_one({"category_id": category_id}, {"_id": 0})
    await record_activity(cat["space_id"], user, "updated", "category", category_id, out.get("name") or "")
    return Category(**out)


@api_router.delete("/categories/{category_id}")
async def delete_category(category_id: str, user: User = Depends(get_current_user)):
    cat = await db.categories.find_one({"category_id": category_id}, {"_id": 0})
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    space = await assert_space_member(cat["space_id"], user.user_id)
    if space.get("owner_id") != user.user_id:
        raise HTTPException(403, "Only the household owner can delete categories.")
    await db.categories.delete_one({"category_id": category_id})
    await db.items.delete_many({"category_id": category_id})
    await record_activity(cat["space_id"], user, "deleted", "category", category_id, cat.get("name") or "")
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
    await assert_can_edit_category_items(body.space_id, body.category_id, user.user_id)
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
    # Permission check: staff can edit only categories where staff_can_edit=true
    target_cat_id = body.category_id if getattr(body, 'category_id', None) else doc.get("category_id")
    await assert_can_edit_category_items(doc["space_id"], target_cat_id, user.user_id)
    if target_cat_id != doc.get("category_id"):
        # Also check the source category (where the item currently lives)
        await assert_can_edit_category_items(doc["space_id"], doc["category_id"], user.user_id)

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
    await assert_can_edit_category_items(doc["space_id"], doc["category_id"], user.user_id)
    await db.items.delete_one({"item_id": item_id})
    await record_activity(doc["space_id"], user, "deleted", "item", item_id, doc["name"])
    return {"success": True}


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


@api_router.post("/items/bulk", response_model=List[Item])
async def bulk_create_items(body: BulkCreateItemsRequest, user: User = Depends(get_current_user)):
    await assert_space_member(body.space_id, user.user_id)
    cat_docs = await db.categories.find({"space_id": body.space_id}, {"_id": 0, "category_id": 1}).to_list(200)
    valid_cat_ids = {c["category_id"] for c in cat_docs}
    if body.category_id not in valid_cat_ids:
        raise HTTPException(status_code=400, detail="Invalid default category")
    # Permission check: bulk-add only goes into the requested category
    await assert_can_edit_category_items(body.space_id, body.category_id, user.user_id)

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


@api_router.get("/inventory/alerts")
async def inventory_alerts(space_id: str, days_threshold: int = 7, user: User = Depends(get_current_user)):
    """Return inventory items grouped by alert kind:
       - low_stock (status=='low')
       - finished (status=='finished')
       - expired (expiry_date < today)
       - expiring (today <= expiry_date <= today + days_threshold)
    """
    await assert_space_member(space_id, user.user_id)
    items = await db.items.find({"space_id": space_id}, {"_id": 0}).to_list(5000)
    cats = await db.categories.find({"space_id": space_id}, {"_id": 0, "category_id": 1, "name": 1, "icon": 1, "tint": 1, "staff_can_edit": 1}).to_list(500)
    cat_map = {c["category_id"]: c for c in cats}

    today = now_utc().replace(hour=0, minute=0, second=0, microsecond=0)
    threshold = today + timedelta(days=max(0, days_threshold))
    low: List[Dict[str, Any]] = []
    finished: List[Dict[str, Any]] = []
    expiring: List[Dict[str, Any]] = []
    expired: List[Dict[str, Any]] = []

    for it in items:
        cat_meta = cat_map.get(it.get("category_id")) or {}
        enriched = {
            **it,
            "category_name": cat_meta.get("name"),
            "category_icon": cat_meta.get("icon"),
            "category_tint": cat_meta.get("tint"),
        }
        # Status-based alerts
        st = (it.get("status") or "available").lower()
        if st == "low":
            low.append(enriched)
        elif st == "finished":
            finished.append(enriched)
        # Expiry-based alerts
        exp = _parse_iso_date(it.get("expiry_date"))
        if exp:
            if exp < today:
                expired.append(enriched)
            elif exp <= threshold:
                expiring.append(enriched)

    # Sort each list: most-urgent / oldest expiry first
    low.sort(key=lambda x: x.get("name", ""))
    finished.sort(key=lambda x: x.get("name", ""))
    expiring.sort(key=lambda x: _parse_iso_date(x.get("expiry_date")) or threshold)
    expired.sort(key=lambda x: _parse_iso_date(x.get("expiry_date")) or today)

    return {
        "space_id": space_id,
        "as_of": today.isoformat(),
        "days_threshold": days_threshold,
        "totals": {
            "low": len(low),
            "finished": len(finished),
            "expiring": len(expiring),
            "expired": len(expired),
            "all": len(low) + len(finished) + len(expiring) + len(expired),
        },
        "low_stock": low,
        "finished": finished,
        "expiring": expiring,
        "expired": expired,
    }


@api_router.post("/inventory/alerts/to-shopping")
async def alerts_to_shopping(body: AlertsToShoppingRequest, user: User = Depends(get_current_user)):
    """Convert one or more inventory items into ShoppingRequest entries (status=pending).
    Skips items that already have an open shopping request (pending or approved) for the same name in this space.
    """
    space = await assert_space_member(body.space_id, user.user_id)
    if not body.item_ids:
        raise HTTPException(400, "Pick at least one item.")
    items = await db.items.find({"space_id": body.space_id, "item_id": {"$in": body.item_ids}}, {"_id": 0}).to_list(500)
    if not items:
        return {"created": 0, "skipped": 0, "request_ids": []}
    currency = (space.get("currency") if isinstance(space, dict) else None) or "USD"

    created_ids: List[str] = []
    skipped = 0
    for it in items:
        name = (it.get("name") or "").strip()
        if not name:
            continue
        # Dedupe: skip if already an open shopping request with the same name
        existing = await db.shopping_requests.find_one({
            "space_id": body.space_id,
            "item_name": name,
            "status": {"$in": ["pending", "approved"]},
        })
        if existing:
            skipped += 1
            continue
        urgency = body.urgency if body.urgency in ("low", "normal", "high") else "normal"
        # Auto-bump urgency for finished/expired
        st = (it.get("status") or "").lower()
        exp = _parse_iso_date(it.get("expiry_date"))
        today = now_utc()
        if st == "finished" or (exp and exp < today):
            urgency = "high"
        doc = {
            "request_id": gen_id("shop"),
            "space_id": body.space_id,
            "item_name": name,
            "quantity": it.get("quantity"),
            "note": body.note or f"Auto from {st or 'inventory'} alert",
            "category_id": it.get("category_id"),
            "urgency": urgency,
            "status": "pending",
            "kind": "request",
            "estimated_price": it.get("price"),
            "actual_price": None,
            "currency": currency,
            "photo_base64": None,
            "requested_by": user.user_id,
            "requested_by_staff_id": None,
            "approved_by": None,
            "approved_at": None,
            "rejected_reason": None,
            "purchased_by": None,
            "purchased_at": None,
            "fulfilled_at": None,
            "created_at": now_utc(),
        }
        await db.shopping_requests.insert_one(doc)
        created_ids.append(doc["request_id"])
        await emit_space_event(body.space_id, "shopping", "created", {"request_id": doc["request_id"], "from_alert": True})

    return {"created": len(created_ids), "skipped": skipped, "request_ids": created_ids}


# Manual trigger / test endpoint — owner-only
@api_router.post("/inventory/alerts/digest/send")
async def send_digest_now(space_id: str, user: User = Depends(get_current_user)):
    space = await assert_space_member(space_id, user.user_id)
    if space.get("owner_id") != user.user_id:
        raise HTTPException(403, "Only the household owner can trigger the digest")
    sent = await _send_digest_for_space(space)
    if sent:
        return {"sent": True, "message": "Digest notification sent"}
    return {"sent": False, "message": "No alerts right now"}
