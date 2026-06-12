"""URL fetcher with retry, redirect validation, and size limits."""
from urllib.parse import urljoin

import httpx

from app.config import FETCH_RETRY_COUNT, HTTP_TIMEOUT_SECONDS
from app.logging_config import get_logger
from app.url_safety import is_safe_external_url

logger = get_logger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; AI-Frontier-Radar/0.1; +https://github.com/yydshly/ai-frontier-radar)"
)
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_REDIRECTS = 5


def fetch_url(url: str) -> tuple[bytes, str]:
    """Fetch URL content without allowing private redirects or oversized bodies."""
    for attempt in range(FETCH_RETRY_COUNT + 1):
        try:
            current_url = url
            with httpx.Client(
                timeout=HTTP_TIMEOUT_SECONDS,
                follow_redirects=False,
                headers={"User-Agent": DEFAULT_USER_AGENT},
            ) as client:
                for redirect_count in range(MAX_REDIRECTS + 1):
                    if not is_safe_external_url(current_url):
                        raise ValueError(f"Unsafe external URL: {current_url}")

                    with client.stream("GET", current_url) as response:
                        if response.is_redirect:
                            location = response.headers.get("location")
                            if not location or redirect_count >= MAX_REDIRECTS:
                                raise httpx.TooManyRedirects(
                                    "Redirect limit exceeded",
                                    request=response.request,
                                )
                            current_url = urljoin(current_url, location)
                            continue

                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "unknown")
                        if ";" in content_type:
                            content_type = content_type.split(";")[0].strip()

                        content_length = response.headers.get("content-length")
                        if content_length:
                            try:
                                declared_size = int(content_length)
                            except ValueError:
                                declared_size = None
                            if declared_size is not None and declared_size > MAX_DOWNLOAD_BYTES:
                                raise ValueError("Response exceeds 50 MB limit")

                        chunks: list[bytes] = []
                        total_bytes = 0
                        for chunk in response.iter_bytes():
                            total_bytes += len(chunk)
                            if total_bytes > MAX_DOWNLOAD_BYTES:
                                raise ValueError("Response exceeds 50 MB limit")
                            chunks.append(chunk)

                        content = b"".join(chunks)
                        logger.info(
                            "Fetched %s (type=%s, size=%s)",
                            current_url,
                            content_type,
                            len(content),
                        )
                        return content, content_type

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "HTTP error %s for %s, attempt %s",
                exc.response.status_code,
                url,
                attempt + 1,
            )
            if attempt == FETCH_RETRY_COUNT:
                raise
        except httpx.TransportError as exc:
            logger.warning("Transport error for %s, attempt %s: %s", url, attempt + 1, exc)
            if attempt == FETCH_RETRY_COUNT:
                raise

    raise RuntimeError(f"Failed to fetch {url} after {FETCH_RETRY_COUNT + 1} attempts")
