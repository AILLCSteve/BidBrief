# Change Management Policy

**Version:** 1.0
**Effective Date:** 2026-03-03
**Owner:** Stephen Bartlett, C.E.O., Security Officer
**Company:** Additional Intelligence LLC
**Review Cycle:** Annual
**Next Review:** 2027-03-03

---

## 1. Purpose

This policy ensures that all changes to BidBrief production systems are
authorized, tested, reviewed, and documented before deployment. Uncontrolled
changes are a primary source of both security vulnerabilities and service
outages. This policy applies equally to code changes, configuration changes,
and infrastructure changes.

## 2. Scope

This policy applies to all changes affecting:

- BidBrief application code (any file in the repository)
- Production environment configuration (Render environment variables, service settings)
- Infrastructure configuration (Render service settings, custom domains, scaling)
- Third-party service integrations (adding, modifying, or removing vendors)
- Security policies and procedures (documents in `docs/policies/`)
- Database schema and migrations (when Neon DB is implemented)
- CI/CD pipeline configuration (`.github/workflows/`)

## 3. Change Classification

| Type | Definition | Examples |
|------|-----------|---------|
| **Standard** | Routine, low-risk change following established procedure | Dependency updates (non-breaking), documentation updates, minor bug fixes |
| **Normal** | Planned change with moderate risk, requires full review cycle | New features, significant refactors, new third-party integrations, policy updates |
| **Emergency** | Urgent fix required to restore security or availability; cannot wait for normal process | P1 security patch, critical production bug causing data loss or outage |

## 4. Standard Change Process (Normal Changes)

All Normal and Standard changes follow this process:

**Step 1 — Branch**
Create a feature branch from `master`:
```
git checkout -b [type]/[short-description]
# Examples: feat/pacp-analysis, fix/session-timeout, docs/soc2-policies
```

**Step 2 — Develop**
Make changes on the feature branch. Follow secure development guidelines:
- No hardcoded secrets or credentials in code
- Input validation on all user-supplied data
- Follow existing code patterns and architecture
- Write or update tests for changed behavior

**Step 3 — Test**
All tests must pass before opening a PR:
```
pytest tests/ -v
```
Expected: ALL PASS — no exceptions.

For security-impacting changes, also run:
```
bandit -r app.py services/ --severity-level medium
pip-audit -r requirements.txt
```

**Step 4 — Pull Request**
Open a PR against `master` on GitHub. PR description must include:
- What changed and why
- How it was tested
- Any security implications
- Rollback plan if deployment fails

**Step 5 — Review**
Security Officer (Stephen Bartlett) reviews the PR:
- Does it accomplish the stated purpose?
- Are there unintended security implications?
- Does it follow coding standards?
- Do tests adequately cover the changes?

Self-review is permitted for solo development, but the PR and review record
must still exist in GitHub.

**Step 6 — Merge and Deploy**
After approval:
- Merge to `master` via GitHub (squash merge preferred for clean history)
- Render auto-deploys from `master` (or manual deploy trigger)
- Verify deployment successful: check `/health` endpoint and test core flows

**Step 7 — Post-Deploy Verification**
Within 30 minutes of deployment:
- [ ] `/health` endpoint returns 200
- [ ] Login flow works
- [ ] Core analysis flow works (test upload + analyze)
- [ ] No unexpected errors in Render logs

## 5. Emergency Change Process

When a P1 or P2 security incident requires immediate action that cannot wait
for the standard review cycle:

**Step 1 — Authorize**
Incident Commander (Stephen Bartlett) verbally authorizes the emergency change.
Log authorization in the incident ticket.

**Step 2 — Implement**
Make the minimal change required to address the immediate threat. Do not
add unrelated changes under the cover of an emergency.

**Step 3 — Deploy**
Deploy immediately to production without waiting for full PR review.

**Step 4 — Retrospective Review (within 24 hours)**
After the emergency is resolved, open a PR documenting the emergency change:
- What was changed
- Why it was treated as an emergency
- Incident reference (INC-YYYY-NNN)
- Any follow-up work required

PR is reviewed and merged as part of incident closeout.

**Step 5 — Document**
Record in incident log that an emergency change was made, with commit reference.

## 6. Configuration Changes

Changes to Render environment variables (API keys, feature flags, secrets) follow
a simplified process:
- Change requires Incident Commander approval (can be self-approved for solo ops)
- Change logged in `docs/soc2/access_grant_log.md` with date, variable name (not value), reason
- Verify service still functions after change
- If change is a secret rotation: follow relevant runbook in Incident Response Plan

## 7. Third-Party Integration Changes

Adding or removing a third-party service (new AI provider, new database, new
monitoring tool) requires:
- Security assessment of the new vendor before integration
- Vendor added to `docs/soc2/vendor_inventory.md`
- DPA reviewed and recorded
- Risk Register updated with any new risks introduced
- Security Officer approval before integration goes to production

## 8. Rollback Plan

Every deployment must have a defined rollback path:

**Application code:** Render → Deploy → Previous deploy → Redeploy
(Available for: last 5 deployments in Render)

**Configuration/secrets:** Restore previous value in Render environment variables

**Database migrations (Phase 3+):** All migrations must include a `down` migration.
Test rollback in staging before production deployment.

**Rollback trigger:** If any post-deploy verification check fails, or if error rate
spikes above normal baseline within 30 minutes of deployment, execute rollback
immediately and investigate before re-attempting deployment.

## 9. Change Log

Git commit history is the authoritative change log for all code and configuration
changes. Commit messages must:
- Be descriptive and explain the _why_, not just the _what_
- Reference incident or feature IDs where applicable
- Follow format: `[type]: [description]` (feat, fix, docs, chore, security)

---

*Approved by: Stephen Bartlett, C.E.O., Security Officer*
*Approval date: 2026-03-03*
*Document location: `docs/policies/change_management_policy.md`*
