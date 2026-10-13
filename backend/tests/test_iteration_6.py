"""Iteration 6 — regression suite covering org profile save, pricing method LATEST,
price change notifications, stock requests by unit, supplier contacts, and auth gates."""
import os
import time
import pytest
import requests

BASE = "https://fearless-ostrich-878.eu-west-1.convex.site/api"
OWNER = {"Authorization": "Bearer test_token_owner"}
ACCT = {"Authorization": "Bearer test_token_acct"}
AGENT = {"Authorization": "Bearer test_token_agent"}
DEV = {"Authorization": "Bearer test_token_dev"}


# ---------- Health / auth sanity ----------
class TestHealth:
    def test_owner_profile_reachable(self):
        r = requests.get(f"{BASE}/org/profile", headers=OWNER, timeout=15)
        assert r.status_code == 200, r.text
        assert "name" in r.json()

    def test_bad_token_rejected(self):
        r = requests.get(f"{BASE}/org/profile", headers={"Authorization": "Bearer nope"}, timeout=15)
        assert r.status_code in (401, 403)


# ---------- Org profile save with extra fields ----------
class TestOrgProfileSave:
    def test_save_profile_rejects_extras_old_bug(self):
        """BUG REPRO: previously /org/profile mutator threw ArgumentValidationError
        when payload included alt_currency/currency/has_logo/exchange_rate.
        After fix the mutator should accept & ignore those."""
        r = requests.get(f"{BASE}/org/profile", headers=OWNER, timeout=15)
        assert r.status_code == 200
        current = r.json()
        payload = {
            "name": current.get("name") or "TEST مؤسسة الاختبار",
            "phone": current.get("phone", ""),
            "email": current.get("email", ""),
            "address": current.get("address", ""),
            "tax_no": current.get("tax_no", ""),
            "cr_no": current.get("cr_no", ""),
            "invoice_footer": current.get("invoice_footer", ""),
            "phone_country_code": current.get("phone_country_code", "963"),
            # Extra fields that OrgProfile.tsx used to send accidentally
            "alt_currency": "USD",
            "currency": current.get("currency") or "ل.س",
            "has_logo": True,
            "exchange_rate": current.get("exchange_rate", 0),
        }
        r2 = requests.put(f"{BASE}/org/profile", headers=OWNER, json=payload, timeout=15)
        assert r2.status_code == 200, f"Expected 200 (extras should be ignored). Body: {r2.text}"

    def test_save_profile_minimal_fields(self):
        r = requests.get(f"{BASE}/org/profile", headers=OWNER, timeout=15).json()
        payload = {
            "name": r.get("name") or "TEST مؤسسة الاختبار",
            "phone": r.get("phone", ""),
            "email": r.get("email", ""),
            "address": r.get("address", ""),
            "tax_no": r.get("tax_no", ""),
            "cr_no": r.get("cr_no", ""),
            "invoice_footer": r.get("invoice_footer", ""),
            "phone_country_code": r.get("phone_country_code", "963"),
        }
        r2 = requests.put(f"{BASE}/org/profile", headers=OWNER, json=payload, timeout=15)
        assert r2.status_code == 200, r2.text
        # verify persistence
        r3 = requests.get(f"{BASE}/org/profile", headers=OWNER, timeout=15).json()
        assert r3.get("name") == payload["name"]


# ---------- Pricing method LATEST ----------
class TestPricingMethod:
    def test_set_latest(self):
        r = requests.put(f"{BASE}/org/pricing-method", headers=OWNER,
                         json={"method": "LATEST"}, timeout=15)
        assert r.status_code == 200, r.text

    def test_invalid_method_rejected(self):
        r = requests.put(f"{BASE}/org/pricing-method", headers=OWNER,
                         json={"method": "BOGUS"}, timeout=15)
        assert r.status_code in (400, 422, 500)

    def test_non_owner_rejected(self):
        r = requests.put(f"{BASE}/org/pricing-method", headers=AGENT,
                         json={"method": "LATEST"}, timeout=15)
        assert r.status_code in (401, 403, 400, 500)


