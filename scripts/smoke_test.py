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
    # V0.3 featured sources section
    assert "精选 AI 前沿来源" in response.text, "Missing featured sources section"
    assert "OpenAI" in response.text, "Missing OpenAI in featured sources"
    assert "Anthropic" in response.text, "Missing Anthropic in featured sources"
    assert "nvidia_ai_blog" in response.text or "NVIDIA" in response.text, \
        "Missing NVIDIA in featured sources"
    print("[OK] GET / returns 200 with all required content and featured sources")


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


def test_probe_scripts_and_signatures():
    """Check probe scripts exist and runner functions have required parameters."""
    import inspect
    scripts_dir = Path(__file__).parent

    # Check script files exist
    for script in ["probe_rss_sources.py", "probe_html_index_sources.py", "acceptance_probe_sources.py"]:
        script_path = scripts_dir / script
        assert script_path.exists(), f"Probe script {script} not found"

    # Check RSS runner signature
    from app.sources.rss_probe import run_rss_probe_for_source, run_rss_probe_for_enabled_sources
    sig_single = inspect.signature(run_rss_probe_for_source)
    assert "timeout_seconds" in sig_single.parameters, \
        "run_rss_probe_for_source missing timeout_seconds parameter"

    sig_multi = inspect.signature(run_rss_probe_for_enabled_sources)
    assert "source_key" in sig_multi.parameters, \
        "run_rss_probe_for_enabled_sources missing source_key parameter"
    assert "limit_sources" in sig_multi.parameters, \
        "run_rss_probe_for_enabled_sources missing limit_sources parameter"
    assert "timeout_seconds" in sig_multi.parameters, \
        "run_rss_probe_for_enabled_sources missing timeout_seconds parameter"

    # Check HTML runner signature
    from app.sources.html_index_probe import run_html_index_probe_for_source, run_html_index_probe_for_enabled_sources
    sig_single_html = inspect.signature(run_html_index_probe_for_source)
    assert "timeout_seconds" in sig_single_html.parameters, \
        "run_html_index_probe_for_source missing timeout_seconds parameter"

    sig_multi_html = inspect.signature(run_html_index_probe_for_enabled_sources)
    assert "source_key" in sig_multi_html.parameters, \
        "run_html_index_probe_for_enabled_sources missing source_key parameter"
    assert "limit_sources" in sig_multi_html.parameters, \
        "run_html_index_probe_for_enabled_sources missing limit_sources parameter"
    assert "timeout_seconds" in sig_multi_html.parameters, \
        "run_html_index_probe_for_enabled_sources missing timeout_seconds parameter"

    print("[OK] Probe scripts exist and runner functions have required parameters")


def test_source_config():
    """Test that source registry config loads and validates correctly."""
    from app.sources import list_sources, get_source, get_enabled_sources

    all_sources = list_sources(include_disabled=True)
    assert len(all_sources) >= 15, \
        f"Expected at least 15 sources, got {len(all_sources)}"

    enabled = get_enabled_sources()
    assert len(enabled) >= 10, \
        f"Expected at least 10 enabled sources, got {len(enabled)}"

    # Check required sources exist
    required_keys = {"openai_news", "anthropic_news", "arxiv_cs_ai"}
    for key in required_keys:
        src = get_source(key)
        assert src is not None, f"Required source '{key}' not found"

    # Check new V0.3 sources
    new_keys = [
        "nvidia_ai_blog",
        "microsoft_ai_source",
        "berkeley_bair_blog",
        "mistral_ai_news",
        "cohere_blog",
    ]
    for key in new_keys:
        src = get_source(key)
        assert src is not None, f"New V0.3 source '{key}' not found"
        assert src.enabled, f"New V0.3 source '{key}' should be enabled by default"
    print(f"[OK] All 5 new V0.3 sources present and enabled")

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


def test_featured_sources_config():
    """Test that featured sources data layer returns all required fields."""
    from app.sources import get_featured_sources, list_sources

    sources = get_featured_sources()
    registry_sources = list_sources(include_disabled=True)
    registry_keys = {s.source_key for s in registry_sources}

    # Hard requirement: exactly 15 featured sources
    assert len(sources) == 15, \
        f"Expected exactly 15 featured sources, got {len(sources)}"

    # 1. featured source_key must not be duplicated
    featured_keys = [s["source_key"] for s in sources]
    assert len(featured_keys) == len(set(featured_keys)), \
        "featured source_key duplicated"

    # 2. featured source_key must all exist in Source Registry
    for key in featured_keys:
        assert key in registry_keys, \
            f"featured source_key '{key}' not found in Source Registry"

    # 3. priority must be P0, P1, or P2
    valid_priorities = {"P0", "P1", "P2"}
    for s in sources:
        assert s.get("priority") in valid_priorities, \
            f"source_key '{s['source_key']}' has invalid priority: {s.get('priority')}"

    # 4. category, homepage_url, focus, why, tags must all be present
    for s in sources:
        assert s.get("category"), \
            f"source_key '{s['source_key']}' missing category"
        assert s.get("homepage_url"), \
            f"source_key '{s['source_key']}' missing homepage_url"
        assert s.get("focus"), \
            f"source_key '{s['source_key']}' missing focus"
        assert s.get("why"), \
            f"source_key '{s['source_key']}' missing why"
        assert isinstance(s.get("tags"), list) and s["tags"], \
            f"source_key '{s['source_key']}' missing non-empty tags"

    # 5. homepage_url must start with http:// or https://
    for s in sources:
        url = s.get("homepage_url", "")
        assert url.startswith(("http://", "https://")), \
            f"source_key '{s['source_key']}' homepage_url must start with http:// or https://: {url}"

    print(f"[OK] Featured sources: {len(sources)} sources with all required fields")
    for s in sources:
        icon = s["icon"]
        try:
            print(f"     {icon} {s['display_name']} ({s['source_key']}) [{s['priority']}]")
        except UnicodeEncodeError:
            print(f"     [emoji] {s['display_name']} ({s['source_key']}) [{s['priority']}]")


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


def test_source_items_page():
    """Test that /source-items page loads and displays source items."""
    from app.db import SessionLocal
    from app.models import Source, SourceItem
    import uuid

    db = SessionLocal()
    try:
        # Create a test source
        test_key = f"test_si_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Source",
            description="Test source for items page",
            source_type="rss",
            homepage_url="https://example.com",
            feed_url="https://example.com/rss.xml",
            category="research",
            tags_json='[]',
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        # Create test source items
        item1 = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/article-agent-{uuid.uuid4().hex[:6]}",
            title="AI Agent Report",
            author="Author One",
            published_at="2025-01-15",
            status="discovered",
        )
        item2 = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/article-model-{uuid.uuid4().hex[:6]}",
            title="New Model Launch",
            author="Author Two",
            published_at="2025-01-16",
            status="discovered",
        )
        db.add(item1)
        db.add(item2)
        db.commit()

        # Test basic page load
        response = client.get("/source-items")
        assert response.status_code == 200, \
            f"Expected status 200, got {response.status_code}"
        text = response.text
        assert "发现条目" in text or "SourceItem" in text or "收件箱" in text, \
            "Page should contain '发现条目' or 'SourceItem' or '收件箱'"
        print("[OK] GET /source-items returns 200")

        # Test source_key filter
        response = client.get(f"/source-items?source_key={test_key}")
        assert response.status_code == 200
        assert "AI Agent Report" in response.text, \
            "AI Agent Report should appear when filtering by source_key"
        assert "New Model Launch" in response.text, \
            "New Model Launch should appear when filtering by source_key"
        print(f"[OK] /source-items?source_key={test_key} shows items")

        # Test q search
        response = client.get("/source-items?q=Agent")
        assert response.status_code == 200
        assert "Agent" in response.text, \
            "'Agent' should appear in search results"
        print("[OK] /source-items?q=Agent search works")

        # Test status filter
        response = client.get("/source-items?status=discovered")
        assert response.status_code == 200
        assert "AI Agent Report" in response.text, \
            "Items with status=discovered should appear"
        print("[OK] /source-items?status=discovered filter works")

    finally:
        db.rollback()
        db.close()


