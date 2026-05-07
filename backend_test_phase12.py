"""
Phase 12 — Push Notifications & Notification Preferences backend test.

Tests:
  1. POST   /api/users/push-token
  2. DELETE /api/users/push-token
  3. GET    /api/users/notification-prefs
  4. PUT    /api/users/notification-prefs
  5. POST   /api/users/push-test
  6. Auth gating on all 5 endpoints
  7. Regression: POST /api/contracts (notify_user) → notification recorded,
     non-blocking, original endpoint returns 200.
  8. Regression: POST /api/inventory/alerts/digest/send returns 200 (no 500).

Credentials from /app/memory/test_credentials.md: test@cozii.app / test1234
"""

import os
import time
import json
import uuid
import requests

BASE = os.environ.get("COZII_BASE_URL", "http://localhost:8001")
EMAIL = "test@cozii.app"
PASSWORD = "test1234"
HOUSEHOLD_SPACE_ID = "space_8784d76aee6d4c56"   # Test Household
ASSIGNED_STAFF_ID = "staff_1713154d2be94f30"    # Sari Putri (linked user_id)
ASSIGNED_STAFF_USER = "user_62a928563ea543aa"

results = []


def record(name: str, ok: bool, msg: str = ""):
    status = "PASS" if ok else "FAIL"
    results.append((status, name, msg))
    print(f"[{status}] {name}{(' — ' + msg) if msg else ''}")


def login() -> str:
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def auth(t: str) -> dict:
    return {"Authorization": f"Bearer {t}"}


