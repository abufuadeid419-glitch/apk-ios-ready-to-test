"""Iteration 4 — RBAC (dev cannot delete), licenses, pricing method (FIFO/WAVG),
deliveries with units, distributor REST endpoints (notifications/targets).
Mutates only TEST org (org_test_1)."""
import os
import uuid
import pytest
import requests

PREVIEW_URL = "https://error-dis-demo.preview.emergentagent.com"
CONVEX = "https://fearless-ostrich-878.eu-west-1.convex.site/api"

TOKENS = {
    "dev": "test_token_dev",
    "owner": "test_token_owner",
    "acct": "test_token_acct",
    "agent": "test_token_agent",
}


def H(role):
    return {"Authorization": f"Bearer {TOKENS[role]}", "Content-Type": "application/json"}


# ---------- Preview health ----------
class TestPreviewHealth:
    def test_preview_health_ok(self):
        r = requests.get(f"{PREVIEW_URL}/api/health", timeout=15)
        assert r.status_code == 200


# ---------- (7) Dev licenses create ----------
class TestDevLicenses:
    created: list[str] = []

    def test_dev_list_licenses(self):
        r = requests.get(f"{CONVEX}/dev/licenses", headers=H("dev"), timeout=15)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_dev_create_license(self):
        payload = {"org_name": f"TEST_LIC_{uuid.uuid4().hex[:6]}", "days": 30, "max_employees": 5}
        r = requests.post(f"{CONVEX}/dev/licenses", headers=H("dev"), json=payload, timeout=20)
        assert r.status_code in (200, 201), f"status={r.status_code} body={r.text[:400]}"
        data = r.json()
        assert data.get("org_name") == payload["org_name"], data
        assert data.get("status") == "READY", data
        assert str(data.get("code", "")).startswith("LIC-"), data
        TestDevLicenses.created.append(data.get("id"))

        # Verify via GET
        lst = requests.get(f"{CONVEX}/dev/licenses", headers=H("dev"), timeout=15).json()
        assert any(x.get("id") == data.get("id") for x in lst)

    def test_non_dev_cannot_create_license(self):
        r = requests.post(f"{CONVEX}/dev/licenses", headers=H("owner"),
                          json={"org_name": "X", "days": 1, "max_employees": 1}, timeout=15)
        assert r.status_code in (400, 401, 403), r.text[:200]

    @classmethod
    def teardown_class(cls):
        for lid in cls.created:
            try:
                requests.delete(f"{CONVEX}/dev/licenses/{lid}", headers=H("dev"), timeout=15)
            except Exception:
                pass


# ---------- (6) RBAC: Developer cannot delete accounts ----------
class TestRbacDeletion:
    def test_dev_delete_account_blocked(self):
        r = requests.delete(f"{CONVEX}/auth/account", headers=H("dev"), timeout=15)
        # Convex throws → maps to non-2xx
        assert r.status_code in (400, 401, 403), f"status={r.status_code} body={r.text[:400]}"
        assert "المطور" in r.text or "صلاحية" in r.text, r.text[:400]

    def test_dev_approve_deletion_blocked(self):
        # Use any bogus id — handler checks role before loading
        r = requests.patch(f"{CONVEX}/dev/deletion-requests/does-not-matter",
                           headers=H("dev"), json={"action": "approve"}, timeout=15)
        assert r.status_code in (400, 401, 403), r.text[:400]
        # Arabic error for approve path
        assert "حذف" in r.text or "متاح" in r.text, r.text[:400]

    def test_dev_reject_deletion_allowed_but_not_found(self):
        r = requests.patch(f"{CONVEX}/dev/deletion-requests/not-real",
                           headers=H("dev"), json={"action": "reject"}, timeout=15)
        # action=reject passes role check, hits "الطلب غير موجود"
        assert r.status_code in (400, 401, 404), r.text[:400]
        assert "الطلب" in r.text or "غير موجود" in r.text, r.text[:400]


