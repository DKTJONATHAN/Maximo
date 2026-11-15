# Roadmap and Acceptance Criteria

## Phase 0 — Repository foundation
- Preserve the existing skill library.
- Define engineering contract, architecture, research register and CI baseline.
- Establish license and contribution/security guidance.
Acceptance: clean repository, documented policies, CI passes.

## Phase 1 — Read-only repository copilot
- Repository tree, file and symbol inspection, diff and branch metadata.
- Planner with acceptance criteria and bounded budgets.
- Skill loader with frontmatter validation and relevance routing.
- Read-only mode and evidence ledger.
- CLI: maximo inspect, maximo plan, maximo review.
Acceptance: map a test repository and plan a small change without modifying source.

## Phase 2 — Sandboxed implementation
- Disposable workspace and command allowlist.
- Patch application, diff review and regression tests.
- Test/typecheck/lint/build runner with captured exit codes.
- Bounded retry and human approval for privileged actions.
Acceptance: solve seeded bug-fix tasks without host credential exposure or writes outside scope.

## Phase 3 — Web quality specialists
- React/Next.js, API/database, SEO, accessibility and performance workflows.
- Browser automation with screenshot and console/network evidence.
- Anti-slop checks and OWASP ASVS-aligned security workflow.
Acceptance: representative feature with test, accessibility, performance and security evidence.

## Phase 4 — Integrations
- GitHub PR and CI lifecycle.
- Supabase schema/RLS inspection and migration review.
- MCP permission registry, Search Console/GA4 and deployment previews.
Acceptance: approved branch/PR, CI inspection and reproducible delivery report.

## Phase 5 — Evaluation and controlled autonomy
- SWE-bench-style issue subset and project-specific tasks.
- UI interaction/visual benchmark and security challenge suite.
- Cost, latency, patch quality, regression and success metrics.
- Canary and rollback; explicit production approval.
Acceptance: reproducible benchmark methodology and no autonomous production deploy by default.