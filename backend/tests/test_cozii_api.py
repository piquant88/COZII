"""Cozii backend API regression tests (pytest)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get('EXPO_PUBLIC_BACKEND_URL', 'https://family-wallet-21.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"


def _session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def user_a():
    s = _session()
    ts = int(time.time())
    email = f"test_a_{ts}@cozii.app"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Tester A"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and "user" in data
    assert "_id" not in data["user"]
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return {"session": s, "token": data["token"], "user": data["user"], "email": email}


@pytest.fixture(scope="module")
def user_b():
    s = _session()
    ts = int(time.time())
    email = f"test_b_{ts}@cozii.app"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Tester B"})
    assert r.status_code == 200, r.text
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return {"session": s, "token": data["token"], "user": data["user"], "email": email}


# ---- Health ----
def test_health():
    r = requests.get(f"{API}/")
    assert r.status_code == 200
    assert "Cozii" in r.json().get("message", "")


# ---- Auth ----
class TestAuth:
    def test_register_dup_returns_409(self, user_a):
        r = user_a["session"].post(f"{API}/auth/register", json={
            "email": user_a["email"], "password": "secret123", "name": "Dup"
        })
        assert r.status_code == 409

    def test_login_success(self, user_a):
        r = requests.post(f"{API}/auth/login", json={"email": user_a["email"], "password": "secret123"})
        assert r.status_code == 200
        body = r.json()
        assert "token" in body and body["user"]["email"] == user_a["email"]
        assert "_id" not in body["user"]

    def test_login_wrong_password(self, user_a):
        r = requests.post(f"{API}/auth/login", json={"email": user_a["email"], "password": "wrong"})
        assert r.status_code == 401

    def test_me_with_token(self, user_a):
        r = user_a["session"].get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["email"] == user_a["email"]
        assert "_id" not in r.json()

    def test_me_without_token_401(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_google_session_invalid(self):
        r = requests.post(f"{API}/auth/google-session", json={"session_id": "INVALID_TEST"})
        assert r.status_code == 401


# ---- Spaces / Categories / Items ----
class TestSpaceFlow:
    space = {}

    def test_create_space_seeds_categories(self, user_a):
        r = user_a["session"].post(f"{API}/spaces", json={"name": "TEST_Home"})
        assert r.status_code == 200, r.text
        sp = r.json()
        assert "_id" not in sp
        assert sp["name"] == "TEST_Home"
        assert user_a["user"]["user_id"] in sp["member_ids"]
        assert len(sp["invite_code"]) == 6
        TestSpaceFlow.space = sp

        # 5 starter categories
        r2 = user_a["session"].get(f"{API}/categories", params={"space_id": sp["space_id"]})
        assert r2.status_code == 200
        cats = r2.json()
        names = {c["name"] for c in cats}
        assert {"Food & Pantry", "Skincare", "Closet", "Toiletries", "Cleaning"}.issubset(names)
        assert all("_id" not in c for c in cats)

    def test_list_spaces(self, user_a):
        r = user_a["session"].get(f"{API}/spaces")
        assert r.status_code == 200
        assert any(s["space_id"] == TestSpaceFlow.space["space_id"] for s in r.json())

    def test_join_space(self, user_a, user_b):
        code = TestSpaceFlow.space["invite_code"]
        r = user_b["session"].post(f"{API}/spaces/join", json={"invite_code": code})
        assert r.status_code == 200
        sp = r.json()
        assert user_b["user"]["user_id"] in sp["member_ids"]

    def test_join_space_invalid_code(self, user_b):
        r = user_b["session"].post(f"{API}/spaces/join", json={"invite_code": "ZZZZZZ"})
        assert r.status_code == 404

    def test_space_members(self, user_a):
        sid = TestSpaceFlow.space["space_id"]
        r = user_a["session"].get(f"{API}/spaces/{sid}/members")
        assert r.status_code == 200
        members = r.json()
        assert len(members) >= 2
        assert all("_id" not in m for m in members)

    def test_custom_category_create_and_update_and_delete(self, user_a):
        sid = TestSpaceFlow.space["space_id"]
        r = user_a["session"].post(f"{API}/categories", json={
            "space_id": sid, "name": "TEST_Books", "icon": "Box", "tint": "mint",
            "fields": [{"key": "author", "label": "Author", "type": "text"}]
        })
        assert r.status_code == 200, r.text
        cat = r.json()
        assert cat["name"] == "TEST_Books"
        assert cat["fields"][0]["key"] == "author"

        # update
        r2 = user_a["session"].patch(f"{API}/categories/{cat['category_id']}", json={"name": "TEST_BooksX"})
        assert r2.status_code == 200
        assert r2.json()["name"] == "TEST_BooksX"

        # create an item in the category
        item_r = user_a["session"].post(f"{API}/items", json={
            "space_id": sid, "category_id": cat["category_id"], "name": "TEST_Book_Item", "price": 12.5
        })
        assert item_r.status_code == 200
        item_id = item_r.json()["item_id"]

        # delete category cascades item
        r3 = user_a["session"].delete(f"{API}/categories/{cat['category_id']}")
        assert r3.status_code == 200

        got = user_a["session"].get(f"{API}/items/{item_id}")
        assert got.status_code == 404

    def test_item_crud_and_status_roundtrip(self, user_a):
        sid = TestSpaceFlow.space["space_id"]
        cats = user_a["session"].get(f"{API}/categories", params={"space_id": sid}).json()
        food_cat = next(c for c in cats if c["name"] == "Food & Pantry")

        # create item
        r = user_a["session"].post(f"{API}/items", json={
            "space_id": sid, "category_id": food_cat["category_id"],
            "name": "TEST_Milk", "price": 3.5, "quantity": 2, "status": "available",
            "expiry_date": "2030-01-01"
        })
        assert r.status_code == 200, r.text
        item = r.json()
        assert "_id" not in item
        iid = item["item_id"]

        # list items filtered
        lst = user_a["session"].get(f"{API}/items", params={"space_id": sid, "category_id": food_cat["category_id"]})
        assert lst.status_code == 200
        assert any(i["item_id"] == iid for i in lst.json())

        # mark finished
        r2 = user_a["session"].patch(f"{API}/items/{iid}", json={"status": "finished"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "finished"

        # CRITICAL: toggle back to available (user requirement)
        r3 = user_a["session"].patch(f"{API}/items/{iid}", json={"status": "available"})
        assert r3.status_code == 200, r3.text
        assert r3.json()["status"] == "available"

        # verify via GET
        g = user_a["session"].get(f"{API}/items/{iid}")
        assert g.status_code == 200
        assert g.json()["status"] == "available"

        # delete
        d = user_a["session"].delete(f"{API}/items/{iid}")
        assert d.status_code == 200
        g2 = user_a["session"].get(f"{API}/items/{iid}")
        assert g2.status_code == 404

    def test_activity_feed(self, user_a):
        sid = TestSpaceFlow.space["space_id"]
        r = user_a["session"].get(f"{API}/activity", params={"space_id": sid})
        assert r.status_code == 200
        acts = r.json()
        assert isinstance(acts, list) and len(acts) > 0
        assert all("_id" not in a for a in acts)

    def test_stats(self, user_a):
        sid = TestSpaceFlow.space["space_id"]
        # ensure 1 priced item exists this month
        cats = user_a["session"].get(f"{API}/categories", params={"space_id": sid}).json()
        cat = cats[0]
        user_a["session"].post(f"{API}/items", json={
            "space_id": sid, "category_id": cat["category_id"],
            "name": "TEST_Priced", "price": 9.99
        })
        r = user_a["session"].get(f"{API}/stats", params={"space_id": sid})
        assert r.status_code == 200
        s = r.json()
        for k in ("total_items", "low_items", "expiring_soon", "spent_this_month"):
            assert k in s
        assert s["spent_this_month"] >= 9.99

    def test_non_member_forbidden(self, user_a):
        # create new user C and try accessing A's space
        ts = int(time.time())
        sC = _session()
        r = sC.post(f"{API}/auth/register", json={"email": f"test_c_{ts}@cozii.app", "password": "secret123", "name": "C"})
        token = r.json()["token"]
        sC.headers.update({"Authorization": f"Bearer {token}"})
        sid = TestSpaceFlow.space["space_id"]
        r2 = sC.get(f"{API}/categories", params={"space_id": sid})
        assert r2.status_code == 403
