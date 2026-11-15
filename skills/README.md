# Skill Library

MAXIMO uses an on-demand skill router. A skill is a focused procedure with triggers, inputs, outputs, validation and references. Skills do not grant tool permissions; the runtime enforces authorization separately.

## Imported skills
The existing seo-coding-ai-skills-v2 library covers code review/debugging, secure code review, web application security testing, threat modelling, UI systems, UX research, accessibility, technical SEO, keyword research, content briefs, structured data and MCP workflow building.

## MAXIMO-authored extensions
- anti-slop-ui-engineering — product-grounded art direction, UI critique and deterministic quality checks.
- frontend-engineering — React/Next.js architecture, component boundaries, state, forms and rendering.
- backend-api-engineering — API contracts, validation, authn/authz, data access and reliability.
- testing-and-quality-engineering — test strategy, regression coverage, browser tests and failure diagnosis.
- performance-engineering — Core Web Vitals, profiling, budgets and regression prevention.
- devops-and-ci — reproducible builds, CI security, deployments and rollback planning.
- repository-intelligence — repo mapping, dependency tracing, change impact and baseline capture.
- seo-engineering — crawlability, indexability, metadata, schema, rendering and measurement.
- agent-orchestration — bounded plans, tool routing, state, retry budgets and approval boundaries.

## Routing
UI bug: repository-intelligence + frontend-engineering + debugging + testing.
New product page: UX research + anti-slop UI + frontend + accessibility.
Auth/API: backend + threat modelling + secure review + testing.
Performance: repository-intelligence + performance + testing.
Technical SEO: SEO audit + SEO engineering + structured data.
Security audit: threat modelling + web testing + secure review.

Use the narrowest relevant skill set. Executable checks and policy gates remain authoritative.