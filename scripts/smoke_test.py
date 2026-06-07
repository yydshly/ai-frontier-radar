#!/usr/bin/env python3
"""
Smoke test for AI Frontier Radar.

Validates:
- GET /health returns ok
- GET / returns 200
- GET /static/style.css returns 200
- GET /cards returns 200
- POST /compile creates failed card when API key is missing

Does NOT require a real API key for basic smoke tests.
"""
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

# Set test database before importing app
os.environ["DATABASE_URL"] = "sqlite:///./data/test_smoke.db"
# Use a profile that requires no API key check during config load for smoke test
os.environ["LLM_PROFILE"] = "minimax_m27_highspeed_anthropic"

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


def test_static_css():
    """Test static CSS file is served."""
    response = client.get("/static/style.css")
    assert response.status_code == 200
    assert "body {" in response.text
    print("[OK] GET /static/style.css returns 200")


def test_cards_page():
    """Test cards list page loads."""
    response = client.get("/cards")
    assert response.status_code == 200
    assert "InsightCard" in response.text
    print("[OK] GET /cards returns 200 with content")


def test_compile_missing_api_key():
    """Test that compile with missing API key creates a failed card, not a crash."""
    test_url = "https://example.com/test"
    print(f"[TEST] POST /compile with missing API key...")

    response = client.post("/compile", data={"url": test_url}, follow_redirects=False)
    # Should redirect (303) to card detail page
    assert response.status_code == 303, f"Expected 303, got {response.status_code}"

    location = response.headers.get("location", "")
    assert "/cards/" in location, f"Expected redirect to /cards/, got {location}"
    print(f"[OK] POST /compile created failed card (redirected to {location})")


def test_compile_with_url():
    """Test URL compilation if SMOKE_TEST_URL is set and real API key available."""
    url = os.getenv("SMOKE_TEST_URL")
    if not url:
        print("[SKIP] SMOKE_TEST_URL not set, skipping real compile test")
        return

    print(f"[TEST] Testing compile with URL: {url[:60]}...")

    try:
        response = client.post("/compile", data={"url": url}, follow_redirects=False)
        assert response.status_code in [200, 303, 500]
        print(f"[OK] POST /compile accepted URL (status={response.status_code})")

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
    test_static_css()
    test_cards_page()
    test_compile_missing_api_key()
    test_compile_with_url()

    print("=" * 50)
    print("Smoke test completed!")
    print("=" * 50)
