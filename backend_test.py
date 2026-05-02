"""
Backend tests for Cozii Household Phase 2:
  - /api/household/tasks (CRUD + completion toggle + due-on-date logic)
  - /api/household/attendance (upsert + filter)
  - /api/household/shopping (CRUD + status transitions + enrichment)

Run:
    python /app/backend_test.py
"""
from __future__ import annotations
import os
import sys
import time
import json
import uuid
import requests
from datetime import datetime, timezone, timedelta, date

BASE = "https://family-wallet-21.preview.emergentagent.com/api"

PRIMARY_EMAIL = "test@cozii.app"
PRIMARY_PASSWORD = "test1234"


def _u(suffix: str) -> str:
    return f"{BASE}/{suffix.lstrip('/')}"


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ============================================================
# Test bookkeeping
# ============================================================
RESULTS: list[tuple[bool, str, str]] = []


def record(ok: bool, name: str, detail: str = ""):
    RESULTS.append((ok, name, detail))
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}" + (f" -- {detail}" if detail and not ok else ""))


def section(title: str):
    print(f"\n=== {title} ===")


# ============================================================
# Auth + space prep
# ============================================================
def login_or_register(email: str, password: str, name: str) -> str:
    r = requests.post(_u("auth/login"), json={"email": email, "password": password}, timeout=30)
    if r.status_code == 200:
        return r.json()["token"]
    r = requests.post(_u("auth/register"), json={"email": email, "password": password, "name": name}, timeout=30)
    if r.status_code in (200, 201):
        return r.json()["token"]
    raise SystemExit(f"login/register failed for {email}: {r.status_code} {r.text}")


def get_or_create_household_space(token: str) -> dict:
    """Find/create a household space owned by this user."""
    r = requests.get(_u("spaces"), headers=_hdr(token), timeout=30)
    r.raise_for_status()
    spaces = r.json()
    me = requests.get(_u("auth/me"), headers=_hdr(token), timeout=30).json()
    my_uid = me["user_id"]
    for s in spaces:
        if s.get("owner_id") == my_uid and s.get("space_type") == "household":
            return s
    # Create a household one
    r = requests.post(_u("spaces"), headers=_hdr(token),
                      json={"name": f"Cozii Household Phase2 {uuid.uuid4().hex[:6]}",
                            "space_type": "household", "currency": "IDR"}, timeout=30)
    r.raise_for_status()
    return r.json()


def ensure_staff_and_category(token: str, space_id: str) -> tuple[str, str]:
    """Return (staff_id, category_id). Create them if missing."""
    # Roles auto-seed
    r = requests.get(_u("household/roles"), headers=_hdr(token), params={"space_id": space_id}, timeout=30)
    r.raise_for_status()
    roles = r.json()
    maid_role = next((x for x in roles if x.get("name") == "Maid"), None) or roles[0]

    # Staff
    r = requests.get(_u("household/staff"), headers=_hdr(token), params={"space_id": space_id}, timeout=30)
    r.raise_for_status()
    staff_list = r.json()
    if staff_list:
        staff_id = staff_list[0]["staff_id"]
    else:
        r = requests.post(_u("household/staff"), headers=_hdr(token), json={
            "space_id": space_id, "name": "Sari Wijaya", "role_id": maid_role["role_id"],
            "salary": 2500000, "pay_cycle": "monthly", "off_day": "Sunday",
        }, timeout=30)
        r.raise_for_status()
        staff_id = r.json()["staff_id"]

    # Category (any)
    r = requests.get(_u("categories"), headers=_hdr(token), params={"space_id": space_id}, timeout=30)
    r.raise_for_status()
    cats = r.json()
    if cats:
        cat_id = cats[0]["category_id"]
    else:
        r = requests.post(_u("categories"), headers=_hdr(token),
                          json={"space_id": space_id, "name": "Pantry", "icon": "Refrigerator", "tint": "mint"},
                          timeout=30)
        r.raise_for_status()
        cat_id = r.json()["category_id"]
    return staff_id, cat_id


