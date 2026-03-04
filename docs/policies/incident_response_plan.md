# Incident Response Plan

**Version:** 1.0
**Effective Date:** 2026-03-03
**Owner:** Stephen Bartlett, C.E.O., Security Officer
**Company:** Additional Intelligence LLC
**Review Cycle:** Annual + after every P1 incident
**Next Review:** 2027-03-03

---

## 1. Purpose

This plan defines how Additional Intelligence LLC detects, contains, eradicates,
recovers from, and communicates security incidents affecting BidBrief. All
personnel must know how to report incidents and understand this plan exists.

## 2. Scope

This plan applies to any security event affecting:
- BidBrief production systems or infrastructure
- Client data processed or stored by BidBrief
- Credentials, API keys, or secrets used by BidBrief
- Source code or deployment pipelines

## 3. Incident Classification

| Severity | Definition | Response SLA |
|----------|-----------|-------------|
| **P1 — Critical** | Active breach confirmed, client data exposed, production system compromised, or credential theft confirmed | Acknowledge within **1 hour**; contain within **4 hours**; notify affected clients within **72 hours** |
| **P2 — High** | Suspected breach, significant unpatched vulnerability in production, partial outage from attack, or unauthorized access attempt with evidence of partial success | Acknowledge within **4 hours**; resolve within **24 hours** |
| **P3 — Medium** | Security misconfiguration found, policy violation, non-critical CVE in production dependency, anomalous access pattern with no confirmed breach | Acknowledge within **1 business day**; resolve within **1 week** |

**P1 Examples:** Confirmed unauthorized login to admin account; client document accessed by unauthorized party; OpenAI API key used from unknown IP; database credentials leaked in git history.

**P2 Examples:** Multiple failed login attempts from single IP (brute force); critical CVE published for Flask or Python affecting production; Render infrastructure alert indicating possible intrusion; accidental exposure of session token in logs.

**P3 Examples:** Dependabot alert for medium-severity dependency; developer accidentally committed a non-production API key (rotated immediately); policy not acknowledged on schedule; log gaps detected.

## 4. Incident Response Team

| Role | Person | Contact | Responsibilities |
|------|--------|---------|-----------------|
| **Incident Commander** | Stephen Bartlett, C.E.O. | stephen@additionalintel.com | Leads all response activities; makes containment decisions; approves client communications; declares incident closed |
| **Technical Lead** | Stephen Bartlett, C.E.O. | stephen@additionalintel.com | Technical investigation; system containment; code remediation; root cause analysis |
| **Client Communications** | Stephen Bartlett, C.E.O. | stephen@additionalintel.com | Drafts and sends client notifications; manages external communications |

> For future team expansion: assign these three roles to separate individuals
> to enable separation of duties during high-pressure incident response.

## 5. Reporting an Incident

**Any person who suspects a security incident must:**

1. **Do NOT** attempt to investigate, fix, or contain the issue alone
2. **Do NOT** delete logs, overwrite files, or make system changes before reporting
3. **Do NOT** discuss details via public channels, social media, or unencrypted messaging
4. **Email** stephen@additionalintel.com within **1 hour** of discovery with:
   - What you observed (exact error messages, screenshots, log excerpts)
   - When you first noticed it (timestamp + timezone)
   - What systems or data may be affected
   - Any actions already taken

## 6. Response Phases

### Phase 1: Detection and Triage (0–1 hour)

- [ ] Incident report received by Incident Commander
- [ ] Initial severity assessed (P1 / P2 / P3)
- [ ] Incident log entry created:
  - GitHub Issue in BidBrief repo with label `security-incident`
  - OR dedicated incident log at `docs/soc2/incident_log.md`
- [ ] Response team notified
- [ ] Evidence preservation begins: do NOT restart servers or clear logs until forensics complete

### Phase 2: Containment (hours 1–4 for P1)

**Universal containment steps:**
- [ ] Identify the attack vector or compromise point
- [ ] Block the source if identifiable (Render IP block, API key revocation)
- [ ] Revoke active sessions if user accounts involved (app restart clears in-memory sessions)
- [ ] Take snapshot of current app logs before any changes