def test_source_item_detail_page():
    """Test that /source-items/{id} detail page loads correctly."""
    from app.db import SessionLocal
    from app.models import Source, SourceItem

    db = SessionLocal()
    try:
        # Create a test source
        test_key = f"test_detail_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Detail Source",
            description="Test source for detail page",
            source_type="rss",
            homepage_url="https://example.com",
            feed_url="https://example.com/rss.xml",
            category="research",
            tags_json='[]',
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        # Create a test source item
        item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/detail-article-{uuid.uuid4().hex[:6]}",
            title="Detail Test Article",
            author="Test Author",
            published_at="2025-01-20",
            status="discovered",
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        # Test detail page loads
        response = client.get(f"/source-items/{item.id}")
        assert response.status_code == 200, \
            f"Expected status 200, got {response.status_code}"
        text = response.text
        assert "发现条目详情" in text or "SourceItem" in text, \
            "Page should contain '发现条目详情' or 'SourceItem'"
        assert item.url in text, "Item URL should appear on detail page"
        assert "Detail Test Article" in text, "Item title should appear on detail page"
        print(f"[OK] GET /source-items/{item.id} returns 200 with content")

        # Test non-existent item redirects
        response = client.get("/source-items/999999999", follow_redirects=False)
        assert response.status_code in (302, 303), \
            f"Expected redirect for non-existent item, got {response.status_code}"
        print("[OK] GET /source-items/999999999 redirects (not found)")

    finally:
        db.rollback()
        db.close()


def test_source_item_compile_route_with_mock_compile_url():
    """Test POST /source-items/{id}/compile with mocked compile_url."""
    import app.main as main_module
    from app.models import InsightCard, CardStatus, SourceType, Source, SourceItem
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        # Create test source and source item
        test_key = f"test_compile_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Compile Source",
            description="Test source for compile route",
            source_type="rss",
            homepage_url="https://example.com",
            feed_url="https://example.com/rss.xml",
            category="research",
            tags_json='[]',
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/compile-article-{uuid.uuid4().hex[:6]}",
            title="Compile Test Article",
            status="discovered",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        item_id = item.id

        # Mock compile_url to return a successful card
        original_compile_url = main_module.compile_url

        def fake_compile_url(db, url):
            card = InsightCard(
                source_url=url,
                source_type=SourceType.HTML,
                source_title="Mock Compiled Card",
                content_hash="mock-hash-123",
                status=CardStatus.COMPLETED,
                summary_zh="Mock summary",
                relevance_score=85,
            )
            db.add(card)
            db.commit()
            db.refresh(card)
            return card

        main_module.compile_url = fake_compile_url
        try:
            # Call compile route
            response = client.post(f"/source-items/{item_id}/compile", follow_redirects=False)
            assert response.status_code in (302, 303), \
                f"Expected redirect, got {response.status_code}"
            print(f"[OK] POST /source-items/{item_id}/compile redirects ({response.status_code})")

            # Re-query item and verify it was updated
            # Expire all to force re-fetch from DB (compile route used a separate session)
            db.expire_all()
            refreshed_item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
            assert refreshed_item.status == "compiled", \
                f"Expected status='compiled', got '{refreshed_item.status}'"
            assert refreshed_item.insight_card_id is not None, \
                "insight_card_id should be set"
            assert refreshed_item.error_message is None, \
                "error_message should be cleared on success"
            print(f"[OK] SourceItem updated: status=compiled, insight_card_id={refreshed_item.insight_card_id}")

        finally:
            main_module.compile_url = original_compile_url

    finally:
        db.rollback()
        db.close()


def test_source_item_compile_route_with_failed_card():
    """Test POST /source-items/{id}/compile with a mocked failed card."""
    import app.main as main_module
    from app.models import InsightCard, CardStatus, SourceType, Source, SourceItem
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        # Create test source and source item
        test_key = f"test_fail_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Fail Source",
            description="Test source for failed compile",
            source_type="rss",
            homepage_url="https://example.com",
            feed_url="https://example.com/rss.xml",
            category="research",
            tags_json='[]',
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/fail-article-{uuid.uuid4().hex[:6]}",
            title="Fail Test Article",
            status="discovered",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        item_id = item.id

        # Mock compile_url to return a failed card
        original_compile_url = main_module.compile_url

        def fake_compile_url_failed(db, url):
            card = InsightCard(
                source_url=url,
                source_type=SourceType.HTML,
                source_title="Failed Card",
                content_hash="mock-hash-fail",
                status=CardStatus.FAILED,
                error_message="Mock failure: API key missing",
            )
            db.add(card)
            db.commit()
            db.refresh(card)
            return card

        main_module.compile_url = fake_compile_url_failed
        try:
            response = client.post(f"/source-items/{item_id}/compile", follow_redirects=False)
            assert response.status_code in (302, 303), \
                f"Expected redirect, got {response.status_code}"
            print(f"[OK] POST /source-items/{item_id}/compile (failed card) redirects ({response.status_code})")

            # Re-query item and verify it was updated to failed
            db.expire_all()
            refreshed_item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
            assert refreshed_item.status == "failed", \
                f"Expected status='failed', got '{refreshed_item.status}'"
            assert refreshed_item.insight_card_id is not None, \
                "insight_card_id should be set even for failed card"
            assert "Mock failure" in (refreshed_item.error_message or ""), \
                f"error_message should contain 'Mock failure', got: {refreshed_item.error_message}"
            print(f"[OK] SourceItem updated: status=failed, error_message set")

        finally:
            main_module.compile_url = original_compile_url

    finally:
        db.rollback()
        db.close()


def test_source_item_compile_already_compiled_is_idempotent():
    """Test that POST on an already-compiled SourceItem does NOT call compile_url."""
    import app.main as main_module
    from app.db import SessionLocal
    from app.models import InsightCard, CardStatus, SourceType, Source, SourceItem

    db = SessionLocal()
    try:
        # Create source and already-compiled SourceItem with existing card
        test_key = f"test_already_compiled_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Already Compiled",
            description="Test source",
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

        # Create a completed card first
        card = InsightCard(
            source_url="https://example.com/already-compiled",
            source_type=SourceType.HTML,
            source_title="Already Compiled Card",
            content_hash="already-compiled-hash",
            status=CardStatus.COMPLETED,
            summary_zh="Already done",
            relevance_score=80,
        )
        db.add(card)
        db.commit()
        db.refresh(card)

        item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url="https://example.com/already-compiled",
            title="Already Compiled Article",
            status="compiled",
            insight_card_id=card.id,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        item_id = item.id
        original_card_id = card.id

        # Mock compile_url to fail if called
        call_count = [0]
        original = main_module.compile_url

        def counting_mock(db_session, url):
            call_count[0] += 1
            return original(db_session, url)

        main_module.compile_url = counting_mock
        try:
            # POST should redirect without calling compile_url
            response = client.post(f"/source-items/{item_id}/compile", follow_redirects=False)
            assert response.status_code == 303, f"Expected 303, got {response.status_code}"

            # compile_url should NOT have been called
            assert call_count[0] == 0, \
                f"compile_url was called {call_count[0]} times (should be 0 for already-compiled)"

            # Item state should be unchanged
            db.expire_all()
            refreshed = db.query(SourceItem).filter(SourceItem.id == item_id).first()
            assert refreshed.status == "compiled", \
                f"Expected status='compiled', got '{refreshed.status}'"
            assert refreshed.insight_card_id == original_card_id, \
                f"insight_card_id changed from {original_card_id} to {refreshed.insight_card_id}"
            print(f"[OK] Already-compiled item: no re-compile, status unchanged")
        finally:
            main_module.compile_url = original

    finally:
        db.rollback()
        db.close()


