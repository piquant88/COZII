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
    _ensure_default_roles, _attach_role_name, _gen_staff_invite_code, _ensure_wages_category, _task_due_on, _create_notification,
)
# Pydantic models are re-exported through `models` for convenience.
from models import *  # noqa: F401,F403
import models as _m  # noqa: F401  (typed access if needed)



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
    is_owner = isinstance(space, dict) and space.get("owner_id") == user.user_id
    # Both regular requests AND reimbursements start as "pending":
    #   - request: pending = awaiting owner approval to buy
    #   - reimbursement: pending = awaiting owner pay-back (item already bought by staff)
    # The `kind` field disambiguates the meaning of "pending" in the UI.
    # Exception: when the OWNER themself is the requester, there's nothing to
    # approve — they are the approver. Auto-approve so the item lands directly
    # in the right "shopping" / "purchased" lane without an extra tap.
    initial_status = "approved" if is_owner else "pending"
    now_ts = now_utc()
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
        "approved_by": user.user_id if is_owner else None,
        "approved_at": now_ts if is_owner else None,
        "rejected_reason": None,
        "purchased_by": None,
        "purchased_at": None,
        "fulfilled_at": None,
        "created_at": now_ts,
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


@api_router.delete("/household/shopping/{request_id}")
async def delete_shopping(request_id: str, user: User = Depends(get_current_user)):
    r = await db.shopping_requests.find_one({"request_id": request_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Request not found")
    await assert_space_member(r["space_id"], user.user_id)
    await db.shopping_requests.delete_one({"request_id": request_id})
    return {"ok": True}
