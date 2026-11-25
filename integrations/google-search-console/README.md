# MAXIMO — direct Google Search Console integration

A GitHub Actions-based, read-only Search Console collector for every property accessible to one Google account. Google Cloud supplies OAuth and (optionally) durable object storage; GitHub Actions runs the collector and stores downloadable reports.

## Architecture

- **GitHub Actions:** daily scheduled collection, manual runs, tests and report artifacts.
- **Google Cloud OAuth:** one Desktop OAuth client authorizes the Google account that already has access to the Search Console properties.
- **Search Console API:** read-only property discovery and query/page performance data.
- **GitHub Actions artifacts:** default report delivery (30-day retention).
- **Google Cloud Storage (optional):** durable report archive, authenticated with GitHub OIDC Workload Identity Federation (no service-account JSON key).

There is no Cloudflare Worker, D1 database, always-on server or Cloudflare secret configuration.

## What it does

- Discovers all Search Console properties visible to the connected Google account.
- Collects Web search query + page rows for the latest settled 28-day period (default end date: three days ago).
- Mines question queries using a configurable regex.
- Preserves query-to-page attribution.
- Compares CTR against the same property's observed CTR baseline within integer average-position buckets.
- Calculates an estimated CTR-gap opportunity score and exports CSV + JSON per property.
- Retries transient Google API errors and caps collection at 100,000 rows per property.
- Runs daily at 06:17 UTC and can also be started manually with custom dates.

The ranking baseline is an internal, same-property diagnostic, not a universal industry CTR benchmark or a promise of future clicks. Search Analytics returns top rows rather than a guaranteed exhaustive query universe; low-volume queries can be anonymized, data is delayed, and capped results are marked as truncated.

## 1. Google Cloud setup (mobile-friendly)

You can complete this from a phone browser; no terminal, Python or Git app is required.