# ---------- Notifications (price change) ----------
class TestNotifications:
    def test_agent_notifications_list(self):
        r = requests.get(f"{BASE}/notifications", headers=AGENT, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # API returns {items: [...], unread: int}
        assert isinstance(data, dict) and "items" in data and "unread" in data
        assert isinstance(data["items"], list)

    def test_price_change_notification_present(self):
        """BUG FEATURE: distributor should receive a price_change notification
        after a purchase that changed sale price."""
        r = requests.get(f"{BASE}/notifications", headers=AGENT, timeout=15).json()
        items = r.get("items", [])
        has_price_change = any(
            (n.get("type") == "price_change") or
            ("تغيّر سعر" in (n.get("title") or "")) or
            ("سعر البيع" in (n.get("body") or ""))
            for n in items
        )
        assert has_price_change, f"No price_change notification found. Items: {items[:3]}"


# ---------- Stock requests ----------
class TestStockRequests:
    def test_list_requests(self):
        r = requests.get(f"{BASE}/stock-requests", headers=AGENT, timeout=15)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_create_request_with_unit_package(self):
        inv = requests.get(f"{BASE}/my/inventory", headers=AGENT, timeout=15)
        assert inv.status_code == 200, inv.text
        items = inv.json()
        if not items:
            pytest.skip("agent has no inventory to request from")
        # Prefer product with pieces_per_package > 1
        target = next((i for i in items if (i.get("pieces_per_package") or 1) > 1), items[0])
        pid = target["product_id"]
        payload = {"items": [{"product_id": pid, "quantity": 1, "unit": "PACKAGE"}]}
        r = requests.post(f"{BASE}/stock-requests", headers=AGENT, json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        # verify request now listed
        lst = requests.get(f"{BASE}/stock-requests", headers=AGENT, timeout=15).json()
        assert any(any(x["product_id"] == pid for x in req["items"]) for req in lst), "created request not visible"

    def test_create_request_piece_unit(self):
        inv = requests.get(f"{BASE}/my/inventory", headers=AGENT, timeout=15).json()
        if not inv:
            pytest.skip("agent has no inventory")
        pid = inv[0]["product_id"]
        payload = {"items": [{"product_id": pid, "quantity": 3, "unit": "PIECE"}]}
        r = requests.post(f"{BASE}/stock-requests", headers=AGENT, json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text


# ---------- Suppliers (contacts) ----------
class TestSuppliers:
    def test_list_suppliers(self):
        r = requests.get(f"{BASE}/suppliers", headers=OWNER, timeout=15)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_save_supplier_phone(self):
        # Find a supplier (seeded TEST_SUP*) else use any
        lst = requests.get(f"{BASE}/suppliers", headers=OWNER, timeout=15).json()
        name = None
        if lst:
            name = next((s["name"] for s in lst if "TEST_SUP" in (s.get("name") or "")), lst[0]["name"])
        else:
            # Nothing to save against — must have at least seeded supplier
            pytest.skip("no suppliers seeded")
        r = requests.put(f"{BASE}/suppliers", headers=OWNER,
                         json={"name": name, "phone": "0944123456"}, timeout=15)
        assert r.status_code == 200, r.text
        # verify
        after = requests.get(f"{BASE}/suppliers", headers=OWNER, timeout=15).json()
        hit = next((s for s in after if s["name"] == name), None)
        assert hit and hit.get("phone") == "0944123456"

    def test_non_owner_cannot_save(self):
        r = requests.put(f"{BASE}/suppliers", headers=AGENT,
                         json={"name": "TEST_SUP", "phone": "0944111111"}, timeout=15)
        assert r.status_code in (401, 403, 400, 500), r.text


# ---------- Regression: core role endpoints ----------
class TestRoleRegression:
    @pytest.mark.parametrize("hdr,label", [(OWNER, "owner"), (ACCT, "acct"), (AGENT, "agent")])
    def test_profile_access(self, hdr, label):
        r = requests.get(f"{BASE}/org/profile", headers=hdr, timeout=15)
        assert r.status_code == 200, f"{label}: {r.text}"

    def test_dev_denied_org_profile(self):
        """Developer role is global; must not have org-scoped profile access."""
        r = requests.get(f"{BASE}/org/profile", headers=DEV, timeout=15)
        assert r.status_code in (401, 403), r.text
