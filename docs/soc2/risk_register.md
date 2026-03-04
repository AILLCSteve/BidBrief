# Risk Register

**Owner:** Stephen Bartlett, C.E.O., Security Officer
**Company:** Additional Intelligence LLC
**Last Updated:** 2026-03-03
**Review Cycle:** Annual minimum; updated when new risks identified or risk posture changes

---

## Risk Scoring Methodology

**Likelihood scale:**
- 1 = Rare (unlikely to occur in most circumstances)
- 2 = Unlikely (could occur but probably won't)
- 3 = Possible (might occur at some point)
- 4 = Likely (will probably occur in most circumstances)
- 5 = Almost Certain (expected to occur)

**Impact scale:**
- 1 = Negligible (no material harm to business or clients)
- 2 = Minor (minimal impact, easily recoverable)
- 3 = Moderate (noticeable impact, some client disruption or data exposure)
- 4 = Major (significant client harm, regulatory concern, reputational damage)
- 5 = Catastrophic (business-threatening, large-scale data breach, legal action)

**Risk Score** = Likelihood × Impact (range: 1–25)

**Risk Treatment options:**
- **Mitigate** — implement controls to reduce likelihood or impact
- **Accept** — risk level is acceptable; document rationale and monitor
- **Transfer** — shift risk via insurance, contract terms, or vendor responsibility
- **Avoid** — eliminate the risk by not doing the activity

---

## Active Risks

### Technical Risks

| ID | Risk | Likelihood | Impact | Score | Treatment | Mitigating Controls | Phase | Owner | Status |
|----|------|-----------|--------|-------|-----------|---------------------|-------|-------|--------|
| R-001 | In-memory session loss on Gunicorn worker restart (single worker, `max_requests=0`) | 3 | 3 | 9 | Mitigate | Neon DB session persistence (Phase 3); single worker mitigates cross-session leakage | Phase 3 | Stephen Bartlett | Open |
| R-002 | Brute-force attack on `/auth/login` endpoint (no rate limiting) | 3 | 4 | 12 | Mitigate | Flask-Limiter rate limiting (Phase 2) | Phase 2 | Stephen Bartlett | Open |
| R-003 | Credential stuffing attack on login endpoint | 3 | 4 | 12 | Mitigate | Rate limiting (Phase 2); MFA on admin (Phase 3); strong password policy | Phase 2/3 | Stephen Bartlett | Open |
| R-004 | Dependency vulnerability (known CVE in `requirements.txt` package) | 4 | 3 | 12 | Mitigate | GitHub Dependabot (Phase 1); pip-audit in CI (Phase 2); vulnerability SLA policy | Phase 1/2 | Stephen Bartlett | Open |
| R-005 | API key or secret leaked in source code or application logs | 2 | 5 | 10 | Mitigate | Secrets in env vars only; git history scans; log sanitization (Phase 2) | Phase 2 | Stephen Bartlett | Open |
| R-006 | No persistent audit trail — logs lost on process restart | 3 | 4 | 12 | Mitigate | Log drain to external service (Phase 2); Neon DB audit log table (Phase 3) | Phase 2/3 | Stephen Bartlett | Open |
| R-007 | Missing security headers enabling clickjacking / XSS / MIME attacks | 3 | 3 | 9 | Mitigate | Flask-Talisman (Phase 2) — HSTS, CSP, X-Frame-Options, X-Content-Type-Options | Phase 2 | Stephen Bartlett | Open |
| R-008 | Malicious or oversized file upload bypassing validation | 2 | 3 | 6 | Mitigate | File type/size validation already partial; Phase 2 hardens with MIME check + 50MB limit | Phase 2 | Stephen Bartlett | Open |
| R-009 | Prompt injection via maliciously crafted uploaded document | 2 | 3 | 6 | Mitigate | Document content sandboxed before LLM; system prompt hardening; output validation | Phase 2 | Stephen Bartlett | Open |
| R-010 | No MFA on admin accounts | 3 | 4 | 12 | Mitigate | MFA on admin role (Phase 3); MFA on Render and GitHub (Phase 1 — manual) | Phase 1/3 | Stephen Bartlett | Open |
| R-011 | User management via env vars — no deprovisioning UI or audit trail | 3 | 3 | 9 | Mitigate | Database-backed user management with access log (Phase 3) | Phase 3 | Stephen Bartlett | Open |
| R-012 | No monitoring or alerting — security incidents may go undetected | 3 | 4 | 12 | Mitigate | Log drain (Phase 2); auth failure alerting (Phase 4); uptime monitoring (Phase 1) | Phase 1/2/4 | Stephen Bartlett | Open |

### Data / Confidentiality Risks

| ID | Risk | Likelihood | Impact | Score | Treatment | Mitigating Controls | Phase | Owner | Status |
|----|------|-----------|--------|-------|-----------|---------------------|-------|-------|--------|
| R-013 | Client document content sent to OpenAI without client awareness | 2 | 5 | 10 | Mitigate | ToS disclosure (Phase 1); OpenAI DPA reviewed and documented | Phase 1 | Stephen Bartlett | Open |
| R-014 | Unauthorized access to client documents by BidBrief personnel (insider threat) | 1 | 5 | 5 | Accept + Mitigate | RBAC; access logging (Phase 3); policy prohibitions (AUP §4) | Phase 3 | Stephen Bartlett | Open |
| R-015 | Client data retained longer than stated retention period | 2 | 4 | 8 | Mitigate | Automated session cleanup (`cleanup_old_sessions`); retention policy published | Phase 1 | Stephen Bartlett | Open — partially mitigated |
| R-016 | Export files (Excel) not deleted after session expiry | 3 | 3 | 9 | Mitigate | Session cleanup covers `/exports/` directory; verify in Phase 2 code review | Phase 2 | Stephen Bartlett | Open |

### Infrastructure / Availability Risks

| ID | Risk | Likelihood | Impact | Score | Treatment | Mitigating Controls | Phase | Owner | Status |
|----|------|-----------|--------|-------|-----------|---------------------|-------|-------|--------|
| R-017 | Render platform outage causing BidBrief unavailability | 2 | 4 | 8 | Accept + Transfer | Stateless architecture enables fast redeploy; Render SLA; status monitoring | Phase 1 | Stephen Bartlett | Open |
| R-018 | OpenAI API outage preventing document analysis | 2 | 4 | 8 | Accept + Mitigate | Graceful error messages; consider fallback model (Phase 3+) | Future | Stephen Bartlett | Open |
| R-019 | Single Gunicorn worker limits availability under load | 3 | 3 | 9 | Accept | Single worker required to preserve in-memory sessions; resolved by Phase 3 DB migration | Phase 3 | Stephen Bartlett | Open |
| R-020 | No rate limiting — API abuse could exhaust OpenAI API quota | 3 | 3 | 9 | Mitigate | Flask-Limiter on analyze and upload endpoints (Phase 2) | Phase 2 | Stephen Bartlett | Open |

### Organizational / Process Risks

| ID | Risk | Likelihood | Impact | Score | Treatment | Mitigating Controls | Phase | Owner | Status |
|----|------|-----------|--------|-------|-----------|---------------------|-------|-------|--------|
| R-021 | No formal change review — untested change deployed to production | 2 | 4 | 8 | Mitigate | Branch protection on master (Phase 1); CI/CD tests (Phase 2); Change Management Policy | Phase 1/2 | Stephen Bartlett | Open |
| R-022 | Key person dependency — all knowledge held by one person | 3 | 4 | 12 | Accept + Mitigate | Documentation of systems, runbooks, credentials in secure location; recovery planning | Ongoing | Stephen Bartlett | Open |
| R-023 | Vendor (OpenAI, Render, Tavily) security incident exposes client data | 1 | 5 | 5 | Transfer + Mitigate | DPAs reviewed; vendor SOC 2 reports obtained; minimal data sent to vendors | Phase 1 | Stephen Bartlett | Open |
| R-024 | No Privacy Policy — clients unaware of data handling | 2 | 4 | 8 | Mitigate | Privacy Policy required (CC2.3 gap); must publish before client onboarding | Phase 1 | Stephen Bartlett | Open |

---

## Risk-to-Control Mapping

| Risk ID | Risk (short) | Primary Control | Location | Implemented? |
|---------|-------------|----------------|---------|-------------|
| R-001 | Session loss on restart | Neon DB sessions | Phase 3 | No |
| R-002 | Brute force on login | Flask-Limiter | Phase 2 / `app.py` | No |
| R-003 | Credential stuffing | Rate limiting + MFA | Phase 2/3 | No |
| R-004 | Dependency CVE | Dependabot + pip-audit | Phase 1/2 | Partial (Dependabot pending) |
| R-005 | API key leaked | Env vars + log sanitization | Phase 2 | Partial |
| R-006 | No persistent audit log | Log drain + Neon DB | Phase 2/3 | No |
| R-007 | Missing security headers | Flask-Talisman | Phase 2 / `app.py` | No |
| R-008 | Malicious upload | File type/size validation | Phase 2 / `app.py` | Partial |
| R-009 | Prompt injection | Prompt hardening | Phase 2 | No |
| R-010 | No MFA admin | MFA Phase 3 + Render/GitHub MFA | Phase 1/3 | No |
| R-011 | No user mgmt UI | DB-backed user management | Phase 3 | No |
| R-012 | No monitoring | Log drain + alerting | Phase 1/2/4 | No |
| R-013 | OpenAI undisclosed | ToS + DPA | Phase 1 | Partial |
| R-014 | Insider threat | RBAC + access logging | Phase 3 + existing | Partial |
| R-015 | Over-retention | Session cleanup + policy | Phase 1 | Partial |
| R-016 | Export not deleted | Session cleanup verification | Phase 2 | Verify needed |
| R-017 | Render outage | Stateless design + Render SLA | Design | Partial |
| R-018 | OpenAI outage | Graceful degradation | Existing | Partial |
| R-019 | Single worker | Phase 3 DB migration | Phase 3 | No |
| R-020 | API abuse / quota | Flask-Limiter | Phase 2 | No |
| R-021 | Untested deploy | Branch protection + CI/CD | Phase 1/2 | No |
| R-022 | Key person risk | Documentation + runbooks | Ongoing | Partial |
| R-023 | Vendor breach | DPAs + minimal data | Phase 1 | Partial |
| R-024 | No Privacy Policy | Publish Privacy Policy | Phase 1 | No |

---

## Closed / Resolved Risks

| ID | Risk | Resolution | Date Closed |
|----|------|-----------|------------|
| — | No closed risks yet | — | — |

---

_Last updated: 2026-03-03_
_Next review: 2027-03-03 (or sooner if new risks identified)_