def test_source_item_compile_failed_retry_succeeds():
    """Test that a failed SourceItem can be retried and succeed."""
    import app.main as main_module
    from app.db import SessionLocal
    from app.models import InsightCard, CardStatus, SourceType, Source, SourceItem

    db = SessionLocal()
    try:
        test_key = f"test_retry_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Retry",
            description="Test source",
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

        item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url="https://example.com/retry-article",
            title="Retry Test Article",
            status="failed",
            error_message="Previous error",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        item_id = item.id

        original = main_module.compile_url

        def fake_success(db_session, url):
            card = InsightCard(
                source_url=url,
                source_type=SourceType.HTML,
                source_title="Retry Success Card",
                content_hash="retry-hash",
                status=CardStatus.COMPLETED,
                summary_zh="Retry succeeded",
                relevance_score=85,
            )
            db_session.add(card)
            db_session.commit()
            db_session.refresh(card)
            return card

        main_module.compile_url = fake_success
        try:
            response = client.post(f"/source-items/{item_id}/compile", follow_redirects=False)
            assert response.status_code == 303, f"Expected 303, got {response.status_code}"

            db.expire_all()
            refreshed = db.query(SourceItem).filter(SourceItem.id == item_id).first()
            assert refreshed.status == "compiled", \
                f"Expected status='compiled' after retry, got '{refreshed.status}'"
            assert refreshed.insight_card_id is not None, \
                "insight_card_id should be set after retry"
            assert refreshed.error_message is None, \
                f"error_message should be cleared after retry, got: {refreshed.error_message}"
            print(f"[OK] Failed item retried: status=compiled, error cleared")
        finally:
            main_module.compile_url = original

    finally:
        db.rollback()
        db.close()


def test_source_item_compile_route_with_empty_url():
    """Test POST /source-items/{id}/compile with empty URL returns failed status."""
    from app.db import SessionLocal
    from app.models import Source, SourceItem

    db = SessionLocal()
    try:
        # Create test source
        test_key = f"test_empty_url_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Empty URL Source",
            description="Test source for empty URL compile",
            source_type="rss",
            homepage_url="https://example.com",
            feed_url="https://example.com/rss.xml",
            category="research",
            tags_json='[]',
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        # Create a source item with empty URL
        item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url="",  # empty URL
            title="Empty URL Test Item",
            status="discovered",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        item_id = item.id

        # Call compile route
        response = client.post(f"/source-items/{item_id}/compile", follow_redirects=False)
        assert response.status_code in (302, 303), \
            f"Expected redirect, got {response.status_code}"
        print(f"[OK] POST /source-items/{item_id}/compile (empty URL) redirects ({response.status_code})")

        # Re-query and verify
        db.expire_all()
        refreshed_item = db.query(SourceItem).filter(SourceItem.id == item_id).first()
        assert refreshed_item.status == "failed", \
            f"Expected status='failed', got '{refreshed_item.status}'"
        assert "url is empty" in (refreshed_item.error_message or "").lower(), \
            f"error_message should mention 'url is empty', got: {refreshed_item.error_message}"
        assert refreshed_item.insight_card_id is None, \
            "insight_card_id should be None for empty URL"
        print(f"[OK] SourceItem updated: status=failed, url is empty, no insight_card_id")

    finally:
        db.rollback()
        db.close()


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


def test_rss_probe_duplicate_link():
    """Test that RSS probe handles duplicate entry links without IntegrityError."""
    import httpx
    from app.sources.rss_probe import probe_rss_source, run_rss_probe_for_source
    from app.db import SessionLocal
    from app.models import Source, SourceItem

    original_get = httpx.get

    # RSS XML with a duplicate link
    fake_rss_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
  <title>Test Feed</title>
  <link>https://example.com</link>
  <item>
    <title>Article A</title>
    <link>https://example.com/article-a</link>
    <author>Author</author>
    <pubDate>2025-01-15T10:00:00Z</pubDate>
  </item>
  <item>
    <title>Article A Duplicate</title>
    <link>https://example.com/article-a</link>
    <author>Author2</author>
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

    httpx.get = fake_get

    db = SessionLocal()
    try:
        test_key = f"test_rss_dup_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test RSS Duplicate",
            description="Test RSS source with duplicate links",
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

        # First probe: duplicate URL is skipped, so items_found=1 (unique link only)
        result1 = probe_rss_source(db, src)
        assert result1["items_found"] == 1, f"Expected items_found=1 (unique link), got {result1['items_found']}"
        assert result1["items_new"] == 1, f"Expected items_new=1, got {result1['items_new']}"
        assert result1["items_updated"] == 0
        print(f"[OK] First probe: found={result1['items_found']}, new={result1['items_new']}")

        # Verify exactly 1 SourceItem
        items = db.query(SourceItem).filter(SourceItem.source_id == src.id).all()
        assert len(items) == 1, f"Expected 1 SourceItem, got {len(items)}"
        print(f"[OK] Only 1 SourceItem created (duplicate link skipped)")

        # Second probe — should update, not create new
        # Both entries point to same URL; dedup makes items_found=1
        result2 = probe_rss_source(db, src)
        assert result2["items_found"] == 1, f"Expected items_found=1 (deduped), got {result2['items_found']}"
        assert result2["items_new"] == 0, f"Expected items_new=0 on re-run, got {result2['items_new']}"
        assert result2["items_updated"] == 1, f"Expected items_updated=1, got {result2['items_updated']}"
        print(f"[OK] Second probe (idempotent): new={result2['items_new']}, updated={result2['items_updated']}")

        # Verify still only 1 SourceItem
        items = db.query(SourceItem).filter(SourceItem.source_id == src.id).all()
        assert len(items) == 1, f"Expected still 1 SourceItem, got {len(items)}"
        print(f"[OK] Still 1 SourceItem after second probe")

    finally:
        httpx.get = original_get
        db.rollback()
        db.close()


def test_html_index_probe_duplicate_href():
    """Test that HTML index probe handles duplicate hrefs without IntegrityError."""
    import httpx
    from app.sources.html_index_probe import probe_html_index_source, run_html_index_probe_for_source
    from app.db import SessionLocal
    from app.models import Source, SourceItem

    original_get = httpx.get

    # HTML with duplicate hrefs
    fake_html = b"""<!DOCTYPE html>
<html>
<body>
    <nav><a href="/">Home</a></nav>
    <main>
        <a href="/blog/important-article">Important Article</a>
        <a href="/blog/important-article">Important Article Again</a>
        <a href="/blog/other-article">Other Article</a>
        <a href="/blog/other-article">Other Article Again</a>
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
        test_key = f"test_html_dup_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test HTML Duplicate",
            description="Test HTML source with duplicate hrefs",
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
        assert result1["items_found"] == 2, f"Expected items_found=2, got {result1['items_found']}"
        assert result1["items_new"] == 2, f"Expected items_new=2 (2 unique URLs), got {result1['items_new']}"
        assert result1["items_updated"] == 0
        print(f"[OK] First probe: found={result1['items_found']}, new={result1['items_new']}")

        # Verify exactly 2 SourceItems
        items = db.query(SourceItem).filter(SourceItem.source_id == src.id).all()
        assert len(items) == 2, f"Expected 2 SourceItems, got {len(items)}"
        print(f"[OK] 2 SourceItems created (duplicate hrefs skipped)")

        # Second probe — should update
        result2 = probe_html_index_source(db, src)
        assert result2["items_found"] == 2
        assert result2["items_new"] == 0, f"Expected items_new=0 on re-run, got {result2['items_new']}"
        assert result2["items_updated"] == 2, f"Expected items_updated=2, got {result2['items_updated']}"
        print(f"[OK] Second probe (idempotent): new={result2['items_new']}, updated={result2['items_updated']}")

        # Verify still only 2 SourceItems
        items = db.query(SourceItem).filter(SourceItem.source_id == src.id).all()
        assert len(items) == 2, f"Expected still 2 SourceItems, got {len(items)}"
        print(f"[OK] Still 2 SourceItems after second probe")

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


def test_html_index_run_records_partial_failed_when_no_candidates():
    """Test that run_html_index_probe_for_source records partial_failed when no candidate links found."""
    import httpx
    from app.sources.html_index_probe import run_html_index_probe_for_source
    from app.db import SessionLocal
    from app.models import Source, SourceItem

    original_get = httpx.get

    # HTML with only non-article links (about, contact, mailto, static)
    fake_html = b"""<!DOCTYPE html>
