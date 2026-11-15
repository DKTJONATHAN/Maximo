# Proposed Architecture

## Design goals
Provider-agnostic, repository-aware, secure by default, observable, testable and cost-aware. The first release is a reliable engineering copilot with gated execution—not a self-authorizing production agent.

## Components
1. Task gateway — identity, project scope, task classification and acceptance criteria.
2. Context assembler — repository map, relevant files, project memory, prior findings and selected skills; token-budgeted and provenance-aware.
3. Policy engine — tool allowlists, path/network scopes, approvals, secret redaction and risk classification.
4. Planner/router — frontend, backend, UX, security, QA, SEO and DevOps specialists.
5. Execution workers — isolated workspaces for reading, editing, testing and browser/security analysis.
6. Tool adapters — GitHub, filesystem, shell, browser, package manager, Supabase, CI, analytics and deployment.
7. Verification engine — tests, typecheck, lint, build, browser, accessibility, security and SEO checks.
8. Evidence ledger — task events, tool outcomes, artifact hashes, approvals and test evidence.
9. Delivery interface — diffs, test reports, risks, approval requests and PR creation.

## Safe lifecycle
queued → scoped → inspected → planned → awaiting_approval (when needed) → executing → verifying → ready_for_review → completed | blocked | failed

Persist state transitions. Use idempotency keys for side effects. Bound retries and prevent duplicate writes.

## Isolation
- Disposable workspace/container per task or branch.
- No ambient host credentials; inject short-lived scoped tokens only when needed.
- Default-deny network egress with explicit allowlists.
- CPU, memory, disk, process and wall-clock limits.
- Shell command policy and approval for privileged/destructive commands.
- Redact secrets from logs and model context.

## Initial implementation
Start with a TypeScript/Node.js control plane and replaceable provider interfaces. Introduce PostgreSQL only when durable multi-user runtime state is required. Git branches and PRs are delivery units; CI is the deterministic gate.

## Core interfaces
Task: id, repo, baseRef, scope, acceptanceCriteria, risk, status, budget.
ToolCall: taskId, actor, tool, argsHash, approvalId, startedAt, result, duration, outcome.
Skill: name, description, triggers, procedure, inputs, outputs, checks, references.
Evidence: kind, command/url/artifact, timestamp, exitCode/status, digest, notes.
Approval: action, scope, requester, approver, expiresAt, decision.

## Non-goals for v0
Unrestricted autonomous production deployment, self-modifying policy, untrusted scripts on host, or claims of security certification/WCAG conformance from automation alone.