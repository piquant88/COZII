"""
Phase 7 — Contract Templates + e-Sign tests.

Run: python /app/backend_test_phase7_contracts.py
"""
import os
import sys
import time
import json
import requests

BASE = os.environ.get("BACKEND_URL", "https://family-wallet-21.preview.emergentagent.com").rstrip("/") + "/api"
OWNER_EMAIL = "test@cozii.app"
OWNER_PASSWORD = "test1234"

TS = int(time.time())
STAFF_EMAIL = f"staff_user_{TS}@cozii.app"
OUTSIDER_EMAIL = f"outsider_{TS}@cozii.app"
COMMON_PW = "test1234"

passed: list[str] = []
failed: list[tuple[str, str]] = []


def rec(ok: bool, name: str, detail: str = ""):
    if ok:
        passed.append(name)
        print(f"  PASS  {name}")
    else:
        failed.append((name, detail))
        print(f"  FAIL  {name}  -> {detail}")


def auth_hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def login(email: str, pw: str) -> str:
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def register_or_login(email: str, pw: str, name: str) -> str:
    r = requests.post(f"{BASE}/auth/register", json={"email": email, "password": pw, "name": name}, timeout=30)
    if r.status_code == 200:
        return r.json()["token"]
    # try login
    return login(email, pw)


