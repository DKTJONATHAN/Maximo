-- MAXIMO direct Google Search Console integration
-- Apply to a dedicated Cloudflare D1 database.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS oauth_states (
  state_hash TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS google_credentials (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  refresh_token_ciphertext TEXT NOT NULL,
  refresh_token_iv TEXT NOT NULL,
  key_version INTEGER NOT NULL DEFAULT 1,
  scopes TEXT NOT NULL,
  connected_email TEXT,
  connected_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gsc_properties (
  site_url TEXT PRIMARY KEY,
  permission_level TEXT,
  property_type TEXT,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  discovered_at TEXT NOT NULL,
  last_synced_at TEXT
);

CREATE TABLE IF NOT EXISTS gsc_analysis_runs (
  id TEXT PRIMARY KEY,
  site_url TEXT NOT NULL REFERENCES gsc_properties(site_url) ON DELETE CASCADE,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  regex_pattern TEXT NOT NULL,
  minimum_impressions INTEGER NOT NULL,
  rows_returned INTEGER NOT NULL DEFAULT 0,
  truncated INTEGER NOT NULL DEFAULT 0 CHECK (truncated IN (0, 1)),
  status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
  error_code TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE IF NOT EXISTS gsc_question_rows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES gsc_analysis_runs(id) ON DELETE CASCADE,
  site_url TEXT NOT NULL REFERENCES gsc_properties(site_url) ON DELETE CASCADE,
  query TEXT NOT NULL,
  page_url TEXT NOT NULL,
  clicks REAL NOT NULL,
  impressions REAL NOT NULL,
  ctr REAL NOT NULL,
  average_position REAL NOT NULL,
  position_bucket INTEGER NOT NULL,
  priority_score REAL NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (run_id, query, page_url)
);

CREATE INDEX IF NOT EXISTS idx_gsc_question_rows_site_run
  ON gsc_question_rows(site_url, run_id, impressions DESC);

CREATE INDEX IF NOT EXISTS idx_gsc_question_rows_query
  ON gsc_question_rows(query);

CREATE INDEX IF NOT EXISTS idx_gsc_analysis_runs_site_date
  ON gsc_analysis_runs(site_url, end_date DESC);
