"""JSON parsing and repair utilities."""
import json
from typing import Any

from app.logging_config import get_logger

logger = get_logger(__name__)


class JSONParseError(Exception):
    """Raised when JSON parsing fails."""
    pass


def strip_markdown_code_block(text: str) -> str:
    """Remove markdown code block wrapper from text."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def extract_json_object(text: str) -> str:
    """Extract the first JSON object from text."""
    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        return text[json_start:json_end]
    raise JSONParseError("No JSON object found in response")


def parse_json(text: str) -> dict[str, Any]:
    """Parse text as JSON, handling markdown blocks."""
    cleaned = strip_markdown_code_block(text)
    json_str = extract_json_object(cleaned)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise JSONParseError(f"JSON decode error: {e}")


def extract_text_from_anthropic_response(response_data: dict[str, Any]) -> str:
    """
    Extract text content from Anthropic Messages API response.

    Response may contain multiple content blocks of types:
    - text: text content to use
    - thinking: thinking content (should be ignored for JSON output)

    Returns:
        Concatenated text from all text-type blocks
    """
    text_parts = []

    try:
        content_blocks = response_data.get("content", [])
    except (KeyError, TypeError):
        content_blocks = []

    for block in content_blocks:
        if isinstance(block, dict):
            block_type = block.get("type", "")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "thinking":
                logger.debug("Ignoring thinking block in response")

    if not text_parts:
        raise JSONParseError("No text content block found in Anthropic response")

    return "\n".join(text_parts)


def parse_anthropic_json_response(response_data: dict[str, Any]) -> dict[str, Any]:
    """
    Parse Anthropic Messages API response into JSON dict.

    Handles:
    - Multiple content blocks (text, thinking)
    - Markdown code blocks in text
    - Missing or malformed JSON
    """
    text = extract_text_from_anthropic_response(response_data)
    return parse_json(text)


def parse_llm_response(content: str | dict[str, Any], provider: str = "generic") -> dict[str, Any]:
    """
    Parse LLM response content into structured dict.
    """
    if provider == "minimax" and isinstance(content, dict):
        return parse_anthropic_json_response(content)

    if isinstance(content, dict):
        if "content" in content:
            return parse_anthropic_json_response(content)
        return content

    return parse_json(content)