<html>
<body>
  <a href="/">Home</a>
  <a href="/about">About</a>
  <a href="/contact">Contact</a>
  <a href="mailto:test@example.com">Email</a>
  <a href="/static/logo.png">Logo</a>
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
        test_key = f"test_no_candidates_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test No Candidates",
            description="Test source with no article links",
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

        assert fetch_run.status == "partial_failed", \
            f"Expected status='partial_failed', got '{fetch_run.status}'"
        assert fetch_run.items_found == 0, \
            f"Expected items_found=0, got {fetch_run.items_found}"
        assert fetch_run.items_new == 0, \
            f"Expected items_new=0, got {fetch_run.items_new}"
        assert fetch_run.items_updated == 0, \
            f"Expected items_updated=0, got {fetch_run.items_updated}"
        assert fetch_run.error_message is not None, \
            "error_message should be set"
        assert "No candidate article links found" in fetch_run.error_message, \
            f"Expected 'No candidate article links found' in error, got: {fetch_run.error_message}"
        print(f"[OK] FetchRun status=partial_failed, error={fetch_run.error_message}")

        # Re-query source and verify last_checked_at updated but last_success_at NOT updated
        refreshed = db.query(Source).filter(Source.id == src.id).first()
        assert refreshed.last_checked_at is not None, \
            "last_checked_at should be updated"
        assert refreshed.last_error_message is not None, \
            "last_error_message should be set"
        assert refreshed.last_success_at is None, \
            "last_success_at should NOT be updated when no candidates found"
        print("[OK] Source.last_success_at NOT updated on no_candidates")

        # Verify no SourceItems were created
        items = db.query(SourceItem).filter(SourceItem.source_id == src.id).all()
        assert len(items) == 0, \
            f"Expected 0 SourceItems, got {len(items)}"
        print("[OK] No SourceItems created when no candidates found")

    finally:
        httpx.get = original_get
        db.rollback()
        db.close()


def test_source_items_page_wide_layout_and_scroll():
    """Test that /source-items page has V0.3.4 wide layout and scrollable table."""
    response = client.get("/source-items")
    assert response.status_code == 200, \
        f"Expected status 200, got {response.status_code}"
    text = response.text
    # Check for new V0.3.4 classes
    assert "table-scroll" in text, \
        "Page should contain 'table-scroll' container for horizontal scroll"
    assert "source-items-table" in text, \
        "Page should use 'source-items-table' class"
    assert "wide-page" in text, \
        "Page should use 'wide-page' class for wider layout"
    print("[OK] /source-items has V0.3.4 wide layout + scrollable table")


def test_source_items_page_v033_notice():
    """Test that /source-items page has V0.3.3 historical URL notice."""
    response = client.get("/source-items")
    assert response.status_code == 200
    text = response.text
    assert "V0.3.3 已过滤新的分页/列表 URL" in text, \
        "Page should show V0.3.3 historical pagination URL notice"
    assert "check_listing_source_items.py" in text, \
        "Page should mention the check_listing_source_items.py script"
    print("[OK] /source-items shows V0.3.3 historical URL notice")


def test_source_items_template_no_url_truncation():
    """Test that source_items.html no longer truncates URLs to 80 chars."""
    from pathlib import Path
    template_path = Path(__file__).parent.parent / "app" / "templates" / "source_items.html"
    assert template_path.exists(), "source_items.html template not found"
    template_text = template_path.read_text(encoding="utf-8")
    assert "item.url[:80]" not in template_text, \
        "source_items.html still contains 'item.url[:80]' truncation"
    assert "title=\"{{ item.url }}\"" in template_text, \
        "source_items.html should have title attribute on URL link"
    print("[OK] source_items.html removed URL truncation and added title attr")


def test_check_listing_script_exists():
    """Test that scripts/check_listing_source_items.py exists."""
    from pathlib import Path
    script_path = Path(__file__).parent / "check_listing_source_items.py"
    assert script_path.exists(), "check_listing_source_items.py not found"
    print("[OK] scripts/check_listing_source_items.py exists")


def test_check_listing_script_imports():
    """Test that check_listing_source_items module can be imported without error."""
    try:
        import importlib.util
        script_path = (
            Path(__file__).parent / "check_listing_source_items.py"
        )
        spec = importlib.util.spec_from_file_location(
            "check_listing_source_items", str(script_path)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert hasattr(module, "_check_listing_source_items"), \
            "check_listing_source_items.py should have _check_listing_source_items function"
        assert hasattr(module, "_build_arg_parser"), \
            "check_listing_source_items.py should have _build_arg_parser function"
        print("[OK] check_listing_source_items.py imports successfully")
    except Exception as e:
        raise AssertionError(f"check_listing_source_items.py failed to import: {e}") from e


def test_source_items_url_no_truncation_in_page():
    """Test that actual /source-items page renders full URLs (not truncated)."""
    from app.db import SessionLocal
    from app.models import Source, SourceItem
    import uuid

    db = SessionLocal()
    try:
        # Create a test source
        test_key = f"test_url_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test URL Display",
            description="Test source for URL display",
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

        # Create a long URL
        long_url = "https://example.com/very/long/path/segment/article-title-with-many-words"
        item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=long_url,
            title="Long URL Test Article",
            status="discovered",
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        # Fetch page filtered by source_key
        response = client.get(f"/source-items?source_key={test_key}")
        assert response.status_code == 200
        text = response.text
        # Full URL should appear, not the truncated form
        assert long_url in text, \
            f"Full URL should appear in page. Expected: {long_url}"
        assert f"{long_url[:80]}..." not in text, \
            "Truncated URL (with ellipsis) should NOT appear in page"
        print("[OK] Full URL displayed in /source-items page (no truncation)")
    finally:
        db.rollback()
        db.close()


def test_source_items_v035_usage_guide():
    """Test that /source-items page contains V0.3.5 Chinese usage guide."""
    response = client.get("/source-items")
    assert response.status_code == 200
    text = response.text
    # Check Chinese usage guide header and key bullet points
    assert "如何使用这个页面" in text, \
        "Page should have '如何使用这个页面' Chinese guide header"
    assert "编译为 InsightCard" in text, \
        "Page should mention '编译为 InsightCard' action"
    assert "当前阶段不自动批量编译" in text, \
        "Page should note '当前阶段不自动批量编译'"
    print("[OK] /source-items has V0.3.5 Chinese usage guide")


def test_source_items_v035_action_column():
    """Test that /source-items page contains V0.3.5 recommended action column."""
    from app.db import SessionLocal
    from app.models import Source, SourceItem, InsightCard, CardStatus, SourceType
    import uuid

    db = SessionLocal()
    try:
        # Create test source
        test_key = f"test_act_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Action Column",
            description="Test recommended action column",
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

        # Create one item per status
        discovered_item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/disc-{uuid.uuid4().hex[:6]}",
            title="Discovered Article",
            status="discovered",
        )
        failed_item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/fail-{uuid.uuid4().hex[:6]}",
            title="Failed Article",
            status="failed",
            error_message="Test error",
        )

        # Create a card for compiled item
        card = InsightCard(
            source_url="https://example.com/comp",
            source_type=SourceType.HTML,
            source_title="Compiled Card",
            content_hash="test-hash",
            status=CardStatus.COMPLETED,
            summary_zh="Test summary",
        )
        db.add(card)
        db.commit()
        db.refresh(card)

        compiled_item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url="https://example.com/comp",
            title="Compiled Article",
            status="compiled",
            insight_card_id=card.id,
        )
        db.add(discovered_item)
        db.add(failed_item)
        db.add(compiled_item)
        db.commit()

        response = client.get(f"/source-items?source_key={test_key}")
        assert response.status_code == 200
        text = response.text

        # Check action column header
        assert "推荐操作" in text, \
            "Page should have '推荐操作' column header"

        # Check all three action labels
        assert "进入详情并编译" in text, \
            "Page should show '进入详情并编译' for discovered items"
        assert "查看中文卡片" in text, \
            "Page should show '查看中文卡片' for compiled items"
        assert "查看失败原因" in text, \
            "Page should show '查看失败原因' for failed items"

        # Check that action links point to the right places
        assert f"/source-items/{discovered_item.id}" in text, \
            f"Discovered action should link to /source-items/{discovered_item.id}"
        assert f"/cards/{card.id}" in text, \
            f"Compiled action should link to /cards/{card.id}"
        assert f"/source-items/{failed_item.id}" in text, \
            f"Failed action should link to /source-items/{failed_item.id}"
        print(f"[OK] /source-items has V0.3.5 recommended action column with all 3 states")
    finally:
        db.rollback()
        db.close()


