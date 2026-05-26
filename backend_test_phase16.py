"""Phase 16 — Unified Purchase Session backend test.

Validates /api/purchase-sessions endpoints and side-effects on inventory,
audit log, shopping_requests, and activity feed.

Runs against http://localhost:8001 (internal preview backend).
"""
import asyncio
import json
import os
import sys
import time
import uuid
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


async def login(c: httpx.AsyncClient, email: str, password: str) -> Optional[Dict[str, Any]]:
    r = await c.post("/auth/login", json={"email": email, "password": password})
    if r.status_code == 200:
        return r.json()
    return None


async def register(c: httpx.AsyncClient, email: str, password: str, name: str) -> Optional[Dict[str, Any]]:
    r = await c.post("/auth/register", json={"email": email, "password": password, "name": name})
    if r.status_code == 200:
        return r.json()
    return None


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30.0) as c:
        print("\n[0] AUTH — login owner")
        owner = await login(c, OWNER_EMAIL, OWNER_PASS)
        if not check("POST /auth/login owner → 200", owner is not None, ""):
            return 1
        owner_tok = owner["token"]
        owner_id = owner["user"]["user_id"]
        OH = {"Authorization": f"Bearer {owner_tok}"}

        # Find a household space (or any owned space)
        r = await c.get("/spaces", headers=OH)
        spaces = r.json() if r.status_code == 200 else []
        # Prefer the seeded "Test Household" (IDR), fall back to any owner-owned
        household = next((s for s in spaces if s.get("space_id") == "space_8784d76aee6d4c56"), None)
        if not household:
            household = next((s for s in spaces if s.get("space_type") == "household" and s.get("owner_id") == owner_id), None)
        if not household:
            household = next((s for s in spaces if s.get("owner_id") == owner_id), None)
        if not check("found owner space", household is not None, ""):
            return 1
        space_id = household["space_id"]
        invite_code = household["invite_code"]
        currency = household.get("currency", "USD")
        print(f"     using space_id={space_id} invite={invite_code} currency={currency}")

        # ── Register 2 ad-hoc members for the membership-related cases ──
        suf = uuid.uuid4().hex[:6]
        m1_email = f"phase16_m1_{suf}@cozii.app"
        m2_email = f"phase16_m2_{suf}@cozii.app"
        m1 = await register(c, m1_email, "test1234", f"Phase16 M1 {suf}")
        m2 = await register(c, m2_email, "test1234", f"Phase16 M2 {suf}")
        check("register member1", m1 is not None, "")
        check("register member2", m2 is not None, "")
        if not m1 or not m2:
            return 1
        m1_tok = m1["token"]; m1_id = m1["user"]["user_id"]
        m2_tok = m2["token"]; m2_id = m2["user"]["user_id"]
        M1H = {"Authorization": f"Bearer {m1_tok}"}
        M2H = {"Authorization": f"Bearer {m2_tok}"}

        # Have them join the space via invite_code
        r = await c.post("/spaces/join", headers=M1H, json={"invite_code": invite_code})
        check("member1 joins space", r.status_code == 200, r.text[:200])
        r = await c.post("/spaces/join", headers=M2H, json={"invite_code": invite_code})
        check("member2 joins space", r.status_code == 200, r.text[:200])

        # Pick / ensure a category exists in the space (Food & Pantry)
        r = await c.get(f"/categories?space_id={space_id}", headers=OH)
        cats = r.json() if r.status_code == 200 else []
        if not cats:
            r = await c.post("/categories", headers=OH, json={
                "space_id": space_id, "name": "Phase16 Cat", "icon": "Box", "tint": "mint",
            })
            cats = [r.json()] if r.status_code == 200 else []
        if not check("space has at least one category", len(cats) >= 1, ""):
            return 1
        category_id = cats[0]["category_id"]
        print(f"     using category_id={category_id} ({cats[0].get('name')})")

        # Create / pick an existing item to be incremented in case A line 3
        r = await c.post("/items", headers=OH, json={
            "space_id": space_id,
            "category_id": category_id,
            "name": f"Phase16 Existing {suf}",
            "quantity": 4,
            "price": 8000,
        })
        check("seed: create existing item", r.status_code == 200, r.text[:200])
        existing_item = r.json() if r.status_code == 200 else None
        if not existing_item:
            return 1
        existing_item_id = existing_item["item_id"]
        existing_item_initial_qty = float(existing_item.get("quantity") or 0)

        # ────────────────────────────────────────────────────────────
        # CASE A — Owner creates a session with 3 line items
        # ────────────────────────────────────────────────────────────
        print("\n[A] POST /purchase-sessions (3 line items, mixed new + existing)")
        caviar_name = f"Caviar Test {suf}"
        milk_name = f"Milk Test {suf}"
        body_A = {
            "space_id": space_id,
            "merchant": "Ranch Market",
            "items": [
                {"name": caviar_name, "quantity": 3, "unit_price": 50000,
                 "category_id": category_id, "create_item": True},
                {"name": milk_name, "quantity": 2, "unit": "l",
                 "unit_price": 15000, "total_price": 30000, "create_item": True,
                 "category_id": category_id},
                {"item_id": existing_item_id, "name": "ignored",
                 "quantity": 1, "unit_price": 8000},
            ],
        }
        r = await c.post("/purchase-sessions", headers=OH, json=body_A)
        ok = check("POST /purchase-sessions → 200", r.status_code == 200, r.text[:300])
        if not ok:
            return 1
        sess = r.json()
        session_id = sess["session_id"]
        # Total = 50000*3 + 30000 + 8000*1 = 188000
        check("total computed = 188000",
              abs(float(sess.get("total") or 0) - 188000) < 0.01,
              f"got total={sess.get('total')}")
        check("session.merchant == 'Ranch Market'", sess.get("merchant") == "Ranch Market",
              str(sess.get("merchant")))
        check("session.currency populated from space",
              isinstance(sess.get("currency"), str) and len(sess["currency"]) > 0,
              str(sess.get("currency")))
        check("session has 3 line items",
              isinstance(sess.get("items"), list) and len(sess["items"]) == 3,
              f"items={len(sess.get('items') or [])}")

        # Verify inventory side-effects via /api/items
        r = await c.get(f"/items?space_id={space_id}", headers=OH)
        items_after = r.json() if r.status_code == 200 else []
        caviar = next((i for i in items_after if i.get("name") == caviar_name), None)
        milk = next((i for i in items_after if i.get("name") == milk_name), None)
        check("new Caviar item exists",
              caviar is not None and float(caviar.get("quantity") or 0) == 3,
              f"caviar={caviar}")
        check("new Milk item exists with qty=2",
              milk is not None and float(milk.get("quantity") or 0) == 2,
              f"milk={milk}")
        # Check the existing item incremented by 1
        existing_after = next((i for i in items_after if i.get("item_id") == existing_item_id), None)
        check("existing item quantity incremented by 1",
              existing_after is not None
              and abs(float(existing_after.get("quantity") or 0) - (existing_item_initial_qty + 1)) < 0.001,
              f"existing_after_qty={existing_after.get('quantity') if existing_after else None}")

        # Verify each line in session has inventory_applied=True and item_id populated
        applied_count = sum(1 for li in sess["items"] if li.get("inventory_applied"))
        check("all 3 lines inventory_applied=True", applied_count == 3,
              f"applied={applied_count}; items={sess['items']}")

        # Audit row check: GET /items/{new_item_id}/audit should have ONE row with source=purchase_session
        if caviar:
            r = await c.get(f"/items/{caviar['item_id']}/audit", headers=OH)
            audit_rows = r.json() if r.status_code == 200 else []
            ps_rows = [a for a in audit_rows if a.get("source") == "purchase_session"
                       and a.get("source_id") == session_id]
            check("Caviar audit has 1 row source=purchase_session",
                  len(ps_rows) == 1,
                  f"rows={audit_rows}")
            if ps_rows:
                check("audit row.delta == 3", abs(float(ps_rows[0].get("delta") or 0) - 3) < 0.001, str(ps_rows[0].get("delta")))
                check("audit row.new_qty == 3", abs(float(ps_rows[0].get("new_qty") or 0) - 3) < 0.001, str(ps_rows[0].get("new_qty")))

        # Existing item's audit list should also include a row tied to this session
        r = await c.get(f"/items/{existing_item_id}/audit", headers=OH)
        ex_audit = r.json() if r.status_code == 200 else []
        ex_ps_rows = [a for a in ex_audit if a.get("source") == "purchase_session"
                      and a.get("source_id") == session_id]
        check("existing item audit has row source=purchase_session for this session",
              len(ex_ps_rows) == 1,
              f"rows={ex_audit[:3]}")

        # ────────────────────────────────────────────────────────────
        # CASE B — GET list filtered by space
        # ────────────────────────────────────────────────────────────
        print("\n[B] GET /purchase-sessions?space_id=…")
        r = await c.get(f"/purchase-sessions?space_id={space_id}&limit=20", headers=OH)
        check("GET list → 200", r.status_code == 200, r.text[:200])
        rows = r.json() if r.status_code == 200 else []
        check("list includes the new session",
              any(s.get("session_id") == session_id for s in rows),
              f"got {len(rows)} rows; session_id={session_id}")

        # ────────────────────────────────────────────────────────────
        # CASE C — GET single
        # ────────────────────────────────────────────────────────────
        print("\n[C] GET /purchase-sessions/{id}")
        r = await c.get(f"/purchase-sessions/{session_id}", headers=OH)
        ok = check("GET single → 200", r.status_code == 200, r.text[:200])
        if ok:
            single = r.json()
            check("single.items has 3 lines",
                  isinstance(single.get("items"), list) and len(single["items"]) == 3,
                  f"items_len={len(single.get('items') or [])}")
            check("single.session_id matches", single.get("session_id") == session_id, "")

        # ────────────────────────────────────────────────────────────
        # CASE D — PATCH merchant + notes
        # ────────────────────────────────────────────────────────────
        print("\n[D] PATCH /purchase-sessions/{id}")
        r = await c.patch(f"/purchase-sessions/{session_id}", headers=OH, json={
            "merchant": "Ranch Market (Updated)",
            "notes": "Phase16 PATCH note",
        })
        ok = check("PATCH → 200", r.status_code == 200, r.text[:200])
        if ok:
            patched = r.json()
            check("PATCH returned new merchant",
                  patched.get("merchant") == "Ranch Market (Updated)", str(patched.get("merchant")))
            check("PATCH returned notes",
                  patched.get("notes") == "Phase16 PATCH note", str(patched.get("notes")))
            check("updated_at populated",
                  patched.get("updated_at") is not None, str(patched.get("updated_at")))

        # ────────────────────────────────────────────────────────────
        # CASE E — Auth required (401 without bearer)
        # ────────────────────────────────────────────────────────────
        print("\n[E] Auth: all 5 endpoints require Bearer token")
        endpoints = [
            ("POST", "/purchase-sessions", {"json": {"space_id": space_id, "merchant": "X", "items": []}}),
            ("GET", f"/purchase-sessions?space_id={space_id}", {}),
            ("GET", f"/purchase-sessions/{session_id}", {}),
            ("PATCH", f"/purchase-sessions/{session_id}", {"json": {"merchant": "Y"}}),
            ("DELETE", f"/purchase-sessions/{session_id}", {}),
        ]
        for method, path, kw in endpoints:
            r = await c.request(method, path, **kw)
            # FastAPI HTTPBearer auto-rejects with 403 by default; some impls return 401.
            check(f"{method} {path.split('?')[0]} unauth → 401/403",
                  r.status_code in (401, 403),
                  f"status={r.status_code}")

        # ────────────────────────────────────────────────────────────
        # CASE F — Member (non-owner) creates session in their space → succeeds
        # ────────────────────────────────────────────────────────────
        print("\n[F] Member creates session in own space")
        body_F = {
            "space_id": space_id,
            "merchant": "Indomaret",
            "items": [
                {"name": f"Bread M1 {suf}", "quantity": 2, "unit_price": 12000,
                 "category_id": category_id, "create_item": True},
            ],
        }
        r = await c.post("/purchase-sessions", headers=M1H, json=body_F)
        ok = check("member POST → 200", r.status_code == 200, r.text[:200])
        m1_session_id = r.json().get("session_id") if ok else None
        if ok:
            check("member session.created_by == m1",
                  r.json().get("created_by") == m1_id, str(r.json().get("created_by")))
            check("member total auto-computed = 24000",
                  abs(float(r.json().get("total") or 0) - 24000) < 0.01,
                  str(r.json().get("total")))

        # ────────────────────────────────────────────────────────────
        # CASE G — Different member's DELETE → 403
        # ────────────────────────────────────────────────────────────
        print("\n[G] Non-owner non-creator DELETE → 403")
        if m1_session_id:
            r = await c.delete(f"/purchase-sessions/{m1_session_id}", headers=M2H)
            check("M2 DELETE M1's session → 403",
                  r.status_code == 403, f"status={r.status_code} body={r.text[:200]}")
            # Verify session still exists
            r = await c.get(f"/purchase-sessions/{m1_session_id}", headers=OH)
            check("M1's session still exists after forbidden DELETE",
                  r.status_code == 200, r.text[:200])

        # ────────────────────────────────────────────────────────────
        # CASE H — Original creator's DELETE → rollback inventory, audit, requests
        # ────────────────────────────────────────────────────────────
        print("\n[H] Original creator DELETE → rollback")
        # Snapshot current quantities of items affected by session A
        snap = {}
        if caviar:
            snap[caviar["item_id"]] = float(caviar.get("quantity") or 0)
        if milk:
            snap[milk["item_id"]] = float(milk.get("quantity") or 0)
        snap[existing_item_id] = existing_after.get("quantity") if existing_after else None

        # Owner deletes session A
        r = await c.delete(f"/purchase-sessions/{session_id}", headers=OH)
        ok = check("owner DELETE session A → 200", r.status_code == 200, r.text[:200])

        # After delete: GET single → 404
        r = await c.get(f"/purchase-sessions/{session_id}", headers=OH)
        check("session A GET after DELETE → 404",
              r.status_code == 404, f"status={r.status_code}")

        # Verify inventory rollback
        r = await c.get(f"/items?space_id={space_id}", headers=OH)
        items_post = r.json() if r.status_code == 200 else []
        caviar_post = next((i for i in items_post if i.get("name") == caviar_name), None)
        milk_post = next((i for i in items_post if i.get("name") == milk_name), None)
        existing_post = next((i for i in items_post if i.get("item_id") == existing_item_id), None)
        # New items quantity should now be 0 (was 3 / 2 → −3 / −2 = 0)
        if caviar_post:
            check("Caviar qty rolled back to 0",
                  abs(float(caviar_post.get("quantity") or 0)) < 0.001,
                  f"qty={caviar_post.get('quantity')}")
        if milk_post:
            check("Milk qty rolled back to 0",
                  abs(float(milk_post.get("quantity") or 0)) < 0.001,
                  f"qty={milk_post.get('quantity')}")
        if existing_post:
            check("Existing item qty rolled back to initial",
                  abs(float(existing_post.get("quantity") or 0) - existing_item_initial_qty) < 0.001,
                  f"qty={existing_post.get('quantity')} expected={existing_item_initial_qty}")

        # Audit rows for the deleted session should be gone
        r = await c.get(f"/items/{existing_item_id}/audit", headers=OH)
        ex_audit_post = r.json() if r.status_code == 200 else []
        check("existing item audit rows for session A are gone",
              not any(a.get("source") == "purchase_session" and a.get("source_id") == session_id
                      for a in ex_audit_post),
              f"still has rows: {[a for a in ex_audit_post if a.get('source_id')==session_id]}")

        # ────────────────────────────────────────────────────────────
        # CASE I — Source-link to shopping_requests
        # ────────────────────────────────────────────────────────────
        print("\n[I] source_request_ids — request becomes purchased; on delete reverts")
        # Owner creates a shopping request (owner-created → auto-approved)
        r = await c.post("/household/shopping", headers=OH, json={
            "space_id": space_id,
            "item_name": f"P16 Linked {suf}",
            "quantity": "1pc",
            "urgency": "normal",
            "category_id": category_id,
        })
        ok = check("create owner shopping request → 200", r.status_code == 200, r.text[:200])
        if ok:
            req = r.json()
            request_id = req.get("request_id")
            check("request initial status approved (owner auto-approves)",
                  req.get("status") == "approved",
                  f"status={req.get('status')}")
            # Create a session linking this request
            r = await c.post("/purchase-sessions", headers=OH, json={
                "space_id": space_id,
                "merchant": "Linked Store",
                "items": [
                    {"name": f"P16 Linked Item {suf}", "quantity": 1, "unit_price": 5000,
                     "category_id": category_id, "create_item": True},
                ],
                "source_request_ids": [request_id],
            })
            ok2 = check("create session with source_request_ids → 200",
                        r.status_code == 200, r.text[:300])
            linked_session_id = r.json().get("session_id") if ok2 else None

            # Verify the request status flipped to "purchased"
            r = await c.get(f"/household/shopping?space_id={space_id}", headers=OH)
            shop_list = r.json() if r.status_code == 200 else []
            req_after = next((s for s in shop_list if s.get("request_id") == request_id), None)
            check("shopping request status flipped to 'purchased'",
                  req_after is not None and req_after.get("status") == "purchased",
                  f"req_after={req_after}")
            check("purchased_via_session_id set on request",
                  req_after is not None and req_after.get("purchased_via_session_id") == linked_session_id,
                  f"got={req_after.get('purchased_via_session_id') if req_after else None}")

            # Delete the linked session → request should revert to approved
            if linked_session_id:
                r = await c.delete(f"/purchase-sessions/{linked_session_id}", headers=OH)
                check("delete linked session → 200", r.status_code == 200, r.text[:200])

                r = await c.get(f"/household/shopping?space_id={space_id}", headers=OH)
                shop_list2 = r.json() if r.status_code == 200 else []
                req_post = next((s for s in shop_list2 if s.get("request_id") == request_id), None)
                check("request reverted to 'approved'",
                      req_post is not None and req_post.get("status") == "approved",
                      f"req_post={req_post}")
                check("purchased_by cleared",
                      req_post is not None and req_post.get("purchased_by") in (None, ""),
                      str(req_post.get("purchased_by") if req_post else None))
                check("purchased_at cleared",
                      req_post is not None and req_post.get("purchased_at") in (None, ""),
                      str(req_post.get("purchased_at") if req_post else None))
                check("purchased_via_session_id cleared",
                      req_post is not None and req_post.get("purchased_via_session_id") in (None, ""),
                      str(req_post.get("purchased_via_session_id") if req_post else None))

        # ────────────────────────────────────────────────────────────
        # REGRESSION smoke — Phase 15 adjust endpoint still works
        # ────────────────────────────────────────────────────────────
        print("\n[REGR] /api/items/{item_id}/adjust still works")
        # Use the existing item (still present, qty restored to initial)
        r = await c.post(f"/items/{existing_item_id}/adjust", headers=OH, json={
            "delta": 1, "note": "Phase16 regression"
        })
        ok = check("POST /items/{id}/adjust → 200", r.status_code == 200, r.text[:200])
        if ok:
            after = r.json()
            check("adjust incremented qty by 1",
                  abs(float(after.get("quantity") or 0) - (existing_item_initial_qty + 1)) < 0.001,
                  f"qty_after={after.get('quantity')}")
            # decrement back
            r = await c.post(f"/items/{existing_item_id}/adjust", headers=OH, json={
                "delta": -1, "note": "Phase16 regression restore"
            })
            check("POST /items/{id}/adjust decrement → 200", r.status_code == 200, r.text[:200])

        # Cleanup: clean up M1's session and the new items left around
        if m1_session_id:
            await c.delete(f"/purchase-sessions/{m1_session_id}", headers=M1H)
        # Best effort: delete new items
        for nm in (caviar_name, milk_name):
            it = next((i for i in items_post if i.get("name") == nm), None)
            if it:
                await c.delete(f"/items/{it['item_id']}", headers=OH)
        # Delete the existing seed item
        await c.delete(f"/items/{existing_item_id}", headers=OH)

        # ────────────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print(f"Phase 16 results: {PASS} PASS / {FAIL} FAIL  (total={PASS+FAIL})")
        if FAILS:
            print("\nFailures:")
            for f in FAILS:
                print(f"  - {f}")
        return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
