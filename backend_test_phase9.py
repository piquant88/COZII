"""
Phase 9 backend tests:
  A) Category CRUD with new staff_can_edit field + owner-only category authorization
  B) Item CRUD permission gating via assert_can_edit_category_items (owner / staff with perm / staff without perm)
  C) Regular non-staff space member can still create items in either category
  D) Socket-emit non-regression — endpoints calling record_activity still return their proper response codes
  E) Phase 7/8 quick smoke regression — contracts create / sign by owner / sign by staff / status flips signed / archive doc

Run:
  python /app/backend_test_phase9.py
"""

from __future__ import annotations

import os
import sys
import time
import json
import uuid
import base64
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests

BACKEND_URL = os.environ.get("BACKEND_URL", "https://family-wallet-21.preview.emergentagent.com")
API = BACKEND_URL.rstrip("/") + "/api"
TS = int(time.time())

PASS: List[str] = []
FAIL: List[str] = []


def _h(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def assert_eq(label: str, got: Any, want: Any) -> bool:
    if got == want:
        PASS.append(label)
        return True
    FAIL.append(f"{label}  -> got={got!r} expected={want!r}")
    return False


def assert_true(label: str, cond: bool, extra: str = "") -> bool:
    if cond:
        PASS.append(label)
        return True
    FAIL.append(f"{label}  -> {extra}")
    return False


def register(email: str, name: str, password: str = "test1234") -> str:
    r = requests.post(f"{API}/auth/register", json={"email": email, "name": name, "password": password})
    r.raise_for_status()
    j = r.json()
    return j.get("token") or j.get("session_token")


def login(email: str, password: str = "test1234") -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    j = r.json()
    return j.get("token") or j.get("session_token")


def main():
    print(f"BACKEND: {API}")
    # ---------- Setup users ----------
    owner_email = f"owner_p9_{TS}@cozii.app"
    staff_email = f"staff_p9_{TS}@cozii.app"
    member_email = f"member_p9_{TS}@cozii.app"
    outsider_email = f"outsider_p9_{TS}@cozii.app"

    tok_owner = register(owner_email, "Anya Sharma")
    tok_staff = register(staff_email, "Sari Putri")
    tok_member = register(member_email, "Riley Chen")
    tok_outsider = register(outsider_email, "Quinn Outsider")

    # ---------- Owner creates household space ----------
    r = requests.post(f"{API}/spaces", headers=_h(tok_owner),
                      json={"name": f"Rumah Anya {TS}", "currency": "IDR", "space_type": "household"})
    assert_true("POST /spaces (household IDR)", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    space = r.json()
    space_id = space["space_id"]
    space_invite_code = space["invite_code"]
    assert_eq("space.space_type=household", space.get("space_type"), "household")

    # ---------- Member M joins via space invite_code ----------
    r = requests.post(f"{API}/spaces/join", headers=_h(tok_member), json={"invite_code": space_invite_code})
    assert_true("M joins space via invite_code", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")

    # ============================================================
    # A) CATEGORY CRUD with new staff_can_edit field
    # ============================================================
    print("\n--- A) Category CRUD + staff_can_edit ---")
    # 1) Owner POST with staff_can_edit:true
    r = requests.post(f"{API}/categories", headers=_h(tok_owner),
                      json={"space_id": space_id, "name": "Groceries", "icon": "Apple", "tint": "mint", "staff_can_edit": True})
    assert_true("A1 POST cat with staff_can_edit:true (owner) -> 200", r.status_code == 200, r.text[:200])
    cat_grocery = r.json()
    cat_grocery_id = cat_grocery["category_id"]
    assert_eq("A1 response.staff_can_edit==true", cat_grocery.get("staff_can_edit"), True)

    # 2) Owner POST without staff_can_edit -> defaults to false
    r = requests.post(f"{API}/categories", headers=_h(tok_owner),
                      json={"space_id": space_id, "name": "Personal Care", "icon": "Heart", "tint": "lavender"})
    assert_true("A2 POST cat without staff_can_edit -> 200", r.status_code == 200, r.text[:200])
    cat_pc = r.json()
    cat_pc_id = cat_pc["category_id"]
    assert_eq("A2 response.staff_can_edit defaults to False", cat_pc.get("staff_can_edit"), False)

    # 3) Owner PATCH with true -> false
    r = requests.patch(f"{API}/categories/{cat_pc_id}", headers=_h(tok_owner),
                       json={"staff_can_edit": True})
    assert_true("A3a PATCH staff_can_edit:true -> 200", r.status_code == 200, r.text[:200])
    assert_eq("A3a response.staff_can_edit==true", r.json().get("staff_can_edit"), True)

    r = requests.patch(f"{API}/categories/{cat_pc_id}", headers=_h(tok_owner),
                       json={"staff_can_edit": False})
    assert_true("A3b PATCH staff_can_edit:false -> 200", r.status_code == 200, r.text[:200])
    assert_eq("A3b response.staff_can_edit==false", r.json().get("staff_can_edit"), False)

    # GET returns updated value
    r = requests.get(f"{API}/categories", headers=_h(tok_owner), params={"space_id": space_id})
    assert_true("A3c GET /categories -> 200", r.status_code == 200, r.text[:200])
    cats = {c["category_id"]: c for c in r.json()}
    assert_eq("A3c GET cat_pc.staff_can_edit==false", cats[cat_pc_id].get("staff_can_edit"), False)
    assert_eq("A3c GET cat_grocery.staff_can_edit==true", cats[cat_grocery_id].get("staff_can_edit"), True)

    # 4) Non-owner regular member: POST cat -> 403
    r = requests.post(f"{API}/categories", headers=_h(tok_member),
                      json={"space_id": space_id, "name": "Sneaky Cat"})
    assert_eq("A4 non-owner member POST /categories -> 403", r.status_code, 403)
    if r.status_code == 403:
        assert_true("A4 detail mentions 'owner'", "owner" in (r.json().get("detail") or "").lower(),
                    extra=str(r.json().get("detail")))

    # 5) Non-owner PATCH -> 403
    r = requests.patch(f"{API}/categories/{cat_grocery_id}", headers=_h(tok_member),
                       json={"name": "Hijacked"})
    assert_eq("A5 non-owner member PATCH /categories/{id} -> 403", r.status_code, 403)

    # 6) Non-owner DELETE -> 403
    r = requests.delete(f"{API}/categories/{cat_grocery_id}", headers=_h(tok_member))
    assert_eq("A6 non-owner member DELETE /categories/{id} -> 403", r.status_code, 403)

    # ============================================================
    # B) ITEM CRUD permission gating (staff)
    # ============================================================
    print("\n--- B) Item CRUD permission gating ---")
    # Owner creates 2 categories: catA (staff_can_edit=true), catB (staff_can_edit=false)
    r = requests.post(f"{API}/categories", headers=_h(tok_owner),
                      json={"space_id": space_id, "name": "CatA editable", "staff_can_edit": True})
    cat_A = r.json()["category_id"]
    r = requests.post(f"{API}/categories", headers=_h(tok_owner),
                      json={"space_id": space_id, "name": "CatB locked", "staff_can_edit": False})
    cat_B = r.json()["category_id"]

    # Owner creates a staff member -> get invite_code
    r = requests.post(f"{API}/household/staff", headers=_h(tok_owner),
                      json={"space_id": space_id, "name": "Sari Putri", "salary": 2500000, "pay_cycle": "monthly"})
    assert_true("B-setup POST /household/staff -> 200", r.status_code == 200, r.text[:200])
    staff_doc = r.json()
    staff_id = staff_doc["staff_id"]
    staff_invite = staff_doc.get("invite_code")
    assert_true("B-setup staff invite_code is non-empty", bool(staff_invite), extra=str(staff_doc))

    # Staff S joins
    r = requests.post(f"{API}/household/staff/join", headers=_h(tok_staff),
                      json={"invite_code": staff_invite})
    assert_true("B-setup staff join -> 200", r.status_code == 200, r.text[:200])

    # As owner, set staff perms: edit_inventory=true (we use PATCH /household/staff/{id}/permissions)
    r = requests.patch(f"{API}/household/staff/{staff_id}/permissions", headers=_h(tok_owner),
                      json={"permissions": {"edit_inventory": True}})
    assert_true("B-setup PATCH staff perms edit_inventory:true -> 200", r.status_code == 200, r.text[:200])
    assert_eq("B-setup response.permissions.edit_inventory==true",
              (r.json().get("permissions") or {}).get("edit_inventory"), True)

    # ----- TEST AS STAFF S -----
    # POST /items into catA -> 200
    r = requests.post(f"{API}/items", headers=_h(tok_staff),
                      json={"space_id": space_id, "category_id": cat_A, "name": "Staff item A1", "price": 10000})
    assert_true("B1 staff POST item into catA -> 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    staff_item_A = r.json().get("item_id") if r.status_code == 200 else None

    # POST /items into catB -> 403
    r = requests.post(f"{API}/items", headers=_h(tok_staff),
                      json={"space_id": space_id, "category_id": cat_B, "name": "Staff item B1"})
    assert_eq("B2 staff POST item into catB -> 403", r.status_code, 403)
    if r.status_code == 403:
        detail = (r.json().get("detail") or "").lower()
        assert_true("B2 detail mentions 'category'", "category" in detail or "ask the owner" in detail, extra=detail)

    # Owner creates item in catB (used to test PATCH/DELETE on it as staff)
    r = requests.post(f"{API}/items", headers=_h(tok_owner),
                      json={"space_id": space_id, "category_id": cat_B, "name": "Owner item B1"})
    assert_true("B-setup owner POST item in catB -> 200", r.status_code == 200, r.text[:200])
    owner_item_B = r.json()["item_id"]

    # PATCH as staff on item in catA -> 200
    if staff_item_A:
        r = requests.patch(f"{API}/items/{staff_item_A}", headers=_h(tok_staff),
                          json={"name": "Staff item A1 updated"})
        assert_true("B3 staff PATCH item in catA -> 200", r.status_code == 200, r.text[:200])

    # PATCH as staff on item in catB -> 403
    r = requests.patch(f"{API}/items/{owner_item_B}", headers=_h(tok_staff),
                      json={"name": "Hijack"})
    assert_eq("B4 staff PATCH item in catB -> 403", r.status_code, 403)

    # DELETE as staff on item in catA -> 200
    if staff_item_A:
        # First create another item to delete (since we still want one in catA for later tests)
        r = requests.post(f"{API}/items", headers=_h(tok_staff),
                          json={"space_id": space_id, "category_id": cat_A, "name": "Staff item A2"})
        if r.status_code == 200:
            del_id = r.json()["item_id"]
            r = requests.delete(f"{API}/items/{del_id}", headers=_h(tok_staff))
            assert_true("B5 staff DELETE item in catA -> 200", r.status_code == 200, r.text[:200])

    # DELETE as staff on item in catB -> 403
    r = requests.delete(f"{API}/items/{owner_item_B}", headers=_h(tok_staff))
    assert_eq("B6 staff DELETE item in catB -> 403", r.status_code, 403)

    # POST /items/bulk into catA -> 200
    r = requests.post(f"{API}/items/bulk", headers=_h(tok_staff),
                      json={"space_id": space_id, "category_id": cat_A,
                            "items": [{"name": "BulkA1", "quantity": 1, "price": 100, "fields": {}}],
                            "auto_fetch_images": False})
    assert_true("B7 staff POST /items/bulk into catA -> 200", r.status_code == 200,
                f"status={r.status_code} body={r.text[:200]}")

    # POST /items/bulk into catB -> 403
    r = requests.post(f"{API}/items/bulk", headers=_h(tok_staff),
                      json={"space_id": space_id, "category_id": cat_B,
                            "items": [{"name": "BulkB1", "quantity": 1, "price": 100, "fields": {}}],
                            "auto_fetch_images": False})
    assert_eq("B8 staff POST /items/bulk into catB -> 403", r.status_code, 403)

    # ----- Now: owner PATCH staff perms edit_inventory:false -----
    r = requests.patch(f"{API}/household/staff/{staff_id}/permissions", headers=_h(tok_owner),
                      json={"permissions": {"edit_inventory": False}})
    assert_true("B-setup PATCH staff perms edit_inventory:false -> 200", r.status_code == 200, r.text[:200])
    assert_eq("B-setup response.permissions.edit_inventory==false",
              (r.json().get("permissions") or {}).get("edit_inventory"), False)

    # Staff POST item in catA -> 403 (no perm anymore)
    r = requests.post(f"{API}/items", headers=_h(tok_staff),
                      json={"space_id": space_id, "category_id": cat_A, "name": "Should fail no perm"})
    assert_eq("B9 staff POST item in catA after edit_inventory:false -> 403", r.status_code, 403)
    if r.status_code == 403:
        detail = (r.json().get("detail") or "").lower()
        assert_true("B9 detail mentions permission/inventory",
                    "permission" in detail or "inventory" in detail, extra=detail)

    # PATCH item in catA -> 403 (the surviving original staff item)
    if staff_item_A:
        r = requests.patch(f"{API}/items/{staff_item_A}", headers=_h(tok_staff),
                          json={"name": "Should fail"})
        assert_eq("B10 staff PATCH item in catA after edit_inventory:false -> 403", r.status_code, 403)

        # DELETE item in catA -> 403
        r = requests.delete(f"{API}/items/{staff_item_A}", headers=_h(tok_staff))
        assert_eq("B11 staff DELETE item in catA after edit_inventory:false -> 403", r.status_code, 403)

    # ----- As owner, all operations should always succeed -----
    r = requests.post(f"{API}/items", headers=_h(tok_owner),
                      json={"space_id": space_id, "category_id": cat_A, "name": "Owner A item", "price": 5000})
    assert_true("B12 owner POST item catA -> 200", r.status_code == 200, r.text[:200])
    owner_item_A = r.json().get("item_id")
    r = requests.post(f"{API}/items", headers=_h(tok_owner),
                      json={"space_id": space_id, "category_id": cat_B, "name": "Owner B item 2", "price": 9000})
    assert_true("B12 owner POST item catB -> 200", r.status_code == 200, r.text[:200])

    if owner_item_A:
        r = requests.patch(f"{API}/items/{owner_item_A}", headers=_h(tok_owner),
                          json={"name": "Owner A item updated"})
        assert_true("B12 owner PATCH item catA -> 200", r.status_code == 200, r.text[:200])
        r = requests.delete(f"{API}/items/{owner_item_A}", headers=_h(tok_owner))
        assert_true("B12 owner DELETE item catA -> 200", r.status_code == 200, r.text[:200])

    # ============================================================
    # C) Regular non-staff member M can still create items
    # ============================================================
    print("\n--- C) Non-staff member access (no regression) ---")
    # M into catA (staff_can_edit=true) -> 200 (owner short-circuit doesn't apply but helper allows non-staff non-owner)
    r = requests.post(f"{API}/items", headers=_h(tok_member),
                      json={"space_id": space_id, "category_id": cat_A, "name": "Member item in A", "price": 100})
    assert_true("C1 member POST item catA -> 200", r.status_code == 200,
                f"status={r.status_code} body={r.text[:200]}")
    member_item_A = r.json().get("item_id") if r.status_code == 200 else None

    # M into catB (staff_can_edit=false)
    # The helper short-circuits for non-staff-non-owner BEFORE the staff_can_edit check,
    # so per the spec this should remain 200 (no regression).
    r = requests.post(f"{API}/items", headers=_h(tok_member),
                      json={"space_id": space_id, "category_id": cat_B, "name": "Member item in B", "price": 200})
    assert_true("C2 member POST item catB -> 200", r.status_code == 200,
                f"status={r.status_code} body={r.text[:200]}")

    # ============================================================
    # D) Socket emit non-regression — every endpoint that uses record_activity
    # ============================================================
    print("\n--- D) Socket emit non-regression ---")
    # POST /api/items
    r = requests.post(f"{API}/items", headers=_h(tok_owner),
                      json={"space_id": space_id, "category_id": cat_A, "name": "D-item", "price": 1})
    assert_true("D1 POST /items -> 200", r.status_code == 200, r.text[:200])
    d_item_id = r.json()["item_id"]
    # PATCH /api/items/{id}
    r = requests.patch(f"{API}/items/{d_item_id}", headers=_h(tok_owner), json={"name": "D-item v2"})
    assert_true("D2 PATCH /items/{id} -> 200", r.status_code == 200, r.text[:200])
    # DELETE /api/items/{id}
    r = requests.delete(f"{API}/items/{d_item_id}", headers=_h(tok_owner))
    assert_true("D3 DELETE /items/{id} -> 200", r.status_code == 200, r.text[:200])

    # POST /api/categories
    r = requests.post(f"{API}/categories", headers=_h(tok_owner),
                      json={"space_id": space_id, "name": f"D-cat-{TS}"})
    assert_true("D4 POST /categories -> 200", r.status_code == 200, r.text[:200])
    d_cat_id = r.json()["category_id"]
    # PATCH /api/categories/{id}
    r = requests.patch(f"{API}/categories/{d_cat_id}", headers=_h(tok_owner),
                       json={"name": f"D-cat-{TS}-x"})
    assert_true("D5 PATCH /categories/{id} -> 200", r.status_code == 200, r.text[:200])
    # DELETE /api/categories/{id}
    r = requests.delete(f"{API}/categories/{d_cat_id}", headers=_h(tok_owner))
    assert_true("D6 DELETE /categories/{id} -> 200", r.status_code == 200, r.text[:200])

    # POST /api/household/tasks
    r = requests.post(f"{API}/household/tasks", headers=_h(tok_owner),
                      json={"space_id": space_id, "title": "D-task", "recurrence": "daily"})
    assert_true("D7 POST /household/tasks -> 200", r.status_code == 200, r.text[:200])
    d_task_id = r.json()["task_id"]
    # PATCH /api/household/tasks/{id}
    r = requests.patch(f"{API}/household/tasks/{d_task_id}", headers=_h(tok_owner),
                       json={"title": "D-task v2"})
    assert_true("D8 PATCH /household/tasks/{id} -> 200", r.status_code == 200, r.text[:200])

    # POST /api/household/shopping
    r = requests.post(f"{API}/household/shopping", headers=_h(tok_owner),
                      json={"space_id": space_id, "item_name": "D-rice", "urgency": "normal"})
    assert_true("D9 POST /household/shopping -> 200", r.status_code == 200, r.text[:200])

    # POST /api/household/attendance
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r = requests.post(f"{API}/household/attendance", headers=_h(tok_owner),
                      json={"space_id": space_id, "staff_id": staff_id, "date": today_str, "status": "present"})
    assert_true("D10 POST /household/attendance -> 200", r.status_code == 200, r.text[:200])

    # POST /api/household/payroll
    r = requests.post(f"{API}/household/payroll", headers=_h(tok_owner),
                      json={"space_id": space_id, "staff_id": staff_id, "gross": 2500000})
    assert_true("D11 POST /household/payroll -> 200", r.status_code == 200, r.text[:200])

    # ============================================================
    # E) Phase 7/8 NON-REGRESSION (contracts smoke)
    # ============================================================
    print("\n--- E) Contract smoke regression ---")
    # Create contract assigned to staff
    r = requests.post(f"{API}/contracts", headers=_h(tok_owner),
                      json={"space_id": space_id, "template_kind": "nda",
                            "title": f"NDA {TS}", "body": "Hello {{staff_name}}",
                            "variables": {"staff_name": "Sari Putri"},
                            "assigned_staff_id": staff_id,
                            "require_owner_signature": True,
                            "require_staff_signature": True})
    assert_true("E1 POST /contracts -> 200", r.status_code == 200,
                f"status={r.status_code} body={r.text[:200]}")
    contract_id = r.json()["contract_id"] if r.status_code == 200 else None
    if contract_id:
        # Owner signs first
        r = requests.post(f"{API}/contracts/{contract_id}/sign", headers=_h(tok_owner),
                         json={"typed_name": "Anya Sharma"})
        assert_true("E2 owner signs -> 200", r.status_code == 200, r.text[:200])
        if r.status_code == 200:
            assert_true("E2 status still pending after owner sign",
                        r.json().get("status") in ("pending", "pending_staff"),
                        extra=str(r.json().get("status")))

        # Staff signs (drawn not required by default => typed_name suffices)
        r = requests.post(f"{API}/contracts/{contract_id}/sign", headers=_h(tok_staff),
                         json={"typed_name": "Sari Putri"})
        assert_true("E3 staff signs -> 200", r.status_code == 200, r.text[:200])
        if r.status_code == 200:
            assert_eq("E3 status flips to signed", r.json().get("status"), "signed")

        # Owner notification: staff signed
        r = requests.get(f"{API}/notifications", headers=_h(tok_owner),
                        params={"space_id": space_id, "unread_only": "true"})
        assert_true("E4 GET /notifications (owner) -> 200", r.status_code == 200, r.text[:200])
        if r.status_code == 200:
            kinds = [n.get("kind") for n in r.json()]
            assert_true("E4 owner has contract_staff_signed",
                        "contract_staff_signed" in kinds,
                        extra=str(kinds))

        # Documents archive
        r = requests.get(f"{API}/documents", headers=_h(tok_owner),
                        params={"space_id": space_id, "folder": "contracts"})
        assert_true("E5 GET /documents?folder=contracts -> 200", r.status_code == 200, r.text[:200])
        if r.status_code == 200:
            docs = r.json()
            related_ok = any(((d.get("related_to") or {}).get("kind") == "contract"
                              and (d.get("related_to") or {}).get("id") == contract_id)
                             for d in docs)
            assert_true("E5 contract archived in documents vault", related_ok,
                        extra=str([d.get("related_to") for d in docs]))

    # ============================================================
    # Summary
    # ============================================================
    print("\n=================================================")
    print(f"PASS: {len(PASS)}    FAIL: {len(FAIL)}")
    if FAIL:
        print("\n----- FAILURES -----")
        for f in FAIL:
            print("  -", f)
    print("\n----- PASSED -----")
    for p in PASS:
        print("  -", p)
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print("HTTPError:", e, getattr(e.response, "text", ""))
        sys.exit(2)
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(3)
