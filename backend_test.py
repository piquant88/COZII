"""
Phase 12.1 backend test — Owner shopping request auto-approval.

Endpoint under test: POST /api/household/shopping
Spec:
  - Owner (space.owner_id == user.user_id) → status="approved",
    approved_by=owner.user_id, approved_at != null
  - Non-owner (member or staff) → status="pending",
    approved_by=null, approved_at=null
Applies to BOTH kind="request" (default) AND kind="reimbursement".

Plus: regression on PATCH/purchase pipeline of an already-approved owner request.
"""

from __future__ import annotations
import os
import sys
import uuid
import requests
from typing import Any, Dict, Optional, Tuple

BASE = os.environ.get(
    "EXPO_PUBLIC_BACKEND_URL",
    "https://family-wallet-21.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE}/api"

OWNER_EMAIL = "test@cozii.app"
OWNER_PASSWORDS_TO_TRY = ["test1234", "Robot1"]
HOUSEHOLD_SPACE_ID = "space_8784d76aee6d4c56"  # per test_credentials.md

results: list[Tuple[str, bool, str]] = []


def log(name: str, ok: bool, detail: str = ""):
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}{(' :: ' + detail) if detail else ''}")
    results.append((name, ok, detail))


def post(path: str, json_body: Any = None, token: Optional[str] = None) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.post(f"{API}{path}", json=json_body, headers=headers, timeout=30)


def get(path: str, token: Optional[str] = None) -> requests.Response:
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.get(f"{API}{path}", headers=headers, timeout=30)


def patch(path: str, json_body: Any = None, token: Optional[str] = None) -> requests.Response:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return requests.patch(f"{API}{path}", json=json_body, headers=headers, timeout=30)


def login(email: str, password: str) -> Optional[Tuple[str, str]]:
    r = post("/auth/login", {"email": email, "password": password})
    if r.status_code == 200:
        data = r.json()
        return data["token"], data["user"]["user_id"]
    return None


def register(email: str, password: str, name: str) -> Tuple[str, str]:
    r = post("/auth/register", {"email": email, "password": password, "name": name})
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    data = r.json()
    return data["token"], data["user"]["user_id"]


print(f"Backend: {API}")

# 1) Owner login
owner_token: Optional[str] = None
owner_uid: Optional[str] = None
for pw in OWNER_PASSWORDS_TO_TRY:
    res = login(OWNER_EMAIL, pw)
    if res:
        owner_token, owner_uid = res
        print(f"Owner login OK with password '{pw}'  uid={owner_uid}")
        break
assert owner_token, f"Owner login failed for {OWNER_EMAIL} (tried {OWNER_PASSWORDS_TO_TRY})"

# 2) Find a household space owned by this user
sp_resp = get("/spaces", token=owner_token)
assert sp_resp.status_code == 200, sp_resp.text
spaces = sp_resp.json()
print(f"Owner has {len(spaces)} spaces")
for sp in spaces:
    print(f"  - {sp.get('space_id')} name={sp.get('name')!r} type={sp.get('space_type')} owner={sp.get('owner_id')} invite={sp.get('invite_code')}")

household_space: Optional[Dict[str, Any]] = None
for sp in spaces:
    if sp.get("space_id") == HOUSEHOLD_SPACE_ID and sp.get("owner_id") == owner_uid:
        household_space = sp
        break
if household_space is None:
    for sp in spaces:
        if sp.get("owner_id") == owner_uid and sp.get("space_type") == "household":
            household_space = sp
            break
if household_space is None:
    for sp in spaces:
        if sp.get("owner_id") == owner_uid:
            household_space = sp
            break

assert household_space, "Could not find a space owned by the owner account"
SPACE_ID = household_space["space_id"]
INVITE_CODE = household_space.get("invite_code")
print(f"Using space_id={SPACE_ID} space_type={household_space.get('space_type')} invite={INVITE_CODE}")
log("Setup: owner-owned space resolved",
    household_space.get("owner_id") == owner_uid,
    f"space_id={SPACE_ID} owner_id={household_space.get('owner_id')}")


