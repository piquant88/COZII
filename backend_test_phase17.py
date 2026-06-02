"""Phase 17 — Verify Emergent removal + Cozii-owned Google OAuth.

Note: The /auth/google/start and /auth/google/callback endpoints are mounted
on the FastAPI `app` directly (NOT under /api), so they are only reachable
internally via http://localhost:8001 (Kubernetes ingress only routes /api/*).
We test those via localhost. The /api/* endpoints are tested via both the
public preview URL and localhost.
"""
import os
import sys
import time
import uuid
import asyncio
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

PREVIEW = os.environ.get("PREVIEW_URL", "https://family-wallet-21.preview.emergentagent.com")
LOCAL   = os.environ.get("LOCAL_URL",   "http://localhost:8001")

API_PREVIEW = f"{PREVIEW}/api"
API_LOCAL   = f"{LOCAL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME   = os.environ.get("DB_NAME", "test_database")

OWNER_EMAIL = "test@cozii.app"
OWNER_PASS  = "test1234"

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


async def login_owner(c: httpx.AsyncClient) -> Dict[str, Any]:
    r = await c.post("/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASS})
    if r.status_code != 200:
        # try register
        r2 = await c.post("/auth/register", json={
            "email": OWNER_EMAIL, "password": OWNER_PASS, "name": "Test User"
        })
        r = await c.post("/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASS})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    return {"token": data["token"], "user": data["user"]}


def auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# A. Regression — existing flows
# ============================================================
async def section_A_regression():
    print("\n=== A. Regression — existing auth & CRUD ===")
    async with httpx.AsyncClient(base_url=API_PREVIEW, timeout=30) as c:
        # Register a fresh user for clean regression
        uniq = uuid.uuid4().hex[:8]
        em = f"phase17_{uniq}@cozii.app"
        rr = await c.post("/auth/register", json={"email": em, "password": "Pa$$word123", "name": f"Phase17 {uniq}"})
        check("POST /auth/register fresh user", rr.status_code == 200, f"{rr.status_code} {rr.text[:200]}")
        if rr.status_code != 200:
            return
        token = rr.json()["token"]
        user_id = rr.json()["user"]["user_id"]
        H = auth_headers(token)

        # Login
        lg = await c.post("/auth/login", json={"email": em, "password": "Pa$$word123"})
        check("POST /auth/login", lg.status_code == 200, f"{lg.status_code} {lg.text[:200]}")

        # /auth/me
        me = await c.get("/auth/me", headers=H)
        check("GET /auth/me", me.status_code == 200 and me.json().get("user_id") == user_id,
              f"{me.status_code} {me.text[:200]}")

        # Create space
        sp = await c.post("/spaces", headers=H, json={"name": f"P17 Space {uniq}", "currency": "USD"})
        check("POST /spaces", sp.status_code == 200, f"{sp.status_code} {sp.text[:200]}")
        if sp.status_code != 200:
            return
        space_id = sp.json()["space_id"]

        gs = await c.get("/spaces", headers=H)
        check("GET /spaces lists new space", gs.status_code == 200 and any(s["space_id"] == space_id for s in gs.json()),
              f"{gs.status_code} {gs.text[:200]}")

        # Categories CRUD
        cat = await c.post("/categories", headers=H, json={
            "space_id": space_id, "name": "Groceries", "icon": "ShoppingCart", "tint": "sage",
        })
        check("POST /categories", cat.status_code == 200, f"{cat.status_code} {cat.text[:200]}")
        if cat.status_code != 200:
            return
        cat_id = cat.json()["category_id"]

        gcats = await c.get(f"/categories?space_id={space_id}", headers=H)
        check("GET /categories", gcats.status_code == 200 and any(x["category_id"] == cat_id for x in gcats.json()),
              f"{gcats.status_code} {gcats.text[:200]}")

        # Items CRUD
        it = await c.post("/items", headers=H, json={
            "space_id": space_id, "category_id": cat_id, "name": "Bananas", "price": 4.50, "quantity": 1
        })
        check("POST /items", it.status_code == 200, f"{it.status_code} {it.text[:200]}")
        if it.status_code != 200:
            return
        item_id = it.json()["item_id"]

        gi = await c.get(f"/items?space_id={space_id}", headers=H)
        check("GET /items", gi.status_code == 200 and any(x["item_id"] == item_id for x in gi.json()),
              f"{gi.status_code} {gi.text[:200]}")

        pat = await c.patch(f"/items/{item_id}", headers=H, json={"price": 5.25})
        check("PATCH /items/{id}", pat.status_code == 200 and abs(pat.json().get("price", 0) - 5.25) < 0.001,
              f"{pat.status_code} {pat.text[:200]}")

        # Bills (Phase 5 etc)
        b = await c.post("/bills", headers=H, json={
            "space_id": space_id, "name": "Internet", "amount": 50, "frequency": "monthly", "due_day": 15
        })
        check("POST /bills", b.status_code == 200, f"{b.status_code} {b.text[:200]}")

        gb = await c.get(f"/bills?space_id={space_id}", headers=H)
        check("GET /bills", gb.status_code == 200, f"{gb.status_code} {gb.text[:200]}")

        # Activity feed
        ga = await c.get(f"/activity?space_id={space_id}", headers=H)
        check("GET /activity", ga.status_code == 200, f"{ga.status_code} {ga.text[:200]}")

        # Stats
        st = await c.get(f"/stats?space_id={space_id}", headers=H)
        check("GET /stats", st.status_code == 200, f"{st.status_code} {st.text[:200]}")

        # Balances
        bal = await c.get(f"/balances?space_id={space_id}", headers=H)
        check("GET /balances", bal.status_code == 200, f"{bal.status_code} {bal.text[:200]}")

        # Delete item
        di = await c.delete(f"/items/{item_id}", headers=H)
        check("DELETE /items/{id}", di.status_code == 200, f"{di.status_code} {di.text[:200]}")

        # Delete category
        dc = await c.delete(f"/categories/{cat_id}", headers=H)
        check("DELETE /categories/{id}", dc.status_code == 200, f"{dc.status_code} {dc.text[:200]}")

        # Logout
        lo = await c.post("/auth/logout", headers=H)
        check("POST /auth/logout", lo.status_code == 200, f"{lo.status_code} {lo.text[:200]}")

        # After logout, /auth/me with same token should be unauthorized
        me2 = await c.get("/auth/me", headers=H)
        check("GET /auth/me after logout returns 401", me2.status_code == 401, f"{me2.status_code} {me2.text[:200]}")


# ============================================================
# B. New Google OAuth endpoints (tested via localhost — non-/api routes)
# ============================================================
async def section_B_google_oauth_endpoints():
    print("\n=== B. /auth/google/start + /auth/google/callback (localhost) ===")
    async with httpx.AsyncClient(base_url=LOCAL, timeout=10, follow_redirects=False) as c:
        # B1 - /auth/google/start with no creds set
        r = await c.get("/auth/google/start")
        body = r.text or ""
        ok = r.status_code == 503 and "Google sign-in not configured" in body
        check("GET /auth/google/start → 503 'not configured'", ok,
              f"status={r.status_code} body={body[:200]}")

        # B2 - callback with no params
        r = await c.get("/auth/google/callback")
        loc = r.headers.get("location", "")
        ok = r.status_code == 302 and "cozii://auth-callback" in loc and "invalid_or_expired_state" in loc
        check("GET /auth/google/callback (no params) → 302 cozii://auth-callback?auth_error=invalid_or_expired_state",
              ok, f"status={r.status_code} location={loc[:200]}")

        # B3 - callback with garbage state
        r = await c.get("/auth/google/callback?state=garbage_value_xyz")
        loc = r.headers.get("location", "")
        ok = r.status_code == 302 and "cozii://auth-callback" in loc and "invalid_or_expired_state" in loc
        check("GET /auth/google/callback?state=garbage → 302 invalid_or_expired_state",
              ok, f"status={r.status_code} location={loc[:200]}")

        # B4 - /auth/google/start with malicious redirect → still 503 (no creds)
        r = await c.get("/auth/google/start?redirect=https://evil.example.com")
        ok = r.status_code == 503
        check("GET /auth/google/start?redirect=evil → 503 (no creds)",
              ok, f"status={r.status_code}")

        # B5 - callback with no code but valid state → expect 302 missing_code
        # (Requires inserting a fake state into mongo)
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        try:
            state = secrets.token_urlsafe(16)
            await db.oauth_states.insert_one({
                "state": state,
                "redirect": "cozii://auth-callback",
                "created_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=10),
            })
            r = await c.get(f"/auth/google/callback?state={state}")
            loc = r.headers.get("location", "")
            ok = r.status_code == 302 and "missing_code" in loc and "cozii://auth-callback" in loc
            check("GET /auth/google/callback?state=<valid>&code=missing → 302 missing_code",
                  ok, f"status={r.status_code} location={loc[:200]}")
        finally:
            client.close()


# ============================================================
# C. POST /api/auth/google-session redemption
# ============================================================
async def section_C_google_session_redeem():
    print("\n=== C. POST /api/auth/google-session redemption (preview URL) ===")
    # Use a real user (we'll register one if needed)
    async with httpx.AsyncClient(base_url=API_PREVIEW, timeout=30) as c:
        uniq = uuid.uuid4().hex[:8]
        em = f"phase17_gs_{uniq}@cozii.app"
        rr = await c.post("/auth/register", json={
            "email": em, "password": "Pa$$word123", "name": f"Phase17 GS {uniq}"
        })
        if rr.status_code != 200:
            check("Register user for session test", False, f"{rr.status_code} {rr.text[:200]}")
            return
        user_id = rr.json()["user"]["user_id"]

        # C1: Missing session_id
        # Empty string passes Pydantic but hits "if not body.session_id" → 400
        r = await c.post("/auth/google-session", json={"session_id": ""})
        ok = r.status_code == 400 and "Missing session_id" in (r.text or "")
        check("POST /api/auth/google-session {session_id:''} → 400 Missing session_id",
              ok, f"status={r.status_code} body={r.text[:200]}")

        # Also test totally-missing field (will be 422 due to Pydantic). Just check no 500.
        r = await c.post("/auth/google-session", json={})
        check("POST /api/auth/google-session {} → 400 or 422 (not 500)",
              r.status_code in (400, 422), f"status={r.status_code} body={r.text[:200]}")

        # C2: Garbage session_id → 401 (and NO outbound httpx to demobackend)
        r = await c.post("/auth/google-session", json={"session_id": "definitely-not-a-real-ticket"})
        ok = r.status_code == 401 and "Invalid or expired session" in (r.text or "")
        check("POST /api/auth/google-session {garbage} → 401 Invalid or expired session",
              ok, f"status={r.status_code} body={r.text[:200]}")

        # C3: Insert synthetic ticket → expect 200 with token+user
        client = AsyncIOMotorClient(MONGO_URL)
        db = client[DB_NAME]
        try:
            short_id = secrets.token_urlsafe(16)
            # Need a valid session_token. We'll grab the most recent one for this user.
            sess = await db.user_sessions.find_one({"user_id": user_id})
            assert sess, "No user session found for newly registered user"
            session_token = sess["session_token"]

            await db.oauth_pending_sessions.insert_one({
                "short_id": short_id,
                "session_token": session_token,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
                "redeemed": False,
            })
            r = await c.post("/auth/google-session", json={"session_id": short_id})
            body = {}
            try: body = r.json()
            except Exception: pass
            ok = (r.status_code == 200 and isinstance(body, dict)
                  and body.get("token") == session_token
                  and body.get("user", {}).get("user_id") == user_id)
            check("POST /api/auth/google-session {valid ticket} → 200 {token, user}",
                  ok, f"status={r.status_code} body={r.text[:300]}")

            # C4: Replay same short_id → 401 Session already redeemed
            r2 = await c.post("/auth/google-session", json={"session_id": short_id})
            ok = r2.status_code == 401 and "Session already redeemed" in (r2.text or "")
            check("POST /api/auth/google-session replay → 401 Session already redeemed",
                  ok, f"status={r2.status_code} body={r2.text[:200]}")

            # C5: Insert expired ticket → 401 Session expired
            short_id2 = secrets.token_urlsafe(16)
            await db.oauth_pending_sessions.insert_one({
                "short_id": short_id2,
                "session_token": session_token,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc) - timedelta(minutes=20),
                "expires_at": datetime.now(timezone.utc) - timedelta(minutes=10),
                "redeemed": False,
            })
            r3 = await c.post("/auth/google-session", json={"session_id": short_id2})
            ok = r3.status_code == 401 and "Session expired" in (r3.text or "")
            check("POST /api/auth/google-session expired ticket → 401 Session expired",
                  ok, f"status={r3.status_code} body={r3.text[:200]}")
        finally:
            client.close()


# ============================================================
# D. /api/ai/scan-receipt with OPENAI_API_KEY unset
# ============================================================
async def section_D_scan_receipt():
    print("\n=== D. /api/ai/scan-receipt (no OPENAI_API_KEY) ===")
    async with httpx.AsyncClient(base_url=API_PREVIEW, timeout=30) as c:
        # Login owner (must be auth'd)
        owner = await login_owner(c)
        H = auth_headers(owner["token"])
        # tiny base64 blob
        r = await c.post("/ai/scan-receipt", headers=H,
                         json={"image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="})
        body = r.text or ""
        ok503 = r.status_code == 503 and "OPENAI_API_KEY missing" in body
        check("POST /api/ai/scan-receipt → 503 OPENAI_API_KEY missing", ok503,
              f"status={r.status_code} body={body[:200]}")
        # And confirm error message no longer references Emergent
        check("Error body does NOT reference Emergent",
              "emergent" not in body.lower(),
              f"body={body[:200]}")


# ============================================================
# E. Backend logs: no outbound calls to demobackend.emergentagent.com
# ============================================================
def section_E_logs_grep():
    print("\n=== E. Backend logs grep for 'demobackend.emergentagent.com' ===")
    # Only count log lines logged AFTER the current backend session start
    # (the refactor that removed Emergent was deployed before that restart).
    # Detect last "Started server process" timestamp in the err log.
    last_start_ts: Optional[str] = None
    try:
        with open("/var/log/supervisor/backend.err.log", "r", errors="ignore") as f:
            prev_ts = None
            for line in f:
                # Format: "YYYY-MM-DD HH:MM:SS,mmm - ..." OR "INFO:     Started server process ..."
                parts = line.split()
                if parts and len(parts) >= 2 and parts[0].count("-") == 2 and ":" in parts[1]:
                    prev_ts = f"{parts[0]} {parts[1]}"
                if "Started server process" in line and prev_ts:
                    last_start_ts = prev_ts
    except FileNotFoundError:
        pass

    # If we couldn't detect a start ts, fall back to "today only"
    cutoff = last_start_ts or datetime.now(timezone.utc).strftime("%Y-%m-%d 00:00:00")
    print(f"  (cutoff timestamp = {cutoff})")

    found_after_cutoff: List[str] = []
    historical: List[str] = []
    for path in ("/var/log/supervisor/backend.out.log", "/var/log/supervisor/backend.err.log"):
        try:
            with open(path, "r", errors="ignore") as f:
                for line in f:
                    if "demobackend.emergentagent.com" in line:
                        # Try to extract leading timestamp
                        parts = line.split()
                        if len(parts) >= 2 and parts[0].count("-") == 2 and ":" in parts[1]:
                            ts = f"{parts[0]} {parts[1]}"
                            if ts >= cutoff:
                                found_after_cutoff.append(f"{path}: {line.rstrip()[:200]}")
                            else:
                                historical.append(ts)
                        else:
                            # No timestamp → conservative: treat as recent
                            found_after_cutoff.append(f"{path}: {line.rstrip()[:200]}")
        except FileNotFoundError:
            pass

    print(f"  Found {len(historical)} historical (pre-refactor) demobackend log entries (latest: {historical[-1] if historical else 'n/a'}).")
    check("No NEW 'demobackend.emergentagent.com' calls since backend restart",
          len(found_after_cutoff) == 0,
          f"post-cutoff lines: {found_after_cutoff[:3]}")


async def main():
    print(f"PREVIEW = {PREVIEW}")
    print(f"LOCAL   = {LOCAL}")
    print(f"MONGO   = {MONGO_URL} / {DB_NAME}")

    await section_A_regression()
    await section_B_google_oauth_endpoints()
    await section_C_google_session_redeem()
    await section_D_scan_receipt()
    section_E_logs_grep()

    print(f"\n=== Phase 17 SUMMARY: {PASS} PASS / {FAIL} FAIL ===")
    if FAILS:
        print("Failures:")
        for f in FAILS:
            print(f"  - {f}")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
