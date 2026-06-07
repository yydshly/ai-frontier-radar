"""URL fetcher with retry and error handling."""
import httpx
from typing import Tuple, Optional

from app.config import HTTP_TIMEOUT_SECONDS, FETCH_RETRY_COUNT
from app.logging_config import get_logger

logger = get_logger(__name__)

# Default User-Agent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; AI-Frontier-Radar/0.1; +https://github.com/yydshly/ai-frontier-radar)"
)


def fetch_url(url: str) -> Tuple[bytes, str]:
    """
    Fetch URL content with retry logic.

    Returns:
        Tuple of (content_bytes, content_type)

    Raises:
        httpx.HTTPStatusError: On HTTP error
        httpx.TransportError: On connection error
        Exception: On other errors
    """
    content_type = "unknown"

    for attempt in range(FETCH_RETRY_COUNT + 1):
        try:
            with httpx.Client(
                timeout=HTTP_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={"User-Agent": DEFAULT_USER_AGENT},
            ) as client:
                response = client.get(url)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "unknown")
                # Strip charset from content-type if present
                if ";" in content_type:
                    content_type = content_type.split(";")[0].strip()

                # Size protection: limit to 50MB
                content = response.content[: 50 * 1024 * 1024]

                logger.info(f"Fetched {url} (type={content_type}, size={len(content)})")
                return content, content_type

        except httpx.HTTPStatusError as e:
            logger.warning(f"HTTP error {e.response.status_code} for {url}, attempt {attempt + 1}")
            if attempt == FETCH_RETRY_COUNT:
                raise

        except httpx.TransportError as e:
            logger.warning(f"Transport error for {url}, attempt {attempt + 1}: {e}")
            if attempt == FETCH_RETRY_COUNT:
                raise

    raise Exception(f"Failed to fetch {url} after {FETCH_RETRY_COUNT + 1} attempts")
