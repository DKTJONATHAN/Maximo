export interface Env {
  DB: D1Database;
  GOOGLE_CLIENT_ID: string;
  GOOGLE_CLIENT_SECRET: string;
  GOOGLE_REDIRECT_URI: string;
  TOKEN_ENCRYPTION_KEY: string;
  ADMIN_API_TOKEN: string;
}

type GscRow = {
  keys?: string[];
  clicks?: number;
  impressions?: number;
  ctr?: number;
  position?: number;
};

type SearchAnalyticsResponse = { rows?: GscRow[] };

const GOOGLE_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly";
const GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth";
const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";
const GOOGLE_API = "https://www.googleapis.com/webmasters/v3";
const DEFAULT_QUESTION_REGEX =
  "^(who|what|when|where|why|how|which|can|could|should|would|will|do|does|did|is|are|was|were|has|have)\\b";
const PAGE_SIZE = 25_000;
const MAX_ROWS = 100_000;
const MAX_REGEX_LENGTH = 400;
const MAX_DATE_RANGE_DAYS = 90;

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

function errorResponse(message: string, status: number): Response {
  return json({ error: message }, status);
}

async function sha256(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function randomToken(bytes = 32): string {
  const data = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...data)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodeBase64(value: string): Uint8Array {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(normalized);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

async function encryptionKey(env: Env): Promise<CryptoKey> {
  const raw = decodeBase64(env.TOKEN_ENCRYPTION_KEY);
  if (raw.byteLength !== 32) throw new Error("TOKEN_ENCRYPTION_KEY must decode to exactly 32 bytes");
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}

async function encryptRefreshToken(token: string, env: Env) {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    await encryptionKey(env),
    new TextEncoder().encode(token),
  );
  return {
    ciphertext: btoa(String.fromCharCode(...new Uint8Array(encrypted))),
    iv: btoa(String.fromCharCode(...iv)),
  };
}

async function decryptRefreshToken(ciphertext: string, iv: string, env: Env): Promise<string> {
  const clear = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: Uint8Array.from(atob(iv), (c) => c.charCodeAt(0)) },
    await encryptionKey(env),
    Uint8Array.from(atob(ciphertext), (c) => c.charCodeAt(0)),
  );
  return new TextDecoder().decode(clear);
}

async function requireAdmin(request: Request, env: Env): Promise<boolean> {
  const header = request.headers.get("authorization") ?? "";
  const supplied = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!supplied || !env.ADMIN_API_TOKEN) return false;
  const [a, b] = await Promise.all([sha256(supplied), sha256(env.ADMIN_API_TOKEN)]);
  return a === b;
}

function validDate(value: unknown): value is string {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value + "T00:00:00Z");
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

function dateDistanceDays(start: string, end: string): number {
  return Math.round((Date.parse(end + "T00:00:00Z") - Date.parse(start + "T00:00:00Z")) / 86_400_000);
}

function validateRegex(pattern: string): string | null {
  if (!pattern || pattern.length > MAX_REGEX_LENGTH) return "Regex must contain 1–400 characters";
  // Google uses RE2. Reject constructs supported by JavaScript but not RE2.
  if (/\\[1-9]|\\k<|\\g<|\\p\{|\\P\{|\(\?([=!]|<[=!]|P<)/.test(pattern)) {
    return "Regex contains a construct unsupported by Google's RE2 engine";
  }
  try { new RegExp(pattern); } catch { return "Regex is not syntactically valid"; }
  return null;
}

async function googleToken(env: Env): Promise<string> {
  const stored = await env.DB.prepare(
    "SELECT refresh_token_ciphertext, refresh_token_iv FROM google_credentials WHERE id = 1",
  ).first<{ refresh_token_ciphertext: string; refresh_token_iv: string }>();
  if (!stored) throw new Error("Google account is not connected. Complete OAuth first.");
  const refreshToken = await decryptRefreshToken(
    stored.refresh_token_ciphertext,
    stored.refresh_token_iv,
    env,
  );
  const response = await fetch(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET,
      refresh_token: refreshToken,
      grant_type: "refresh_token",
    }),
  });
  const payload = await response.json() as { access_token?: string; error?: string };
  if (!response.ok || !payload.access_token) {
    throw new Error(`Google token refresh failed: ${payload.error ?? response.status}`);
  }
  return payload.access_token;
}

