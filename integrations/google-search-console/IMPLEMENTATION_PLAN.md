# Implementation plan — GitHub + Google Cloud

## Architecture decisions

- Execution: GitHub Actions (daily schedule + manual dispatch).
- Google identity: one Google OAuth Desktop client and one Google account.
- Permission: `webmasters.readonly` only.
- Runtime: Python 3.12 in GitHub-hosted runners; no always-on server.
- Secrets: refresh token, OAuth client ID and client secret in GitHub Actions Secrets.
- Default persistence: downloadable GitHub Actions artifacts (30-day retention).
- Optional durable archive: Google Cloud Storage via GitHub OIDC Workload Identity Federation; no static service-account key.
- Initial behavior: read, analyse and recommend only; no website changes or publishing.

## Status

- [x] Remove Cloudflare Worker/D1 runtime from the integration.
- [x] Implement local OAuth bootstrap that stores credentials directly in GitHub Actions Secrets.
- [x] Implement Search Console property discovery for the authorized Google account.
- [x] Implement query + page collection with bounded pagination (100,000 rows/property).
- [x] Implement question-query filtering, minimum-impression threshold and position-bucket CTR baseline.
- [x] Export per-property CSV/JSON and run summaries.
- [x] Add transient API retry/backoff.
- [x] Add daily scheduled and manual GitHub Actions workflow.
- [x] Add optional GCS archive using OIDC/WIF.
- [x] Add unit tests for date bounds, position buckets and opportunity scoring.
- [ ] Configure Google Cloud OAuth consent/client and add GitHub Secrets (account-side action required).
- [ ] Run a live Search Console sync and inspect real property/report results.
- [ ] Configure optional GCS bucket/WIF variables if durable archive is wanted.
- [ ] Merge to the default branch to activate scheduled runs.
- [ ] Build a dashboard and longer-term change measurement workflow.

## Acceptance criteria

1. Only `webmasters.readonly` is requested.
2. Refresh token and OAuth client secret are never logged or committed.
3. All properties returned by the authorized account are discovered automatically.
4. Data is queried only for properties returned by the Search Console Sites API.
5. Query/page attribution is preserved.
6. Pagination is bounded and truncation is disclosed.
7. CTR comparison is position-bucketed and clearly labelled as an internal observed baseline.
8. Daily collection uses a settled date window and manual runs accept explicit dates.
9. Reports are available as GitHub artifacts; optional GCS uses short-lived WIF credentials.
10. No site content is modified or published.

## Known limitations

- Search Analytics API data is delayed, top-row based and may omit anonymized low-volume queries.
- The 100k-row cap may truncate large properties.
- GitHub artifacts expire after 30 days; configure GCS for durable history.
- No dashboard, scheduled historical backfill, automatic publishing or site-side integration is included in this first release.
- Google OAuth External apps left in Testing may receive refresh tokens that expire after seven days for sensitive scopes; configure consent-screen production status as required.