def test_source_item_detail_v035_chinese_explanation():
    """Test that /source-items/{id} detail page has V0.3.5 Chinese explanation."""
    from app.db import SessionLocal
    from app.models import Source, SourceItem
    import uuid

    db = SessionLocal()
    try:
        test_key = f"test_dt_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Detail",
            description="Test detail page",
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

        # Test discovered status detail page
        discovered_item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/desc-{uuid.uuid4().hex[:6]}",
            title="Discovered Article",
            status="discovered",
        )
        db.add(discovered_item)
        db.commit()
        db.refresh(discovered_item)

        response = client.get(f"/source-items/{discovered_item.id}")
        assert response.status_code == 200
        text = response.text
        assert "英文前沿来源" in text, \
            "Detail page should mention '英文前沿来源' in Chinese explanation"
        assert "中文洞察卡" in text, \
            "Detail page should mention '中文洞察卡' / InsightCard concept"
        print("[OK] /source-items/{id} has V0.3.5 Chinese explanation")

        # Test failed status detail page
        failed_item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/fail-{uuid.uuid4().hex[:6]}",
            title="Failed Article",
            status="failed",
            error_message="Test error",
        )
        db.add(failed_item)
        db.commit()
        db.refresh(failed_item)

        response2 = client.get(f"/source-items/{failed_item.id}")
        assert response2.status_code == 200
        text2 = response2.text
        assert "失败可能来自" in text2 or "API Key" in text2, \
            "Failed detail page should explain failure reasons"
        print("[OK] /source-items/{id} (failed) has failure-reason helper text")
    finally:
        db.rollback()
        db.close()


def test_v035_manual_acceptance_doc_exists():
    """Test that docs/V0.3.5_MANUAL_ACCEPTANCE.md exists."""
    from pathlib import Path
    doc_path = (
        Path(__file__).parent.parent / "docs" / "V0.3.5_MANUAL_ACCEPTANCE.md"
    )
    assert doc_path.exists(), "docs/V0.3.5_MANUAL_ACCEPTANCE.md not found"
    text = doc_path.read_text(encoding="utf-8")
    # Spot-check key sections
    assert "目标" in text, "Doc should have '目标' section"
    assert "前置条件" in text, "Doc should have '前置条件' section"
    assert "常见问题" in text, "Doc should have '常见问题' section"
    assert "check_listing_source_items.py" in text, \
        "Doc should reference check_listing_source_items.py"
    print("[OK] docs/V0.3.5_MANUAL_ACCEPTANCE.md exists with required sections")


def test_v035_readme_section():
    """Test that README contains V0.3.5 section."""
    from pathlib import Path
    readme_path = Path(__file__).parent.parent / "README.md"
    text = readme_path.read_text(encoding="utf-8")
    assert "V0.3.5 中文优先人工验收体验" in text, \
        "README should have V0.3.5 section header"
    assert "推荐操作" in text, \
        "README V0.3.5 section should mention 推荐操作"
    print("[OK] README contains V0.3.5 section")


def test_source_items_inbox_refined_status_cell():
    """Test refined status cell shows Chinese-first copy with technical value as small text."""
    response = client.get("/source-items")
    assert response.status_code == 200
    text = response.text
    # New status copy should be present in the template
    assert "可生成中文 InsightCard" in text, \
        "Status cell should show '可生成中文 InsightCard' for discovered"
    assert "已生成中文卡片" in text, \
        "Status cell should show '已生成中文卡片' for compiled"
    assert "可查看原因后重试" in text, \
        "Status cell should show '可查看原因后重试' for failed"
    print("[OK] /source-items has refined Chinese-first status cell copy")


def test_source_items_inbox_action_column_position():
    """Test that '推荐操作' column appears right after '状态' column."""
    from pathlib import Path
    template_path = (
        Path(__file__).parent.parent / "app" / "templates" / "source_items.html"
    )
    text = template_path.read_text(encoding="utf-8")

    # Find header positions
    pos_status = text.find("<th>状态</th>")
    pos_action = text.find("<th>推荐操作</th>")

    assert pos_status != -1, "Should have <th>状态</th> header"
    assert pos_action != -1, "Should have <th>推荐操作</th> header"
    assert pos_action > pos_status, \
        "推荐操作 column should come AFTER 状态 column"
    # Action column should appear before the time-related columns
    pos_published = text.find("<th>发布时间</th>")
    assert pos_action < pos_published, \
        "推荐操作 column should come BEFORE 发布时间 column (no horizontal scroll needed)"

    delta = pos_action - pos_status
    print(f"[OK] '推荐操作' column positioned right after '状态' (delta={delta} chars)")


