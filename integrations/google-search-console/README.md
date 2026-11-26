# MAXIMO — direct Google Search Console integration

A GitHub Actions-based, read-only Search Console collector for every property accessible to one Google account. Google Cloud supplies OAuth and (optionally) durable object storage; GitHub Actions runs the collector and stores downloadable reports.

## Architecture

- **GitHub Actions:** daily scheduled collection, manual runs, tests and report artifacts.
- **Google Cloud OAuth:** a Web OAuth client supports the mobile OAuth Playground flow; the optional local bootstrap script uses a separate Desktop OAuth client.
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


## 1. MAXIMO public information pages (GitHub Pages)

The repository includes a static homepage and privacy policy in `docs/`:

- Homepage: `docs/index.html`
- Privacy policy: `docs/privacy.html`

To publish from a phone:

1. Open the [MAXIMO repository](https://github.com/DKTJONATHAN/Maximo) in your browser.
2. Open **Settings → Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**.
4. Select branch **main** and folder **/docs**, then tap **Save**.
5. Wait for the Pages deployment to finish. GitHub will show the published site URL on the Pages settings screen.
6. Open the homepage and privacy policy URLs to confirm both load publicly over HTTPS.
7. In Google Cloud **Google Auth Platform → Branding**, set the application homepage URL to the published homepage and the privacy policy URL to the published `privacy.html` page.

**Important Google verification limitation:** this repository is public so GitHub Pages can be hosted on the free plan. The default `github.io` host is a shared GitHub domain, not a domain you own. Google's production brand-verification rules may require a homepage and privacy policy on a domain you own and can verify in Search Console. A `github.io` URL alone is not a guarantee of Google brand verification. For production verification, connect a custom domain you own to GitHub Pages, verify that domain in Search Console, and use the custom-domain URLs in Google Auth Platform.

## 2. Google Cloud setup

1. Create or select a Google Cloud project.
2. Enable **Google Search Console API**.
3. Configure the OAuth consent screen. Add the Google account that owns/has access to the properties as a test user while setting up.
4. Create an OAuth client with application type **Desktop app** and download its JSON file. Keep that file private and outside the repository.
5. For long-lived automation, move an External consent screen from Testing to In production and complete any verification Google requires. External apps in Testing can receive refresh tokens that expire after seven days for non-basic scopes such as Search Console.
6. Confirm the Google account has at least read access to each Search Console property you want collected.

The only requested OAuth scope is:

`https://www.googleapis.com/auth/webmasters.readonly`

## 2. Connect Google OAuth to GitHub Secrets

Requirements on your computer: Python 3.10+, Git, and the GitHub CLI (`gh`).

```bash
gh auth login
git clone https://github.com/DKTJONATHAN/Maximo.git
cd Maximo
git checkout feat/direct-google-search-console
python -m pip install -r requirements.txt
python scripts/authorize_gsc.py --client-secrets /path/to/downloaded-oauth-client.json --repo DKTJONATHAN/Maximo
```

The script opens Google's consent screen in your browser, receives the OAuth callback on localhost, and writes these three values directly to GitHub Actions Secrets using `gh` (they are not printed or committed):

- `GSC_CLIENT_ID`
- `GSC_CLIENT_SECRET`
- `GSC_REFRESH_TOKEN`

If Google does not issue a refresh token, revoke the app's previous grant from your Google Account security settings and run the script again. Never paste OAuth credentials into chat or source control.

## 4. Run the collector

Open **GitHub → Maximo → Actions → Google Search Console sync → Run workflow**. Leave dates blank for the default settled 28-day window, or supply `YYYY-MM-DD` start/end dates (maximum 90 days).

The workflow runs tests and discovers properties. **Important:** this repository is public, so it does not upload Search Console report files as GitHub artifacts. Configure the optional private Google Cloud Storage archive to retain and retrieve reports. Artifacts are enabled only when the repository itself is private. It runs automatically each day after the workflow is merged into the repository's default branch. GitHub scheduled workflows run from the default branch, not an unmerged feature branch.

The default question regex and minimum-impression threshold (20) are defined in `gsc/collector.py`. To override them, add repository Variables named `GSC_QUESTION_REGEX` and `GSC_MIN_IMPRESSIONS` under Settings → Secrets and variables → Actions → Variables.

## 5. Optional durable Google Cloud Storage archive

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

The workflow uploads each run under `maximo/gsc/END_DATE/RUN_ID/`. No service-account private key is needed. If these three variables are not configured, collection still runs, but generated reports remain only on the temporary runner and are discarded at the end of the run. Do not make a public GCS bucket or public artifact the report destination.

## Output and limitations

- `*-opportunities.csv` — spreadsheet-friendly opportunities.
- `*-opportunities.json` — complete structured opportunity records.
- `*-summary.json` — per-property date window, row count and truncation status.
- `run-summary.json` — overall property success/failure summary.

This first version is an analytics collector, not a web dashboard. It does not edit site content, submit sitemaps, publish pages, or modify Search Console settings. Google Search Console API quotas and data availability apply.
