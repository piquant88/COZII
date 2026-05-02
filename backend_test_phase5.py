"""
Phase 5 backend tests:
  1) Task shortcuts CRUD (GET/POST/DELETE /api/household/shortcuts)
  2) Quick-fire task POST /api/household/tasks/quick
  3) task_assigned notification on POST /api/household/tasks
  4) Preview staff home GET /api/household/staff/{staff_id}/view
"""
import os
import sys
import time
import uuid
import json
from datetime import datetime, timezone

import requests

BASE = "https://family-wallet-21.preview.emergentagent.com/api"

OWNER_EMAIL = "test@cozii.app"
OWNER_PASS = "test1234"

results = []
def rec(label, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    line = f"[{tag}] {label}" + (f" :: {detail}" if detail else "")
    results.append((ok, line))
    print(line, flush=True)


def req(method, path, token=None, json_body=None, params=None, allow_codes=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.request(method, BASE + path, headers=headers, json=json_body, params=params, timeout=30)
    return r


def login_or_register(email, password, name):
    r = requests.post(BASE + "/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code == 200:
        return r.json()["token"], r.json()["user"]
    r2 = requests.post(BASE + "/auth/register", json={"email": email, "password": password, "name": name}, timeout=30)
    if r2.status_code != 200:
        raise RuntimeError(f"Cannot register {email}: {r2.status_code} {r2.text}")
    return r2.json()["token"], r2.json()["user"]


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # --- Auth: owner + helpers ---
    owner_token, owner_user = login_or_register(OWNER_EMAIL, OWNER_PASS, "Test Owner")

    # Outsider (non-member) for 403 checks
    outsider_email = f"outsider+{uuid.uuid4().hex[:6]}@cozii.app"
    out_token, out_user = login_or_register(outsider_email, "passw0rd!", "Outsider Olivia")

    # Staff user account (will join via invite code)
    staff_email = f"staff+{uuid.uuid4().hex[:6]}@cozii.app"
    staff_token, staff_user = login_or_register(staff_email, "passw0rd!", "Sari Putri")

    # --- Pick or create a household space owned by owner ---
    sp = req("GET", "/spaces", token=owner_token).json()
    household = next((s for s in sp if s.get("space_type") == "household" and s.get("owner_id") == owner_user["user_id"]), None)
    if not household:
        # create one
        r = req("POST", "/spaces", token=owner_token, json_body={"name": f"Household {uuid.uuid4().hex[:4]}", "currency": "IDR", "space_type": "household"})
        if r.status_code != 200:
            rec("create household space", False, f"{r.status_code} {r.text[:200]}")
            return
        household = r.json()
    space_id = household["space_id"]
    print(f"[setup] using space {space_id}")

    # --- Get a 'Maid' role_id ---
    roles = req("GET", "/household/roles", token=owner_token, params={"space_id": space_id}).json()
    maid_role = next((r for r in roles if r["key"] == "maid"), roles[0])
    role_id = maid_role["role_id"]

    # --- Create a staff member (linked) ---
    r = req("POST", "/household/staff", token=owner_token, json_body={
        "space_id": space_id,
        "name": "Sari Putri",
        "role_id": role_id,
        "salary": 2500000,
        "pay_cycle": "monthly",
    })
    if r.status_code != 200:
        rec("create staff", False, f"{r.status_code} {r.text[:200]}")
        return
    staff_doc = r.json()
    staff_id = staff_doc["staff_id"]
    invite = staff_doc.get("invite_code")
    rec("create staff returns invite_code + permissions", bool(invite) and isinstance(staff_doc.get("permissions"), dict))

    # Staff user joins via invite code → links user_id and adds them to space members
    r = req("POST", "/household/staff/join", token=staff_token, json_body={"invite_code": invite})
    rec("staff joins via invite code", r.status_code == 200, f"{r.status_code} {r.text[:120]}")

    # --- Create another staff with NO invite redemption (to test view_wage_amount=false) ---
    r = req("POST", "/household/staff", token=owner_token, json_body={
        "space_id": space_id,
        "name": "Andi Wibowo",
        "role_id": role_id,
        "salary": 3000000,
        "pay_cycle": "monthly",
    })
    staff2 = r.json()
    staff2_id = staff2["staff_id"]

    # Force view_wage_amount=false on staff2 via PATCH /permissions
    perms2 = {**(staff2.get("permissions") or {}), "view_wage_amount": False}
    r = req("PATCH", f"/household/staff/{staff2_id}/permissions", token=owner_token, json_body={"permissions": perms2})
    rec("patch staff2 view_wage_amount=false", r.status_code == 200 and r.json().get("permissions", {}).get("view_wage_amount") is False)

    # =============================================================
    # 1) TASK SHORTCUTS CRUD
    # =============================================================
    print("\n=== 1) Task shortcuts CRUD ===")

    # POST staff-specific
    r = req("POST", "/household/shortcuts", token=owner_token, json_body={
        "space_id": space_id, "staff_id": staff_id, "title": "Mop the kitchen", "icon": "Sparkles",
    })
    rec("POST shortcut (staff-specific)", r.status_code == 200 and r.json().get("staff_id") == staff_id, f"{r.status_code} {r.text[:160]}")
    sc_specific_id = r.json().get("shortcut_id")

    # POST shared (omit staff_id)
    r = req("POST", "/household/shortcuts", token=owner_token, json_body={
        "space_id": space_id, "title": "Take out the trash",
    })
    rec("POST shortcut (shared, staff_id omitted)", r.status_code == 200 and r.json().get("staff_id") is None, f"{r.status_code} {r.text[:160]}")
    sc_shared_id = r.json().get("shortcut_id")

    # POST a shortcut for staff2 (should NOT appear when filter=staff_id)
    r = req("POST", "/household/shortcuts", token=owner_token, json_body={
        "space_id": space_id, "staff_id": staff2_id, "title": "Wash car",
    })
    sc_staff2_id = r.json().get("shortcut_id")

    # GET all (no staff filter)
    r = req("GET", "/household/shortcuts", token=owner_token, params={"space_id": space_id})
    all_ids = {x["shortcut_id"] for x in r.json()}
    rec("GET shortcuts (no filter) returns all 3", r.status_code == 200 and {sc_specific_id, sc_shared_id, sc_staff2_id}.issubset(all_ids), f"got {len(r.json())}")

    # GET filtered by staff_id → must include the staff-specific + shared, exclude staff2's
    r = req("GET", "/household/shortcuts", token=owner_token, params={"space_id": space_id, "staff_id": staff_id})
    ids = {x["shortcut_id"] for x in r.json()}
    cond = sc_specific_id in ids and sc_shared_id in ids and sc_staff2_id not in ids
    rec("GET shortcuts ?staff_id=X includes staff+shared, excludes other staff", cond, f"ids={ids}")

    # DELETE
    r = req("DELETE", f"/household/shortcuts/{sc_staff2_id}", token=owner_token)
    rec("DELETE shortcut", r.status_code == 200)
    r = req("GET", "/household/shortcuts", token=owner_token, params={"space_id": space_id})
    after_ids = {x["shortcut_id"] for x in r.json()}
    rec("after DELETE, shortcut absent", sc_staff2_id not in after_ids)

    # Non-member 403
    r = req("GET", "/household/shortcuts", token=out_token, params={"space_id": space_id})
    rec("non-member GET shortcuts → 403", r.status_code == 403)
    r = req("POST", "/household/shortcuts", token=out_token, json_body={"space_id": space_id, "title": "x"})
    rec("non-member POST shortcuts → 403", r.status_code == 403)
    # need a valid id to test DELETE 403; sc_specific_id is in space → outsider should get 403
    r = req("DELETE", f"/household/shortcuts/{sc_specific_id}", token=out_token)
    rec("non-member DELETE shortcut → 403", r.status_code == 403)

    # =============================================================
    # 2) QUICK-FIRE TASK
    # =============================================================
    print("\n=== 2) Quick-fire task ===")

    quick_title = f"Buy milk {uuid.uuid4().hex[:4]}"
    r = req("POST", "/household/tasks/quick", token=owner_token, json_body={
        "space_id": space_id, "staff_id": staff_id, "title": quick_title,
    })
    if r.status_code != 200:
        rec("POST /tasks/quick basic", False, f"{r.status_code} {r.text[:200]}")
    else:
        body = r.json()
        ok = (
            body.get("recurrence") == "once"
            and body.get("once_date") == today
            and body.get("staff_id") == staff_id
            and body.get("active") is True
        )
        rec("POST /tasks/quick → recurrence=once, once_date=today, staff_id, active", ok,
            f"recurrence={body.get('recurrence')}, once_date={body.get('once_date')}, staff_id={body.get('staff_id')}, active={body.get('active')}")
        first_quick_task_id = body.get("task_id")

    # Empty title → 400
    r = req("POST", "/household/tasks/quick", token=owner_token, json_body={
        "space_id": space_id, "staff_id": staff_id, "title": "  ",
    })
    rec("quick: empty title → 400", r.status_code == 400, f"got {r.status_code}")

    # Non-existent staff → 404
    r = req("POST", "/household/tasks/quick", token=owner_token, json_body={
        "space_id": space_id, "staff_id": "staff_doesnotexist", "title": "x",
    })
    rec("quick: missing staff → 404", r.status_code == 404, f"got {r.status_code}")

    # save_as_shortcut=true → also creates shortcut, visible via GET
    sas_title = f"Sweep porch {uuid.uuid4().hex[:4]}"
    r = req("POST", "/household/tasks/quick", token=owner_token, json_body={
        "space_id": space_id, "staff_id": staff_id, "title": sas_title, "save_as_shortcut": True,
    })
    rec("quick: save_as_shortcut=true creates task", r.status_code == 200)

    # GET shortcuts ?staff_id=staff → should now include the new one
    r = req("GET", "/household/shortcuts", token=owner_token, params={"space_id": space_id, "staff_id": staff_id})
    titles = [x["title"] for x in r.json()]
    matches = [t for t in titles if t == sas_title]
    rec("quick: shortcut visible via GET shortcuts (count=1)", len(matches) == 1, f"matches={len(matches)}, titles={titles}")

    # Idempotency: call again with same title + save_as_shortcut=true → still 1 shortcut
    r = req("POST", "/household/tasks/quick", token=owner_token, json_body={
        "space_id": space_id, "staff_id": staff_id, "title": sas_title, "save_as_shortcut": True,
    })
    rec("quick: second call same title 200", r.status_code == 200)
    r = req("GET", "/household/shortcuts", token=owner_token, params={"space_id": space_id, "staff_id": staff_id})
    matches2 = [t for t in (x["title"] for x in r.json()) if t == sas_title]
    rec("quick: no duplicate shortcut after second call", len(matches2) == 1, f"matches={len(matches2)}")

    # Notification to staff user (since staff has user_id linked via /staff/join)
    # Read first quick task notification as the staff user
    r = req("GET", "/notifications", token=staff_token, params={"space_id": space_id})
    notifs = r.json() if r.status_code == 200 else []
    quick_notifs = [n for n in notifs if n.get("kind") == "task_assigned" and n.get("title", "").startswith("Quick task: ")]
    rec("staff received task_assigned notif for quick task", len(quick_notifs) >= 1, f"got {len(quick_notifs)} quick notifs (total {len(notifs)})")
    # Verify data.task_id and data.quick=true on the latest
    if quick_notifs:
        latest = quick_notifs[0]
        d = latest.get("data") or {}
        rec("quick notif title matches 'Quick task: <title>'", latest.get("title") in (f"Quick task: {quick_title}", f"Quick task: {sas_title}"),
            f"title={latest.get('title')}")
        rec("quick notif data.task_id present", bool(d.get("task_id")), f"data={d}")
        rec("quick notif data.quick=True", d.get("quick") is True, f"data.quick={d.get('quick')}")

    # =============================================================
    # 3) task_assigned notification on POST /api/household/tasks
    # =============================================================
    print("\n=== 3) task_assigned on POST /household/tasks ===")

    daily_title = f"Daily check {uuid.uuid4().hex[:4]}"
    r = req("POST", "/household/tasks", token=owner_token, json_body={
        "space_id": space_id, "title": daily_title, "staff_id": staff_id, "recurrence": "daily",
    })
    rec("create normal daily task", r.status_code == 200, f"{r.status_code} {r.text[:160]}")

    r = req("GET", "/notifications", token=staff_token, params={"space_id": space_id, "unread_only": "true"})
    notifs = r.json() if r.status_code == 200 else []
    matches = [n for n in notifs if n.get("kind") == "task_assigned" and n.get("title") == f"New task: {daily_title}"]
    rec("staff sees task_assigned 'New task: <title>' (unread_only=true)", len(matches) == 1, f"got {len(matches)} matching, total unread={len(notifs)}")

    # =============================================================
    # 4) Preview staff home view
    # =============================================================
    print("\n=== 4) GET /household/staff/{staff_id}/view ===")

    r = req("GET", f"/household/staff/{staff_id}/view", token=owner_token)
    if r.status_code != 200:
        rec("owner GET staff view → 200", False, f"{r.status_code} {r.text[:200]}")
    else:
        body = r.json()
        keys_ok = all(k in body for k in ("staff", "permissions", "today_tasks", "attendance", "payments", "preview"))
        rec("owner GET staff view: 200 + all required keys", keys_ok, f"keys={list(body.keys())}")
        rec("preview=True", body.get("preview") is True)
        rec("today_tasks is array", isinstance(body.get("today_tasks"), list))
        rec("attendance is array", isinstance(body.get("attendance"), list))
        rec("payments is array", isinstance(body.get("payments"), list))
        sd = body.get("staff") or {}
        rec("staff.name present", bool(sd.get("name")))
        rec("staff.role_id present", "role_id" in sd)
        rec("staff.invite_code present", bool(sd.get("invite_code")))
        # since permissions for staff1 are defaults → view_wage_amount=true → payments must NOT be forced empty here

    # Staff2 has view_wage_amount=false → payments must be []
    r = req("GET", f"/household/staff/{staff2_id}/view", token=owner_token)
    rec("staff2 view: 200 with view_wage_amount=false", r.status_code == 200)
    if r.status_code == 200:
        b = r.json()
        rec("staff2 view: payments=[] when view_wage_amount=false", b.get("payments") == [],
            f"perms.view_wage_amount={b.get('permissions', {}).get('view_wage_amount')}, payments_len={len(b.get('payments') or [])}")

    # Non-member of space → 403
    r = req("GET", f"/household/staff/{staff_id}/view", token=out_token)
    rec("non-member GET staff view → 403", r.status_code == 403, f"got {r.status_code}")

    # Random fake staff_id → 404
    r = req("GET", "/household/staff/staff_doesnotexist_xxx/view", token=owner_token)
    rec("fake staff_id → 404", r.status_code == 404, f"got {r.status_code}")

    # =============================================================
    # Summary
    # =============================================================
    total = len(results)
    failed = [l for ok, l in results if not ok]
    print(f"\n==== {total - len(failed)}/{total} PASS ====")
    if failed:
        print("FAILURES:")
        for line in failed:
            print(" ", line)
        sys.exit(1)


if __name__ == "__main__":
    main()