# ============================================================
# 1. Tasks
# ============================================================
def test_tasks(token: str, space_id: str, outsider_token: str):
    section("Tasks (/api/household/tasks)")
    today = datetime.now(timezone.utc).date()
    today_str = today.isoformat()
    today_wd = today.weekday()  # Mon=0

    created_ids: list[str] = []

    # POST daily
    r = requests.post(_u("household/tasks"), headers=_hdr(token), json={
        "space_id": space_id, "title": "Dust living room", "recurrence": "daily",
    }, timeout=30)
    if r.status_code == 200:
        body = r.json()
        ok = (body.get("recurrence") == "daily"
              and body.get("active") is True
              and body.get("requires_photo") is False)
        record(ok, "POST daily task returns recurrence=daily, active=true, requires_photo=false",
               f"got {body}")
        daily_id = body.get("task_id")
        if daily_id: created_ids.append(daily_id)
    else:
        record(False, "POST daily task", f"{r.status_code} {r.text}")
        daily_id = None

    # POST weekly with weekdays Mon/Wed/Fri
    weekly_wds = [0, 2, 4]
    r = requests.post(_u("household/tasks"), headers=_hdr(token), json={
        "space_id": space_id, "title": "Mop floors", "recurrence": "weekly",
        "weekdays": weekly_wds,
    }, timeout=30)
    if r.status_code == 200:
        body = r.json()
        ok = (body.get("recurrence") == "weekly"
              and sorted(body.get("weekdays") or []) == sorted(weekly_wds))
        record(ok, "POST weekly task returns weekdays list", f"got weekdays={body.get('weekdays')}")
        weekly_id = body.get("task_id")
        if weekly_id: created_ids.append(weekly_id)
    else:
        record(False, "POST weekly task", f"{r.status_code} {r.text}")
        weekly_id = None

    # POST monthly with monthly_day
    monthly_day = 15
    r = requests.post(_u("household/tasks"), headers=_hdr(token), json={
        "space_id": space_id, "title": "Pay water bill", "recurrence": "monthly",
        "monthly_day": monthly_day,
    }, timeout=30)
    if r.status_code == 200:
        body = r.json()
        ok = (body.get("recurrence") == "monthly" and body.get("monthly_day") == monthly_day)
        record(ok, "POST monthly task returns monthly_day=15", f"got {body}")
        monthly_id = body.get("task_id")
        if monthly_id: created_ids.append(monthly_id)
    else:
        record(False, "POST monthly task", f"{r.status_code} {r.text}")
        monthly_id = None

    # POST once with once_date
    once_date_str = "2026-06-15"
    r = requests.post(_u("household/tasks"), headers=_hdr(token), json={
        "space_id": space_id, "title": "AC service annual", "recurrence": "once",
        "once_date": once_date_str,
    }, timeout=30)
    if r.status_code == 200:
        body = r.json()
        ok = (body.get("recurrence") == "once" and body.get("once_date") == once_date_str)
        record(ok, "POST once task returns once_date", f"got {body}")
        once_id = body.get("task_id")
        if once_id: created_ids.append(once_id)
    else:
        record(False, "POST once task", f"{r.status_code} {r.text}")
        once_id = None

    # GET tasks for TODAY
    r = requests.get(_u("household/tasks"), headers=_hdr(token),
                     params={"space_id": space_id, "date": today_str}, timeout=30)
    if r.status_code == 200:
        payload = r.json()
        ok_shape = (payload.get("date") == today_str and isinstance(payload.get("tasks"), list))
        record(ok_shape, "GET tasks?date=TODAY shape {date, tasks[]}", f"got date={payload.get('date')}")
        tasks_by_id = {t["task_id"]: t for t in payload.get("tasks", [])}

        # daily: due_today=true
        if daily_id and daily_id in tasks_by_id:
            record(tasks_by_id[daily_id].get("due_today") is True,
                   "Daily task has due_today=true",
                   f"got {tasks_by_id[daily_id].get('due_today')}")

        # weekly: due_today only if today's weekday in [0,2,4]
        if weekly_id and weekly_id in tasks_by_id:
            expected = today_wd in weekly_wds
            record(tasks_by_id[weekly_id].get("due_today") is expected,
                   f"Weekly task due_today reflects today.weekday()={today_wd} in {weekly_wds} -> {expected}",
                   f"got {tasks_by_id[weekly_id].get('due_today')}")

        # monthly: due_today only if today.day == 15
        if monthly_id and monthly_id in tasks_by_id:
            expected = today.day == monthly_day
            record(tasks_by_id[monthly_id].get("due_today") is expected,
                   f"Monthly task due_today reflects today.day=={monthly_day} -> {expected}",
                   f"got {tasks_by_id[monthly_id].get('due_today')}")

        # once: due_today only if date matches
        if once_id and once_id in tasks_by_id:
            expected = (once_date_str == today_str)
            record(tasks_by_id[once_id].get("due_today") is expected,
                   f"Once task due_today reflects exact date match -> {expected}",
                   f"got {tasks_by_id[once_id].get('due_today')}")
    else:
        record(False, "GET tasks?date=TODAY", f"{r.status_code} {r.text}")
        tasks_by_id = {}

    # PATCH task (title + description)
    if daily_id:
        new_title = "Dust + vacuum living room"
        new_desc = "Mind the rugs"
        r = requests.patch(_u(f"household/tasks/{daily_id}"), headers=_hdr(token),
                           json={"title": new_title, "description": new_desc}, timeout=30)
        if r.status_code == 200:
            body = r.json()
            ok = (body.get("title") == new_title and body.get("description") == new_desc)
            record(ok, "PATCH task updates title + description", f"got title={body.get('title')}")
        else:
            record(False, "PATCH task", f"{r.status_code} {r.text}")

    # POST /complete first call -> {completed: true}
    if daily_id:
        r = requests.post(_u(f"household/tasks/{daily_id}/complete"), headers=_hdr(token),
                          json={"date": today_str}, timeout=30)
        if r.status_code == 200:
            record(r.json().get("completed") is True,
                   "POST /complete first call returns {completed: true}",
                   f"got {r.json()}")
        else:
            record(False, "POST /complete first call", f"{r.status_code} {r.text}")

        # Verify GET shows completed_today=true
        r = requests.get(_u("household/tasks"), headers=_hdr(token),
                         params={"space_id": space_id, "date": today_str}, timeout=30)
        if r.status_code == 200:
            t = next((x for x in r.json().get("tasks", []) if x["task_id"] == daily_id), None)
            record(bool(t) and t.get("completed_today") is True,
                   "GET tasks shows completed_today=true after first complete",
                   f"got completed_today={t and t.get('completed_today')}")
        else:
            record(False, "GET tasks after first complete", f"{r.status_code} {r.text}")

        # Second call -> {completed: false} (toggle)
        r = requests.post(_u(f"household/tasks/{daily_id}/complete"), headers=_hdr(token),
                          json={"date": today_str}, timeout=30)
        if r.status_code == 200:
            record(r.json().get("completed") is False,
                   "POST /complete second call toggles to {completed: false}",
                   f"got {r.json()}")
        else:
            record(False, "POST /complete second call", f"{r.status_code} {r.text}")

        # Verify GET shows completed_today=false
        r = requests.get(_u("household/tasks"), headers=_hdr(token),
                         params={"space_id": space_id, "date": today_str}, timeout=30)
        if r.status_code == 200:
            t = next((x for x in r.json().get("tasks", []) if x["task_id"] == daily_id), None)
            record(bool(t) and t.get("completed_today") is False,
                   "GET tasks shows completed_today=false after toggle off",
                   f"got completed_today={t and t.get('completed_today')}")

    # DELETE task
    if monthly_id:
        r = requests.delete(_u(f"household/tasks/{monthly_id}"), headers=_hdr(token), timeout=30)
        record(r.status_code == 200, "DELETE task -> 200", f"{r.status_code} {r.text[:120]}")
        # GET should not include it
        r = requests.get(_u("household/tasks"), headers=_hdr(token),
                         params={"space_id": space_id, "date": today_str}, timeout=30)
        if r.status_code == 200:
            ids = [t["task_id"] for t in r.json().get("tasks", [])]
            record(monthly_id not in ids, "Deleted task disappears from GET",
                   f"still in list: {monthly_id in ids}")

    # Non-member 403
    r = requests.get(_u("household/tasks"), headers=_hdr(outsider_token),
                     params={"space_id": space_id, "date": today_str}, timeout=30)
    record(r.status_code == 403, "Non-member GET tasks -> 403", f"got {r.status_code}")

    r = requests.post(_u("household/tasks"), headers=_hdr(outsider_token),
                      json={"space_id": space_id, "title": "x", "recurrence": "daily"}, timeout=30)
    record(r.status_code == 403, "Non-member POST tasks -> 403", f"got {r.status_code}")

    # Cleanup remaining tasks
    for tid in created_ids:
        if tid == monthly_id:
            continue
        try: requests.delete(_u(f"household/tasks/{tid}"), headers=_hdr(token), timeout=15)
        except Exception: pass