**Credential/API key compromise:**
- [ ] Immediately revoke the compromised credential at the provider (Render, OpenAI, Tavily, GitHub)
- [ ] Generate replacement credential
- [ ] Update environment variable in Render dashboard
- [ ] Verify service resumes normally
- [ ] Search git history: `git log --all -p | grep -i "[first 6 chars of exposed key]"`
- [ ] If found in git history: purge with BFG Repo Cleaner, force push, notify GitHub

**Unauthorized access to application:**
- [ ] Identify affected account(s) in session logs
- [ ] Invalidate all active sessions (restart app if in-memory sessions)
- [ ] Reset affected account credentials
- [ ] Determine scope: what was accessed, exported, or modified?

**Client data exposure:**
- [ ] Identify exactly which client data was accessed and by whom
- [ ] Document: data types, records/files involved, time window of exposure
- [ ] Preserve all evidence for forensic review
- [ ] Escalate immediately to Phase 5 (Client Notification) if P1

### Phase 3: Eradication

- [ ] Root cause confirmed (not just suspected)
- [ ] Vulnerability or misconfiguration patched in code or configuration
- [ ] Malicious access paths removed (unauthorized accounts deleted, backdoors closed)
- [ ] Patch deployed via standard change management process (PR + review + test)
- [ ] Verify no secondary or related vulnerabilities remain
- [ ] All rotated credentials verified functional in production

### Phase 4: Recovery

- [ ] Service restored from verified clean state
- [ ] All systems functioning normally — spot-check core user flows
- [ ] Enhanced monitoring activated for 72 hours post-recovery
- [ ] Confirm no data integrity issues (analysis results not tampered with)
- [ ] Incident status updated to "Contained — Monitoring"

### Phase 5: Client Notification (P1 only, or when client data confirmed exposed)

**Timing:** Within 72 hours of confirmed client data exposure.

**Notification must include:**
- What happened (factual, non-speculative)
- What client data was involved (specific data types)
- Time window of potential exposure
- What Additional Intelligence LLC did to contain and remediate
- What the client should do (if anything)
- Contact for client questions: stephen@additionalintel.com

**Template subject line:** `Important Security Notice from Additional Intelligence LLC — Action May Be Required`

**Notification delivery:** Direct email to client primary contact on file. BCC security@[domain] for record.

**Log all notifications** in the incident log with: recipient, date sent, method, client response.

### Phase 6: Post-Incident Review (within 5 business days of closure)

- [ ] Complete timeline of events documented (detection → containment → eradication → recovery)
- [ ] Root cause confirmed and documented
- [ ] What worked well in the response (preserve)
- [ ] What did not work (improve)
- [ ] Action items created with owner and due date
- [ ] IRP updated if gaps found in this plan
- [ ] Incident log entry closed with resolution summary
- [ ] Lessons learned shared with all personnel (even if small team)

## 7. Runbooks

### Runbook A: API Key or Secret Exposed

**Trigger:** Any credential (OpenAI key, Render deploy key, Tavily key, SECRET_KEY) is suspected or confirmed to be exposed.

```
1. IMMEDIATELY revoke the key in the provider's dashboard
   - OpenAI: platform.openai.com → API keys → Revoke
   - Render: dashboard.render.com → Account Settings → API Keys → Revoke
   - Tavily: app.tavily.com → API → Revoke

2. Generate a new key in the same provider dashboard

3. Update the environment variable in Render:
   Render → [Service] → Environment → Update variable → Save → Redeploy

4. Verify service is functional:
   - Test login at production URL
   - Test a document analysis end-to-end

5. Search git history for the exposed key:
   git log --all -p | grep "[first_8_chars_of_exposed_key]"

6. If found in git history:
   a. Install BFG Repo Cleaner: https://rtyley.github.io/bfg-repo-cleaner/
   b. java -jar bfg.jar --replace-text exposed_key.txt .git
   c. git reflog expire --expire=now --all
   d. git gc --prune=now --aggressive
   e. git push --force-with-lease origin master
   f. Notify GitHub Support of the exposure

7. Document: key name, exposure window (estimated), vector, resolution date
```

### Runbook B: Unauthorized Account Access Confirmed

**Trigger:** Evidence of login from unexpected location/time, admin access by non-admin, or account used after offboarding.

