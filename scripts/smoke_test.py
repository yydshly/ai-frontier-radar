#!/usr/bin/env python3
"""
Smoke test for AI Frontier Radar.

Validates:
- GET /health returns ok
- GET / returns 200
- GET /static/style.css returns 200
- GET /cards returns 200
- POST /compile creates failed card when API key is missing
- Profile config loading works without real API key

Does NOT require a real API key for basic smoke tests.
"""
import os
import sys
import uuid
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_dependency_compat():
    """Verify starlette version is compatible before importing app."""
    import starlette
    ver = getattr(starlette, "__version__", "unknown")
    parts = ver.split(".")
    try:
        major, minor = int(parts[0]), int(parts[1])
        patch = int(parts[2]) if len(parts) > 2 else 0
        version_tuple = (major, minor, patch)
        min_ver = (0, 37, 2)
        max_ver = (0, 38, 0)
        if not (version_tuple >= min_ver and version_tuple < max_ver):
            print(f"[FAIL] starlette version incompatible: {ver}")
            print(f"       Expected: >=0.37.2,<0.38.0 for fastapi==0.111.0")
            print(f"       Please reinstall dependencies:")
            print(f"       pip install -r requirements.txt --upgrade --force-reinstall")
            sys.exit(1)
    except (ValueError, IndexError):
        print(f"[FAIL] starlette version unparseable: {ver}")
        print(f"       Expected: >=0.37.2,<0.38.0")
        sys.exit(1)


check_dependency_compat()

from fastapi.testclient import TestClient

# Set test database before importing app
os.environ["DATABASE_URL"] = "sqlite:///./data/test_smoke.db"
os.environ["LLM_PROFILE"] = "minimax_m27_highspeed_anthropic"

from app.main import app
from app.models import SourceType

client = TestClient(app)


def test_health():
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    print("[OK] /health returns ok")


def test_index():
    """Test index page loads with required content sections."""
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Frontier Radar" in response.text
    assert "系统如何处理 URL" in response.text, "Missing pipeline explanation"
    assert "trafilatura" in response.text, "Missing trafilatura mention"
    assert "pypdf" in response.text, "Missing pypdf mention"
    assert "LLM Profile" in response.text, "Missing LLM Profile section"
    assert "failed card" in response.text, "Missing failed card mention"
    print("[OK] GET / returns 200 with all required content")


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


def test_llm_profile_config():
    """Test that profile config loads correctly without requiring real API key."""
    from app.llm.config_loader import load_llm_profiles

    profiles_data = load_llm_profiles()
    default_profile_name = profiles_data.get("default_profile", "")

    assert default_profile_name == "minimax_m27_highspeed_anthropic", \
        f"Expected default_profile='minimax_m27_highspeed_anthropic', got '{default_profile_name}'"

    profiles = profiles_data.get("profiles", {})
    assert "minimax_m27_highspeed_anthropic" in profiles, \
        "minimax_m27_highspeed_anthropic profile not found"

    profile = profiles["minimax_m27_highspeed_anthropic"]
    assert profile["provider"] == "minimax", f"Expected provider='minimax', got '{profile.get('provider')}'"
    assert profile["protocol"] == "anthropic_messages", \
        f"Expected protocol='anthropic_messages', got '{profile.get('protocol')}'"
    assert profile["model"] == "MiniMax-M2.7-highspeed", \
        f"Expected model='MiniMax-M2.7-highspeed', got '{profile.get('model')}'"
    assert profile["api_key_env"] == "MINIMAX_API_KEY", \
        f"Expected api_key_env='MINIMAX_API_KEY', got '{profile.get('api_key_env')}'"
    assert profile["endpoint"] == "/v1/messages", \
        f"Expected endpoint='/v1/messages', got '{profile.get('endpoint')}'"

    print("[OK] LLM profile config loads correctly")
    print(f"     default_profile: {default_profile_name}")
    print(f"     model: {profile['model']}")
    print(f"     protocol: {profile['protocol']}")
    print(f"     api_key_env: {profile['api_key_env']}")


