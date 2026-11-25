# Implementation plan

## Selected decisions

- Hosting: Cloudflare Workers.
- Google identity: one Google account, one OAuth connection.
- Permission: Search Console read-only scope only.
- Storage: dedicated D1 database; refresh token encrypted at application layer.
- First consumer: MAXIMO admin workflow; site-specific dashboards can be added later.
- Initial behavior: read, analyze and recommend only. No automatic content edits or publishing.

## Milestones

### A. Cloud and Google prerequisites
- [ ] Create Google Cloud project and enable Search Console API.
- [ ] Configure OAuth consent screen and OAuth Web client.
- [ ] Deploy Worker and set exact redirect URI.
- [ ] Create D1 database and apply schema.
- [ ] Set secrets and non-secret variables.
- [ ] Complete OAuth consent and store encrypted refresh token.

### B. Read-only API
- [ ] Implement OAuth state validation, token exchange and refresh.
- [ ] Implement property discovery and local property registry.
- [ ] Implement query + page Search Analytics request and bounded pagination.
- [ ] Enforce property allowlist, date validation and RE2 regex length limits.
- [ ] Add structured, redacted error handling and audit events.

### C. Question mining
- [ ] Implement configurable question regex patterns.
- [ ] Persist query/page pairs without losing page attribution.
- [ ] Calculate CTR and position buckets.
- [ ] Build position-aware CTR baselines from the same property/date window.
- [ ] Rank by impression-weighted CTR gap and practical opportunity size.
- [ ] Flag low sample sizes, truncated datasets and missing baseline data.

### D. Operations and reporting
- [ ] Add daily Cron Trigger using a settled date window.
- [ ] Add retry/backoff for transient Google API errors and quota responses.
- [ ] Add monitoring for expired/revoked authorization and failed syncs.
- [ ] Expose CSV/JSON export and a MAXIMO dashboard view.
- [ ] Add a four-week before/after comparison for changed pages.

## Acceptance criteria

1. OAuth refresh token never appears in source code, browser output or logs.
2. Only the read-only Search Console scope is requested.
3. Property discovery returns only sites visible to the authorized Google account.
4. A query is rejected if its siteUrl is not in the discovered property registry.
5. Regex analysis returns query/page pairs and preserves the page attribution.
6. Pagination is bounded and the report explicitly marks truncated results.
7. CTR is compared within position buckets; low-impression rows are not promoted as strong opportunities.
8. Scheduled collection uses settled dates and is idempotent for a property/date/run.
9. No page content is changed or published by this integration.
10. Unit tests cover regex validation, date validation, scoring, encryption/decryption and pagination boundaries.

## Dependencies and deployment blocker

The code can be completed in the MAXIMO repository, but live authorization and deployment require the user's Google Cloud OAuth client credentials and access to the target Cloudflare account. These must be entered directly into Google Cloud and Cloudflare; they should never be sent in chat or committed to Git.
