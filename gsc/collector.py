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

from gsc.history import previous_window, write_comparison_outputs

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
            detail = ""
            if response is not None:
                try:
                    error = response.json().get("error", {})
                    reasons = [item.get("reason") for item in error.get("errors", []) if item.get("reason")]
                    reason = reasons[0] if reasons else "unknown"
                    message = str(error.get("message") or "").strip()
                    message = re.sub(r"https?://\S+", "[URL]", message)
                    message = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", message)
                    detail = f" (reason={reason})" + (f": {message[:240]}" if message else "")
                except (ValueError, AttributeError, TypeError):
                    pass
            raise RuntimeError(f"Search Console API returned HTTP {status}{detail}")
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
    # Preserve the complete query/page dataset as well as the question-only opportunity subset.
    raw_records = []
    for row in rows:
        keys = row.get("keys") or []
        raw_records.append({
            "query": str(keys[0]) if len(keys) > 0 else "",
            "page": str(keys[1]) if len(keys) > 1 else "",
            "clicks": float(row.get("clicks") or 0),
            "impressions": float(row.get("impressions") or 0),
            "ctr": float(row.get("ctr") or 0),
            "position": float(row.get("position") or 0),
        })
    raw_json = out_dir / f"{slug}-search-performance.json"
    raw_json.write_text(json.dumps(raw_records, indent=2), encoding="utf-8")
    raw_csv = out_dir / f"{slug}-search-performance.csv"
    with raw_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["query", "page", "clicks", "impressions", "ctr", "position"])
        writer.writeheader()
        writer.writerows(raw_records)
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



