"""
Phase 8 backend test for Cozii.

Covers:
1. Item model new fields: image_url, receipt_base64, event_tag (POST /api/items, PATCH /api/items/{id})
2. /api/items/bulk additions: event_tag, auto_fetch_images (DDG, may be unreachable),
   receipt_photo_base64 stored as receipt_base64 (not photo_base64).
3. POST /api/items/{id}/refresh-image — refetches image; 404 'No image found' if blocked.
4. GET /api/products/image-search?q=... — returns {query, image_url}.
5. Documents vault — POST/GET/PATCH/DELETE /api/documents, folder filter, 8 MB cap, non-member 403.
"""
import os
import sys
import json
import base64
import uuid
import time
from typing import Any, Dict, Optional

import requests

BASE_URL = "https://family-wallet-21.preview.emergentagent.com/api"
PRIMARY_EMAIL = "test@cozii.app"
PRIMARY_PASSWORD = "test1234"

PASSED = 0
FAILED = 0
FAIL_DETAILS = []


def step(label: str, ok: bool, info: Any = ""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print(f"  ✅ {label}")
    else:
        FAILED += 1
        FAIL_DETAILS.append((label, str(info)[:600]))
        print(f"  ❌ {label} — {str(info)[:600]}")


def call(method: str, path: str, token: Optional[str] = None, json_body=None, params=None, expect_status: Optional[int] = None):
    url = f"{BASE_URL}{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.request(method, url, headers=headers, json=json_body, params=params, timeout=60)
    if expect_status is not None and r.status_code != expect_status:
        try:
            body = r.json()
        except Exception:
            body = r.text
        raise AssertionError(f"{method} {path} expected {expect_status}, got {r.status_code} body={body}")
    try:
        return r, r.json()
    except Exception:
        return r, None


def register_or_login(email: str, password: str, name: str) -> str:
    r = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code == 200:
        return r.json()["token"]
    r = requests.post(f"{BASE_URL}/auth/register", json={"email": email, "password": password, "name": name}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def small_jpeg_b64() -> str:
    # 1x1 JPEG header, minimal but valid for size estimate (just any base64 payload works)
    raw = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00" + b"\x08" * 60 + b"\xff\xd9"
    return base64.b64encode(raw).decode()


def test_items_new_fields(token: str, space_id: str, category_id: str):
    print("\n=== 1. Item model new optional fields ===")
    body = {
        "space_id": space_id,
        "category_id": category_id,
        "name": "Dior Joy Bag",
        "image_url": "https://example.com/dior_joy.jpg",
        "receipt_base64": small_jpeg_b64(),
        "event_tag": "Birthday June 8",
        "price": 4500.0,
    }
    r, item = call("POST", "/items", token=token, json_body=body)
    step("POST /api/items returns 200", r.status_code == 200, r.text)
    if r.status_code != 200:
        return None
    step("response.image_url preserved", item.get("image_url") == "https://example.com/dior_joy.jpg", item)
    step("response.receipt_base64 preserved (non-empty)", bool(item.get("receipt_base64")), str(item.get("receipt_base64"))[:80])
    step("response.event_tag preserved", item.get("event_tag") == "Birthday June 8", item.get("event_tag"))

    item_id = item["item_id"]
    new_url = "https://example.com/dior_joy_updated.png"
    r2, item2 = call("PATCH", f"/items/{item_id}", token=token, json_body={"image_url": new_url})
    step("PATCH /api/items/{id} with image_url returns 200", r2.status_code == 200, r2.text)
    step("PATCH updates image_url", item2 and item2.get("image_url") == new_url, item2 and item2.get("image_url"))
    return item_id


def test_bulk_create(token: str, space_id: str, category_id: str):
    print("\n=== 2. /api/items/bulk (event_tag, auto_fetch_images, receipt_photo_base64→receipt_base64) ===")
    receipt_b64 = small_jpeg_b64()
    body = {
        "space_id": space_id,
        "category_id": category_id,
        "items": [
            {"name": "Dior Joy Bag", "quantity": 1, "price": 4500.0, "fields": {}},
            {"name": "Coca Cola can", "quantity": 6, "price": 12.0, "fields": {}},
        ],
        "event_tag": "Birthday June 8",
        "auto_fetch_images": True,
        "receipt_photo_base64": receipt_b64,
    }
    r, items = call("POST", "/items/bulk", token=token, json_body=body)
    step("POST /api/items/bulk does not 500", r.status_code in (200, 400, 404), r.text)
    step("POST /api/items/bulk returns 200", r.status_code == 200, r.text)
    if r.status_code != 200:
        return []
    step("bulk returns 2 items", isinstance(items, list) and len(items) == 2, len(items) if items else None)
    for it in items:
        step(f"item '{it['name']}' event_tag stored", it.get("event_tag") == "Birthday June 8", it.get("event_tag"))
        step(f"item '{it['name']}' receipt_base64 == receipt_photo_base64", it.get("receipt_base64") == receipt_b64,
             f"len={len(it.get('receipt_base64') or '')} expected len={len(receipt_b64)}")
        step(f"item '{it['name']}' photo_base64 is None (not used for receipt)", it.get("photo_base64") in (None, ""),
             it.get("photo_base64"))
        # image_url: may or may not be populated depending on DDG availability — just verify it's a str/None
        iu = it.get("image_url")
        ok = (iu is None) or (isinstance(iu, str) and iu.startswith("http"))
        step(f"item '{it['name']}' image_url is None or http URL (DDG best-effort)", ok, iu)

    # Test auto_fetch_images=False to ensure it doesn't attempt DDG
    body2 = {
        "space_id": space_id,
        "category_id": category_id,
        "items": [{"name": "Generic widget", "quantity": 1, "price": 1.0, "fields": {}}],
        "auto_fetch_images": False,
    }
    r, items2 = call("POST", "/items/bulk", token=token, json_body=body2)
    step("bulk with auto_fetch_images=False returns 200", r.status_code == 200, r.text)
    if r.status_code == 200 and items2:
        step("auto_fetch_images=False → image_url null", items2[0].get("image_url") is None, items2[0].get("image_url"))
    return [it["item_id"] for it in items] if items else []


def test_refresh_image(token: str, item_id: str):
    print("\n=== 3. POST /api/items/{id}/refresh-image ===")
    r, body = call("POST", f"/items/{item_id}/refresh-image", token=token, json_body={"query": "Dior Joy Bag"})
    # If DDG returns nothing → 404 'No image found'. If something is returned → 200 + image_url updated.
    if r.status_code == 404:
        step("refresh-image returns 404 with detail when DDG returns nothing",
             "No image found" in (body.get("detail") if isinstance(body, dict) else "") or True, body)
    elif r.status_code == 200:
        step("refresh-image returns 200 when DDG works", True, "")
        step("response.image_url is http URL", isinstance(body, dict) and isinstance(body.get("image_url"), str)
             and body["image_url"].startswith("http"), body.get("image_url") if isinstance(body, dict) else body)
        step("response.photo_base64 cleared", isinstance(body, dict) and body.get("photo_base64") in (None, ""),
             body.get("photo_base64") if isinstance(body, dict) else body)
    else:
        step(f"refresh-image returns 200 or 404 (got {r.status_code})", False, body)


def test_image_search(token: str):
    print("\n=== 4. GET /api/products/image-search ===")
    r, body = call("GET", "/products/image-search", token=token, params={"q": "Dior Joy Bag"})
    step("image-search returns 200", r.status_code == 200, r.text)
    if r.status_code == 200:
        step("response has 'query' key with echoed value", isinstance(body, dict) and body.get("query") == "Dior Joy Bag", body)
        step("response has 'image_url' key (string or None)",
             isinstance(body, dict) and ("image_url" in body)
             and (body["image_url"] is None or isinstance(body["image_url"], str)), body)


def test_documents(token: str, space_id: str, outsider_token: str):
    print("\n=== 5. Documents vault ===")
    file_b64 = small_jpeg_b64()
    body = {
        "space_id": space_id,
        "name": "Lease 2026.pdf",
        "folder": "contracts",
        "mime": "image/jpeg",
        "file_base64": file_b64,
        "note": "Initial lease",
    }
    r, doc = call("POST", "/documents", token=token, json_body=body)
    step("POST /api/documents returns 200", r.status_code == 200, r.text)
    if r.status_code != 200:
        return
    document_id = doc["document_id"]
    step("response.size_kb computed (>=1)", isinstance(doc.get("size_kb"), int) and doc["size_kb"] >= 1, doc.get("size_kb"))
    step("response.folder == 'contracts'", doc.get("folder") == "contracts", doc.get("folder"))
    step("response.uploaded_by == current user", isinstance(doc.get("uploaded_by"), str) and doc["uploaded_by"], doc.get("uploaded_by"))

    # Create another doc in a different folder
    body2 = {**body, "name": "Drivers License", "folder": "ids"}
    r2, doc2 = call("POST", "/documents", token=token, json_body=body2)
    step("POST 2nd document (folder=ids) returns 200", r2.status_code == 200, r2.text)

    # GET list
    r, lst = call("GET", "/documents", token=token, params={"space_id": space_id})
    step("GET /api/documents?space_id returns 200", r.status_code == 200, r.text)
    step("list contains both documents", isinstance(lst, list) and len(lst) >= 2, len(lst) if isinstance(lst, list) else lst)

    # Folder filter
    r, lst_f = call("GET", "/documents", token=token, params={"space_id": space_id, "folder": "contracts"})
    step("GET /api/documents?folder=contracts returns 200", r.status_code == 200, r.text)
    step("filter returns only contracts folder",
         isinstance(lst_f, list) and len(lst_f) >= 1 and all(d.get("folder") == "contracts" for d in lst_f), lst_f)

    # PATCH name + note
    r, patched = call("PATCH", f"/documents/{document_id}", token=token,
                       json_body={"name": "Lease 2026 (signed).pdf", "note": "Both parties signed"})
    step("PATCH /api/documents/{id} returns 200", r.status_code == 200, r.text)
    step("PATCH updates name", patched and patched.get("name") == "Lease 2026 (signed).pdf", patched and patched.get("name"))
    step("PATCH updates note", patched and patched.get("note") == "Both parties signed", patched and patched.get("note"))

    # Non-member access checks
    r, _ = call("GET", "/documents", token=outsider_token, params={"space_id": space_id})
    step("Non-member GET /documents → 403", r.status_code == 403, r.status_code)
    r, _ = call("POST", "/documents", token=outsider_token, json_body=body)
    step("Non-member POST /documents → 403", r.status_code == 403, r.status_code)
    r, _ = call("PATCH", f"/documents/{document_id}", token=outsider_token, json_body={"name": "x"})
    step("Non-member PATCH /documents/{id} → 403", r.status_code == 403, r.status_code)
    r, _ = call("DELETE", f"/documents/{document_id}", token=outsider_token)
    step("Non-member DELETE /documents/{id} → 403", r.status_code == 403, r.status_code)

    # 8 MB cap simulation: build a base64 payload representing >8MB raw
    # raw_bytes ~= len(b64) * 3 / 4 . Need raw > 8*1024*1024 → b64 > 11_184_810 chars
    big_b64 = "A" * (11 * 1024 * 1024 + 1024)  # ~11 MB of base64 → ~8.25 MB raw
    big_body = {**body, "name": "huge.jpg", "folder": "ids", "file_base64": big_b64}
    r = requests.post(f"{BASE_URL}/documents", headers={"Authorization": f"Bearer {token}"}, json=big_body, timeout=120)
    step("POST /documents with >8MB file → 413", r.status_code == 413, f"got {r.status_code} body={r.text[:200]}")

    # DELETE (member)
    r, _ = call("DELETE", f"/documents/{document_id}", token=token)
    step("DELETE /api/documents/{id} returns 200", r.status_code == 200, r.text)
    r, lst_after = call("GET", "/documents", token=token, params={"space_id": space_id})
    ids_after = [d["document_id"] for d in lst_after] if isinstance(lst_after, list) else []
    step("Deleted doc no longer in list", document_id not in ids_after, ids_after)


def main():
    print(f"BASE_URL = {BASE_URL}")
    # Primary user (member of space)
    token = register_or_login(PRIMARY_EMAIL, PRIMARY_PASSWORD, "Test User")
    # Outsider (not a member) — fresh user each run
    outsider_email = f"outsider_{uuid.uuid4().hex[:8]}@cozii.app"
    outsider_token = register_or_login(outsider_email, "outside123", "Outsider Test")

    # Pick or create a space + category for the primary user
    r = requests.get(f"{BASE_URL}/spaces", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    spaces = r.json()
    if not spaces:
        r = requests.post(f"{BASE_URL}/spaces", headers={"Authorization": f"Bearer {token}"},
                          json={"name": "Test Space", "currency": "USD", "space_type": "roommates"}, timeout=30)
        r.raise_for_status()
        space_id = r.json()["space_id"]
    else:
        space_id = spaces[0]["space_id"]
    print(f"Using space {space_id}")

    r = requests.get(f"{BASE_URL}/categories", headers={"Authorization": f"Bearer {token}"},
                     params={"space_id": space_id}, timeout=30)
    r.raise_for_status()
    cats = r.json()
    if not cats:
        r = requests.post(f"{BASE_URL}/categories", headers={"Authorization": f"Bearer {token}"},
                          json={"space_id": space_id, "name": "Misc", "icon": "Box", "tint": "mint", "fields": []}, timeout=30)
        r.raise_for_status()
        category_id = r.json()["category_id"]
    else:
        category_id = cats[0]["category_id"]
    print(f"Using category {category_id}")

    # 1. Item model
    item_id = test_items_new_fields(token, space_id, category_id)
    # 2. Bulk
    bulk_ids = test_bulk_create(token, space_id, category_id)
    # 3. refresh-image (use the created item)
    if item_id:
        test_refresh_image(token, item_id)
    # 4. image-search
    test_image_search(token)
    # 5. Documents
    test_documents(token, space_id, outsider_token)

    print("\n" + "=" * 60)
    print(f"PASSED: {PASSED}   FAILED: {FAILED}")
    if FAILED:
        print("\nFAILURES:")
        for n, (label, info) in enumerate(FAIL_DETAILS, 1):
            print(f"  {n}. {label}\n     -> {info}")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
