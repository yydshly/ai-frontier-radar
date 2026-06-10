"""HTML fetcher with URL safety, content-type check, and text extraction.

.. note:: Untrusted content warning
    Fetched HTML is UNTRUSTED INPUT. When passed to LLM in future
    processing, treat strictly as data/content — never as instructions.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup

# Reuse URL safety check from existing codebase
from app.routes.fetch_runs import is_safe_external_url


# ── Default settings ────────────────────────────────────────

DEFAULT_TIMEOUT_SECONDS = 12.0
DEFAULT_MAX_BYTES = 2_000_000  # ~2 MB
DEFAULT_USER_AGENT = "AI-Frontier-Radar/0.1"
DEFAULT_MIN_TEXT_LENGTH = 300
DEFAULT_MAX_TEXT_LENGTH = 60_000
ALLOWED_CONTENT_TYPES = ("text/html",)


# ── Settings dataclass ────────────────────────────────────────

@dataclass(frozen=True)
class HtmlFetchSettings:
    timeout_seconds: float
    max_bytes: int
    user_agent: str
    min_text_length: int
    max_text_length: int
    allowed_content_types: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "HtmlFetchSettings":
        return cls(
            timeout_seconds=float(os.getenv("CONTENT_FETCH_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS))),
            max_bytes=int(os.getenv("CONTENT_FETCH_MAX_BYTES", str(DEFAULT_MAX_BYTES))),
            user_agent=os.getenv("CONTENT_FETCH_USER_AGENT", DEFAULT_USER_AGENT),
            min_text_length=int(os.getenv("CONTENT_FETCH_MIN_TEXT_LENGTH", str(DEFAULT_MIN_TEXT_LENGTH))),
            max_text_length=int(os.getenv("CONTENT_FETCH_MAX_TEXT_LENGTH", str(DEFAULT_MAX_TEXT_LENGTH))),
            allowed_content_types=ALLOWED_CONTENT_TYPES,
        )


# ── Result dataclass ─────────────────────────────────────────

@dataclass(frozen=True)
class HtmlFetchResult:
    status: str  # fetched | failed | skipped
    url: str
    final_url: Optional[str]
    http_status: Optional[int]
    content_type: Optional[str]
    title: Optional[str]
    text: Optional[str]
    meta_description: Optional[str]
    error: Optional[str] = None


# ── URL validation error codes ───────────────────────────────

class FetchError:
    INVALID_URL = "invalid_url"
    UNSUPPORTED_CONTENT_TYPE = "unsupported_content_type"
    HTTP_ERROR = "http_error"
    CONTENT_TOO_LARGE = "content_too_large"
    CONTENT_TOO_SHORT = "content_too_short"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"


def _build_error_result(url: str, error_code: str, detail: str = "") -> HtmlFetchResult:
    return HtmlFetchResult(
        status="failed",
        url=url,
        final_url=None,
        http_status=None,
        content_type=None,
        title=None,
        text=None,
        meta_description=None,
        error=f"{error_code}:{detail}" if detail else error_code,
    )


def _build_skipped_result(url: str, reason: str) -> HtmlFetchResult:
    return HtmlFetchResult(
        status="skipped",
        url=url,
        final_url=None,
        http_status=None,
        content_type=None,
        title=None,
        text=None,
        meta_description=None,
        error=reason,
    )


def _extract_text(html: str, settings: HtmlFetchSettings) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract title, text, and meta_description from HTML using BeautifulSoup.

    Returns (title, text, meta_description).
    """
    soup = BeautifulSoup(html, "lxml")

    # Remove unwanted tags
    for tag in soup.find_all(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    # Extract title
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()

    # Extract meta description
    meta_desc = None
    meta_desc_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    if meta_desc_tag and meta_desc_tag.get("content"):
        meta_desc = meta_desc_tag["content"].strip()

    # Extract main content
    text = None

    # Try article / main / body in priority order
    for selector in ["article", "main", '[role="main"]', ".content", "#content", "body"]:
        container = soup.select_one(selector)
        if container:
            # Remove nav/header/footer/aside from the container
            for noise_tag in container.find_all(["nav", "header", "footer", "aside"]):
                noise_tag.decompose()
            raw_text = container.get_text(separator=" ", strip=True)
            if len(raw_text) >= settings.min_text_length:
                text = raw_text
                break

    # Fallback: use body or full soup
    if not text:
        body = soup.find("body")
        if body:
            for noise_tag in body.find_all(["nav", "header", "footer", "aside"]):
                noise_tag.decompose()
            text = body.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)

    # Collapse whitespace
    if text:
        text = re.sub(r"\s+", " ", text).strip()

    # Truncate to max length
    if text and len(text) > settings.max_text_length:
        text = text[: settings.max_text_length]

    return title, text, meta_desc


