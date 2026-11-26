# MAXIMO — direct Google Search Console integration

A GitHub Actions-based, read-only Search Console collector for every property accessible to one Google account. Google Cloud supplies OAuth and (optionally) durable object storage; GitHub Actions runs the collector and stores downloadable reports.

## Architecture

- **GitHub Actions:** daily scheduled collection, manual runs, tests and report artifacts.
- **Google Cloud OAuth:** a Web OAuth client supports the mobile OAuth Playground flow; the optional local bootstrap script uses a separate Desktop OAuth client.
- **Search Console API:** read-only property discovery, query/page performance, sitemap health and sampled URL Inspection results.
- **GitHub Pages dashboard:** publishes a compact site-health snapshot at `docs/dashboard.html`; the UI checks for a new snapshot every five minutes while collection runs on schedule.
- **GitHub Actions artifacts:** default report delivery (30-day retention).
- **Google Cloud Storage (optional):** durable report archive, authenticated with GitHub OIDC Workload Identity Federation (no service-account JSON key).

There is no Cloudflare Worker, D1 database, always-on server or Cloudflare secret configuration.

## What it does

- Discovers all Search Console properties visible to the connected Google account.
- Collects Web search query + page rows for the latest settled 28-day period (default end date: three days ago).
- Collects the immediately preceding equal-length 28-day period for historical comparison.
- Reports query/page click and impression changes, CTR movement, ranking-position movement, newly visible/lost query rows and pages with the largest observed click losses.
- Diagnoses property permission failures and prints the exact Google Search Console access remediation steps.
- Lists sitemap submission/download dates, Google-reported sitemap warnings/errors and submitted-versus-indexed URL counts.
- Inspects up to five high-value HTTPS landing-page URLs per property each daily run, recording Google verdict, coverage, canonical and last-crawl status.
- Publishes best performers, click gainers/decliners, access/indexing/sitemap alerts and submission history in the website command centre.
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

The workflow runs tests and discovers properties. **Important privacy notice:** this repository is public. Successful runs upload CSV, JSON and Markdown reports as GitHub Actions artifacts for 30 days, and anyone with repository access can download them. Only connect properties whose data you are comfortable making public. For confidential sites or client data, move the workflow to a private repository or configure private Google Cloud Storage with restrictive IAM permissions. It runs automatically each day after the workflow is merged into the repository's default branch. GitHub scheduled workflows run from the default branch, not an unmerged feature branch.

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

The workflow uploads each run under `maximo/gsc/END_DATE/RUN_ID/`. No service-account private key is needed. If these three variables are not configured, the downloadable GitHub Actions artifact remains available for 30 days. Remember that artifacts in this public repository are publicly downloadable.

## Website command centre and indexing operations

Open the portal at `https://dktjonathan.github.io/Maximo/dashboard.html`. It shows property-level search metrics, period-over-period movement, top performers, declining sites, sitemap coverage, sitemap errors/warnings, sampled URL inspections, activity alerts and recorded submission attempts. The page checks for a new data snapshot every five minutes; the underlying collector runs on its daily schedule. It is not a real-time Google feed.

The standard collector remains read-only. URL Inspection is limited to a small daily sample of up to five HTTPS landing pages per property, selected from pages with Search Console query data. Google documents a per-property URL Inspection quota of 2,000 requests per day; MAXIMO deliberately uses only a small fraction. This sample is not a full-site crawl or a complete index count. <https://developers.google.com/webmaster-tools/limits>

### Submit a sitemap to Google

A separate manual workflow is available under **Actions → Submit sitemap to Google Search Console**. It uses a separate OAuth grant with the broader `https://www.googleapis.com/auth/webmasters` scope and does not change the read-only token used for daily reporting. To configure it once on a trusted computer with Python and GitHub CLI:

```bash
python -m pip install -r requirements.txt
gh auth login
python scripts/authorize_gsc_write.py --client-secrets /path/to/oauth-desktop-client.json --repo DKTJONATHAN/Maximo
```

