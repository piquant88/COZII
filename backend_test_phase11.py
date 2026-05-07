"""
Phase 11 backend tests — Daily morning digest endpoints.

Endpoints under test:
  - POST /api/inventory/alerts/digest/send?space_id=...
  - PATCH /api/spaces/{space_id}/digest-prefs
  - (sanity) GET /api/inventory/alerts
  - (sanity) POST /api/inventory/alerts/to-shopping
  - (verification) GET /api/notifications?space_id=...

Test plan:
  A. Manual trigger with alerts -> {sent: true} + notification recorded
  B. Manual trigger without alerts -> {sent: false}
  C. Permissions: non-owner member -> 403 ; outsider -> 403
  D. Digest preferences PATCH (toggle, hour clamping, non-owner 403)
  E. Idempotency sanity (manual trigger twice in a row both succeed)
  F. Existing endpoints non-regression: /alerts buckets + /alerts/to-shopping
"""
import json
import os
import sys
import time
import uuid
import requests
from datetime import datetime, timezone, timedelta

BASE_URL = "https://family-wallet-21.preview.emergentagent.com/api"

# Counters
PASSED = 0
FAILED = 0
FAILURES = []


def log(name, ok, info=""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        FAILURES.append(f"{name} :: {info}")
        print(f"  FAIL  {name} :: {info}")


def post(path, token=None, json_body=None, params=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.post(BASE_URL + path, headers=headers, json=json_body, params=params, timeout=30)


def get(path, token=None, params=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.get(BASE_URL + path, headers=headers, params=params, timeout=30)


def patch(path, token=None, json_body=None, params=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.patch(BASE_URL + path, headers=headers, json=json_body, params=params, timeout=30)


def register(name, email, password):
    r = post("/auth/register", json_body={"name": name, "email": email, "password": password})
    if r.status_code == 200:
        return r.json()["token"]
    # Fall back to login
    r2 = post("/auth/login", json_body={"email": email, "password": password})
    if r2.status_code == 200:
        return r2.json()["token"]
    raise RuntimeError(f"register/login failed: {r.status_code} {r.text} / {r2.status_code} {r2.text}")


def main():
    print(f"\nUsing BASE_URL={BASE_URL}\n")

    ts = int(time.time())
    # Three accounts: owner, member (joined), outsider
    owner_email = f"owner_p11_{ts}@cozii.app"
    member_email = f"member_p11_{ts}@cozii.app"
    outsider_email = f"outsider_p11_{ts}@cozii.app"
    pwd = "Test1234!"

    print("== Setup: register owner / member / outsider ==")
    owner_token = register("Riya Sharma", owner_email, pwd)
    member_token = register("Aditya Rao", member_email, pwd)
    outsider_token = register("Pierre Lambert", outsider_email, pwd)
    log("register owner/member/outsider", True)

    # Owner creates a household space
    print("\n== Setup: owner creates household space ==")
    r = post("/spaces", token=owner_token, json_body={
        "name": f"Phase11 Household {ts}",
        "currency": "USD",
        "space_type": "household",
    })
    if r.status_code != 200:
        log("create household space", False, f"{r.status_code} {r.text}")
        return
    space = r.json()
    space_id = space["space_id"]
    invite_code = space["invite_code"]
    log("create household space", True, f"space_id={space_id}")

    # Member joins via invite_code
    print("\n== Setup: member joins via invite_code ==")
    r = post("/spaces/join", token=member_token, json_body={"invite_code": invite_code})
    log("member joins space", r.status_code == 200, f"{r.status_code} {r.text}")

    # ---------------------------------------------------------------
    # Setup alerts: create category + 1 low item + 1 expired item
    # ---------------------------------------------------------------
    print("\n== Setup: create category + items that trigger alerts ==")
    r = post("/categories", token=owner_token, json_body={
        "space_id": space_id,
        "name": "Pantry",
        "icon": "Apple",
        "tint": "mint",
    })
    log("create category", r.status_code == 200, f"{r.status_code} {r.text}")
    cat = r.json()
    cat_id = cat["category_id"]

    # Item 1: low-stock
    r = post("/items", token=owner_token, json_body={
        "space_id": space_id,
        "category_id": cat_id,
        "name": "Basmati Rice",
        "status": "low",
        "quantity": 1,
        "price": 4.99,
    })
    log("create low-stock item", r.status_code == 200, f"{r.status_code} {r.text}")

    # Item 2: expired (expiry_date = today - 1)
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    r = post("/items", token=owner_token, json_body={
        "space_id": space_id,
        "category_id": cat_id,
        "name": "Greek Yogurt",
        "expiry_date": yesterday,
        "quantity": 1,
        "price": 3.50,
    })
    log("create expired item (yesterday)", r.status_code == 200, f"{r.status_code} {r.text}")

    # Sanity: GET /api/inventory/alerts shows the buckets
    print("\n== F. Existing endpoint non-regression: GET /inventory/alerts ==")
    r = get("/inventory/alerts", token=owner_token, params={"space_id": space_id})
    if r.status_code == 200:
        body = r.json()
        keys_ok = all(k in body for k in ("low_stock", "finished", "expiring", "expired", "totals"))
        log("/inventory/alerts has 4-bucket structure", keys_ok, f"keys={list(body.keys())}")
        log("/inventory/alerts low_stock has >=1", len(body.get("low_stock", [])) >= 1)
        log("/inventory/alerts expired has >=1", len(body.get("expired", [])) >= 1)
        totals = body.get("totals", {})
        log("/inventory/alerts totals.all >=2", totals.get("all", 0) >= 2, f"totals={totals}")
    else:
        log("/inventory/alerts 200", False, f"{r.status_code} {r.text}")

    # ---------------------------------------------------------------
    # A. Manual trigger with alerts -> sent: true
    # ---------------------------------------------------------------
    print("\n== A. POST /inventory/alerts/digest/send (with alerts) ==")
    r = post("/inventory/alerts/digest/send", token=owner_token, params={"space_id": space_id})
    if r.status_code != 200:
        log("digest/send returns 200", False, f"{r.status_code} {r.text}")
    else:
        body = r.json()
        log("digest/send sent=true", body.get("sent") is True, f"body={body}")
        log("digest/send has message", isinstance(body.get("message"), str) and len(body["message"]) > 0, f"body={body}")

    # Verify notification was inserted
    print("\n== A. GET /notifications has daily_digest record ==")
    r = get("/notifications", token=owner_token, params={"space_id": space_id})
    if r.status_code != 200:
        log("/notifications 200", False, f"{r.status_code} {r.text}")
    else:
        notes = r.json()
        digest_notes = [n for n in notes if n.get("kind") == "daily_digest"]
        log("notifications has daily_digest entry", len(digest_notes) >= 1, f"notes count={len(notes)}, digest count={len(digest_notes)}")
        if digest_notes:
            n0 = digest_notes[0]
            title = n0.get("title", "")
            body = n0.get("body", "")
            data = n0.get("data") or {}
            # Title pattern: "Good morning! N item(s) need attention"
            log("title starts with 'Good morning!'", title.startswith("Good morning!"), f"title={title!r}")
            log("title mentions 'need attention'", "need attention" in title, f"title={title!r}")
            log("body mentions 'shopping list'", "shopping list" in body.lower(), f"body={body!r}")
            log("data.screen == /shopping-list", data.get("screen") == "/shopping-list", f"data={data}")
            counts = data.get("counts") or {}
            log("data.counts present and is dict", isinstance(counts, dict) and len(counts) > 0, f"counts={counts}")
            log("data.counts.low >= 1", counts.get("low", 0) >= 1, f"counts={counts}")
            log("data.counts.expired >= 1", counts.get("expired", 0) >= 1, f"counts={counts}")

    # ---------------------------------------------------------------
    # E. Idempotency: trigger again — manual endpoint must still send
    # ---------------------------------------------------------------
    print("\n== E. Idempotency: manual trigger second time still sends ==")
    r = post("/inventory/alerts/digest/send", token=owner_token, params={"space_id": space_id})
    if r.status_code == 200:
        body = r.json()
        log("second manual digest still sent=true", body.get("sent") is True, f"body={body}")
    else:
        log("second manual digest 200", False, f"{r.status_code} {r.text}")

    # Verify TWO daily_digest notifications now exist
    r = get("/notifications", token=owner_token, params={"space_id": space_id})
    if r.status_code == 200:
        notes = r.json()
        digest_notes = [n for n in notes if n.get("kind") == "daily_digest"]
        log("two daily_digest notifications recorded", len(digest_notes) >= 2, f"count={len(digest_notes)}")

    # ---------------------------------------------------------------
    # C. Permissions: non-owner member -> 403, outsider -> 403
    # ---------------------------------------------------------------
    print("\n== C. Permissions on digest/send ==")
    r = post("/inventory/alerts/digest/send", token=member_token, params={"space_id": space_id})
    log("member (non-owner) digest/send -> 403", r.status_code == 403, f"got {r.status_code} {r.text[:120]}")

    r = post("/inventory/alerts/digest/send", token=outsider_token, params={"space_id": space_id})
    log("outsider digest/send -> 403", r.status_code == 403, f"got {r.status_code} {r.text[:120]}")

    # ---------------------------------------------------------------
    # D. Digest preferences PATCH
    # ---------------------------------------------------------------
    print("\n== D. PATCH /spaces/{id}/digest-prefs ==")

    r = patch(f"/spaces/{space_id}/digest-prefs", token=owner_token, json_body={"daily_digest_enabled": False})
    if r.status_code == 200:
        b = r.json()
        log("PATCH enabled=false returns enabled=false", b.get("daily_digest_enabled") is False, f"body={b}")
    else:
        log("PATCH digest-prefs (enabled=false) 200", False, f"{r.status_code} {r.text}")

    # Re-enable
    r = patch(f"/spaces/{space_id}/digest-prefs", token=owner_token, json_body={"daily_digest_enabled": True})
    if r.status_code == 200:
        b = r.json()
        log("PATCH enabled=true returns enabled=true", b.get("daily_digest_enabled") is True, f"body={b}")

    # Set hour=5
    r = patch(f"/spaces/{space_id}/digest-prefs", token=owner_token, json_body={"daily_digest_utc_hour": 5})
    if r.status_code == 200:
        b = r.json()
        log("PATCH hour=5 returns hour=5", b.get("daily_digest_utc_hour") == 5, f"body={b}")
    else:
        log("PATCH digest-prefs (hour=5) 200", False, f"{r.status_code} {r.text}")

    # Hour=99 -> clamped to 23
    r = patch(f"/spaces/{space_id}/digest-prefs", token=owner_token, json_body={"daily_digest_utc_hour": 99})
    if r.status_code == 200:
        b = r.json()
        log("PATCH hour=99 clamped to 23", b.get("daily_digest_utc_hour") == 23, f"body={b}")

    # Hour=-5 -> clamped to 0
    r = patch(f"/spaces/{space_id}/digest-prefs", token=owner_token, json_body={"daily_digest_utc_hour": -5})
    if r.status_code == 200:
        b = r.json()
        log("PATCH hour=-5 clamped to 0", b.get("daily_digest_utc_hour") == 0, f"body={b}")

    # Non-owner member -> 403
    r = patch(f"/spaces/{space_id}/digest-prefs", token=member_token, json_body={"daily_digest_enabled": False})
    log("member PATCH digest-prefs -> 403", r.status_code == 403, f"got {r.status_code} {r.text[:120]}")

    # Outsider -> 403 (not a member)
    r = patch(f"/spaces/{space_id}/digest-prefs", token=outsider_token, json_body={"daily_digest_enabled": False})
    log("outsider PATCH digest-prefs -> 403", r.status_code == 403, f"got {r.status_code} {r.text[:120]}")

    # ---------------------------------------------------------------
    # B. Manual trigger without alerts -> {sent: false}
    # ---------------------------------------------------------------
    print("\n== B. Empty space: manual trigger -> sent:false ==")
    r = post("/spaces", token=owner_token, json_body={
        "name": f"Phase11 Empty {ts}",
        "currency": "USD",
        "space_type": "household",
    })
    if r.status_code == 200:
        empty_space_id = r.json()["space_id"]
        log("create empty household space", True, f"space_id={empty_space_id}")
        r = post("/inventory/alerts/digest/send", token=owner_token, params={"space_id": empty_space_id})
        if r.status_code == 200:
            b = r.json()
            log("empty space digest/send sent=false", b.get("sent") is False, f"body={b}")
            log("empty space has explicit 'No alerts' message", "no alert" in (b.get("message") or "").lower(), f"body={b}")
        else:
            log("empty space digest/send 200", False, f"{r.status_code} {r.text}")
    else:
        log("create empty household space", False, f"{r.status_code} {r.text}")

    # ---------------------------------------------------------------
    # F. Non-regression: POST /inventory/alerts/to-shopping
    # ---------------------------------------------------------------
    print("\n== F. Non-regression: alerts/to-shopping creates pending shopping requests ==")
    # Get alert items first
    r = get("/inventory/alerts", token=owner_token, params={"space_id": space_id})
    if r.status_code == 200:
        body = r.json()
        item_ids = []
        for bucket in ("low_stock", "expired"):
            for it in body.get(bucket, []):
                item_ids.append(it["item_id"])
        if item_ids:
            r2 = post("/inventory/alerts/to-shopping", token=owner_token, json_body={
                "space_id": space_id,
                "item_ids": item_ids,
                "urgency": "normal",
            })
            if r2.status_code == 200:
                b2 = r2.json()
                created = b2.get("created", 0)
                log("alerts/to-shopping returns created>=1", created >= 1, f"body={b2}")
                log("alerts/to-shopping returns request_ids list", isinstance(b2.get("request_ids"), list), f"body={b2}")
            else:
                log("alerts/to-shopping 200", False, f"{r2.status_code} {r2.text}")

            # Confirm shopping requests are pending
            r3 = get("/household/shopping", token=owner_token, params={"space_id": space_id, "status": "pending"})
            if r3.status_code == 200:
                pending = r3.json()
                log("at least one pending shopping request", len(pending) >= 1, f"count={len(pending)}")
        else:
            log("got item_ids from alerts", False, "no items returned")

    # Summary
    print(f"\n========================================")
    print(f"PASSED: {PASSED}")
    print(f"FAILED: {FAILED}")
    if FAILURES:
        print("\nFailures:")
        for f in FAILURES:
            print(f"  - {f}")
    print(f"========================================\n")
    sys.exit(0 if FAILED == 0 else 1)


if __name__ == "__main__":
    main()