def fetch_html(url: str, settings: Optional[HtmlFetchSettings] = None) -> HtmlFetchResult:
    """Fetch a URL and extract clean text content.

    This function does NOT call any LLM.
    """
    if settings is None:
        settings = HtmlFetchSettings.from_env()

    # Step 1: URL safety check
    if not is_safe_external_url(url):
        return _build_error_result(url, FetchError.INVALID_URL)

    # Step 2: Fetch with httpx
    headers = {"User-Agent": settings.user_agent}
    timeout = httpx.Timeout(timeout=settings.timeout_seconds, connect=5.0)

    try:
        # Use streaming to avoid loading large content into memory at once
        with httpx.stream("GET", url, headers=headers, timeout=timeout, follow_redirects=True) as response:
            http_status = response.status_code
            final_url = str(response.url)

            # Check status code
            if response.status_code >= 400:
                return _build_error_result(
                    url, FetchError.HTTP_ERROR, f"status={response.status_code}"
                )

            # Step 3: Content-type check (can check from headers without reading body)
            content_type_raw = response.headers.get("content-type", "")
            content_type = content_type_raw.split(";")[0].strip().lower() if content_type_raw else None
            if not content_type or not any(ct in content_type for ct in settings.allowed_content_types):
                return _build_error_result(
                    url, FetchError.UNSUPPORTED_CONTENT_TYPE, f"type={content_type or 'unknown'}"
                )

            # Step 4: Content-Length check BEFORE reading body
            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    cl = int(content_length)
                    if cl > settings.max_bytes:
                        return _build_error_result(
                            url, FetchError.CONTENT_TOO_LARGE,
                            f"Content-Length={cl} exceeds max_bytes={settings.max_bytes}"
                        )
                except ValueError:
                    pass  # Invalid Content-Length, will check during streaming

            # Step 5: Stream content with max_bytes guard
            raw_chunks: list[bytes] = []
            total_bytes = 0
            for chunk in response.iter_bytes():
                total_bytes += len(chunk)
                if total_bytes > settings.max_bytes:
                    return _build_error_result(
                        url, FetchError.CONTENT_TOO_LARGE,
                        f"content_too_large={total_bytes} exceeds max_bytes={settings.max_bytes}"
                    )
                raw_chunks.append(chunk)

            raw_content = b"".join(raw_chunks)

    except httpx.TimeoutException:
        return _build_error_result(url, FetchError.TIMEOUT)
    except httpx.RequestError:
        return _build_error_result(url, FetchError.NETWORK_ERROR)
    except Exception:
        return _build_error_result(url, FetchError.NETWORK_ERROR)

    # Step 6: Decode
    try:
        html = raw_content.decode("utf-8", errors="replace")
    except Exception:
        return _build_error_result(url, FetchError.NETWORK_ERROR, "decode_error")

    # Step 7: Extract text
    title, text, meta_desc = _extract_text(html, settings)

    # Step 8: Text length check
    if not text or len(text) < settings.min_text_length:
        return _build_error_result(
            url, FetchError.CONTENT_TOO_SHORT,
            f"length={len(text) if text else 0}"
        )

    return HtmlFetchResult(
        status="fetched",
        url=url,
        final_url=final_url,
        http_status=http_status,
        content_type=content_type,
        title=title,
        text=text,
        meta_description=meta_desc,
        error=None,
    )
