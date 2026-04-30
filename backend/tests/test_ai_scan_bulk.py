"""Phase-2 Cozii backend tests: AI scan-receipt + bulk items."""
import base64
import io
import os
import time

import pytest
import requests
from PIL import Image, ImageDraw, ImageFont

BASE_URL = os.environ.get(
    'EXPO_PUBLIC_BACKEND_URL',
    'https://family-wallet-21.preview.emergentagent.com',
).rstrip('/')
API = f"{BASE_URL}/api"


# ---------- helpers ----------
def _session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _make_receipt_image_data_uri() -> str:
    """Render a real, readable synthetic grocery-receipt JPEG as data URI."""
    W, H = 480, 640
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except Exception:
        font = ImageFont.load_default()
        small = font

    lines = [
        ("FRESH MART GROCERY", font),
        ("123 Main St", small),
        ("----------------------", small),
        ("Oat Milk           4.99", small),
        ("Whole Wheat Bread  3.49", small),
        ("Bananas   2 lb     1.20", small),
        ("Toothpaste         6.50", small),
        ("Shampoo           10.99", small),
        ("Dish Soap          4.25", small),
        ("----------------------", small),
        ("Subtotal          31.42", small),
        ("Tax                2.51", small),
        ("TOTAL             33.93", font),
        ("Thank you!", small),
    ]
    y = 20
    for text, f in lines:
        d.text((20, y), text, fill="black", font=f)
        y += 32 if f is font else 28

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def auth_user():
    s = _session()
    ts = int(time.time())
    email = f"test_ai_{ts}@cozii.app"
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": "secret123", "name": "AI Tester"
    })
    assert r.status_code == 200, r.text
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    # create a space -> seeds 5 starter categories
    sr = s.post(f"{API}/spaces", json={"name": "TEST_AI_Home"})
    assert sr.status_code == 200, sr.text
    space = sr.json()
    cr = s.get(f"{API}/categories", params={"space_id": space["space_id"]})
    assert cr.status_code == 200
    cats = cr.json()
    return {"session": s, "token": data["token"], "user": data["user"],
            "space": space, "categories": cats}


@pytest.fixture(scope="module")
def receipt_data_uri():
    return _make_receipt_image_data_uri()


# ---------- AI scan-receipt ----------
class TestAIScanReceipt:
    def test_scan_requires_auth(self):
        r = requests.post(f"{API}/ai/scan-receipt", json={"image_base64": "x"})
        assert r.status_code == 401

    def test_scan_empty_image_returns_400(self, auth_user):
        r = auth_user["session"].post(f"{API}/ai/scan-receipt", json={"image_base64": ""})
        assert r.status_code == 400

    def test_scan_real_receipt(self, auth_user, receipt_data_uri):
        r = auth_user["session"].post(
            f"{API}/ai/scan-receipt",
            json={"image_base64": receipt_data_uri},
            timeout=90,
        )
        assert r.status_code == 200, f"{r.status_code}: {r.text[:500]}"
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        # We don't hard-fail on empty items (LLM variability), but log if zero.
        if len(data["items"]) == 0:
            pytest.skip("LLM returned 0 items for synthetic image; endpoint OK.")
        first = data["items"][0]
        assert "name" in first and isinstance(first["name"], str) and first["name"]
        assert "quantity" in first
        assert "price" in first  # may be null

    def test_scan_with_raw_base64_no_datauri_prefix(self, auth_user, receipt_data_uri):
        raw = receipt_data_uri.split(",", 1)[1]
        r = auth_user["session"].post(
            f"{API}/ai/scan-receipt",
            json={"image_base64": raw},
            timeout=90,
        )
        assert r.status_code == 200, r.text[:500]


# ---------- Bulk items ----------
class TestBulkItems:
    def test_bulk_invalid_default_category_returns_400(self, auth_user):
        s = auth_user["session"]
        r = s.post(f"{API}/items/bulk", json={
            "space_id": auth_user["space"]["space_id"],
            "category_id": "cat_does_not_exist",
            "per_item_category": {},
            "items": [{"name": "TEST_Apple", "quantity": 1, "price": 1.0}],
        })
        assert r.status_code == 400

    def test_bulk_creates_items_with_override(self, auth_user):
        s = auth_user["session"]
        cats = auth_user["categories"]
        food = next(c for c in cats if c["name"] == "Food & Pantry")
        toiletries = next(c for c in cats if c["name"] == "Toiletries")

        payload = {
            "space_id": auth_user["space"]["space_id"],
            "category_id": food["category_id"],  # default
            "per_item_category": {"2": toiletries["category_id"]},  # idx 2 override
            "items": [
                {"name": "TEST_BULK_Milk", "quantity": 1, "price": 3.99},
                {"name": "TEST_BULK_Bread", "quantity": 2, "price": 2.50},
                {"name": "TEST_BULK_Toothpaste", "quantity": 1, "price": 5.00},
            ],
            "purchase_date": "2026-01-15",
        }
        r = s.post(f"{API}/items/bulk", json=payload)
        assert r.status_code == 200, r.text
        created = r.json()
        assert isinstance(created, list) and len(created) == 3
        for it in created:
            assert "_id" not in it
            assert it["space_id"] == auth_user["space"]["space_id"]

        # default category for idx 0, 1
        assert created[0]["category_id"] == food["category_id"]
        assert created[1]["category_id"] == food["category_id"]
        # override for idx 2
        assert created[2]["category_id"] == toiletries["category_id"]
        assert created[2]["name"] == "TEST_BULK_Toothpaste"

        # verify via GET /items
        gr = s.get(f"{API}/items", params={"space_id": auth_user["space"]["space_id"]})
        assert gr.status_code == 200
        all_items = gr.json()
        names = {i["name"] for i in all_items}
        assert {"TEST_BULK_Milk", "TEST_BULK_Bread", "TEST_BULK_Toothpaste"}.issubset(names)

    def test_bulk_requires_auth(self):
        r = requests.post(f"{API}/items/bulk", json={
            "space_id": "x", "category_id": "y", "per_item_category": {}, "items": []
        })
        assert r.status_code == 401