# ============================================================
# 2. Attendance
# ============================================================
def test_attendance(token: str, space_id: str, staff_id: str, outsider_token: str):
    section("Attendance (/api/household/attendance)")
    target_date = "2026-06-01"

    # POST present
    r = requests.post(_u("household/attendance"), headers=_hdr(token), json={
        "space_id": space_id, "staff_id": staff_id, "date": target_date, "status": "present",
    }, timeout=30)
    if r.status_code == 200:
        body = r.json()
        ok = (body.get("status") == "present" and body.get("staff_id") == staff_id
              and body.get("date") == target_date and body.get("attendance_id"))
        record(ok, "POST attendance present returns AttendanceLog", f"got {body}")
        first_aid = body.get("attendance_id")
    else:
        record(False, "POST attendance present", f"{r.status_code} {r.text}")
        first_aid = None

    # Upsert: same staff+date with status=sick should keep id, change status
    r = requests.post(_u("household/attendance"), headers=_hdr(token), json={
        "space_id": space_id, "staff_id": staff_id, "date": target_date, "status": "sick",
    }, timeout=30)
    if r.status_code == 200:
        body = r.json()
        same_id = body.get("attendance_id") == first_aid if first_aid else True
        record(same_id and body.get("status") == "sick",
               "Upsert: same staff+date+sick keeps attendance_id, status='sick'",
               f"got id={body.get('attendance_id')} (was {first_aid}) status={body.get('status')}")
    else:
        record(False, "POST attendance upsert sick", f"{r.status_code} {r.text}")

    # Invalid status -> 400
    r = requests.post(_u("household/attendance"), headers=_hdr(token), json={
        "space_id": space_id, "staff_id": staff_id, "date": target_date, "status": "partying",
    }, timeout=30)
    record(r.status_code == 400, "POST invalid status 'partying' -> 400", f"got {r.status_code}")

    # GET range filter
    r = requests.get(_u("household/attendance"), headers=_hdr(token), params={
        "space_id": space_id, "date_from": target_date, "date_to": target_date,
    }, timeout=30)
    if r.status_code == 200:
        docs = r.json()
        found = any(d.get("staff_id") == staff_id and d.get("date") == target_date for d in docs)
        record(found, "GET attendance with date range returns the record", f"len={len(docs)}")
    else:
        record(False, "GET attendance range", f"{r.status_code} {r.text}")

    # GET with staff_id filter -> only that staff's records
    # Seed a 2nd staff record with different staff_id (if possible) to confirm filter narrows
    r = requests.get(_u("household/staff"), headers=_hdr(token), params={"space_id": space_id}, timeout=30)
    other_staff_id = None
    if r.status_code == 200:
        for s in r.json():
            if s["staff_id"] != staff_id:
                other_staff_id = s["staff_id"]
                break
    if other_staff_id is None:
        # Create second staff
        r = requests.get(_u("household/roles"), headers=_hdr(token), params={"space_id": space_id}, timeout=15)
        roles = r.json() if r.status_code == 200 else []
        rid = (next((x for x in roles if x.get("name") == "Driver"), None) or roles[0])["role_id"]
        r = requests.post(_u("household/staff"), headers=_hdr(token), json={
            "space_id": space_id, "name": "Budi Santoso", "role_id": rid,
            "salary": 3000000, "pay_cycle": "monthly", "off_day": "Saturday",
        }, timeout=15)
        if r.status_code == 200:
            other_staff_id = r.json()["staff_id"]

    if other_staff_id:
        requests.post(_u("household/attendance"), headers=_hdr(token), json={
            "space_id": space_id, "staff_id": other_staff_id, "date": target_date, "status": "present",
        }, timeout=15)
        r = requests.get(_u("household/attendance"), headers=_hdr(token), params={
            "space_id": space_id, "staff_id": staff_id,
        }, timeout=30)
        if r.status_code == 200:
            docs = r.json()
            only_one_staff = all(d.get("staff_id") == staff_id for d in docs) and len(docs) >= 1
            record(only_one_staff, "GET attendance with staff_id filter returns only that staff",
                   f"len={len(docs)} unique_staff={ {d.get('staff_id') for d in docs} }")
        else:
            record(False, "GET attendance staff_id filter", f"{r.status_code} {r.text}")

    # Non-member 403
    r = requests.get(_u("household/attendance"), headers=_hdr(outsider_token),
                     params={"space_id": space_id}, timeout=30)
    record(r.status_code == 403, "Non-member GET attendance -> 403", f"got {r.status_code}")
    r = requests.post(_u("household/attendance"), headers=_hdr(outsider_token), json={
        "space_id": space_id, "staff_id": staff_id, "date": target_date, "status": "present",
    }, timeout=30)
    record(r.status_code == 403, "Non-member POST attendance -> 403", f"got {r.status_code}")


