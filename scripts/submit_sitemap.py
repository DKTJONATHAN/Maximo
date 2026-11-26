#!/usr/bin/env python3
"""Submit one existing sitemap to Google Search Console with a dedicated write token."""
from __future__ import annotations
import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

API_ROOT = "https://www.googleapis.com/webmasters/v3"
SCOPE = "https://www.googleapis.com/auth/webmasters"


def validate_target(site_url: str, sitemap_url: str) -> None:
    parsed = urlparse(sitemap_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Sitemap URL must be an absolute HTTP(S) URL without embedded credentials")
    if site_url.startswith("sc-domain:"):
        domain = site_url.split(":", 1)[1].lower().strip(".")
        host = parsed.hostname.lower().strip(".")
        if host != domain and not host.endswith("." + domain):
            raise ValueError("Sitemap host must belong to the selected Search Console domain property")
    else:
        prop = urlparse(site_url)
        if prop.scheme not in {"http", "https"} or not prop.hostname:
            raise ValueError("Search Console property must be a valid URL-prefix property or sc-domain property")
        if parsed.hostname.lower() != prop.hostname.lower() or not parsed.path.startswith(prop.path or "/"):
            raise ValueError("Sitemap URL must be inside the selected URL-prefix property")


def append_history(record: dict) -> None:
    path = Path("docs/data/sitemap-submissions.json")
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
        dashboard["submission_history"] = history
        dashboard_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError, TypeError):
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-url", required=True)
    parser.add_argument("--sitemap-url", required=True)
    args = parser.parse_args()
    record = {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "property": args.site_url,
        "sitemap_url": args.sitemap_url,
        "success": False,
    }
    try:
        validate_target(args.site_url, args.sitemap_url)
        required = ("GSC_WRITE_CLIENT_ID", "GSC_WRITE_CLIENT_SECRET", "GSC_WRITE_REFRESH_TOKEN")
        if not all(os.environ.get(name) for name in required):
            raise RuntimeError("Missing dedicated GSC_WRITE_CLIENT_ID, GSC_WRITE_CLIENT_SECRET or GSC_WRITE_REFRESH_TOKEN secret")
        credentials = Credentials(
            token=None, refresh_token=os.environ["GSC_WRITE_REFRESH_TOKEN"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.environ["GSC_WRITE_CLIENT_ID"],
            client_secret=os.environ["GSC_WRITE_CLIENT_SECRET"], scopes=[SCOPE],
        )
        session = AuthorizedSession(credentials)
        endpoint = f"{API_ROOT}/sites/{quote(args.site_url, safe='')}/sitemaps/{quote(args.sitemap_url, safe='')}"
        response = session.put(endpoint, timeout=45)
        record["response_code"] = response.status_code
        if response.status_code in {200, 201, 204}:
            record.update({"success": True, "status": "submitted", "message": "Google accepted the sitemap submission request; this does not confirm indexing."})
        else:
            try:
                error = response.json().get("error", {})
                message = str(error.get("message") or "Google rejected the sitemap submission")
            except (ValueError, AttributeError):
                message = "Google rejected the sitemap submission"
            message = re.sub(r"https?://\S+", "[URL]", message)
            record.update({"status": "failed", "message": message[:300]})
    except Exception as exc:
        message = re.sub(r"https?://\S+", "[URL]", str(exc))
        record.update({"status": "failed", "message": f"{type(exc).__name__}: {message[:300]}"})
    append_history(record)
    print(json.dumps(record, indent=2))
    return 0 if record["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
