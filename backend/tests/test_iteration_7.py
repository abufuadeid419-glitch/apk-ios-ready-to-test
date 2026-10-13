"""
Iteration 7 — Convex-backed verification for Android PDF share bugfix retest.
- Code review of /app/frontend/src/printDoc.ts for copySync usage (static sanity check).
- Backend: ensure stock-requests listing / reject / fulfill endpoints are still live for test_token_agent and test_token_owner.
- Verify we can "clear" pending requests so the agent + button becomes visible for interactive UI testing.
"""
import os
import re
import requests
import pytest

BASE = "https://fearless-ostrich-878.eu-west-1.convex.site/api"
OWNER = "test_token_owner"
AGENT = "test_token_agent"

PRODUCT_ID = "504c618ff474444793b7f4ac7ba26bc1"  # from review_request


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- printDoc.ts static check ----------
def test_printdoc_uses_copySync():
    with open("/app/frontend/src/printDoc.ts") as f:
        src = f.read()
    assert "copySync(dest)" in src, "printDoc.ts should call copySync() (sync) after iteration_6 RCA"
    # old async-dropped-promise call must be gone
    assert not re.search(r"new File\(uri\)\.copy\(dest\)\s*;", src), \
        "printDoc.ts still has unawaited File#copy(dest); this is the race bug"
    # delete() must stay sync too (no deleteAsync usage without await)
    assert "dest.delete()" in src


# ---------- stock-requests endpoints ----------
@pytest.fixture(scope="module")
def pending_reqs_for_product():
    r = requests.get(f"{BASE}/stock-requests", headers=auth(OWNER), timeout=15)
    assert r.status_code == 200, r.text
    items = r.json()
    assert isinstance(items, list)
    pending = [
        req for req in items
        if req.get("status") == "PENDING"
        and any(x.get("product_id") == PRODUCT_ID for x in req.get("items", []))
    ]
    return pending


def test_owner_can_list_stock_requests():
    r = requests.get(f"{BASE}/stock-requests", headers=auth(OWNER), timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_agent_can_list_own_stock_requests():
    r = requests.get(f"{BASE}/stock-requests", headers=auth(AGENT), timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_owner_rejects_pending_for_target_product(pending_reqs_for_product):
    """Clear pending request on PRODUCT_ID so the agent + button becomes visible for UI test."""
    if not pending_reqs_for_product:
        pytest.skip("No pending request for target product — + button should already be visible for agent")
    for req in pending_reqs_for_product:
        rid = req["id"]
        resp = requests.post(f"{BASE}/stock-requests/{rid}/reject", headers=auth(OWNER), timeout=15)
        assert resp.status_code in (200, 204), f"reject failed {resp.status_code} {resp.text}"
    # verify cleared
    r = requests.get(f"{BASE}/stock-requests", headers=auth(OWNER), timeout=15)
    still_pending = [
        req for req in r.json()
        if req.get("status") == "PENDING"
        and any(x.get("product_id") == PRODUCT_ID for x in req.get("items", []))
    ]
    assert not still_pending, "pending still present after reject"


def test_agent_creates_stock_request_with_package_unit():
    """Simulate the stock-request-sheet send-stock-request-button flow via API."""
    # Convex createRequest validator only allows {product_id, quantity, unit};
    # product_name / unit_label / pieces are computed server-side via unitQty().
    payload = {
        "items": [{
            "product_id": PRODUCT_ID,
            "quantity": 1,
            "unit": "PACKAGE",
        }]
    }
    r = requests.post(f"{BASE}/stock-requests", headers=auth(AGENT), json=payload, timeout=15)
    assert r.status_code in (200, 201), r.text
    created = r.json()
    # verify persisted and shows up in list for the agent with PACKAGE / 'كرتونة'
    list_r = requests.get(f"{BASE}/stock-requests", headers=auth(AGENT), timeout=15)
    assert list_r.status_code == 200
    found = [req for req in list_r.json() if req.get("status") == "PENDING"
             and any(x.get("product_id") == PRODUCT_ID and x.get("unit") == "PACKAGE" for x in req.get("items", []))]
    assert found, f"created PACKAGE stock-request not found in agent list; created={created}"
    item = next(x for x in found[0]["items"] if x["product_id"] == PRODUCT_ID)
    assert item.get("unit_label") == "كرتونة" or "كرتون" in (item.get("unit_label") or "")
    assert item.get("pieces") == 10


def test_owner_sees_new_request_and_can_fulfill():
    r = requests.get(f"{BASE}/stock-requests", headers=auth(OWNER), timeout=15)
    assert r.status_code == 200
    pending = [req for req in r.json() if req.get("status") == "PENDING"
               and any(x.get("product_id") == PRODUCT_ID and x.get("unit") == "PACKAGE" for x in req.get("items", []))]
    assert pending, "owner cannot see the new PACKAGE request"
    rid = pending[0]["id"]
    # fulfill it (creates a delivery) to leave inventory clean for next iteration
    resp = requests.post(f"{BASE}/stock-requests/{rid}/fulfill", headers=auth(OWNER), timeout=15)
    assert resp.status_code in (200, 204), resp.text


def test_my_inventory_still_lists_target_product():
    r = requests.get(f"{BASE}/my/inventory", headers=auth(AGENT), timeout=15)
    assert r.status_code == 200
    inv = r.json()
    assert any(i.get("product_id") == PRODUCT_ID for i in inv), \
        f"target product {PRODUCT_ID} missing from agent inventory"
