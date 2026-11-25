from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

API_ROOT = "https://www.googleapis.com/webmasters/v3"
SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
DEFAULT_QUESTION_REGEX = (
    r"^(who|what|when|where|why|how|which|can|could|should|would|will|"
    r"do|does|did|is|are|was|were|has|have)\b"
)
PAGE_SIZE = 25_000
MAX_ROWS_PER_PROPERTY = 100_000
MIN_IMPRESSIONS = int(os.getenv("GSC_MIN_IMPRESSIONS") or "20")
QUESTION_RE = re.compile(os.getenv("GSC_QUESTION_REGEX") or DEFAULT_QUESTION_REGEX, re.I)


@dataclass
class Opportunity:
    property: str
    query: str
    page: str
    clicks: float
    impressions: float
    ctr: float
    average_position: float
    position_bucket: int
    baseline_ctr: float | None
    ctr_gap_percentage_points: float | None
    estimated_click_gap: float
    priority_score: float


def settled_window(start: str | None = None, end: str | None = None) -> tuple[str, str]:
    """Default to the latest 28-day window ending three days ago."""
    today = datetime.now(timezone.utc).date()
    end_day = date.fromisoformat(end) if end else today - timedelta(days=3)
    start_day = date.fromisoformat(start) if start else end_day - timedelta(days=27)
    if start_day > end_day:
        raise ValueError("start date must be on or before end date")
    if (end_day - start_day).days > 90:
        raise ValueError("date range cannot exceed 90 days")
    return start_day.isoformat(), end_day.isoformat()


def bucket(position: float) -> int:
    return max(1, min(100, int(position)))


def build_opportunities(property_url: str, rows: list[dict[str, Any]], minimum: int = MIN_IMPRESSIONS) -> list[Opportunity]:
    """Compare question-query CTR with same-property, same-window position buckets."""
    baseline: dict[int, list[float]] = {}
    for row in rows:
        b = bucket(float(row.get("position") or 100))
        totals = baseline.setdefault(b, [0.0, 0.0])
        totals[0] += float(row.get("clicks") or 0)
        totals[1] += float(row.get("impressions") or 0)

    output: list[Opportunity] = []
    for row in rows:
        keys = row.get("keys") or []
        if len(keys) < 2:
            continue
        query, page = str(keys[0]), str(keys[1])
        impressions = float(row.get("impressions") or 0)
        if impressions < minimum or not QUESTION_RE.search(query):
            continue
        clicks = float(row.get("clicks") or 0)
        ctr = float(row.get("ctr") if row.get("ctr") is not None else (clicks / impressions if impressions else 0))
        position = float(row.get("position") or 100)
        b = bucket(position)
        base_clicks, base_impressions = baseline.get(b, [0.0, 0.0])
        baseline_ctr = base_clicks / base_impressions if base_impressions else None
        gap = max(0.0, baseline_ctr - ctr) if baseline_ctr is not None else 0.0
        estimated_gap = gap * impressions
        score = estimated_gap * (1.0 + min(impressions, 1000) / 1000.0)
        output.append(Opportunity(
            property=property_url, query=query, page=page, clicks=clicks,
            impressions=impressions, ctr=ctr, average_position=position,
            position_bucket=b, baseline_ctr=baseline_ctr,
            ctr_gap_percentage_points=(gap * 100) if baseline_ctr is not None else None,
            estimated_click_gap=estimated_gap, priority_score=score,
        ))
    return sorted(output, key=lambda item: (item.priority_score, item.impressions), reverse=True)


