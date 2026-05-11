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

    # Always notify the other party that they signed (the gate was wrong before
    # — owner should still be notified when staff is the LAST signer, so the
    # owner sees "fully signed" arrive in their notifications).
    if role == "owner" and d.get("assigned_staff_id"):
        sm = await db.staff_members.find_one({"staff_id": d["assigned_staff_id"]}, {"_id": 0})
        if sm and sm.get("user_id"):
            await notify_user(
                user_id=sm["user_id"],
                space_id=d["space_id"],
                kind="contract_owner_signed",
                title=f"{user.name} signed: {d.get('title')}",
                body="Your turn — open the contract to review and sign." if update.get("status") != "signed" else "Both parties have now signed.",
                data={"contract_id": contract_id},
            )
    if role == "staff":
        await notify_user(
            user_id=space.get("owner_id"),
            space_id=d["space_id"],
            kind="contract_staff_signed",
            title=f"{user.name} signed: {d.get('title')}",
            body="The staff member has signed the agreement.",
            data={"contract_id": contract_id},
        )

    if update.get("status") == "signed":
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