async function googleFetch<T>(url: string, accessToken: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      authorization: `Bearer ${accessToken}`,
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = await response.text();
    // Do not return raw Google error payloads to callers; they may contain sensitive metadata.
    throw new Error(`Google API request failed with HTTP ${response.status}: ${body.slice(0, 500)}`);
  }
  return response.json() as Promise<T>;
}

async function startOAuth(env: Env): Promise<string> {
  const state = randomToken(32);
  const stateHash = await sha256(state);
  const now = new Date();
  const expires = new Date(now.getTime() + 10 * 60_000);
  await env.DB.prepare(
    "INSERT INTO oauth_states (state_hash, created_at, expires_at) VALUES (?, ?, ?)",
  ).bind(stateHash, now.toISOString(), expires.toISOString()).run();

  const url = new URL(GOOGLE_AUTH_URL);
  url.search = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID,
    redirect_uri: env.GOOGLE_REDIRECT_URI,
    response_type: "code",
    scope: GOOGLE_SCOPE,
    access_type: "offline",
    prompt: "consent",
    state,
  }).toString();
  return url.toString();
}

async function handleOAuthCallback(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const oauthError = url.searchParams.get("error");
  if (oauthError) return errorResponse("Google authorization was declined or failed", 400);
  if (!code || !state) return errorResponse("Missing OAuth code or state", 400);

  const stateHash = await sha256(state);
  const saved = await env.DB.prepare(
    "SELECT state_hash FROM oauth_states WHERE state_hash = ? AND expires_at > ?",
  ).bind(stateHash, new Date().toISOString()).first();
  if (!saved) return errorResponse("OAuth state is invalid, expired or already used", 400);
  await env.DB.prepare("DELETE FROM oauth_states WHERE state_hash = ?").bind(stateHash).run();

  const tokenResponse = await fetch(GOOGLE_TOKEN_URL, {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      code,
      client_id: env.GOOGLE_CLIENT_ID,
      client_secret: env.GOOGLE_CLIENT_SECRET,
      redirect_uri: env.GOOGLE_REDIRECT_URI,
      grant_type: "authorization_code",
    }),
  });
  const tokens = await tokenResponse.json() as {
    refresh_token?: string;
    scope?: string;
    error?: string;
  };
  if (!tokenResponse.ok || !tokens.refresh_token) {
    return errorResponse(
      "Google did not return a refresh token. Revoke the previous app grant and connect again with offline consent.",
      400,
    );
  }
  if (!(tokens.scope ?? "").split(" ").includes(GOOGLE_SCOPE)) {
    return errorResponse("Google authorization did not include the required read-only Search Console scope", 403);
  }

  const encrypted = await encryptRefreshToken(tokens.refresh_token, env);
  const now = new Date().toISOString();
  await env.DB.prepare(`
    INSERT INTO google_credentials
      (id, refresh_token_ciphertext, refresh_token_iv, key_version, scopes, connected_at, updated_at)
    VALUES (1, ?, ?, 1, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
      refresh_token_ciphertext = excluded.refresh_token_ciphertext,
      refresh_token_iv = excluded.refresh_token_iv,
      scopes = excluded.scopes,
      connected_at = excluded.connected_at,
      updated_at = excluded.updated_at
  `).bind(encrypted.ciphertext, encrypted.iv, tokens.scope, now, now).run();

  return json({ connected: true, message: "Google Search Console read-only authorization saved. You may close this page." });
}

async function listProperties(env: Env) {
  const token = await googleToken(env);
  const result = await googleFetch<{ siteEntry?: Array<{ siteUrl: string; permissionLevel?: string }> }>(
    `${GOOGLE_API}/sites`,
    token,
  );
  const entries = result.siteEntry ?? [];
  const now = new Date().toISOString();
  for (const entry of entries) {
    const propertyType = entry.siteUrl.startsWith("sc-domain:") ? "domain" : "url-prefix";
    await env.DB.prepare(`
      INSERT INTO gsc_properties (site_url, permission_level, property_type, discovered_at)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(site_url) DO UPDATE SET
        permission_level = excluded.permission_level,
        property_type = excluded.property_type,
        discovered_at = excluded.discovered_at
    `).bind(entry.siteUrl, entry.permissionLevel ?? null, propertyType, now).run();
  }
  return entries;
}