class SearchConsole:
    def __init__(self, credentials: Any):
        from google.auth.transport.requests import AuthorizedSession
        self.session = AuthorizedSession(credentials)

    def _request(self, url: str, *, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = None
        for attempt in range(5):
            response = self.session.request(method, url, json=payload, timeout=60)
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            if attempt < 4:
                retry_after = response.headers.get("Retry-After")
                delay = min(60, int(retry_after)) if retry_after and retry_after.isdigit() else min(30, 2 ** attempt)
                time.sleep(delay)
        if response is None or not response.ok:
            status = response.status_code if response is not None else "no response"
            raise RuntimeError(f"Search Console API returned HTTP {status}")
        return response.json()

    def properties(self) -> list[dict[str, str]]:
        data = self._request(f"{API_ROOT}/sites")
        return [
            {"siteUrl": item["siteUrl"], "permissionLevel": item.get("permissionLevel", "unknown")}
            for item in data.get("siteEntry", [])
        ]

    def query_all(self, site_url: str, start: str, end: str) -> tuple[list[dict[str, Any]], bool]:
        rows: list[dict[str, Any]] = []
        start_row = 0
        while start_row < MAX_ROWS_PER_PROPERTY:
            endpoint = f"{API_ROOT}/sites/{quote(site_url, safe='')}/searchAnalytics/query"
            payload = {
                "startDate": start, "endDate": end, "type": "web",
                "dimensions": ["query", "page"], "rowLimit": PAGE_SIZE,
                "startRow": start_row,
            }
            page = self._request(endpoint, method="POST", payload=payload).get("rows", [])
            rows.extend(page)
            if len(page) < PAGE_SIZE:
                return rows, False
            start_row += len(page)
        return rows, True


def make_credentials() -> Any:
    from google.oauth2.credentials import Credentials
    refresh_token = os.environ.get("GSC_REFRESH_TOKEN")
    client_id = os.environ.get("GSC_CLIENT_ID")
    client_secret = os.environ.get("GSC_CLIENT_SECRET")
    if not all((refresh_token, client_id, client_secret)):
        raise RuntimeError("Set GSC_REFRESH_TOKEN, GSC_CLIENT_ID and GSC_CLIENT_SECRET as GitHub Actions secrets")
    return Credentials(
        token=None, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id, client_secret=client_secret, scopes=[SCOPE],
    )


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("._-")[:90] or "property"


def write_outputs(property_url: str, rows: list[dict[str, Any]], truncated: bool, start: str, end: str, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    opportunities = build_opportunities(property_url, rows)
    slug = safe_name(property_url)
    csv_path = out_dir / f"{slug}-opportunities.csv"
    fields = list(asdict(opportunities[0]).keys()) if opportunities else list(Opportunity.__dataclass_fields__.keys())
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(item) for item in opportunities)
    summary = {
        "property": property_url, "start_date": start, "end_date": end,
        "rows_returned": len(rows), "question_opportunities": len(opportunities),
        "truncated": truncated, "minimum_impressions": MIN_IMPRESSIONS,
        "ranking_formula": "max(0, position_bucket_baseline_CTR - query_CTR) * impressions * (1 + min(impressions,1000)/1000)",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / f"{slug}-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / f"{slug}-opportunities.json").write_text(
        json.dumps([asdict(item) for item in opportunities], indent=2), encoding="utf-8"
    )
    return summary


def upload_to_gcs(out_dir: Path, bucket_name: str, prefix: str) -> int:
    from google.cloud import storage
    client = storage.Client()
    bucket_ref = client.bucket(bucket_name)
    count = 0
    for path in out_dir.iterdir():
        if path.is_file():
            blob = bucket_ref.blob(f"{prefix.rstrip('/')}/{path.name}")
            blob.upload_from_filename(str(path), content_type="application/json" if path.suffix == ".json" else "text/csv")
            count += 1
    return count


def main() -> int:
    start, end = settled_window(os.getenv("GSC_START_DATE"), os.getenv("GSC_END_DATE"))
    output_dir = Path(os.getenv("GSC_OUTPUT_DIR", "reports/gsc"))
    api = SearchConsole(make_credentials())
    properties = api.properties()
    if not properties:
        raise RuntimeError("The connected Google account has no accessible Search Console properties")
    summaries: list[dict[str, Any]] = []
    for prop in properties:
        site_url = prop["siteUrl"]
        try:
            rows, truncated = api.query_all(site_url, start, end)
            summaries.append(write_outputs(site_url, rows, truncated, start, end, output_dir))
            print(f"Processed property: {site_url} | rows={len(rows)} | truncated={truncated}")
        except Exception as exc:
            print(f"Property failed: {site_url} | {type(exc).__name__}: {exc}", file=sys.stderr)
            summaries.append({"property": site_url, "error": type(exc).__name__})
    (output_dir / "run-summary.json").write_text(json.dumps({
        "start_date": start, "end_date": end, "properties_discovered": len(properties),
        "properties_succeeded": sum("error" not in item for item in summaries),
        "properties": summaries,
    }, indent=2), encoding="utf-8")
    if not any("error" not in item for item in summaries):
        return 1
    bucket_name = os.getenv("GCS_BUCKET")
    if bucket_name:
        prefix = os.getenv("GCS_PREFIX", "maximo/gsc") + f"/{end}/{os.getenv('GSC_RUN_ID', 'manual')}"
        count = upload_to_gcs(output_dir, bucket_name, prefix)
        print(f"Uploaded {count} report files to Google Cloud Storage")
    return 0 if all("error" not in item for item in summaries) else 2


if __name__ == "__main__":
    raise SystemExit(main())