# ============================================================
# 3. Shopping requests
# ============================================================
def test_shopping(token: str, space_id: str, category_id: str, outsider_token: str):
    section("Shopping requests (/api/household/shopping)")
    created_ids: list[str] = []

    # Get cat name
    r = requests.get(_u("categories"), headers=_hdr(token), params={"space_id": space_id}, timeout=15)
    cat_map = {c["category_id"]: c["name"] for c in (r.json() if r.status_code == 200 else [])}
    cat_name = cat_map.get(category_id)

    # POST high urgency Rice
    r = requests.post(_u("household/shopping"), headers=_hdr(token), json={
        "space_id": space_id, "item_name": "Rice", "quantity": "5kg",
        "urgency": "high", "category_id": category_id,
    }, timeout=30)
    if r.status_code == 200:
        body = r.json()
        ok = (body.get("status") == "pending" and body.get("urgency") == "high"
              and body.get("item_name") == "Rice")
        record(ok, "POST shopping {Rice, high} -> status=pending urgency=high", f"got {body}")
        rice_id = body.get("request_id")
        if rice_id: created_ids.append(rice_id)
    else:
        record(False, "POST shopping Rice", f"{r.status_code} {r.text}")
        rice_id = None

    # POST urgency 'xyz' normalised to 'normal'
    r = requests.post(_u("household/shopping"), headers=_hdr(token), json={
        "space_id": space_id, "item_name": "Cooking oil", "quantity": "2L",
        "urgency": "xyz",
    }, timeout=30)
    if r.status_code == 200:
        body = r.json()
        record(body.get("urgency") == "normal", "POST urgency='xyz' normalised to 'normal'",
               f"got urgency={body.get('urgency')}")
        oil_id = body.get("request_id")
        if oil_id: created_ids.append(oil_id)
    else:
        record(False, "POST shopping xyz urgency", f"{r.status_code} {r.text}")
        oil_id = None

    # GET sorted desc + enrichment
    r = requests.get(_u("household/shopping"), headers=_hdr(token), params={"space_id": space_id}, timeout=30)
    if r.status_code == 200:
        docs = r.json()
        # sort desc by created_at: newest first
        ts = []
        for d in docs:
            ca = d.get("created_at")
            if isinstance(ca, str):
                try:
                    ts.append(datetime.fromisoformat(ca.replace("Z", "+00:00")))
                except Exception:
                    ts.append(None)
            else:
                ts.append(None)
        sorted_desc = all(
            (ts[i] is None or ts[i+1] is None or ts[i] >= ts[i+1])
            for i in range(len(ts) - 1)
        )
        record(sorted_desc, "GET shopping sorted by created_at desc",
               f"timestamps={[t.isoformat() if t else None for t in ts[:5]]}")

        # Enrichment: each entry has requested_by_name and category_name (where applicable)
        if rice_id:
            rice = next((d for d in docs if d.get("request_id") == rice_id), None)
            if rice:
                has_name = bool(rice.get("requested_by_name"))
                cat_ok = (rice.get("category_name") == cat_name) if cat_name else True
                record(has_name and cat_ok,
                       "GET shopping entry enriched with requested_by_name + category_name",
                       f"requested_by_name={rice.get('requested_by_name')} category_name={rice.get('category_name')} (expected {cat_name})")
    else:
        record(False, "GET shopping list", f"{r.status_code} {r.text}")

    # GET with status=pending filter
    r = requests.get(_u("household/shopping"), headers=_hdr(token),
                     params={"space_id": space_id, "status": "pending"}, timeout=30)
    if r.status_code == 200:
        docs = r.json()
        all_pending = all(d.get("status") == "pending" for d in docs)
        record(all_pending and len(docs) >= 1, "GET ?status=pending filters",
               f"len={len(docs)} statuses={[d.get('status') for d in docs[:5]]}")
    else:
        record(False, "GET shopping ?status=pending", f"{r.status_code} {r.text}")

    me = requests.get(_u("auth/me"), headers=_hdr(token), timeout=15).json()
    my_uid = me["user_id"]

    # PATCH approve
    if rice_id:
        r = requests.patch(_u(f"household/shopping/{rice_id}"), headers=_hdr(token),
                           json={"status": "approved"}, timeout=30)
        if r.status_code == 200:
            body = r.json()
            ok = (body.get("status") == "approved" and body.get("approved_by") == my_uid)
            record(ok, "PATCH shopping status=approved -> approved_by=current user",
                   f"got status={body.get('status')} approved_by={body.get('approved_by')}")
        else:
            record(False, "PATCH approved", f"{r.status_code} {r.text}")

    # PATCH purchased -> fulfilled_at set
    if rice_id:
        r = requests.patch(_u(f"household/shopping/{rice_id}"), headers=_hdr(token),
                           json={"status": "purchased"}, timeout=30)
        if r.status_code == 200:
            body = r.json()
            ok = (body.get("status") == "purchased" and body.get("fulfilled_at"))
            record(ok, "PATCH shopping status=purchased -> fulfilled_at set",
                   f"got status={body.get('status')} fulfilled_at={body.get('fulfilled_at')}")
        else:
            record(False, "PATCH purchased", f"{r.status_code} {r.text}")

    # DELETE
    if oil_id:
        r = requests.delete(_u(f"household/shopping/{oil_id}"), headers=_hdr(token), timeout=30)
        record(r.status_code == 200, "DELETE shopping -> 200", f"{r.status_code} {r.text[:120]}")
        if r.status_code == 200:
            r2 = requests.get(_u("household/shopping"), headers=_hdr(token),
                              params={"space_id": space_id}, timeout=15)
            if r2.status_code == 200:
                ids = {d.get("request_id") for d in r2.json()}
                record(oil_id not in ids, "Deleted shopping disappears from GET",
                       f"still present: {oil_id in ids}")

    # Non-member 403
    r = requests.get(_u("household/shopping"), headers=_hdr(outsider_token),
                     params={"space_id": space_id}, timeout=30)
    record(r.status_code == 403, "Non-member GET shopping -> 403", f"got {r.status_code}")
    r = requests.post(_u("household/shopping"), headers=_hdr(outsider_token), json={
        "space_id": space_id, "item_name": "x",
    }, timeout=30)
    record(r.status_code == 403, "Non-member POST shopping -> 403", f"got {r.status_code}")

    # Cleanup
    for rid in created_ids:
        try: requests.delete(_u(f"household/shopping/{rid}"), headers=_hdr(token), timeout=10)
        except Exception: pass


