from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _number(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def build_dashboard_data(
    out_dir: Path,
    summaries: list[dict[str, Any]],
    start: str,
    end: str,
    sitemap_results: list[dict[str, Any]] | None = None,
    inspection_results: list[dict[str, Any]] | None = None,
    submission_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a compact dashboard snapshot from collected Search Console evidence."""
    sitemap_results = sitemap_results or []
    inspection_results = inspection_results or []
    submission_history = submission_history or []
    properties: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    for summary in summaries:
        site = str(summary.get("property") or "")
        if not site:
            continue
        slug = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in site).strip("._-")[:90] or "property"
        current = _read(out_dir / f"{slug}-search-performance.json", [])
        historical = _read(out_dir / f"{slug}-historical-comparison.json", [])
        current_clicks = sum(_number(row, "clicks") for row in current)
        current_impressions = sum(_number(row, "impressions") for row in current)
        previous_clicks = sum(_number(row, "previous_clicks") for row in historical)
        previous_impressions = sum(_number(row, "previous_impressions") for row in historical)
        weighted_position = sum(_number(row, "position") * _number(row, "impressions") for row in current)
        position = weighted_position / current_impressions if current_impressions else None
        ctr = current_clicks / current_impressions if current_impressions else 0.0
        site_sitemaps = [item for item in sitemap_results if item.get("property") == site]
        site_inspections = [item for item in inspection_results if item.get("property") == site]
        sitemap_errors = sum(int(item.get("errors") or 0) for item in site_sitemaps)
        sitemap_fetch_errors = sum(1 for item in site_sitemaps if item.get("error"))
        sitemap_warnings = sum(int(item.get("warnings") or 0) for item in site_sitemaps)
        sitemap_submitted = sum(int(part.get("submitted") or 0) for item in site_sitemaps for part in item.get("contents", []))
        sitemap_indexed = sum(int(part.get("indexed") or 0) for item in site_sitemaps for part in item.get("contents", []))
        inspected = len([item for item in site_inspections if not item.get("error")])
        not_indexed = [item for item in site_inspections if not item.get("error") and item.get("status") == "FAIL"]
        inspection_errors = sum(1 for item in site_inspections if item.get("error"))
        if summary.get("error"):
            health = "access_error" if "403" in str(summary.get("error_message", "")) else "collection_error"
            events.append({"level": "error", "property": site, "message": summary.get("error_message") or summary.get("error")})
        elif sitemap_errors or sitemap_warnings or sitemap_fetch_errors or not_indexed or inspection_errors:
            health = "needs_attention"
        elif current_impressions or current_clicks:
            health = "healthy"
        else:
            health = "no_search_data"
        if sitemap_fetch_errors:
            events.append({"level": "error", "property": site, "message": f"{sitemap_fetch_errors} sitemap status requests failed"})
        if inspection_errors:
            events.append({"level": "error", "property": site, "message": f"{inspection_errors} URL inspection requests failed"})
        if sitemap_errors:
            events.append({"level": "error", "property": site, "message": f"{sitemap_errors} sitemap errors reported by Search Console"})
        if sitemap_warnings:
            events.append({"level": "warning", "property": site, "message": f"{sitemap_warnings} sitemap warnings reported by Search Console"})
        for item in not_indexed[:10]:
            events.append({"level": "warning", "property": site, "url": item.get("url"), "message": item.get("coverage_state") or item.get("status") or "Indexing issue"})
        host = site.replace("sc-domain:", "")
        if site.startswith("http"):
            host = urlparse(site).netloc
        properties.append({
            "property": site, "host": host,
            "permission_level": summary.get("permission_level", "unknown"),
            "health": health,
            "clicks": round(current_clicks, 2), "previous_clicks": round(previous_clicks, 2),
            "clicks_delta": round(current_clicks - previous_clicks, 2),
            "impressions": round(current_impressions, 2), "previous_impressions": round(previous_impressions, 2),
            "impressions_delta": round(current_impressions - previous_impressions, 2),
            "ctr": round(ctr, 6), "position": round(position, 2) if position is not None else None,
            "query_page_rows": len(current), "sitemaps": site_sitemaps,
            "sitemap_errors": sitemap_errors, "sitemap_warnings": sitemap_warnings, "sitemap_fetch_errors": sitemap_fetch_errors, "inspection_errors": inspection_errors,
            "sitemap_submitted_urls": sitemap_submitted, "sitemap_indexed_urls": sitemap_indexed,
            "inspected_urls": inspected, "not_indexed_urls": len(not_indexed),
            "indexing": site_inspections,
            "collection_error": summary.get("error_message") if summary.get("error") else None,
            "historical_error": summary.get("historical_error"),
        })

    performers = sorted((p for p in properties if p["query_page_rows"]), key=lambda p: (p["clicks"], p["impressions"]), reverse=True)
    gainers = sorted((p for p in properties if p["query_page_rows"]), key=lambda p: p["clicks_delta"], reverse=True)
    decliners = sorted((p for p in properties if p["query_page_rows"]), key=lambda p: p["clicks_delta"])
    previous_start = next((item.get("previous_start_date") for item in summaries if item.get("previous_start_date")), None)
    previous_end = next((item.get("previous_end_date") for item in summaries if item.get("previous_end_date")), None)
    return {
        "schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": {"start": start, "end": end},
        "comparison_period": {"start": previous_start, "end": previous_end},
        "summary": {
            "properties_discovered": len(summaries),
            "properties_collected": sum(1 for item in summaries if not item.get("error")),
            "properties_with_errors": sum(1 for item in summaries if item.get("error")),
            "clicks": round(sum(p["clicks"] for p in properties), 2),
            "previous_clicks": round(sum(p["previous_clicks"] for p in properties), 2),
            "impressions": round(sum(p["impressions"] for p in properties), 2),
            "previous_impressions": round(sum(p["previous_impressions"] for p in properties), 2),
            "sitemap_errors": sum(p["sitemap_errors"] for p in properties),
            "sitemap_warnings": sum(p["sitemap_warnings"] for p in properties),
            "sitemap_submitted_urls": sum(p["sitemap_submitted_urls"] for p in properties),
            "sitemap_indexed_urls": sum(p["sitemap_indexed_urls"] for p in properties),
            "inspected_urls": sum(p["inspected_urls"] for p in properties),
            "not_indexed_urls": sum(p["not_indexed_urls"] for p in properties),
        },
        "properties": properties, "best_performers": performers[:8],
        "biggest_gainers": gainers[:8], "biggest_decliners": decliners[:8],
        "events": sorted(events, key=lambda item: (0 if item["level"] == "error" else 1, item.get("property", "")))[:100],
        "submission_history": submission_history[-100:],
    }
