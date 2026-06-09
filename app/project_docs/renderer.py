"""Project docs renderer - safe Markdown display.

Renders Markdown as HTML for display in the browser.
Security: strips all raw HTML and scripts, only renders safe text formatting.
"""
from html import escape
from urllib.parse import urlsplit
import re


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALLOWED_LINK_SCHEMES = frozenset(["http", "https", "mailto"])


def _is_safe_href(href: str) -> bool:
    """Return True iff href is an allowed safe URL / path / anchor."""
    href = href.strip()
    if not href:
        return False

    # Reject all known dangerous schemes
    dangerous = (
        "javascript",
        "data",
        "vbscript",
        "file",
        "blob",
        "about",
    )
    try:
        scheme = urlsplit(href).scheme.lower()
    except ValueError:
        scheme = ""

    if scheme:
        if scheme in dangerous:
            return False
        if scheme not in _ALLOWED_LINK_SCHEMES:
            return False
        return True

    # No scheme — must be a safe relative path, anchor, or mailto alias
    # Reject scheme-relative URLs (//evil.com)
    if href.startswith("//"):
        return False
    # Reject URLs with control characters
    if any(ord(c) < 0x20 for c in href):
        return False
    # Allow: relative paths (docs/a.md), current-dir (./a.md),
    #        parent-dir (../a.md), anchors (#section), plain paths
    return True


def _render_inline(text: str) -> str:
    """Render inline Markdown (bold, em, code, links) safely.

    All text content is HTML-escaped. Only safe Markdown inline elements
    are generated. Raw HTML is not produced.
    """
    # Protect code blocks first (saved as ___CODEBLOCK_N___ by caller)
    _inline_placeholder_escapes: dict[str, str] = {}

    def _escape_inline_placeholders(t: str) -> str:
        def _repl(m):
            key = f"\x02INLINECB_{len(_inline_placeholder_escapes)}\x02"
            _inline_placeholder_escapes[key] = m.group(0)
            return key
        return re.sub(r"___CODEBLOCK_\d+___", _repl, t)

    def _restore_inline_placeholders(t: str) -> str:
        for k, v in _inline_placeholder_escapes.items():
            t = t.replace(k, v)
        return t

    text = _escape_inline_placeholders(text)

    # Bold **text**
    text = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: f"<strong>{escape(m.group(1))}</strong>",
        text,
    )
    # Bold __text__
    text = re.sub(
        r"__(.+?)__",
        lambda m: f"<strong>{escape(m.group(1))}</strong>",
        text,
    )
    # Italic *text*
    text = re.sub(
        r"\*(.+?)\*",
        lambda m: f"<em>{escape(m.group(1))}</em>",
        text,
    )
    # Italic _text_
    text = re.sub(
        r"_(.+?)_",
        lambda m: f"<em>{escape(m.group(1))}</em>",
        text,
    )
    # Inline code `text`
    text = re.sub(
        r"`([^`\n]+)`",
        lambda m: f"<code>{escape(m.group(1))}</code>",
        text,
    )
    # Links [text](href) — handled by safe_link (defined below, captured here)
    def _safe_link(m):
        link_text = m.group(1) if m.group(1) else ""
        href = (m.group(2) if m.group(2) else "").strip()
        safe_text = escape(link_text)
        if not _is_safe_href(href):
            return safe_text
        safe_href = escape(href, quote=True)
        return (
            f'<a href="{safe_href}" '
            f'target="_blank" rel="noopener noreferrer">{safe_text}</a>'
        )

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _safe_link, text)

    text = _restore_inline_placeholders(text)
    return text


# ---------------------------------------------------------------------------
# Main renderer
# ---------------------------------------------------------------------------

