#!/usr/bin/env python3
"""Phase 10 backend tests: inventory alerts + shopping list mode + reimbursement fix."""
import os
import sys
import time
import json
import asyncio
from datetime import datetime, timedelta, timezone

import requests

BASE = os.environ.get("BACKEND_URL", "https://family-wallet-21.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

OWNER_EMAIL = "test@cozii.app"
OWNER_PASSWORD = "test1234"

passes = 0
fails = 0
failures = []


def _record(ok: bool, name: str, detail: str = ""):
    global passes, fails
    if ok:
        passes += 1
        print(f"PASS  {name}")
    else:
        fails += 1
        failures.append((name, detail))
        print(f"FAIL  {name} :: {detail}")


def login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


def register(email: str, password: str, name: str) -> str:
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": password, "name": name})
    if r.status_code == 200:
        return r.json()["token"]
    if r.status_code in (400, 409):
        return login(email, password)
    raise AssertionError(f"register failed: {r.status_code} {r.text}")


def H(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def get_household_space_id(tok):
    r = requests.get(f"{API}/spaces", headers=H(tok))
    assert r.status_code == 200, r.text
    spaces = r.json()
    for s in spaces:
        if s.get("space_type") == "household" and (s.get("name") or "").lower().startswith("test household"):
            return s["space_id"]
    for s in spaces:
        if s.get("space_type") == "household":
            return s["space_id"]
    r = requests.post(f"{API}/spaces", headers=H(tok),
                      json={"name": "Phase10 Test Household", "space_type": "household", "currency": "USD"})
    assert r.status_code == 200, r.text
    return r.json()["space_id"]


def create_category(tok, space_id, name="Pantry P10"):
    r = requests.post(f"{API}/categories", headers=H(tok),
                      json={"space_id": space_id, "name": name, "icon": "Apple", "tint": "mint"})
    assert r.status_code == 200, r.text
    return r.json()["category_id"]


def create_item(tok, space_id, category_id, name, status="available", expiry_date=None, price=None):
    payload = {"space_id": space_id, "category_id": category_id, "name": name, "status": status, "quantity": 1}
    if expiry_date:
        payload["expiry_date"] = expiry_date
    if price is not None:
        payload["price"] = price
    r = requests.post(f"{API}/items", headers=H(tok), json=payload)
    assert r.status_code == 200, f"create_item failed: {r.text}"
    return r.json()


def cleanup_open_shopping(tok, space_id, item_names):
    r = requests.get(f"{API}/household/shopping", headers=H(tok), params={"space_id": space_id})
    if r.status_code != 200:
        return
    for s in r.json():
        if s.get("item_name") in item_names and s.get("status") in ("pending", "approved"):
            requests.delete(f"{API}/household/shopping/{s['request_id']}", headers=H(tok))


# ============================================================
print(f"\n=== Phase 10 backend tests against {API} ===\n")

owner_tok = login(OWNER_EMAIL, OWNER_PASSWORD)

ts = int(time.time())
outsider_email = f"phase10_outsider_{ts}@cozii.app"
outsider_tok = register(outsider_email, "Outsider!2026", "Olivia Stone")

space_id = get_household_space_id(owner_tok)
print(f"Using space_id={space_id}")


# A. Reimbursement starts pending
print("\n--- A. Reimbursement starts pending ---")
cat_id = create_category(owner_tok, space_id, name=f"Pantry P10 {ts}")

unique_name1 = f"P10 Almond Milk {ts}"
r = requests.post(f"{API}/household/shopping", headers=H(owner_tok), json={
    "space_id": space_id, "item_name": unique_name1, "kind": "reimbursement",
    "actual_price": 12.50, "category_id": cat_id, "urgency": "normal"})
ok = r.status_code == 200 and r.json().get("status") == "pending" and r.json().get("kind") == "reimbursement"
_record(ok, "A1: POST kind=reimbursement -> status=pending, kind=reimbursement",
        f"status={r.status_code} body={r.text[:300]}")
reimb_id = r.json().get("request_id") if r.status_code == 200 else None
ok = (r.status_code == 200 and r.json().get("actual_price") == 12.50)
_record(ok, "A1b: reimbursement preserves actual_price", f"body={r.text[:300]}")

unique_name2 = f"P10 Eggs {ts}"
r = requests.post(f"{API}/household/shopping", headers=H(owner_tok), json={
    "space_id": space_id, "item_name": unique_name2, "kind": "request",
    "estimated_price": 4.0, "urgency": "normal", "category_id": cat_id})
ok = r.status_code == 200 and r.json().get("status") == "pending" and r.json().get("kind") == "request"
_record(ok, "A2: POST kind=request -> status=pending, kind=request",
        f"status={r.status_code} body={r.text[:300]}")

if reimb_id:
    r = requests.patch(f"{API}/household/shopping/{reimb_id}", headers=H(owner_tok), json={"status": "approved"})
    ok = r.status_code == 200 and r.json().get("status") == "approved"
    _record(ok, "A3: PATCH reimbursement status=approved -> approved",
            f"status={r.status_code} body={r.text[:300]}")

    r = requests.post(f"{API}/household/shopping/{reimb_id}/purchase", headers=H(owner_tok),
                      json={"actual_price": 12.50})
    ok = r.status_code == 200 and r.json().get("status") == "purchased"
    _record(ok, "A4: POST /shopping/{id}/purchase -> status=purchased",
            f"status={r.status_code} body={r.text[:300]}")
else:
    _record(False, "A3: PATCH approve", "no reimb_id")
    _record(False, "A4: POST purchase", "no reimb_id")


# B. Inventory alerts endpoint
print("\n--- B. Inventory alerts endpoint ---")
today = datetime.now(timezone.utc).date()
items_meta = [
    ("P10_item1_avail", "available", None),
    ("P10_item2_low", "low", None),
    ("P10_item3_finished", "finished", None),
    ("P10_item4_exp3", "available", (today + timedelta(days=3)).isoformat()),
    ("P10_item5_exp30", "available", (today + timedelta(days=30)).isoformat()),
    ("P10_item6_expired", "available", (today - timedelta(days=2)).isoformat()),
]
created_items = {}
for label, st, exp in items_meta:
    name = f"{label} {ts}"
    it = create_item(owner_tok, space_id, cat_id, name=name, status=st, expiry_date=exp, price=5.0)
    created_items[label] = it

r = requests.get(f"{API}/inventory/alerts", headers=H(owner_tok),
                 params={"space_id": space_id, "days_threshold": 7})
ok = r.status_code == 200
_record(ok, "B1: GET /inventory/alerts -> 200", f"status={r.status_code}")
alerts = r.json() if ok else {}

def _has_item(bucket, label):
    target_id = created_items[label]["item_id"]
    return any(x.get("item_id") == target_id for x in alerts.get(bucket, []))

ok = _has_item("low_stock", "P10_item2_low") and not _has_item("low_stock", "P10_item3_finished")
_record(ok, "B2: low_stock contains item2 (low)",
        json.dumps([x.get("name") for x in alerts.get("low_stock", [])])[:200])

ok = _has_item("finished", "P10_item3_finished")
_record(ok, "B3: finished contains item3",
        json.dumps([x.get("name") for x in alerts.get("finished", [])])[:200])

ok = _has_item("expiring", "P10_item4_exp3") and not _has_item("expiring", "P10_item5_exp30")
_record(ok, "B4: expiring at threshold=7 contains item4 (3d), excludes item5 (30d)",
        f"expiring={[x.get('name') for x in alerts.get('expiring', [])]}")

ok = _has_item("expired", "P10_item6_expired")
_record(ok, "B5: expired contains item6",
        json.dumps([x.get("name") for x in alerts.get("expired", [])])[:200])

totals = alerts.get("totals", {}) or {}
ok = (totals.get("low") == len(alerts.get("low_stock", []))
      and totals.get("finished") == len(alerts.get("finished", []))
      and totals.get("expiring") == len(alerts.get("expiring", []))
      and totals.get("expired") == len(alerts.get("expired", []))
      and totals.get("all") == (totals.get("low", 0) + totals.get("finished", 0)
                                + totals.get("expiring", 0) + totals.get("expired", 0)))
_record(ok, "B6: totals math matches bucket lengths", json.dumps(totals))

# Each alerted item enriched with category_name
ok = True
target_ids = [created_items[k]["item_id"] for k in ("P10_item2_low", "P10_item3_finished",
                                                    "P10_item4_exp3", "P10_item6_expired")]
for bucket in ("low_stock", "finished", "expiring", "expired"):
    for x in alerts.get(bucket, []):
        if x.get("item_id") in target_ids and not x.get("category_name"):
            ok = False
_record(ok, "B7: alerted items enriched with category_name", "")

ok = True
for bucket in ("low_stock", "finished", "expiring", "expired"):
    for x in alerts.get(bucket, []):
        if x.get("item_id") in target_ids:
            if "category_icon" not in x or "category_tint" not in x:
                ok = False
_record(ok, "B7b: alerted items also include category_icon and category_tint", "")

r = requests.get(f"{API}/inventory/alerts", headers=H(owner_tok),
                 params={"space_id": space_id, "days_threshold": 60})
ok = r.status_code == 200
alerts60 = r.json() if ok else {}
ok = ok and any(x.get("item_id") == created_items["P10_item5_exp30"]["item_id"]
                for x in alerts60.get("expiring", []))
_record(ok, "B8: threshold=60 includes item5 (30d expiry) in expiring",
        f"expiring count={len(alerts60.get('expiring', []))}")
ok = len(alerts60.get("expiring", [])) >= len(alerts.get("expiring", [])) + 1
_record(ok, "B8b: expiring count grows when threshold raised 7->60",
        f"7d={len(alerts.get('expiring', []))}, 60d={len(alerts60.get('expiring', []))}")


# C. Convert alerts to shopping
print("\n--- C. Convert alerts to shopping ---")
cleanup_names = [created_items[k]["name"] for k in ("P10_item2_low", "P10_item3_finished",
                                                    "P10_item4_exp3", "P10_item6_expired",
                                                    "P10_item5_exp30")]
cleanup_open_shopping(owner_tok, space_id, cleanup_names)

ids = [created_items["P10_item2_low"]["item_id"],
       created_items["P10_item3_finished"]["item_id"],
       created_items["P10_item4_exp3"]["item_id"]]
r = requests.post(f"{API}/inventory/alerts/to-shopping", headers=H(owner_tok),
                  json={"space_id": space_id, "item_ids": ids})
ok = r.status_code == 200 and r.json().get("created") == 3 and r.json().get("skipped") == 0
_record(ok, "C1: to-shopping creates 3, skips 0", f"status={r.status_code} body={r.text[:300]}")
created_request_ids = r.json().get("request_ids", []) if r.status_code == 200 else []
ok = isinstance(created_request_ids, list) and len(created_request_ids) == 3
_record(ok, "C1b: response includes 3 request_ids", str(created_request_ids))

r = requests.get(f"{API}/household/shopping", headers=H(owner_tok), params={"space_id": space_id})
ok = r.status_code == 200
shopping = r.json() if ok else []
matching = [s for s in shopping if s.get("request_id") in created_request_ids]
ok = ok and len(matching) == 3 and all(s.get("status") == "pending" and s.get("kind") == "request" for s in matching)
_record(ok, "C2: 3 new pending kind=request shopping requests exist",
        f"matched={len(matching)} statuses={[s.get('status') for s in matching]}")

item3_name = created_items["P10_item3_finished"]["name"]
finished_req = next((s for s in matching if s.get("item_name") == item3_name), None)
ok = finished_req is not None and finished_req.get("urgency") == "high"
_record(ok, "C3: shopping from finished item -> urgency=high (auto-bumped)",
        f"req={finished_req}")

item4_name = created_items["P10_item4_exp3"]["name"]
exp3_req = next((s for s in matching if s.get("item_name") == item4_name), None)
ok = exp3_req is not None and exp3_req.get("urgency") in ("normal", "low")
_record(ok, "C3b: shopping from soon-expiring (not expired) item NOT auto-bumped",
        f"urgency={(exp3_req or {}).get('urgency')}")

item2_name = created_items["P10_item2_low"]["name"]
low_req = next((s for s in matching if s.get("item_name") == item2_name), None)
ok = low_req is not None and low_req.get("urgency") in ("normal", "low")
_record(ok, "C3c: shopping from low-stock item NOT auto-bumped",
        f"urgency={(low_req or {}).get('urgency')}")

cleanup_open_shopping(owner_tok, space_id, [created_items["P10_item6_expired"]["name"]])
r = requests.post(f"{API}/inventory/alerts/to-shopping", headers=H(owner_tok),
                  json={"space_id": space_id,
                        "item_ids": [created_items["P10_item6_expired"]["item_id"]]})
ok = r.status_code == 200 and r.json().get("created") == 1 and r.json().get("skipped") == 0
_record(ok, "C4: to-shopping for expired item creates 1", f"body={r.text[:300]}")
new_id = r.json().get("request_ids", [None])[0] if r.status_code == 200 else None
if new_id:
    r = requests.get(f"{API}/household/shopping", headers=H(owner_tok), params={"space_id": space_id})
    sh = next((s for s in r.json() if s.get("request_id") == new_id), None)
    ok = sh is not None and sh.get("urgency") == "high"
    _record(ok, "C4b: shopping from expired item -> urgency=high",
            f"urgency={sh.get('urgency') if sh else None}")
else:
    _record(False, "C4b", "no request created")

r = requests.post(f"{API}/inventory/alerts/to-shopping", headers=H(owner_tok),
                  json={"space_id": space_id,
                        "item_ids": [created_items["P10_item2_low"]["item_id"]]})
ok = r.status_code == 200 and r.json().get("created") == 0 and r.json().get("skipped") == 1
_record(ok, "C5: re-converting item with open pending request -> created=0 skipped=1",
        f"body={r.text[:300]}")

r = requests.post(f"{API}/inventory/alerts/to-shopping", headers=H(owner_tok),
                  json={"space_id": space_id, "item_ids": []})
ok = r.status_code == 400
_record(ok, "C6: empty item_ids -> 400", f"status={r.status_code} body={r.text[:200]}")

r = requests.post(f"{API}/inventory/alerts/to-shopping", headers=H(owner_tok),
                  json={"space_id": space_id, "item_ids": ["item_doesnotexist1", "item_doesnotexist2"]})
ok = r.status_code == 200 and r.json().get("created") == 0 and r.json().get("skipped") == 0
_record(ok, "C7: only non-existent ids -> 200 created=0 skipped=0",
        f"body={r.text[:200]}")

cleanup_open_shopping(owner_tok, space_id, [created_items["P10_item5_exp30"]["name"]])
r = requests.post(f"{API}/inventory/alerts/to-shopping", headers=H(owner_tok),
                  json={"space_id": space_id, "item_ids": [
                      "item_doesnotexist3",
                      created_items["P10_item5_exp30"]["item_id"]]})
ok = r.status_code == 200 and r.json().get("created") == 1
_record(ok, "C7b: valid + non-existent ids -> only valid processed (created=1)",
        f"body={r.text[:200]}")


# D. Permission/membership
print("\n--- D. Permission/membership ---")
r = requests.get(f"{API}/inventory/alerts", headers=H(outsider_tok),
                 params={"space_id": space_id, "days_threshold": 7})
ok = r.status_code == 403
_record(ok, "D1: outsider GET /inventory/alerts -> 403",
        f"status={r.status_code} body={r.text[:200]}")

r = requests.post(f"{API}/inventory/alerts/to-shopping", headers=H(outsider_tok),
                  json={"space_id": space_id,
                        "item_ids": [created_items["P10_item5_exp30"]["item_id"]]})
ok = r.status_code == 403
_record(ok, "D2: outsider POST /to-shopping -> 403",
        f"status={r.status_code} body={r.text[:200]}")


# E. Realtime emit
print("\n--- E. Realtime emit (Socket.IO) ---")
events_received = []

async def run_socket_test():
    try:
        import socketio as sio_lib
    except Exception as e:
        return f"socketio client missing: {e}"
    cli = sio_lib.AsyncClient(reconnection=False, logger=False, engineio_logger=False)

    @cli.on("space.event")
    async def _on_space(data):
        events_received.append(data)

    try:
        await cli.connect(BASE, socketio_path="/api/socket.io",
                          auth={"token": owner_tok}, transports=["websocket"])
    except Exception as e:
        return f"connect failed: {e}"

    await asyncio.sleep(1.0)

    cleanup_open_shopping(owner_tok, space_id, [created_items["P10_item4_exp3"]["name"],
                                                created_items["P10_item6_expired"]["name"]])
    rr = requests.post(f"{API}/inventory/alerts/to-shopping", headers=H(owner_tok),
                       json={"space_id": space_id,
                             "item_ids": [created_items["P10_item4_exp3"]["item_id"],
                                          created_items["P10_item6_expired"]["item_id"]]})
    if rr.status_code != 200 or rr.json().get("created") != 2:
        await cli.disconnect()
        return f"to-shopping failed during socket test: {rr.status_code} {rr.text}"

    await asyncio.sleep(2.5)
    await cli.disconnect()
    return None

err = asyncio.run(run_socket_test())
if err:
    _record(False, "E1: socket received space.event for to-shopping", err)
else:
    matching_evts = [e for e in events_received
                     if e.get("kind") == "shopping"
                     and e.get("action") == "created"
                     and (e.get("payload") or {}).get("from_alert") is True
                     and e.get("space_id") == space_id]
    ok = len(matching_evts) >= 2
    _record(ok, "E1: received >=2 space.event shopping/created with from_alert=true",
            f"count={len(matching_evts)} all_events={len(events_received)}")


# ============================================================
print("\n=== SUMMARY ===")
print(f"PASS: {passes}")
print(f"FAIL: {fails}")
if failures:
    print("\nFAILURES:")
    for n, d in failures:
        print(f"  - {n}\n      {d}")
sys.exit(0 if fails == 0 else 1)
