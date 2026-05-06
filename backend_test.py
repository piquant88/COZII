"""
Backend test suite for Cozii — Phase 8: Socket.IO real-time sync.

Focus: the new socket.io integration mounted at /api/socket.io, emit helpers,
and event wiring on contract CRUD + staff join + notifications.

Usage: /root/.venv/bin/python backend_test.py
"""
import asyncio
import os
import time
import uuid
import traceback
from typing import Any, Dict, List, Optional, Tuple

import requests
import socketio

BASE = os.environ.get("BACKEND_BASE", "http://localhost:8001")
API = f"{BASE}/api"


# -------------- HTTP helpers -------------- #

def _uniq_email(prefix: str) -> str:
    return f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:6]}@cozii.app"


def http_register(email: str, password: str, name: str) -> Dict[str, Any]:
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "name": name},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def H(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def create_space(token: str, space_type: str = "household") -> Dict[str, Any]:
    r = requests.post(
        f"{API}/spaces",
        headers=H(token),
        json={"name": f"Test Space {uuid.uuid4().hex[:6]}", "space_type": space_type, "currency": "USD"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def get_roles(token: str, space_id: str) -> List[Dict[str, Any]]:
    r = requests.get(f"{API}/household/roles", headers=H(token), params={"space_id": space_id}, timeout=10)
    r.raise_for_status()
    return r.json()


def create_staff(token: str, space_id: str, name: str, role_id: str) -> Dict[str, Any]:
    r = requests.post(
        f"{API}/household/staff",
        headers=H(token),
        json={
            "space_id": space_id,
            "name": name,
            "role_id": role_id,
            "salary": 1000,
            "pay_cycle": "monthly",
            "off_day": "sun",
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def staff_join_by_code(token: str, invite_code: str) -> Dict[str, Any]:
    r = requests.post(
        f"{API}/household/staff/join",
        headers=H(token),
        json={"invite_code": invite_code},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


# -------------- Socket.IO test client -------------- #

class SioTestClient:
    def __init__(self, name: str):
        self.name = name
        self.sio = socketio.AsyncClient(logger=False, engineio_logger=False, reconnection=False)
        self.hello: Optional[Dict[str, Any]] = None
        self.space_events: List[Dict[str, Any]] = []
        self.user_events: List[Dict[str, Any]] = []
        self._hello_evt = asyncio.Event()

        @self.sio.on("hello")
        async def _h(data):
            self.hello = data
            self._hello_evt.set()

        @self.sio.on("space.event")
        async def _s(data):
            self.space_events.append(data)

        @self.sio.on("user.event")
        async def _u(data):
            self.user_events.append(data)

    async def connect(self, token: Optional[str], path: str = "/api/socket.io", timeout: float = 5.0):
        auth = {"token": token} if token else None
        await self.sio.connect(
            BASE, socketio_path=path, auth=auth,
            transports=["polling", "websocket"], wait_timeout=timeout,
        )

    async def wait_hello(self, timeout: float = 5.0):
        await asyncio.wait_for(self._hello_evt.wait(), timeout=timeout)
        return self.hello

    async def emit_join(self, payload):
        return await self.sio.call("join_room", payload, timeout=5)

    async def disconnect(self):
        try:
            await self.sio.disconnect()
        except Exception:
            pass

    async def wait_for(self, pred, timeout: float = 3.0, source: str = "space"):
        end = time.time() + timeout
        src = self.space_events if source == "space" else self.user_events
        while time.time() < end:
            for e in src:
                if pred(e):
                    return e
            await asyncio.sleep(0.1)
        return None


# -------------- Test runner -------------- #

class Runner:
    def __init__(self):
        self.results: List[Tuple[str, bool, str]] = []

    def ok(self, name: str, msg: str = ""):
        self.results.append((name, True, msg))
        print(f"  PASS  {name}  {msg}".rstrip())

    def fail(self, name: str, msg: str):
        self.results.append((name, False, msg))
        print(f"  FAIL  {name}  {msg}")

    def summary(self):
        p = sum(1 for _, ok, _ in self.results if ok)
        f = len(self.results) - p
        print("\n=== Summary ===")
        print(f"  PASS: {p}  FAIL: {f}  TOTAL: {len(self.results)}")
        if f:
            print("\nFAILED:")
            for n, ok, m in self.results:
                if not ok:
                    print(f"  - {n}: {m}")
        return p, f


R = Runner()


# -------------- Test cases -------------- #

async def setup_world() -> Dict[str, Any]:
    a = http_register(_uniq_email("alex"), "test1234", "Alex Morgan")
    b = http_register(_uniq_email("riley"), "test1234", "Riley Chen")
    c = http_register(_uniq_email("quinn"), "test1234", "Quinn Park")

    space_a = create_space(a["token"])
    space_c = create_space(c["token"])

    roles = get_roles(a["token"], space_a["space_id"])
    maid = next((r for r in roles if (r.get("name") or "").lower() == "maid"), roles[0])
    staff = create_staff(a["token"], space_a["space_id"], "Riley Chen", maid["role_id"])
    inv = staff.get("invite_code")
    if not inv:
        raise RuntimeError("create_staff did not return invite_code")
    staff_join_by_code(b["token"], inv)

    return {
        "A": a, "B": b, "C": c,
        "space_a": space_a, "space_c": space_c,
        "staff_id": staff["staff_id"],
    }


async def test_connection_lifecycle(ctx):
    # valid connect
    client = SioTestClient("A-valid")
    try:
        await client.connect(ctx["A"]["token"])
        R.ok("connect with valid token")
        try:
            await client.wait_hello(timeout=5)
            sp = client.hello or {}
            if sp.get("user_id") == ctx["A"]["user"]["user_id"] and ctx["space_a"]["space_id"] in (sp.get("spaces") or []):
                R.ok("hello event has user_id + spaces")
            else:
                R.fail("hello event payload", f"got={sp}")
        except asyncio.TimeoutError:
            R.fail("hello event received", "no hello within 5s")
    except Exception as e:
        R.fail("connect with valid token", f"{type(e).__name__}: {e}")
    finally:
        await client.disconnect()

    # no token
    c2 = SioTestClient("no-token")
    try:
        await c2.connect(None)
        R.fail("connect with no token refused", "connection succeeded")
        await c2.disconnect()
    except Exception as e:
        R.ok("connect with no token refused", f"{type(e).__name__}")

    # bad token
    c3 = SioTestClient("bad-token")
    try:
        await c3.connect("this-is-not-a-valid-token-xyz")
        R.fail("connect with bad token refused", "connection succeeded")
        await c3.disconnect()
    except Exception as e:
        R.ok("connect with bad token refused", f"{type(e).__name__}")

    # wrong path
    c4 = SioTestClient("wrong-path")
    try:
        await c4.connect(ctx["A"]["token"], path="/socket.io", timeout=3)
        R.fail("connect with wrong path fails", "succeeded unexpectedly")
        await c4.disconnect()
    except Exception as e:
        R.ok("connect with wrong path fails", f"{type(e).__name__}")


async def test_join_room(ctx):
    client = SioTestClient("A-join")
    try:
        await client.connect(ctx["A"]["token"])
        await client.wait_hello(5)

        ack = await client.emit_join({"space_id": ctx["space_a"]["space_id"]})
        if isinstance(ack, dict) and ack.get("ok") is True and ack.get("joined") == ctx["space_a"]["space_id"]:
            R.ok("join_room valid space")
        else:
            R.fail("join_room valid space", f"ack={ack}")

        ack2 = await client.emit_join({"space_id": "space_invalid_xyz"})
        if isinstance(ack2, dict) and ack2.get("ok") is False:
            R.ok("join_room invalid space rejected")
        else:
            R.fail("join_room invalid space rejected", f"ack={ack2}")

        ack3 = await client.emit_join({})
        if isinstance(ack3, dict) and ack3.get("ok") is False:
            R.ok("join_room empty payload rejected")
        else:
            R.fail("join_room empty payload rejected", f"ack={ack3}")
    except Exception as e:
        R.fail("join_room suite", f"{type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        await client.disconnect()


async def _connect_all(ctx) -> Tuple[SioTestClient, SioTestClient, SioTestClient]:
    a = SioTestClient("A"); b = SioTestClient("B"); c = SioTestClient("C")
    await a.connect(ctx["A"]["token"])
    await b.connect(ctx["B"]["token"])
    await c.connect(ctx["C"]["token"])
    await a.wait_hello(5); await b.wait_hello(5); await c.wait_hello(5)
    return a, b, c


async def test_contract_events_and_isolation(ctx):
    a, b, c = None, None, None
    try:
        a, b, c = await _connect_all(ctx)
        for cli in (a, b, c):
            cli.space_events.clear(); cli.user_events.clear()

        # POST /api/contracts
        r = requests.post(
            f"{API}/contracts",
            headers=H(ctx["A"]["token"]),
            json={
                "space_id": ctx["space_a"]["space_id"],
                "title": "Full-time Employment Agreement",
                "assigned_staff_id": ctx["staff_id"],
                "body": "Work Tuesday-Sunday.",
                "require_drawn_signature_owner": False,
                "require_drawn_signature_staff": False,
            },
            timeout=10,
        )
        if r.status_code != 200:
            R.fail("POST /api/contracts", f"status={r.status_code} body={r.text[:300]}")
            return
        contract_id = r.json().get("contract_id")
        R.ok("POST /api/contracts", f"contract_id={contract_id}")

        ev_a = await a.wait_for(lambda e: e.get("kind") == "contract" and e.get("action") == "created", 3)
        R.ok("A receives space.event contract.created") if ev_a else R.fail("A receives space.event contract.created", f"events={a.space_events}")
        ev_b = await b.wait_for(lambda e: e.get("kind") == "contract" and e.get("action") == "created", 3)
        R.ok("B receives space.event contract.created") if ev_b else R.fail("B receives space.event contract.created", f"events={b.space_events}")

        un_b = await b.wait_for(
            lambda e: e.get("kind") == "notification" and (e.get("payload") or {}).get("kind") == "contract_assigned",
            3, source="user",
        )
        R.ok("B receives user.event notification contract_assigned") if un_b else R.fail("B receives user.event notification contract_assigned", f"events={b.user_events}")

        # Cross-space isolation: C receives nothing
        if not c.space_events and not c.user_events:
            R.ok("C (different space) receives no events")
        else:
            R.fail("C (different space) receives no events", f"space={c.space_events} user={c.user_events}")

        # REST notification exists
        rn = requests.get(f"{API}/notifications", headers=H(ctx["B"]["token"]),
                          params={"space_id": ctx["space_a"]["space_id"]}, timeout=10)
        if rn.status_code == 200 and any(n.get("kind") == "contract_assigned" for n in rn.json()):
            R.ok("notify_user inserted contract_assigned notification (REST GET /notifications)")
        else:
            R.fail("notify_user inserted contract_assigned notification", f"status={rn.status_code} body={rn.text[:300]}")

        # ---- sign by owner ----
        for cli in (a, b, c):
            cli.space_events.clear(); cli.user_events.clear()

        r = requests.post(f"{API}/contracts/{contract_id}/sign",
                          headers=H(ctx["A"]["token"]), json={"typed_name": "Alex Morgan"}, timeout=10)
        if r.status_code != 200:
            R.fail("POST /contracts/{id}/sign (owner)", f"status={r.status_code} body={r.text[:300]}")
            return
        R.ok("POST /contracts/{id}/sign (owner)")

        eva = await a.wait_for(lambda e: e.get("kind") == "contract" and e.get("action") == "signed", 3)
        if eva and (eva.get("payload") or {}).get("by") == "owner":
            R.ok("A receives space.event contract.signed by=owner")
        else:
            R.fail("A receives space.event contract.signed by=owner", f"eva={eva}")
        evb = await b.wait_for(lambda e: e.get("kind") == "contract" and e.get("action") == "signed", 3)
        if evb and (evb.get("payload") or {}).get("by") == "owner":
            R.ok("B receives space.event contract.signed by=owner")
        else:
            R.fail("B receives space.event contract.signed by=owner", f"evb={evb}")
        unb = await b.wait_for(
            lambda e: e.get("kind") == "notification" and (e.get("payload") or {}).get("kind") == "contract_owner_signed",
            3, source="user",
        )
        R.ok("B receives user.event notification contract_owner_signed") if unb else R.fail("B receives user.event notification contract_owner_signed", f"user_events={b.user_events}")

        # ---- sign by staff ----
        for cli in (a, b):
            cli.space_events.clear(); cli.user_events.clear()

        r = requests.post(f"{API}/contracts/{contract_id}/sign",
                          headers=H(ctx["B"]["token"]), json={"typed_name": "Riley Chen"}, timeout=10)
        if r.status_code != 200:
            R.fail("POST /contracts/{id}/sign (staff)", f"status={r.status_code} body={r.text[:300]}")
            return
        R.ok("POST /contracts/{id}/sign (staff)")

        eva2 = await a.wait_for(
            lambda e: e.get("kind") == "contract" and e.get("action") == "signed" and (e.get("payload") or {}).get("by") == "staff",
            3,
        )
        if eva2 and (eva2.get("payload") or {}).get("status") == "signed":
            R.ok("A receives space.event contract.signed by=staff status=signed")
        else:
            R.fail("A receives space.event contract.signed by=staff status=signed", f"eva2={eva2}")
        evb2 = await b.wait_for(
            lambda e: e.get("kind") == "contract" and e.get("action") == "signed" and (e.get("payload") or {}).get("by") == "staff",
            3,
        )
        R.ok("B receives space.event contract.signed by=staff") if evb2 else R.fail("B receives space.event contract.signed by=staff", f"evb2={evb2}")
        una = await a.wait_for(
            lambda e: e.get("kind") == "notification" and (e.get("payload") or {}).get("kind") == "contract_staff_signed",
            3, source="user",
        )
        R.ok("A receives user.event notification contract_staff_signed") if una else R.fail("A receives user.event notification contract_staff_signed", f"user_events={a.user_events}")

        # ---- void ----
        a.space_events.clear(); b.space_events.clear()
        r = requests.post(f"{API}/contracts/{contract_id}/void", headers=H(ctx["A"]["token"]), json={}, timeout=10)
        if r.status_code == 200:
            R.ok("POST /contracts/{id}/void")
            evv = await a.wait_for(lambda e: e.get("kind") == "contract" and e.get("action") == "voided", 3)
            R.ok("A receives space.event contract.voided") if evv else R.fail("A receives space.event contract.voided", f"events={a.space_events}")
        else:
            R.fail("POST /contracts/{id}/void", f"status={r.status_code}")

        # ---- delete ----
        a.space_events.clear()
        r = requests.delete(f"{API}/contracts/{contract_id}", headers=H(ctx["A"]["token"]), timeout=10)
        if r.status_code == 200:
            R.ok("DELETE /contracts/{id}")
            evd = await a.wait_for(lambda e: e.get("kind") == "contract" and e.get("action") == "deleted", 3)
            R.ok("A receives space.event contract.deleted") if evd else R.fail("A receives space.event contract.deleted", f"events={a.space_events}")
        else:
            R.fail("DELETE /contracts/{id}", f"status={r.status_code}")

    except Exception as e:
        R.fail("contract_events suite", f"{type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        for cli in (a, b, c):
            if cli:
                await cli.disconnect()


async def test_contract_update(ctx):
    a = SioTestClient("A-patch")
    try:
        await a.connect(ctx["A"]["token"])
        await a.wait_hello(5)

        r = requests.post(
            f"{API}/contracts",
            headers=H(ctx["A"]["token"]),
            json={
                "space_id": ctx["space_a"]["space_id"],
                "title": "Employment Contract v2",
                "assigned_staff_id": ctx["staff_id"],
                "body": "Original body",
                "require_drawn_signature_owner": False,
                "require_drawn_signature_staff": False,
            },
            timeout=10,
        )
        if r.status_code != 200:
            R.fail("PATCH setup: POST /contracts", f"status={r.status_code}")
            return
        cid = r.json()["contract_id"]
        a.space_events.clear()

        r = requests.patch(f"{API}/contracts/{cid}", headers=H(ctx["A"]["token"]),
                           json={"title": "Employment Contract (renamed)"}, timeout=10)
        if r.status_code == 200:
            R.ok("PATCH /contracts/{id}")
            evu = await a.wait_for(lambda e: e.get("kind") == "contract" and e.get("action") == "updated", 3)
            R.ok("A receives space.event contract.updated") if evu else R.fail("A receives space.event contract.updated", f"events={a.space_events}")
        else:
            R.fail("PATCH /contracts/{id}", f"status={r.status_code}")
    except Exception as e:
        R.fail("contract_update suite", f"{type(e).__name__}: {e}")
    finally:
        await a.disconnect()


async def test_staff_join_event(ctx):
    a = SioTestClient("A-staff-join")
    try:
        await a.connect(ctx["A"]["token"])
        await a.wait_hello(5)

        roles = get_roles(ctx["A"]["token"], ctx["space_a"]["space_id"])
        cook = next((r for r in roles if (r.get("name") or "").lower() == "cook"), roles[0])
        staff = create_staff(ctx["A"]["token"], ctx["space_a"]["space_id"], "Jordan Kim", cook["role_id"])

        newu = http_register(_uniq_email("jordan"), "test1234", "Jordan Kim")

        a.space_events.clear()
        staff_join_by_code(newu["token"], staff["invite_code"])

        ev = await a.wait_for(lambda e: e.get("kind") == "staff" and e.get("action") == "joined", 3)
        R.ok("A receives space.event staff.joined") if ev else R.fail("A receives space.event staff.joined", f"events={a.space_events}")
    except Exception as e:
        R.fail("staff_join suite", f"{type(e).__name__}: {e}")
    finally:
        await a.disconnect()


async def test_reconnect(ctx):
    a = SioTestClient("A-reconnect")
    try:
        try:
            await a.connect(ctx["A"]["token"])
            await a.wait_hello(5)
            await a.disconnect()
        except Exception as e:
            R.fail("reconnect: initial connect", f"{type(e).__name__}: {e}")
            return

        a2 = SioTestClient("A-reconnect-2")
        try:
            await a2.connect(ctx["A"]["token"])
            await a2.wait_hello(5)
            R.ok("reconnect with valid token works")
        finally:
            await a2.disconnect()

        a3 = SioTestClient("A-reconnect-bad")
        try:
            await a3.connect("definitely-not-a-valid-token")
            R.fail("reconnect with invalid token refused", "connection succeeded")
            await a3.disconnect()
        except Exception as e:
            R.ok("reconnect with invalid token refused", f"{type(e).__name__}")
    finally:
        await a.disconnect()


async def test_concurrent_rooms(ctx):
    space_a2 = create_space(ctx["A"]["token"], space_type="roommates")

    a = SioTestClient("A-multi")
    try:
        await a.connect(ctx["A"]["token"])
        h = await a.wait_hello(5)
        if space_a2["space_id"] in (h.get("spaces") or []) and ctx["space_a"]["space_id"] in (h.get("spaces") or []):
            R.ok("hello.spaces includes both owned spaces")
        else:
            R.fail("hello.spaces includes both owned spaces", f"hello={h}")

        roles2 = get_roles(ctx["A"]["token"], space_a2["space_id"])
        r2 = next(iter(roles2), None)
        if not r2:
            R.fail("concurrent rooms setup: roles", "empty")
            return
        st2 = create_staff(ctx["A"]["token"], space_a2["space_id"], "Casey Lee", r2["role_id"])

        a.space_events.clear()
        r = requests.post(
            f"{API}/contracts",
            headers=H(ctx["A"]["token"]),
            json={
                "space_id": space_a2["space_id"],
                "title": "Second space contract",
                "assigned_staff_id": st2["staff_id"],
                "body": "x",
                "require_drawn_signature_owner": False,
                "require_drawn_signature_staff": False,
            },
            timeout=10,
        )
        if r.status_code != 200:
            R.fail("concurrent rooms: POST contract in space_a2", f"status={r.status_code}")
            return
        ev = await a.wait_for(
            lambda e: e.get("kind") == "contract" and e.get("action") == "created" and e.get("space_id") == space_a2["space_id"],
            3,
        )
        R.ok("A receives events from second space room concurrently") if ev else R.fail("A receives events from second space room concurrently", f"events={a.space_events}")
    except Exception as e:
        R.fail("concurrent_rooms suite", f"{type(e).__name__}: {e}")
    finally:
        await a.disconnect()


async def main():
    print("=== Phase 8: Socket.IO real-time sync tests ===")
    print(f"BASE={BASE}")

    try:
        ctx = await setup_world()
        print(f"setup OK: owner={ctx['A']['user']['user_id']} staff={ctx['B']['user']['user_id']} outsider={ctx['C']['user']['user_id']} space={ctx['space_a']['space_id']}")
    except Exception as e:
        print(f"FATAL: setup failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return

    print("\n-- 1. Connection lifecycle --")
    await test_connection_lifecycle(ctx)

    print("\n-- 3. join_room --")
    await test_join_room(ctx)

    print("\n-- 4/5/6. Contract events + cross-space isolation --")
    await test_contract_events_and_isolation(ctx)

    print("\n-- Contract update event --")
    await test_contract_update(ctx)

    print("\n-- Staff join event --")
    await test_staff_join_event(ctx)

    print("\n-- 7. Reconnect --")
    await test_reconnect(ctx)

    print("\n-- 8. Concurrent rooms --")
    await test_concurrent_rooms(ctx)

    p, f = R.summary()
    os._exit(0 if f == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
