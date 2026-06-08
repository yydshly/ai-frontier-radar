"""SourceItem URL quality classification — path-based content type checking.

Does NOT call LLM, does NOT make network requests.
"""
from urllib.parse import urlparse


# Paths that are listing/index pages for any source
_GENERIC_LISTING_PATHS = {
    "blog", "news", "research", "articles", "posts",
    "announcements", "updates", "reports",
}

# Query params that indicate listing/pagination
_LISTING_QUERY_PARAMS = {
    "p", "page", "paged", "offset", "start",
    "sort", "filter",
    "tag", "tags", "category", "search",
    "q", "author", "topic",
}

# Source-specific expected content path rules
# Format: source_key -> {allowed_paths: set, denied_paths: set}
_SOURCE_PATH_RULES = {
    "anthropic_news": {
        "allowed_paths": {"/news/"},
        "denied_paths": {"/", "/company", "/careers", "/pricing", "/about", "/research"},
    },
    "deepmind_blog": {
        "allowed_paths": {
            "/discover/blog/",
            "/discover/research/",
            "/blog/",
            "/research/",
        },
        "denied_paths": {
            "/models/",
            "/technologies/",
            "/about/",
            "/careers/",
            "/events/",
        },
    },
    "mistral_ai_news": {
        "allowed_paths": {"/news/"},
        "denied_paths": {"/", "/technology", "/products", "/company", "/careers"},
    },
    "huggingface_blog": {
        "allowed_paths": {"/blog/"},
        "denied_paths": set(),
    },
}


def is_suspected_listing_url(url: str, source_homepage_url: str | None = None) -> bool:
    """Check if URL is a suspected listing/pagination page.

    Args:
        url: Absolute URL to check.
        source_homepage_url: Homepage URL of the source (used for netloc check).

    Returns:
        True if URL appears to be a listing or pagination page.
    """
    parsed = urlparse(url)

    if source_homepage_url:
        source_parsed = urlparse(source_homepage_url)
        if parsed.netloc != source_parsed.netloc:
            return False

    path = parsed.path.lower().rstrip("/")

    if not path or path == "/":
        return False

    path_segments = [seg for seg in path.split("/") if seg]

    # Single segment that's a generic listing path
    if len(path_segments) == 1 and path_segments[0] in _GENERIC_LISTING_PATHS:
        return True

    if path in _GENERIC_LISTING_PATHS:
        return True

    # Has listing query params
    qs = parsed.query.lower()
    for param in _LISTING_QUERY_PARAMS:
        if param in qs:
            return True

    return False


def is_expected_content_url(source_key: str, url: str) -> bool:
    """Check if URL matches the expected content path for a given source.

    Args:
        source_key: The source identifier.
        url: Absolute URL to check.

    Returns:
        True if URL matches expected content path for the source.
        For unknown sources, returns True if not a listing URL.
    """
    parsed = urlparse(url)
    path = parsed.path.lower()

    rules = _SOURCE_PATH_RULES.get(source_key)

    if rules is None:
        # Unknown source: default to True if not listing
        return not is_suspected_listing_url(url)

    allowed = rules["allowed_paths"]
    denied = rules["denied_paths"]

    # Check if path matches any allowed prefix
    for allowed_prefix in allowed:
        if allowed_prefix in path:
            return True

    # Check if path matches any denied prefix
    for denied_prefix in denied:
        if denied_prefix in path:
            return False

    # For sources with specific rules but no match: only allow if path has 2+ segments
    # (e.g., /blog/slug is article, /blog is listing already filtered above)
    path_segments = [seg for seg in path.split("/") if seg]
    if len(path_segments) >= 2:
        return True

    return False


def classify_source_item_url(
    source_key: str,
    url: str,
    source_homepage_url: str | None = None,
) -> dict:
    """Classify a SourceItem URL by content quality.

    Args:
        source_key: The source identifier.
        url: Absolute URL of the SourceItem.
        source_homepage_url: Homepage URL of the source.

    Returns:
        dict with keys:
            - suspected_listing: bool
            - expected_content: bool
            - suspected_off_topic: bool
            - reason: str
    """
    suspected_listing = is_suspected_listing_url(url, source_homepage_url)

    if suspected_listing:
        return {
            "suspected_listing": True,
            "expected_content": False,
            "suspected_off_topic": False,
            "reason": "listing_page",
        }

    expected_content = is_expected_content_url(source_key, url)

    # suspected_off_topic = not a listing, but also not expected content
    suspected_off_topic = not expected_content

    if expected_content:
        reason = "expected_content"
    elif suspected_off_topic:
        # Give more specific reason based on source
        parsed = urlparse(url)
        path = parsed.path.lower()
        if source_key == "deepmind_blog" and "/models/" in path:
            reason = "deepmind_models_not_blog"
        elif source_key == "mistral_ai_news" and path == "/":
            reason = "mistral_homepage_not_news"
        else:
            reason = "off_topic_path"
    else:
        reason = "unknown"

    return {
        "suspected_listing": suspected_listing,
        "expected_content": expected_content,
        "suspected_off_topic": suspected_off_topic,
        "reason": reason,
    }
