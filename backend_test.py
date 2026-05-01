"""
Cozii Household Phase 1 Backend Tests.

Focus: new endpoints only.
- Space type field (POST/PATCH/GET /api/spaces)
- Roles      /api/household/roles
- Family     /api/household/family
- Staff      /api/household/staff
- Handbook   /api/household/handbook
"""
import os
import time
import uuid
import json
import requests

BASE = "https://family-wallet-21.preview.emergentagent.com/api"

PRIMARY_EMAIL = "test@cozii.app"
PRIMARY_PASSWORD = "test1234"


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def login(email, password):
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": email, "password": password}, timeout=30)
    r.raise_for_status()
    return r.json()["token"], r.json()["user"]


def register(email, password, name):
    r = requests.post(f"{BASE}/auth/register",
                      json={"email": email, "password": password, "name": name},
                      timeout=30)
    r.raise_for_status()
    return r.json()["token"], r.json()["user"]


results = []


def rec(section, name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results.append((section, name, ok, detail))
    print(f"[{status}] [{section}] {name}  {detail if not ok else ''}")


# -------- 1. Space type field --------
def test_space_type(token):
    S = "SpaceType"
    r = requests.post(f"{BASE}/spaces",
                      headers=_auth_header(token),
                      json={"name": "Big Home", "currency": "IDR", "space_type": "household"},
                      timeout=30)
    if r.status_code != 200:
        rec(S, "POST /spaces {space_type: household}", False,
            f"status={r.status_code} body={r.text[:200]}")
        household_space_id = None
    else:
        body = r.json()
        ok = body.get("space_type") == "household" and body.get("currency") == "IDR"
        rec(S, "POST /spaces {space_type: household}", ok, f"body={body}")
        household_space_id = body.get("space_id")

    r = requests.post(f"{BASE}/spaces",
                      headers=_auth_header(token),
                      json={"name": "Default Space " + uuid.uuid4().hex[:4]},
                      timeout=30)
    default_space_id = None
    if r.status_code != 200:
        rec(S, "POST /spaces (no space_type) defaults to roommates", False,
            f"status={r.status_code} body={r.text[:200]}")
    else:
        body = r.json()
        rec(S, "POST /spaces (no space_type) defaults to roommates",
            body.get("space_type") == "roommates",
            f"space_type={body.get('space_type')}")
        default_space_id = body.get("space_id")

    target_id = household_space_id or default_space_id
    if target_id:
        r = requests.patch(f"{BASE}/spaces/{target_id}",
                           headers=_auth_header(token),
                           json={"space_type": "HOUSEHOLD"}, timeout=30)
        if r.status_code != 200:
            rec(S, "PATCH /spaces {space_type: HOUSEHOLD} -> 'household'", False,
                f"status={r.status_code} body={r.text[:200]}")
        else:
            body = r.json()
            rec(S, "PATCH /spaces {space_type: HOUSEHOLD} -> 'household'",
                body.get("space_type") == "household",
                f"space_type={body.get('space_type')}")

        before_r = requests.get(f"{BASE}/spaces", headers=_auth_header(token), timeout=30)
        before_val = None
        if before_r.status_code == 200:
            for s in before_r.json():
                if s["space_id"] == target_id:
                    before_val = s.get("space_type")
                    break
        r = requests.patch(f"{BASE}/spaces/{target_id}",
                           headers=_auth_header(token),
                           json={"space_type": "foo"}, timeout=30)
        if r.status_code != 200:
            rec(S, "PATCH /spaces invalid space_type ignored", False,
                f"status={r.status_code} body={r.text[:200]}")
        else:
            body = r.json()
            rec(S, "PATCH /spaces invalid space_type ignored",
                body.get("space_type") == before_val,
                f"before={before_val} after={body.get('space_type')}")

    r = requests.get(f"{BASE}/spaces", headers=_auth_header(token), timeout=30)
    if r.status_code != 200:
        rec(S, "GET /spaces each entry has space_type", False,
            f"status={r.status_code}")
    else:
        spaces = r.json()
        missing = [s["space_id"] for s in spaces if "space_type" not in s]
        rec(S, "GET /spaces each entry has space_type",
            len(missing) == 0 and len(spaces) > 0,
            f"missing in: {missing} count={len(spaces)}")

    return household_space_id


def get_or_make_household_space(token):
    r = requests.get(f"{BASE}/spaces", headers=_auth_header(token), timeout=30)
    if r.status_code == 200 and r.json():
        spaces = r.json()
        for s in spaces:
            if s.get("space_type") == "household":
                return s["space_id"], s.get("currency", "USD")
        s = spaces[0]
        return s["space_id"], s.get("currency", "USD")
    return None, None


def test_roles(token, space_id, non_member_token):
    S = "Roles"

    r = requests.get(f"{BASE}/household/roles",
                     headers=_auth_header(token),
                     params={"space_id": space_id}, timeout=30)
    if r.status_code != 200:
        rec(S, "GET roles auto-seeds 10 defaults", False,
            f"status={r.status_code} body={r.text[:200]}")
        return None
    roles = r.json()
    expected = {"Owner", "Spouse", "Child", "Parent", "Maid", "Driver",
                "Nanny", "Cook", "Gardener", "Security"}
    names = {r_["name"] for r_ in roles}
    ok_default = expected.issubset(names) and all(
        r_["is_default"] for r_ in roles if r_["name"] in expected)
    rec(S, "GET roles auto-seeds 10 defaults (is_default=true)",
        ok_default, f"names={names}")

    child_role_id = next((r_["role_id"] for r_ in roles if r_["name"] == "Child"), None)
    maid_role_id = next((r_["role_id"] for r_ in roles if r_["name"] == "Maid"), None)
    owner_role_id = next((r_["role_id"] for r_ in roles if r_["name"] == "Owner"), None)

    r = requests.post(f"{BASE}/household/roles",
                      headers=_auth_header(token),
                      json={"space_id": space_id, "name": "Tutor",
                            "icon": "BookOpen", "color": "lavender",
                            "category": "staff"}, timeout=30)
    if r.status_code != 200:
        rec(S, "POST custom role Tutor", False,
            f"status={r.status_code} body={r.text[:200]}")
        custom_role_id = None
    else:
        body = r.json()
        ok = (body.get("name") == "Tutor" and body.get("icon") == "BookOpen"
              and body.get("color") == "lavender"
              and body.get("category") == "staff"
              and body.get("is_default") is False)
        rec(S, "POST custom role Tutor (is_default=false)", ok, f"body={body}")
        custom_role_id = body.get("role_id")

    rid_to_patch = custom_role_id or child_role_id
    if rid_to_patch:
        r = requests.patch(f"{BASE}/household/roles/{rid_to_patch}",
                           headers=_auth_header(token),
                           json={"name": "Tutor Sr", "icon": "Star",
                                 "color": "peach"}, timeout=30)
        if r.status_code != 200:
            rec(S, "PATCH role updates name/icon/color", False,
                f"status={r.status_code} body={r.text[:200]}")
        else:
            body = r.json()
            ok = (body.get("name") == "Tutor Sr"
                  and body.get("icon") == "Star"
                  and body.get("color") == "peach")
            rec(S, "PATCH role updates name/icon/color", ok, f"body={body}")

    if owner_role_id:
        r = requests.delete(f"{BASE}/household/roles/{owner_role_id}",
                            headers=_auth_header(token), timeout=30)
        rec(S, "DELETE default role returns 400",
            r.status_code == 400, f"status={r.status_code} body={r.text[:200]}")

    if custom_role_id:
        r = requests.delete(f"{BASE}/household/roles/{custom_role_id}",
                            headers=_auth_header(token), timeout=30)
        ok_del = r.status_code == 200
        r2 = requests.get(f"{BASE}/household/roles",
                          headers=_auth_header(token),
                          params={"space_id": space_id}, timeout=30)
        still_there = False
        if r2.status_code == 200:
            still_there = any(rl["role_id"] == custom_role_id for rl in r2.json())
        rec(S, "DELETE custom role 200 and disappears",
            ok_del and not still_there,
            f"del_status={r.status_code} still_there={still_there}")

    r = requests.get(f"{BASE}/household/roles",
                     headers=_auth_header(non_member_token),
                     params={"space_id": space_id}, timeout=30)
    rec(S, "GET roles as non-member returns 403",
        r.status_code == 403, f"status={r.status_code}")

    return {"child": child_role_id, "maid": maid_role_id}


def test_family(token, space_id, child_role_id, non_member_token):
    S = "Family"

    r = requests.post(f"{BASE}/household/family",
                      headers=_auth_header(token),
                      json={"space_id": space_id, "name": "Maya",
                            "role_id": child_role_id, "age": 8,
                            "school": "Bali Primary",
                            "allergies": "peanuts"}, timeout=30)
    if r.status_code != 200:
        rec(S, "POST family member with role_name resolved", False,
            f"status={r.status_code} body={r.text[:200]}")
        return
    body = r.json()
    ok = (body.get("name") == "Maya" and body.get("age") == 8
          and body.get("school") == "Bali Primary"
          and body.get("allergies") == "peanuts"
          and body.get("role_name") == "Child")
    rec(S, "POST family with role_name resolved", ok, f"body={body}")
    member_id = body.get("member_id")

    r = requests.get(f"{BASE}/household/family",
                     headers=_auth_header(token),
                     params={"space_id": space_id}, timeout=30)
    ok = (r.status_code == 200
          and any(m["member_id"] == member_id and m.get("role_name") == "Child"
                  for m in (r.json() if r.status_code == 200 else [])))
    rec(S, "GET family list returns new member with role_name", ok,
        f"status={r.status_code}")

    photo = "data:image/png;base64,iVBORw0KGgo"
    r = requests.patch(f"{BASE}/household/family/{member_id}",
                       headers=_auth_header(token),
                       json={"name": "Maya Chen", "photo_base64": photo},
                       timeout=30)
    ok = (r.status_code == 200
          and r.json().get("name") == "Maya Chen"
          and r.json().get("photo_base64") == photo)
    rec(S, "PATCH family update name + photo_base64", ok,
        f"status={r.status_code}")

    r = requests.delete(f"{BASE}/household/family/{member_id}",
                        headers=_auth_header(token), timeout=30)
    ok_del = r.status_code == 200
    r2 = requests.get(f"{BASE}/household/family",
                      headers=_auth_header(token),
                      params={"space_id": space_id}, timeout=30)
    still = any(m["member_id"] == member_id for m in r2.json()) if r2.status_code == 200 else True
    rec(S, "DELETE family removes it", ok_del and not still,
        f"del_status={r.status_code} still={still}")

    r = requests.get(f"{BASE}/household/family",
                     headers=_auth_header(non_member_token),
                     params={"space_id": space_id}, timeout=30)
    rec(S, "GET family as non-member returns 403",
        r.status_code == 403, f"status={r.status_code}")


def test_staff(token, space_id, maid_role_id, space_currency, non_member_token):
    S = "Staff"

    r = requests.post(f"{BASE}/household/staff",
                      headers=_auth_header(token),
                      json={"space_id": space_id, "name": "Mbak Rina",
                            "role_id": maid_role_id, "salary": 3500000,
                            "pay_cycle": "monthly", "off_day": "Sunday"},
                      timeout=30)
    if r.status_code != 200:
        rec(S, "POST staff with role + salary + off_day", False,
            f"status={r.status_code} body={r.text[:200]}")
        return
    body = r.json()
    ok = (body.get("name") == "Mbak Rina" and body.get("salary") == 3500000
          and body.get("pay_cycle") == "monthly"
          and body.get("off_day") == "Sunday"
          and body.get("role_name") == "Maid"
          and body.get("salary_currency") == space_currency)
    rec(S, f"POST staff (salary_currency defaults to space.currency='{space_currency}')",
        ok, f"body={body}")
    staff_id = body.get("staff_id")

    r = requests.get(f"{BASE}/household/staff",
                     headers=_auth_header(token),
                     params={"space_id": space_id}, timeout=30)
    ok = (r.status_code == 200
          and any(s["staff_id"] == staff_id and s.get("role_name") == "Maid"
                  for s in (r.json() if r.status_code == 200 else [])))
    rec(S, "GET staff list returns new staff with role_name", ok,
        f"status={r.status_code}")

    r = requests.patch(f"{BASE}/household/staff/{staff_id}",
                       headers=_auth_header(token),
                       json={"phone": "+62-812-0000-1234",
                             "notes": "Reliable, speaks English"},
                       timeout=30)
    ok = (r.status_code == 200
          and r.json().get("phone") == "+62-812-0000-1234"
          and r.json().get("notes") == "Reliable, speaks English")
    rec(S, "PATCH staff phone + notes", ok, f"status={r.status_code}")

    r = requests.delete(f"{BASE}/household/staff/{staff_id}",
                        headers=_auth_header(token), timeout=30)
    ok_del = r.status_code == 200
    r2 = requests.get(f"{BASE}/household/staff",
                      headers=_auth_header(token),
                      params={"space_id": space_id}, timeout=30)
    still = any(s["staff_id"] == staff_id for s in r2.json()) if r2.status_code == 200 else True
    rec(S, "DELETE staff removes it", ok_del and not still,
        f"del_status={r.status_code} still={still}")

    r = requests.get(f"{BASE}/household/staff",
                     headers=_auth_header(non_member_token),
                     params={"space_id": space_id}, timeout=30)
    rec(S, "GET staff as non-member returns 403",
        r.status_code == 403, f"status={r.status_code}")


def test_handbook(token, space_id, non_member_token):
    S = "Handbook"

    r = requests.post(f"{BASE}/household/handbook",
                      headers=_auth_header(token),
                      json={"space_id": space_id, "title": "Wifi",
                            "body": "Network: HomeNet\nPassword: 12345",
                            "icon": "Star", "color": "sage"}, timeout=30)
    if r.status_code != 200:
        rec(S, "POST handbook entry", False,
            f"status={r.status_code} body={r.text[:200]}")
        return
    body = r.json()
    ok = (body.get("title") == "Wifi"
          and body.get("body") == "Network: HomeNet\nPassword: 12345"
          and body.get("icon") == "Star"
          and body.get("color") == "sage"
          and body.get("sort") == 0)
    rec(S, "POST handbook entry (sort defaults 0)", ok, f"body={body}")
    entry_id = body.get("entry_id")
    created_updated_at = body.get("updated_at")

    r = requests.get(f"{BASE}/household/handbook",
                     headers=_auth_header(token),
                     params={"space_id": space_id}, timeout=30)
    ok = (r.status_code == 200
          and any(e["entry_id"] == entry_id for e in r.json()))
    rec(S, "GET handbook list includes entry", ok,
        f"status={r.status_code}")

    time.sleep(1.1)
    r = requests.patch(f"{BASE}/household/handbook/{entry_id}",
                       headers=_auth_header(token),
                       json={"title": "Wifi (Guest)",
                             "body": "Network: HomeNet-Guest\nPassword: guest123"},
                       timeout=30)
    if r.status_code != 200:
        rec(S, "PATCH handbook title/body updates updated_at", False,
            f"status={r.status_code} body={r.text[:200]}")
    else:
        body = r.json()
        ok = (body.get("title") == "Wifi (Guest)"
              and body.get("body") == "Network: HomeNet-Guest\nPassword: guest123"
              and body.get("updated_at") != created_updated_at)
        rec(S, "PATCH handbook title/body updates updated_at", ok,
            f"before={created_updated_at} after={body.get('updated_at')}")

    r = requests.delete(f"{BASE}/household/handbook/{entry_id}",
                        headers=_auth_header(token), timeout=30)
    ok_del = r.status_code == 200
    r2 = requests.get(f"{BASE}/household/handbook",
                      headers=_auth_header(token),
                      params={"space_id": space_id}, timeout=30)
    still = any(e["entry_id"] == entry_id for e in r2.json()) if r2.status_code == 200 else True
    rec(S, "DELETE handbook removes it", ok_del and not still,
        f"del_status={r.status_code} still={still}")

    r = requests.get(f"{BASE}/household/handbook",
                     headers=_auth_header(non_member_token),
                     params={"space_id": space_id}, timeout=30)
    rec(S, "GET handbook as non-member returns 403",
        r.status_code == 403, f"status={r.status_code}")


def main():
    token, _ = login(PRIMARY_EMAIL, PRIMARY_PASSWORD)

    stamp = uuid.uuid4().hex[:6]
    nm_token, _ = register(f"outsider_{stamp}@example.com", "outside1234",
                           "Outsider Nolan")

    household_space_id_from_test = test_space_type(token)

    space_id, currency = get_or_make_household_space(token)
    if household_space_id_from_test:
        space_id = household_space_id_from_test
        currency = "IDR"
    if not space_id:
        print("Cannot continue - no space_id available for household tests")
        return

    print(f"\nUsing space_id={space_id} currency={currency} for household tests\n")

    role_ids = test_roles(token, space_id, nm_token)
    if not role_ids:
        role_ids = {"child": None, "maid": None}

    test_family(token, space_id, role_ids["child"], nm_token)
    test_staff(token, space_id, role_ids["maid"], currency, nm_token)
    test_handbook(token, space_id, nm_token)

    total = len(results)
    failed = [r for r in results if not r[2]]
    print("\n==== SUMMARY ====")
    print(f"Total: {total}  Passed: {total - len(failed)}  Failed: {len(failed)}")
    for sec, name, ok, detail in failed:
        print(f"  FAIL [{sec}] {name} :: {detail}")


if __name__ == "__main__":
    main()
