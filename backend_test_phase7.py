"""
Phase 7 backend tests for Cozii household:
  1) Shopping: price + photo + notifications
  2) Shopping status transitions (approve / reject / purchase)
  3) Task completion photo enforcement + annotate
  4) Household counts
  5) Quick task notification regression
"""
import os
import time
import uuid
import json
import sys
import requests

BASE = "https://family-wallet-21.preview.emergentagent.com/api"

PNG_DATA_URI = "data:image/jpeg;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII="

PASS = []
FAIL = []


def ok(msg):
    print(f"PASS  {msg}")
    PASS.append(msg)


def bad(msg, detail=""):
    print(f"FAIL  {msg}{(' :: ' + detail) if detail else ''}")
    FAIL.append(f"{msg}: {detail}")


def post(path, token=None, json_body=None, params=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.post(f"{BASE}{path}", headers=headers, json=json_body or {}, params=params, timeout=30)


def get(path, token=None, params=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.get(f"{BASE}{path}", headers=headers, params=params, timeout=30)


def patch(path, token=None, json_body=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return requests.patch(f"{BASE}{path}", headers=headers, json=json_body or {}, timeout=30)


def register(name, email_prefix):
    email = f"{email_prefix}_{uuid.uuid4().hex[:6]}@cozii.app"
    r = post("/auth/register", json_body={"email": email, "password": "test1234", "name": name})
    if r.status_code != 200:
        raise SystemExit(f"register failed: {r.status_code} {r.text}")
    return r.json()["token"], r.json()["user"], email


def main():
    print(f"BASE={BASE}")
    # ------- setup users + space -------
    owner_tk, owner_u, _ = register("Anya Sharma", "owner")
    staff_tk, staff_u, _ = register("Sari Putri", "staff")
    nonmember_tk, nonmember_u, _ = register("Outsider Carl", "outsider")

    r = post("/spaces", owner_tk, {"name": "Sharma Household", "space_type": "household", "currency": "IDR"})
    if r.status_code != 200:
        bad("create household space", f"{r.status_code} {r.text}")
        return finish()
    space = r.json()
    space_id = space["space_id"]
    if space.get("currency") != "IDR" or space.get("space_type") != "household":
        bad("space currency/type wrong", str(space))
    else:
        ok("create household space (IDR)")

    # roles for staff role
    r = get("/household/roles", owner_tk, {"space_id": space_id})
    role_id = next((x["role_id"] for x in r.json() if x.get("key") == "maid"), None)

    # create staff
    r = post("/household/staff", owner_tk, {
        "space_id": space_id,
        "name": "Sari Putri",
        "role_id": role_id,
        "salary": 2500000,
        "pay_cycle": "monthly",
        "off_day": "sunday",
    })
    if r.status_code != 200:
        bad("create staff", f"{r.status_code} {r.text}")
        return finish()
    staff = r.json()
    staff_id = staff["staff_id"]
    invite_code = staff.get("invite_code")
    if not invite_code:
        bad("staff invite_code missing", json.dumps(staff))
        return finish()
    ok(f"create staff (invite_code={invite_code})")

    # staff joins via invite code
    r = post("/household/staff/join", staff_tk, {"invite_code": invite_code})
    if r.status_code != 200:
        bad("staff join", f"{r.status_code} {r.text}")
        return finish()
    ok("staff joined household via invite code")

    # ============================================================
    # 1) Shopping: price + photo + notifications
    # ============================================================
    print("\n=== 1) Shopping create with price + photo ===")
    r = post("/household/shopping", staff_tk, {
        "space_id": space_id,
        "item_name": "Rice",
        "quantity": "5 kg",
        "estimated_price": 50000,
        "photo_base64": PNG_DATA_URI,
        "requested_by_staff_id": staff_id,
        "urgency": "high",
    })
    if r.status_code != 200:
        bad("POST /household/shopping (Rice)", f"{r.status_code} {r.text}")
        return finish()
    rice = r.json()
    if rice.get("estimated_price") != 50000:
        bad("estimated_price mismatch", str(rice.get("estimated_price")))
    else:
        ok("estimated_price=50000 returned")
    if rice.get("photo_base64") != PNG_DATA_URI:
        bad("photo_base64 not preserved", str(rice.get("photo_base64"))[:80])
    else:
        ok("photo_base64 preserved")
    if rice.get("currency") != "IDR":
        bad("currency mismatch", str(rice.get("currency")))
    else:
        ok("currency=IDR (matches space)")
    if rice.get("status") != "pending":
        bad("status not pending", str(rice.get("status")))
    else:
        ok("status=pending")
    if rice.get("urgency") != "high":
        bad("urgency not high", str(rice.get("urgency")))
    else:
        ok("urgency=high")
    rice_id = rice["request_id"]

    # owner notifications include shopping_request
    r = get("/notifications", owner_tk, {"space_id": space_id})
    if r.status_code != 200:
        bad("GET /notifications owner", f"{r.status_code} {r.text}")
    else:
        notifs = r.json()
        match = [n for n in notifs if n.get("kind") == "shopping_request" and n.get("title") == "Shopping request: Rice"]
        if not match:
            bad("owner shopping_request notification missing",
                f"got titles: {[n.get('title') for n in notifs]}")
        else:
            ok("owner notification 'Shopping request: Rice' present")

    # ============================================================
    # 2) Shopping status transitions
    # ============================================================
    print("\n=== 2) Shopping status transitions ===")
    # Approve the rice request
    r = patch(f"/household/shopping/{rice_id}", owner_tk, {"status": "approved"})
    if r.status_code != 200:
        bad("PATCH approved", f"{r.status_code} {r.text}")
    else:
        approved = r.json()
        if not approved.get("approved_at"):
            bad("approved_at not populated", str(approved.get("approved_at")))
        else:
            ok("approved_at populated")
        if approved.get("approved_by") != owner_u["user_id"]:
            bad("approved_by != owner", str(approved.get("approved_by")))
        else:
            ok("approved_by=owner.user_id")

    # staff sees shopping_status notif with title ending '· approved'
    r = get("/notifications", staff_tk, {"space_id": space_id})
    if r.status_code == 200:
        notifs = r.json()
        approved_notifs = [n for n in notifs if n.get("kind") == "shopping_status" and n.get("title", "").endswith("· approved")]
        if not approved_notifs:
            bad("staff shopping_status (approved) notif missing",
                f"got: {[n.get('title') for n in notifs if n.get('kind') == 'shopping_status']}")
        else:
            ok(f"staff sees shopping_status notif '{approved_notifs[0]['title']}'")

    # Create a new pending request to reject
    r = post("/household/shopping", staff_tk, {
        "space_id": space_id,
        "item_name": "Premium Caviar",
        "quantity": "200g",
        "estimated_price": 8000000,
        "requested_by_staff_id": staff_id,
        "urgency": "low",
    })
    if r.status_code != 200:
        bad("create caviar request", f"{r.status_code} {r.text}")
    else:
        caviar = r.json()
        cav_id = caviar["request_id"]
        r = patch(f"/household/shopping/{cav_id}", owner_tk, {"status": "rejected", "rejected_reason": "too expensive"})
        if r.status_code != 200:
            bad("PATCH rejected", f"{r.status_code} {r.text}")
        else:
            rej = r.json()
            if rej.get("rejected_reason") != "too expensive":
                bad("rejected_reason not stored", str(rej.get("rejected_reason")))
            else:
                ok("rejected_reason='too expensive' stored")
        # staff notif body mentions reason
        r = get("/notifications", staff_tk, {"space_id": space_id})
        if r.status_code == 200:
            cav_notifs = [n for n in r.json() if n.get("kind") == "shopping_status" and "Caviar" in (n.get("title") or "")]
            if not cav_notifs:
                bad("staff rejection notif missing")
            else:
                body_text = cav_notifs[0].get("body") or ""
                if "too expensive" not in body_text:
                    bad("rejection notif body missing reason", body_text)
                else:
                    ok("staff rejection notif body mentions reason")

    # purchase the rice
    r = post(f"/household/shopping/{rice_id}/purchase", owner_tk, {
        "actual_price": 55000,
        "note": "bought at supermarket",
    })
    if r.status_code != 200:
        bad("POST /shopping/{id}/purchase", f"{r.status_code} {r.text}")
    else:
        purch = r.json()
        if purch.get("status") != "purchased":
            bad("status not purchased", str(purch.get("status")))
        else:
            ok("status=purchased after purchase endpoint")
        if not purch.get("purchased_at"):
            bad("purchased_at missing")
        else:
            ok("purchased_at populated")
        if purch.get("actual_price") != 55000:
            bad("actual_price wrong", str(purch.get("actual_price")))
        else:
            ok("actual_price=55000 stored")
        note = purch.get("note") or ""
        if "[Purchase]" not in note or "bought at supermarket" not in note:
            bad("note not appended with [Purchase] prefix", note)
        else:
            ok("note appended with [Purchase] prefix")

    # requester (staff) gets Purchased: Rice notif
    r = get("/notifications", staff_tk, {"space_id": space_id})
    if r.status_code == 200:
        purch_notifs = [n for n in r.json() if n.get("title") == "Purchased: Rice"]
        if not purch_notifs:
            bad("staff Purchased: Rice notif missing",
                f"titles: {[n.get('title') for n in r.json()]}")
        else:
            ok("requester notif titled 'Purchased: Rice' received")

    # ============================================================
    # 3) Task completion photo enforcement
    # ============================================================
    print("\n=== 3) Task completion photo enforcement ===")
    r = post("/household/tasks", owner_tk, {
        "space_id": space_id,
        "title": "Clean kitchen",
        "staff_id": staff_id,
        "recurrence": "daily",
        "requires_photo": True,
    })
    if r.status_code != 200:
        bad("POST /household/tasks", f"{r.status_code} {r.text}")
        return finish()
    task = r.json()
    task_id = task["task_id"]
    if not task.get("requires_photo"):
        bad("requires_photo not set on task", str(task))
    else:
        ok("create task with requires_photo=true")

    # complete with no photo → 400
    r = post(f"/household/tasks/{task_id}/complete", staff_tk, {})
    if r.status_code != 400:
        bad("complete without photo should be 400", f"{r.status_code} {r.text}")
    else:
        msg = ""
        try:
            msg = r.json().get("detail", "")
        except Exception:
            msg = r.text
        if "requires a photo" not in msg:
            bad("400 message missing 'requires a photo'", msg)
        else:
            ok("400 with 'requires a photo' message")

    # complete with photo → 200
    r = post(f"/household/tasks/{task_id}/complete", staff_tk, {"photo_base64": PNG_DATA_URI})
    if r.status_code != 200:
        bad("complete with photo failed", f"{r.status_code} {r.text}")
        return finish()
    completion_id = r.json().get("completion_id")
    if not completion_id:
        bad("completion_id missing in response")
        return finish()
    ok("completed task with photo (200)")

    # verify completion stored has staff link & name
    r = get("/household/completions", owner_tk, {"space_id": space_id, "task_id": task_id})
    if r.status_code == 200:
        comps = r.json()
        target = next((c for c in comps if c.get("completion_id") == completion_id), None)
        if not target:
            bad("completion not in list", str(comps))
        else:
            if target.get("staff_id") != staff_id:
                bad("completion.staff_id mismatch", str(target.get("staff_id")))
            else:
                ok("completion.staff_id linked to staff")
            if target.get("completed_by_name") != "Sari Putri":
                bad("completed_by_name not staff name", str(target.get("completed_by_name")))
            else:
                ok("completed_by_name='Sari Putri'")

    # owner gets task_done notif
    r = get("/notifications", owner_tk, {"space_id": space_id})
    if r.status_code == 200:
        td = [n for n in r.json() if n.get("kind") == "task_done"]
        if not td:
            bad("owner task_done notif missing")
        else:
            ok(f"owner task_done notif present ('{td[0].get('title')}')")

    # owner annotate completion
    r = patch(f"/household/completions/{completion_id}/annotate", owner_tk, {"owner_note": "Great job"})
    if r.status_code != 200:
        bad("PATCH annotate", f"{r.status_code} {r.text}")
    else:
        ok("PATCH /completions/{id}/annotate (owner_note='Great job')")

    # staff gets task_comment notif with body containing 'Great job'
    r = get("/notifications", staff_tk, {"space_id": space_id})
    if r.status_code == 200:
        tcs = [n for n in r.json() if n.get("kind") == "task_comment"]
        if not tcs:
            bad("staff task_comment notif missing")
        else:
            body_text = tcs[0].get("body") or ""
            if "Great job" not in body_text:
                bad("task_comment body missing 'Great job'", body_text)
            else:
                ok("staff task_comment notif body contains 'Great job'")

    # ============================================================
    # 4) Household counts
    # ============================================================
    print("\n=== 4) Household counts ===")
    # First snapshot baseline counts
    r = get("/household/counts", owner_tk, {"space_id": space_id})
    if r.status_code != 200:
        bad("GET /household/counts", f"{r.status_code} {r.text}")
    else:
        counts = r.json()
        for k in ("shopping_pending", "shopping_approved", "tasks_open_today"):
            if k not in counts or not isinstance(counts[k], int):
                bad(f"counts.{k} missing or not int", str(counts))
                break
        else:
            ok(f"counts shape ok (pending={counts['shopping_pending']}, "
               f"approved={counts['shopping_approved']}, "
               f"tasks_open_today={counts['tasks_open_today']})")
        baseline = counts

    # Create another pending shopping request and a non-completed daily task → check increments
    r = post("/household/shopping", staff_tk, {
        "space_id": space_id,
        "item_name": "Detergent",
        "quantity": "1",
        "requested_by_staff_id": staff_id,
        "urgency": "normal",
    })
    if r.status_code != 200:
        bad("create detergent shopping", f"{r.status_code} {r.text}")

    r = post("/household/tasks", owner_tk, {
        "space_id": space_id,
        "title": "Sweep porch",
        "staff_id": staff_id,
        "recurrence": "daily",
    })
    if r.status_code != 200:
        bad("create extra daily task", f"{r.status_code} {r.text}")

    r = get("/household/counts", owner_tk, {"space_id": space_id})
    if r.status_code == 200:
        new_counts = r.json()
        if new_counts["shopping_pending"] < baseline["shopping_pending"] + 1:
            bad("shopping_pending did not increment",
                f"{baseline['shopping_pending']} -> {new_counts['shopping_pending']}")
        else:
            ok(f"shopping_pending incremented ({baseline['shopping_pending']} -> {new_counts['shopping_pending']})")
        # tasks_open_today: at least baseline+1 (the new daily task)
        if new_counts["tasks_open_today"] < baseline["tasks_open_today"] + 1:
            bad("tasks_open_today did not increment",
                f"{baseline['tasks_open_today']} -> {new_counts['tasks_open_today']}")
        else:
            ok(f"tasks_open_today incremented ({baseline['tasks_open_today']} -> {new_counts['tasks_open_today']})")
        # shopping_approved: should still be 0 (we approved+purchased rice → not approved anymore)
        # No assertion needed beyond integer type.

    # Non-member → 403
    r = get("/household/counts", nonmember_tk, {"space_id": space_id})
    if r.status_code != 403:
        bad("non-member /counts not 403", f"{r.status_code} {r.text}")
    else:
        ok("non-member GET /household/counts → 403")

    # ============================================================
    # 5) Quick task notification regression
    # ============================================================
    print("\n=== 5) Quick task notification regression ===")
    r = post("/household/tasks/quick", owner_tk, {
        "space_id": space_id,
        "staff_id": staff_id,
        "title": "Take out trash",
    })
    if r.status_code != 200:
        bad("POST /household/tasks/quick", f"{r.status_code} {r.text}")
    else:
        ok("quick task created")
        time.sleep(0.5)
        r = get("/notifications", staff_tk, {"space_id": space_id})
        if r.status_code == 200:
            qn = [n for n in r.json() if n.get("kind") == "task_assigned" and n.get("title") == "Quick task: Take out trash"]
            if not qn:
                bad("quick-task notification missing")
            else:
                ok("staff received 'Quick task: Take out trash' notification")

    return finish()


def finish():
    print("\n" + "=" * 60)
    print(f"PASSED: {len(PASS)}  FAILED: {len(FAIL)}")
    if FAIL:
        print("\nFailures:")
        for f in FAIL:
            print(f"  - {f}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
