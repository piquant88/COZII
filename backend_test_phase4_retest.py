"""Phase 4 retest — focused on:
  1) StaffMember response model returns invite_code (6-char) + permissions dict (with view_inventory)
  2) GET /api/categories after POST /household/payroll (no 500), includes Staff wages with non-null created_by
"""
import os
import sys
import time
import requests

BASE = "https://family-wallet-21.preview.emergentagent.com/api"

def _ts():
    return int(time.time())

def register_or_login(email, password, name):
    r = requests.post(f"{BASE}/auth/register", json={"email": email, "password": password, "name": name})
    if r.status_code in (200, 201):
        return r.json()["token"], r.json()["user"]["user_id"]
    # try login
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["token"], r.json()["user"]["user_id"]

def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def main():
    results = []
    def check(name, ok, detail=""):
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}{(' :: ' + detail) if detail else ''}")
        results.append((name, ok, detail))

    ts = _ts()
    owner_email = f"owner_p4retest_{ts}@cozii.app"
    owner_tok, owner_uid = register_or_login(owner_email, "Test1234!", "Owner Re Test")

    # 1) Create household space
    sp_body = {"name": f"RetestHouse_{ts}", "space_type": "household", "currency": "IDR"}
    r = requests.post(f"{BASE}/spaces", json=sp_body, headers=H(owner_tok))
    check("POST /spaces (household, IDR)", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code != 200:
        return summarize(results)
    space = r.json()
    space_id = space["space_id"]

    # 2) Create staff with salary
    staff_body = {
        "space_id": space_id,
        "name": "Sari Putri",
        "salary": 2500000,
        "pay_cycle": "monthly",
        "off_day": "Sunday",
    }
    r = requests.post(f"{BASE}/household/staff", json=staff_body, headers=H(owner_tok))
    check("POST /household/staff", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code != 200:
        return summarize(results)
    staff = r.json()
    staff_id = staff["staff_id"]

    # 2a) Verify invite_code present, 6 chars
    inv = staff.get("invite_code")
    check("POST /household/staff response.invite_code populated (6-char)",
          isinstance(inv, str) and len(inv) == 6 and inv.isalnum(),
          f"invite_code={inv}")

    # 2b) Verify permissions dict populated, has view_inventory key
    perms = staff.get("permissions")
    check("POST /household/staff response.permissions is dict",
          isinstance(perms, dict) and len(perms) > 0,
          f"permissions={perms}")
    if isinstance(perms, dict):
        check("POST /household/staff response.permissions has 'view_inventory' key",
              "view_inventory" in perms,
              f"keys={list(perms.keys())}")

    # 3) PATCH /household/staff/{id}/permissions — set view_inventory=true
    r = requests.patch(f"{BASE}/household/staff/{staff_id}/permissions",
                       json={"permissions": {"view_inventory": True, "view_finance": True}},
                       headers=H(owner_tok))
    check("PATCH /household/staff/{id}/permissions returns 200",
          r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code == 200:
        p2 = r.json()
        check("PATCH response has invite_code", isinstance(p2.get("invite_code"), str) and len(p2.get("invite_code")) == 6,
              f"invite_code={p2.get('invite_code')}")
        merged = p2.get("permissions") or {}
        check("PATCH response.permissions.view_inventory == True",
              merged.get("view_inventory") is True, f"perms={merged}")
        check("PATCH response.permissions retains other defaults (view_tasks)",
              "view_tasks" in merged, f"keys={list(merged.keys())}")

    # 4) GET /household/staff list response includes invite_code & permissions
    r = requests.get(f"{BASE}/household/staff?space_id={space_id}", headers=H(owner_tok))
    check("GET /household/staff list", r.status_code == 200, f"status={r.status_code}")
    if r.status_code == 200:
        lst = r.json()
        target = next((s for s in lst if s["staff_id"] == staff_id), None)
        check("GET /household/staff list contains created staff", target is not None)
        if target:
            check("GET list entry.invite_code populated (6-char)",
                  isinstance(target.get("invite_code"), str) and len(target["invite_code"]) == 6,
                  f"invite_code={target.get('invite_code')}")
            tperms = target.get("permissions") or {}
            check("GET list entry.permissions has view_inventory=True",
                  tperms.get("view_inventory") is True,
                  f"perms keys={list(tperms.keys())} view_inventory={tperms.get('view_inventory')}")

    # 5) POST /household/payroll
    pay_body = {
        "space_id": space_id,
        "staff_id": staff_id,
        # use defaults: gross from staff.salary, bonus/advances/deductions=0
    }
    r = requests.post(f"{BASE}/household/payroll", json=pay_body, headers=H(owner_tok))
    check("POST /household/payroll", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")

    # 6) GET /api/categories?space_id=... must return 200 (regression check)
    r = requests.get(f"{BASE}/categories?space_id={space_id}", headers=H(owner_tok))
    check("GET /api/categories after payroll returns 200 (regression)",
          r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")
    if r.status_code == 200:
        cats = r.json()
        wages = next((c for c in cats if c.get("name") == "Staff wages"), None)
        check("GET /categories includes 'Staff wages' category", wages is not None,
              f"category names: {[c.get('name') for c in cats]}")
        if wages:
            check("'Staff wages' category.created_by is non-null",
                  wages.get("created_by") not in (None, ""),
                  f"created_by={wages.get('created_by')}")
            check("'Staff wages' created_by == owner.user_id",
                  wages.get("created_by") == owner_uid,
                  f"created_by={wages.get('created_by')} owner={owner_uid}")

    return summarize(results)


def summarize(results):
    pass_n = sum(1 for _, ok, _ in results if ok)
    fail_n = sum(1 for _, ok, _ in results if not ok)
    print()
    print(f"=== TOTAL: {pass_n}/{pass_n+fail_n} PASS ===")
    if fail_n:
        print("FAILED:")
        for n, ok, d in results:
            if not ok:
                print(f"  - {n} :: {d}")
    return 0 if fail_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
