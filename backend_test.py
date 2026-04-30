"""
Cozii backend test suite.
Covers:
  - Auth (register/login/me)
  - Spaces (create, join via invite, members)
  - Categories
  - Items (basic smoke)
  - Balance details (new)
  - Recurring bills CRUD + pay
  - Roommate agreement (GET/PUT/sign + access control)
  - Existing /balances and /settlements regression
"""
import os
import time
import uuid
import requests
from typing import Optional

BASE_URL = "https://family-wallet-21.preview.emergentagent.com/api"

results = []  # list of (name, ok, detail)


def log(name: str, ok: bool, detail: str = ""):
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}{(' - ' + detail) if detail else ''}")
    results.append((name, ok, detail))


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_or_login(email: str, password: str, name: str) -> dict:
    """Returns {token, user}. Tries register first; if 409, falls back to login."""
    r = requests.post(f"{BASE_URL}/auth/register", json={"email": email, "password": password, "name": name})
    if r.status_code == 409:
        r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        raise RuntimeError(f"auth failed for {email}: {r.status_code} {r.text}")
    return r.json()


def main():
    ts = int(time.time())
    # Use realistic looking emails. Use timestamp suffix so we get fresh users per run.
    user_a_email = f"alex.morgan+{ts}@cozii.app"
    user_b_email = f"riley.chen+{ts}@cozii.app"
    user_c_email = f"jordan.park+{ts}@cozii.app"  # third party (not in space)

    # === 1. Auth: register A + B + C ===
    try:
        a = register_or_login(user_a_email, "Hunter#2026", "Alex Morgan")
        log("auth/register A", True, f"user_id={a['user']['user_id']}")
    except Exception as e:
        log("auth/register A", False, str(e))
        return

    try:
        b = register_or_login(user_b_email, "Hunter#2026", "Riley Chen")
        log("auth/register B", True, f"user_id={b['user']['user_id']}")
    except Exception as e:
        log("auth/register B", False, str(e))
        return

    try:
        c = register_or_login(user_c_email, "Hunter#2026", "Jordan Park")
        log("auth/register C (outsider)", True)
    except Exception as e:
        log("auth/register C", False, str(e))
        return

    # === 1b. /auth/me sanity ===
    r = requests.get(f"{BASE_URL}/auth/me", headers=auth_headers(a["token"]))
    log("auth/me works", r.status_code == 200 and r.json().get("email") == user_a_email,
        f"status={r.status_code}")

    # === 1c. /auth/login regression with primary credentials in test_credentials.md ===
    # Try to login with the seed account; if not present register it once.
    primary_email, primary_pwd = "test@cozii.app", "test1234"
    rr = requests.post(f"{BASE_URL}/auth/login", json={"email": primary_email, "password": primary_pwd})
    if rr.status_code == 401:
        rr = requests.post(f"{BASE_URL}/auth/register",
                           json={"email": primary_email, "password": primary_pwd, "name": "Test User"})
    log("auth/login primary credentials", rr.status_code == 200, f"status={rr.status_code}")

    # === 2. Spaces ===
    r = requests.post(f"{BASE_URL}/spaces", json={"name": "Roommate HQ"}, headers=auth_headers(a["token"]))
    if r.status_code != 200:
        log("spaces/create", False, f"{r.status_code} {r.text}")
        return
    space = r.json()
    space_id = space["space_id"]
    invite_code = space["invite_code"]
    log("spaces/create", True, f"space_id={space_id}")

    # B joins via invite_code
    r = requests.post(f"{BASE_URL}/spaces/join", json={"invite_code": invite_code}, headers=auth_headers(b["token"]))
    log("spaces/join (B)", r.status_code == 200 and a["user"]["user_id"] in r.json()["member_ids"]
        and b["user"]["user_id"] in r.json()["member_ids"],
        f"status={r.status_code}")

    # GET /spaces (A)
    r = requests.get(f"{BASE_URL}/spaces", headers=auth_headers(a["token"]))
    log("spaces/list (A)", r.status_code == 200 and any(s["space_id"] == space_id for s in r.json()),
        f"status={r.status_code} count={len(r.json()) if r.status_code == 200 else 0}")

    # GET /spaces/{id}/members
    r = requests.get(f"{BASE_URL}/spaces/{space_id}/members", headers=auth_headers(a["token"]))
    log("spaces/members", r.status_code == 200 and len(r.json()) == 2, f"status={r.status_code}")

    # === 3. Categories: create a shared category ===
    a_id = a["user"]["user_id"]
    b_id = b["user"]["user_id"]

    cat_payload = {
        "space_id": space_id,
        "name": "Groceries (Shared)",
        "icon": "ShoppingCart",
        "tint": "mint",
        "fields": [],
        "shared_with": [a_id, b_id],
    }
    r = requests.post(f"{BASE_URL}/categories", json=cat_payload, headers=auth_headers(a["token"]))
    if r.status_code != 200:
        log("categories/create shared", False, f"{r.status_code} {r.text}")
        return
    shared_cat = r.json()
    shared_cat_id = shared_cat["category_id"]
    log("categories/create shared", set(shared_cat["shared_with"]) == {a_id, b_id})

    # GET /categories
    r = requests.get(f"{BASE_URL}/categories?space_id={space_id}", headers=auth_headers(a["token"]))
    log("categories/list", r.status_code == 200 and any(c["category_id"] == shared_cat_id for c in r.json()),
        f"status={r.status_code}")

    # === 4. Items: A creates 2, B creates 1 ===
    item_ids = []
    for i, (token, price, name) in enumerate([
        (a["token"], 24.50, "Olive oil"),
        (a["token"], 60.00, "Costco run"),
        (b["token"], 18.00, "Fresh produce"),
    ]):
        r = requests.post(f"{BASE_URL}/items",
                          json={"space_id": space_id, "category_id": shared_cat_id,
                                "name": name, "price": price},
                          headers=auth_headers(token))
        if r.status_code != 200:
            log(f"items/create #{i}", False, f"{r.status_code} {r.text}")
            return
        item_ids.append(r.json()["item_id"])
    log("items/create 3 items", True, f"items={item_ids}")

    # === 5. Balance details ===
    # As A: should have 3 entries: 2 they_owe_you (A's own) + 1 you_owe_them (B's)
    r = requests.get(f"{BASE_URL}/balance-details?space_id={space_id}&with_user_id={b_id}",
                     headers=auth_headers(a["token"]))
    if r.status_code != 200:
        log("balance-details (A)", False, f"{r.status_code} {r.text}")
    else:
        body = r.json()
        bd = body.get("breakdown", [])
        a_own = [x for x in bd if x["direction"] == "they_owe_you"]
        a_other = [x for x in bd if x["direction"] == "you_owe_them"]
        ok = (len(bd) == 3 and len(a_own) == 2 and len(a_other) == 1
              and "settlements" in body and isinstance(body["settlements"], list))
        # Verify share_each math for one entry
        ent = bd[0]
        expected_share = round(ent["price"] / ent["split_count"], 2)
        share_ok = abs(ent["share_each"] - expected_share) < 0.001
        log("balance-details (A) breakdown counts", ok,
            f"total={len(bd)} they_owe_you={len(a_own)} you_owe_them={len(a_other)}")
        log("balance-details share_each math", share_ok,
            f"price={ent['price']} split={ent['split_count']} share_each={ent['share_each']}")
        log("balance-details settlements present", "settlements" in body and isinstance(body["settlements"], list))

    # As B: mirror — should see 1 they_owe_you (B's own) + 2 you_owe_them (A's)
    r = requests.get(f"{BASE_URL}/balance-details?space_id={space_id}&with_user_id={a_id}",
                     headers=auth_headers(b["token"]))
    if r.status_code != 200:
        log("balance-details (B)", False, f"{r.status_code} {r.text}")
    else:
        body = r.json()
        bd = body.get("breakdown", [])
        b_own = [x for x in bd if x["direction"] == "they_owe_you"]
        b_other = [x for x in bd if x["direction"] == "you_owe_them"]
        log("balance-details (B) mirror",
            len(bd) == 3 and len(b_own) == 1 and len(b_other) == 2,
            f"total={len(bd)} they_owe_you={len(b_own)} you_owe_them={len(b_other)}")

    # === 6. /balances regression ===
    r = requests.get(f"{BASE_URL}/balances?space_id={space_id}", headers=auth_headers(a["token"]))
    if r.status_code != 200:
        log("balances regression", False, f"{r.status_code} {r.text}")
    else:
        bal = r.json()
        # A paid 24.50+60 = 84.50, share each 42.25; B paid 18.00, share each 9.00
        # B owes A 42.25, A owes B 9.00 → net B owes A 33.25
        owed_to_a = bal.get("total_owed_to_you", 0)
        log("balances net math (A perspective)", abs(owed_to_a - 33.25) < 0.05,
            f"owed_to_you={owed_to_a} (expected 33.25)")

    # === 7. Settlements regression ===
    r = requests.post(f"{BASE_URL}/settlements",
                      json={"space_id": space_id, "to_user_id": a_id, "amount": 5.00, "note": "venmo"},
                      headers=auth_headers(b["token"]))
    if r.status_code != 200:
        log("settlements/create", False, f"{r.status_code} {r.text}")
    else:
        settlement_id = r.json()["settlement_id"]
        log("settlements/create", True, f"id={settlement_id}")

        r = requests.get(f"{BASE_URL}/settlements?space_id={space_id}", headers=auth_headers(a["token"]))
        log("settlements/list", r.status_code == 200 and any(s["settlement_id"] == settlement_id for s in r.json()),
            f"status={r.status_code}")

        # balance-details should now show this settlement
        r = requests.get(f"{BASE_URL}/balance-details?space_id={space_id}&with_user_id={b_id}",
                         headers=auth_headers(a["token"]))
        log("balance-details settlements populated",
            r.status_code == 200 and len(r.json().get("settlements", [])) >= 1,
            f"settlements={len(r.json().get('settlements', [])) if r.status_code == 200 else 'err'}")

    # === 8. Recurring Bills ===
    bill_payload = {
        "space_id": space_id,
        "name": "Wi-Fi",
        "amount": 100.00,
        "frequency": "monthly",
        "due_day": 15,
        "category_id": shared_cat_id,
        "shared_with": [a_id, b_id],
        "icon": "Wifi",
    }
    r = requests.post(f"{BASE_URL}/bills", json=bill_payload, headers=auth_headers(a["token"]))
    if r.status_code != 200:
        log("bills/create", False, f"{r.status_code} {r.text}")
        return
    bill = r.json()
    bill_id = bill["bill_id"]
    log("bills/create monthly",
        bill.get("next_due_date") is not None and bill.get("is_paid_current_period") is False,
        f"next_due={bill.get('next_due_date')} is_paid={bill.get('is_paid_current_period')}")

    # GET /bills
    r = requests.get(f"{BASE_URL}/bills?space_id={space_id}", headers=auth_headers(b["token"]))
    log("bills/list (B sees A's bill)",
        r.status_code == 200 and any(x["bill_id"] == bill_id for x in r.json()),
        f"status={r.status_code}")

    # PATCH /bills/{id}
    r = requests.patch(f"{BASE_URL}/bills/{bill_id}",
                       json={"name": "Wi-Fi (Comcast)", "amount": 110.00},
                       headers=auth_headers(a["token"]))
    log("bills/update",
        r.status_code == 200 and r.json()["name"] == "Wi-Fi (Comcast)" and abs(r.json()["amount"] - 110.0) < 0.01,
        f"status={r.status_code}")

    # POST /bills/{id}/pay
    r = requests.post(f"{BASE_URL}/bills/{bill_id}/pay", headers=auth_headers(a["token"]))
    if r.status_code != 200:
        log("bills/pay", False, f"{r.status_code} {r.text}")
    else:
        paid = r.json()
        from datetime import date
        today_iso = date.today().isoformat()
        log("bills/pay flips state",
            paid.get("is_paid_current_period") is True and paid.get("last_paid_date") == today_iso,
            f"is_paid={paid.get('is_paid_current_period')} last_paid={paid.get('last_paid_date')}")

        # Verify item was created in category
        r = requests.get(f"{BASE_URL}/items?space_id={space_id}&category_id={shared_cat_id}",
                         headers=auth_headers(a["token"]))
        if r.status_code == 200:
            items_in_cat = r.json()
            wifi_items = [it for it in items_in_cat if "Wi-Fi" in it["name"] and abs((it.get("price") or 0) - 110.0) < 0.01]
            log("bills/pay creates item in category",
                len(wifi_items) >= 1,
                f"matching items={len(wifi_items)}")
        else:
            log("bills/pay creates item in category", False, f"items list status={r.status_code}")

        # Verify balance-details now includes the bill payment item
        r = requests.get(f"{BASE_URL}/balance-details?space_id={space_id}&with_user_id={b_id}",
                         headers=auth_headers(a["token"]))
        if r.status_code == 200:
            bd = r.json()["breakdown"]
            wifi_in_bd = any("Wi-Fi" in x["name"] for x in bd)
            log("bills/pay shows in balance-details", wifi_in_bd,
                f"breakdown_size={len(bd)}")
        else:
            log("bills/pay shows in balance-details", False, f"status={r.status_code}")

    # DELETE /bills/{id}
    r = requests.delete(f"{BASE_URL}/bills/{bill_id}", headers=auth_headers(a["token"]))
    log("bills/delete", r.status_code == 200, f"status={r.status_code}")

    r = requests.get(f"{BASE_URL}/bills?space_id={space_id}", headers=auth_headers(a["token"]))
    log("bills deletion removes from list",
        r.status_code == 200 and not any(x["bill_id"] == bill_id for x in r.json()))

    # Items should still be present
    r = requests.get(f"{BASE_URL}/items?space_id={space_id}&category_id={shared_cat_id}",
                     headers=auth_headers(a["token"]))
    if r.status_code == 200:
        items_in_cat = r.json()
        wifi_items = [it for it in items_in_cat if "Wi-Fi" in it["name"]]
        log("bills/delete keeps historical items", len(wifi_items) >= 1, f"wifi items still present={len(wifi_items)}")

    # === 9. Roommate Agreement ===
    # GET when none exists -> null
    # First make sure no agreement exists for a fresh space — create another space for clean test.
    r = requests.post(f"{BASE_URL}/spaces", json={"name": "Agreement Test House"}, headers=auth_headers(a["token"]))
    ag_space_id = r.json()["space_id"]
    ag_invite = r.json()["invite_code"]
    requests.post(f"{BASE_URL}/spaces/join", json={"invite_code": ag_invite}, headers=auth_headers(b["token"]))

    r = requests.get(f"{BASE_URL}/agreement?space_id={ag_space_id}", headers=auth_headers(a["token"]))
    log("agreement/get returns null when none exists",
        r.status_code == 200 and r.json() in (None, "null"),
        f"status={r.status_code} body={r.text[:100]}")

    # PUT to create
    r = requests.put(f"{BASE_URL}/agreement?space_id={ag_space_id}",
                     json={"text": "Quiet hours after 10pm. Trash on Tuesdays.", "sections": []},
                     headers=auth_headers(a["token"]))
    if r.status_code != 200:
        log("agreement/put create", False, f"{r.status_code} {r.text}")
    else:
        ag = r.json()
        log("agreement/put create",
            ag.get("text") == "Quiet hours after 10pm. Trash on Tuesdays." and ag.get("signatures") == [],
            f"sigs={len(ag.get('signatures', []))}")

    # POST sign as A
    r = requests.post(f"{BASE_URL}/agreement/sign?space_id={ag_space_id}", headers=auth_headers(a["token"]))
    if r.status_code != 200:
        log("agreement/sign A", False, f"{r.status_code} {r.text}")
    else:
        ag = r.json()
        log("agreement/sign A adds signature",
            len(ag["signatures"]) == 1 and ag["signatures"][0]["user_id"] == a_id,
            f"sigs={ag['signatures']}")

    # Sign again as A → still 1
    time.sleep(1)
    r = requests.post(f"{BASE_URL}/agreement/sign?space_id={ag_space_id}", headers=auth_headers(a["token"]))
    if r.status_code == 200:
        ag = r.json()
        log("agreement/sign A again is dedup'd",
            len(ag["signatures"]) == 1 and ag["signatures"][0]["user_id"] == a_id,
            f"sigs={len(ag['signatures'])}")

    # B signs too → 2 signatures
    r = requests.post(f"{BASE_URL}/agreement/sign?space_id={ag_space_id}", headers=auth_headers(b["token"]))
    if r.status_code == 200:
        log("agreement/sign B added", len(r.json()["signatures"]) == 2,
            f"sigs={len(r.json()['signatures'])}")

    # PUT to edit (B) — signatures must reset
    r = requests.put(f"{BASE_URL}/agreement?space_id={ag_space_id}",
                     json={"text": "EDITED: quiet hours after 11pm.", "sections": []},
                     headers=auth_headers(b["token"]))
    if r.status_code == 200:
        log("agreement edit resets signatures",
            r.json().get("signatures") == [],
            f"sigs={r.json().get('signatures')}")

    # === Access control: C is NOT in space ===
    r = requests.get(f"{BASE_URL}/agreement?space_id={ag_space_id}", headers=auth_headers(c["token"]))
    log("agreement GET 403 for non-member", r.status_code == 403, f"status={r.status_code}")

    r = requests.put(f"{BASE_URL}/agreement?space_id={ag_space_id}",
                     json={"text": "hacked", "sections": []}, headers=auth_headers(c["token"]))
    log("agreement PUT 403 for non-member", r.status_code == 403, f"status={r.status_code}")

    r = requests.post(f"{BASE_URL}/agreement/sign?space_id={ag_space_id}", headers=auth_headers(c["token"]))
    log("agreement/sign 403 for non-member", r.status_code == 403, f"status={r.status_code}")

    # === Summary ===
    print("\n========== SUMMARY ==========")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"PASSED: {passed}/{total}")
    failed = [(n, d) for n, ok, d in results if not ok]
    if failed:
        print("\nFAILED TESTS:")
        for n, d in failed:
            print(f"  - {n}: {d}")
    return passed, total, failed


if __name__ == "__main__":
    main()