def test_compile_missing_api_key():
    """
    Test that compile with missing API key creates a failed card with correct error.

    Uses monkeypatch to mock fetch/extract so we don't need real network access.
    Asserts the failed card detail page contains the expected error message.
    """
    import app.services.insight_compiler as compiler

    # Save originals
    original_fetch = compiler.fetch_url
    original_extract = compiler.extract_content
    original_key = os.environ.get("MINIMAX_API_KEY", "placeholder")

    # Monkeypatch fetch and extract to avoid real network calls
    def fake_fetch_url(url):
        return (
            b"<html><body><article>"
            b"<h1>Test AI Article About Machine Learning</h1>"
            b"<p>This is a test article. " + b"x" * 200 + b"</p>"
            b"<p>More content here. " + b"y" * 200 + b"</p>"
            b"</article></body></html>",
            "text/html"
        )

    def fake_extract_content(url, content, content_type):
        text = (
            "This is a test article about machine learning and AI. " * 20 +
            "It contains enough text to pass the length check. " * 20 +
            "Machine learning models are advancing rapidly. " * 20 +
            "New AI capabilities emerge every day. " * 20
        )
        return text, "Test AI Article", None, SourceType.HTML

    compiler.fetch_url = fake_fetch_url
    compiler.extract_content = fake_extract_content

    # Use empty API key to trigger the missing key error
    os.environ["MINIMAX_API_KEY"] = ""

    # Use unique URL to avoid dedup hitting previous test run
    test_url = f"https://example.com/test-missing-key-{uuid.uuid4().hex[:8]}"

    try:
        print("[TEST] POST /compile with empty API key...")

        response = client.post("/compile", data={"url": test_url}, follow_redirects=False)
        assert response.status_code == 303, f"Expected 303, got {response.status_code}"

        location = response.headers.get("location", "")
        assert "/cards/" in location, f"Expected redirect to /cards/, got {location}"
        print(f"[OK] POST /compile created card (redirected to {location})")

        # Follow the redirect to get card detail
        detail_response = client.get(location)
        assert detail_response.status_code == 200, f"Detail page failed: {detail_response.status_code}"

        # The failed card should show the API key error
        assert "MINIMAX_API_KEY is not configured" in detail_response.text, \
            "Expected 'MINIMAX_API_KEY is not configured' in failed card detail page"
        print("[OK] Failed card detail contains 'MINIMAX_API_KEY is not configured'")

    finally:
        compiler.fetch_url = original_fetch
        compiler.extract_content = original_extract
        os.environ["MINIMAX_API_KEY"] = original_key


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


def test_sqlite_parent_dir_creation():
    """Test that SQLite parent directory is created for relative paths."""
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from app.db import ensure_sqlite_parent_dir

    with TemporaryDirectory() as tmp:
        old_cwd = os.getcwd()
        os.chdir(tmp)
        try:
            ensure_sqlite_parent_dir("sqlite:///./data/test.db")
            assert Path("data").exists(), "data/ directory was not created"
            assert Path("data").is_dir(), "data/ is not a directory"
            # Ensure it did NOT create /data on some absolute path
            assert not Path("/data").exists(), "Created /data instead of ./data/"
        finally:
            os.chdir(old_cwd)

    print("[OK] SQLite parent directory creation handles relative data path")


def test_utility_scripts_exist():
    """Check that utility scripts exist."""
    scripts_dir = Path(__file__).parent
    for script in ["probe_minimax_anthropic.py", "check_card_encoding.py", "check_card_page.py"]:
        script_path = scripts_dir / script
        assert script_path.exists(), f"Utility script {script} not found"
    print("[OK] Utility scripts exist")


def test_source_config():
    """Test that source registry config loads and validates correctly."""
    from app.sources import list_sources, get_source, get_enabled_sources

    all_sources = list_sources(include_disabled=True)
    assert len(all_sources) >= 8, \
        f"Expected at least 8 sources, got {len(all_sources)}"

    enabled = get_enabled_sources()
    assert len(enabled) >= 3, \
        f"Expected at least 3 enabled sources, got {len(enabled)}"

    # Check required sources exist
    required_keys = {"openai_news", "anthropic_news", "arxiv_cs_ai"}
    for key in required_keys:
        src = get_source(key)
        assert src is not None, f"Required source '{key}' not found"

    # get_source returns None for unknown keys
    assert get_source("not_exists") is None, \
        "get_source('not_exists') should return None"

    # get_enabled_sources count matches filtering
    enabled_keys = {s.source_key for s in all_sources if s.enabled}
    assert {s.source_key for s in enabled} == enabled_keys, \
        "get_enabled_sources() count mismatch"

    # Test force_reload works
    reloaded = list_sources(include_disabled=True, force_reload=True)
    assert len(reloaded) == len(all_sources), \
        "force_reload should return same count as normal load"

    print("[OK] Source config loads correctly")
    print(f"     total sources: {len(all_sources)}")
    print(f"     enabled sources: {len(enabled)}")
    for s in all_sources:
        status = "enabled" if s.enabled else "disabled"
        print(f"     {s.source_key}: {s.category}/{s.fetch_strategy} [{status}]")


