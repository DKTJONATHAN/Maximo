#!/usr/bin/env python3
"""Submit recently changed same-host URLs to IndexNow (Bing and other participants)."""
from __future__ import annotations
import argparse
import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def record_result(record: dict) -> None:
    path = Path("docs/data/indexnow-submissions.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        history = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(history, list):
            history = []
    except (OSError, json.JSONDecodeError):
        history = []
    history.append(record)
    history = history[-100:]
    path.write_text(json.dumps(history, indent=2), encoding="utf-8")
    dashboard_path = Path("docs/data/dashboard.json")
    try:
        dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
        sitemap_path = Path("docs/data/sitemap-submissions.json")
        sitemap_history = json.loads(sitemap_path.read_text(encoding="utf-8")) if sitemap_path.exists() else []
        dashboard["submission_history"] = sorted(sitemap_history + history, key=lambda item: item.get("submitted_at", ""))[-100:]
        dashboard_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError, TypeError):
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True, help="Verified host, e.g. example.com")
    parser.add_argument("--urls-file", required=True, help="UTF-8 file containing one URL per line")
    args = parser.parse_args()
    key = os.environ.get("INDEXNOW_API_KEY", "")
    host_input = args.host.strip()
    host_parsed = urlparse(host_input if "://" in host_input else "https://" + host_input)
    host = host_parsed.hostname or ""
    urls = list(dict.fromkeys(line.strip() for line in Path(args.urls_file).read_text(encoding="utf-8").splitlines() if line.strip()))
    record = {"channel": "IndexNow", "host": host, "url_count": len(urls), "urls": urls[:100],
              "submitted_at": datetime.now(timezone.utc).isoformat(), "success": False}
    try:
        if (not re.fullmatch(r"[A-Za-z0-9.-]+", host) or ".." in host
                or host_parsed.path not in {"", "/"} or host_parsed.query or host_parsed.fragment
                or host_parsed.username or host_parsed.password or host_parsed.port):
            raise ValueError("Provide a valid hostname without a path or port")
        if not key or not re.fullmatch(r"[A-Za-z0-9-]{8,128}", key):
            raise RuntimeError("INDEXNOW_API_KEY is missing or invalid (8–128 letters, digits or hyphens)")
        if not 1 <= len(urls) <= 100:
            raise ValueError("Provide between 1 and 100 URLs per IndexNow batch")
        for url in urls:
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != host or parsed.username or parsed.password or parsed.port:
                raise ValueError("Every URL must be HTTPS and belong to the exact submitted host")
        key_url = f"https://{host}/{key}.txt"
        with urllib.request.urlopen(key_url, timeout=20) as response:
            if urlparse(response.geturl()).hostname != host:
                raise RuntimeError("IndexNow key file redirected away from the submitted host")
            key_content = response.read(512).decode("utf-8", errors="replace").strip()
        if key_content != key:
            raise RuntimeError(f"IndexNow key file is missing or does not contain the configured key: {key_url}")
        body = json.dumps({"host": host, "key": key, "keyLocation": key_url, "urlList": urls}).encode("utf-8")
        request = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
            headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                code = response.status
        except urllib.error.HTTPError as response:
            code = response.code
        record["response_code"] = code
        if code == 200:
            record.update({"success": True, "status": "submitted", "message": "IndexNow validated and accepted the URL batch. This does not confirm indexing."})
        elif code == 202:
            record.update({"success": True, "status": "accepted_pending_validation", "message": "Accepted; search engines still need to validate the key file. This does not confirm indexing."})
        else:
            record.update({"status": "failed", "message": f"IndexNow rejected the request (HTTP {code})"})
    except Exception as exc:
        message = re.sub(r"https?://\S+", "[URL]", str(exc))
        record.update({"status": "failed", "message": f"{type(exc).__name__}: {message[:280]}"})
    record_result(record)
    print(json.dumps({k: v for k, v in record.items() if k != "urls"}, indent=2))
    return 0 if record["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
