# Research and Reference Register

Snapshot: 2026-11-15. Prefer primary standards and official documentation. Re-check versions before implementation.

## Security
- OWASP ASVS 5.0.0 stable: https://asvs.owasp.org/
- OWASP Web Security Testing Guide: https://owasp.org/www-project-web-security-testing-guide/
- OWASP Cheat Sheet Series: https://cheatsheetseries.owasp.org/
- NIST SP 800-218 SSDF 1.1 final: https://csrc.nist.gov/pubs/sp/800/218/final
- NIST SP 800-218 Rev.1 / SSDF 1.2 initial public draft (Dec 2025): https://csrc.nist.gov/pubs/sp/800/218/r1/ipd — draft, not final.
- GitHub Actions hardening: https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions

## UI, UX and accessibility
- WCAG 2.2: https://www.w3.org/TR/WCAG22/
- WAI-ARIA Authoring Practices: https://www.w3.org/WAI/ARIA/apg/
- Vercel Agent Skills: https://vercel.com/docs/agent-resources/skills
- Impeccable: https://github.com/pbakaus/impeccable — inspect license, telemetry and install behavior before adoption.
- Unslop: https://github.com/heydamir/unslop — verify license and compatibility.
- UX/UI Skills: https://github.com/taylorwinfield/ux-ui-skills
- Anti-slop design: https://github.com/nyrthoughts/anti-slop-design — verify license and scripts before reuse.

## Frontend and performance
- React: https://react.dev/learn
- Next.js: https://nextjs.org/docs
- TypeScript: https://www.typescriptlang.org/docs/
- MDN: https://developer.mozilla.org/en-US/docs/Web
- web.dev: https://web.dev/learn/
- Core Web Vitals: https://developers.google.com/search/docs/appearance/core-web-vitals — field good thresholds at p75: LCP ≤2.5s, INP <200ms, CLS <0.1.
- Playwright: https://playwright.dev/docs/intro
- Vitest: https://vitest.dev/guide/

## Agent engineering
- SWE-bench: https://openreview.net/forum?id=VTF8yNQM66
- SWE-agent (NeurIPS 2024): https://arxiv.org/abs/2405.15793
- Agentless (2024): https://arxiv.org/abs/2407.01489 — reported benchmark results are paper-specific.
- Agent Skills: https://agentskills.io/
- Anthropic skills examples: https://github.com/anthropics/skills — inspect licensing; do not copy wholesale.

## Integrations to evaluate
GitHub API/App (least privilege); MCP (server/tool allowlists); Supabase (schema/RLS review); Playwright (isolated browser); Sentry (PII scrubbing); Search Console/GA4 (read-only); Cloudflare/Vercel (preview first); Semgrep/CodeQL/Gitleaks (pinned versions); Lighthouse/axe-core (automated checks plus manual review).

## Licensing policy
Do not bundle third-party source, skills, fonts, icons, screenshots or datasets until exact license and asset terms are checked. Prefer original procedures with upstream references and preserve required attribution.