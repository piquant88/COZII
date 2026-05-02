"""
Phase 4 backend tests for Cozii:
  1) Staff permissions (view_inventory default + PATCH merge + non-owner 403)
  2) Notifications CRUD + auto-creation on payroll
  3) Household monthly report

Run:
    python /app/backend_test_phase4.py
"""
from __future__ import annotations
import sys
import time
import uuid
import requests
from datetime import datetime, timezone, timedelta

from pymongo import MongoClient

# Direct mongo handle (used only to read fields that the response model strips,
# e.g. StaffMember does not expose invite_code/permissions). Tests still drive
# functionality through HTTP API.
_mc = MongoClient("mongodb://localhost:27017")
_mdb = _mc["test_database"]


def mongo_staff(staff_id: str) -> dict:
    return _mdb.staff_members.find_one({"staff_id": staff_id}, {"_id": 0})

BASE = "https://family-wallet-21.preview.emergentagent.com/api"

PRIMARY_EMAIL = "test@cozii.app"
PRIMARY_PASSWORD = "test1234"


def _u(p: str) -> str:
    return f"{BASE}/{p.lstrip('/')}"


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


RESULTS: list[tuple[bool, str, str]] = []


def record(ok: bool, name: str, detail: str = ""):
    RESULTS.append((ok, name, detail))
    flag = "PASS" if ok else "FAIL"
    print(f"  [{flag}] {name}" + (f" -- {detail}" if detail else ""))


def section(title: str):
    print(f"\n=== {title} ===")


def login_or_register(email: str, password: str, name: str) -> str:
    r = requests.post(_u("auth/login"), json={"email": email, "password": password}, timeout=30)
    if r.status_code == 200:
        return r.json()["token"]
    r = requests.post(_u("auth/register"), json={"email": email, "password": password, "name": name}, timeout=30)
    if r.status_code in (200, 201):
        return r.json()["token"]
    raise SystemExit(f"login/register failed for {email}: {r.status_code} {r.text}")


def me(token: str) -> dict:
    r = requests.get(_u("auth/me"), headers=_hdr(token), timeout=30)
    r.raise_for_status()
    return r.json()