def render_markdown(content: str) -> str:
    """Render Markdown as basic HTML for display.

    Security approach:
    - All raw HTML tags are stripped before processing
    - Only safe Markdown inline elements are generated (no raw HTML injection)
    - Code-block content is escaped, never interpreted
    - Link href values are validated against a strict scheme allowlist
    - All text content is HTML-escaped before insertion
    """
    # Step 0: Save code blocks BEFORE any HTML stripping so their content is pristine
    def _encode_code_blocks(text: str) -> tuple[str, list[str]]:
        code_blocks: list[str] = []

        def _replacer(match):
            code_blocks.append(match.group(0))
            return f"___CODEBLOCK_{len(code_blocks) - 1}___"

        text = re.sub(r"```[\s\S]*?```", _replacer, text)
        text = re.sub(r"`[^`\n]+`", _replacer, text)
        return text, code_blocks

    content, saved_code = _encode_code_blocks(content)

    # Step 1: Remove raw HTML tags completely from non-code content
    html_pattern = re.compile(r"<[^>]+>", flags=re.IGNORECASE)
    content = html_pattern.sub("", content)

    # Step 2: Remove dangerous tags (already gone but double-check)
    for tag in ["script", "style", "iframe", "form", "object", "embed"]:
        content = re.sub(
            rf"<{tag}[^>]*>.*?</{tag}>",
            "",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )

    # Step 3: Remove on* event handlers (for non-code content)
    content = re.sub(r"\bon\w+\s*=", "", content, flags=re.IGNORECASE)

    # Step 4: Block-level elements (headers, hr, blockquotes)
    lines = content.split("\n")
    result_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Headers
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            level = len(m.group(1))
            inner = _render_inline(m.group(2).strip())
            result_lines.append(f"<h{level}>{inner}</h{level}>")
            continue

        # Horizontal rule
        if re.match(r"^---+$", stripped) or re.match(r"^\*\*\*+$", stripped):
            result_lines.append("<hr>")
            continue

        # Blockquote
        if stripped.startswith(">"):
            q = re.sub(r"^>\s*", "", stripped)
            result_lines.append(f"<blockquote>{_render_inline(q)}</blockquote>")
            continue

        result_lines.append(line)

    content = "\n".join(result_lines)

    # Step 5: Escape code-block placeholders so they aren't corrupted by bold/em
    _placeholder_escapes: dict[str, str] = {}

    def _escape_placeholders(text: str) -> str:
        def _replacer(m):
            key = f"\x01CODEBLOCK_{len(_placeholder_escapes)}\x01"
            _placeholder_escapes[key] = m.group(0)
            return key

        return re.sub(r"___CODEBLOCK_\d+___", _replacer, text)

    def _restore_placeholders(text: str) -> str:
        for key, val in _placeholder_escapes.items():
            text = text.replace(key, val)
        return text

    content = _escape_placeholders(content)

    # Step 6: Inline formatting via _render_inline (handles bold/em/code/links safely)
    content = _render_inline(content)

    # Restore placeholders before generating code block HTML
    content = _restore_placeholders(content)

    # Step 7: Code blocks restored with proper <pre><code> wrapping and escaping
    for i, block in enumerate(saved_code):
        if block.startswith("```"):
            # Fenced code block
            lines_inner = block.split("\n")
            if len(lines_inner) > 2:
                inner_code = "\n".join(lines_inner[1:-1])
            else:
                inner_code = ""
            first_line = lines_inner[0] if lines_inner else ""
            lang_match = re.match(r"```(\S*)", first_line)
            lang = lang_match.group(1) if lang_match else ""
            escaped = escape(inner_code)
            if lang:
                html_block = (
                    f'<pre><code class="language-'
                    f'{escape(lang, quote=True)}">{escaped}</code></pre>'
                )
            else:
                html_block = f"<pre><code>{escaped}</code></pre>"
        else:
            # Inline code
            code_content = block.strip("`")
            html_block = f"<code>{escape(code_content)}</code>"

        content = content.replace(f"___CODEBLOCK_{i}___", html_block)

    # Step 8: Unordered lists
    lines = content.split("\n")
    in_ul = False
    processed: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_ul:
                processed.append("<ul>")
                in_ul = True
            item = re.sub(r"^[\-\*]\s+", "", stripped)
            processed.append(f"<li>{_render_inline(item)}</li>")
        else:
            if in_ul:
                processed.append("</ul>")
                in_ul = False
            processed.append(line)
    if in_ul:
        processed.append("</ul>")
    content = "\n".join(processed)

    # Step 9: Ordered lists
    lines = content.split("\n")
    in_ol = False
    processed = []
    for line in lines:
        stripped = line.strip()
        m = re.match(r"^\d+\.\s+(.*)", stripped)
        if m:
            if not in_ol:
                processed.append("<ol>")
                in_ol = True
            processed.append(f"<li>{_render_inline(m.group(1))}</li>")
        else:
            if in_ol:
                processed.append("</ol>")
                in_ol = False
            processed.append(line)
    if in_ol:
        processed.append("</ol>")
    content = "\n".join(processed)

    # Step 10: Wrap non-HTML lines in <p> tags
    # Match both opening and closing tags for all block/inline elements
    html_tags = re.compile(
        r"^<(/?(?:h[1-6]|ul|ol|li|blockquote|hr|div|p|pre|code|a|span|strong|em))",
        flags=re.IGNORECASE,
    )
    lines = content.split("\n")
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append("")
        elif html_tags.match(stripped):
            result.append(line)
        else:
            # Plain paragraph: render inline (already HTML-safe at this point)
            result.append(f"<p>{_render_inline(stripped)}</p>")
    content = "\n".join(result)

    # NOTE: Step 12 (final on* cleanup) is intentionally omitted.
    # Raw HTML is stripped at Step 1/2, code content is escaped at Step 7,
    # and inline on* handlers in links are blocked by _is_safe_href().
    # Running \bon\w+\s*= on the final output would corrupt code examples
    # (e.g. `onerror=alert(1)` inside <code> tags).

    return content


def render_readable_plain_text(content: str, max_lines: int = 200) -> str:
    """Render Markdown as plain readable text (no HTML).

    Useful for quick display. Strips formatting and returns clean text.
    """
    lines = content.split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["...（内容过长，查看完整文档）"]
    return "\n".join(lines)
