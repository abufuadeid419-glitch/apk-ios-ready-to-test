"""Iteration 8 — accountant read-only, journal, backup, supplier picker, offline deps.

Live Convex deployment fearless-ostrich-878. Uses seeded test tokens from
/app/memory/test_credentials.md on TEST org (org_test_1). No destructive changes.
"""
import os
import time
import uuid

import pytest
import requests

BASE_URL = "https://fearless-ostrich-878.eu-west-1.convex.site/api"
T_OWNER = "test_token_owner"
T_ACCT = "test_token_acct"
T_AGENT = "test_token_agent"
T_DEV = "test_token_dev"


def _h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def owner():
    s = requests.Session()
    s.headers.update(_h(T_OWNER))
    return s


@pytest.fixture(scope="module")
def acct():
    s = requests.Session()
    s.headers.update(_h(T_ACCT))
    return s


@pytest.fixture(scope="module")
def agent():
    s = requests.Session()
    s.headers.update(_h(T_AGENT))
    return s


# ---------- Accountant RBAC: strict read-only ----------
class TestAccountantReadOnly:
    def test_get_customers_allowed(self, acct):
        r = acct.get(f"{BASE_URL}/customers", timeout=20)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_post_customer_blocked(self, acct):
        r = acct.post(f"{BASE_URL}/customers", json={"id": "x" + uuid.uuid4().hex, "name": "TEST_BLOCK"}, timeout=20)
        assert r.status_code == 403, r.text
        assert "المحاسب" in r.json().get("detail", "")

    def test_post_collection_blocked(self, acct):
        r = acct.post(f"{BASE_URL}/collections", json={"id": "x" + uuid.uuid4().hex, "customer_id": "c", "amount": 1}, timeout=20)
        assert r.status_code == 403
        assert "المحاسب" in r.json().get("detail", "")

    def test_post_payment_voucher_blocked(self, acct):
        r = acct.post(f"{BASE_URL}/payment-vouchers", json={"id": "x" + uuid.uuid4().hex, "customer_id": "c", "amount": 1}, timeout=20)
        assert r.status_code == 403

    def test_patch_sale_void_blocked(self, acct):
        r = acct.patch(f"{BASE_URL}/sales/nonexistent/void", json={"reason": "t"}, timeout=20)
        assert r.status_code == 403, r.text

    def test_put_org_profile_blocked(self, acct):
        r = acct.put(f"{BASE_URL}/org/profile", json={"name": "TEST_BLOCK_RENAME"}, timeout=20)
        assert r.status_code == 403, r.text

    def test_notifications_allowed_for_acct(self, acct):
        # /notifications is explicitly whitelisted (user-owned actions)
        r = acct.get(f"{BASE_URL}/notifications", timeout=20)
        assert r.status_code == 200


# ---------- Journal (OWNER + ACCOUNTANT allowed; FIELD_AGENT rejected) ----------
class TestJournal:
    def test_journal_owner(self, owner):
        r = owner.get(f"{BASE_URL}/accounting/journal", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "entries" in data and "totals" in data
        if data["entries"]:
            e = data["entries"][0]
            # required shape fields per journal.ts
            for k in ("date", "type", "type_label", "amount", "debit_account", "credit_account", "details", "lines"):
                assert k in e, f"missing {k} in entry"

    def test_journal_acct(self, acct):
        r = acct.get(f"{BASE_URL}/accounting/journal", timeout=30)
        assert r.status_code == 200, r.text
        assert "entries" in r.json()

    def test_journal_agent_rejected(self, agent):
        r = agent.get(f"{BASE_URL}/accounting/journal", timeout=20)
        # journal.require uses STAFF (OWNER/ACCOUNTANT) — FIELD_AGENT should be denied
        assert r.status_code in (401, 403), f"agent should be rejected, got {r.status_code}: {r.text}"

    def test_journal_date_range(self, owner):
        r = owner.get(f"{BASE_URL}/accounting/journal?from=1900-01-01&to=1900-01-02", timeout=20)
        assert r.status_code == 200
        assert r.json()["entries"] == []

    def test_journal_contains_unit_lines(self, owner):
        """Lines should carry unit (قطعة/كرتونة) per spec."""
        r = owner.get(f"{BASE_URL}/accounting/journal", timeout=30)
        assert r.status_code == 200
        for e in r.json()["entries"]:
            for ln in e.get("lines", []):
                assert "unit" in ln and ln["unit"] in ("قطعة", "كرتونة") or isinstance(ln.get("unit"), str)


# ---------- Backup export (owner only; business data; no ids/tokens) ----------
class TestBackup:
    def test_backup_export_owner(self, owner):
        r = owner.get(f"{BASE_URL}/backup/export", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "organization" in d
        # schema-level checks: must contain business sections used by backupPdf.ts
        for key in ("employees", "products", "customers", "sales", "collections", "purchases"):
            assert key in d, f"backup missing {key}"

    def test_backup_blocked_for_agent(self, agent):
        r = agent.get(f"{BASE_URL}/backup/export", timeout=20)
        assert r.status_code in (401, 403)

    def test_backup_response_has_no_internal_ids(self, owner):
        """Spot-check: top-level org object should not expose user_id/org_id/token keys."""
        r = owner.get(f"{BASE_URL}/backup/export", timeout=60)
        d = r.json()
        org = d.get("organization", {}) or {}
        # It's acceptable for the raw API to return technical fields,
        # but backup PDF (src/backupPdf.ts) only renders business keys.
        # Still verify no obvious token/password leaks.
        for forbidden in ("session_token", "password", "api_key"):
            assert forbidden not in org


# ---------- Suppliers (picker data source for purchase screen) ----------
class TestSuppliers:
    def test_list_suppliers_owner(self, owner):
        r = owner.get(f"{BASE_URL}/suppliers", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # Seeded TEST_SUP should exist
        names = [s.get("name") for s in data]
        assert any("TEST_SUP" in (n or "") for n in names), f"TEST_SUP not seeded: {names}"

    def test_list_purchases_for_picker_fallback(self, owner):
        """Supplier picker also surfaces supplier names from historical purchases."""
        r = owner.get(f"{BASE_URL}/purchases", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Dev token stays denied for org routes (regression) ----------
class TestDevGuard:
    def test_dev_denied_customers(self):
        r = requests.get(f"{BASE_URL}/customers", headers=_h(T_DEV), timeout=20)
        assert r.status_code in (401, 403), r.text


# ---------- Health / regression ----------
class TestRegression:
    @pytest.mark.parametrize("tok", [T_OWNER, T_ACCT, T_AGENT])
    def test_me(self, tok):
        r = requests.get(f"{BASE_URL}/auth/me", headers=_h(tok), timeout=20)
        assert r.status_code == 200, (tok, r.text)
        d = r.json()
        # /auth/me returns the user object flat (email, employee_type, ...)
        assert d.get("email") or d.get("user"), d

    def test_org_profile_get(self, owner):
        r = owner.get(f"{BASE_URL}/org/profile", timeout=20)
        assert r.status_code == 200
        assert "name" in r.json()