def create_household_space(token: str, name: str, currency: str = "IDR") -> dict:
    r = requests.post(
        _u("spaces"),
        headers=_hdr(token),
        json={"name": name, "space_type": "household", "currency": currency},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ============================================================
# 1) STAFF PERMISSIONS
# ============================================================
def test_staff_permissions(owner_token: str, staff_user_token: str, outsider_token: str):
    section("1) Staff permissions (view_inventory default + PATCH + non-owner 403)")

    # Fresh household space owned by the primary user
    sp = create_household_space(owner_token, f"PermsHH {uuid.uuid4().hex[:6]}", "IDR")
    space_id = sp["space_id"]
    record(sp.get("space_type") == "household" and sp.get("currency") == "IDR",
           "POST /spaces household IDR", f"got space_type={sp.get('space_type')} currency={sp.get('currency')}")

    # Fetch a role
    rr = requests.get(_u("household/roles"), headers=_hdr(owner_token),
                      params={"space_id": space_id}, timeout=30)
    rr.raise_for_status()
    roles = rr.json()
    role = next((x for x in roles if x.get("name") == "Maid"), None) or roles[0]

    # Create staff
    cs = requests.post(_u("household/staff"), headers=_hdr(owner_token), json={
        "space_id": space_id,
        "name": "Sari Putri",
        "role_id": role["role_id"],
        "salary": 2500000,
        "pay_cycle": "monthly",
        "off_day": "Sunday",
    }, timeout=30)
    if cs.status_code != 200:
        record(False, "POST /household/staff", f"status={cs.status_code} body={cs.text}")
        return None, None
    staff = cs.json()
    staff_id = staff["staff_id"]
    record(bool(staff_id), "POST /household/staff returns staff_id")

    # NOTE: StaffMember response model omits invite_code & permissions fields.
    # Capture them from the raw API response and report whether they're exposed.
    invite_code_api = staff.get("invite_code")
    perms_api = staff.get("permissions")
    record(bool(invite_code_api),
           "POST /household/staff response includes invite_code (API contract)",
           f"got invite_code={invite_code_api!r} (StaffMember model missing field)")
    record(isinstance(perms_api, dict) and "view_inventory" in (perms_api or {}),
           "POST /household/staff response includes permissions dict",
           f"got permissions={perms_api!r} (StaffMember model missing field)")

    # GET staff and verify permissions.view_inventory == False (default)
    gs = requests.get(_u("household/staff"), headers=_hdr(owner_token),
                     params={"space_id": space_id}, timeout=30)
    gs.raise_for_status()
    staff_list = gs.json()
    me_staff = next((s for s in staff_list if s["staff_id"] == staff_id), None)
    perms = (me_staff or {}).get("permissions") or {}
    record("view_inventory" in perms,
           "GET /household/staff response includes permissions.view_inventory key",
           f"got perms={perms}")
    if "view_inventory" in perms:
        record(perms.get("view_inventory") is False,
               "permissions.view_inventory defaults to False",
               f"got {perms.get('view_inventory')}")
        expected_keys = {"view_tasks", "log_attendance", "request_shopping", "view_handbook",
                         "view_wage_amount", "view_other_staff", "view_family", "view_finance",
                         "view_inventory"}
        missing = expected_keys - set(perms.keys())
        record(len(missing) == 0, "permissions has all 9 default keys",
               f"missing={sorted(missing)}")

    # FALLBACK: read invite_code & default permissions from MongoDB so we can drive
    # the rest of the test even though the response model strips them.
    mdoc = mongo_staff(staff_id)
    invite_code = (mdoc or {}).get("invite_code") or invite_code_api
    mongo_perms = (mdoc or {}).get("permissions") or {}
    record(mongo_perms.get("view_inventory") is False,
           "(mongo) DEFAULT_STAFF_PERMS.view_inventory == False on new staff",
           f"mongo perms={mongo_perms}")
    expected_keys = {"view_tasks", "log_attendance", "request_shopping", "view_handbook",
                     "view_wage_amount", "view_other_staff", "view_family", "view_finance",
                     "view_inventory"}
    missing = expected_keys - set(mongo_perms.keys())
    record(len(missing) == 0,
           "(mongo) staff doc has all 9 permission keys including view_inventory",
           f"missing={sorted(missing)}")

    # Non-owner cannot PATCH permissions before joining (use outsider who isn't a member)
    no = requests.patch(_u(f"household/staff/{staff_id}/permissions"),
                        headers=_hdr(outsider_token),
                        json={"permissions": {"view_inventory": True}}, timeout=30)
    record(no.status_code == 403, "non-member PATCH permissions → 403",
           f"got status={no.status_code} body={no.text[:120]}")

    # Owner PATCH: enable view_inventory + view_finance, others should remain default
    pp = requests.patch(_u(f"household/staff/{staff_id}/permissions"),
                       headers=_hdr(owner_token),
                       json={"permissions": {"view_inventory": True, "view_finance": True}},
                       timeout=30)
    if pp.status_code != 200:
        record(False, "owner PATCH permissions", f"status={pp.status_code} body={pp.text}")
    else:
        body = pp.json()
        rperms = body.get("permissions") or {}
        # If the response model strips the field, verify via mongo.
        if not rperms:
            mdoc2 = mongo_staff(staff_id)
            rperms = (mdoc2 or {}).get("permissions") or {}
            record(False,
                   "PATCH /household/staff/{id}/permissions response body includes permissions",
                   f"response keys={sorted(body.keys())} (StaffMember model strips it; verifying via mongo)")
        record(rperms.get("view_inventory") is True and rperms.get("view_finance") is True,
               "After PATCH: view_inventory=True and view_finance=True",
               f"perms={rperms}")
        record(rperms.get("view_tasks") is True and rperms.get("view_handbook") is True
               and rperms.get("view_other_staff") is False,
               "Other default permissions preserved on merge",
               f"view_tasks={rperms.get('view_tasks')} view_handbook={rperms.get('view_handbook')} view_other_staff={rperms.get('view_other_staff')}")

    # Link secondary user as staff via invite_code
    jr = requests.post(_u("household/staff/join"), headers=_hdr(staff_user_token),
                      json={"invite_code": invite_code}, timeout=30)
    if jr.status_code != 200:
        record(False, "POST /household/staff/join with invite_code",
               f"status={jr.status_code} body={jr.text}")
    else:
        jb = jr.json()
        record(jb.get("space_id") == space_id and jb.get("staff_id") == staff_id,
               "join returns matching space_id + staff_id", f"got {jb}")

    # GET /spaces/{space_id}/my_role as the staff user
    mr = requests.get(_u(f"spaces/{space_id}/my_role"), headers=_hdr(staff_user_token), timeout=30)
    if mr.status_code != 200:
        record(False, "GET /spaces/{id}/my_role as staff user",
               f"status={mr.status_code} body={mr.text}")
    else:
        mb = mr.json()
        record(mb.get("role") == "staff",
               "my_role role == 'staff'", f"got {mb.get('role')}")
        mperms = mb.get("permissions") or {}
        record(mperms.get("view_inventory") is True,
               "my_role.permissions.view_inventory == True",
               f"perms={mperms}")
        record(mperms.get("view_finance") is True,
               "my_role.permissions.view_finance == True (set via PATCH)")

    # Non-owner (the staff user, who is now a member) attempting PATCH → still 403
    no2 = requests.patch(_u(f"household/staff/{staff_id}/permissions"),
                         headers=_hdr(staff_user_token),
                         json={"permissions": {"view_finance": False}}, timeout=30)
    record(no2.status_code == 403,
           "staff (non-owner member) PATCH permissions → 403",
           f"got {no2.status_code} body={no2.text[:120]}")

    return space_id, staff_id


# ============================================================
# 2) NOTIFICATIONS
# ============================================================
def test_notifications(owner_token: str, staff_user_token: str, outsider_token: str,
                       space_id: str, staff_id: str):
    section("2) Notifications CRUD + auto-creation on payroll")

    # Initially empty for staff user
    r0 = requests.get(_u("notifications"), headers=_hdr(staff_user_token),
                      params={"space_id": space_id}, timeout=30)
    if r0.status_code != 200:
        record(False, "GET /notifications initial", f"status={r0.status_code}")
        return
    initial = r0.json()
    record(isinstance(initial, list) and len(initial) == 0,
           "GET /notifications?space_id=... initially empty",
           f"len={len(initial)}")

    # Owner creates payroll
    pp = requests.post(_u("household/payroll"), headers=_hdr(owner_token),
                      json={"space_id": space_id, "staff_id": staff_id}, timeout=30)
    if pp.status_code != 200:
        record(False, "POST /household/payroll", f"status={pp.status_code} body={pp.text}")
        return
    payment = pp.json()
    payment_id = payment["payment_id"]
    record(bool(payment_id) and payment.get("net", 0) > 0,
           "POST /household/payroll returns payment with net>0",
           f"net={payment.get('net')} currency={payment.get('currency')}")

    # Give server a tick (write should be immediate, but be safe)
    time.sleep(0.5)

    # Staff user GET notifications
    r1 = requests.get(_u("notifications"), headers=_hdr(staff_user_token),
                      params={"space_id": space_id}, timeout=30)
    r1.raise_for_status()
    nlist = r1.json()
    record(len(nlist) >= 1, "GET /notifications has wage_paid record",
           f"count={len(nlist)}")
    n0 = nlist[0] if nlist else {}
    record(n0.get("kind") == "wage_paid",
           "notification.kind == 'wage_paid'", f"kind={n0.get('kind')}")
    record(isinstance(n0.get("title"), str) and n0.get("title", "").startswith("Wage received ·"),
           "notification.title startswith 'Wage received ·'",
           f"title={n0.get('title')}")
    record(bool(n0.get("body")),
           "notification.body is non-empty", f"body={n0.get('body')}")
    data = n0.get("data") or {}
    record(data.get("payment_id") == payment_id and "net" in data,
           "notification.data has payment_id + net",
           f"data={data}")
    record(n0.get("read") is False, "notification.read=false initially")

    # unread_only filter
    r2 = requests.get(_u("notifications"), headers=_hdr(staff_user_token),
                      params={"space_id": space_id, "unread_only": "true"}, timeout=30)
    r2.raise_for_status()
    unread = r2.json()
    record(any(x.get("notification_id") == n0.get("notification_id") for x in unread),
           "unread_only=true returns the unread notification",
           f"unread_count={len(unread)}")

    # Mark single read
    nid = n0["notification_id"]
    r3 = requests.post(_u(f"notifications/{nid}/read"), headers=_hdr(staff_user_token), timeout=30)
    record(r3.status_code == 200, "POST /notifications/{id}/read → 200",
           f"status={r3.status_code}")
    # Verify
    r4 = requests.get(_u("notifications"), headers=_hdr(staff_user_token),
                      params={"space_id": space_id}, timeout=30)
    r4.raise_for_status()
    after = r4.json()
    found = next((x for x in after if x.get("notification_id") == nid), None)
    record(found is not None and found.get("read") is True,
           "after /read: that notification.read=true",
           f"found={found}")

    # Create another payroll → second notification
    pp2 = requests.post(_u("household/payroll"), headers=_hdr(owner_token),
                       json={"space_id": space_id, "staff_id": staff_id}, timeout=30)
    record(pp2.status_code == 200, "second POST /household/payroll",
           f"status={pp2.status_code}")
    time.sleep(0.5)

    # mark_all_read
    r5 = requests.post(_u("notifications/read_all"), headers=_hdr(staff_user_token),
                      params={"space_id": space_id}, timeout=30)
    record(r5.status_code == 200, "POST /notifications/read_all → 200",
           f"status={r5.status_code}")
    r6 = requests.get(_u("notifications"), headers=_hdr(staff_user_token),
                      params={"space_id": space_id}, timeout=30)
    r6.raise_for_status()
    all_after = r6.json()
    record(len(all_after) >= 2 and all(x.get("read") is True for x in all_after),
           "all notifications in that space are now read",
           f"count={len(all_after)} reads={[x.get('read') for x in all_after]}")

    # Outsider should not see staff user's notifications
    ro = requests.get(_u("notifications"), headers=_hdr(outsider_token), timeout=30)
    ro.raise_for_status()
    olist = ro.json()
    record(len(olist) == 0,
           "outsider GET /notifications is empty (only their own)",
           f"len={len(olist)}")


# ============================================================
# 3) HOUSEHOLD MONTHLY REPORT
# ============================================================
def test_household_report(owner_token: str, outsider_token: str, space_id: str, staff_id: str):
    section("3) GET /api/reports/household")

    # Ensure attendance for current month
    today = datetime.now(timezone.utc)
    today_str = today.strftime("%Y-%m-%d")
    yest_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    for d, st in [(today_str, "present"), (yest_str, "present")]:
        ar = requests.post(_u("household/attendance"), headers=_hdr(owner_token), json={
            "space_id": space_id, "staff_id": staff_id, "date": d, "status": st,
        }, timeout=30)
        # ok if 200; otherwise log and continue
        if ar.status_code != 200:
            print(f"   [warn] attendance POST {d} {st} -> {ar.status_code} {ar.text[:120]}")

    # Add a shopping_request
    sr = requests.post(_u("household/shopping"), headers=_hdr(owner_token), json={
        "space_id": space_id, "item_name": "Eggs", "quantity": "1 dozen", "urgency": "normal",
    }, timeout=30)
    if sr.status_code != 200:
        print(f"   [warn] shopping POST -> {sr.status_code} {sr.text[:120]}")

    # Add a priced item in some category. Use mongo directly to find a category
    # because GET /api/categories is currently broken in this space (the auto-created
    # "Staff wages" category from _ensure_wages_category is missing the `created_by`
    # field which is required by the Category Pydantic response model — causes a
    # 500 ValidationError). We log this as a separate failure below.
    cresp = requests.get(_u("categories"), headers=_hdr(owner_token),
                       params={"space_id": space_id}, timeout=30)
    record(cresp.status_code == 200,
           "GET /api/categories after payroll returns 200 (auto-created 'Staff wages' must include created_by)",
           f"got status={cresp.status_code} body={cresp.text[:240]}")
    cats: list = []
    if cresp.status_code == 200:
        try:
            cats = cresp.json()
        except Exception:
            cats = []
    if not cats:
        # Fall back to mongo to find any category we can use
        cats = list(_mdb.categories.find({"space_id": space_id}, {"_id": 0}).limit(5))
    if not cats:
        cr = requests.post(_u("categories"), headers=_hdr(owner_token), json={
            "space_id": space_id, "name": "Pantry", "icon": "Refrigerator", "tint": "mint",
        }, timeout=30)
        cr.raise_for_status()
        cat_id = cr.json()["category_id"]
    else:
        cat_id = cats[0]["category_id"]
    ir = requests.post(_u("items"), headers=_hdr(owner_token), json={
        "space_id": space_id, "category_id": cat_id,
        "name": "Bali Coffee Beans", "price": 175000, "quantity": 1,
    }, timeout=30)
    if ir.status_code != 200:
        print(f"   [warn] item POST -> {ir.status_code} {ir.text[:120]}")

    # The default report: GET with no year/month
    rep = requests.get(_u("reports/household"), headers=_hdr(owner_token),
                      params={"space_id": space_id}, timeout=30)
    if rep.status_code != 200:
        record(False, "GET /reports/household default", f"status={rep.status_code} body={rep.text[:200]}")
        return
    body = rep.json()

    # Top-level keys
    expected_keys = {"month", "year", "month_num", "currency", "total_spent", "total_wages",
                     "top_categories", "staff", "shopping", "tasks_done"}
    missing = expected_keys - set(body.keys())
    record(len(missing) == 0, "report has all expected top-level keys",
           f"missing={sorted(missing)}")
    record(isinstance(body.get("month"), str) and isinstance(body.get("year"), int)
           and isinstance(body.get("month_num"), int),
           "month/year/month_num types correct",
           f"month={body.get('month')!r} year={body.get('year')!r} month_num={body.get('month_num')!r}")
    record(body.get("currency") == "IDR", "currency inherited from space (IDR)",
           f"currency={body.get('currency')}")
    record(body.get("month_num") == today.month and body.get("year") == today.year,
           "default month/year == current",
           f"got year={body.get('year')} month_num={body.get('month_num')} (today={today.year}-{today.month})")

    # total_wages == sum of staff_payments.net in window
    pays = requests.get(_u("household/payroll"), headers=_hdr(owner_token),
                       params={"space_id": space_id}, timeout=30).json()
    expected_total_wages = round(sum(float(p.get("net") or 0) for p in pays), 2)
    record(abs(float(body.get("total_wages") or 0) - expected_total_wages) < 0.01,
           "total_wages == sum of payroll.net in window",
           f"got {body.get('total_wages')} expected {expected_total_wages}")

    # staff[] has matching staff entry with all required fields
    staff_arr = body.get("staff") or []
    me_staff = next((s for s in staff_arr if s.get("staff_id") == staff_id), None)
    if not me_staff:
        record(False, "staff[] contains created staff", f"staff_arr={staff_arr}")
    else:
        required = {"days_present", "days_off", "days_sick", "days_leave", "tasks_done",
                    "paid", "salary", "pay_cycle", "name", "photo_base64", "role_id"}
        miss = required - set(me_staff.keys())
        record(len(miss) == 0,
               "staff[] item has all required fields",
               f"missing={sorted(miss)} item_keys={sorted(me_staff.keys())}")
        record(me_staff.get("days_present", 0) >= 1,
               "days_present >= 1 (we logged 'present' today)",
               f"days_present={me_staff.get('days_present')}")
        record(abs(float(me_staff.get("paid") or 0) - expected_total_wages) < 0.01,
               "staff.paid == sum of that staff's payroll in window",
               f"got {me_staff.get('paid')} expected {expected_total_wages}")

    # top_categories[] structure
    tcs = body.get("top_categories") or []
    if not tcs:
        record(False, "top_categories non-empty", "got empty list")
    else:
        sample = tcs[0]
        required = {"category_id", "name", "icon", "tint", "total", "count"}
        miss = required - set(sample.keys())
        record(len(miss) == 0, "top_categories items have category_id/name/icon/tint/total/count",
               f"missing={sorted(miss)} keys={sorted(sample.keys())}")
        # Sum approx == total_spent
        sum_top = sum(float(c.get("total") or 0) for c in tcs)
        record(abs(sum_top - float(body.get("total_spent") or 0)) < 0.5,
               "sum(top_categories.total) ≈ total_spent (top<=5; we have <=5 cats here)",
               f"sum={sum_top} total_spent={body.get('total_spent')}")
        # Staff wages category should appear because we logged payroll
        wages_cat = next((c for c in tcs if c.get("name") == "Staff wages"), None)
        record(wages_cat is not None,
               "top_categories includes 'Staff wages' (from payroll auto-item)",
               f"names={[c.get('name') for c in tcs]}")

    # shopping summary
    sh = body.get("shopping") or {}
    required = {"total", "pending", "approved", "purchased"}
    miss = required - set(sh.keys())
    record(len(miss) == 0, "shopping has total/pending/approved/purchased",
           f"missing={sorted(miss)} shopping={sh}")
    record(sh.get("total", 0) >= 1 and sh.get("pending", 0) >= 1,
           "shopping totals reflect created request",
           f"shopping={sh}")

    # Far-past month → zeros
    rep2 = requests.get(_u("reports/household"), headers=_hdr(owner_token),
                       params={"space_id": space_id, "year": 2020, "month": 1}, timeout=30)
    if rep2.status_code != 200:
        record(False, "GET /reports/household past month",
               f"status={rep2.status_code} body={rep2.text[:160]}")
    else:
        b2 = rep2.json()
        record(b2.get("year") == 2020 and b2.get("month_num") == 1,
               "past month: year=2020 month_num=1",
               f"got year={b2.get('year')} month_num={b2.get('month_num')}")
        record(b2.get("total_spent") == 0 and b2.get("total_wages") == 0,
               "past month: total_spent=0 total_wages=0",
               f"got spent={b2.get('total_spent')} wages={b2.get('total_wages')}")
        record(b2.get("top_categories") == [] and b2.get("tasks_done") == 0,
               "past month: top_categories=[] tasks_done=0",
               f"got top_categories={b2.get('top_categories')} tasks_done={b2.get('tasks_done')}")
        sh2 = b2.get("shopping") or {}
        record(sh2.get("total") == 0 and sh2.get("pending") == 0
               and sh2.get("approved") == 0 and sh2.get("purchased") == 0,
               "past month: shopping all zeros",
               f"got {sh2}")
        record(b2.get("currency") == "IDR",
               "past month: currency still set from space",
               f"currency={b2.get('currency')}")

    # Non-member 403
    nm = requests.get(_u("reports/household"), headers=_hdr(outsider_token),
                     params={"space_id": space_id}, timeout=30)
    record(nm.status_code == 403,
           "non-member GET /reports/household → 403",
           f"got status={nm.status_code} body={nm.text[:140]}")


# ============================================================
# Main
# ============================================================
def main():
    ts = uuid.uuid4().hex[:8]
    staff_email = f"phase4-staff-{ts}@cozii.app"
    outsider_email = f"phase4-out-{ts}@cozii.app"

    print(f"BASE = {BASE}")
    print(f"Owner = {PRIMARY_EMAIL}")
    print(f"Staff user = {staff_email}")
    print(f"Outsider = {outsider_email}")

    owner = login_or_register(PRIMARY_EMAIL, PRIMARY_PASSWORD, "Test User")
    staff_user = login_or_register(staff_email, "phase4pass", "Sari Putri")
    outsider = login_or_register(outsider_email, "phase4pass", "Outsider Oz")

    space_id, staff_id = test_staff_permissions(owner, staff_user, outsider)
    if space_id and staff_id:
        test_notifications(owner, staff_user, outsider, space_id, staff_id)
        test_household_report(owner, outsider, space_id, staff_id)

    # Summary
    section("SUMMARY")
    fails = [(n, d) for ok, n, d in RESULTS if not ok]
    passes = [n for ok, n, _ in RESULTS if ok]
    print(f"PASS {len(passes)} / FAIL {len(fails)} (total {len(RESULTS)})")
    if fails:
        print("\nFailures:")
        for n, d in fails:
            print(f" - {n} -- {d}")
        sys.exit(1)


if __name__ == "__main__":
    main()