# ---------- (3) Pricing method FIFO/WAVG ----------
class TestPricingMethod:
    product_id: str | None = None

    def test_invalid_method_rejected(self):
        r = requests.put(f"{CONVEX}/org/pricing-method", headers=H("owner"),
                         json={"method": "BOGUS"}, timeout=15)
        assert r.status_code in (400, 422), r.text[:300]

    def test_non_owner_cannot_change(self):
        r = requests.put(f"{CONVEX}/org/pricing-method", headers=H("agent"),
                         json={"method": "WAVG"}, timeout=15)
        assert r.status_code in (400, 401, 403), r.text[:300]

    def _ensure_product(self):
        prods = requests.get(f"{CONVEX}/products", headers=H("owner"), timeout=15).json()
        # Create a dedicated iteration-4 test product with stock & cost_price
        name = f"TEST_PRICING_{uuid.uuid4().hex[:6]}"
        payload = {
            "name": name, "category": "test", "unit": "قطعة",
            "sale_price": 1000, "cost_price": 500, "stock": 20,
            "min_stock": 1, "price_currency": "SYP",
            "pieces_per_package": 10, "package_unit": "كرتونة",
        }
        r = requests.post(f"{CONVEX}/products", headers=H("owner"), json=payload, timeout=20)
        assert r.status_code in (200, 201), r.text[:300]
        pid = r.json().get("id") or r.json().get("_id")
        TestPricingMethod.product_id = pid
        return pid

    def test_fifo_creates_cost_layers(self):
        # Switch to FIFO
        r = requests.put(f"{CONVEX}/org/pricing-method", headers=H("owner"),
                         json={"method": "FIFO"}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("pricing_method") == "FIFO"
        pid = self._ensure_product()
        # Buy at different unit_cost (700 piece) — must add a new layer, keep oldest cost/sale
        r = requests.post(f"{CONVEX}/purchases", headers=H("owner"),
                          json={"product_id": pid, "quantity": 5, "unit_cost": 700, "unit": "piece"},
                          timeout=20)
        assert r.status_code in (200, 201), r.text[:300]

        # Verify product has >=2 cost_layers and cost_price stayed at oldest (500)
        prods = requests.get(f"{CONVEX}/products", headers=H("owner"), timeout=15).json()
        p = next(x for x in prods if (x.get("id") == pid or x.get("_id") == pid))
        layers = p.get("cost_layers") or []
        assert len(layers) >= 2, f"expected ≥2 FIFO layers, got {layers}"
        assert float(p.get("cost_price")) == 500.0, p

    def test_fifo_return_consumes_oldest(self):
        pid = TestPricingMethod.product_id
        assert pid, "need product"
        prods = requests.get(f"{CONVEX}/products", headers=H("owner"), timeout=15).json()
        before = next(x for x in prods if (x.get("id") == pid or x.get("_id") == pid))
        oldest_qty = (before.get("cost_layers") or [{}])[0].get("qty", 0)

        # Purchase-return 1 piece — should consume oldest layer
        r = requests.post(f"{CONVEX}/purchase-returns", headers=H("owner"),
                          json={"product_id": pid, "quantity": 1, "unit_cost": 500,
                                "unit": "piece", "reason": "TEST"}, timeout=20)
        assert r.status_code in (200, 201), r.text[:300]
        prods = requests.get(f"{CONVEX}/products", headers=H("owner"), timeout=15).json()
        after = next(x for x in prods if (x.get("id") == pid or x.get("_id") == pid))
        after_oldest = (after.get("cost_layers") or [{}])[0].get("qty", 0)
        # Oldest layer qty decreased by 1 (or layer removed/replaced) OR a FIFO consume occurred
        # Weak check: either qty decreased, or layer count decreased (if ran out)
        assert after_oldest < oldest_qty or len(after.get("cost_layers") or []) < len(before.get("cost_layers") or []), \
            f"FIFO return didn't consume oldest: before={before.get('cost_layers')} after={after.get('cost_layers')}"

    def test_wavg_switch_updates_cost(self):
        r = requests.put(f"{CONVEX}/org/pricing-method", headers=H("owner"),
                         json={"method": "WAVG"}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        pid = TestPricingMethod.product_id
        assert pid
        prods = requests.get(f"{CONVEX}/products", headers=H("owner"), timeout=15).json()
        before = next(x for x in prods if (x.get("id") == pid or x.get("_id") == pid))
        before_cost = float(before.get("cost_price"))

        # Purchase at new cost 800 — WAVG should blend into cost_price
        r = requests.post(f"{CONVEX}/purchases", headers=H("owner"),
                          json={"product_id": pid, "quantity": 5, "unit_cost": 800, "unit": "piece"},
                          timeout=20)
        assert r.status_code in (200, 201), r.text[:300]
        prods = requests.get(f"{CONVEX}/products", headers=H("owner"), timeout=15).json()
        after = next(x for x in prods if (x.get("id") == pid or x.get("_id") == pid))
        after_cost = float(after.get("cost_price"))
        # Under WAVG, cost should move toward 800 (blended)
        assert after_cost != before_cost, f"WAVG didn't update cost_price: before={before_cost} after={after_cost}"
        # Cost_layers should be cleared under WAVG
        assert not (after.get("cost_layers") or []), f"WAVG left cost_layers: {after.get('cost_layers')}"


# ---------- (4) Deliveries with unit=PACKAGE deducts pieces_per_package ----------
class TestDeliveriesUnits:
    def test_delivery_package_deducts_pieces(self):
        # Use the specified product
        pid_target = "504c618ff474444793b7f4ac7ba26bc1"
        prods = requests.get(f"{CONVEX}/products", headers=H("owner"), timeout=15).json()
        prod = next((x for x in prods if (x.get("id") == pid_target or x.get("_id") == pid_target)), None)
        if not prod:
            # Fallback: pick any product with pieces_per_package=10
            prod = next((x for x in prods if int(x.get("pieces_per_package", 1)) == 10 and (x.get("stock") or 0) >= 10), None)
            if not prod:
                pytest.skip("no suitable product with pieces_per_package=10 and stock≥10")
        pid = prod.get("id") or prod.get("_id")
        ppp = int(prod.get("pieces_per_package", 10))

        # Find the agent (distributor) user id
        r = requests.get(f"{CONVEX}/auth/me", headers=H("agent"), timeout=15)
        assert r.status_code == 200, r.text
        dist_id = r.json().get("user_id")
        assert dist_id

        stock_before = float(prod.get("stock") or 0)

        payload = {
            "distributor_id": dist_id,
            "items": [{"product_id": pid, "quantity": 1, "unit": "PACKAGE"}],
            "notes": "TEST pkg unit",
        }
        r = requests.post(f"{CONVEX}/deliveries", headers=H("owner"), json=payload, timeout=20)
        assert r.status_code in (200, 201), f"status={r.status_code} body={r.text[:400]}"
        d = r.json()
        delivery_id = d.get("id")
        assert delivery_id

        # Owner-side stock should drop by ppp
        prods2 = requests.get(f"{CONVEX}/products", headers=H("owner"), timeout=15).json()
        prod2 = next(x for x in prods2 if (x.get("id") == pid or x.get("_id") == pid))
        stock_after = float(prod2.get("stock") or 0)
        assert abs((stock_before - stock_after) - ppp) < 0.01, \
            f"expected stock -{ppp}, got before={stock_before} after={stock_after}"

        # Agent confirms delivery → adds pieces to distributor inventory
        inv_before = requests.get(f"{CONVEX}/my/inventory", headers=H("agent"), timeout=15).json()
        qty_before = next((float(i.get("quantity") or 0) for i in inv_before if i.get("product_id") == pid), 0.0)

        r = requests.post(f"{CONVEX}/deliveries/{delivery_id}/confirm", headers=H("agent"), timeout=20)
        assert r.status_code in (200, 201), r.text[:400]

        inv_after = requests.get(f"{CONVEX}/my/inventory", headers=H("agent"), timeout=15).json()
        qty_after = next((float(i.get("quantity") or 0) for i in inv_after if i.get("product_id") == pid), 0.0)
        assert abs((qty_after - qty_before) - ppp) < 0.01, \
            f"expected dist inv +{ppp}, got before={qty_before} after={qty_after}"


# ---------- (1) Distributor REST endpoints: notifications + targets ----------
class TestDistributorRest:
    def test_notifications_agent(self):
        r = requests.get(f"{CONVEX}/notifications", headers=H("agent"), timeout=15)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # Expect {items/notifications, unread}
        assert isinstance(data, dict) or isinstance(data, list), data

    def test_targets_agent(self):
        r = requests.get(f"{CONVEX}/targets", headers=H("agent"), timeout=15)
        assert r.status_code == 200, r.text[:300]

    def test_invalid_token_401(self):
        r = requests.get(f"{CONVEX}/auth/me",
                         headers={"Authorization": "Bearer invalid_xxx"}, timeout=15)
        assert r.status_code == 401


# ---------- Regression: all 4 roles still identify ----------
class TestRoleIdentity:
    @pytest.mark.parametrize("role,expected", [
        ("owner", "OWNER"), ("acct", "EMPLOYEE"), ("agent", "EMPLOYEE"), ("dev", "DEVELOPER"),
    ])
    def test_me(self, role, expected):
        r = requests.get(f"{CONVEX}/auth/me", headers=H(role), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("role") == expected