# ============================================================
# Main
# ============================================================
def main():
    section("Auth")
    token = login_or_register(PRIMARY_EMAIL, PRIMARY_PASSWORD, "Test User")
    print(f"  primary token len={len(token)}")

    # Outsider account that is NOT a member of the household space
    outsider_email = f"outsider+{int(time.time())}@cozii.app"
    outsider_token = login_or_register(outsider_email, "outsider1234!", "Outsider Tester")
    print(f"  outsider={outsider_email}")

    section("Space + staff + category prep")
    space = get_or_create_household_space(token)
    space_id = space["space_id"]
    print(f"  space_id={space_id} type={space.get('space_type')} currency={space.get('currency')}")
    staff_id, category_id = ensure_staff_and_category(token, space_id)
    print(f"  staff_id={staff_id} category_id={category_id}")

    test_tasks(token, space_id, outsider_token)
    test_attendance(token, space_id, staff_id, outsider_token)
    test_shopping(token, space_id, category_id, outsider_token)

    # Summary
    section("SUMMARY")
    passed = sum(1 for ok, *_ in RESULTS if ok)
    failed = len(RESULTS) - passed
    print(f"  {passed}/{len(RESULTS)} passed, {failed} failed")
    if failed:
        print("\n  Failures:")
        for ok, name, detail in RESULTS:
            if not ok:
                print(f"   - {name}: {detail}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
