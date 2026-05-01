"""
Focused retest of:
  1) Space type field on POST/PATCH/GET /api/spaces
  2) Household Staff salary_currency default from space.currency
"""
import os
import sys
import time
import uuid
import json
import requests

BASE = "https://family-wallet-21.preview.emergentagent.com/api"

PRIMARY_EMAIL = "test@cozii.app"
PRIMARY_PASS  = "test1234"

results = []

def ok(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    results.append((mark, name, detail))
    print(f"[{mark}] {name}" + (f" :: {detail}" if detail else ""))
    return cond

def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        return None
    return r.json()["token"]

def register(name, email, password):
    r = requests.post(f"{BASE}/auth/register",
                      json={"name": name, "email": email, "password": password}, timeout=30)
    if r.status_code != 200:
        print(f"  register failed: {r.status_code} {r.text[:120]}")
        return None
    return r.json()["token"]


def main():
    # ---- Auth ----
    tokA = login(PRIMARY_EMAIL, PRIMARY_PASS)
    if not tokA:
        # Try register if not seeded
        tokA = register("Test User", PRIMARY_EMAIL, PRIMARY_PASS)
    if not tokA:
        print("Could not auth primary user; abort")
        sys.exit(1)

    # Second user for non-member PATCH test
    ts = int(time.time())
    emailB = f"riley.chen.{ts}@coziiqa.app"
    tokB = register("Riley Chen", emailB, "Pass_12345")
    if not tokB:
        print("Could not register secondary user; abort")
        sys.exit(1)

    # ---------------------------------------------------------
    # 1) SPACE TYPE FIELD
    # ---------------------------------------------------------
    print("\n=== 1) Space type field ===")

    # 1a) POST /spaces with space_type="household", currency="IDR"
    r = requests.post(f"{BASE}/spaces",
                      headers=headers(tokA),
                      json={"name": f"Jakarta Household {ts}", "space_type": "household", "currency": "IDR"},
                      timeout=30)
    ok("POST /spaces {household, IDR} → 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    household_id = None
    if r.status_code == 200:
        body = r.json()
        ok("  space_type == 'household'", body.get("space_type") == "household", f"got={body.get('space_type')}")
        ok("  currency == 'IDR'", body.get("currency") == "IDR", f"got={body.get('currency')}")
        household_id = body.get("space_id")

    # 1b) POST /spaces with no space_type → defaults to "roommates"
    r = requests.post(f"{BASE}/spaces",
                      headers=headers(tokA),
                      json={"name": f"Default Roommates {ts}"},
                      timeout=30)
    ok("POST /spaces {name only} → 200", r.status_code == 200, f"status={r.status_code}")
    default_roommates_id = None
    if r.status_code == 200:
        body = r.json()
        ok("  space_type defaults to 'roommates'", body.get("space_type") == "roommates", f"got={body.get('space_type')}")
        default_roommates_id = body.get("space_id")

    # 1c) POST with invalid space_type "garbage" → falls back to "roommates"
    r = requests.post(f"{BASE}/spaces",
                      headers=headers(tokA),
                      json={"name": f"Garbage Fallback {ts}", "space_type": "garbage"},
                      timeout=30)
    ok("POST /spaces {space_type:garbage} → 200", r.status_code == 200, f"status={r.status_code}")
    garbage_space_id = None
    if r.status_code == 200:
        body = r.json()
        ok("  invalid space_type falls back to 'roommates'", body.get("space_type") == "roommates",
           f"got={body.get('space_type')}")
        garbage_space_id = body.get("space_id")

    # 1d) PATCH /spaces/{id} with {space_type: "HOUSEHOLD"} → normalises to "household"
    if default_roommates_id:
        r = requests.patch(f"{BASE}/spaces/{default_roommates_id}",
                           headers=headers(tokA),
                           json={"space_type": "HOUSEHOLD"},
                           timeout=30)
        ok("PATCH /spaces {HOUSEHOLD} → 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
        if r.status_code == 200:
            body = r.json()
            ok("  normalised to 'household'", body.get("space_type") == "household",
               f"got={body.get('space_type')}")

    # 1e) PATCH with invalid space_type "foo" → unchanged (should stay 'household' from 1d)
    if default_roommates_id:
        r = requests.patch(f"{BASE}/spaces/{default_roommates_id}",
                           headers=headers(tokA),
                           json={"space_type": "foo"},
                           timeout=30)
        ok("PATCH /spaces {foo} → 200", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            body = r.json()
            ok("  invalid space_type leaves prior value unchanged (household)",
               body.get("space_type") == "household", f"got={body.get('space_type')}")

    # 1f) GET /spaces → every entry contains space_type (existing rows should be "roommates" default)
    r = requests.get(f"{BASE}/spaces", headers=headers(tokA), timeout=30)
    ok("GET /spaces → 200", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        docs = r.json()
        ok("  at least one space returned", len(docs) >= 1, f"count={len(docs)}")
        all_have = all("space_type" in d and d["space_type"] for d in docs)
        ok("  every entry has space_type field set", all_have,
           detail=f"entries={[(d.get('name'), d.get('space_type')) for d in docs]}")
        # Verify household one matches household, garbage one is roommates
        if household_id:
            match = next((d for d in docs if d.get("space_id") == household_id), None)
            ok("  created household space_type='household' in listing",
               match is not None and match.get("space_type") == "household",
               f"entry={match}")
        if garbage_space_id:
            match = next((d for d in docs if d.get("space_id") == garbage_space_id), None)
            ok("  garbage fallback space_type='roommates' in listing",
               match is not None and match.get("space_type") == "roommates",
               f"entry={match}")

    # 1g) Non-member PATCH returns 403
    if household_id:
        r = requests.patch(f"{BASE}/spaces/{household_id}",
                           headers=headers(tokB),
                           json={"space_type": "household"},
                           timeout=30)
        ok("Non-member PATCH /spaces → 403", r.status_code == 403, f"status={r.status_code} body={r.text[:160]}")

    # ---------------------------------------------------------
    # 2) HOUSEHOLD STAFF salary_currency default
    # ---------------------------------------------------------
    print("\n=== 2) Household staff salary_currency default ===")

    # 2a) Create a USD space fresh to isolate
    r = requests.post(f"{BASE}/spaces", headers=headers(tokA),
                      json={"name": f"Staff USD {ts}", "currency": "USD", "space_type": "household"}, timeout=30)
    ok("POST /spaces {USD} for staff test → 200", r.status_code == 200, f"status={r.status_code}")
    usd_space_id = r.json().get("space_id") if r.status_code == 200 else None

    # 2b) Create IDR space (already have household_id with IDR above, reuse)
    idr_space_id = household_id

    # 2c) POST /household/staff into USD space without salary_currency
    if usd_space_id:
        payload = {
            "space_id": usd_space_id,
            "name": "Ana Garcia",
            "salary": 2500,
            "pay_cycle": "monthly",
            "off_day": "Sunday",
        }
        r = requests.post(f"{BASE}/household/staff", headers=headers(tokA), json=payload, timeout=30)
        ok("POST /household/staff (USD space, no salary_currency) → 200",
           r.status_code == 200, f"status={r.status_code} body={r.text[:220]}")
        if r.status_code == 200:
            body = r.json()
            ok("  salary_currency defaults to space currency 'USD'",
               body.get("salary_currency") == "USD", f"got={body.get('salary_currency')}")

    # 2d) POST /household/staff into IDR space without salary_currency
    if idr_space_id:
        payload = {
            "space_id": idr_space_id,
            "name": "Siti Pertiwi",
            "salary": 4000000,
            "pay_cycle": "monthly",
            "off_day": "Friday",
        }
        r = requests.post(f"{BASE}/household/staff", headers=headers(tokA), json=payload, timeout=30)
        ok("POST /household/staff (IDR space, no salary_currency) → 200",
           r.status_code == 200, f"status={r.status_code} body={r.text[:220]}")
        if r.status_code == 200:
            body = r.json()
            ok("  salary_currency defaults to space currency 'IDR'",
               body.get("salary_currency") == "IDR", f"got={body.get('salary_currency')}")

    # 2e) POST /household/staff with explicit salary_currency='EUR' → returns 'EUR'
    if idr_space_id:
        payload = {
            "space_id": idr_space_id,
            "name": "Pierre Lambert",
            "salary": 1800,
            "pay_cycle": "monthly",
            "salary_currency": "EUR",
        }
        r = requests.post(f"{BASE}/household/staff", headers=headers(tokA), json=payload, timeout=30)
        ok("POST /household/staff (explicit EUR) → 200",
           r.status_code == 200, f"status={r.status_code} body={r.text[:220]}")
        if r.status_code == 200:
            body = r.json()
            ok("  explicit salary_currency 'EUR' wins over space currency",
               body.get("salary_currency") == "EUR", f"got={body.get('salary_currency')}")

    # ---- summary ----
    print("\n=== SUMMARY ===")
    fails = [r for r in results if r[0] == "FAIL"]
    passes = [r for r in results if r[0] == "PASS"]
    print(f"Passed: {len(passes)} | Failed: {len(fails)}")
    if fails:
        print("\nFAILURES:")
        for _, name, detail in fails:
            print(f" - {name} :: {detail}")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
