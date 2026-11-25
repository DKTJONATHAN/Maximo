# Direct Google Search Console integration

A shared, read-only Google Search Console integration hosted on Cloudflare Workers for MAXIMO-managed websites.

## Scope

- One Google OAuth connection for the Google account that already has access to the user's Search Console properties.
- Discover all properties visible to that account through the Search Console Sites API.
- Pull query + page performance rows directly from the Search Analytics API.
- Detect question queries using configurable RE2-compatible regular expressions.
- Rank opportunities using impressions, CTR, average position and position-aware CTR comparisons.
- Persist snapshots for trend comparison and export.
- Never edit site content or submit sitemaps in the initial release.

## Hosting and storage

- Cloudflare Worker: OAuth callback, API routes and scheduled collection.
- Cloudflare D1: OAuth state, encrypted refresh token, property registry, query snapshots and analysis runs.
- Cloudflare Worker secrets: Google OAuth client secret, token-encryption key and API admin token.
- Cron Trigger: daily collection. Search Console data is delayed; use a settled end date rather than assuming yesterday is complete.

No credentials belong in source control, browser JavaScript, Worker responses or logs.

## OAuth

Request only:

`https://www.googleapis.com/auth/webmasters.readonly`

Use Google's OAuth 2.0 authorization-code flow with offline access. The refresh token is encrypted with AES-GCM before it is stored in D1. Access tokens are short-lived and held only in Worker memory for the request.

The account must already have at least read permission for every property to be analyzed. The API cannot grant Search Console property access.

## Setup checklist

1. Create a Google Cloud project and enable **Google Search Console API**.
2. Configure the OAuth consent screen and add the account as a test user if the app is still in testing.
3. Create a **Web application** OAuth client.
4. Deploy the Worker once to obtain its stable HTTPS URL.
5. Set the exact callback URI to `https://<worker-host>/oauth/google/callback` in the Google OAuth client.
6. Create a D1 database and apply `schema.sql`.
7. Add Worker secrets:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `TOKEN_ENCRYPTION_KEY` (32 random bytes, base64 encoded)
   - `ADMIN_API_TOKEN` (high-entropy random token)
8. Set non-secret Worker variables:
   - `GOOGLE_REDIRECT_URI`
   - `APP_ORIGIN` (the approved MAXIMO dashboard origin, when a UI is added)
9. Run the OAuth connection flow and verify that property discovery returns the expected sites.
10. Run a read-only query against one property, then enable the daily Cron Trigger.

Do not paste OAuth client secrets, refresh tokens or encryption keys into chat or commit them to Git.

## API contract (initial)

All `/api/*` endpoints require `Authorization: Bearer <ADMIN_API_TOKEN>`.

- `GET /health` — health check; no secrets or token state returned.
- `POST /oauth/google/start` — returns a Google authorization URL; requires admin authorization.
- `GET /oauth/google/callback` — validates one-time OAuth state, exchanges the code and encrypts the refresh token.
- `GET /api/properties` — list accessible Search Console properties.
- `POST /api/properties/sync` — refresh the property registry.
- `POST /api/questions/analyze` — request question query/page rows for a property and date range.
- `GET /api/questions/opportunities?siteUrl=...` — read the most recent stored opportunity snapshot.

The OAuth start endpoint returns a URL rather than redirecting directly so an authorized admin client can initiate the flow without putting an admin token in a URL.

## Question regex

Default pattern:

```regex
^(who|what|when|where|why|how|which|can|could|should|would|will|do|does|did|is|are|was|were|has|have)\\b
```

Google's Search Analytics API uses RE2-compatible regular expressions. Keep patterns configurable per analysis and validate them before sending the request.

## Opportunity ranking

Do not rank by impressions alone. Each opportunity must include:

- impressions, clicks and CTR from Google;
- average position from Google;
- the page URL associated with the query;
- a position bucket;
- a position-aware comparison against the property's observed CTR baseline when enough rows exist;
- a transparent priority score and the exact formula used.

Use a minimum-impression threshold to avoid noisy recommendations. Never promise a click increase from a content change. Recommendations are advisory; publishing requires a separate explicit approval workflow.

## Known Search Console limitations

- Search Analytics returns top rows, not a guaranteed exhaustive query universe.
- Some low-volume queries are anonymized or omitted by Google.
- Data commonly lags by a few days.
- A query can map to multiple pages; preserve query/page pairs rather than collapsing them prematurely.
- The API's row limit is 25,000 per request; paginate with `startRow` and disclose truncation.

## Operational security

- Use read-only OAuth scope.
- Encrypt refresh tokens at rest using AES-GCM and a dedicated 256-bit key.
- Rotate the encryption key with a planned re-encryption procedure; do not simply replace it.
- Validate siteUrl against the property registry before querying.
- Validate dates, regex length and allowed dimensions.
- Apply request throttling and bounded pagination.
- Redact authorization headers, OAuth codes and token payloads from logs.
- Add an audit record for OAuth connect/disconnect and each analysis run.
- Keep content publishing and Search Console write operations out of this service.
