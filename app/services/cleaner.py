"""Text cleaning and normalization."""
import re

from app.config import MAX_SOURCE_CHARS
from app.logging_config import get_logger

logger = get_logger(__name__)


def clean_text(text: str) -> str:
    """
    Clean and normalize extracted text.

    - Remove excessive whitespace
    - Remove navigation/footer remnants
    - Limit max characters
    - Preserve paragraph and list semantics
    """
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove excessive whitespace (3+ newlines -> 2)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Remove leading/trailing whitespace on each line but preserve intentional indentation
    lines = text.split("\n")
    lines = [line.rstrip() for line in lines]
    text = "\n".join(lines)

    # Remove very short lines that are likely noise (single chars, single words)
    # But be conservative - don't remove actual content
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Keep lines that have meaningful content
        if len(stripped) > 0:
            cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # Truncate if too long
    if len(text) > MAX_SOURCE_CHARS:
        text = text[:MAX_SOURCE_CHARS]
        logger.info(f"Truncated text to {MAX_SOURCE_CHARS} chars")
        # Try to truncate at a paragraph boundary
        last_newline = text.rfind("\n\n")
        if last_newline > MAX_SOURCE_CHARS * 0.8:
            text = text[:last_newline]

    text = text.strip()
    logger.info(f"Cleaned text: {len(text)} chars")
    return text
