"""Phase 13 — server.py refactor regression smoke test.

Hits one representative endpoint per refactored module to verify the
split server.py -> core.py + models.py + routes/*.py did not break wiring.

Tests run against http://localhost:8001 (internal preview backend).
"""
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

BASE = os.environ.get("BACKEND_URL", "http://localhost:8001") + "/api"
OWNER_EMAIL = "test@cozii.app"
OWNER_PASS = "test1234"

PASS = 0
FAIL = 0
FAILS: List[str] = []


def check(label: str, ok: bool, extra: str = "") -> bool:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {label}")
        return True
    FAIL += 1
    FAILS.append(f"{label} :: {extra}")
    print(f"  ❌ {label}  -- {extra}")
    return False


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as c:
        # ── 1. AUTH ─────────────────────────────────────────────
        print("\n[1] auth.py")
        r = await c.post("/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASS})
        check("POST /auth/login → 200", r.status_code == 200, r.text[:200])
        if r.status_code != 200:
            return 1
        tok = r.json()["token"]
        owner_id = r.json()["user"]["user_id"]
        H = {"Authorization": f"Bearer {tok}"}

        r = await c.get("/auth/me", headers=H)
        check("GET /auth/me → 200 + email match",
              r.status_code == 200 and r.json().get("email") == OWNER_EMAIL,
              r.text[:200])

        # ── 2. SPACES ───────────────────────────────────────────
        print("\n[2] spaces.py")
        r = await c.get("/spaces", headers=H)
        spaces = r.json() if r.status_code == 200 else []
        check("GET /spaces → 200 + non-empty", r.status_code == 200 and len(spaces) >= 1, r.text[:200])

        # find a household space — the test_credentials seed
        household = next((s for s in spaces if s.get("space_type") == "household"), None)
        roommates = next((s for s in spaces if s.get("space_type") != "household"), None)
        space = household or spaces[0]
        space_id = space["space_id"]
        print(f"     using space_id={space_id} ({space.get('space_type')})")

        # POST a brand-new space
        unique = uuid.uuid4().hex[:6]
        r = await c.post("/spaces", headers=H,
                         json={"name": f"P13 Test {unique}", "space_type": "roommates",
                               "currency": "USD"})
        check("POST /spaces → 200", r.status_code == 200, r.text[:200])
        new_space_id = r.json().get("space_id") if r.status_code == 200 else None

        r = await c.get(f"/spaces/{space_id}/members", headers=H)
        check("GET /spaces/{id}/members → 200 + list",
              r.status_code == 200 and isinstance(r.json(), list), r.text[:200])

        r = await c.get(f"/spaces/{space_id}/my_role", headers=H)
        check("GET /spaces/{id}/my_role → 200 + role",
              r.status_code == 200 and "role" in r.json(), r.text[:200])

        r = await c.patch(f"/spaces/{space_id}/digest-prefs", headers=H,
                          json={"daily_digest_enabled": True, "daily_digest_utc_hour": 8})
        check("PATCH /spaces/{id}/digest-prefs → 200",
              r.status_code == 200 and r.json().get("daily_digest_enabled") is True,
              r.text[:200])

        # ── 3. INVENTORY (categories, items, alerts) ────────────
        print("\n[3] inventory.py")
        r = await c.get(f"/categories?space_id={space_id}", headers=H)
        cats = r.json() if r.status_code == 200 else []
        check("GET /categories → 200 + list", r.status_code == 200 and isinstance(cats, list),
              r.text[:200])

        r = await c.post("/categories", headers=H,
                         json={"space_id": space_id, "name": f"P13 Cat {unique}", "icon": "Star",
                               "tint": "mint", "share_with": [owner_id]})
        check("POST /categories → 200", r.status_code == 200, r.text[:300])
        cat_id = r.json().get("category_id") if r.status_code == 200 else None

        item_id = None
        if cat_id:
            r = await c.post("/items", headers=H,
                             json={"space_id": space_id, "category_id": cat_id,
                                   "name": f"P13 Item {unique}", "price": 12.5,
                                   "status": "available"})
            check("POST /items → 200", r.status_code == 200, r.text[:300])
            item_id = r.json().get("item_id") if r.status_code == 200 else None

        r = await c.get(f"/items?space_id={space_id}", headers=H)
        check("GET /items → 200 + list", r.status_code == 200 and isinstance(r.json(), list),
              r.text[:200])

        if item_id:
            r = await c.patch(f"/items/{item_id}", headers=H, json={"price": 15.0})
            check("PATCH /items/{id} → 200 + price",
                  r.status_code == 200 and r.json().get("price") == 15.0, r.text[:200])

        r = await c.get(f"/inventory/alerts?space_id={space_id}&days_threshold=7", headers=H)
        check("GET /inventory/alerts → 200 + buckets",
              r.status_code == 200 and "low_stock" in r.json() and "totals" in r.json(),
              r.text[:200])

        # ── 4. FINANCE ──────────────────────────────────────────
        print("\n[4] finance.py")
        r = await c.get(f"/balances?space_id={space_id}", headers=H)
        check("GET /balances → 200 + list",
              r.status_code == 200 and isinstance(r.json(), list), r.text[:200])

        r = await c.get(f"/bills?space_id={space_id}", headers=H)
        bills = r.json() if r.status_code == 200 else []
        check("GET /bills → 200 + list",
              r.status_code == 200 and isinstance(bills, list), r.text[:200])

        # create a bill
        r = await c.post("/bills", headers=H,
                         json={"space_id": space_id, "name": f"P13 Bill {unique}",
                               "amount": 100.0, "frequency": "monthly", "due_day": 15})
        check("POST /bills → 200", r.status_code == 200, r.text[:300])
        bill_id = r.json().get("bill_id") if r.status_code == 200 else None

        if bill_id:
            r = await c.post(f"/bills/{bill_id}/pay", headers=H, json={})
            check("POST /bills/{id}/pay → 200",
                  r.status_code == 200 and r.json().get("is_paid_current_period") is True,
                  r.text[:300])

        r = await c.get(f"/agreement?space_id={space_id}", headers=H)
        check("GET /agreement → 200",
              r.status_code == 200, r.text[:200])

        r = await c.get(f"/reports/finance?space_id={space_id}&period=this_month", headers=H)
        check("GET /reports/finance → 200 + totals",
              r.status_code == 200 and "totals" in r.json(), r.text[:200])

        # ── 5. HOUSEHOLD ────────────────────────────────────────
        print("\n[5] household.py")
        r = await c.get(f"/household/roles?space_id={space_id}", headers=H)
        check("GET /household/roles → 200 + 10+ defaults",
              r.status_code == 200 and isinstance(r.json(), list) and len(r.json()) >= 10,
              r.text[:200])

        r = await c.get(f"/household/family?space_id={space_id}", headers=H)
        check("GET /household/family → 200", r.status_code == 200, r.text[:200])

        r = await c.get(f"/household/staff?space_id={space_id}", headers=H)
        staff = r.json() if r.status_code == 200 else []
        check("GET /household/staff → 200 + list",
              r.status_code == 200 and isinstance(staff, list), r.text[:200])

        r = await c.get(f"/household/handbook?space_id={space_id}", headers=H)
        check("GET /household/handbook → 200", r.status_code == 200, r.text[:200])

        today_iso = datetime.now(timezone.utc).date().isoformat()
        r = await c.get(f"/household/tasks?space_id={space_id}&date={today_iso}", headers=H)
        check("GET /household/tasks → 200 + shape",
              r.status_code == 200 and "tasks" in r.json(),
              r.text[:200])

        # Phase 12.1: owner POST /household/shopping → auto-approved
        r = await c.post("/household/shopping", headers=H,
                         json={"space_id": space_id, "item_name": f"P13 Auto {unique}",
                               "quantity": "1", "urgency": "normal", "kind": "request"})
        body = r.json() if r.status_code == 200 else {}
        check("POST /household/shopping (owner) → status='approved' (Phase 12.1)",
              r.status_code == 200 and body.get("status") == "approved"
              and body.get("approved_by") == owner_id,
              f"status={body.get('status')} approved_by={body.get('approved_by')} resp={r.text[:200]}")

        r = await c.get(f"/household/shortcuts?space_id={space_id}", headers=H)
        check("GET /household/shortcuts → 200",
              r.status_code == 200 and isinstance(r.json(), list), r.text[:200])

        r = await c.get(f"/household/attendance?space_id={space_id}&date_from={today_iso}&date_to={today_iso}",
                        headers=H)
        check("GET /household/attendance → 200",
              r.status_code == 200 and isinstance(r.json(), list), r.text[:200])

        r = await c.get(f"/household/counts?space_id={space_id}", headers=H)
        check("GET /household/counts → 200 + dict",
              r.status_code == 200 and isinstance(r.json(), dict), r.text[:200])

        # ── 6. DOCUMENTS ────────────────────────────────────────
        print("\n[6] documents.py")
        r = await c.get(f"/documents?space_id={space_id}", headers=H)
        check("GET /documents → 200", r.status_code == 200, r.text[:200])

        r = await c.get(f"/documents/folders?space_id={space_id}", headers=H)
        check("GET /documents/folders → 200",
              r.status_code == 200, r.text[:200])

        # ── 7. NOTIFICATIONS ────────────────────────────────────
        print("\n[7] notifications.py")
        r = await c.get("/notifications", headers=H)
        notifs = r.json() if r.status_code == 200 else []
        check("GET /notifications → 200 + list",
              r.status_code == 200 and isinstance(notifs, list), r.text[:200])

        r = await c.post("/notifications/read_all", headers=H, json={})
        check("POST /notifications/read_all → 200",
              r.status_code == 200, r.text[:200])

        # ── 8. CONTRACTS ────────────────────────────────────────
        print("\n[8] contracts.py")
        r = await c.get("/contract-templates", headers=H)
        tpls = r.json() if r.status_code == 200 else []
        check("GET /contract-templates → 200 + 4 templates",
              r.status_code == 200 and isinstance(tpls, list) and len(tpls) >= 4, r.text[:200])

        # Full lifecycle attempt (skip if no household space)
        contract_id = None
        if household:
            hid = household["space_id"]
            r = await c.get(f"/contracts?space_id={hid}", headers=H)
            check("GET /contracts (household) → 200",
                  r.status_code == 200, r.text[:200])

            r = await c.get(f"/household/staff?space_id={hid}", headers=H)
            hstaff = r.json() if r.status_code == 200 else []
            if hstaff:
                sid = hstaff[0]["staff_id"]
                r = await c.post("/contracts", headers=H,
                                 json={"space_id": hid, "template_kind": "blank",
                                       "title": f"P13 contract {unique}",
                                       "body": "Test body — refactor smoke.",
                                       "assigned_staff_id": sid,
                                       "require_owner_signature": True,
                                       "require_drawn_signature_owner": False,
                                       "require_staff_signature": False,
                                       "require_drawn_signature_staff": False})
                check("POST /contracts (owner) → 200",
                      r.status_code == 200 and "contract_id" in r.json(),
                      r.text[:300])
                contract_id = r.json().get("contract_id") if r.status_code == 200 else None

                if contract_id:
                    r = await c.post(f"/contracts/{contract_id}/sign", headers=H,
                                     json={"typed_name": "Test User"})
                    check("POST /contracts/{id}/sign (owner) → 200",
                          r.status_code == 200, r.text[:300])

                    r = await c.delete(f"/contracts/{contract_id}", headers=H)
                    check("DELETE /contracts/{id} → 200",
                          r.status_code == 200, r.text[:200])

        # ── 9. REPORTS ──────────────────────────────────────────
        print("\n[9] reports.py")
        if household:
            hid = household["space_id"]
            now = datetime.now(timezone.utc)
            r = await c.get(f"/reports/household?space_id={hid}&year={now.year}&month={now.month}",
                            headers=H)
            check("GET /reports/household → 200 + shape",
                  r.status_code == 200 and "total_spent" in r.json() and "staff" in r.json(),
                  r.text[:200])

            r = await c.get(f"/household/export?space_id={hid}", headers=H)
            check("GET /household/export → 200",
                  r.status_code == 200, r.text[:200])

        # ── 10. PUSH ────────────────────────────────────────────
        print("\n[10] push.py")
        fake_token = f"ExponentPushToken[P13-{unique}]"
        r = await c.post("/users/push-token", headers=H,
                         json={"token": fake_token, "platform": "ios", "device_name": "P13 device"})
        check("POST /users/push-token → 200",
              r.status_code == 200 and r.json().get("ok") is True, r.text[:200])

        r = await c.get("/users/notification-prefs", headers=H)
        check("GET /users/notification-prefs → 200 + keys",
              r.status_code == 200 and "daily_digest" in r.json()
              and "important_alerts" in r.json(),
              r.text[:200])

        r = await c.put("/users/notification-prefs", headers=H,
                        json={"daily_digest": True, "important_alerts": True})
        check("PUT /users/notification-prefs → 200",
              r.status_code == 200, r.text[:200])

        r = await c.post("/users/push-test", headers=H, json={})
        check("POST /users/push-test → 200 + sent flag",
              r.status_code == 200 and "sent" in r.json(),
              r.text[:200])

        r = await c.delete(f"/users/push-token?token={fake_token}", headers=H)
        check("DELETE /users/push-token → 200",
              r.status_code == 200 and r.json().get("ok") is True, r.text[:200])

        # ── 11. MISC ────────────────────────────────────────────
        print("\n[11] misc.py")
        r = await c.get("/")
        check("GET /api/ → 200",
              r.status_code == 200, r.text[:200])

        r = await c.get(f"/activity?space_id={space_id}", headers=H)
        check("GET /activity → 200 + list",
              r.status_code == 200 and isinstance(r.json(), list), r.text[:200])

        r = await c.get(f"/stats?space_id={space_id}", headers=H)
        check("GET /stats → 200 + dict",
              r.status_code == 200 and isinstance(r.json(), dict), r.text[:200])

        # ── 12. SOCKET.IO real-time ─────────────────────────────
        print("\n[12] Socket.IO real-time (core.sio + record_activity emit spot-check)")
        try:
            import socketio
            sio_client = socketio.AsyncClient(reconnection=False)
            hello_payload = {}

            @sio_client.on("hello")
            async def _on_hello(d):
                hello_payload.update(d if isinstance(d, dict) else {})

            await sio_client.connect("http://localhost:8001",
                                     socketio_path="/api/socket.io",
                                     auth={"token": tok},
                                     wait_timeout=10)
            check("socket.io connect → ok", sio_client.connected, "")

            # wait briefly for hello
            for _ in range(20):
                if hello_payload:
                    break
                await asyncio.sleep(0.1)
            check("socket.io hello event received",
                  hello_payload.get("user_id") == owner_id,
                  json.dumps(hello_payload)[:200])

            # spot-check record_activity DB row written
            r = await c.get(f"/activity?space_id={space_id}", headers=H)
            check("activity log rows present after recent writes",
                  r.status_code == 200 and isinstance(r.json(), list)
                  and len(r.json()) >= 1,
                  r.text[:200])

            await sio_client.disconnect()
        except Exception as e:
            check("socket.io connect/hello", False, repr(e))

        # ── 13. NOTIFY_USER → push noop without tokens ──────────
        # We registered a fake token earlier and deleted it. Trigger
        # notify_user via a benign contract creation/delete already covered.
        # Just verify push-test returns sent=false on no tokens (no 500).
        r = await c.post("/users/push-test", headers=H, json={})
        check("POST /users/push-test after delete → 200 (no 500)",
              r.status_code == 200, r.text[:200])

        # ── CLEANUP ─────────────────────────────────────────────
        if item_id:
            await c.delete(f"/items/{item_id}", headers=H)
        if cat_id:
            await c.delete(f"/categories/{cat_id}", headers=H)
        if bill_id:
            await c.delete(f"/bills/{bill_id}", headers=H)

    print(f"\n========== Phase 13 smoke regression: {PASS} PASS / {FAIL} FAIL ==========")
    if FAILS:
        print("\nFailures:")
        for f in FAILS:
            print("  -", f)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
