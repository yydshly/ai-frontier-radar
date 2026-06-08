"""Project docs renderer - safe Markdown display.

Renders Markdown as HTML for display in the browser.
Security: strips all raw HTML and scripts, only renders safe text formatting.
"""
from html import escape
import re


def render_markdown(content: str) -> str:
    """Render Markdown as basic HTML for display.

    Security approach:
    - Strips all raw HTML tags completely
    - Removes script, style, iframe, form tags
    - Removes on* event handler patterns
    - Only renders safe Markdown: headings, bold, italic, code blocks, lists, links (text only)
    - No image loading, no external links (all links open in new tab)
    - All text content is HTML-escaped before insertion
    """
    # Step 0: Save code blocks BEFORE any HTML stripping so their content is pristine
    def encode_code_blocks(text: str) -> tuple[str, list[str]]:
        code_blocks: list[str] = []

        def replacer(match):
            code_blocks.append(match.group(0))
            return f"___CODEBLOCK_{len(code_blocks) - 1}___"

        text = re.sub(r"```[\s\S]*?```", replacer, text)
        text = re.sub(r"`[^`\n]+`", replacer, text)
        return text, code_blocks

    content, saved_code = encode_code_blocks(content)

    # Step 1: Remove raw HTML tags completely from non-code content
    html_pattern = re.compile(r"<[^>]+>", flags=re.IGNORECASE)
    content = html_pattern.sub("", content)

    # Step 2: Remove script/style/iframe/form tags (already gone but double-check)
    for tag in ["script", "style", "iframe", "form", "object", "embed"]:
        content = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", content, flags=re.IGNORECASE | re.DOTALL)

    # Step 3: Remove on* event handlers
    content = re.sub(r"\bon\w+\s*=", "", content, flags=re.IGNORECASE)

    # Step 4: Block-level elements (headers, hr, lists, blockquotes)
    lines = content.split("\n")
    result_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Headers
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            level = len(m.group(1))
            inner = escape(m.group(2).strip())
            result_lines.append(f"<h{level}>{inner}</h{level}>")
            continue

        # Horizontal rule
        if re.match(r"^---+$", stripped) or re.match(r"^\*\*\*+$", stripped):
            result_lines.append("<hr>")
            continue

        # Blockquote
        if stripped.startswith(">"):
            q = re.sub(r"^>\s*", "", stripped)
            result_lines.append(f"<blockquote>{escape(q)}</blockquote>")
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

    # Step 6: Inline formatting — escape content first
    content = re.sub(r"\*\*(.+?)\*\*", lambda m: f"<strong>{escape(m.group(1))}</strong>", content)
    content = re.sub(r"__(.+?)__", lambda m: f"<strong>{escape(m.group(1))}</strong>", content)
    content = re.sub(r"\*(.+?)\*", lambda m: f"<em>{escape(m.group(1))}</em>", content)
    content = re.sub(r"_(.+?)_", lambda m: f"<em>{escape(m.group(1))}</em>", content)

    # Restore placeholders before generating code block HTML
    content = _restore_placeholders(content)

    # Step 7: Code blocks restored with proper <pre><code> wrapping and escaping
    for i, block in enumerate(saved_code):
        if block.startswith("```"):
            # Fenced code block — extract content between fence lines
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
                html_block = f'<pre><code class="language-{escape(lang, quote=True)}">{escaped}</code></pre>'
            else:
                html_block = f"<pre><code>{escaped}</code></pre>"
        else:
            # Inline code — strip backticks and escape
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
            processed.append(f"<li>{escape(item)}</li>")
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
            processed.append(f"<li>{escape(m.group(1))}</li>")
        else:
            if in_ol:
                processed.append("</ol>")
                in_ol = False
            processed.append(line)
    if in_ol:
        processed.append("</ol>")
    content = "\n".join(processed)

    # Step 10: Links — convert to safe format (open in new tab, no scripts)
    def safe_link(m):
        # Group 1 = text (inside brackets), Group 2 = href (inside parens)
        text = m.group(1) if m.group(1) else ""
        href = m.group(2) if m.group(2) else ""
        safe_text = escape(text)
        href_lower = href.lower()
        if re.match(r"^(javascript:|data:|vbscript:)", href_lower):
            return safe_text
        safe_href = escape(href, quote=True)
        return f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer">{safe_text}</a>'

    content = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", safe_link, content)

    # Step 11: Wrap non-HTML lines in <p> tags
    html_tags = re.compile(
        r"^<(?:h[1-6]|ul|ol|li|blockquote|hr|div|p|pre|code|a|span|strong|em)",
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
            result.append(f"<p>{escape(stripped)}</p>")
    content = "\n".join(result)

    # Step 12: Final cleanup — remove any remaining dangerous patterns
    content = re.sub(r"\bon\w+\s*=", "", content, flags=re.IGNORECASE)

    return content


def render_readable_plain_text(content: str, max_lines: int = 200) -> str:
    """Render Markdown as plain readable text (no HTML).

    Useful for quick display. Strips formatting and returns clean text.
    """
    lines = content.split("\n")
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["...（内容过长，查看完整文档）"]
    return "\n".join(lines)
