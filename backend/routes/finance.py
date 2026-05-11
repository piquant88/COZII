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