The script saves `GSC_WRITE_CLIENT_ID`, `GSC_WRITE_CLIENT_SECRET` and `GSC_WRITE_REFRESH_TOKEN` as GitHub Actions secrets. Then open **Actions → Submit sitemap to Google Search Console → Run workflow**, enter the exact Search Console property and the full URL of an existing sitemap. The workflow validates that the sitemap belongs to the property, submits it and records success/failure in the dashboard. Sitemap submission tells Google where to find the sitemap; it does not guarantee that any URL is crawled or indexed. Google documents the Sitemaps API submit operation as a `PUT` request. <https://developers.google.com/webmaster-tools/v1/api_reference_index>

### Notify Bing and participating engines with IndexNow

A separate manual workflow is available under **Actions → Submit URLs through IndexNow**. Add an `INDEXNOW_API_KEY` repository secret, publish a plain-text key file at `https://HOST/KEY.txt` containing exactly the key, then run the workflow with the exact hostname and up to 100 changed HTTPS URLs on that host. The workflow checks the public key file before sending and records the result. Submit only new, updated or deleted URLs, not the whole unchanged site. An HTTP 202 means accepted pending key validation, not indexed.

#### Automatic daily IndexNow notifications

MAXIMO also has an **Automatic IndexNow updates** workflow scheduled daily at 08:17 UTC (11:17 Nairobi time). Once `INDEXNOW_API_KEY` is configured and the same key is published at `https://HOST/KEY.txt` on each participating website, the workflow reads sitemap `lastmod` values and sends only new/updated HTTPS URLs to IndexNow. It remembers the last successfully notified `lastmod` per URL so unchanged pages are not repeatedly submitted. On first setup it only sends URLs whose `lastmod` is within the previous 48 hours. URLs without a valid `lastmod` are skipped. The workflow checks the key file, limits batches to 100 URLs per host/request, records errors and results, and does not update its per-URL state for rejected batches.

To enable it:
1. Add repository secret `INDEXNOW_API_KEY` in **Settings → Secrets and variables → Actions → Secrets**.
2. Publish a plain-text file at `https://YOUR-HOST/KEY.txt` containing exactly the secret value, on every website host you want included.
3. Open **Actions → Automatic IndexNow updates** and run it once to test. Future daily runs are automatic.

This sends notifications to IndexNow participants (including Bing and Yandex), not Google. It is not a Google indexing request.

**Important Google limitation:** Google does not participate in IndexNow. Google's Indexing API is restricted to pages with `JobPosting` or `BroadcastEvent` embedded in a `VideoObject`; it is not a general indexing-request API for ordinary pages. For normal pages, use valid sitemaps, internal links, URL Inspection diagnostics and fix coverage issues. <https://developers.google.com/search/apis/indexing-api/v3/quickstart> <https://indexnow.com/faq>

## Output and limitations

- `*-opportunities.csv` — spreadsheet-friendly opportunities.
- `*-opportunities.json` — complete structured opportunity records.
- `*-summary.json` — per-property date window, row count and truncation status.
- `run-summary.json` — overall property success/failure summary, Google permission level and historical collection status.
- `*-historical-comparison.csv` / `.json` — current-versus-previous query/page comparison, including clicks, impressions, CTR, position and visibility changes.
- `dashboard.json` — compact property performance, sitemap, URL Inspection, health and submission-history snapshot.

Historical declines are directional signals from the query/page rows returned by Search Analytics. A missing row is not proof of deindexing: Google can omit low-volume/anonymized queries and only returns top rows. MAXIMO cannot grant Google Search Console property permissions; for HTTP 403/forbidden errors, add the Google account used by the OAuth refresh token under Search Console → Settings → Users and permissions with at least Restricted access, then rerun collection.

The dashboard and daily collector do not edit site content or publish pages. Google sitemap submission and IndexNow are separate, manually triggered workflows with separate credentials/configuration. Google Search Console API quotas and data availability apply.