```
1. Identify the compromised account from audit logs or session records

2. Immediately invalidate all sessions:
   - If session is in active_sessions dict: identify session token and remove
   - If uncertain scope: restart the application on Render to clear all in-memory sessions
     Render → [Service] → Manual Deploy → Redeploy (clears all sessions)

3. Disable or delete the compromised account:
   - Update AUTH_USER* environment variables in Render to remove or change credentials
   - Redeploy to pick up changes

4. Review logs for what was accessed:
   - Check application logs in Render log drain
   - Look for: file uploads, analysis runs, export downloads, admin actions
   - Time-box the suspicious activity

5. If client data was accessed → escalate to Phase 5 (Client Notification)

6. Reset credentials for compromised account with new strong password

7. Enable/verify MFA on all admin accounts

8. Document: account affected, access window, actions taken during compromise
```

### Runbook C: Dependency Vulnerability (CVE in requirements.txt)

**Trigger:** GitHub Dependabot alert, pip-audit finding, or published security advisory for a dependency.

```
1. Assess severity:
   - Critical/High: follow P1/P2 response timeline
   - Medium/Low: follow P3 timeline

2. Determine exploitability in BidBrief context:
   - Is the vulnerable code path reachable?
   - Does BidBrief use the vulnerable feature?
   - Is it exploitable without auth? (higher risk)

3. Update the package:
   pip install --upgrade [package_name]
   pip freeze | grep [package_name]  # Note the new version

4. Update requirements.txt with pinned new version

5. Run full test suite:
   pytest tests/ -v
   Expected: ALL PASS

6. If tests pass: create PR, get review, merge, deploy to Render

7. Close Dependabot alert with reference to the fixing commit

8. If tests fail: investigate compatibility, do not deploy broken code
   Create P2 issue to track fix with timeline per vulnerability severity
```

### Runbook D: Production Outage (Suspected Attack)

**Trigger:** Render alerts showing app down, health check failing, or anomalous traffic pattern.

```
1. Check Render status page: status.render.com
   - If Render platform incident: monitor and wait; document in incident log

2. Check application logs in Render dashboard or log drain:
   - Look for: OOM errors, connection floods, unusual request patterns

3. If DDoS or request flood suspected:
   - Render → [Service] → Settings → Enable maintenance mode (if available)
   - Or temporarily restrict access while investigating

4. If application crash (not infrastructure):
   - Review last deployment: did a recent change cause this?
   - If yes: roll back in Render → Deploy → Previous deploy → Redeploy

5. Verify restoration:
   - Hit /health endpoint: should return 200
   - Test full login flow

6. Document: outage start/end times, root cause, resolution steps
```

## 8. Evidence Preservation

During any P1 or P2 incident, preserve the following before making any changes:

- [ ] Screenshot or export of current application logs (Render log view)
- [ ] Export from log drain service covering incident window
- [ ] Screenshot of active sessions (if admin dashboard accessible)
- [ ] Network traffic logs if available (Render network tab)
- [ ] Git log of recent commits: `git log --oneline -20`
- [ ] Environment variable audit: confirm no unexpected changes (Render dashboard)

Store evidence in: `docs/soc2/incident_evidence/[date]-[incident-id]/`

## 9. Incident Log

All incidents (P1, P2, P3) must be logged. Maintain log at:
`docs/soc2/incident_log.md`

Required fields per incident:

| Field | Description |
|-------|-------------|
| Incident ID | Sequential: INC-2026-001, INC-2026-002, etc. |
| Date/Time Detected | Timestamp in UTC |
| Severity | P1 / P2 / P3 |
| Status | Open / Contained / Closed |
| Description | Brief factual description |
| Systems Affected | Which systems/data involved |
| Client Data Involved | Yes/No — if Yes, which clients |
| Root Cause | Confirmed root cause |
| Resolution | What was done to resolve |
| Notifications Sent | Client/regulatory notifications, dates |
| Closed Date | Date incident formally closed |
| Lessons Learned | Key improvements made |

---

*Approved by: Stephen Bartlett, C.E.O., Security Officer*
*Approval date: 2026-03-03*
*Document location: `docs/policies/incident_response_plan.md`*
