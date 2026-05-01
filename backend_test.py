"""
Cozii backend test suite — focused on NEW additions:
  1. Currency on Space + PATCH /api/spaces/{space_id}
  2. GET /api/reports/finance (totals/by_category/by_member/daily/monthly/top_items/all_items/bills/settlements/insights)
  3. Smoke tests for existing endpoints (auth/login, spaces, categories, items, bills, agreement, balance-details, balances)

To seed items with specific created_at dates (today / 2d ago / 5d ago) we
connect to MongoDB directly (read MONGO_URL/DB_NAME from /app/backend/.env)
and overwrite created_at AFTER the item was created via the API.
"""
import os
import sys
import time
import uuid
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_URL = "https://family-wallet-21.preview.emergentagent.com/api"

# Load mongo creds from backend .env
BACKEND_ENV = Path("/app/backend/.env")
env_vars = {}
for line in BACKEND_ENV.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env_vars[k.strip()] = v.strip().strip('"').strip("'")

MONGO_URL = env_vars.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = env_vars.get("DB_NAME", "test_database")

try:
    from pymongo import MongoClient
    mongo = MongoClient(MONGO_URL)
    mdb = mongo[DB_NAME]
    MONGO_OK = True
except Exception as e:
    print(f"WARN: pymongo not available: {e}")
    MONGO_OK = False

results = []


