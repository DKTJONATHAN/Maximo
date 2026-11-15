# Security Model

## Trust boundaries
- User request and approved task scope.
- Repository files, issues, pull request comments and documentation (untrusted).
- Model-generated plans and patches (untrusted until reviewed).
- Tool adapters and external services.
- Execution workspace and host environment.
- Secrets and production systems.

## Baseline controls
1. Default-deny tool permissions; skills never grant capabilities.
2. Read-only inspection by default.
3. Explicit, scoped approval for writes, dependency installation, network egress, migrations, production changes and active security testing.
4. Disposable isolated execution with resource limits and no ambient credentials.
5. Short-lived least-privilege credentials; redact secrets from logs and model context.
6. Validate tool arguments and external input at trust boundaries.
7. Record actor, task, tool, scope, approval, result and evidence digest.
8. Bound retries, execution time, token budgets and external side effects.
9. Treat prompt injection in files and web content as untrusted input.
10. Human review before production deployment.

## Security verification
Use OWASP ASVS as a requirements catalogue, OWASP WSTG for authorized testing methodology, and NIST SSDF for secure development practices. Automated checks are evidence, not certification. Findings must include scope, reproduction, impact, confidence and remediation.

## Incident response
Stop affected workers, revoke scoped credentials, preserve relevant logs, identify affected tasks/artifacts, notify the operator, remediate and verify before resuming. Never silently retry a suspected credential compromise.