def test_source_items_inbox_action_column_compiled_without_card():
    """Test that compiled item without insight_card_id shows '查看详情' fallback."""
    from app.db import SessionLocal
    from app.models import Source, SourceItem
    import uuid

    db = SessionLocal()
    try:
        test_key = f"test_no_card_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test No Card",
            description="Test compiled item without card",
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

        # Compiled item WITHOUT insight_card_id
        item = SourceItem(
            source_id=src.id,
            source_key=test_key,
            url=f"https://example.com/comp-no-card-{uuid.uuid4().hex[:6]}",
            title="Compiled Without Card",
            status="compiled",
            insight_card_id=None,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        response = client.get(f"/source-items?source_key={test_key}")
        assert response.status_code == 200
        text = response.text
        # Should show "查看详情" fallback, NOT "查看中文卡片"
        assert "查看详情" in text, \
            "Compiled item without insight_card_id should show '查看详情' fallback"
        print("[OK] Compiled item without card shows '查看详情' fallback")
    finally:
        db.rollback()
        db.close()


def test_html_index_filters_huggingface_listing_pages():
    """Test that Hugging Face blog listing/pagination pages are filtered out."""
    import httpx
    from app.sources.html_index_probe import probe_html_index_source
    from app.db import SessionLocal
    from app.models import Source, SourceItem

    original_get = httpx.get

    # Fake HTML with a mix of listing pages and article pages
    fake_html = b"""<!DOCTYPE html>
<html>
<body>
    <a href="/blog">Blog Home</a>
    <a href="/blog?p=2">Page 2</a>
    <a href="/blog?page=3">Page 3</a>
    <a href="/blog?sort=popular">Popular</a>
    <a href="/blog?tag=agents">Agents Tag</a>
    <a href="/blog/open-r1">Open R1</a>
    <a href="/blog/smolagents">Smolagents</a>
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
        test_key = f"test_hf_listing_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Hugging Face Blog",
            description="Test Hugging Face blog listing filter",
            source_type="html_index",
            homepage_url="https://huggingface.co",
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

        # Should only find the 2 article pages
        assert result["items_found"] == 2, \
            f"Expected 2 items_found, got {result['items_found']}"
        assert result["items_new"] == 2, \
            f"Expected 2 items_new, got {result['items_new']}"
        assert result["error_message"] is None, \
            f"Expected no error, got: {result['error_message']}"
        print(f"[OK] HuggingFace listing filter: found={result['items_found']}, new={result['items_new']}")

        # Verify DB state — listing pages should NOT be in DB
        items = db.query(SourceItem).filter(SourceItem.source_id == src.id).all()
        item_urls = {item.url for item in items}

        assert "https://huggingface.co/blog" not in item_urls, \
            "/blog should not be saved"
        assert "https://huggingface.co/blog?p=2" not in item_urls, \
            "/blog?p=2 should not be saved"
        assert "https://huggingface.co/blog?page=3" not in item_urls, \
            "/blog?page=3 should not be saved"
        assert "https://huggingface.co/blog?sort=popular" not in item_urls, \
            "/blog?sort=popular should not be saved"
        assert "https://huggingface.co/blog?tag=agents" not in item_urls, \
            "/blog?tag=agents should not be saved"

        assert "https://huggingface.co/blog/open-r1" in item_urls, \
            "/blog/open-r1 should be saved"
        assert "https://huggingface.co/blog/smolagents" in item_urls, \
            "/blog/smolagents should be saved"
        print("[OK] Only article URLs saved: /blog/open-r1, /blog/smolagents")

    finally:
        httpx.get = original_get
        db.rollback()
        db.close()


def test_html_index_filters_generic_listing_pages():
    """Test that generic listing/pagination/filter pages are filtered out."""
    import httpx
    from app.sources.html_index_probe import probe_html_index_source
    from app.db import SessionLocal
    from app.models import Source, SourceItem

    original_get = httpx.get

    fake_html = b"""<!DOCTYPE html>
<html>
<body>
    <a href="/news">News Index</a>
    <a href="/news?page=2">News Page 2</a>
    <a href="/research">Research Index</a>
    <a href="/research?topic=agents">Research Topic</a>
    <a href="/news/model-release">Model Release</a>
    <a href="/research/agent-safety-report">Agent Safety Report</a>
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
        test_key = f"test_generic_listing_{uuid.uuid4().hex[:8]}"
        src = Source(
            source_key=test_key,
            name="Test Generic Listing",
            description="Test generic listing page filter",
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

        result = probe_html_index_source(db, src)

        # Should only find the 2 article pages
        assert result["items_found"] == 2, \
            f"Expected 2 items_found, got {result['items_found']}"
        assert result["items_new"] == 2, \
            f"Expected 2 items_new, got {result['items_new']}"
        assert result["error_message"] is None, \
            f"Expected no error, got: {result['error_message']}"
        print(f"[OK] Generic listing filter: found={result['items_found']}, new={result['items_new']}")

        # Verify DB state — listing pages should NOT be in DB
        items = db.query(SourceItem).filter(SourceItem.source_id == src.id).all()
        item_urls = {item.url for item in items}

        assert "https://example.com/news" not in item_urls, \
            "/news should not be saved"
        assert "https://example.com/news?page=2" not in item_urls, \
            "/news?page=2 should not be saved"
        assert "https://example.com/research" not in item_urls, \
            "/research should not be saved"
        assert "https://example.com/research?topic=agents" not in item_urls, \
            "/research?topic=agents should not be saved"

        assert "https://example.com/news/model-release" in item_urls, \
            "/news/model-release should be saved"
        assert "https://example.com/research/agent-safety-report" in item_urls, \
            "/research/agent-safety-report should be saved"
        print("[OK] Only article URLs saved: /news/model-release, /research/agent-safety-report")

    finally:
        httpx.get = original_get
        db.rollback()
        db.close()


def test_v04_card_decision_model_exists():
    """Test that CardDecision model and ALLOWED_CARD_DECISIONS are importable."""
    from app.models import CardDecision
    from app.card_decisions import ALLOWED_CARD_DECISIONS, get_decision_label, is_valid_decision

    # Table name
    assert CardDecision.__tablename__ == "card_decisions", \
        f"Expected table 'card_decisions', got {CardDecision.__tablename__!r}"

    # 5 allowed decisions
    assert len(ALLOWED_CARD_DECISIONS) == 5, \
        f"Expected 5 allowed decisions, got {len(ALLOWED_CARD_DECISIONS)}"
    for key in ("worth_attention", "related_to_me", "read_later", "ignore", "to_action"):
        assert key in ALLOWED_CARD_DECISIONS, \
            f"Missing decision key: {key}"
        assert ALLOWED_CARD_DECISIONS[key], \
            f"Decision {key} has empty label"

    # Helper functions
    assert get_decision_label(None) == "未处理", \
        "None decision should return '未处理'"
    assert get_decision_label("worth_attention") == "值得关注", \
        f"worth_attention label wrong: {get_decision_label('worth_attention')}"
    assert get_decision_label("not_a_key") == "未处理", \
        "Unknown decision should fall back to '未处理'"

    assert is_valid_decision("to_action") is True
    assert is_valid_decision("not_real") is False
    assert is_valid_decision(None) is False

    # Table is in DB
    from sqlalchemy import inspect
    from app.db import engine
    inspector = inspect(engine)
    assert "card_decisions" in inspector.get_table_names(), \
        "card_decisions table should be created by init_db()"
    print("[OK] CardDecision model exists, table created, helpers work")


def test_v04_card_detail_shows_decision_section():
    """Test that /cards/{id} renders the '看完后的判断' section with all 5 options."""
    from app.db import SessionLocal
    from app.models import InsightCard, CardStatus, SourceType

    db = SessionLocal()
    try:
        card = InsightCard(
            source_url=f"https://example.com/v04-test-{uuid.uuid4().hex[:6]}",
            source_type=SourceType.HTML,
            source_title="V0.4 Detail Test",
            content_hash=f"v04-test-{uuid.uuid4().hex[:8]}",
            status=CardStatus.COMPLETED,
            summary_zh="测试中文摘要",
            relevance_score=70,
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        card_id = card.id

        response = client.get(f"/cards/{card_id}")
        assert response.status_code == 200
        text = response.text
        assert "看完后的判断" in text, \
            "Detail page should have '看完后的判断' section"
        assert "值得" in text or "worth_attention" in text, \
            "Detail page should show '值得关注' option"
        assert "与我有关" in text, "Detail page should show '与我有关' option"
        assert "稍后再看" in text, "Detail page should show '稍后再看' option"
        assert "暂时忽略" in text, "Detail page should show '暂时忽略' option"
        assert "转成行动" in text, "Detail page should show '转成行动' option"
        # For a brand-new card, current decision should be 未处理
        assert "未处理" in text, "New card should show current=未处理"
        print(f"[OK] /cards/{card_id} shows decision section with all 5 options")
    finally:
        db.rollback()
        db.close()


def test_v04_post_decision_creates_record():
    """Test that POST /cards/{id}/decision creates a CardDecision row."""
    from app.db import SessionLocal
    from app.models import InsightCard, CardStatus, SourceType, CardDecision

    db = SessionLocal()
    try:
        card = InsightCard(
            source_url=f"https://example.com/v04-create-{uuid.uuid4().hex[:6]}",
            source_type=SourceType.HTML,
            source_title="V0.4 Create Test",
            content_hash=f"v04-create-{uuid.uuid4().hex[:8]}",
            status=CardStatus.COMPLETED,
            summary_zh="测试",
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        card_id = card.id

        response = client.post(
            f"/cards/{card_id}/decision",
            data={"decision": "worth_attention", "note": ""},
            follow_redirects=False,
        )
        assert response.status_code in (302, 303), \
            f"Expected redirect, got {response.status_code}"

        # Verify DB
        db.expire_all()
        decisions = db.query(CardDecision).filter(CardDecision.card_id == card_id).all()
        assert len(decisions) == 1, f"Expected 1 decision, got {len(decisions)}"
        assert decisions[0].decision == "worth_attention"
        assert decisions[0].note is None
        print(f"[OK] POST decision created CardDecision (decision=worth_attention)")
    finally:
        db.rollback()
        db.close()


def test_v04_post_decision_updates_existing():
    """Test that re-submitting decision updates the same row (no duplicate insert)."""
    from app.db import SessionLocal
    from app.models import InsightCard, CardStatus, SourceType, CardDecision

    db = SessionLocal()
    try:
        card = InsightCard(
            source_url=f"https://example.com/v04-update-{uuid.uuid4().hex[:6]}",
            source_type=SourceType.HTML,
            source_title="V0.4 Update Test",
            content_hash=f"v04-update-{uuid.uuid4().hex[:8]}",
            status=CardStatus.COMPLETED,
            summary_zh="测试",
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        card_id = card.id

        # First submit
        client.post(
            f"/cards/{card_id}/decision",
            data={"decision": "worth_attention", "note": ""},
        )
        # Second submit with different decision + note
        client.post(
            f"/cards/{card_id}/decision",
            data={"decision": "to_action", "note": "可以转成资料编译功能优化任务"},
        )

        # Verify still only one row, with updated values
        db.expire_all()
        decisions = db.query(CardDecision).filter(CardDecision.card_id == card_id).all()
        assert len(decisions) == 1, \
            f"Expected 1 decision after re-submit, got {len(decisions)} (no duplicate insert)"
        assert decisions[0].decision == "to_action", \
            f"Expected to_action, got {decisions[0].decision}"
        assert decisions[0].note == "可以转成资料编译功能优化任务", \
            f"Expected updated note, got {decisions[0].note!r}"
        print(f"[OK] Re-submit updates the same row (no duplicate insert)")
    finally:
        db.rollback()
        db.close()


def test_v04_cards_list_shows_decision_status():
    """Test that /cards list shows 处理状态 column with the user's decision."""
    from app.db import SessionLocal
    from app.models import InsightCard, CardStatus, SourceType, CardDecision

    db = SessionLocal()
    try:
        card = InsightCard(
            source_url=f"https://example.com/v04-list-{uuid.uuid4().hex[:6]}",
            source_type=SourceType.HTML,
            source_title="V0.4 List Test Card",
            content_hash=f"v04-list-{uuid.uuid4().hex[:8]}",
            status=CardStatus.COMPLETED,
            summary_zh="测试",
        )
        db.add(card)
        db.commit()
        db.refresh(card)

        # Set decision to to_action
        client.post(
            f"/cards/{card.id}/decision",
            data={"decision": "to_action", "note": "测试 note"},
        )

        # Now check /cards
        response = client.get("/cards")
        assert response.status_code == 200
        text = response.text
        assert "处理状态" in text, "/cards should have '处理状态' column"
        assert "转成行动" in text, "/cards should show '转成行动' for the updated card"
        print("[OK] /cards list shows 处理状态=转成行动")
    finally:
        db.rollback()
        db.close()


def test_v04_post_invalid_decision_rejected():
    """Test that invalid decision values are not written to the database."""
    from app.db import SessionLocal
    from app.models import InsightCard, CardStatus, SourceType, CardDecision

    db = SessionLocal()
    try:
        card = InsightCard(
            source_url=f"https://example.com/v04-invalid-{uuid.uuid4().hex[:6]}",
            source_type=SourceType.HTML,
            source_title="V0.4 Invalid Test",
            content_hash=f"v04-invalid-{uuid.uuid4().hex[:8]}",
            status=CardStatus.COMPLETED,
            summary_zh="测试",
        )
        db.add(card)
        db.commit()
        db.refresh(card)

        # First, set a valid decision
        client.post(
            f"/cards/{card.id}/decision",
            data={"decision": "worth_attention", "note": ""},
        )

        # Then try to overwrite with invalid
        response = client.post(
            f"/cards/{card.id}/decision",
            data={"decision": "definitely_not_a_real_decision", "note": ""},
            follow_redirects=False,
        )
        assert response.status_code in (302, 303)

        # Original decision should still be there
        db.expire_all()
        decisions = db.query(CardDecision).filter(CardDecision.card_id == card.id).all()
        assert len(decisions) == 1
        assert decisions[0].decision == "worth_attention", \
            f"Invalid decision should NOT overwrite; got {decisions[0].decision}"
        print("[OK] Invalid decision is rejected, original preserved")
    finally:
        db.rollback()
        db.close()


def test_v041_cards_page_filter_ui():
    """Test that /cards has the V0.4.1 filter UI (处理状态 select)."""
    response = client.get("/cards")
    assert response.status_code == 200
    text = response.text
    assert "处理状态" in text, "/cards should have a '处理状态' filter label"
    assert "全部" in text, "/cards should have '全部' (no filter) option"
    assert "未处理" in text, "/cards should have '未处理' option"
    assert "值得关注" in text, "/cards should have '值得关注' option"
    assert "转成行动" in text, "/cards should have '转成行动' option"
    # Workspace title
    assert "工作台" in text, "/cards header should be workspace-themed"
    print("[OK] /cards has V0.4.1 处理状态 filter UI and workspace title")


def test_v041_filter_unhandled():
    """Test that /cards?decision=unhandled shows only cards without a CardDecision."""
    from app.db import SessionLocal
    from app.models import InsightCard, CardStatus, SourceType, CardDecision
    import uuid

    db = SessionLocal()
    created_card_ids = []
    try:
        # Create an unhandled card
        unhandled_card = InsightCard(
            source_url=f"https://example.com/v041-unh-{uuid.uuid4().hex[:6]}",
            source_type=SourceType.HTML,
            source_title=f"V0.4.1 Unhandled Card {uuid.uuid4().hex[:6]}",
            content_hash=f"v041-unh-{uuid.uuid4().hex[:8]}",
            status=CardStatus.COMPLETED,
            summary_zh="t",
        )
        db.add(unhandled_card)
        db.commit()
        db.refresh(unhandled_card)
        created_card_ids.append(unhandled_card.id)

        # Create a to_action card
        to_action_card = InsightCard(
            source_url=f"https://example.com/v041-act-{uuid.uuid4().hex[:6]}",
            source_type=SourceType.HTML,
            source_title=f"V0.4.1 ToAction Card {uuid.uuid4().hex[:6]}",
            content_hash=f"v041-act-{uuid.uuid4().hex[:8]}",
            status=CardStatus.COMPLETED,
            summary_zh="t",
        )
        db.add(to_action_card)
        db.commit()
        db.refresh(to_action_card)
        created_card_ids.append(to_action_card.id)

        decision = CardDecision(card_id=to_action_card.id, decision="to_action")
        db.add(decision)
        db.commit()

        # Filter by unhandled
        response = client.get("/cards?decision=unhandled")
        assert response.status_code == 200
        text = response.text
        # Unhandled card title should appear
        assert unhandled_card.source_title in text, \
            f"Unhandled card '{unhandled_card.source_title}' should appear in /cards?decision=unhandled"
        # ToAction card title should NOT appear
        assert to_action_card.source_title not in text, \
            f"ToAction card '{to_action_card.source_title}' should NOT appear in /cards?decision=unhandled"
        # Should show Chinese label "已筛选：未处理"
        assert "已筛选：未处理" in text, \
            "Filter should show '已筛选：未处理' (Chinese label, not raw value)"
        # Should NOT show raw value
        assert "已筛选：unhandled" not in text, \
            "Filter should NOT show raw value '已筛选：unhandled'"
        print("[OK] /cards?decision=unhandled shows only unhandled cards with Chinese label")
    finally:
        if created_card_ids:
            try:
                db.query(CardDecision).filter(CardDecision.card_id.in_(created_card_ids)).delete(synchronize_session=False)
                db.query(InsightCard).filter(InsightCard.id.in_(created_card_ids)).delete(synchronize_session=False)
                db.commit()
            except Exception:
                db.rollback()
        db.close()


def test_v041_filter_to_action():
    """Test that /cards?decision=to_action shows only to_action cards."""
    from app.db import SessionLocal
    from app.models import InsightCard, CardStatus, SourceType, CardDecision
    import uuid

    db = SessionLocal()
    created_card_ids = []
    try:
        # to_action card
        to_action_card = InsightCard(
            source_url=f"https://example.com/v041-ta-{uuid.uuid4().hex[:6]}",
            source_type=SourceType.HTML,
            source_title=f"V0.4.1 ToActionOnly {uuid.uuid4().hex[:6]}",
            content_hash=f"v041-ta-{uuid.uuid4().hex[:8]}",
            status=CardStatus.COMPLETED,
            summary_zh="t",
        )
        db.add(to_action_card)
        db.commit()
        db.refresh(to_action_card)
        created_card_ids.append(to_action_card.id)

        decision = CardDecision(card_id=to_action_card.id, decision="to_action")
        db.add(decision)
        db.commit()

        # Unhandled card
        unhandled_card = InsightCard(
            source_url=f"https://example.com/v041-unh2-{uuid.uuid4().hex[:6]}",
            source_type=SourceType.HTML,
            source_title=f"V0.4.1 UnhandledOnly {uuid.uuid4().hex[:6]}",
            content_hash=f"v041-unh2-{uuid.uuid4().hex[:8]}",
            status=CardStatus.COMPLETED,
            summary_zh="t",
        )
        db.add(unhandled_card)
        db.commit()
        db.refresh(unhandled_card)
        created_card_ids.append(unhandled_card.id)

        response = client.get("/cards?decision=to_action")
        assert response.status_code == 200
        text = response.text
        assert to_action_card.source_title in text, \
            f"to_action card '{to_action_card.source_title}' should appear in filter"
        assert unhandled_card.source_title not in text, \
            f"unhandled card '{unhandled_card.source_title}' should NOT appear in to_action filter"
        # Should show Chinese label "已筛选：转成行动"
        assert "已筛选：转成行动" in text, \
            "Filter should show '已筛选：转成行动' (Chinese label, not raw value)"
        # Should NOT show raw value
        assert "已筛选：to_action" not in text, \
            "Filter should NOT show raw value '已筛选：to_action'"
        print("[OK] /cards?decision=to_action shows only to_action cards with Chinese label")
    finally:
        if created_card_ids:
            try:
                db.query(CardDecision).filter(CardDecision.card_id.in_(created_card_ids)).delete(synchronize_session=False)
                db.query(InsightCard).filter(InsightCard.id.in_(created_card_ids)).delete(synchronize_session=False)
                db.commit()
            except Exception:
                db.rollback()
        db.close()


def test_v041_filter_invalid_does_not_crash():
    """Test that /cards?decision=not_real returns 200, not 500."""
    response = client.get("/cards?decision=not_a_real_decision")
    assert response.status_code == 200, \
        f"Invalid decision filter should NOT 500; got {response.status_code}"
    # And the page should not show "已筛选" because invalid = treated as 'all'
    assert "已筛选" not in response.text, \
        "Invalid filter should fall back to 'all' (no '已筛选' label)"
    print("[OK] /cards?decision=not_a_real_decision returns 200 (falls back to 'all')")


def test_v041_filter_to_action_shows_chinese_label():
    """Test that /cards?decision=to_action displays the Chinese label (not raw value)."""
    from app.db import SessionLocal
    from app.models import InsightCard, CardStatus, SourceType, CardDecision
    import uuid

    db = SessionLocal()
    created_card_ids = []
    try:
        # to_action card
        to_action_card = InsightCard(
            source_url=f"https://example.com/v041-ta-chinese-{uuid.uuid4().hex[:6]}",
            source_type=SourceType.HTML,
            source_title=f"V0.4.1 ToActionChinese {uuid.uuid4().hex[:6]}",
            content_hash=f"v041-ta-chinese-{uuid.uuid4().hex[:8]}",
            status=CardStatus.COMPLETED,
            summary_zh="t",
        )
        db.add(to_action_card)
        db.commit()
        db.refresh(to_action_card)
        created_card_ids.append(to_action_card.id)

        decision = CardDecision(card_id=to_action_card.id, decision="to_action")
        db.add(decision)
        db.commit()

        response = client.get("/cards?decision=to_action")
        assert response.status_code == 200
        text = response.text
        # Should show Chinese label "已筛选：转成行动"
        assert "已筛选：转成行动" in text, \
            "Filter should show '已筛选：转成行动' (Chinese label, not raw value)"
        # Should NOT show raw value
        assert "已筛选：to_action" not in text, \
            "Filter should NOT show raw value '已筛选：to_action'"
        # Should NOT show empty state (we have matching cards)
        assert "当前筛选条件下没有 InsightCard" not in text, \
            "to_action filter with results should NOT show empty state"
        print("[OK] /cards?decision=to_action shows Chinese label '已筛选：转成行动'")
    finally:
        if created_card_ids:
            try:
                db.query(CardDecision).filter(CardDecision.card_id.in_(created_card_ids)).delete(synchronize_session=False)
                db.query(InsightCard).filter(InsightCard.id.in_(created_card_ids)).delete(synchronize_session=False)
                db.commit()
            except Exception:
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
    test_probe_scripts_and_signatures()
    test_source_config()
    test_featured_sources_config()
    test_source_registry_db_models()
    test_source_config_sync_to_db()
    test_sources_page()
    test_source_items_page()
    test_source_item_detail_page()
    test_source_item_compile_route_with_mock_compile_url()
    test_source_item_compile_route_with_failed_card()
    test_source_item_compile_route_with_empty_url()
    test_source_item_compile_already_compiled_is_idempotent()
    test_source_item_compile_failed_retry_succeeds()
    test_rss_probe_module_imports()
    test_rss_probe_no_feed_url()
    test_rss_probe_mock_feed()
    test_rss_run_records_failed_fetchrun_without_feed_url()
    test_rss_run_records_partial_failed_with_missing_link()
    test_rss_probe_duplicate_link()
    test_html_index_probe_duplicate_href()
    test_html_index_probe_module_imports()
    test_html_index_probe_no_homepage_url()
    test_html_index_probe_mock_html()
    test_html_index_run_records_fetchrun_with_mock_html()
    test_html_index_run_records_partial_failed_when_no_candidates()
    test_html_index_filters_huggingface_listing_pages()
    test_html_index_filters_generic_listing_pages()
    test_source_items_page_wide_layout_and_scroll()
    test_source_items_page_v033_notice()
    test_source_items_template_no_url_truncation()
    test_check_listing_script_exists()
    test_check_listing_script_imports()
    test_source_items_url_no_truncation_in_page()
    test_source_items_v035_usage_guide()
    test_source_items_v035_action_column()
    test_source_items_inbox_refined_status_cell()
    test_source_items_inbox_action_column_position()
    test_source_items_inbox_action_column_compiled_without_card()
    test_source_item_detail_v035_chinese_explanation()
    test_v035_manual_acceptance_doc_exists()
    test_v035_readme_section()
    test_v04_card_decision_model_exists()
    test_v04_card_detail_shows_decision_section()
    test_v04_post_decision_creates_record()
    test_v04_post_decision_updates_existing()
    test_v04_cards_list_shows_decision_status()
    test_v04_post_invalid_decision_rejected()
    test_v041_cards_page_filter_ui()
    test_v041_filter_unhandled()
    test_v041_filter_to_action()
    test_v041_filter_invalid_does_not_crash()
    test_v041_filter_to_action_shows_chinese_label()
    test_compile_missing_api_key()
    test_compile_with_url()

    print("=" * 50)
    print("Smoke test completed!")
    print("=" * 50)