def log(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    results.append((name, ok, detail))


def h(token):
    return {"Authorization": f"Bearer {token}"}


def register_or_login(email, password, name):
    r = requests.post(f"{BASE_URL}/auth/register", json={"email": email, "password": password, "name": name})
    if r.status_code == 409:
        r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise RuntimeError(f"auth failed for {email}: {r.status_code} {r.text}")
    return r.json()


def test_login_primary():
    # Section 3 smoke: existing /auth/login with seeded creds
    r = requests.post(f"{BASE_URL}/auth/login", json={"email": "test@cozii.app", "password": "test1234"})
    if r.status_code == 200:
        log("auth/login (seeded test@cozii.app)", True)
        return r.json()
    else:
        # try to register if missing
        r2 = requests.post(f"{BASE_URL}/auth/register", json={"email": "test@cozii.app", "password": "test1234", "name": "Test User"})
        if r2.status_code == 200:
            log("auth/login (seeded test@cozii.app) — created", True)
            return r2.json()
        log("auth/login (seeded test@cozii.app)", False, f"login {r.status_code} / register {r2.status_code}")
        return None


# ==============================================================
# 1. Currency on Space + PATCH /api/spaces/{space_id}
# ==============================================================
def test_currency_and_patch(tok_a, user_a, tok_c, user_c):
    # POST /spaces with currency: CAD
    r = requests.post(f"{BASE_URL}/spaces", json={"name": "Maple House", "currency": "CAD"}, headers=h(tok_a))
    ok1 = r.status_code == 200 and r.json().get("currency") == "CAD"
    log("POST /spaces with currency=CAD returns currency=CAD", ok1, "" if ok1 else r.text)
    space_cad = r.json() if r.status_code == 200 else None

    # POST /spaces without currency -> default USD
    r2 = requests.post(f"{BASE_URL}/spaces", json={"name": "Default Place"}, headers=h(tok_a))
    ok2 = r2.status_code == 200 and r2.json().get("currency") == "USD"
    log("POST /spaces without currency defaults to USD", ok2, "" if ok2 else r2.text)
    space_def = r2.json() if r2.status_code == 200 else None

    # PATCH currency: "idr" -> normalize "IDR"
    if space_cad:
        r3 = requests.patch(f"{BASE_URL}/spaces/{space_cad['space_id']}", json={"currency": "idr"}, headers=h(tok_a))
        ok3 = r3.status_code == 200 and r3.json().get("currency") == "IDR"
        log("PATCH /spaces currency=idr normalizes to IDR", ok3, "" if ok3 else f"{r3.status_code} {r3.text}")

        # PATCH name only; currency unchanged
        r4 = requests.patch(f"{BASE_URL}/spaces/{space_cad['space_id']}", json={"name": "Renamed Maple"}, headers=h(tok_a))
        ok4 = r4.status_code == 200 and r4.json().get("name") == "Renamed Maple" and r4.json().get("currency") == "IDR"
        log("PATCH /spaces name-only keeps currency", ok4, "" if ok4 else f"{r4.status_code} {r4.text}")

        # Non-member attempt -> 403
        r5 = requests.patch(f"{BASE_URL}/spaces/{space_cad['space_id']}", json={"name": "Hacker"}, headers=h(tok_c))
        ok5 = r5.status_code == 403
        log("PATCH /spaces as non-member returns 403", ok5, f"got {r5.status_code}" if not ok5 else "")

    # GET /spaces includes currency for every space
    r6 = requests.get(f"{BASE_URL}/spaces", headers=h(tok_a))
    ok6 = r6.status_code == 200 and all("currency" in s for s in r6.json())
    log("GET /spaces includes currency on every space", ok6, "" if ok6 else r6.text[:300])

    return space_cad, space_def


# ==============================================================
# 2. GET /api/reports/finance
# ==============================================================
def test_finance_report(tok_a, user_a, tok_c):
    # Create dedicated space with currency EUR for clarity
    r = requests.post(f"{BASE_URL}/spaces", json={"name": "Finance Lab", "currency": "EUR"}, headers=h(tok_a))
    assert r.status_code == 200, r.text
    space = r.json()
    sid = space["space_id"]

    # Create a category
    rc = requests.post(
        f"{BASE_URL}/categories",
        json={"space_id": sid, "name": "Groceries", "icon": "ShoppingCart", "tint": "mint", "fields": []},
        headers=h(tok_a),
    )
    assert rc.status_code == 200, rc.text
    cat = rc.json()

    # Create 3 items with prices 10, 20, 30
    created_items = []
    for idx, price in enumerate([10.0, 20.0, 30.0]):
        name = ["Apples", "Bread", "Cheese Wheel"][idx]
        ri = requests.post(
            f"{BASE_URL}/items",
            json={"space_id": sid, "category_id": cat["category_id"], "name": name, "price": price},
            headers=h(tok_a),
        )
        assert ri.status_code == 200, ri.text
        created_items.append(ri.json())

    # Override created_at in Mongo: today (keep as-is), 2 days ago, 5 days ago
    if MONGO_OK:
        today = datetime.now(timezone.utc)
        dates = [today, today - timedelta(days=2), today - timedelta(days=5)]
        for it, dt in zip(created_items, dates):
            mdb.items.update_one({"item_id": it["item_id"]}, {"$set": {"created_at": dt}})
    else:
        log("finance: cannot override created_at (pymongo missing) — daily test may skew", False)

    # ---- period=this_month (status smoke) ----
    rep_tm = requests.get(f"{BASE_URL}/reports/finance", params={"space_id": sid, "period": "this_month"}, headers=h(tok_a))
    ok_tm = rep_tm.status_code == 200
    log("GET /reports/finance?period=this_month 200", ok_tm, "" if ok_tm else f"{rep_tm.status_code} {rep_tm.text[:300]}")
    if not ok_tm:
        return
    log("finance(this_month): period_key == this_month", rep_tm.json().get("period_key") == "this_month")

    # ---- primary shape assertions use period=ytd so all 3 backdated items fall in the window ----
    # (items seeded at today, today-2d, today-5d may straddle month boundary if today is early in the month)
    rep = requests.get(f"{BASE_URL}/reports/finance", params={"space_id": sid, "period": "ytd"}, headers=h(tok_a))
    ok_status = rep.status_code == 200
    log("GET /reports/finance?period=ytd 200", ok_status, "" if ok_status else f"{rep.status_code} {rep.text[:300]}")
    if not ok_status:
        return
    body = rep.json()

    # Shape checks
    required_keys = ["period_key", "period_label", "start", "end", "currency",
                     "totals", "by_category", "by_member", "daily", "monthly",
                     "top_items", "all_items", "bills", "settlements", "insights"]
    missing = [k for k in required_keys if k not in body]
    log("finance: response has all required top-level keys", not missing, f"missing={missing}")

    log("finance: period_key == ytd", body.get("period_key") == "ytd")
    log("finance: currency == EUR (inherited from space)", body.get("currency") == "EUR",
        f"got {body.get('currency')}")

    # Totals (all 3 items should be within this month assuming run is not in the first 5 days of month)
    totals = body.get("totals", {})
    totals_ok = (
        totals.get("total") == 60
        and totals.get("count") == 3
        and totals.get("avg_per_item") == 20
        and totals.get("largest") == 30
        and totals.get("smallest") == 10
    )
    log("finance: totals {total:60,count:3,avg:20,largest:30,smallest:10}", totals_ok, f"got {totals}")

    # by_category: 1 entry, 100% pct
    bc = body.get("by_category", [])
    bc_ok = (
        len(bc) == 1
        and bc[0].get("category_id") == cat["category_id"]
        and bc[0].get("name") == "Groceries"
        and bc[0].get("tint") == "mint"
        and bc[0].get("total") == 60
        and bc[0].get("count") == 3
        and bc[0].get("pct") == 100
    )
    log("finance: by_category single entry at 100%", bc_ok, f"got {bc}")

    # by_member: current user contributes 100%
    bm = body.get("by_member", [])
    bm_ok = (
        len(bm) >= 1
        and bm[0].get("user_id") == user_a["user_id"]
        and bm[0].get("total") == 60
        and bm[0].get("count") == 3
        and bm[0].get("pct") == 100
    )
    log("finance: by_member shows current user at 100%", bm_ok, f"got {bm}")

    # daily: 3 entries (one per day)
    daily = body.get("daily", [])
    log("finance: daily has 3 entries (one per day)", len(daily) == 3, f"got {len(daily)} entries")

    # monthly: >= 1 entry
    monthly = body.get("monthly", [])
    log("finance: monthly has at least 1 entry", len(monthly) >= 1, f"got {len(monthly)}")

    # top_items: 3, sorted desc by price
    ti = body.get("top_items", [])
    ti_ok = (
        len(ti) == 3
        and ti[0].get("price") == 30
        and ti[1].get("price") == 20
        and ti[2].get("price") == 10
        and ti[0].get("purchased_by") == user_a["name"]
    )
    log("finance: top_items sorted desc (30,20,10) with purchased_by", ti_ok, f"got {ti}")

    # all_items: 3 with required fields
    ai = body.get("all_items", [])
    required_item_fields = ["item_id", "name", "category_name", "price", "quantity", "purchased_by", "created_at"]
    ai_shape_ok = len(ai) == 3 and all(all(f in x for f in required_item_fields) for x in ai)
    log("finance: all_items has 3 entries with required fields", ai_shape_ok,
        f"len={len(ai)} sample_keys={list(ai[0].keys()) if ai else None}")

    # bills: [] initially
    log("finance: bills is [] initially", body.get("bills") == [], f"got {body.get('bills')}")

    # settlements: [] initially
    log("finance: settlements is [] initially", body.get("settlements") == [], f"got {body.get('settlements')}")

    # insights: non-empty list; first should mention "3 purchases"
    ins = body.get("insights", [])
    ins_ok = isinstance(ins, list) and len(ins) >= 1 and ("3 purchases" in ins[0] or "3 " in ins[0])
    log("finance: insights non-empty & mentions '3 purchases'", ins_ok, f"insights[0]={ins[0] if ins else None}")

    # ---- Other periods smoke: last_month (should be 0 IF we had seeded items only today;
    # but we backdated 2 items to -2d/-5d so on month boundaries they may fall into last_month.
    # The semantic check we care about here is that period filtering is enforced:
    # period=this_month must NOT include the -5d item. Verify by comparing ytd count vs this_month count.
    rep2 = requests.get(f"{BASE_URL}/reports/finance", params={"space_id": sid, "period": "last_month"}, headers=h(tok_a))
    log("finance: period=last_month 200", rep2.status_code == 200, "" if rep2.status_code == 200 else rep2.text[:200])

    rep_tm2 = requests.get(f"{BASE_URL}/reports/finance", params={"space_id": sid, "period": "this_month"}, headers=h(tok_a))
    tm_count = rep_tm2.json().get("totals", {}).get("count", -1) if rep_tm2.status_code == 200 else -1
    # Period filtering sanity: the -5d item must NOT be in this_month (unless today >= 6th of month).
    today_day = datetime.now(timezone.utc).day
    if today_day >= 6:
        filter_ok = tm_count == 3
        note = f"today.day={today_day} expect all 3 in this_month, got {tm_count}"
    elif today_day >= 3:
        filter_ok = tm_count < 3  # -5d is excluded at minimum
        note = f"today.day={today_day} expect <3 in this_month, got {tm_count}"
    else:
        filter_ok = tm_count <= 1
        note = f"today.day={today_day} expect <=1 in this_month, got {tm_count}"
    log("finance: period filtering excludes out-of-window items", filter_ok, note)

    for p in ["last_3_months", "ytd", "all"]:
        rp = requests.get(f"{BASE_URL}/reports/finance", params={"space_id": sid, "period": p}, headers=h(tok_a))
        log(f"finance: period={p} 200", rp.status_code == 200, "" if rp.status_code == 200 else rp.text[:200])

    # Non-member -> 403
    r403 = requests.get(f"{BASE_URL}/reports/finance", params={"space_id": sid, "period": "this_month"}, headers=h(tok_c))
    log("finance: non-member returns 403", r403.status_code == 403, f"got {r403.status_code}")

    return sid, cat


# ==============================================================
# 3. Smoke tests for existing endpoints
# ==============================================================
def test_existing_smoke(tok_a, user_a):
    # /spaces GET
    rs = requests.get(f"{BASE_URL}/spaces", headers=h(tok_a))
    log("smoke: GET /spaces", rs.status_code == 200 and isinstance(rs.json(), list))
    if rs.status_code != 200 or not rs.json():
        return
    sid = rs.json()[0]["space_id"]

    # /categories CRUD
    rc = requests.post(
        f"{BASE_URL}/categories",
        json={"space_id": sid, "name": f"SmokeCat_{uuid.uuid4().hex[:4]}", "icon": "Box", "tint": "mint", "fields": []},
        headers=h(tok_a),
    )
    log("smoke: POST /categories", rc.status_code == 200)
    cat_id = rc.json().get("category_id") if rc.status_code == 200 else None

    rlc = requests.get(f"{BASE_URL}/categories", params={"space_id": sid}, headers=h(tok_a))
    log("smoke: GET /categories", rlc.status_code == 200)

    if cat_id:
        ru = requests.patch(f"{BASE_URL}/categories/{cat_id}", json={"name": "SmokeCat Renamed"}, headers=h(tok_a))
        log("smoke: PATCH /categories/{id}", ru.status_code == 200)

        # /items CRUD
        ri = requests.post(
            f"{BASE_URL}/items",
            json={"space_id": sid, "category_id": cat_id, "name": "Smoke Milk", "price": 4.50},
            headers=h(tok_a),
        )
        log("smoke: POST /items", ri.status_code == 200)
        item_id = ri.json().get("item_id") if ri.status_code == 200 else None
        rli = requests.get(f"{BASE_URL}/items", params={"space_id": sid}, headers=h(tok_a))
        log("smoke: GET /items", rli.status_code == 200)
        if item_id:
            rup = requests.patch(f"{BASE_URL}/items/{item_id}", json={"status": "low"}, headers=h(tok_a))
            log("smoke: PATCH /items/{id}", rup.status_code == 200)
            rdi = requests.delete(f"{BASE_URL}/items/{item_id}", headers=h(tok_a))
            log("smoke: DELETE /items/{id}", rdi.status_code == 200)

        # /bills CRUD + pay
        rb = requests.post(
            f"{BASE_URL}/bills",
            json={"space_id": sid, "name": "Internet", "amount": 45.0, "frequency": "monthly", "due_day": 5,
                  "category_id": cat_id},
            headers=h(tok_a),
        )
        log("smoke: POST /bills", rb.status_code == 200, "" if rb.status_code == 200 else rb.text[:200])
        bid = rb.json().get("bill_id") if rb.status_code == 200 else None
        rlb = requests.get(f"{BASE_URL}/bills", params={"space_id": sid}, headers=h(tok_a))
        log("smoke: GET /bills", rlb.status_code == 200)
        if bid:
            rpb = requests.patch(f"{BASE_URL}/bills/{bid}", json={"amount": 55.0}, headers=h(tok_a))
            log("smoke: PATCH /bills/{id}", rpb.status_code == 200)
            rpay = requests.post(f"{BASE_URL}/bills/{bid}/pay", headers=h(tok_a))
            pay_ok = rpay.status_code == 200 and rpay.json().get("is_paid_current_period") is True
            log("smoke: POST /bills/{id}/pay -> is_paid_current_period=True", pay_ok,
                "" if pay_ok else f"{rpay.status_code} {rpay.text[:200]}")
            rdb = requests.delete(f"{BASE_URL}/bills/{bid}", headers=h(tok_a))
            log("smoke: DELETE /bills/{id}", rdb.status_code == 200)

        # Clean up category
        requests.delete(f"{BASE_URL}/categories/{cat_id}", headers=h(tok_a))

    # /agreement GET/PUT/sign
    rag = requests.get(f"{BASE_URL}/agreement", params={"space_id": sid}, headers=h(tok_a))
    log("smoke: GET /agreement", rag.status_code == 200)
    rput = requests.put(f"{BASE_URL}/agreement", params={"space_id": sid},
                        json={"text": "House rules", "sections": []}, headers=h(tok_a))
    log("smoke: PUT /agreement", rput.status_code == 200, "" if rput.status_code == 200 else rput.text[:200])
    rsign = requests.post(f"{BASE_URL}/agreement/sign", params={"space_id": sid}, headers=h(tok_a))
    sign_ok = rsign.status_code == 200 and len(rsign.json().get("signatures", [])) == 1
    log("smoke: POST /agreement/sign", sign_ok, "" if sign_ok else f"{rsign.status_code} {rsign.text[:200]}")

    # /balance-details (need with_user_id — use self, API should return 400 because not in space? Actually self IS in space_id. But endpoint expects 2+ users. Let's just call with self to verify 200 + empty breakdown.)
    rbd = requests.get(f"{BASE_URL}/balance-details",
                       params={"space_id": sid, "with_user_id": user_a["user_id"]}, headers=h(tok_a))
    log("smoke: GET /balance-details", rbd.status_code == 200)

    # /balances
    rbal = requests.get(f"{BASE_URL}/balances", params={"space_id": sid}, headers=h(tok_a))
    log("smoke: GET /balances", rbal.status_code == 200)


# ==============================================================
def main():
    test_login_primary()

    ts = int(time.time())
    user_a_email = f"alex.morgan+{ts}@cozii.app"
    user_c_email = f"jordan.park+{ts}@cozii.app"

    a = register_or_login(user_a_email, "SuperStrongPwd!23", "Alex Morgan")
    c = register_or_login(user_c_email, "SuperStrongPwd!23", "Jordan Park")

    test_currency_and_patch(a["token"], a["user"], c["token"], c["user"])
    test_finance_report(a["token"], a["user"], c["token"])
    test_existing_smoke(a["token"], a["user"])

    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n=== SUMMARY: {passed} passed / {failed} failed / {len(results)} total ===")
    if failed:
        print("FAILURES:")
        for n, ok, d in results:
            if not ok:
                print(f"  - {n}: {d}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
