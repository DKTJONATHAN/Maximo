#!/usr/bin/env python3
"""One-time local OAuth bootstrap; stores credentials directly as GitHub Actions secrets."""
from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


def set_secret(name: str, value: str, repo: str) -> None:
    result = subprocess.run(
        ["gh", "secret", "set", name, "--repo", repo], input=value,
        text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Could not set GitHub secret {name}: {result.stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Connect Search Console and save GitHub Actions secrets")
    parser.add_argument("--client-secrets", required=True, help="Downloaded Google OAuth Desktop client JSON")
    parser.add_argument("--repo", default="DKTJONATHAN/Maximo", help="GitHub owner/repository")
    args = parser.parse_args()
    client_path = Path(args.client_secrets).expanduser()
    config = json.loads(client_path.read_text(encoding="utf-8"))
    client = config.get("installed")
    if not client:
        raise SystemExit("OAuth JSON must be a Google Desktop (installed) OAuth client")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), scopes=[SCOPE])
    credentials = flow.run_local_server(host="localhost", port=0, access_type="offline", prompt="consent")
    if not credentials.refresh_token:
        raise SystemExit("Google did not issue a refresh token. Revoke the previous grant and run again.")
    set_secret("GSC_CLIENT_ID", client["client_id"], args.repo)
    set_secret("GSC_CLIENT_SECRET", client.get("client_secret", ""), args.repo)
    set_secret("GSC_REFRESH_TOKEN", credentials.refresh_token, args.repo)
    print(f"Google Search Console connected. Three GitHub Actions secrets saved for {args.repo}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