1. Open [Google Cloud Console](https://console.cloud.google.com/), select your project, and enable **Google Search Console API**.
2. Open **Google Auth Platform → Audience**. Configure the consent screen as External if prompted, and add your Google account as a test user while testing.
3. Open **Google Auth Platform → Clients** (or APIs & Services → Credentials) and create an OAuth client of type **Web application**. The OAuth Playground requires a Web client, not the Desktop client used by the optional local script.
4. Under **Authorized redirect URIs**, add this exact URI: `https://developers.google.com/oauthplayground`
5. Create the client and securely copy its **Client ID** and **Client secret**. Do not post either value in chat or commit them to the repository.

The only requested scope is `https://www.googleapis.com/auth/webmasters.readonly`.

## 2. Generate and save the refresh token from your phone

1. Open [Google OAuth 2.0 Playground](https://developers.google.com/oauthplayground/) in your mobile browser.
2. Open the gear/settings icon. Set **OAuth flow** to **Server-side**, **Access type** to **Offline**, and **Force prompt** to **Consent Screen**.
3. Enable **Use your own OAuth credentials** and enter the Web application's Client ID and Client secret created above. Google notes that the Playground proxies the OAuth exchange, so use only Google's official Playground URL and do not share its session or links containing credentials.
4. In Step 1, enter this exact scope in the custom scope field: `https://www.googleapis.com/auth/webmasters.readonly`
5. Tap **Authorize APIs** and sign in with the Google account that has access to all the Search Console properties you want MAXIMO to analyse. Approve the read-only access.
6. In Step 2, tap **Exchange authorization code for tokens**. Copy the **Refresh token** (not the access token).
7. Open [MAXIMO GitHub Actions Secrets](https://github.com/DKTJONATHAN/Maximo/settings/secrets/actions/new) in your browser. Add three repository secrets, one at a time:
   - Name: `GSC_CLIENT_ID` · Secret: your Web OAuth Client ID
   - Name: `GSC_CLIENT_SECRET` · Secret: your Web OAuth Client secret
   - Name: `GSC_REFRESH_TOKEN` · Secret: the refresh token from Step 2
8. Save each secret. GitHub will show the secret names, but will not reveal their values afterward.

Do not paste any of these values into ChatGPT, GitHub issues, pull requests, workflow inputs or source files. If the Playground does not return a refresh token, check that Access type is Offline, Force prompt is Consent Screen, and that the app is authorized with your own OAuth client.

For a long-lived connection, configure the External consent screen as **In production** and complete any Google verification requirements. An External app left in Testing may issue refresh tokens that expire after seven days for non-basic scopes. If you keep it in Testing, expect to repeat authorization.

The optional computer-based alternative is `scripts/authorize_gsc.py`; it is not required for the mobile procedure above.

## 3. Run the collector

Open **GitHub → Maximo → Actions → Google Search Console sync → Run workflow**. Leave dates blank for the default settled 28-day window, or supply `YYYY-MM-DD` start/end dates (maximum 90 days).

The workflow runs tests, discovers properties and uploads CSV/JSON reports as a downloadable artifact retained for 30 days. It runs automatically each day after the workflow is merged into the repository's default branch. GitHub scheduled workflows run from the default branch, not an unmerged feature branch.

The default question regex and minimum-impression threshold (20) are defined in `gsc/collector.py`. To override them, add repository Variables named `GSC_QUESTION_REGEX` and `GSC_MIN_IMPRESSIONS` under Settings → Secrets and variables → Actions → Variables.

## 4. Optional durable Google Cloud Storage archive

GitHub artifacts are convenient but expire after 30 days. For long-term history, create a bucket and configure Workload Identity Federation (WIF), so GitHub Actions receives short-lived Google credentials without a service-account key.

Set shell variables first:

```bash
PROJECT_ID="your-google-cloud-project-id"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
BUCKET="a-globally-unique-maximo-gsc-bucket"
SA="maximo-gsc-github"
POOL="github-pool"
PROVIDER="github-provider"
REPO="DKTJONATHAN/Maximo"
```

Create the bucket and service account:

```bash
gcloud config set project "$PROJECT_ID"
gcloud services enable iamcredentials.googleapis.com sts.googleapis.com storage.googleapis.com
gcloud storage buckets create "gs://$BUCKET" --location=US --uniform-bucket-level-access
gcloud iam service-accounts create "$SA" --display-name="MAXIMO GitHub GSC archive"
```

Create the GitHub OIDC identity pool/provider restricted to this repository:

```bash
gcloud iam workload-identity-pools create "$POOL" --location=global --display-name="GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --location=global --workload-identity-pool="$POOL" \
  --display-name="MAXIMO repository" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository == '$REPO'"
```

Grant the repository permission to impersonate the service account and create archive objects:

```bash
gcloud iam service-accounts add-iam-policy-binding "$SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL/attribute.repository/$REPO"
gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
  --member="serviceAccount:$SA@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"
```

Add these **GitHub repository Variables** (Settings → Secrets and variables → Actions → Variables):

- `GCP_WIF_PROVIDER` = `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/providers/github-provider`
- `GCP_SERVICE_ACCOUNT` = `maximo-gsc-github@PROJECT_ID.iam.gserviceaccount.com`
- `GCS_BUCKET` = your bucket name (without `gs://`)

The workflow uploads each run under `maximo/gsc/END_DATE/RUN_ID/`. No service-account private key is needed. If these three variables are not configured, collection still works and reports are available as GitHub artifacts.

## Output and limitations

- `*-opportunities.csv` — spreadsheet-friendly opportunities.
- `*-opportunities.json` — complete structured opportunity records.
- `*-summary.json` — per-property date window, row count and truncation status.
- `run-summary.json` — overall property success/failure summary.

This first version is an analytics collector, not a web dashboard. It does not edit site content, submit sitemaps, publish pages, or modify Search Console settings. Google Search Console API quotas and data availability apply.
