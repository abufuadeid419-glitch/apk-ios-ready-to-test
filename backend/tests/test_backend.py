"""Backend smoke tests for Convex-migrated app.
Verifies the local FastAPI health stub + Convex live /api/auth/me endpoint.
"""
import os
import pytest
import requests

PREVIEW_URL = "https://error-dis-demo.preview.emergentagent.com"
CONVEX_SITE = "https://fearless-ostrich-878.eu-west-1.convex.site"


# ---------- Preview FastAPI stub ----------
class TestPreviewHealth:
    def test_preview_health_ok(self):
        r = requests.get(f"{PREVIEW_URL}/api/health", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True

    def test_preview_root(self):
        r = requests.get(f"{PREVIEW_URL}/api/", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("backend") == "convex"
        assert data.get("mongodb") is False


# ---------- Convex live backend ----------
class TestConvexAuth:
    def test_auth_me_unauthenticated_returns_401(self):
        r = requests.get(f"{CONVEX_SITE}/api/auth/me", timeout=20)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:300]}"

    def test_auth_me_with_bogus_token_returns_401(self):
        r = requests.get(
            f"{CONVEX_SITE}/api/auth/me",
            headers={"Authorization": "Bearer not-a-real-token"},
            timeout=20,
        )
        assert r.status_code == 401
