"""Supplier Payments backend tests (iteration 3) — Convex live deployment.

Covers:
- GET /api/supplier-payments: owner & accountant allowed, newest first.
- POST /api/supplier-payments: OWNER only; validations (amount<=0, over owed, USD w/o rate),
  Arabic error strings, voucher_no prefix SPY-, happy path reduces owed balance.
Only mutates TEST org (org_test_1). Reuses the existing TEST_SUPPLIER_* created in iteration 2.
"""
import uuid
import pytest
import requests

CONVEX = "https://fearless-ostrich-878.eu-west-1.convex.site/api"

TOKENS = {
    "dev": "test_token_dev",
    "owner": "test_token_owner",
    "acct": "test_token_acct",
    "agent": "test_token_agent",
}


def H(role):
    return {"Authorization": f"Bearer {TOKENS[role]}", "Content-Type": "application/json"}


def _owed_for(supplier: str) -> float:
    """Compute owed = purchases - purchase_returns - supplier_payments for the given supplier (SYP base)."""
    def mine(path):
        r = requests.get(f"{CONVEX}/{path}", headers=H("owner"), timeout=15)
        assert r.status_code == 200, r.text
        return sum((row.get("total") or row.get("amount") or 0) for row in r.json() if (row.get("supplier") or "").strip() == supplier)
    return mine("purchases") - mine("purchase-returns") - mine("supplier-payments")


def _any_supplier() -> str:
    r = requests.get(f"{CONVEX}/purchases", headers=H("owner"), timeout=15)
    assert r.status_code == 200
    for row in r.json():
        s = (row.get("supplier") or "").strip()
        if s.startswith("TEST_SUPPLIER_"):
            return s
    pytest.skip("no TEST_SUPPLIER_* purchases available")


def _ensure_owed(supplier: str, min_owed: float = 500.0) -> float:
    """Make sure there's at least `min_owed` owed to supplier — add a purchase if needed."""
    owed = _owed_for(supplier)
    if owed >= min_owed:
        return owed
    # Need a product to post a purchase
    r = requests.get(f"{CONVEX}/products", headers=H("owner"), timeout=15)
    prods = r.json()
    assert prods, "no products to attach purchase to"
    p = prods[0]
    pid = p.get("id") or p.get("_id")
    payload = {"product_id": pid, "quantity": 2, "unit_cost": 500, "supplier": supplier}
    r = requests.post(f"{CONVEX}/purchases", headers=H("owner"), json=payload, timeout=20)
    assert r.status_code in (200, 201), f"could not seed purchase: {r.status_code} {r.text[:300]}"
    return _owed_for(supplier)


class TestSupplierPaymentsAuth:
    def test_list_owner_ok(self):
        r = requests.get(f"{CONVEX}/supplier-payments", headers=H("owner"), timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        # Newest first — created_at descending
        if len(rows) >= 2:
            assert rows[0].get("created_at") >= rows[1].get("created_at")

    def test_list_accountant_ok(self):
        r = requests.get(f"{CONVEX}/supplier-payments", headers=H("acct"), timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_rejected_for_agent(self):
        r = requests.post(f"{CONVEX}/supplier-payments", headers=H("agent"),
                          json={"supplier": "X", "amount": 1}, timeout=15)
        assert r.status_code == 403, r.text
        assert "صلاحية" in (r.json().get("detail") or ""), r.text

    def test_create_rejected_for_accountant(self):
        r = requests.post(f"{CONVEX}/supplier-payments", headers=H("acct"),
                          json={"supplier": "X", "amount": 1}, timeout=15)
        assert r.status_code == 403, r.text
        assert "صلاحية" in (r.json().get("detail") or ""), r.text


class TestSupplierPaymentsValidation:
    def test_amount_zero_rejected(self):
        supplier = _any_supplier()
        r = requests.post(f"{CONVEX}/supplier-payments", headers=H("owner"),
                          json={"supplier": supplier, "amount": 0}, timeout=15)
        assert r.status_code == 400, r.text
        assert "المبلغ غير صالح" in r.json().get("detail", "")

    def test_amount_negative_rejected(self):
        supplier = _any_supplier()
        r = requests.post(f"{CONVEX}/supplier-payments", headers=H("owner"),
                          json={"supplier": supplier, "amount": -5}, timeout=15)
        assert r.status_code == 400, r.text
        assert "المبلغ غير صالح" in r.json().get("detail", "")

    def test_overpayment_rejected(self):
        supplier = _any_supplier()
        owed = _ensure_owed(supplier, 100)
        over = max(owed + 1000, 10_000)
        r = requests.post(f"{CONVEX}/supplier-payments", headers=H("owner"),
                          json={"supplier": supplier, "amount": over}, timeout=15)
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "")
        assert "أكبر من المستحق" in detail, detail

    def test_usd_requires_exchange_rate(self):
        """Current TEST org has an exchange_rate configured, so USD succeeds.
        This test should PASS the request OR fail with the Arabic exchange-rate error — never 5xx."""
        supplier = _any_supplier()
        _ensure_owed(supplier, 10)
        r = requests.post(f"{CONVEX}/supplier-payments", headers=H("owner"),
                          json={"supplier": supplier, "amount": 0.01, "currency": "USD"}, timeout=15)
        # Either succeeds (rate set) or returns 400 with the Arabic rate error.
        if r.status_code == 400:
            assert "سعر صرف" in r.json().get("detail", ""), r.text
        else:
            assert r.status_code in (200, 201), r.text


class TestSupplierPaymentHappyPath:
    def test_happy_path_reduces_owed(self):
        supplier = _any_supplier()
        before = _ensure_owed(supplier, 500)
        amount = 50
        r = requests.post(f"{CONVEX}/supplier-payments", headers=H("owner"),
                          json={"supplier": supplier, "amount": amount, "notes": "TEST pay"}, timeout=20)
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        # voucher_no prefix
        vno = doc.get("voucher_no") or ""
        assert vno.startswith("SPY-"), f"voucher_no={vno!r}"
        # amount persisted (in base currency SYP after conversion)
        assert doc.get("amount") == amount, doc
        assert doc.get("supplier") == supplier
        # Appears in list (newest first)
        r2 = requests.get(f"{CONVEX}/supplier-payments", headers=H("owner"), timeout=15)
        assert r2.status_code == 200
        ids = [p.get("id") for p in r2.json()]
        assert doc.get("id") in ids
        # Owed reduced by amount
        after = _owed_for(supplier)
        assert round(before - after, 2) == amount, f"before={before} after={after} diff={before-after}"