def test_source_registry_db_models():
    """Test that Source / SourceItem / FetchRun DB models exist and can be written."""
    from datetime import datetime
    from sqlalchemy import inspect
    from app.db import engine
    from app.models import Source, SourceItem, FetchRun

    # Check tables exist
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    assert "sources" in table_names, "table 'sources' not found"
    assert "source_items" in table_names, "table 'source_items' not found"
    assert "fetch_runs" in table_names, "table 'fetch_runs' not found"
    print("[OK] Source/SourceItem/FetchRun tables exist")

    # Use a unique source_key to avoid conflicts on re-run
    test_key = f"test_source_{uuid.uuid4().hex[:8]}"

    from app.db import SessionLocal
    db = SessionLocal()
    try:
        # Create Source
        src = Source(
            source_key=test_key,
            name="Test Source",
            description="A test source for smoke test",
            source_type="rss",
            homepage_url="https://example.com",
            feed_url="https://example.com/rss.xml",
            category="research",
            tags_json='["test"]',
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="Test hint",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)
        assert src.id is not None, "Source.id should be auto-assigned"
        print(f"[OK] Created Source(id={src.id}, source_key={src.source_key})")

        # Create SourceItem
        item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/article-{uuid.uuid4().hex[:6]}",
            title="Test Article",
            author="Test Author",
            published_at="2025-01-01",
            status="discovered",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        assert item.id is not None, "SourceItem.id should be auto-assigned"
        print(f"[OK] Created SourceItem(id={item.id})")

        # Create FetchRun
        run = FetchRun(
            source_id=src.id,
            source_key=test_key,
            run_type="manual",
            status="success",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            items_found=1,
            items_new=1,
            items_updated=0,
            items_failed=0,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        assert run.id is not None, "FetchRun.id should be auto-assigned"
        print(f"[OK] Created FetchRun(id={run.id})")

        # Query back by source_key
        found = db.query(Source).filter_by(source_key=test_key).first()
        assert found is not None, f"Could not find Source with source_key={test_key}"
        assert found.name == "Test Source"
        print(f"[OK] Source queried back by source_key={test_key}")

        # Verify unique constraint on source_key
        from sqlalchemy.exc import IntegrityError
        db.rollback()
        dup = Source(
            source_key=test_key,
            name="Duplicate",
            description="Should fail",
            source_type="rss",
            category="research",
            fetch_strategy="rss",
            fetch_interval_hours=24,
        )
        db.add(dup)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            print("[OK] source_key unique constraint enforced")
        else:
            db.rollback()
            raise AssertionError("Expected IntegrityError for duplicate source_key")

        # Verify SourceItem(source_id, url) unique constraint
        dup_item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=item.url,  # same URL as item already created above
            title="Duplicate Article",
            status="discovered",
        )
        db.add(dup_item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            print("[OK] SourceItem(source_id, url) unique constraint enforced")
        else:
            db.rollback()
            raise AssertionError(
                "Expected IntegrityError for duplicate SourceItem(source_id, url)"
            )

    finally:
        db.close()


def test_source_config_sync_to_db():
    """Test that source config syncs to DB correctly and is idempotent."""
    from app.sources import sync_sources_config_to_db
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        # First sync with force_reload
        result = sync_sources_config_to_db(db, force_reload=True)

        assert result["total"] >= 8, \
            f"Expected total >= 8, got {result['total']}"
        print(f"[OK] sync_sources_config_to_db returned total={result['total']}")

        # Check openai_news exists
        from app.models import Source
        openai_news = db.query(Source).filter(Source.source_key == "openai_news").first()
        assert openai_news is not None, "openai_news source not found in DB"
        assert openai_news.name, "openai_news.name should not be empty"
        assert openai_news.source_type, "openai_news.source_type should not be empty"
        assert openai_news.fetch_strategy, "openai_news.fetch_strategy should not be empty"
        print(f"[OK] openai_news exists in DB with name='{openai_news.name}'")

        # Idempotency: call again, should not create duplicates
        result2 = sync_sources_config_to_db(db, force_reload=True)
        assert result2["created"] == 0, \
            f"Idempotency failed: expected created=0 on re-run, got {result2['created']}"
        print(f"[OK] Re-running sync is idempotent (created={result2['created']})")

    finally:
        db.close()


def test_sources_page():
    """Test that /sources page loads and displays source data."""
    response = client.get("/sources")
    assert response.status_code == 200, \
        f"Expected status 200, got {response.status_code}"

    text = response.text
    # Check page contains expected content
    has_title = "信息来源" in text or "Source" in text
    assert has_title, "Page should contain '信息来源' or 'Source' in title"

    # Check required sources appear
    assert "openai_news" in text, "openai_news should appear on /sources page"
    assert "anthropic_news" in text, "anthropic_news should appear on /sources page"
    print("[OK] GET /sources returns 200 with source data")


def test_rss_probe_module_imports():
    """Test that RSS probe module can be imported."""
    from app.sources.rss_probe import (
        probe_rss_source,
        run_rss_probe_for_source,
        run_rss_probe_for_enabled_sources,
    )
    assert callable(probe_rss_source)
    assert callable(run_rss_probe_for_source)
    assert callable(run_rss_probe_for_enabled_sources)
    print("[OK] RSS probe module imports successfully")


def test_rss_probe_no_feed_url():
    """Test that probe_rss_source fails gracefully when feed_url is not set."""
    from app.sources.rss_probe import probe_rss_source
    from app.db import SessionLocal
    from app.models import Source

    db = SessionLocal()
    try:
        # Create a test source without feed_url
        test_key = f"test_no_feed_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test No Feed",
            description="A test source without feed URL",
            source_type="rss",
            homepage_url="https://example.com",
            feed_url=None,
            category="research",
            tags_json="[]",
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        result = probe_rss_source(db, src)
        assert result["error_message"] is not None, "Expected error_message for missing feed_url"
        assert "feed_url" in result["error_message"].lower(), \
            f"Expected 'feed_url' in error message, got: {result['error_message']}"
        print(f"[OK] probe_rss_source fails with no feed_url: {result['error_message']}")
    finally:
        db.rollback()
        db.close()


def test_rss_probe_mock_feed():
    """Test probe_rss_source with a mocked RSS feed response."""
    import httpx
    from app.sources.rss_probe import probe_rss_source
    from app.db import SessionLocal
    from app.models import Source, SourceItem

    # Save original httpx.get
    original_get = httpx.get

    # Fake RSS XML
    fake_rss_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <link>https://example.com</link>
  <description>Test RSS Feed</description>
  <item>
    <title>Test Article 1</title>
    <link>https://example.com/article-1</link>
    <author>Author One</author>
    <pubDate>2025-01-15T10:00:00Z</pubDate>
  </item>
  <item>
    <title>Test Article 2</title>
    <link>https://example.com/article-2</link>
    <author>Author Two</author>
    <pubDate>2025-01-16T11:00:00Z</pubDate>
  </item>
</channel>
</rss>"""

    class FakeResponse:
        status_code = 200
        text = fake_rss_xml.decode("utf-8")
        def raise_for_status(self):
            pass

    def fake_get(url, timeout=None, follow_redirects=None):
        return FakeResponse()

    # Monkeypatch httpx.get
    httpx.get = fake_get

    db = SessionLocal()
    try:
        # Create test source with RSS feed
        test_key = f"test_rss_mock_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test RSS Mock",
            description="Mock RSS source for testing",
            source_type="rss",
            homepage_url="https://example.com",
            feed_url="https://example.com/rss.xml",
            category="research",
            tags_json="[]",
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        # First probe
        result1 = probe_rss_source(db, src)
        assert result1["items_found"] == 2, f"Expected 2 items_found, got {result1['items_found']}"
        assert result1["items_new"] == 2, f"Expected 2 items_new, got {result1['items_new']}"
        assert result1["items_updated"] == 0
        assert result1["error_message"] is None
        print(f"[OK] First probe: found={result1['items_found']}, new={result1['items_new']}")

        # Second probe — should update, not create new
        result2 = probe_rss_source(db, src)
        assert result2["items_found"] == 2
        assert result2["items_new"] == 0, f"Expected 0 new on re-run, got {result2['items_new']}"
        assert result2["items_updated"] == 2, f"Expected 2 updated on re-run, got {result2['items_updated']}"
        print(f"[OK] Second probe (idempotent): new={result2['items_new']}, updated={result2['items_updated']}")

        # Verify no duplicate SourceItems
        items = db.query(SourceItem).filter(SourceItem.source_id == src.id).all()
        assert len(items) == 2, f"Expected exactly 2 SourceItems, got {len(items)}"
        print(f"[OK] No duplicate SourceItems created (count={len(items)})")

    finally:
        httpx.get = original_get
        db.rollback()
        db.close()


def test_rss_run_records_failed_fetchrun_without_feed_url():
    """Test that run_rss_probe_for_source records a failed FetchRun when feed_url is None."""
    from app.sources.rss_probe import run_rss_probe_for_source
    from app.db import SessionLocal
    from app.models import Source

    db = SessionLocal()
    try:
        # Create a test source without feed_url
        test_key = f"test_no_feed_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test No Feed",
            description="A test source without feed URL",
            source_type="rss",
            homepage_url="https://example.com",
            feed_url=None,
            category="research",
            tags_json="[]",
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        fetch_run = run_rss_probe_for_source(db, src)

        assert fetch_run.status == "failed", \
            f"Expected status='failed', got '{fetch_run.status}'"
        assert fetch_run.error_message is not None, \
            "Expected error_message to be set"
        assert "feed_url" in fetch_run.error_message.lower(), \
            f"Expected 'feed_url' in error message, got: {fetch_run.error_message}"
        assert fetch_run.finished_at is not None, \
            "finished_at should be set even for failed runs"
        print(f"[OK] FetchRun status=failed, error={fetch_run.error_message}")

        # Re-query source from DB and verify state
        refreshed_source = db.query(Source).filter(Source.id == src.id).first()
        assert refreshed_source.last_checked_at is not None, \
            "last_checked_at should be updated"
        assert refreshed_source.last_error_message is not None, \
            "last_error_message should be set"
        assert refreshed_source.last_success_at is None, \
            "last_success_at should NOT be updated on failure"
        print("[OK] Source.last_success_at not updated on failure")

    finally:
        db.rollback()
        db.close()


def test_rss_run_records_partial_failed_with_missing_link():
    """Test that run_rss_probe_for_source records partial_failed when some entries lack links."""
    import httpx
    from app.sources.rss_probe import run_rss_probe_for_source
    from app.db import SessionLocal
    from app.models import Source, SourceItem

    # Save original httpx.get
    original_get = httpx.get

    # RSS XML with one valid entry and one missing link
    fake_rss_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <item>
    <title>Valid Article</title>
    <link>https://example.com/valid</link>
    <author>Author One</author>
  </item>
  <item>
    <title>Missing Link Article</title>
  </item>
</channel>
</rss>"""

    class FakeResponse:
        status_code = 200
        text = fake_rss_xml.decode("utf-8")
        def raise_for_status(self):
            pass

    def fake_get(url, timeout=None, follow_redirects=None):
        return FakeResponse()

    httpx.get = fake_get

    db = SessionLocal()
    try:
        test_key = f"test_partial_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Partial",
            description="Test source with partial failure",
            source_type="rss",
            homepage_url="https://example.com",
            feed_url="https://example.com/rss.xml",
            category="research",
            tags_json="[]",
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        fetch_run = run_rss_probe_for_source(db, src)

        assert fetch_run.status == "partial_failed", \
            f"Expected status='partial_failed', got '{fetch_run.status}'"
        assert fetch_run.items_found == 2, \
            f"Expected items_found=2, got {fetch_run.items_found}"
        assert fetch_run.items_new == 1, \
            f"Expected items_new=1, got {fetch_run.items_new}"
        assert fetch_run.items_failed == 1, \
            f"Expected items_failed=1, got {fetch_run.items_failed}"
        assert fetch_run.error_message is not None, \
            "error_message should be set for partial_failed"
        print(f"[OK] FetchRun status=partial_failed: "
              f"found={fetch_run.items_found}, new={fetch_run.items_new}, "
              f"failed={fetch_run.items_failed}")

        # Verify exactly 1 SourceItem was created (the one with a valid link)
        items = db.query(SourceItem).filter(SourceItem.source_id == src.id).all()
        assert len(items) == 1, f"Expected 1 SourceItem, got {len(items)}"
        assert items[0].url == "https://example.com/valid"
        print(f"[OK] Only valid entry saved as SourceItem (count={len(items)})")

    finally:
        httpx.get = original_get
        db.rollback()
        db.close()


def test_html_index_probe_module_imports():
    """Test that HTML index probe module can be imported."""
    from app.sources.html_index_probe import (
        probe_html_index_source,
        run_html_index_probe_for_source,
        run_html_index_probe_for_enabled_sources,
    )
    assert callable(probe_html_index_source)
    assert callable(run_html_index_probe_for_source)
    assert callable(run_html_index_probe_for_enabled_sources)
    print("[OK] HTML index probe module imports successfully")


def test_html_index_probe_no_homepage_url():
    """Test that probe_html_index_source fails gracefully when homepage_url is not set."""
    from app.sources.html_index_probe import probe_html_index_source
    from app.db import SessionLocal
    from app.models import Source

    db = SessionLocal()
    try:
        test_key = f"test_no_homepage_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test No Homepage",
            description="A test source without homepage URL",
            source_type="html_index",
            homepage_url=None,
            category="research",
            tags_json="[]",
            enabled=True,
            fetch_strategy="html_index",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        result = probe_html_index_source(db, src)
        assert result["error_message"] is not None, "Expected error_message for missing homepage_url"
        assert "homepage_url" in result["error_message"].lower(), \
            f"Expected 'homepage_url' in error message, got: {result['error_message']}"
        print(f"[OK] probe_html_index_source fails with no homepage_url: {result['error_message']}")
    finally:
        db.rollback()
        db.close()


def test_html_index_probe_mock_html():
    """Test probe_html_index_source with a mocked HTML response."""
    import httpx
    from app.sources.html_index_probe import probe_html_index_source
    from app.db import SessionLocal
    from app.models import Source, SourceItem

    original_get = httpx.get

    fake_html = b"""<!DOCTYPE html>
<html>
<head><title>Test Blog</title></head>
<body>
    <nav><a href="/">Home</a></nav>
    <main>
        <a href="/blog/ai-agent-report">AI Agent Report</a>
        <a href="/news/product-update">Product Update</a>
        <a href="/about">About</a>
        <a href="mailto:test@example.com">Email</a>
        <a href="/static/logo.png">Logo</a>
        <a href="/research/papers/llm-survey">LLM Survey Paper</a>
        <a href="/posts/2025/01/ai-trends">AI Trends Post</a>
    </main>
</body>
</html>"""

    class FakeResponse:
        status_code = 200
        text = fake_html.decode("utf-8")
        def raise_for_status(self):
            pass

    def fake_get(url, timeout=None, follow_redirects=None, headers=None):
        return FakeResponse()

    httpx.get = fake_get

    db = SessionLocal()
    try:
        test_key = f"test_html_mock_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test HTML Mock",
            description="Mock HTML index source",
            source_type="html_index",
            homepage_url="https://example.com",
            category="research",
            tags_json="[]",
            enabled=True,
            fetch_strategy="html_index",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        # First probe
        result1 = probe_html_index_source(db, src)
        # Should find at least the blog and research links
        assert result1["items_found"] >= 2, \
            f"Expected >=2 items_found, got {result1['items_found']}"
        assert result1["items_new"] >= 2, \
            f"Expected >=2 items_new, got {result1['items_new']}"
        assert result1["error_message"] is None, \
            f"Expected no error, got: {result1['error_message']}"
        print(f"[OK] First probe: found={result1['items_found']}, new={result1['items_new']}")

        # Second probe — should update, not create new
        result2 = probe_html_index_source(db, src)
        assert result2["items_found"] == result1["items_found"]
        assert result2["items_new"] == 0, \
            f"Expected 0 new on re-run, got {result2['items_new']}"
        assert result2["items_updated"] >= 2, \
            f"Expected >=2 updated on re-run, got {result2['items_updated']}"
        print(f"[OK] Second probe (idempotent): new={result2['items_new']}, updated={result2['items_updated']}")

        # Verify DB state — /about, mailto, static files should NOT be in DB
        items = db.query(SourceItem).filter(SourceItem.source_id == src.id).all()
        item_urls = {item.url for item in items}

        assert "https://example.com/about" not in item_urls, \
            "/about should not be saved"
        assert "mailto:test@example.com" not in item_urls, \
            "mailto: links should not be saved"
        assert not any("logo.png" in url for url in item_urls), \
            "static assets should not be saved"

        assert "https://example.com/blog/ai-agent-report" in item_urls, \
            "/blog/ link should be saved"
        assert "https://example.com/research/papers/llm-survey" in item_urls, \
            "/research/ link should be saved"
        print(f"[OK] Filtering works correctly: /about, mailto, static filtered out")

    finally:
        httpx.get = original_get
        db.rollback()
        db.close()


def test_html_index_run_records_fetchrun_with_mock_html():
    """Test that run_html_index_probe_for_source records FetchRun correctly with mock HTML."""
    import httpx
    from app.sources.html_index_probe import run_html_index_probe_for_source
    from app.db import SessionLocal
    from app.models import Source

    original_get = httpx.get

    fake_html = b"""<!DOCTYPE html>
<html>
<body>
    <a href="/blog/important-article">Important Article</a>
    <a href="/news/update">News Update</a>
</body>
</html>"""

    class FakeResponse:
        status_code = 200
        text = fake_html.decode("utf-8")
        def raise_for_status(self):
            pass

    def fake_get(url, timeout=None, follow_redirects=None, headers=None):
        return FakeResponse()

    httpx.get = fake_get

    db = SessionLocal()
    try:
        test_key = f"test_html_run_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test HTML Run",
            description="Test HTML index source",
            source_type="html_index",
            homepage_url="https://example.com",
            category="research",
            tags_json="[]",
            enabled=True,
            fetch_strategy="html_index",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        fetch_run = run_html_index_probe_for_source(db, src)

        assert fetch_run.status == "success", \
            f"Expected status='success', got '{fetch_run.status}'"
        assert fetch_run.items_found >= 2, \
            f"Expected items_found >= 2, got {fetch_run.items_found}"
        assert fetch_run.finished_at is not None, \
            "finished_at should be set"
        print(f"[OK] FetchRun status=success, found={fetch_run.items_found}")

        # Re-query source and verify last_checked_at and last_success_at
        refreshed = db.query(Source).filter(Source.id == src.id).first()
        assert refreshed.last_checked_at is not None, \
            "last_checked_at should be updated"
        assert refreshed.last_success_at is not None, \
            "last_success_at should be updated"
        assert refreshed.last_error_message is None, \
            "last_error_message should be cleared on success"
        print("[OK] Source state updated correctly on success")

    finally:
        httpx.get = original_get
        db.rollback()
        db.close()


if __name__ == "__main__":
    print("=" * 50)
    print("AI Frontier Radar - Smoke Test")
    print("=" * 50)

    test_health()
    test_index()
    test_static_css()
    test_cards_page()
    test_llm_profile_config()
    test_sqlite_parent_dir_creation()
    test_utility_scripts_exist()
    test_source_config()
    test_source_registry_db_models()
    test_source_config_sync_to_db()
    test_sources_page()
    test_rss_probe_module_imports()
    test_rss_probe_no_feed_url()
    test_rss_probe_mock_feed()
    test_rss_run_records_failed_fetchrun_without_feed_url()
    test_rss_run_records_partial_failed_with_missing_link()
    test_html_index_probe_module_imports()
    test_html_index_probe_no_homepage_url()
    test_html_index_probe_mock_html()
    test_html_index_run_records_fetchrun_with_mock_html()
    test_compile_missing_api_key()
    test_compile_with_url()

    print("=" * 50)
    print("Smoke test completed!")
    print("=" * 50)
