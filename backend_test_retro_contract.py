"""
Backend test for retroactive contract notifications on POST /api/household/staff/join

Verifies that when a staff user joins via invite_code, the backend creates
contract_assigned notifications for any pending contracts that were assigned
to the staff record before the user was linked.
"""
import os
import sys
import time
import requests
from typing import Any, Dict, List, Optional


BASE_URL = "https://family-wallet-21.preview.emergentagent.com/api"


def _post(path: str, token: Optional[str] = None, **kwargs):
    h = kwargs.pop("headers", {}) or {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.post(f"{BASE_URL}{path}", headers=h, timeout=30, **kwargs)


def _get(path: str, token: Optional[str] = None, **kwargs):
    h = kwargs.pop("headers", {}) or {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return requests.get(f"{BASE_URL}{path}", headers=h, timeout=30, **kwargs)


def _register(email: str, password: str, name: str) -> str:
    r = _post("/auth/register", json={"email": email, "password": password, "name": name})
    assert r.status_code == 200, f"register {email} failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("token") or j.get("access_token")


def main() -> int:
    ts = int(time.time())
    owner_email = f"owner_retro_{ts}@cozii.app"
    staff_email = f"staff_retro_{ts}@cozii.app"
    extra_email = f"extra_retro_{ts}@cozii.app"
    pw = "Retro1234!"

    fails: List[str] = []
    passes: List[str] = []

    def ok(msg: str):
        passes.append(msg)
        print(f"PASS  {msg}")

    def bad(msg: str):
        fails.append(msg)
        print(f"FAIL  {msg}")

    # 1. Register owner A
    a_token = _register(owner_email, pw, "Owner Retro")
    ok(f"Registered owner A {owner_email}")

    # Create household space
    r = _post("/spaces", a_token, json={"name": "Retro Household", "space_type": "household", "currency": "USD"})
    if r.status_code != 200:
        bad(f"Create space failed: {r.status_code} {r.text}")
        return 1
    space = r.json()
    space_id = space["space_id"]
    ok(f"Created household space {space_id}")

    # 2. Create staff
    r = _post(
        "/household/staff",
        a_token,
        json={
            "space_id": space_id,
            "name": "RetroStaff",
            "salary": 1000000,
            "pay_cycle": "monthly",
        },
    )
    if r.status_code != 200:
        bad(f"Create staff failed: {r.status_code} {r.text}")
        return 1
    staff = r.json()
    staff_id = staff["staff_id"]
    invite_code = staff.get("invite_code")
    if not invite_code:
        bad("Staff response missing invite_code")
        return 1
    if staff.get("user_id") not in (None, ""):
        bad(f"New staff already has user_id linked: {staff.get('user_id')}")
    else:
        ok("Newly-created staff has user_id=null")
    ok(f"Created staff {staff_id} with invite_code={invite_code}")

    # 3. Create the retro NDA contract assigned to staff while user_id is null
    retro_body_text = (
        "This Confidentiality Agreement is entered between {{owner_name}} and {{staff_name}}.\n"
        "Confidential information shall not be disclosed to third parties."
    )
    r = _post(
        "/contracts",
        a_token,
        json={
            "space_id": space_id,
            "template_kind": "confidentiality",
            "title": "Retro test NDA",
            "body": retro_body_text,
            "assigned_staff_id": staff_id,
            "require_drawn_signature_staff": False,
        },
    )
    if r.status_code != 200:
        bad(f"Create retro NDA failed: {r.status_code} {r.text}")
        return 1
    retro_contract = r.json()
    retro_contract_id = retro_contract["contract_id"]
    ok(f"Created retro contract {retro_contract_id}")

    # 4. Sanity check: register a 3rd throwaway user and confirm that user has no
    # contract_assigned notification
    extra_token = _register(extra_email, pw, "Extra Retro")
    r = _get("/notifications", extra_token, params={"unread_only": "true"})
    if r.status_code == 200:
        nots = r.json()
        ca = [n for n in nots if n.get("kind") == "contract_assigned" and (n.get("data") or {}).get("contract_id") == retro_contract_id]
        if not ca:
            ok("Throwaway user sees no contract_assigned for retro contract")
        else:
            bad(f"Throwaway user unexpectedly sees retro contract notification: {ca}")
    else:
        bad(f"GET notifications for extra failed: {r.status_code} {r.text}")

    # 5. Register staff user B
    b_token = _register(staff_email, pw, "Staff Retro")
    ok(f"Registered staff user B {staff_email}")

    # Confirm B has no retro notification yet (defensive)
    r = _get("/notifications", b_token, params={"space_id": space_id, "unread_only": "true"})
    if r.status_code == 200:
        nots = r.json()
        if not any(n.get("kind") == "contract_assigned" for n in nots):
            ok("B has no contract_assigned notifications before join (expected)")
        else:
            bad(f"B already has contract_assigned notifications BEFORE join: {nots}")
    else:
        # Note: GET /notifications without space_id may behave differently; OK if 200/4xx
        print(f"note: pre-join GET /notifications returned {r.status_code}")

    # 6. As B: join via invite_code
    r = _post("/household/staff/join", b_token, json={"invite_code": invite_code})
    if r.status_code != 200:
        bad(f"Staff join failed: {r.status_code} {r.text}")
        return 1
    j = r.json()
    if not j.get("ok"):
        bad(f"Join response missing ok=true: {j}")
    if j.get("space_id") != space_id:
        bad(f"Join response space_id mismatch: got {j.get('space_id')} expected {space_id}")
    if j.get("staff_id") != staff_id:
        bad(f"Join response staff_id mismatch: got {j.get('staff_id')} expected {staff_id}")
    ok("Staff join returned 200 with correct ok/space_id/staff_id")

    # 7. As B: GET /notifications?space_id=...&unread_only=true
    r = _get("/notifications", b_token, params={"space_id": space_id, "unread_only": "true"})
    if r.status_code != 200:
        bad(f"GET notifications after join failed: {r.status_code} {r.text}")
        return 1
    nots = r.json()
    retro_notifs = [
        n for n in nots
        if n.get("kind") == "contract_assigned"
        and (n.get("data") or {}).get("contract_id") == retro_contract_id
    ]
    if len(retro_notifs) != 1:
        bad(f"Expected exactly 1 retro contract_assigned notification, got {len(retro_notifs)}: {retro_notifs}")
    else:
        n = retro_notifs[0]
        if "Retro test NDA" not in (n.get("title") or ""):
            bad(f"Retro notification title does not contain 'Retro test NDA': {n.get('title')}")
        else:
            ok(f"Retro notification title contains 'Retro test NDA': {n.get('title')}")
        if n.get("read") is not False:
            bad(f"Retro notification read flag is not False: {n.get('read')}")
        else:
            ok("Retro notification read=false")
        ok("B received retroactive contract_assigned notification for Retro NDA")

    # 8. Idempotency: call join again with same invite_code as B
    r = _post("/household/staff/join", b_token, json={"invite_code": invite_code})
    if r.status_code != 200:
        bad(f"Second join failed: {r.status_code} {r.text}")
    else:
        ok("Second join returned 200 (same user, same code)")
    # Re-fetch notifications (this time include read ones too) to count contract_assigned for retro
    r = _get("/notifications", b_token, params={"space_id": space_id})
    if r.status_code != 200:
        bad(f"GET notifications (all) after second join failed: {r.status_code} {r.text}")
        return 1
    all_nots = r.json()
    retro_count = sum(
        1 for n in all_nots
        if n.get("kind") == "contract_assigned"
        and (n.get("data") or {}).get("contract_id") == retro_contract_id
    )
    if retro_count != 1:
        bad(f"Idempotency: expected 1 retro contract_assigned, got {retro_count}")
    else:
        ok("Idempotency: retro contract_assigned count is still 1 after second join")

    # 9. Create a SECOND contract assigned to the same staff (now linked)
    r = _post(
        "/contracts",
        a_token,
        json={
            "space_id": space_id,
            "template_kind": "nda",
            "title": "Post-join contract",
            "body": "This is a post-join NDA between owner and staff.",
            "assigned_staff_id": staff_id,
        },
    )
    if r.status_code != 200:
        bad(f"Create post-join contract failed: {r.status_code} {r.text}")
        return 1
    post_contract = r.json()
    post_contract_id = post_contract["contract_id"]
    ok(f"Created post-join contract {post_contract_id}")

    # GET notifications: should now have 2 contract_assigned, one for retro, one for post-join
    r = _get("/notifications", b_token, params={"space_id": space_id})
    if r.status_code != 200:
        bad(f"GET notifications after post-join contract failed: {r.status_code} {r.text}")
        return 1
    all_nots = r.json()
    contract_assigned = [n for n in all_nots if n.get("kind") == "contract_assigned"]
    contract_ids = [(n.get("data") or {}).get("contract_id") for n in contract_assigned]
    if retro_contract_id in contract_ids and post_contract_id in contract_ids:
        ok("B has both retro and post-join contract_assigned notifications")
    else:
        bad(f"Missing notifications. Have contract_ids={contract_ids}, expected both {retro_contract_id} and {post_contract_id}")

    # 10. Voided contracts NOT backfilled
    # Need a SECOND staff record (so we can have an unlinked staff that the new user joins).
    r = _post(
        "/household/staff",
        a_token,
        json={
            "space_id": space_id,
            "name": "RetroStaff2",
            "salary": 500000,
            "pay_cycle": "monthly",
        },
    )
    if r.status_code != 200:
        bad(f"Create 2nd staff failed: {r.status_code} {r.text}")
        return 1
    staff2 = r.json()
    staff2_id = staff2["staff_id"]
    staff2_invite = staff2["invite_code"]
    ok(f"Created 2nd staff {staff2_id} with invite_code={staff2_invite}")

    # Create a contract assigned to the unlinked 2nd staff
    r = _post(
        "/contracts",
        a_token,
        json={
            "space_id": space_id,
            "template_kind": "blank",
            "title": "Voided contract",
            "body": "This contract will be voided before staff joins.",
            "assigned_staff_id": staff2_id,
        },
    )
    if r.status_code != 200:
        bad(f"Create void-target contract failed: {r.status_code} {r.text}")
        return 1
    void_target = r.json()
    void_contract_id = void_target["contract_id"]
    ok(f"Created contract {void_contract_id} on unlinked staff2")

    # Void it
    r = _post(f"/contracts/{void_contract_id}/void", a_token)
    if r.status_code != 200:
        bad(f"Void contract failed: {r.status_code} {r.text}")
        return 1
    voided = r.json()
    if voided.get("status") != "void":
        bad(f"Voided contract status not 'void': {voided.get('status')}")
    else:
        ok("Contract voided successfully")

    # Register a new staff user C and join with the 2nd invite code
    c_email = f"staff_retro_c_{ts}@cozii.app"
    c_token = _register(c_email, pw, "Staff Retro C")
    r = _post("/household/staff/join", c_token, json={"invite_code": staff2_invite})
    if r.status_code != 200:
        bad(f"Staff2 user join failed: {r.status_code} {r.text}")
        return 1
    ok("Staff2 user C joined via 2nd invite_code")

    # Check C has NO contract_assigned for the voided contract
    r = _get("/notifications", c_token, params={"space_id": space_id})
    if r.status_code != 200:
        bad(f"C GET notifications failed: {r.status_code} {r.text}")
        return 1
    c_nots = r.json()
    c_void = [
        n for n in c_nots
        if n.get("kind") == "contract_assigned"
        and (n.get("data") or {}).get("contract_id") == void_contract_id
    ]
    if c_void:
        bad(f"C unexpectedly received notification for voided contract: {c_void}")
    else:
        ok("C has NO contract_assigned for the voided contract (expected)")

    # ----- Summary -----
    print()
    print("===== SUMMARY =====")
    print(f"PASS: {len(passes)}")
    print(f"FAIL: {len(fails)}")
    if fails:
        for f in fails:
            print(f"  - {f}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
