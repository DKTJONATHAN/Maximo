"""Historical Google Search Console query/page comparisons."""
from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def previous_window(start: str, end: str) -> tuple[str, str]:
    """Return the immediately preceding window with the same inclusive length."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError("start date must be on or before end date")
    days = (last - first).days + 1
    prior_end = first - timedelta(days=1)
    prior_start = prior_end - timedelta(days=days - 1)
    return prior_start.isoformat(), prior_end.isoformat()


def _metric(row: dict[str, Any], key: str) -> float:
    return float(row.get(key) or 0)


def compare_query_page_rows(
    current_rows: list[dict[str, Any]], previous_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Join exact query/page pairs and calculate directional period changes."""
    def index(rows: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            keys = row.get("keys") or []
            if len(keys) < 2:
                continue
            result[(str(keys[0]), str(keys[1]))] = row
        return result

    current, previous = index(current_rows), index(previous_rows)
    output: list[dict[str, Any]] = []
    for query, page in sorted(set(current) | set(previous)):
        now, before = current.get((query, page), {}), previous.get((query, page), {})
        clicks, old_clicks = _metric(now, "clicks"), _metric(before, "clicks")
        impressions, old_impressions = _metric(now, "impressions"), _metric(before, "impressions")
        ctr = _metric(now, "ctr") if now else 0.0
        old_ctr = _metric(before, "ctr") if before else 0.0
        position = _metric(now, "position") if now else 0.0
        old_position = _metric(before, "position") if before else 0.0
        output.append({
            "query": query, "page": page,
            "clicks": clicks, "previous_clicks": old_clicks,
            "clicks_delta": clicks - old_clicks,
            "impressions": impressions, "previous_impressions": old_impressions,
            "impressions_delta": impressions - old_impressions,
            "ctr": ctr, "previous_ctr": old_ctr, "ctr_delta": ctr - old_ctr,
            "position": position, "previous_position": old_position,
            # Positive means the average ranking position worsened.
            "position_delta": (position - old_position) if now and before else None,
            "newly_visible": bool(now) and not bool(before),
            "lost_visibility": bool(before) and not bool(now),
        })
    return output


def write_comparison_outputs(
    property_url: str,
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    out_dir: Path,
    slug: str,
) -> list[dict[str, Any]]:
    rows = compare_query_page_rows(current_rows, previous_rows)
    for row in rows:
        row["property"] = property_url
    json_path = out_dir / f"{slug}-historical-comparison.json"
    json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    csv_path = out_dir / f"{slug}-historical-comparison.csv"
    fields = list(rows[0]) if rows else [
        "property", "query", "page", "clicks", "previous_clicks", "clicks_delta",
        "impressions", "previous_impressions", "impressions_delta", "ctr",
        "previous_ctr", "ctr_delta", "position", "previous_position",
        "position_delta", "newly_visible", "lost_visibility",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows
