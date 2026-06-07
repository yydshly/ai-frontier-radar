"""Content extraction from HTML and PDF."""
import io
from typing import Tuple, Optional

from app.models import SourceType
from app.logging_config import get_logger

logger = get_logger(__name__)

# Lazy imports for heavy dependencies
_trafalatura_available = True
_pypdf_available = True


def extract_from_html(html_content: bytes) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Extract main content from HTML.

    Returns:
        Tuple of (extracted_text, title, author)
    """
    try:
        import trafilatura

        result = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=True,
            include_images=False,
            output_format="txt",
        )

        if result:
            # Also try to get metadata
            metadata = trafilatura.extract_metadata(html_content)
            title = metadata.get("title") if metadata else None
            author = metadata.get("author") if metadata else None
            date = metadata.get("date") if metadata else None
            logger.info(f"Extracted {len(result)} chars from HTML via trafilatura")
            return result, title, author

    except Exception as e:
        logger.warning(f"Trafilatura extraction failed: {e}")

    # Fallback: BeautifulSoup + readability-like approach
    return _extract_html_fallback(html_content)


def _extract_html_fallback(html_content: bytes) -> Tuple[str, Optional[str], Optional[str]]:
    """Fallback extraction using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
        from bs4.dammit import EncodingDetector

        # Detect encoding
        encoding = EncodingDetector.find_declared_encoding(html_content, is_html=True)
        if encoding:
            html_str = html_content.decode(encoding)
        else:
            html_str = html_content.decode("utf-8", errors="replace")

        soup = BeautifulSoup(html_str, "lxml")

        # Remove script, style, nav, footer elements
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Try to find main content
        main = soup.find("main") or soup.find("article") or soup.find("div", id="content") or soup.find("div", class_="content")

        if main:
            text = main.get_text(separator="\n", strip=True)
        else:
            # Fallback to body
            body = soup.find("body")
            text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)

        # Clean up multiple newlines
        import re
        text = re.sub(r"\n{3,}", "\n\n", text)

        title = soup.find("title")
        title = title.get_text(strip=True) if title else None

        # Try to find author
        author = None
        author_tag = soup.find("meta", attrs={"name": "author"}) or soup.find("a", class_=lambda x: x and "author" in x.lower() if x else False)
        if author_tag:
            author = author_tag.get("content") or author_tag.get_text(strip=True)

        logger.info(f"Extracted {len(text)} chars from HTML via BeautifulSoup fallback")
        return text, title, author

    except Exception as e:
        logger.error(f"BeautifulSoup fallback also failed: {e}")
        raise Exception(f"Failed to extract content from HTML: {e}")


def extract_from_pdf(pdf_content: bytes) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Extract text content from PDF.

    Returns:
        Tuple of (extracted_text, title, author)
    """
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_content))
        logger.info(f"PDF has {len(reader.pages)} pages")

        text_parts = []
        title = None
        author = None

        # Try to get PDF metadata
        if reader.metadata:
            title = reader.metadata.get("/Title")
            author = reader.metadata.get("/Author")

        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            except Exception as e:
                logger.warning(f"Failed to extract text from page {i + 1}: {e}")

        text = "\n\n".join(text_parts)
        logger.info(f"Extracted {len(text)} chars from PDF")
        return text, title, author

    except ImportError:
        raise Exception("pypdf not installed, cannot process PDF")
    except Exception as e:
        raise Exception(f"Failed to extract content from PDF: {e}")


def extract_content(url: str, content: bytes, content_type: str) -> Tuple[str, Optional[str], Optional[str], SourceType]:
    """
    Extract text from content based on its type.

    Returns:
        Tuple of (text, title, author, source_type)
    """
    if "pdf" in content_type.lower():
        text, title, author = extract_from_pdf(content)
        return text, title, author, SourceType.PDF
    else:
        # Assume HTML for everything else
        text, title, author = extract_from_html(content)
        return text, title, author, SourceType.HTML