def write_daily_report(summaries: list[dict[str, Any]], out_dir: Path, start: str, end: str) -> None:
    """Create a human-readable daily report and prioritized SEO action plan."""
    all_rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    for summary in summaries:
        property_url = summary.get("property")
        if not property_url or summary.get("error"):
            continue
        path = out_dir / f"{safe_name(property_url)}-opportunities.json"
        if path.exists():
            all_rows.extend(json.loads(path.read_text(encoding="utf-8")))
        raw_path = out_dir / f"{safe_name(property_url)}-search-performance.json"
        if raw_path.exists():
            for raw in json.loads(raw_path.read_text(encoding="utf-8")):
                raw["property"] = property_url
                raw_rows.append(raw)

    # Same-property, same-position-bucket CTR baselines for all queries, not just question phrasing.
    baselines: dict[tuple[str, int], list[float]] = {}
    for row in raw_rows:
        key = (str(row.get("property")), bucket(float(row.get("position") or 100)))
        totals = baselines.setdefault(key, [0.0, 0.0])
        totals[0] += float(row.get("clicks") or 0)
        totals[1] += float(row.get("impressions") or 0)
    for row in raw_rows:
        key = (str(row.get("property")), bucket(float(row.get("position") or 100)))
        clicks, impressions = baselines[key]
        row["bucket_baseline_ctr"] = clicks / impressions if impressions else 0.0
        row["estimated_click_gap"] = max(0.0, row["bucket_baseline_ctr"] - float(row.get("ctr") or 0)) * float(row.get("impressions") or 0)

    raw_row_count = len(raw_rows)
    deduplicated: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in raw_rows:
        key = (row.get("query"), row.get("page"), row.get("clicks"), row.get("impressions"), row.get("ctr"), row.get("position"))
        current = deduplicated.get(key)
        if current is None or (str(row.get("property", "")).startswith("sc-domain:") and not str(current.get("property", "")).startswith("sc-domain:")):
            deduplicated[key] = row
    raw_rows = list(deduplicated.values())
    duplicate_rows_suppressed = raw_row_count - len(raw_rows)
    question_candidates = [row for row in raw_rows if QUESTION_RE.search(str(row.get("query", "")))]
    all_rows.sort(key=lambda row: (float(row.get("priority_score") or 0), float(row.get("impressions") or 0)), reverse=True)
    prior_start, prior_end = previous_window(start, end)
    lines = [
        "# MAXIMO — Daily Search Console & SEO Report", "",
        f"**Reporting window:** {start} to {end}  ",
        f"**Comparison window:** {prior_start} to {prior_end}  ",
        f"**Generated (UTC):** {datetime.now(timezone.utc).isoformat()}  ",
        f"**Properties discovered:** {len(summaries)}  ",
        f"**Properties successfully collected:** {sum('error' not in item for item in summaries)}", "",
        "## Executive summary", "",
        f"- Question-query candidates found (all impression levels): **{len(question_candidates)}**",
        f"- Priority-qualified question opportunities (minimum {MIN_IMPRESSIONS} impressions): **{len(all_rows)}**",
        f"- Duplicate query/page rows suppressed across overlapping properties: **{duplicate_rows_suppressed}**",
        f"- Total query/page rows collected: **{sum(int(item.get('rows_returned', 0)) for item in summaries)}**",
        f"- Properties with collection errors: **{sum('error' in item for item in summaries)}**", "",
        "## Question-query mining (all impression levels)", "",
        "| Property | Question query | Landing page | Clicks | Impressions | CTR | Position |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in sorted(question_candidates, key=lambda item: (float(item.get("impressions") or 0), float(item.get("position") or 100)), reverse=True):
        lines.append(
            f"| {row.get('property','')} | {str(row.get('query','')).replace('|','/')} | {row.get('page','')} "
            f"| {float(row.get('clicks') or 0):.0f} | {float(row.get('impressions') or 0):.0f} "
            f"| {float(row.get('ctr') or 0):.1%} | {float(row.get('position') or 0):.1f} |"
        )
    if not question_candidates:
        lines.append("| — | No matching question queries in this date range | — | — | — | — | — |")

    lines += [
        "## Highest-priority question opportunities", "",
        "| Property | Question query | Landing page | Clicks | Impressions | CTR | Avg. position | Est. click gap |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in all_rows[:30]:
        query = str(row.get("query", "")).replace("|", "/")
        lines.append(
            f"| {row.get('property','')} | {query} | {row.get('page','')} "
            f"| {float(row.get('clicks') or 0):.0f} | {float(row.get('impressions') or 0):.0f} "
            f"| {float(row.get('ctr') or 0):.1%} | {float(row.get('average_position') or 0):.1f} "
            f"| {float(row.get('estimated_click_gap') or 0):.1f} |"
        )
    if not all_rows:
        lines.append("| — | No qualifying question-query opportunities | — | — | — | — | — | — |")

    # Historical comparison: exact query/page pairs across equal-length settled windows.
    historical_rows: list[dict[str, Any]] = []
    historical_errors = [item for item in summaries if item.get("historical_error")]
    for item in summaries:
        property_url = item.get("property")
        if not property_url or item.get("error"):
            continue
        comparison_path = out_dir / f"{safe_name(property_url)}-historical-comparison.json"
        if comparison_path.exists():
            historical_rows.extend(json.loads(comparison_path.read_text(encoding="utf-8")))
    # Avoid double-counting identical rows exposed through overlapping domain/URL-prefix properties.
    historical_deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in historical_rows:
        key = (row.get("query"), row.get("page"), row.get("clicks"), row.get("previous_clicks"),
               row.get("impressions"), row.get("previous_impressions"), row.get("position"),
               row.get("previous_position"))
        current = historical_deduped.get(key)
        if current is None or str(row.get("property", "")).startswith("sc-domain:"):
            historical_deduped[key] = row
    historical_rows = list(historical_deduped.values())
    declining = [row for row in historical_rows if float(row.get("clicks_delta") or 0) < 0]
    declining.sort(key=lambda row: (float(row.get("clicks_delta") or 0), float(row.get("impressions_delta") or 0)))
    lines += [
        "", "## Historical query/page movement", "",
        f"- Query/page pairs compared across equal-length periods: **{len(historical_rows)}**",
        f"- Pairs with fewer clicks than the previous period: **{len(declining)}**",
        f"- Properties where the historical comparison failed: **{len(historical_errors)}**",
        "",
        "| Property | Query | Landing page | Clicks now | Clicks before | Change | Impressions change | Position change |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in declining[:25]:
        pos_delta = row.get("position_delta")
        position_change = f"{float(pos_delta):+.1f}" if pos_delta is not None else "n/a"
        lines.append(
            f"| {row.get('property','')} | {str(row.get('query','')).replace('|','/')} | {row.get('page','')} "
            f"| {float(row.get('clicks') or 0):.0f} | {float(row.get('previous_clicks') or 0):.0f} "
            f"| {float(row.get('clicks_delta') or 0):+.0f} | {float(row.get('impressions_delta') or 0):+.0f} "
            f"| {position_change} |"
        )
    if not declining:
        lines.append("| — | No declining query/page pairs detected in the returned rows | — | — | — | — | — | — |")
    page_totals: dict[tuple[str, str], dict[str, float]] = {}
    for row in historical_rows:
        key = (str(row.get("property", "")), str(row.get("page", "")))
        totals = page_totals.setdefault(key, {"clicks_delta": 0.0, "impressions_delta": 0.0, "clicks": 0.0, "previous_clicks": 0.0})
        for metric in totals:
            totals[metric] += float(row.get(metric) or 0)
    page_declines = sorted(
        ((prop, page, metrics) for (prop, page), metrics in page_totals.items() if metrics["clicks_delta"] < 0),
        key=lambda item: item[2]["clicks_delta"],
    )
    lines += [
        "", "### Pages with the largest click losses", "",
        "| Property | Page | Clicks now | Clicks before | Change | Impressions change |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for prop, page, metrics in page_declines[:15]:
        lines.append(
            f"| {prop} | {page} | {metrics['clicks']:.0f} | {metrics['previous_clicks']:.0f} "
            f"| {metrics['clicks_delta']:+.0f} | {metrics['impressions_delta']:+.0f} |"
        )
    if not page_declines:
        lines.append("| — | No page-level click losses detected | — | — | — | — |")
    if historical_errors:
        for item in historical_errors:
            lines.append(f"- Historical comparison unavailable for {item.get('property', 'a property')}: {item.get('historical_error')}")
    lines += [
        "",
        "Interpretation: a positive position change means ranking position worsened; a negative change means it improved. Missing pairs mean no row was returned in that period, not proof that the page was deindexed. Search Console query rows are sampled/top-row limited and low-volume queries may be anonymized.",
    ]

    failed = [item for item in summaries if item.get("error")]
    if failed:
        lines += ["", "## Properties needing attention", ""]
        for item in failed:
            lines.append(f"- **{item.get('property', 'Unknown property')}** (Google access: {item.get('permission_level', 'unknown')}) — {item.get('error_message', item.get('error', 'Collection failed'))}")
            if "403" in str(item.get("error_message", "")) or "forbidden" in str(item.get("error_message", "")).lower():
                lines.append("  - **Required action:** open Google Search Console → Settings → Users and permissions and grant the Google account connected to MAXIMO at least **Restricted** access to this property. Re-run the collector after access is granted. MAXIMO uses read-only OAuth and cannot grant itself access.")
    lines += [
        "", "## Search query and landing-page opportunities (all queries)", "",
        "| Property | Search query | Landing page | Clicks | Impressions | CTR | Position | Est. CTR click gap |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    ranked_raw = sorted(raw_rows, key=lambda row: (float(row.get("estimated_click_gap") or 0), float(row.get("impressions") or 0)), reverse=True)
    for row in ranked_raw[:30]:
        query = str(row.get("query", "")).replace("|", "/")
        lines.append(
            f"| {row.get('property','')} | {query} | {row.get('page','')} "
            f"| {float(row.get('clicks') or 0):.0f} | {float(row.get('impressions') or 0):.0f} "
            f"| {float(row.get('ctr') or 0):.1%} | {float(row.get('position') or 0):.1f} "
            f"| {float(row.get('estimated_click_gap') or 0):.1f} |"
        )
    if not raw_rows:
        lines.append("| — | No query/page rows returned | — | — | — | — | — | — |")

    lines += ["", "## Prioritized SEO action plan", ""]
    if all_rows or raw_rows:
        lines += [
            "1. **Improve snippets first:** rewrite titles and meta descriptions for high-impression questions with CTR below the same-position baseline.",
            "2. **Strengthen page-one contenders:** for positions 4–10, improve the direct answer, topical coverage, supporting evidence and relevant internal links.",
            "3. **Build topical depth:** for positions 11–20, expand the best-matching existing page before creating a competing URL.",
            "4. **Add question coverage:** use the exact query as a natural H2/FAQ heading and answer it directly near the top of the page.",
            "5. **Avoid cannibalization:** consolidate near-duplicate intents on one strongest URL rather than creating thin pages for wording variations.",
            "", "### Page-level work queue", "",
        ]
        seen: set[tuple[str, str]] = set()
        queue = ranked_raw if raw_rows else all_rows
        for row in queue:
            key = (str(row.get("property")), str(row.get("page")))
            if key in seen:
                continue
            seen.add(key)
            position = float(row.get("position", row.get("average_position", 100)) or 100)
            impressions = float(row.get("impressions") or 0)
            query = str(row.get("query", ""))
            if position <= 3 and float(row.get("estimated_click_gap") or 0) > 0:
                action = "Rewrite title/meta description to lift CTR while protecting the strong ranking."
            elif position <= 10:
                action = "Improve the direct answer, add useful supporting sections and strengthen internal links."
            elif position <= 20:
                action = "Expand intent coverage and topical depth on this existing URL."
            else:
                action = "Validate search intent and content fit before investing in a major rewrite."
            lines.append(
                f"- **{row.get('page','')}** — lead query: “{query}” "
                f"(position {position:.1f}, {impressions:.0f} impressions). {action}"
            )
            if len(seen) >= 15:
                break
    else:
        lines.append("No qualifying query rows were returned. Check property coverage, date range and minimum-impression threshold.")

    lines += [
        "", "## Collection notes", "",
        "- CTR comparisons use the same-property, same-position-bucket baseline; estimated click gaps are directional, not guaranteed gains.",
        "- The default date window ends three days before collection to reduce reporting-latency effects.",
        "- Cannibalization and content-decay conclusions require historical/page-level comparisons; they are not asserted from this single snapshot.", "",
    ]
    (out_dir / "daily-seo-report.md").write_text(chr(10).join(lines), encoding="utf-8")



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
    for index, prop in enumerate(properties, start=1):
        site_url = prop["siteUrl"]
        try:
            rows, truncated = api.query_all(site_url, start, end)
            summary = write_outputs(site_url, rows, truncated, start, end, output_dir)
            summary["permission_level"] = prop.get("permissionLevel", "unknown")
            prior_start, prior_end = previous_window(start, end)
            try:
                prior_rows, prior_truncated = api.query_all(site_url, prior_start, prior_end)
                comparison = write_comparison_outputs(site_url, rows, prior_rows, output_dir, safe_name(site_url))
                summary.update({
                    "previous_start_date": prior_start, "previous_end_date": prior_end,
                    "previous_rows_returned": len(prior_rows),
                    "historical_pairs_compared": len(comparison),
                    "previous_truncated": prior_truncated,
                })
            except Exception as history_exc:
                # Preserve the successful current-period report if the historical read alone fails.
                safe_history_error = re.sub(r"https?://\S+", "[URL]", str(history_exc))
                safe_history_error = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", safe_history_error)
                summary["historical_error"] = f"{type(history_exc).__name__}: {safe_history_error[:240]}"
            summaries.append(summary)
            print(f"Property {index}/{len(properties)} processed | rows={len(rows)} | historical={summary.get('historical_pairs_compared', 'unavailable')} | truncated={truncated}")
        except Exception as exc:
            # Avoid printing property URLs or provider error text into public workflow logs.
            safe_error = re.sub(r"https?://\S+", "[URL]", str(exc))
            safe_error = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", safe_error)
            for secret_name, replacement in (("GSC_CLIENT_ID", "[CLIENT_ID]"), ("GSC_CLIENT_SECRET", "[CLIENT_SECRET]"), ("GSC_REFRESH_TOKEN", "[REFRESH_TOKEN]")):
                secret_value = os.getenv(secret_name)
                if secret_value:
                    safe_error = safe_error.replace(secret_value, replacement)
            print(f"Property {index}/{len(properties)} failed | {type(exc).__name__}: {safe_error[:300]}", file=sys.stderr)
            summaries.append({"property": site_url, "permission_level": prop.get("permissionLevel", "unknown"), "error": type(exc).__name__, "error_message": safe_error[:300]})
    (output_dir / "run-summary.json").write_text(json.dumps({
        "start_date": start, "end_date": end, "properties_discovered": len(properties),
        "properties_succeeded": sum("error" not in item for item in summaries),
        "properties": summaries,
    }, indent=2), encoding="utf-8")
    write_daily_report(summaries, output_dir, start, end)
    if not any("error" not in item for item in summaries):
        return 1
    bucket_name = os.getenv("GCS_BUCKET")
    if bucket_name:
        prefix = os.getenv("GCS_PREFIX", "maximo/gsc") + f"/{end}/{os.getenv('GSC_RUN_ID', 'manual')}"
        count = upload_to_gcs(output_dir, bucket_name, prefix)
        print(f"Uploaded {count} report files to Google Cloud Storage")
    # A partial run is still useful: preserve successful properties and expose failures in the report.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