def main():
    print(f"BASE = {BASE}")
    # --- 1. Logins
    owner_token = login(OWNER_EMAIL, OWNER_PASSWORD)
    staff_token = register_or_login(STAFF_EMAIL, COMMON_PW, "Sari Putri")
    outsider_token = register_or_login(OUTSIDER_EMAIL, COMMON_PW, "Outsider Olivia")
    print(f"owner token: {owner_token[:10]}...")
    print(f"staff token: {staff_token[:10]}...")
    print(f"outsider token: {outsider_token[:10]}...")

    # who am I (need user_id for notifications checks)
    me_owner = requests.get(f"{BASE}/auth/me", headers=auth_hdr(owner_token), timeout=30).json()
    me_staff = requests.get(f"{BASE}/auth/me", headers=auth_hdr(staff_token), timeout=30).json()
    print("owner user_id:", me_owner.get("user_id"))
    print("staff user_id:", me_staff.get("user_id"))

    # --- 2. Create a household space with IDR
    print("\n== Create household space ==")
    r = requests.post(
        f"{BASE}/spaces",
        headers=auth_hdr(owner_token),
        json={"name": f"Rumah Bali {TS}", "space_type": "household", "currency": "IDR"},
        timeout=30,
    )
    rec(r.status_code == 200, "POST /spaces household IDR 200", f"{r.status_code} {r.text[:200]}")
    space = r.json()
    space_id = space["space_id"]
    print("space_id:", space_id)

    # --- 3. Create a staff member
    print("\n== Create staff ==")
    r = requests.post(
        f"{BASE}/household/staff",
        headers=auth_hdr(owner_token),
        json={"space_id": space_id, "name": "Sari Putri", "role_id": None, "salary": 2500000, "pay_cycle": "monthly", "off_day": "Sunday"},
        timeout=30,
    )
    rec(r.status_code == 200, "POST /household/staff 200", f"{r.status_code} {r.text[:300]}")
    staff = r.json()
    staff_id = staff["staff_id"]
    invite_code = staff.get("invite_code")
    print("staff_id:", staff_id, "invite_code:", invite_code)
    rec(bool(invite_code), "invite_code returned", f"got: {invite_code!r}")

    # --- Create a SECOND staff (we'll PATCH contract to this one later)
    r = requests.post(
        f"{BASE}/household/staff",
        headers=auth_hdr(owner_token),
        json={"space_id": space_id, "name": "Bayu Dwi", "role_id": None, "salary": 2000000, "pay_cycle": "monthly", "off_day": "Monday"},
        timeout=30,
    )
    rec(r.status_code == 200, "POST /household/staff #2 200", f"{r.status_code} {r.text[:200]}")
    staff2 = r.json()
    staff2_id = staff2["staff_id"]

    # --- 4. Link staff user via /staff/join
    print("\n== Staff join ==")
    r = requests.post(
        f"{BASE}/household/staff/join",
        headers=auth_hdr(staff_token),
        json={"invite_code": invite_code},
        timeout=30,
    )
    rec(r.status_code == 200 and r.json().get("staff_id") == staff_id, "POST /household/staff/join 200", f"{r.status_code} {r.text[:200]}")

    # --- 5. GET /contract-templates
    print("\n== GET /contract-templates ==")
    r = requests.get(f"{BASE}/contract-templates", headers=auth_hdr(owner_token), timeout=30)
    rec(r.status_code == 200, "GET /contract-templates 200", f"{r.status_code}")
    templates = r.json() if r.status_code == 200 else []
    kinds = sorted([t.get("kind") for t in templates])
    rec(kinds == ["blank", "confidentiality", "employment", "nda"], "contract-templates has expected 4 kinds", f"got: {kinds}")
    # shape check
    shape_ok = True
    for t in templates:
        for key in ("kind", "title", "icon", "summary", "default_variables", "body"):
            if key not in t:
                shape_ok = False
                break
        if not isinstance(t.get("default_variables"), dict) or not isinstance(t.get("body"), str):
            shape_ok = False
    rec(shape_ok, "contract-templates shape valid", "")
    # unauth
    r = requests.get(f"{BASE}/contract-templates", timeout=30)
    rec(r.status_code in (401, 403), "GET /contract-templates no auth -> 401/403", f"{r.status_code}")

    # --- 6. POST /contracts — empty body => 400
    print("\n== POST /contracts edge cases ==")
    nda = next(t for t in templates if t["kind"] == "nda")
    body_text = nda["body"]
    # Use variables that match placeholders in the NDA template (which uses {{household_name}} etc.)
    variables = {
        "household_name": "Rumah Bali",
        "staff_name": "Sari Putri",
        "start_date": "2026-05-02",
        "city": "Denpasar",
    }
    r = requests.post(
        f"{BASE}/contracts",
        headers=auth_hdr(owner_token),
        json={"space_id": space_id, "template_kind": "nda", "title": "NDA — Sari", "body": "", "variables": variables, "assigned_staff_id": staff_id},
        timeout=30,
    )
    rec(r.status_code == 400, "POST /contracts empty body -> 400", f"{r.status_code} {r.text[:200]}")

    # bad assigned_staff_id
    r = requests.post(
        f"{BASE}/contracts",
        headers=auth_hdr(owner_token),
        json={"space_id": space_id, "template_kind": "nda", "title": "X", "body": body_text, "assigned_staff_id": "staff_does_not_exist"},
        timeout=30,
    )
    rec(r.status_code == 404, "POST /contracts bad assigned_staff_id -> 404", f"{r.status_code} {r.text[:200]}")

    # Non-member of the space
    r = requests.post(
        f"{BASE}/contracts",
        headers=auth_hdr(outsider_token),
        json={"space_id": space_id, "template_kind": "blank", "title": "X", "body": "hello world"},
        timeout=30,
    )
    rec(r.status_code == 403 and "Not a member" in r.text, "POST /contracts non-member -> 403 'Not a member'", f"{r.status_code} {r.text[:200]}")

    # Non-owner member (the staff user who just joined is now a member)
    r = requests.post(
        f"{BASE}/contracts",
        headers=auth_hdr(staff_token),
        json={"space_id": space_id, "template_kind": "blank", "title": "X", "body": "hello world"},
        timeout=30,
    )
    rec(r.status_code == 403 and "owner" in r.text.lower(), "POST /contracts non-owner member -> 403 owner-only", f"{r.status_code} {r.text[:200]}")

    # --- 7. Create valid contract (owner)
    print("\n== POST /contracts happy path ==")
    r = requests.post(
        f"{BASE}/contracts",
        headers=auth_hdr(owner_token),
        json={
            "space_id": space_id,
            "template_kind": "nda",
            "title": "NDA — Sari",
            "body": body_text,
            "variables": variables,
            "assigned_staff_id": staff_id,
            "require_owner_signature": True,
            "require_staff_signature": True,
            "require_drawn_signature_owner": False,
            "require_drawn_signature_staff": True,
        },
        timeout=30,
    )
    rec(r.status_code == 200, "POST /contracts happy 200", f"{r.status_code} {r.text[:300]}")
    c = r.json()
    contract_id = c["contract_id"]
    print("contract_id:", contract_id)
    rec(c.get("status") == "pending", "new contract status=pending", f"status={c.get('status')}")
    rec(c.get("assigned_staff_name") == "Sari Putri", "assigned_staff_name resolved", f"got: {c.get('assigned_staff_name')}")
    rec(c.get("owner_signature") is None and c.get("staff_signature") is None, "both signatures null at creation", "")

    # Verify notification created for staff user
    r = requests.get(f"{BASE}/notifications", headers=auth_hdr(staff_token), params={"space_id": space_id}, timeout=30)
    rec(r.status_code == 200, "GET /notifications (staff) 200", f"{r.status_code}")
    notifs = r.json() if r.status_code == 200 else []
    ca = [n for n in notifs if n.get("kind") == "contract_assigned" and n.get("data", {}).get("contract_id") == contract_id]
    rec(len(ca) == 1, "staff got 1 contract_assigned notification", f"found: {len(ca)} — all kinds: {[n.get('kind') for n in notifs]}")

    # --- 8. GET /contracts listing
    print("\n== GET /contracts ==")
    r = requests.get(f"{BASE}/contracts", headers=auth_hdr(owner_token), params={"space_id": space_id}, timeout=30)
    rec(r.status_code == 200 and any(x["contract_id"] == contract_id for x in r.json()), "owner sees created contract", f"{r.status_code} {r.text[:200]}")

    r = requests.get(f"{BASE}/contracts", headers=auth_hdr(staff_token), params={"space_id": space_id}, timeout=30)
    rec(r.status_code == 200 and all(x.get("assigned_staff_id") == staff_id for x in r.json()), "staff only sees their assigned contracts", f"{r.status_code} entries={len(r.json()) if r.status_code == 200 else 'N/A'}")

    r = requests.get(f"{BASE}/contracts", headers=auth_hdr(owner_token), params={"space_id": space_id, "staff_id": staff2_id}, timeout=30)
    rec(r.status_code == 200 and not any(x["contract_id"] == contract_id for x in r.json()), "staff_id filter excludes contract assigned to other staff", f"got: {r.text[:200]}")

    r = requests.get(f"{BASE}/contracts", headers=auth_hdr(owner_token), params={"space_id": space_id, "status": "pending"}, timeout=30)
    rec(r.status_code == 200 and all(x["status"] == "pending" for x in r.json()), "status=pending filter works", "")

    r = requests.get(f"{BASE}/contracts", headers=auth_hdr(outsider_token), params={"space_id": space_id}, timeout=30)
    rec(r.status_code == 403, "non-member GET /contracts -> 403", f"{r.status_code}")

    # --- 9. GET /contracts/{id}
    print("\n== GET /contracts/{id} ==")
    r = requests.get(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(owner_token), timeout=30)
    rec(r.status_code == 200, "owner GET single contract 200", f"{r.status_code}")
    r = requests.get(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(staff_token), timeout=30)
    rec(r.status_code == 200, "assigned staff GET single contract 200", f"{r.status_code} {r.text[:200]}")
    r = requests.get(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(outsider_token), timeout=30)
    rec(r.status_code == 403, "non-member GET single -> 403", f"{r.status_code}")

    # Create a 3rd user who joins as staff2 (a staff who's NOT the assignee)
    other_staff_email = f"staff_other_{TS}@cozii.app"
    other_staff_token = register_or_login(other_staff_email, COMMON_PW, "Other Staff")
    r = requests.post(f"{BASE}/household/staff/join", headers=auth_hdr(other_staff_token), json={"invite_code": staff2.get("invite_code")}, timeout=30)
    joined_ok = r.status_code == 200
    if joined_ok:
        r2 = requests.get(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(other_staff_token), timeout=30)
        rec(r2.status_code == 403, "staff not the assignee GET single -> 403", f"{r2.status_code} {r2.text[:200]}")
    else:
        rec(False, "staff2 join for non-assignee test", f"join failed: {r.status_code} {r.text[:200]}")

    # --- 10. PATCH /contracts/{id}
    print("\n== PATCH /contracts/{id} ==")
    # Non-owner member (staff) cannot patch
    r = requests.patch(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(staff_token), json={"title": "Nope"}, timeout=30)
    rec(r.status_code == 403, "non-owner PATCH -> 403", f"{r.status_code} {r.text[:200]}")

    # Owner reassigns to staff2
    r = requests.patch(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(owner_token), json={"assigned_staff_id": staff2_id}, timeout=30)
    rec(r.status_code == 200 and r.json().get("assigned_staff_name") == "Bayu Dwi", "PATCH assigned_staff_id updates name", f"{r.status_code} {r.text[:300]}")

    # Reassign back to original staff
    r = requests.patch(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(owner_token), json={"assigned_staff_id": staff_id}, timeout=30)
    rec(r.status_code == 200 and r.json().get("assigned_staff_id") == staff_id, "PATCH assigned_staff_id revert OK", f"{r.status_code}")

    # --- 11. POST /contracts/{id}/render
    print("\n== GET /contracts/{id}/render ==")
    r = requests.get(f"{BASE}/contracts/{contract_id}/render", headers=auth_hdr(staff_token), timeout=30)
    rec(r.status_code == 200, "GET render (staff) 200", f"{r.status_code} {r.text[:200]}")
    rj = r.json() if r.status_code == 200 else {}
    rb = rj.get("rendered_body", "")
    # Placeholders should have been replaced — none of the {{key}} tokens should remain for provided variables
    tokens_remaining = [f"{{{{{k}}}}}" in rb for k in variables.keys()]
    rec(not any(tokens_remaining) and "Rumah Bali" in rb and "Sari Putri" in rb and "Denpasar" in rb,
        "rendered_body has placeholders replaced",
        f"tokens still present: {tokens_remaining}, sample={rb[:200]!r}")
    rec(rj.get("title") == "NDA — Sari", "render returns title", f"got title={rj.get('title')}")
    rec(rj.get("status") == "pending", "render returns status=pending", f"got status={rj.get('status')}")
    rec(isinstance(rj.get("variables"), dict), "render returns variables dict", "")

    # --- 12. Sign flow
    print("\n== POST /contracts/{id}/sign ==")
    # Sign with no body -> 400
    r = requests.post(f"{BASE}/contracts/{contract_id}/sign", headers=auth_hdr(owner_token), json={}, timeout=30)
    rec(r.status_code == 400, "sign with neither typed_name nor drawing -> 400", f"{r.status_code} {r.text[:200]}")

    # Owner signs with typed_name only (owner does not require drawn)
    r = requests.post(f"{BASE}/contracts/{contract_id}/sign", headers=auth_hdr(owner_token), json={"typed_name": "Test User"}, timeout=30)
    rec(r.status_code == 200, "owner sign typed_name 200", f"{r.status_code} {r.text[:300]}")
    c1 = r.json()
    rec(c1.get("status") == "pending", "after owner sign status still pending", f"status={c1.get('status')}")
    os_sig = c1.get("owner_signature") or {}
    rec(os_sig.get("typed_name") == "Test User" and os_sig.get("role") == "owner" and os_sig.get("user_id") == me_owner.get("user_id"),
        "owner_signature populated correctly",
        f"got: {json.dumps(os_sig, default=str)[:300]}")
    rec(os_sig.get("signed_at") is not None, "owner_signature.signed_at present", "")
    rec(os_sig.get("user_agent") is not None, "owner_signature.user_agent captured", "")

    # Staff should get a contract_owner_signed notification
    r = requests.get(f"{BASE}/notifications", headers=auth_hdr(staff_token), params={"space_id": space_id}, timeout=30)
    notifs = r.json() if r.status_code == 200 else []
    cos = [n for n in notifs if n.get("kind") == "contract_owner_signed" and n.get("data", {}).get("contract_id") == contract_id]
    rec(len(cos) >= 1, "staff got contract_owner_signed notification", f"count={len(cos)}")

    # Staff signs WITHOUT drawing_base64 but with typed_name (drawn required => 400)
    r = requests.post(f"{BASE}/contracts/{contract_id}/sign", headers=auth_hdr(staff_token), json={"typed_name": "Sari Putri"}, timeout=30)
    rec(r.status_code == 400 and "hand-drawn" in r.text.lower(), "staff sign missing drawing -> 400 (drawn required)", f"{r.status_code} {r.text[:200]}")

    # Staff signs with drawing_base64
    r = requests.post(
        f"{BASE}/contracts/{contract_id}/sign",
        headers=auth_hdr(staff_token),
        json={"typed_name": "Sari Putri", "drawing_base64": "data:image/svg+xml;base64,PHN2Zy8+"},
        timeout=30,
    )
    rec(r.status_code == 200, "staff sign with drawing 200", f"{r.status_code} {r.text[:300]}")
    c2 = r.json()
    rec(c2.get("status") == "signed", "after both signed, status=signed", f"status={c2.get('status')}")
    ss = c2.get("staff_signature") or {}
    rec(ss.get("drawing_base64", "").startswith("data:image/svg"), "staff_signature.drawing_base64 stored", f"got: {str(ss.get('drawing_base64'))[:60]}")
    rec(ss.get("role") == "staff" and ss.get("user_id") == me_staff.get("user_id"), "staff_signature role+user_id OK", "")

    # Verify a document was auto-archived to /documents folder=contracts
    r = requests.get(f"{BASE}/documents", headers=auth_hdr(owner_token), params={"space_id": space_id}, timeout=30)
    if r.status_code == 200:
        docs = r.json()
        matches = [d for d in docs if d.get("folder") == "contracts" and (d.get("related_to") or {}).get("id") == contract_id]
        rec(len(matches) >= 1, "auto-archived doc in folder=contracts with related_to.id==contract_id", f"matches={len(matches)}")
    else:
        # documents endpoint may use different query/contract
        rec(False, "GET /documents for auto-archive verification", f"{r.status_code} {r.text[:200]}")

    # Owner PATCH after signed -> 400
    r = requests.patch(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(owner_token), json={"title": "Can't edit now"}, timeout=30)
    rec(r.status_code == 400 and "signed" in r.text.lower(), "PATCH after sign -> 400 cannot edit", f"{r.status_code} {r.text[:200]}")

    # --- 13. Void contract
    print("\n== POST /contracts/{id}/void ==")
    # Non-owner void -> 403
    r = requests.post(f"{BASE}/contracts/{contract_id}/void", headers=auth_hdr(staff_token), timeout=30)
    rec(r.status_code == 403, "non-owner void -> 403", f"{r.status_code} {r.text[:200]}")
    # Owner void
    r = requests.post(f"{BASE}/contracts/{contract_id}/void", headers=auth_hdr(owner_token), timeout=30)
    rec(r.status_code == 200 and r.json().get("status") == "void", "owner void -> status=void", f"{r.status_code} {r.text[:200]}")

    # Sign after void -> 400
    r = requests.post(f"{BASE}/contracts/{contract_id}/sign", headers=auth_hdr(owner_token), json={"typed_name": "X"}, timeout=30)
    rec(r.status_code == 400, "sign after void -> 400", f"{r.status_code} {r.text[:200]}")

    # --- 14. DELETE /contracts/{id}
    print("\n== DELETE /contracts/{id} ==")
    r = requests.delete(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(outsider_token), timeout=30)
    rec(r.status_code == 403, "outsider DELETE -> 403", f"{r.status_code}")
    r = requests.delete(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(staff_token), timeout=30)
    rec(r.status_code == 403, "non-owner DELETE -> 403", f"{r.status_code}")
    r = requests.delete(f"{BASE}/contracts/{contract_id}", headers=auth_hdr(owner_token), timeout=30)
    rec(r.status_code == 200, "owner DELETE -> 200", f"{r.status_code} {r.text[:200]}")

    # --- 15. Outsider blanket 403s for GET/PATCH/DELETE on a fresh contract
    print("\n== Outsider full lockout ==")
    r = requests.post(
        f"{BASE}/contracts",
        headers=auth_hdr(owner_token),
        json={"space_id": space_id, "template_kind": "blank", "title": "Lockout test", "body": "hello world"},
        timeout=30,
    )
    if r.status_code == 200:
        c3_id = r.json()["contract_id"]
        r = requests.get(f"{BASE}/contracts/{c3_id}", headers=auth_hdr(outsider_token), timeout=30)
        rec(r.status_code == 403, "outsider GET single -> 403", f"{r.status_code}")
        r = requests.patch(f"{BASE}/contracts/{c3_id}", headers=auth_hdr(outsider_token), json={"title": "x"}, timeout=30)
        rec(r.status_code == 403, "outsider PATCH -> 403", f"{r.status_code}")
        r = requests.delete(f"{BASE}/contracts/{c3_id}", headers=auth_hdr(outsider_token), timeout=30)
        rec(r.status_code == 403, "outsider DELETE (fresh) -> 403", f"{r.status_code}")
        # cleanup
        requests.delete(f"{BASE}/contracts/{c3_id}", headers=auth_hdr(owner_token), timeout=30)

    # --- Summary
    print("\n================ SUMMARY ================")
    print(f"PASSED: {len(passed)}   FAILED: {len(failed)}")
    if failed:
        for name, detail in failed:
            print(f"  FAIL: {name}")
            if detail:
                print(f"         {detail}")
        sys.exit(1)


if __name__ == "__main__":
    main()
