#!/usr/bin/env python3
"""Automatically notify IndexNow participants about sitemap URLs with changed lastmod values."""
from __future__ import annotations
import gzip
import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

MAX_XML_BYTES = 5 * 1024 * 1024
MAX_CHILD_SITEMAPS = 20
MAX_BATCH = 100


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _same_host(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname == host and not parsed.username and not parsed.password and not parsed.port


def _covered(site_url: str, url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if site_url.startswith("sc-domain:"):
        domain = site_url.split(":", 1)[1].lower().strip(".")
        return host == domain or host.endswith("." + domain)
    prop = urlparse(site_url)
    parsed = urlparse(url)
    prefix = prop.path or "/"
    path_ok = parsed.path.startswith(prefix) if prefix.endswith("/") else (parsed.path == prefix or parsed.path.startswith(prefix + "/"))
    return parsed.scheme == prop.scheme and host == (prop.hostname or "").lower() and path_ok


def parse_lastmod(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def should_submit(lastmod: datetime, previous: str | None, bootstrap_cutoff: datetime) -> bool:
    if previous:
        old = parse_lastmod(previous)
        return old is None or lastmod > old
    return lastmod >= bootstrap_cutoff


def fetch_xml(url: str, host: str) -> ET.Element:
    if not _same_host(url, host):
        raise ValueError("Sitemap URL is not HTTPS on the expected host")
    request = urllib.request.Request(url, headers={"User-Agent": "MAXIMO-IndexNow/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        if urlparse(response.geturl()).hostname != host:
            raise ValueError("Sitemap redirected away from its host")
        raw = response.read(MAX_XML_BYTES + 1)
    if len(raw) > MAX_XML_BYTES:
        raise ValueError("Sitemap exceeds the 5 MB inspection limit")
    if url.lower().endswith(".gz"):
        raw = gzip.decompress(raw)
        if len(raw) > MAX_XML_BYTES:
            raise ValueError("Expanded sitemap exceeds the 5 MB inspection limit")
    return ET.fromstring(raw)


def sitemap_lastmods(sitemap_url: str, host: str) -> dict[str, str]:
    root = fetch_xml(sitemap_url, host)
    urls: dict[str, str] = {}
    children = [node.text.strip() for node in root.iter() if _local(node.tag) == "loc" and node.text]
    if _local(root.tag) == "sitemapindex":
        children = [url for url in children[:MAX_CHILD_SITEMAPS] if _same_host(url, host)]
        roots = [fetch_xml(url, host) for url in children]
    else:
        roots = [root]
    for sitemap in roots:
        if _local(sitemap.tag) != "urlset":
            continue
        for node in sitemap:
            if _local(node.tag) != "url":
                continue
            loc = next((child.text.strip() for child in node if _local(child.tag) == "loc" and child.text), None)
            lastmod = next((child.text.strip() for child in node if _local(child.tag) == "lastmod" and child.text), None)
            if loc and lastmod and _same_host(loc, host):
                parsed = parse_lastmod(lastmod)
                if parsed:
                    urls[loc] = parsed.isoformat()
    return urls


def verify_key(host: str, key: str) -> str:
    key_url = f"https://{host}/{key}.txt"
    with urllib.request.urlopen(key_url, timeout=20) as response:
        if urlparse(response.geturl()).hostname != host:
            raise ValueError("IndexNow key file redirected away from the expected host")
        content = response.read(512).decode("utf-8", errors="replace").strip()
    if content != key:
        raise ValueError("IndexNow key file is missing or does not match the configured key")
    return key_url


def send_batch(host: str, key: str, key_url: str, urls: list[str]) -> int:
    body = json.dumps({"host": host, "key": key, "keyLocation": key_url, "urlList": urls}).encode("utf-8")
    request = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as response:
        return response.code


def append_history(records: list[dict], state: dict[str, str]) -> None:
    history_path = Path("docs/data/indexnow-submissions.json")
    history_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else []
    except (OSError, json.JSONDecodeError):
        history = []
    history.extend(records)
    history_path.write_text(json.dumps(history[-100:], indent=2), encoding="utf-8")
    Path("docs/data/indexnow-lastmod-state.json").write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    dashboard_path = Path("docs/data/dashboard.json")
    try:
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        sitemap_path = Path("docs/data/sitemap-submissions.json")
        sitemap_history = json.loads(sitemap_path.read_text(encoding="utf-8")) if sitemap_path.exists() else []
        dashboard["submission_history"] = sorted(sitemap_history + history[-100:], key=lambda item: item.get("submitted_at", ""))[-100:]
        dashboard_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError, TypeError):
        pass


def main() -> int:
    key = os.environ.get("INDEXNOW_API_KEY", "")
    if not key:
        print("IndexNow auto-submission disabled: INDEXNOW_API_KEY is not configured.")
        return 0
    if not re.fullmatch(r"[A-Za-z0-9-]{8,128}", key):
        print("IndexNow auto-submission disabled: INDEXNOW_API_KEY has an invalid format.")
        return 1
    dashboard_path = Path("docs/data/dashboard.json")
    if not dashboard_path.exists():
        print("No dashboard snapshot exists yet; IndexNow auto-submission skipped.")
        return 0
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    try:
        state = json.loads(Path("docs/data/indexnow-lastmod-state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        state = {}
    now = datetime.now(timezone.utc)
    bootstrap_cutoff = now - timedelta(days=2)
    records: list[dict] = []
    any_failed = False
    by_host: dict[str, dict[str, str]] = {}

    for prop in dashboard.get("properties", []):
        site_url = str(prop.get("property") or "")
        for sitemap in prop.get("sitemaps", []):
            sitemap_url = str(sitemap.get("path") or "")
            host = (urlparse(sitemap_url).hostname or "").lower()
            if not host or not _same_host(sitemap_url, host):
                continue
            try:
                found = sitemap_lastmods(sitemap_url, host)
            except Exception as exc:
                records.append({"channel": "IndexNow auto", "host": host, "property": site_url,
                    "sitemap_url": sitemap_url, "submitted_at": now.isoformat(), "success": False,
                    "status": "sitemap_read_failed", "message": f"{type(exc).__name__}: {str(exc)[:200]}"})
                any_failed = True
                continue
            for url, lastmod in found.items():
                if _covered(site_url, url) and should_submit(parse_lastmod(lastmod), state.get(url), bootstrap_cutoff):
                    by_host.setdefault(host, {})[url] = lastmod

    for host, candidates in by_host.items():
        urls = sorted(candidates)
        try:
            key_url = verify_key(host, key)
        except Exception as exc:
            records.append({"channel": "IndexNow auto", "host": host, "url_count": len(urls),
                "submitted_at": now.isoformat(), "success": False, "status": "key_validation_failed",
                "message": f"{type(exc).__name__}: {str(exc)[:200]}"})
            any_failed = True
            continue
        for offset in range(0, len(urls), MAX_BATCH):
            batch = urls[offset:offset + MAX_BATCH]
            try:
                code = send_batch(host, key, key_url, batch)
                accepted = code in {200, 202}
                records.append({"channel": "IndexNow auto", "host": host, "url_count": len(batch),
                    "urls": batch, "submitted_at": now.isoformat(), "response_code": code,
                    "success": accepted, "status": "submitted" if code == 200 else "accepted_pending_validation" if code == 202 else "failed",
                    "message": "Accepted by IndexNow; indexing is not guaranteed." if accepted else f"IndexNow returned HTTP {code}"})
                if accepted:
                    for url in batch:
                        state[url] = candidates[url]
                else:
                    any_failed = True
            except Exception as exc:
                records.append({"channel": "IndexNow auto", "host": host, "url_count": len(batch),
                    "urls": batch, "submitted_at": now.isoformat(), "success": False, "status": "request_failed",
                    "message": f"{type(exc).__name__}: {str(exc)[:200]}"})
                any_failed = True

    if records:
        append_history(records, state)
    print(json.dumps({"hosts_with_changes": len(by_host), "batches_recorded": len(records),
                      "urls_in_state": len(state), "failed": any_failed}, indent=2))
    return 1 if any_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