async function queryRows(
  siteUrl: string,
  startDate: string,
  endDate: string,
  token: string,
  regex?: string,
): Promise<{ rows: GscRow[]; truncated: boolean }> {
  const all: GscRow[] = [];
  let startRow = 0;
  let truncated = false;
  while (startRow < MAX_ROWS) {
    const body: Record<string, unknown> = {
      startDate,
      endDate,
      type: "web",
      dimensions: ["query", "page"],
      rowLimit: PAGE_SIZE,
      startRow,
    };
    if (regex) {
      body.dimensionFilterGroups = [{
        groupType: "and",
        filters: [{ dimension: "query", operator: "includingRegex", expression: regex }],
      }];
    }
    const endpoint = `${GOOGLE_API}/sites/${encodeURIComponent(siteUrl)}/searchAnalytics/query`;
    const result = await googleFetch<SearchAnalyticsResponse>(endpoint, token, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const batch = result.rows ?? [];
    all.push(...batch);
    if (batch.length < PAGE_SIZE) return { rows: all, truncated: false };
    startRow += batch.length;
  }
  truncated = true;
  return { rows: all, truncated };
}

function positionBucket(position: number): number {
  return Math.max(1, Math.min(100, Math.floor(position)));
}

function buildBaseline(rows: GscRow[]): Map<number, { clicks: number; impressions: number }> {
  const map = new Map<number, { clicks: number; impressions: number }>();
  for (const row of rows) {
    const bucket = positionBucket(row.position ?? 100);
    const current = map.get(bucket) ?? { clicks: 0, impressions: 0 };
    current.clicks += row.clicks ?? 0;
    current.impressions += row.impressions ?? 0;
    map.set(bucket, current);
  }
  return map;
}

async function analyzeQuestions(request: Request, env: Env): Promise<Response> {
  const input = await request.json() as {
    siteUrl?: string;
    startDate?: string;
    endDate?: string;
    regex?: string;
    minimumImpressions?: number;
  };
  const { siteUrl, startDate, endDate } = input;
  if (!siteUrl || !validDate(startDate) || !validDate(endDate) || startDate > endDate) {
    return errorResponse("Provide a registered siteUrl and valid startDate/endDate in YYYY-MM-DD format", 400);
  }
  if (dateDistanceDays(startDate, endDate) > MAX_DATE_RANGE_DAYS) {
    return errorResponse(`Date range cannot exceed ${MAX_DATE_RANGE_DAYS} days per analysis`, 400);
  }
  const regex = input.regex ?? DEFAULT_QUESTION_REGEX;
  const regexError = validateRegex(regex);
  if (regexError) return errorResponse(regexError, 400);
  const minimumImpressions = Math.max(1, Math.min(100_000, Math.floor(input.minimumImpressions ?? 50)));

  const property = await env.DB.prepare(
    "SELECT site_url FROM gsc_properties WHERE site_url = ? AND is_active = 1",
  ).bind(siteUrl).first();
  if (!property) return errorResponse("Property is not registered. Sync accessible Search Console properties first.", 403);

  const runId = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  await env.DB.prepare(`
    INSERT INTO gsc_analysis_runs
      (id, site_url, start_date, end_date, regex_pattern, minimum_impressions, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 'running', ?)
  `).bind(runId, siteUrl, startDate, endDate, regex, minimumImpressions, createdAt).run();

  try {
    const token = await googleToken(env);
    const [questionResult, baselineResult] = await Promise.all([
      queryRows(siteUrl, startDate, endDate, token, regex),
      queryRows(siteUrl, startDate, endDate, token),
    ]);
    const baseline = buildBaseline(baselineResult.rows);
    const now = new Date().toISOString();
    const insert = env.DB.prepare(`
      INSERT OR REPLACE INTO gsc_question_rows
        (run_id, site_url, query, page_url, clicks, impressions, ctr, average_position,
         position_bucket, baseline_ctr, ctr_gap_pp, estimated_click_gap, priority_score, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    const writes = [];
    let saved = 0;
    for (const row of questionResult.rows) {
      const query = row.keys?.[0] ?? "";
      const pageUrl = row.keys?.[1] ?? "";
      const impressions = row.impressions ?? 0;
      if (!query || !pageUrl || impressions < minimumImpressions) continue;
      const clicks = row.clicks ?? 0;
      const ctr = (row.ctr ?? 0) * 100;
      const position = row.position ?? 100;
      const bucket = positionBucket(position);
      const bucketData = baseline.get(bucket);
      const baselineCtr = bucketData && bucketData.impressions > 0
        ? (bucketData.clicks / bucketData.impressions) * 100
        : null;
      const gap = baselineCtr === null ? null : baselineCtr - ctr;
      const estimatedClickGap = gap === null ? 0 : Math.max(0, gap / 100) * impressions;
      const priorityScore = estimatedClickGap;
      writes.push(insert.bind(
        runId, siteUrl, query, pageUrl, clicks, impressions, ctr, position,
        bucket, baselineCtr, gap, estimatedClickGap, priorityScore, now,
      ));
      saved++;
    }
    for (let offset = 0; offset < writes.length; offset += 100) {
      await env.DB.batch(writes.slice(offset, offset + 100));
    }
    const truncated = questionResult.truncated || baselineResult.truncated;
    await env.DB.prepare(`
      UPDATE gsc_analysis_runs
      SET rows_returned = ?, truncated = ?, status = 'completed', completed_at = ?
      WHERE id = ?
    `).bind(saved, truncated ? 1 : 0, new Date().toISOString(), runId).run();

    return json({
      runId,
      siteUrl,
      startDate,
      endDate,
      regex,
      minimumImpressions,
      rowsSaved: saved,
      truncated,
      baseline: "Property-specific weighted CTR by integer average-position bucket",
      note: "Estimated click gap is a diagnostic comparison, not a traffic forecast. Search Console may omit anonymized queries and limit returned rows.",
    });
  } catch (error) {
    await env.DB.prepare(
      "UPDATE gsc_analysis_runs SET status = 'failed', error_code = ?, completed_at = ? WHERE id = ?",
    ).bind(error instanceof Error ? error.message.slice(0, 300) : "unknown_error", new Date().toISOString(), runId).run();
    throw error;
  }
}

async function opportunities(url: URL, env: Env): Promise<Response> {
  const siteUrl = url.searchParams.get("siteUrl");
  if (!siteUrl) return errorResponse("siteUrl is required", 400);
  const run = await env.DB.prepare(`
    SELECT id, start_date, end_date, regex_pattern, rows_returned, truncated, created_at
    FROM gsc_analysis_runs
    WHERE site_url = ? AND status = 'completed'
    ORDER BY created_at DESC LIMIT 1
  `).bind(siteUrl).first<{
    id: string; start_date: string; end_date: string; regex_pattern: string;
    rows_returned: number; truncated: number; created_at: string;
  }>();
  if (!run) return errorResponse("No completed analysis exists for this property", 404);
  const rows = await env.DB.prepare(`
    SELECT query, page_url, clicks, impressions, ctr, average_position, position_bucket,
           baseline_ctr, ctr_gap_pp, estimated_click_gap, priority_score
    FROM gsc_question_rows
    WHERE run_id = ?
    ORDER BY priority_score DESC, impressions DESC
    LIMIT 500
  `).bind(run.id).all();
  return json({ run, opportunities: rows.results });
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    try {
      if (url.pathname === "/health" && request.method === "GET") {
        return json({ ok: true, service: "maximo-gsc", version: "0.1.0" });
      }

      if (url.pathname === "/oauth/google/callback" && request.method === "GET") {
        return await handleOAuthCallback(request, env);
      }

      if (!(await requireAdmin(request, env))) return errorResponse("Unauthorized", 401);

      if (url.pathname === "/oauth/google/start" && request.method === "POST") {
        return json({ authorizationUrl: await startOAuth(env) });
      }
      if (url.pathname === "/api/properties" && request.method === "GET") {
        return json({ properties: await listProperties(env) });
      }
      if (url.pathname === "/api/properties/sync" && request.method === "POST") {
        return json({ properties: await listProperties(env) });
      }
      if (url.pathname === "/api/questions/analyze" && request.method === "POST") {
        return await analyzeQuestions(request, env);
      }
      if (url.pathname === "/api/questions/opportunities" && request.method === "GET") {
        return await opportunities(url, env);
      }
      return errorResponse("Not found", 404);
    } catch (error) {
      // Detailed error strings are deliberately not sent to the client.
      console.error("GSC integration request failed", {
        path: url.pathname,
        message: error instanceof Error ? error.message.slice(0, 300) : "unknown_error",
      });
      return errorResponse("The request could not be completed. Check Worker logs using the request timestamp.", 502);
    }
  },
};
