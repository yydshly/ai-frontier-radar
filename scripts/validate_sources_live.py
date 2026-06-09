#!/usr/bin/env python3
"""Validate enabled sources by running real probes against an isolated DB."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WEAK_TITLE_PATTERNS = frozenset({
    "learn more",
    "featured",
    "read more",
    "more",
    "view",
    "explore",
    "see more",
    "continue reading",
    "details",
})


def is_weak_title(title: str | None) -> bool:
    """Return whether a title is empty or a weak CTA-like label."""
    if not title:
        return True
    normalized = " ".join(title.strip().split()).lower()
    return not normalized or normalized in WEAK_TITLE_PATTERNS


def title_coverage(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    return sum(1 for item in items if not is_weak_title(item.get("title"))) / len(items)


def summary_coverage(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    return sum(1 for item in items if item.get("summary") or item.get("description")) / len(items)


def published_coverage(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    return sum(1 for item in items if item.get("published_at")) / len(items)


def url_coverage(items: list[dict[str, Any]]) -> float:
    if not items:
        return 0.0
    return sum(1 for item in items if item.get("url")) / len(items)


def _suggestion_for_error(error_message: str) -> str:
    em = error_message.lower()
    if "404" in em:
        return "HTTP 404 -> 检查 homepage_url/feed_url 是否失效。"
    if "timeout" in em:
        return "Timeout -> 稍后重试或增大 timeout。"
    if "no candidate article links found" in em:
        return "No candidate article links found -> 页面结构可能变化，需要调整 html_index_probe URL 识别规则。"
    if "rss" in em and ("malformed" in em or "empty" in em):
        return "RSS malformed or empty -> RSS endpoint 可能不可用，考虑改为 html_index。"
    if "request failed" in em:
        return "Request failed -> 网络问题或来源不可达，稍后重试。"
    if "feed_url" in em or "homepage_url" in em:
        return "URL 配置缺失 -> 检查 feed_url/homepage_url。"
    return f"检查来源配置或网络错误：{error_message}"


def make_verdict(
    error_message: str | None,
    items_found: int,
    title_cov: float,
    summary_cov: float,
    published_cov: float,
    weak_count: int,
    source_item_count: int | None = None,
    url_cov: float = 1.0,
) -> tuple[str, str]:
    """Return PASS/WARN/FAIL and a concise suggestion."""
    count = items_found if source_item_count is None else source_item_count

    if error_message and items_found == 0:
        return "FAIL", _suggestion_for_error(error_message)
    if count == 0:
        return "FAIL", "SourceItem 数量为 0 -> 来源不可用或未发现候选内容。"

    if error_message:
        suggestion = _suggestion_for_error(error_message)
        em = error_message.lower()
        if (
            "404" in em
            or "timeout" in em
            or "request failed" in em
            or "no candidate article links found" in em
            or ("rss" in em and ("malformed" in em or "empty" in em))
        ):
            return "FAIL", suggestion
        return "WARN", suggestion

    if title_cov < 0.8:
        return "WARN", "非弱标题覆盖率低于 80% -> 检查详情页标题提取或运行 repair 脚本。"
    if url_cov < 0.8:
        return "FAIL", "URL 覆盖率低于 80% -> 检查候选链接提取。"
    if summary_cov < 0.5:
        return "WARN", "summary_coverage 低 -> 检查 detail_description / RSS summary 提取。"
    if published_cov < 0.5:
        return "WARN", "published_coverage 低 -> 检查 published_at 提取。"
    if weak_count > 0:
        return "WARN", "weak_title_count > 0 -> 检查详情页标题提取或运行 repair 脚本。"

    return "PASS", "Source is healthy."


def _select_config_path(config_path: str | None) -> Path:
    if config_path:
        return Path(config_path)
    primary = PROJECT_ROOT / "config" / "sources.yaml"
    fallback = PROJECT_ROOT / "config" / "sources.example.yaml"
    return primary if primary.exists() else fallback


def load_config(config_path: str | None) -> tuple[Path, dict[str, Any]]:
    import yaml

    path = _select_config_path(config_path)
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return path, data


def enabled_source_configs(config: dict[str, Any], source_key: str | None = None) -> list[tuple[str, dict[str, Any]]]:
    sources = config.get("sources") or {}
    if not isinstance(sources, dict):
        raise ValueError("config.sources must be a mapping")
    rows = [
        (key, value)
        for key, value in sources.items()
        if isinstance(value, dict) and value.get("enabled", False)
    ]
    if source_key:
        rows = [(key, value) for key, value in rows if key == source_key]
    return rows


def _create_source(db, source_key: str, cfg: dict[str, Any]):
    from app.models import Source

    source = Source(
        source_key=source_key,
        name=cfg.get("name") or source_key,
        description=cfg.get("description") or "",
        source_type=cfg.get("type") or cfg.get("source_type") or cfg.get("fetch_strategy") or "html_index",
        homepage_url=cfg.get("homepage_url"),
        feed_url=cfg.get("feed_url"),
        category=cfg.get("category") or "unknown",
        tags_json=json.dumps(cfg.get("tags") or [], ensure_ascii=False),
        enabled=bool(cfg.get("enabled", False)),
        fetch_strategy=cfg.get("fetch_strategy") or cfg.get("type") or "html_index",
        relevance_hint=cfg.get("relevance_hint") or "",
        fetch_interval_hours=int(cfg.get("fetch_interval_hours") or 24),
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def _items_for_source(db, source_key: str) -> list[dict[str, Any]]:
    from app.models import SourceItem

    rows = (
        db.query(SourceItem)
        .filter(SourceItem.source_key == source_key)
        .order_by(SourceItem.last_seen_at.desc(), SourceItem.id.desc())
        .all()
    )
    items: list[dict[str, Any]] = []
    for item in rows:
        raw: dict[str, Any] = {}
        if item.raw_metadata_json:
            try:
                raw = json.loads(item.raw_metadata_json)
            except json.JSONDecodeError:
                raw = {}
        items.append({
            "title": item.title,
            "url": item.url,
            "published_at": item.published_at,
            "summary": raw.get("summary") or raw.get("description"),
        })
    return items


def validate_source(db, source_key: str, cfg: dict[str, Any], timeout: int) -> dict[str, Any]:
    from app.application.sources.fetch_service import SourceFetchService

    source = _create_source(db, source_key, cfg)
    result = SourceFetchService(db).run_source(source_key, timeout_seconds=timeout)
    items = _items_for_source(db, source_key)

    title_cov = title_coverage(items)
    summary_cov = summary_coverage(items)
    published_cov = published_coverage(items)
    url_cov = url_coverage(items)
    weak_count = sum(1 for item in items if is_weak_title(item.get("title")))

    error_message = result.fetch_run.error_message if result else "source fetch returned no result"
    items_found = result.items_found if result else 0
    items_new = result.items_new if result else 0
    items_updated = result.items_updated if result else 0
    items_failed = result.items_failed if result else 0
    status = result.fetch_run.status if result else "failed"

    verdict, suggestion = make_verdict(
        error_message,
        items_found,
        title_cov,
        summary_cov,
        published_cov,
        weak_count,
        source_item_count=len(items),
        url_cov=url_cov,
    )

    return {
        "source_key": source_key,
        "name": source.name,
        "fetch_strategy": source.fetch_strategy,
        "homepage_url": source.homepage_url,
        "feed_url": source.feed_url,
        "status": status,
        "items_found": items_found,
        "items_new": items_new,
        "items_updated": items_updated,
        "items_failed": items_failed,
        "source_item_count": len(items),
        "error_message": error_message,
        "title_coverage": round(title_cov, 3),
        "summary_coverage": round(summary_cov, 3),
        "published_coverage": round(published_cov, 3),
        "url_coverage": round(url_cov, 3),
        "weak_title_count": weak_count,
        "sample_titles": [item["title"] for item in items[:5] if item.get("title")],
        "sample_urls": [item["url"] for item in items[:5] if item.get("url")],
        "verdict": verdict,
        "suggestion": suggestion,
    }


def build_markdown(results: list[dict[str, Any]], total: int, passed: int, warned: int, failed: int) -> str:
    lines = [
        "# AI Frontier Radar Live Source Validation Report",
        "",
        f"- Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        f"- Total sources: {total}",
        f"- PASS: {passed}",
        f"- WARN: {warned}",
        f"- FAIL: {failed}",
        "",
    ]

    for r in results:
        lines.extend([
            f"## {r['verdict']} {r['source_key']}",
            "",
            f"- name: {r['name']}",
            f"- strategy: {r['fetch_strategy']}",
            f"- verdict: {r['verdict']}",
            f"- items_found: {r['items_found']}",
            f"- title coverage: {r['title_coverage']:.0%}",
            f"- summary coverage: {r['summary_coverage']:.0%}",
            f"- published coverage: {r['published_coverage']:.0%}",
            f"- weak title count: {r['weak_title_count']}",
            f"- error_message: {r['error_message'] or '-'}",
            "- sample titles:",
        ])
        lines.extend([f"  - {title}" for title in r.get("sample_titles", [])[:3]] or ["  - -"])
        lines.append("- sample urls:")
        lines.extend([f"  - {url}" for url in r.get("sample_urls", [])[:3]] or ["  - -"])
        lines.extend([f"- suggestion: {r['suggestion']}", ""])

    return "\n".join(lines)


def _write_reports(out_dir: Path, timestamp: str, config_path: Path, results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    warned = sum(1 for r in results if r["verdict"] == "WARN")
    failed = sum(1 for r in results if r["verdict"] == "FAIL")
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "config_path": str(config_path),
        "total": len(results),
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "results": results,
    }

    latest_json = out_dir / "source_validation_latest.json"
    latest_md = out_dir / "source_validation_latest.md"
    timestamp_json = out_dir / f"source_validation_{timestamp}.json"
    timestamp_md = out_dir / f"source_validation_{timestamp}.md"

    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    md_text = build_markdown(results, len(results), passed, warned, failed)
    for path in (latest_json, timestamp_json):
        path.write_text(json_text, encoding="utf-8")
    for path in (latest_md, timestamp_md):
        path.write_text(md_text, encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate enabled live sources with real probes.")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--source-key", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--keep-db", action="store_true")
    args = parser.parse_args()

    config_path, config = load_config(args.config)
    sources = enabled_source_configs(config, args.source_key)
    if args.source_key and not sources:
        print(f"[ERROR] Enabled source not found: {args.source_key}")
        return 1

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_dir = PROJECT_ROOT / "data" / "source_validation"
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / f"source_validation_{timestamp}.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from app.db import SessionLocal, engine, init_db

    init_db()
    db = SessionLocal()
    results: list[dict[str, Any]] = []

    print(f"Config: {config_path}")
    print(f"Isolated DB: {db_path}")
    print(f"Validating {len(sources)} enabled source(s)")

    try:
        for source_key, cfg in sources:
            print(f"- {source_key} ... ", end="", flush=True)
            result = validate_source(db, source_key, cfg, args.timeout)
            results.append(result)
            print(f"{result['verdict']} ({result['items_found']} found)")
    finally:
        db.close()

    report = _write_reports(out_dir, timestamp, config_path, results)
    print(
        f"Done: total={report['total']} PASS={report['passed']} "
        f"WARN={report['warned']} FAIL={report['failed']}"
    )
    print(f"Reports: {out_dir / 'source_validation_latest.json'}")
    print(f"         {out_dir / 'source_validation_latest.md'}")

    if not args.keep_db:
        try:
            engine.dispose()
            db_path.unlink()
        except OSError as exc:
            print(f"[WARN] Could not delete isolated DB: {exc}")

    return 0 if report["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