# ---------------- Test 1 & 2: Owner request / reimbursement auto-approve ----------------
def assert_owner_approved(label: str, body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    r = post("/household/shopping", body, token=owner_token)
    if r.status_code != 200:
        log(label, False, f"http {r.status_code} :: {r.text[:300]}")
        return None
    j = r.json()
    expected_kind = body.get("kind", "request")
    ok_status = j.get("status") == "approved"
    ok_by = j.get("approved_by") == owner_uid
    ok_at = bool(j.get("approved_at"))
    ok_kind = j.get("kind") == expected_kind
    detail = (
        f"status={j.get('status')} approved_by={j.get('approved_by')} "
        f"approved_at={j.get('approved_at')} kind={j.get('kind')}"
    )
    log(label, ok_status and ok_by and ok_at and ok_kind, detail)
    return j


owner_req = assert_owner_approved(
    "T1: Owner kind=request → status=approved + approved_by + approved_at",
    {
        "space_id": SPACE_ID,
        "kind": "request",
        "item_name": "Detergent",
        "quantity": "1",
        "urgency": "normal",
    },
)

owner_reimb = assert_owner_approved(
    "T2: Owner kind=reimbursement → status=approved + approved_by + approved_at",
    {
        "space_id": SPACE_ID,
        "kind": "reimbursement",
        "item_name": "Eggs",
        "quantity": "1",
        "actual_price": 50000,
    },
)


# ---------------- Test 3: Member (non-owner) → pending ----------------

suffix = uuid.uuid4().hex[:10]
member_email = f"member_{suffix}@cozii.app"
member_password = "Test1234!"
member_name = f"Test Member {suffix[:4]}"
member_token, member_uid = register(member_email, member_password, member_name)
print(f"Registered member uid={member_uid} email={member_email}")

if not INVITE_CODE:
    log("T3-prep: invite_code present on space response", False,
        "GET /spaces did not return invite_code; cannot join member")
else:
    jr = post("/spaces/join", {"invite_code": INVITE_CODE}, token=member_token)
    log("T3-prep: member joins via invite_code",
        jr.status_code == 200,
        f"http {jr.status_code} :: {jr.text[:200]}")

mr = post(
    "/household/shopping",
    {
        "space_id": SPACE_ID,
        "kind": "request",
        "item_name": "Bread",
        "quantity": "2 loaves",
        "urgency": "normal",
    },
    token=member_token,
)
if mr.status_code != 200:
    log("T3: Member request stays pending", False, f"http {mr.status_code} :: {mr.text[:300]}")
    member_req = None
else:
    mj = mr.json()
    ok = (
        mj.get("status") == "pending"
        and mj.get("approved_by") is None
        and mj.get("approved_at") is None
        and mj.get("kind") == "request"
    )
    log(
        "T3: Member request stays pending (approved_by=null, approved_at=null)",
        ok,
        f"status={mj.get('status')} approved_by={mj.get('approved_by')} approved_at={mj.get('approved_at')}",
    )
    member_req = mj


# ---------------- Test 4: Staff (linked via /household/staff/join) → pending ----------------

# Resolve a staff role_id (owner-only POST /household/staff requires it in some envs)
role_id = None
rr = get(f"/household/roles?space_id={SPACE_ID}", token=owner_token)
if rr.status_code == 200:
    roles = rr.json()
    for role in roles:
        if role.get("category") == "staff" or role.get("name", "").lower() in ("maid", "driver", "nanny", "cook", "gardener"):
            role_id = role.get("role_id")
            break
    if not role_id and roles:
        role_id = roles[0].get("role_id")

staff_create_body = {
    "space_id": SPACE_ID,
    "name": f"Phase121 Staff {suffix[:4]}",
    "role_id": role_id,
    "salary": 1000000,
    "salary_currency": "IDR",
    "pay_cycle": "monthly",
}
staff_create = post("/household/staff", staff_create_body, token=owner_token)

if staff_create.status_code != 200:
    log("T4-prep: owner created fresh staff", False,
        f"http {staff_create.status_code} :: {staff_create.text[:300]}")
    staff_doc = None
else:
    staff_doc = staff_create.json()
    log(
        "T4-prep: owner created fresh staff",
        bool(staff_doc.get("invite_code")) and bool(staff_doc.get("staff_id")),
        f"staff_id={staff_doc.get('staff_id')} invite_code={staff_doc.get('invite_code')}",
    )

if staff_doc:
    staff_email = f"staff_{suffix}@cozii.app"
    staff_password = "Test1234!"
    staff_user_token, staff_user_uid = register(staff_email, staff_password, f"Test Staff {suffix[:4]}")
    print(f"Registered staff-user uid={staff_user_uid} email={staff_email}")

    join_resp = post(
        "/household/staff/join",
        {"invite_code": staff_doc["invite_code"]},
        token=staff_user_token,
    )
    log(
        "T4-prep: staff-user joins via /household/staff/join",
        join_resp.status_code == 200,
        f"http {join_resp.status_code} :: {join_resp.text[:200]}",
    )

    sr = post(
        "/household/shopping",
        {
            "space_id": SPACE_ID,
            "kind": "request",
            "item_name": "Toothpaste",
            "quantity": "2",
            "urgency": "low",
            "requested_by_staff_id": staff_doc["staff_id"],
        },
        token=staff_user_token,
    )
    if sr.status_code != 200:
        log("T4: Staff request stays pending", False, f"http {sr.status_code} :: {sr.text[:300]}")
    else:
        sj = sr.json()
        ok = (
            sj.get("status") == "pending"
            and sj.get("approved_by") is None
            and sj.get("approved_at") is None
            and sj.get("requested_by_staff_id") == staff_doc["staff_id"]
        )
        log(
            "T4: Staff cannot self-approve (status=pending, approved_by=null)",
            ok,
            f"status={sj.get('status')} approved_by={sj.get('approved_by')} approved_at={sj.get('approved_at')} staff_id={sj.get('requested_by_staff_id')}",
        )


# ---------------- Test 5: Regression — purchase on owner-approved request ----------------

if owner_req:
    rid = owner_req["request_id"]
    actor_token = member_token  # any space member should be able to mark purchased
    pr = post(
        f"/household/shopping/{rid}/purchase",
        {"actual_price": 25000},
        token=actor_token,
    )
    if pr.status_code == 200:
        pj = pr.json()
        log(
            "T5: POST /shopping/{id}/purchase on owner-approved request → purchased",
            pj.get("status") == "purchased",
            f"status={pj.get('status')} purchased_by={pj.get('purchased_by')} actual_price={pj.get('actual_price')} approved_by_preserved={pj.get('approved_by') == owner_uid}",
        )
    else:
        pr2 = patch(
            f"/household/shopping/{rid}",
            {"status": "purchased", "actual_price": 25000},
            token=actor_token,
        )
        if pr2.status_code == 200:
            pj2 = pr2.json()
            log(
                "T5: PATCH /shopping/{id} status=purchased on owner-approved request → purchased",
                pj2.get("status") == "purchased",
                f"status={pj2.get('status')} purchased_by={pj2.get('purchased_by')}",
            )
        else:
            log(
                "T5: regression — purchase on owner-approved request",
                False,
                f"/purchase http={pr.status_code} :: {pr.text[:200]} | "
                f"PATCH http={pr2.status_code} :: {pr2.text[:200]}",
            )


# ---------------- Summary ----------------

passes = sum(1 for _, ok, _ in results if ok)
fails = sum(1 for _, ok, _ in results if not ok)
print("\n" + "=" * 70)
print(f"Phase 12.1 shopping auto-approve — {passes} passed, {fails} failed")
print("=" * 70)
for name, ok, detail in results:
    print(f"  {'OK ' if ok else 'XX '} {name}  {detail}")

sys.exit(0 if fails == 0 else 1)
