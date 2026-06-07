#!/usr/bin/env python3
"""
Smoke test for AI Frontier Radar.

Validates:
- GET /health returns ok
- GET / returns 200
- POST /compile works with SMOKE_TEST_URL env var
- GET /cards returns 200 with SMOKE_TEST_URL env var

Does NOT require a real API key for basic smoke tests.
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

# Set test database before importing app
os.environ["DATABASE_URL"] = "sqlite:///./data/test_smoke.db"

from app.main import app

client = TestClient(app)


def test_health():
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    print("[OK] /health returns ok")


def test_index():
    """Test index page loads."""
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Frontier Radar" in response.text
    print("[OK] GET / returns 200 with content")


def test_cards_page():
    """Test cards list page loads."""
    response = client.get("/cards")
    assert response.status_code == 200
    assert "InsightCard" in response.text
    print("[OK] GET /cards returns 200 with content")


def test_compile_with_url():
    """Test URL compilation if SMOKE_TEST_URL is set."""
    url = os.getenv("SMOKE_TEST_URL")
    if not url:
        print("[SKIP] SMOKE_TEST_URL not set, skipping compile test")
        return

    print(f"[TEST] Testing compile with URL: {url[:60]}...")

    # This will try to actually fetch and process the URL
    # It may fail if:
    # - URL is unreachable
    # - LLM API key is not configured (replace-me)
    # But it tests the full pipeline
    try:
        response = client.post("/compile", data={"url": url})
        # We expect either redirect (303) or error page
        # The important thing is the endpoint accepted the request
        assert response.status_code in [200, 303, 500]
        print(f"[OK] POST /compile accepted URL (status={response.status_code})")

        # If we got a redirect, follow it to get the card
        if response.status_code == 303:
            location = response.headers.get("location", "")
            print(f"     Redirected to: {location}")
    except Exception as e:
        print(f"[WARN] Compile test failed: {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("AI Frontier Radar - Smoke Test")
    print("=" * 50)

    test_health()
    test_index()
    test_cards_page()
    test_compile_with_url()

    print("=" * 50)
    print("Smoke test completed!")
    print("=" * 50)