def main():
    token = login()
    h = auth(token)
    print(f"Logged in as {EMAIL}")

    # =========================================================================
    # 0. AUTH GATING — 401 without bearer
    # =========================================================================
    fake_token = "ExponentPushToken[" + uuid.uuid4().hex + "]"
    auth_endpoints = [
        ("POST",   "/api/users/push-token",         {"token": fake_token}),
        ("DELETE", f"/api/users/push-token?token={fake_token}", None),
        ("GET",    "/api/users/notification-prefs", None),
        ("PUT",    "/api/users/notification-prefs", {"daily_digest": True}),
        ("POST",   "/api/users/push-test",          None),
    ]
    for method, path, body in auth_endpoints:
        r = requests.request(method, BASE + path, json=body, timeout=10)
        record(
            f"AUTH GATE {method} {path.split('?')[0]}",
            r.status_code in (401, 403),
            f"got {r.status_code}",
        )

    # =========================================================================
    # 1. POST /api/users/push-token (register fake token)
    # =========================================================================
    fake = f"ExponentPushToken[FAKE-{uuid.uuid4().hex[:12]}]"
    r = requests.post(
        f"{BASE}/api/users/push-token",
        json={"token": fake, "platform": "ios", "device_name": "Pytest device"},
        headers=h,
        timeout=10,
    )
    record(
        "POST /api/users/push-token register",
        r.status_code == 200 and r.json().get("ok") is True,
        f"status={r.status_code} body={r.text[:200]}",
    )

    # 1b. Repeat upsert (same token) → still ok=true, no duplicate
    r = requests.post(
        f"{BASE}/api/users/push-token",
        json={"token": fake, "platform": "ios", "device_name": "Pytest device renamed"},
        headers=h,
        timeout=10,
    )
    record(
        "POST /api/users/push-token upsert (same token)",
        r.status_code == 200 and r.json().get("ok") is True,
        f"status={r.status_code}",
    )

    # =========================================================================
    # 5. POST /api/users/push-test WITH a token registered
    #    (Expo will reject the fake token but the call itself must not 500.)
    # =========================================================================
    r = requests.post(f"{BASE}/api/users/push-test", headers=h, timeout=20)
    body_test_with_tok = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    record(
        "POST /api/users/push-test (with fake token registered)",
        r.status_code == 200 and "sent" in body_test_with_tok,
        f"status={r.status_code} body={body_test_with_tok}",
    )

    # =========================================================================
    # 2. DELETE /api/users/push-token?token=...
    # =========================================================================
    r = requests.delete(
        f"{BASE}/api/users/push-token",
        params={"token": fake},
        headers=h,
        timeout=10,
    )
    body = r.json() if r.status_code == 200 else {}
    record(
        "DELETE /api/users/push-token (existing)",
        r.status_code == 200 and body.get("ok") is True and body.get("matched", -1) >= 1,
        f"status={r.status_code} body={body}",
    )

    # 2b. Idempotent: DELETE again on same token → still 200, matched_count may be 0
    r = requests.delete(
        f"{BASE}/api/users/push-token",
        params={"token": fake},
        headers=h,
        timeout=10,
    )
    body = r.json() if r.status_code == 200 else {}
    # Note: even if matched_count is >0 here (because the doc still exists, just
    # already inactive), it should still be 200 and ok=true.
    record(
        "DELETE /api/users/push-token (idempotent)",
        r.status_code == 200 and body.get("ok") is True,
        f"status={r.status_code} body={body}",
    )

    # 2c. DELETE for an unknown token → still 200, matched=0 (idempotent)
    r = requests.delete(
        f"{BASE}/api/users/push-token",
        params={"token": "ExponentPushToken[never-registered-xxx]"},
        headers=h,
        timeout=10,
    )
    body = r.json() if r.status_code == 200 else {}
    record(
        "DELETE /api/users/push-token (unknown token, idempotent)",
        r.status_code == 200 and body.get("ok") is True and body.get("matched", -1) == 0,
        f"status={r.status_code} body={body}",
    )

    # =========================================================================
    # 5b. POST /api/users/push-test WITH NO active tokens → sent=false, no 500
    # =========================================================================
    r = requests.post(f"{BASE}/api/users/push-test", headers=h, timeout=20)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    record(
        "POST /api/users/push-test (no active tokens) returns sent=false",
        r.status_code == 200 and body.get("sent") is False,
        f"status={r.status_code} body={body}",
    )

    # =========================================================================
    # 3. GET /api/users/notification-prefs (defaults)
    # =========================================================================
    # Reset to defaults first (so this run is deterministic across reruns)
    requests.put(
        f"{BASE}/api/users/notification-prefs",
        json={"daily_digest": True, "important_alerts": True},
        headers=h,
        timeout=10,
    )
    r = requests.get(f"{BASE}/api/users/notification-prefs", headers=h, timeout=10)
    body = r.json() if r.status_code == 200 else {}
    record(
        "GET /api/users/notification-prefs returns defaults",
        r.status_code == 200
        and body.get("daily_digest") is True
        and body.get("important_alerts") is True,
        f"status={r.status_code} body={body}",
    )

    # =========================================================================
    # 4. PUT /api/users/notification-prefs partial update
    # =========================================================================
    # 4a. Disable only daily_digest, leave important_alerts alone.
    r = requests.put(
        f"{BASE}/api/users/notification-prefs",
        json={"daily_digest": False},
        headers=h,
        timeout=10,
    )
    body = r.json() if r.status_code == 200 else {}
    record(
        "PUT /api/users/notification-prefs partial (daily_digest=false)",
        r.status_code == 200
        and body.get("daily_digest") is False
        and body.get("important_alerts") is True,
        f"status={r.status_code} body={body}",
    )

    # 4b. GET again — make sure it persisted.
    r = requests.get(f"{BASE}/api/users/notification-prefs", headers=h, timeout=10)
    body = r.json()
    record(
        "GET /api/users/notification-prefs after PUT persisted",
        body.get("daily_digest") is False and body.get("important_alerts") is True,
        f"body={body}",
    )

    # 4c. PUT empty body — nothing should change.
    r = requests.put(
        f"{BASE}/api/users/notification-prefs",
        json={},
        headers=h,
        timeout=10,
    )
    body = r.json()
    record(
        "PUT /api/users/notification-prefs empty body keeps prior values",
        r.status_code == 200
        and body.get("daily_digest") is False
        and body.get("important_alerts") is True,
        f"body={body}",
    )

    # 4d. PUT important_alerts only → daily_digest unchanged (still false).
    r = requests.put(
        f"{BASE}/api/users/notification-prefs",
        json={"important_alerts": False},
        headers=h,
        timeout=10,
    )
    body = r.json()
    record(
        "PUT /api/users/notification-prefs partial (important_alerts=false)",
        r.status_code == 200
        and body.get("daily_digest") is False
        and body.get("important_alerts") is False,
        f"body={body}",
    )

    # 4e. Restore both to true so we don't pollute future test runs / push-test.
    r = requests.put(
        f"{BASE}/api/users/notification-prefs",
        json={"daily_digest": True, "important_alerts": True},
        headers=h,
        timeout=10,
    )
    body = r.json()
    record(
        "PUT /api/users/notification-prefs restore both true",
        body.get("daily_digest") is True and body.get("important_alerts") is True,
        f"body={body}",
    )

    # =========================================================================
    # 6. REGRESSION — POST /api/contracts triggers notify_user; must:
    #     - return 200 promptly (push is fire-and-forget)
    #     - insert a notification row for the assigned staff user
    # =========================================================================
    # Snapshot existing notifications for the staff user (we'll log in as them
    # since we already have invite_code on file? No, simpler: use the household
    # owner's GET /api/notifications?space_id=... — but notifications are
    # per-user. The notification we care about is for the staff user, but we
    # can check via Mongo? We don't want to touch Mongo here. Easier route:
    # the contract creation inserts a notification for the linked staff
    # user (user_62a928563ea543aa). Since we are the owner we cannot read
    # their notifications. Instead, we'll use the staff user account by
    # logging in via their invite — but they are already a space member, so
    # we need their email/password.
    #
    # Workaround: register a brand-new user, link them as a staff via invite
    # code (already-linked staff_1713154d2be94f30 has user_id, can't reuse).
    # Easier: just verify (a) contract creation returns 200, (b) /notifications
    # for the OWNER will include "contract_created" if applicable, and (c)
    # the request completes promptly (<5s).
    #
    # Actually, looking at server.py, the contract endpoint only notifies the
    # ASSIGNED STAFF user, not the owner. So we'll instead create an extra
    # user that is a staff with a linked user_id, and use them. The Sari
    # Putri staff member already has user_id=user_62a928563ea543aa — but we
    # don't know that user's password. So instead: register a brand-new
    # account via /api/auth/register, join the household via invite code, and
    # promote them as a staff via POST /household/staff/join with that
    # staff's invite_code. But Sari Putri is already linked. We need a
    # different staff record.
    #
    # Simplest: we'll create the contract, time it, assert 200, and then
    # check the OWNER's /notifications list to see whether *any* notification
    # was created (the owner won't get one for their own contracts) — so the
    # "notification was inserted" check is best done by querying the
    # collection via an ADMIN account... not available.
    #
    # Pragmatic approach taken below:
    #   * Verify POST /contracts returns 200 promptly (<5s).
    #   * Create a NEW user, have them join the household using the staff
    #     "Andi Wibowo" invite code (has user_id=null). After join, post a
    #     contract assigned to them, then login as them and GET /notifications
    #     should include the contract_assigned row.
    # =========================================================================

    new_email = f"phase12+{int(time.time())}@cozii.app"
    new_password = "TestPass123!"
    r = requests.post(
        f"{BASE}/api/auth/register",
        json={"email": new_email, "password": new_password, "name": "Phase12 Tester"},
        timeout=15,
    )
    record(
        "Register helper user",
        r.status_code == 200,
        f"status={r.status_code} body={r.text[:200]}",
    )
    helper_token = r.json()["token"]

    # Look up Andi Wibowo's invite_code (user_id is null per earlier inspection)
    r = requests.get(
        f"{BASE}/api/household/staff",
        params={"space_id": HOUSEHOLD_SPACE_ID},
        headers=h,
        timeout=10,
    )
    staff_list = r.json() if r.status_code == 200 else []
    target_staff = next(
        (s for s in staff_list if not s.get("user_id")),
        None,
    )
    if target_staff is None:
        record("Find unlinked staff", False, f"staff list: {[s.get('name') + '/' + str(s.get('user_id')) for s in staff_list]}")
        return
    record("Find unlinked staff", True, f"name={target_staff['name']} staff_id={target_staff['staff_id']}")
    target_staff_id = target_staff["staff_id"]
    target_invite = target_staff["invite_code"]

    # helper joins as staff
    r = requests.post(
        f"{BASE}/api/household/staff/join",
        json={"invite_code": target_invite},
        headers=auth(helper_token),
        timeout=15,
    )
    record(
        "Helper joins as staff via invite_code",
        r.status_code == 200 and r.json().get("ok") is True,
        f"status={r.status_code} body={r.text[:200]}",
    )

    # Now have OWNER create a contract assigned to that staff. notify_user fires.
    create_body = {
        "space_id": HOUSEHOLD_SPACE_ID,
        "title": f"Phase12 Test Contract {int(time.time())}",
        "body": "This is a test contract created by the Phase 12 push notification regression test.",
        "template_kind": "custom",
        "assigned_staff_id": target_staff_id,
        "require_owner_signature": True,
        "require_staff_signature": True,
    }
    t0 = time.time()
    r = requests.post(f"{BASE}/api/contracts", json=create_body, headers=h, timeout=20)
    elapsed = time.time() - t0
    contract_ok = r.status_code == 200
    contract_id = r.json().get("contract_id") if contract_ok else None
    record(
        "POST /api/contracts (regression: notify_user fires)",
        contract_ok,
        f"status={r.status_code} elapsed={elapsed:.2f}s contract_id={contract_id} body={r.text[:200]}",
    )
    record(
        "POST /api/contracts is non-blocking (push fire-and-forget)",
        elapsed < 5.0,
        f"elapsed={elapsed:.2f}s",
    )

    # Helper user (the assigned staff) should now see the notification
    time.sleep(1)  # tiny grace for the insert
    r = requests.get(
        f"{BASE}/api/notifications",
        params={"space_id": HOUSEHOLD_SPACE_ID},
        headers=auth(helper_token),
        timeout=10,
    )
    notifs = r.json() if r.status_code == 200 else []
    matching = [
        n for n in notifs
        if n.get("kind") == "contract_assigned"
        and (n.get("data") or {}).get("contract_id") == contract_id
    ]
    record(
        "GET /api/notifications shows contract_assigned for helper staff",
        r.status_code == 200 and len(matching) >= 1,
        f"count={len(matching)} total={len(notifs)} (notif kinds: {[n.get('kind') for n in notifs[:5]]})",
    )

    # =========================================================================
    # 7. REGRESSION — /api/inventory/alerts/digest/send must not 500.
    # =========================================================================
    r = requests.post(
        f"{BASE}/api/inventory/alerts/digest/send",
        params={"space_id": HOUSEHOLD_SPACE_ID},
        headers=h,
        timeout=20,
    )
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    record(
        "POST /api/inventory/alerts/digest/send (regression, no 500)",
        r.status_code == 200 and "sent" in body,
        f"status={r.status_code} body={body}",
    )

    # If digest reported sent=true, the OWNER (this test account) should see
    # a daily_digest notification — _send_digest_for_space addresses owner_id.
    if body.get("sent") is True:
        time.sleep(1)
        r2 = requests.get(
            f"{BASE}/api/notifications",
            params={"space_id": HOUSEHOLD_SPACE_ID},
            headers=h,
            timeout=10,
        )
        notifs2 = r2.json() if r2.status_code == 200 else []
        digests = [n for n in notifs2 if n.get("kind") == "daily_digest"]
        record(
            "Daily digest writes a daily_digest notification (owner)",
            len(digests) >= 1,
            f"count={len(digests)}",
        )
    else:
        record(
            "Daily digest reported no alerts (sent=false) — accepted, no 500",
            True,
            f"body={body}",
        )

    # =========================================================================
    # CLEANUP — delete the test contract so re-runs are clean
    # =========================================================================
    if contract_id:
        try:
            requests.delete(
                f"{BASE}/api/contracts/{contract_id}",
                headers=h,
                timeout=10,
            )
        except Exception:
            pass

    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r[0] == "PASS")
    failed = sum(1 for r in results if r[0] == "FAIL")
    print(f"TOTAL {passed + failed}  PASS {passed}  FAIL {failed}")
    if failed:
        print("\nFAILURES:")
        for status, name, msg in results:
            if status == "FAIL":
                print(f"  - {name}: {msg}")
    print("=" * 70)
    return failed


if __name__ == "__main__":
    rc = main()
    raise SystemExit(0 if not rc else 1)
