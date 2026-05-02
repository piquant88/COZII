"""Phase 6 backend tests:
- Staff lifecycle fields (active, end_date) on POST/PATCH /api/household/staff
- /api/reports/household filter logic
- Legacy Item/Category listing with missing updated_at
- Spot-check existing endpoints
"""
import os
import time
import uuid
import requests
from datetime import datetime, timezone
from pymongo import MongoClient

BASE = "https://family-wallet-21.preview.emergentagent.com/api"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "test_database"

mongo = MongoClient(MONGO_URL)[DB_NAME]

results = []
def check(label, ok, info=""):
    tag = "PASS" if ok else "FAIL"
    results.append((tag, label, info))
    print(f"[{tag}] {label}{(' :: ' + info) if info else ''}")
    return ok

def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def register(email, name, password="test1234"):
    r = requests.post(f"{BASE}/auth/register", json={"email": email, "name": name, "password": password}, timeout=30)
    if r.status_code == 200:
        return r.json()["token"], r.json()["user"]["user_id"]
    # already exists -> login
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()["token"], r.json()["user"]["user_id"]


def main():
    ts = int(time.time())
    owner_email = f"phase6_owner_{ts}@cozii.app"
    other_email = f"phase6_other_{ts}@cozii.app"
    print(f"\n=== Phase 6 Test Run {ts} ===")
    owner_token, owner_uid = register(owner_email, "Anya Patel")
    other_token, other_uid = register(other_email, "Sam Lee")

    # 1) Create a fresh household space (IDR)
    r = requests.post(f"{BASE}/spaces",
                      json={"name": f"Patel Household {ts}", "space_type": "household", "currency": "IDR"},
                      headers=hdr(owner_token), timeout=30)
    check("POST /spaces (household, IDR)", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    space = r.json()
    space_id = space["space_id"]
    check("space.currency == IDR", space.get("currency") == "IDR", f"got={space.get('currency')}")
    check("space.space_type == household", space.get("space_type") == "household", f"got={space.get('space_type')}")

    # ====== Section 1: Staff lifecycle fields on POST/PATCH ======
    print("\n--- Section 1: Staff lifecycle fields ---")
    # POST with {space_id, name, salary, active: false}
    r = requests.post(f"{BASE}/household/staff",
                      json={"space_id": space_id, "name": "Lifecycle Test", "salary": 1000000, "active": False},
                      headers=hdr(owner_token), timeout=30)
    check("POST /household/staff active=false returns 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        s = r.json()
        check("POST response.active == false", s.get("active") is False, f"got={s.get('active')!r}")
        check("POST response.end_date is null", s.get("end_date") is None, f"got={s.get('end_date')!r}")
        lifecycle_staff_id = s["staff_id"]

        # PATCH with end_date + active
        r2 = requests.patch(f"{BASE}/household/staff/{lifecycle_staff_id}",
                            json={"end_date": "2026-01-31", "active": False},
                            headers=hdr(owner_token), timeout=30)
        check("PATCH /household/staff/{id} returns 200", r2.status_code == 200, f"status={r2.status_code} body={r2.text[:200]}")
        if r2.status_code == 200:
            s2 = r2.json()
            check("PATCH response.end_date == 2026-01-31", s2.get("end_date") == "2026-01-31", f"got={s2.get('end_date')!r}")
            check("PATCH response.active == false", s2.get("active") is False, f"got={s2.get('active')!r}")

        # cleanup
        requests.delete(f"{BASE}/household/staff/{lifecycle_staff_id}", headers=hdr(owner_token), timeout=30)

    # ====== Section 2: /api/reports/household filter logic ======
    print("\n--- Section 2: /reports/household filter logic ---")
    # Create 4 staff
    def create_staff(payload):
        r = requests.post(f"{BASE}/household/staff", json={"space_id": space_id, **payload},
                          headers=hdr(owner_token), timeout=30)
        if r.status_code != 200:
            print(f"  ! create_staff failed: status={r.status_code} body={r.text[:300]}")
            return None
        return r.json()

    A = create_staff({"name": "A_active_clean", "salary": 5000000})
    B = create_staff({"name": "B_inactive_quit", "salary": 3000000, "active": False})
    C = create_staff({"name": "C_future_start", "salary": 4000000, "start_date": "2099-01-01"})
    D = create_staff({"name": "D_ended_long_ago", "salary": 2000000, "end_date": "2020-01-31"})

    check("All 4 staff created (A,B,C,D)", all([A, B, C, D]),
          f"A={bool(A)} B={bool(B)} C={bool(C)} D={bool(D)}")

    # Inspect what was actually stored — verify B/C/D have the lifecycle fields persisted
    if B:
        bdoc = mongo.staff_members.find_one({"staff_id": B["staff_id"]}, {"_id": 0})
        check("Mongo: B has active=false stored", bdoc and bdoc.get("active") is False,
              f"stored active={bdoc.get('active')!r}, keys={sorted(bdoc.keys()) if bdoc else None}")
    if C:
        cdoc = mongo.staff_members.find_one({"staff_id": C["staff_id"]}, {"_id": 0})
        check("Mongo: C has start_date=2099-01-01 stored", cdoc and cdoc.get("start_date") == "2099-01-01",
              f"stored start_date={cdoc.get('start_date')!r}")
    if D:
        ddoc = mongo.staff_members.find_one({"staff_id": D["staff_id"]}, {"_id": 0})
        check("Mongo: D has end_date=2020-01-31 stored", ddoc and ddoc.get("end_date") == "2020-01-31",
              f"stored end_date={ddoc.get('end_date')!r}")

    # POST one payroll for staff A (current month)
    if A:
        r = requests.post(f"{BASE}/household/payroll",
                          json={"space_id": space_id, "staff_id": A["staff_id"], "gross": 5000000},
                          headers=hdr(owner_token), timeout=30)
        check("POST /household/payroll for A", r.status_code == 200,
              f"status={r.status_code} body={r.text[:200]}")

    # GET /reports/household defaulting to current month
    r = requests.get(f"{BASE}/reports/household", params={"space_id": space_id},
                     headers=hdr(owner_token), timeout=30)
    check("GET /reports/household current-month 200", r.status_code == 200,
          f"status={r.status_code} body={r.text[:200]}")
    rep = r.json() if r.status_code == 200 else {}
    rep_staff = rep.get("staff", [])
    rep_ids = {s["staff_id"] for s in rep_staff}
    rep_names = {s.get("name") for s in rep_staff}
    print(f"  report.staff names: {rep_names}")

    if A:
        check("report.staff includes A (active, paid in window)", A["staff_id"] in rep_ids,
              f"rep_names={rep_names}")
    if B:
        check("report.staff EXCLUDES B (active=false, no activity)", B["staff_id"] not in rep_ids,
              f"rep_names={rep_names}")
    if C:
        check("report.staff EXCLUDES C (future start_date)", C["staff_id"] not in rep_ids,
              f"rep_names={rep_names}")
    if D:
        check("report.staff EXCLUDES D (end_date in 2020)", D["staff_id"] not in rep_ids,
              f"rep_names={rep_names}")

    check("report.staff has exactly {A}", rep_ids == ({A["staff_id"]} if A else set()),
          f"got={rep_names}")

    # Historical injection for D: insert a staff_payments doc directly with paid_at in 2020-01
    if D:
        hist_payment_id = f"pay_hist_{uuid.uuid4().hex[:10]}"
        hist_paid_at = datetime(2020, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        mongo.staff_payments.insert_one({
            "payment_id": hist_payment_id,
            "space_id": space_id,
            "staff_id": D["staff_id"],
            "staff_name": D.get("name"),
            "period": "2020-01",
            "gross": 2000000.0,
            "advances": 0.0,
            "deductions": 0.0,
            "bonus": 0.0,
            "net": 2000000.0,
            "currency": "IDR",
            "receipt_photo": None,
            "notes": "historical test injection",
            "item_id": None,
            "paid_at": hist_paid_at,
        })

        r = requests.get(f"{BASE}/reports/household",
                         params={"space_id": space_id, "year": 2020, "month": 1},
                         headers=hdr(owner_token), timeout=30)
        check("GET /reports/household 2020-01 200", r.status_code == 200,
              f"status={r.status_code} body={r.text[:200]}")
        if r.status_code == 200:
            hist_rep = r.json()
            hist_staff = hist_rep.get("staff", [])
            d_entry = next((s for s in hist_staff if s["staff_id"] == D["staff_id"]), None)
            check("Historical 2020-01 report includes D", d_entry is not None,
                  f"hist staff names={[s.get('name') for s in hist_staff]}")
            if d_entry:
                check("Historical D.paid > 0", float(d_entry.get("paid", 0)) > 0,
                      f"paid={d_entry.get('paid')}")

    # ====== Section 3: Legacy Item/Category list no longer 500s ======
    print("\n--- Section 3: Legacy items/categories without updated_at ---")
    # Need a category in this space to add an item; use POST then strip updated_at directly
    r = requests.post(f"{BASE}/categories",
                      json={"space_id": space_id, "name": "Snacks", "icon": "Cookie", "tint": "lavender", "fields": []},
                      headers=hdr(owner_token), timeout=30)
    check("POST /categories OK", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        cat = r.json()
        cat_id = cat["category_id"]
        # Strip updated_at on this category to simulate legacy
        mongo.categories.update_one({"category_id": cat_id}, {"$unset": {"updated_at": ""}})
        # Insert an item, then strip updated_at
        r = requests.post(f"{BASE}/items",
                          json={"space_id": space_id, "category_id": cat_id, "name": "Legacy Cookies", "price": 25000},
                          headers=hdr(owner_token), timeout=30)
        check("POST /items OK", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
        if r.status_code == 200:
            item_id = r.json()["item_id"]
            mongo.items.update_one({"item_id": item_id}, {"$unset": {"updated_at": ""}})

            # Now GET both endpoints -> 200 even though docs lack updated_at
            r1 = requests.get(f"{BASE}/items", params={"space_id": space_id},
                              headers=hdr(owner_token), timeout=30)
            check("GET /items?space_id=... returns 200 (legacy doc, no updated_at)", r1.status_code == 200,
                  f"status={r1.status_code} body={r1.text[:300]}")
            if r1.status_code == 200:
                items = r1.json()
                legacy = next((it for it in items if it.get("item_id") == item_id), None)
                check("Legacy item present in /items list", legacy is not None,
                      f"got count={len(items)}")
                if legacy is not None:
                    check("Legacy item.updated_at is null/None allowed",
                          legacy.get("updated_at") is None,
                          f"updated_at={legacy.get('updated_at')!r}")

            r2 = requests.get(f"{BASE}/categories", params={"space_id": space_id},
                              headers=hdr(owner_token), timeout=30)
            check("GET /categories?space_id=... returns 200 (legacy doc, no updated_at)", r2.status_code == 200,
                  f"status={r2.status_code} body={r2.text[:300]}")

    # ====== Section 4: Spot-check existing endpoints ======
    print("\n--- Section 4: Spot-check existing endpoints ---")
    # GET /reports/finance
    r = requests.get(f"{BASE}/reports/finance", params={"space_id": space_id, "period": "this_month"},
                     headers=hdr(owner_token), timeout=30)
    check("GET /reports/finance still works", r.status_code == 200,
          f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        fin = r.json()
        check("/reports/finance has expected keys",
              all(k in fin for k in ["totals", "by_category", "by_member", "daily", "monthly", "all_items"]),
              f"keys={list(fin.keys())}")

    # POST /household/tasks/quick — create staff w/ default active to attach to
    r = requests.post(f"{BASE}/household/staff",
                      json={"space_id": space_id, "name": "QuickTask Recipient", "salary": 1000000},
                      headers=hdr(owner_token), timeout=30)
    if r.status_code == 200:
        staff_for_quick = r.json()
        r = requests.post(f"{BASE}/household/tasks/quick",
                          json={"space_id": space_id, "staff_id": staff_for_quick["staff_id"],
                                "title": "Buy garlic"},
                          headers=hdr(owner_token), timeout=30)
        check("POST /household/tasks/quick still works", r.status_code == 200,
              f"status={r.status_code} body={r.text[:200]}")
        if r.status_code == 200:
            t = r.json()
            check("quick task recurrence=once", t.get("recurrence") == "once",
                  f"got={t.get('recurrence')}")
        # cleanup
        requests.delete(f"{BASE}/household/staff/{staff_for_quick['staff_id']}", headers=hdr(owner_token), timeout=30)

    # ====== Summary ======
    fails = [r for r in results if r[0] == "FAIL"]
    print(f"\n=== Summary: {len(results)-len(fails)}/{len(results)} pass, {len(fails)} fail ===")
    for tag, label, info in fails:
        print(f"  [{tag}] {label} :: {info}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
