# SOC 2 Type I Security Design
**Date:** 2026-03-03
**Status:** Approved — awaiting phased implementation

---

## Decision Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| SOC 2 Type | **Type I** | Starting from zero controls — prove design first, then Type II proves operation |
| Trust Service Criteria | **Security (CC) + Confidentiality (C)** | CC is mandatory; C directly addresses client concern "you have our files" |
| Compliance approach | **DIY / In-House** | No compliance platform SaaS cost; Claude Code serves as requirements authority |
| Implementation strategy | **Phased, preserving functionality** | Never break existing features; each phase independently deployable |

---

## Requirements Authority

All SOC 2 control requirements are documented in:
`docs/soc2/SOC2_TYPE1_REQUIREMENTS.md`

That file is the single source of truth for:
- What each criterion requires
- How to verify it in BidBrief's codebase
- Current pass/fail/gap status
- Priority of each gap (P1 / P2 / P3)

---

## Current Baseline

**What passes today (10 controls):** Auth, RBAC, session TTL, upload encryption, auto-deletion, HTTPS, env var secrets, random session tokens, graceful degradation.

**Gap count:** 38 P1 gaps, 19 P2 gaps, 8 P3 gaps (see `docs/soc2/SOC2_TYPE1_REQUIREMENTS.md` Gap Summary).

**Biggest technical gaps:**
1. No rate limiting anywhere
2. No persistent audit log storage
3. No CI/CD security scanning (Dependabot, pip-audit, Bandit)
4. No security headers (HSTS, CSP, etc.)
5. No branch protection on master
6. No MFA / user management UI

**Biggest policy gaps:**
1. No Information Security Policy
2. No Incident Response Plan
3. No Privacy Policy or ToS
4. No vendor inventory / DPAs
5. No Risk Register
6. No data classification policy

---

## Implementation Philosophy

> **Preserve functionality at every step. Each phase must leave the app fully operational.**

- Policy documents and technical controls are separate work streams
- Technical changes follow the existing architecture (Flask/Python, Render deployment)
- No database migration required for Phase 1 (policy + lightweight controls)
- Database migration (Neon DB) is a Phase 2 prerequisite for persistent audit logs
- Every change gets its own PR with tests before merging

---

## Phased Approach (High Level)

### Phase 1 — Foundation (Policies + Quick Wins)
*Target: ~4 weeks | No app code changes required*
- Write all 7 policy documents
- Enable GitHub branch protection and Dependabot
- Configure Render log drain
- Set up uptime monitoring
- Vendor inventory + DPA reviews (OpenAI, Render, Tavily)
- Risk Register + System Description

### Phase 2 — Technical Controls: Access & Headers
*Target: ~3 weeks | Minimal app changes*
- Add rate limiting to auth and API endpoints (Flask-Limiter)
- Add security headers (Flask-Talisman)
- Implement idle session timeout
- Add file size limits and MIME validation to upload
- Add CI/CD pipeline (GitHub Actions) with pip-audit + Bandit

### Phase 3 — Persistent Audit Logging
*Target: ~4 weeks | Requires Neon DB migration*
- Migrate to Neon DB (PostgreSQL)
- Persistent audit log table (who accessed what, when)
- Log retention enforcement
- User management UI (add/remove/disable users without env var restarts)

### Phase 4 — Monitoring & Incident Response
*Target: ~3 weeks*
- Alerting on auth failure thresholds
- Incident response plan operationalized
- Quarterly access review process
- Annual penetration test scheduled

### Phase 5 — Audit Readiness
*Target: ~2 weeks*
- Final gap review against SOC2_TYPE1_REQUIREMENTS.md
- System Description document finalized
- Evidence package assembled
- Auditor engaged

---

## Files Created

| File | Purpose |
|------|---------|
| `docs/soc2/SOC2_TYPE1_REQUIREMENTS.md` | Master requirements + live audit checklist |
| `docs/plans/2026-03-03-soc2-security-design.md` | This file — design decisions and phased approach |

---

## Next Step

Run the `writing-plans` skill against Phase 1 to generate a detailed, step-by-step implementation plan with specific files to create, content outlines for each policy, and verification criteria for each task.
