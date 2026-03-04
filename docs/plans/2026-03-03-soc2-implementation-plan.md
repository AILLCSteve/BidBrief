# SOC 2 Type I Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Achieve SOC 2 Type I readiness (Security + Confidentiality criteria) for BidBrief without breaking existing functionality at any step.

**Architecture:** Five sequential phases — Phase 1 is pure documentation with zero app changes, Phases 2-4 add technical controls incrementally, Phase 5 assembles the audit evidence package. Each phase is independently deployable and verifiable against `docs/soc2/SOC2_TYPE1_REQUIREMENTS.md`.

**Tech Stack:** Python/Flask, Render (hosting), GitHub (source control), Neon DB (PostgreSQL, Phase 3+), Flask-Limiter, Flask-Talisman, GitHub Actions CI/CD, pip-audit, Bandit (SAST)

**Reference Documents:**
- Requirements + audit checklist: `docs/soc2/SOC2_TYPE1_REQUIREMENTS.md`
- Design decisions: `docs/plans/2026-03-03-soc2-security-design.md`

**Critical Rule:** Every task that touches `app.py` or any service file MUST run the full test suite before committing (`pytest tests/ -v`). Never commit a broken app.

---

## PHASE 1 — Foundation: Policies and Quick Wins
*No changes to `app.py` or any service file. Pure documentation + repo settings.*
*Estimated: 3–4 weeks calendar time, ~8 hours of actual work*

---

### Task 1.1: Create Policy Directory Structure

**Files:**
- Create: `docs/policies/` (directory)
- Create: `docs/policies/README.md`

**Step 1: Create the directory and index**

```bash
mkdir -p docs/policies
```

Create `docs/policies/README.md` with this content:

```markdown
# BidBrief Security Policies

This directory contains all security policies required for SOC 2 Type I compliance.

| Policy | File | Last Reviewed | Owner |
|--------|------|---------------|-------|
| Information Security Policy | information_security_policy.md | 2026-03-03 | [Name] |
| Access Control Policy | access_control_policy.md | 2026-03-03 | [Name] |
| Incident Response Plan | incident_response_plan.md | 2026-03-03 | [Name] |
| Data Classification Policy | data_classification_policy.md | 2026-03-03 | [Name] |
| Change Management Policy | change_management_policy.md | 2026-03-03 | [Name] |
| Vulnerability Management Policy | vulnerability_management_policy.md | 2026-03-03 | [Name] |
| Acceptable Use Policy | acceptable_use_policy.md | 2026-03-03 | [Name] |

All policies reviewed annually. Next review due: 2027-03-03.
```

**Step 2: Verify directory exists**

```bash
ls docs/policies/
```
Expected: `README.md`

**Step 3: Commit**

```bash
git add docs/policies/README.md
git commit -m "docs: create security policies directory structure"
```

---

### Task 1.2: Write Information Security Policy

**Files:**
- Create: `docs/policies/information_security_policy.md`

**Step 1: Create the policy document**

Write `docs/policies/information_security_policy.md` with ALL of the following sections (auditors check for completeness):

```markdown
# Information Security Policy

**Version:** 1.0
**Effective Date:** [DATE]
**Owner:** [Security Officer Name], [Title]
**Review Cycle:** Annual
**Next Review:** [DATE + 1 year]

---

## 1. Purpose and Scope

This policy establishes the information security requirements for BidBrief,
an AI-powered document analysis platform operated by Additional Intelligence LLC.
It applies to all personnel, contractors, and systems that access, process, or
store BidBrief data or infrastructure.

## 2. Security Objectives

BidBrief is committed to:
- **Confidentiality:** Protecting client documents and data from unauthorized disclosure
- **Integrity:** Ensuring data accuracy and preventing unauthorized modification
- **Availability:** Maintaining system availability per committed service levels

## 3. Roles and Responsibilities

| Role | Person | Responsibilities |
|------|--------|-----------------|
| Security Officer | [Name] | Owns this policy; conducts security reviews; approves exceptions |
| Developer | [Name] | Follows secure development standards; reports vulnerabilities |
| All Personnel | Everyone | Completes security training; reports incidents; follows this policy |

## 4. Asset Classification

All information assets are classified per the Data Classification Policy
(`data_classification_policy.md`). Client documents uploaded to BidBrief
are classified as **Confidential** by default.

## 5. Access Control

Access to BidBrief systems is governed by the Access Control Policy
(`access_control_policy.md`). Key principles:
- Least privilege: users receive minimum access needed for their role
- Unique accounts: no shared credentials
- Access reviews conducted quarterly

## 6. Acceptable Use

All personnel must comply with the Acceptable Use Policy (`acceptable_use_policy.md`).
Violations are handled per Section 9 of this document.

## 7. Incident Response

Security incidents are handled per the Incident Response Plan
(`incident_response_plan.md`). All personnel must report suspected
incidents within 1 hour of discovery to [security contact email].

## 8. Change Management

All changes to BidBrief production systems follow the Change Management
Policy (`change_management_policy.md`). Emergency changes require
retrospective approval within 24 hours.

## 9. Violation Enforcement

Policy violations are reviewed by the Security Officer. Depending on
severity, consequences range from retraining to contract termination.
Violations that expose client data are treated as security incidents.

## 10. Exceptions

Exceptions to this policy require written approval from the Security Officer.
All approved exceptions are logged with: date, requester, justification,
compensating controls, and expiry date.

## 11. Policy Review

This policy is reviewed annually or after any significant security incident.
Changes require Security Officer approval and are communicated to all personnel.

---
*Approved by: [Security Officer Name] | Date: [DATE]*
```

**Step 2: Verify the policy contains all required sections**

Check that these 11 sections are present:
- [ ] Purpose and Scope
- [ ] Security Objectives (CIA triad)
- [ ] Roles and Responsibilities with named owner
- [ ] Asset Classification reference
- [ ] Access Control reference
- [ ] Acceptable Use reference
- [ ] Incident Response reference
- [ ] Change Management reference
- [ ] Violation Enforcement
- [ ] Exceptions process
- [ ] Policy Review cycle

**Step 3: Commit**

```bash
git add docs/policies/information_security_policy.md
git commit -m "docs: add Information Security Policy (SOC2 CC1.1, CC5.3)"
```

---

### Task 1.3: Write Access Control Policy

**Files:**
- Create: `docs/policies/access_control_policy.md`

**Step 1: Create the policy document**

```markdown
# Access Control Policy

**Version:** 1.0
**Effective Date:** [DATE]
**Owner:** [Security Officer Name]
**Review Cycle:** Annual

---

## 1. Purpose

This policy defines how access to BidBrief systems and data is granted,
managed, reviewed, and revoked. It implements the principle of least privilege.

## 2. Scope

Applies to all accounts with access to: BidBrief application, Render dashboard,
GitHub repository, OpenAI API, Tavily API, and any production environment.

## 3. Access Roles

| Role | Description | Who Assigns |
|------|-------------|-------------|
| `admin` | Full system access including user management, config, all sessions | Security Officer |
| `user` | Analysis and export only; cannot access admin functions | Admin |

## 4. Provisioning Process

**Step 1:** Requester submits access request to Security Officer (email or ticket)
**Step 2:** Security Officer reviews: is this person authorized? Does role match need?
**Step 3:** Security Officer creates account or approves account creation
**Step 4:** New user is notified and acknowledges Acceptable Use Policy
**Step 5:** Access grant is logged in the Access Grant Log (see Section 8)

New accounts default to `user` role. Admin role requires explicit approval.

## 5. Password Requirements

- Minimum 12 characters
- Mix of uppercase, lowercase, numbers, and symbols
- Not reused from other services
- Changed immediately if compromise suspected

## 6. Multi-Factor Authentication

MFA is required for:
- Render dashboard access
- GitHub repository access
- Any admin-role BidBrief account (when MFA is implemented in app)

## 7. Access Reviews

The Security Officer conducts a quarterly access review:
- Verify all accounts belong to current, authorized personnel
- Verify role assignments match current responsibilities
- Remove or downgrade any excess access
- Document review completion and findings

Quarterly review months: March, June, September, December.

## 8. Access Grant Log

Maintain a log at `docs/soc2/access_grant_log.md` with:
- Date granted
- Username / identifier
- Role assigned
- Approved by
- Business justification

## 9. Offboarding / Access Revocation

When a person's access needs to be removed:
**Same-day action required for:**
- Terminations (voluntary or involuntary)
- Suspected credential compromise

**Within 5 business days:**
- Role changes
- Contractor engagement endings

Offboarding checklist:
- [ ] BidBrief account disabled or deleted
- [ ] Render dashboard access removed
- [ ] GitHub repository access removed
- [ ] API keys rotated if shared
- [ ] Confirmation logged in Access Grant Log

## 10. Shared / Service Accounts

Service accounts (e.g., deployment keys) are:
- Named to identify their purpose (not generic)
- Not used for human login
- Rotated annually or on personnel change
- Documented in vendor inventory

---
*Approved by: [Security Officer Name] | Date: [DATE]*
```

**Step 2: Verify all sections present**

- [ ] Roles defined with descriptions
- [ ] Provisioning process step-by-step
- [ ] Password requirements
- [ ] MFA requirements
- [ ] Quarterly review schedule
- [ ] Access Grant Log location defined
- [ ] Offboarding checklist
- [ ] Service accounts policy

**Step 3: Create the Access Grant Log template**

Create `docs/soc2/access_grant_log.md`:

```markdown
# Access Grant Log

| Date | Username | Role | Approved By | Justification | Status |
|------|----------|------|-------------|---------------|--------|
| 2026-03-03 | [admin_user] | admin | [Name] | Founding team | Active |
| 2026-03-03 | [user_1] | user | [Name] | Client demo | Active |
```

**Step 4: Commit**

```bash
git add docs/policies/access_control_policy.md docs/soc2/access_grant_log.md
git commit -m "docs: add Access Control Policy and Access Grant Log (SOC2 CC6.2, CC6.3)"
```

---

### Task 1.4: Write Data Classification Policy

**Files:**
- Create: `docs/policies/data_classification_policy.md`

**Step 1: Create the policy document**

```markdown
# Data Classification Policy

**Version:** 1.0
**Effective Date:** [DATE]
**Owner:** [Security Officer Name]
**Review Cycle:** Annual

---

## 1. Purpose

Defines how BidBrief classifies data assets, the handling requirements
for each classification level, and the retention and disposal rules.

## 2. Classification Levels

### PUBLIC
Information intended for public disclosure.
**Examples:** Marketing website content, public documentation, open-source code
**Handling:** No restrictions on access or distribution

### INTERNAL
Information for internal use; not for public distribution but not sensitive.
**Examples:** Internal process docs, meeting notes, non-sensitive config
**Handling:** Do not share externally without approval; transmit over HTTPS

### CONFIDENTIAL
Sensitive information whose unauthorized disclosure could harm the business
or its clients.
**Examples:** Client uploaded documents, API keys, user credentials, audit logs,
source code, analysis results, contract terms
**Handling:**
- Encrypt in transit (TLS 1.2+) and at rest
- Access restricted to authorized personnel only
- Log all access
- Do not share with third parties without client consent and DPA
- Do not store beyond retention period

### RESTRICTED
Highest sensitivity. Disclosure could cause serious harm.
**Examples:** Authentication secrets, production database credentials,
private encryption keys
**Handling:** All CONFIDENTIAL requirements plus:
- Access limited to Security Officer and essential personnel only
- Stored in secrets manager / environment variables (never in code)
- Rotated on any suspected compromise
- Dual-person authorization for access where feasible

## 3. Data Inventory

| Data Type | Classification | Location | Retention | Third Parties |
|-----------|---------------|----------|-----------|---------------|
| Client uploaded documents | CONFIDENTIAL | Encrypted temp storage | Session duration (max 24h) | OpenAI API (analysis) |
| Analysis results | CONFIDENTIAL | In-memory session | Session duration (max 24h) | None |
| Audit logs | CONFIDENTIAL | App logs / log drain | 12 months | Log aggregation service |
| User credentials (hashed) | RESTRICTED | Environment variables | Until offboarded | None |
| OpenAI API key | RESTRICTED | Environment variable | Until rotated | None |
| Render deploy credentials | RESTRICTED | Render dashboard | Until rotated | Render |

## 4. Third-Party Data Sharing

Before sending CONFIDENTIAL or RESTRICTED data to any third-party service:
1. Verify a Data Processing Agreement (DPA) exists with the vendor
2. Verify the vendor's security certifications (SOC 2, ISO 27001)
3. Document the sharing in the vendor inventory

**Current third-party data flows:**
- Client document text → OpenAI API (for analysis). OpenAI DPA: [link/date reviewed]
- No other CONFIDENTIAL data shared with third parties

## 5. Data Retention Schedule

| Data Type | Retention Period | Disposal Method |
|-----------|-----------------|-----------------|
| Uploaded documents | Session duration (≤24h) | Secure auto-deletion |
| In-memory session data | Session duration (≤24h) | Process cleanup |
| Application logs | 12 months | Log service auto-expiry |
| Audit logs | 12 months minimum | Log service auto-expiry |
| Policy documents | Indefinite (version controlled) | Git history |

## 6. Disposal

CONFIDENTIAL and RESTRICTED data must be disposed of securely:
- **Digital data:** Overwrite or cryptographic erasure (not just file deletion)
- **Verification:** Deletion must be logged with: data type, date, method, confirming person
- **Customer requests:** Data deletion requests fulfilled within 30 days

---
*Approved by: [Security Officer Name] | Date: [DATE]*
```

**Step 2: Verify all sections present**

- [ ] 4 classification levels defined with examples
- [ ] Data inventory table
- [ ] Third-party data sharing requirements
- [ ] Retention schedule
- [ ] Disposal requirements

**Step 3: Commit**

```bash
git add docs/policies/data_classification_policy.md
git commit -m "docs: add Data Classification Policy (SOC2 CC3.1, C1.1, C1.2)"
```

---

### Task 1.5: Write Incident Response Plan

**Files:**
- Create: `docs/policies/incident_response_plan.md`

**Step 1: Create the IRP document**

```markdown
# Incident Response Plan

**Version:** 1.0
**Effective Date:** [DATE]
**Owner:** [Security Officer Name]
**Review Cycle:** Annual + after every P1 incident

---

## 1. Purpose

Defines how BidBrief detects, contains, eradicates, recovers from, and
communicates security incidents. All personnel must know how to report
incidents and who takes over from there.

## 2. Incident Classification

| Severity | Definition | Examples | Response SLA |
|----------|-----------|---------|--------------|
| **P1 — Critical** | Active breach, data exposure, system compromise | Unauthorized access confirmed, client data exposed, production down due to attack | Respond within 1 hour; contain within 4 hours |
| **P2 — High** | Suspected breach, significant vulnerability, partial outage | Brute-force attack, dependency CVE affecting production, credential compromise suspected | Respond within 4 hours; resolve within 24 hours |
| **P3 — Medium** | Security misconfiguration, policy violation, minor anomaly | Dependabot alert (non-critical), unexpected access pattern, policy acknowledged late | Respond within 1 business day; resolve within 1 week |

## 3. Incident Response Team

| Role | Person | Contact | Responsibilities |
|------|--------|---------|-----------------|
| Incident Commander | [Name] | [email/phone] | Leads response; makes containment decisions; client comms |
| Technical Lead | [Name] | [email/phone] | Investigation; containment; remediation |
| Communications | [Name] | [email/phone] | Client and stakeholder notifications |

## 4. Reporting an Incident

**Anyone who suspects a security incident must:**
1. Do NOT attempt to fix it alone or share details publicly
2. Email [security@yourdomain.com] within 1 hour with:
   - What you observed (be specific — logs, screenshots, timestamps)
   - When you first noticed it
   - What systems/data may be affected
   - What actions you've already taken

## 5. Response Phases

### Phase 1: Detection and Triage (0–1 hour)
- [ ] Incident Reporter notifies security contact
- [ ] Incident Commander assesses and classifies severity (P1/P2/P3)
- [ ] Incident log entry created (GitHub Issue with `security-incident` label)
- [ ] Response team assembled

### Phase 2: Containment (1–4 hours for P1)
**Credential Compromise:**
- [ ] Immediately rotate compromised credentials
- [ ] Revoke all active sessions for affected users
- [ ] Block source IP if applicable (Render firewall)
- [ ] Notify affected user(s)

**Data Breach / Unauthorized Access:**
- [ ] Identify what data was accessed
- [ ] Revoke attacker's access immediately
- [ ] Preserve logs (do not delete or overwrite)
- [ ] Determine if client data was exposed

**Production Compromise:**
- [ ] Take snapshot of current state for forensics
- [ ] Redeploy from known-good commit
- [ ] Rotate all production secrets
- [ ] Block traffic if necessary (Render maintenance mode)

### Phase 3: Eradication
- [ ] Identify root cause
- [ ] Remove malicious code/access paths
- [ ] Patch vulnerability or misconfiguration
- [ ] Verify no backdoors or persistence mechanisms remain

### Phase 4: Recovery
- [ ] Restore service from verified clean state
- [ ] Verify all systems functioning normally
- [ ] Monitor closely for 48 hours post-recovery
- [ ] Confirm no data integrity issues

### Phase 5: Post-Incident Review (within 5 business days)
- [ ] Timeline of events documented
- [ ] Root cause confirmed
- [ ] What worked in the response (keep)
- [ ] What didn't work (improve)
- [ ] Action items with owners and due dates
- [ ] Incident log closed with resolution summary

## 6. Client Notification

**When client data may have been exposed:**
- Notify affected clients within 72 hours of confirmed exposure
- Notification must include: what happened, what data, when, what we did, what clients should do
- Log all notifications sent

**Template subject:** "Important Security Notice from BidBrief"

## 7. Runbooks

### Runbook A: API Key Leaked
1. Immediately revoke compromised key in provider dashboard (OpenAI/Render/Tavily)
2. Generate new key
3. Update environment variable in Render
4. Verify service restores (test analysis endpoint)
5. Search git history for leaked key: `git log -p | grep [key_prefix]`
6. If found in git history: use BFG Repo Cleaner to purge; force push
7. Notify provider that key was exposed

### Runbook B: Unauthorized Account Access
1. Identify affected account in active_sessions
2. Immediately invalidate their session (restart app if necessary to clear in-memory sessions)
3. Change account password
4. Review audit logs for what the account accessed
5. Determine if client data was accessed
6. If client data accessed: escalate to client notification

### Runbook C: Dependency Vulnerability (CVE)
1. Identify affected package from Dependabot / pip-audit alert
2. Check CVE severity and exploitability in BidBrief context
3. Update package: `pip install --upgrade [package]`; update `requirements.txt`
4. Run full test suite: `pytest tests/ -v`
5. Deploy if tests pass
6. Close Dependabot alert with reference to commit

---
*Approved by: [Security Officer Name] | Date: [DATE]*
```

**Step 2: Verify all sections present**

- [ ] Severity classification (P1/P2/P3) with SLAs
- [ ] Response team with contacts
- [ ] Reporting procedure (email + what to include)
- [ ] 5 response phases with checklists
- [ ] Client notification trigger and timeline
- [ ] 3 runbooks (API key, account access, CVE)

**Step 3: Commit**

```bash
git add docs/policies/incident_response_plan.md
git commit -m "docs: add Incident Response Plan with runbooks (SOC2 CC7.3, CC7.4, CC7.5)"
```

---

### Task 1.6: Write Remaining Three Policies

**Files:**
- Create: `docs/policies/change_management_policy.md`
- Create: `docs/policies/vulnerability_management_policy.md`
- Create: `docs/policies/acceptable_use_policy.md`

**Step 1: Write Change Management Policy**

Required sections:
- What constitutes a change (code, config, infrastructure, third-party integrations)
- Pre-production requirement: all changes tested in dev/staging first
- PR required: no direct pushes to master (reference branch protection)
- Review required: Security Officer or designated reviewer approves before merge
- Testing requirement: full test suite passes before deployment
- Rollback plan required for any deployment
- Emergency change procedure: deploy first, retrospective approval within 24 hours
- Change log reference: git history IS the change log

**Step 2: Write Vulnerability Management Policy**

Required sections:
- Vulnerability sources monitored (GitHub Dependabot, pip-audit, SAST, external reports)
- Severity-to-SLA table:
  - Critical CVE: patch within 24 hours
  - High CVE: patch within 7 days
  - Medium CVE: patch within 30 days
  - Low CVE: patch at next scheduled maintenance
- Process: detect → assess → prioritize → patch → verify → close
- Acceptance of risk: documented exceptions require Security Officer approval
- Disclosure policy reference (for external reporters)

**Step 3: Write Acceptable Use Policy**

Required sections:
- Authorized use: BidBrief systems used only for legitimate business purposes
- Prohibited actions (explicit list): sharing credentials, storing client data outside BidBrief, disabling security controls, using systems for personal gain
- Privacy: no expectation of privacy on company systems; activity may be monitored
- Reporting: report suspected violations or security issues immediately
- Acknowledgment: all personnel must sign/acknowledge annually

**Step 4: Verify each policy is complete (spot check)**

For each policy file, confirm it has:
- [ ] Version number
- [ ] Effective date
- [ ] Named owner
- [ ] Review cycle
- [ ] All required sections from Steps 1–3
- [ ] Approval signature block

**Step 5: Commit all three**

```bash
git add docs/policies/change_management_policy.md \
        docs/policies/vulnerability_management_policy.md \
        docs/policies/acceptable_use_policy.md
git commit -m "docs: add Change Management, Vulnerability Management, and Acceptable Use policies (SOC2 CC5.3, CC7.1, CC8.1)"
```

---

### Task 1.7: Write Risk Register

**Files:**
- Create: `docs/soc2/risk_register.md`

**Step 1: Create the Risk Register**

The Risk Register must contain every risk identified in `docs/soc2/SOC2_TYPE1_REQUIREMENTS.md` §5.1 plus the gaps identified in Phase 1. Use this format:

```markdown
# Risk Register

**Last Updated:** 2026-03-03
**Owner:** [Security Officer Name]
**Review Cycle:** Annual minimum; update when new risks identified

## Risk Scoring Matrix

**Likelihood:** 1=Rare, 2=Unlikely, 3=Possible, 4=Likely, 5=Almost Certain
**Impact:** 1=Negligible, 2=Minor, 3=Moderate, 4=Major, 5=Catastrophic
**Risk Score:** Likelihood × Impact (1–25)
**Treatment:** Mitigate / Accept / Transfer / Avoid

---

## Active Risks

| ID | Risk | Likelihood | Impact | Score | Treatment | Controls | Owner | Status |
|----|------|-----------|--------|-------|-----------|---------|-------|--------|
| R-001 | In-memory session loss on worker restart | 3 | 3 | 9 | Mitigate | Neon DB migration (Phase 3) | [Name] | Open |
| R-002 | Brute-force attack on login endpoint | 3 | 4 | 12 | Mitigate | Rate limiting (Phase 2) | [Name] | Open |
| R-003 | Dependency vulnerability (CVE in requirements.txt) | 4 | 3 | 12 | Mitigate | Dependabot + pip-audit CI (Phase 2) | [Name] | Open |
| R-004 | Client document content sent to OpenAI without disclosure | 2 | 5 | 10 | Mitigate | ToS disclosure + DPA (Phase 1) | [Name] | Open |
| R-005 | API key leaked in source code or logs | 2 | 5 | 10 | Mitigate | git-secrets scan; env var policy | [Name] | Open |
| R-006 | No persistent audit trail for access events | 3 | 4 | 12 | Mitigate | Persistent logging (Phase 3) | [Name] | Open |
| R-007 | Insider misuse of client documents | 1 | 5 | 5 | Accept | RBAC; access logging (Phase 3) | [Name] | Open |
| R-008 | Render platform outage | 2 | 4 | 8 | Accept | Stateless architecture; quick redeploy | [Name] | Open |
| R-009 | Clickjacking / UI redress attack | 2 | 3 | 6 | Mitigate | Security headers (Phase 2) | [Name] | Open |
| R-010 | Prompt injection via malicious uploaded document | 2 | 3 | 6 | Mitigate | Document sanitization; prompt hardening (Phase 2) | [Name] | Open |
| R-011 | No MFA on admin accounts | 3 | 4 | 12 | Mitigate | MFA implementation (Phase 3) | [Name] | Open |
| R-012 | Undetected security incident (no monitoring) | 3 | 4 | 12 | Mitigate | Log drain + alerting (Phase 2/4) | [Name] | Open |
```

**Step 2: Add risk-to-control mapping**

At the bottom of the risk register, add a section:

```markdown
## Risk-to-Control Mapping

| Risk ID | Control | Location | Implemented? |
|---------|---------|---------|--------------|
| R-001 | Neon DB session persistence | Phase 3 | No |
| R-002 | Flask-Limiter rate limiting | Phase 2 / app.py | No |
| R-003 | GitHub Dependabot + pip-audit | Phase 2 / .github/ | No |
| R-004 | OpenAI DPA + ToS disclosure | Phase 1 / docs/ | No |
| R-005 | Secrets scanning (git-secrets) | Phase 2 / CI/CD | No |
| R-006 | Persistent audit log table | Phase 3 / Neon DB | No |
| R-007 | Access logging + RBAC | Partial (app.py) | Partial |
| R-008 | Stateless design + Render SLA | Design / render.yaml | Partial |
| R-009 | Flask-Talisman security headers | Phase 2 / app.py | No |
| R-010 | Input sanitization | Phase 2 / app.py | Partial |
| R-011 | MFA for admin accounts | Phase 3 | No |
| R-012 | Log drain + alert rules | Phase 2/4 | No |
```

**Step 3: Commit**

```bash
git add docs/soc2/risk_register.md
git commit -m "docs: add Risk Register with scoring and control mapping (SOC2 CC3.2, CC5.1)"
```

---

### Task 1.8: Write System Description Document

**Files:**
- Create: `docs/soc2/system_description.md`

**Step 1: Create the System Description**

This document becomes Section III of the SOC 2 audit report. Auditors review it carefully. It must be accurate.

Required sections:
- **Infrastructure:** Render (cloud hosting), single Gunicorn worker, Flask app, Python 3.x
- **Software:** Python/Flask, PyMuPDF/pdfplumber (PDF extraction), OpenAI GPT-4o (analysis), vanilla JS frontend
- **People:** List of personnel with system access and their roles
- **Data:** What data the system processes, stores, and transmits (reference Data Classification Policy)
- **Network:** HTTPS inbound (Render TLS), HTTPS outbound to OpenAI/Tavily APIs
- **Data flows diagram** (text/ASCII is acceptable for Type I):
  ```
  User Browser
      ↓ HTTPS (TLS 1.2+)
  Render Platform (Flask App)
      ↓ Encrypted temp storage
  Ephemeral Upload Store
      ↓ Document text (HTTPS)
  OpenAI API
      ↑ Analysis results (HTTPS)
  Flask App
      ↓ In-memory session
  User Browser
  ```
- **Subservice organizations:** Render (hosting), OpenAI (AI processing), Tavily (web search)
- **Relevant aspects of control environment:** References to policy docs
- **Trust service criteria:** Which criteria are in scope (CC + C)

**Step 2: Commit**

```bash
git add docs/soc2/system_description.md
git commit -m "docs: add System Description (SOC2 CC3.1 - required for audit report Section III)"
```

---

### Task 1.9: Create Vendor Inventory and Review DPAs

**Files:**
- Create: `docs/soc2/vendor_inventory.md`

**Step 1: Create vendor inventory**

```markdown
# Vendor Inventory

**Last Updated:** 2026-03-03
**Owner:** [Security Officer Name]
**Review Cycle:** Annual

| Vendor | Service | Data Shared | Classification | SOC 2? | DPA? | Review Date | Notes |
|--------|---------|------------|----------------|--------|------|-------------|-------|
| OpenAI | GPT-4o LLM inference | Document text (CONFIDENTIAL) | Critical | Yes (Type 2) | Yes | 2026-03-03 | Review API ToS §3 on data retention |
| Render | Application hosting | All system data transits | Critical | Yes | Via ToS | 2026-03-03 | Obtain SOC 2 report from render.com/security |
| Tavily | Web search | Search queries only | Standard | Unknown | Via ToS | 2026-03-03 | Assess: what queries contain, data retention |
| GitHub | Source code hosting | Source code (INTERNAL) | Standard | Yes | Via ToS | 2026-03-03 | Enterprise or Teams plan for advanced security |
```

**Step 2: Obtain and file vendor compliance docs**

For each Critical vendor:
1. **OpenAI:** Download current ToS and DPA from platform.openai.com → save to `docs/soc2/vendor_certs/openai_dpa_[date].pdf`
2. **Render:** Download SOC 2 report from render.com/security → save to `docs/soc2/vendor_certs/render_soc2_[date].pdf`

**Step 3: Verify DPA covers key items for each critical vendor**

For OpenAI DPA, confirm:
- [ ] Data is not used to train models (or customer can opt out)
- [ ] Data retention period defined
- [ ] Data deletion process defined
- [ ] Security measures described
- [ ] Breach notification commitment

**Step 4: Commit**

```bash
git add docs/soc2/vendor_inventory.md docs/soc2/vendor_certs/
git commit -m "docs: add vendor inventory and DPA records (SOC2 CC9.2)"
```

---

### Task 1.10: Enable GitHub Branch Protection

**This is a repository settings change, not a code change.**

**Step 1: Navigate to GitHub repository settings**

```
GitHub → [repo] → Settings → Branches → Add rule
```

**Step 2: Configure branch protection rule for `master`**

Enable ALL of the following:
- [x] **Require a pull request before merging**
  - [x] Require approvals: 1 (can approve your own PRs for solo work — this still forces PR creation)
  - [x] Dismiss stale pull request approvals when new commits are pushed
- [x] **Require status checks to pass before merging** (enable when CI/CD is added in Phase 2)
- [x] **Require branches to be up to date before merging**
- [x] **Do not allow bypassing the above settings**

**Step 3: Verify protection is active**

Try: `git push origin master` with a direct commit (it should be rejected with a protection error).

Expected: `! [remote rejected] master -> master (protected branch hook declined)`

**Step 4: Document in audit log**

Add entry to `docs/soc2/access_grant_log.md`:
```
| 2026-03-03 | GitHub master branch | Protected | [Name] | SOC2 CC8.1 compliance |
```

**Step 5: Commit documentation**

```bash
git add docs/soc2/access_grant_log.md
git commit -m "docs: record branch protection activation (SOC2 CC8.1)"
```

---

### Task 1.11: Enable GitHub Dependabot

**Step 1: Create Dependabot configuration**

Create `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "09:00"
    open-pull-requests-limit: 10
    reviewers:
      - "[github-username]"
    labels:
      - "security"
      - "dependencies"
    commit-message:
      prefix: "fix"
      include: "scope"
```

**Step 2: Verify Dependabot activates**

Navigate to: `GitHub → [repo] → Security → Dependabot alerts`

Expected: Dependabot is active and any existing alerts are visible.

**Step 3: Commit**

```bash
git add .github/dependabot.yml
git commit -m "feat: enable Dependabot weekly security scans (SOC2 CC7.1)"
```

---

### Task 1.12: Configure Uptime Monitoring

**Step 1: Create free UptimeRobot account (or equivalent)**

Go to uptimerobot.com → Sign up free → Add Monitor:
- Monitor type: HTTP(s)
- Friendly name: BidBrief Production
- URL: `https://[your-render-domain]/health`
- Monitoring interval: 5 minutes
- Alert contacts: [security email]

**Step 2: Verify monitoring is active**

Check UptimeRobot dashboard shows monitor as "Up".

**Step 3: Document monitoring setup**

Add to `docs/soc2/system_description.md` under "Monitoring":
```
Uptime monitoring: UptimeRobot monitors /health every 5 minutes.
Alerts sent to [security email] on downtime.
```

**Step 4: Commit**

```bash
git add docs/soc2/system_description.md
git commit -m "docs: record uptime monitoring setup (SOC2 CC4.1, CC7.2)"
```

---

### Task 1.13: Phase 1 Audit Pass

**Step 1: Open `docs/soc2/SOC2_TYPE1_REQUIREMENTS.md`**

Walk every CC1, CC2, CC3, CC4 (partial), CC5.3, CC8.1, CC9.2, and C1 checklist item.

**Step 2: Update statuses**

For each item where Phase 1 work has been completed, change `❌ GAP` to `✅ PASS` or `⚠️ PARTIAL` as appropriate.

**Step 3: Update the Quick Gap Dashboard table at the top of the file**

Recalculate P1/P2/P3 counts after Phase 1 completions.

**Step 4: Commit updated checklist**

```bash
git add docs/soc2/SOC2_TYPE1_REQUIREMENTS.md
git commit -m "docs: update SOC2 checklist after Phase 1 completion"
```

---

---

## PHASE 2 — Technical Controls: Access, Headers, and CI/CD
*First phase with `app.py` changes. Run full test suite after every task.*
*Estimated: 2–3 weeks*

**CRITICAL: Before starting Phase 2:**
- Phase 1 must be 100% complete
- Run `pytest tests/ -v` and confirm all tests pass as baseline
- Record the passing baseline in git: `git stash && pytest tests/ -v && git stash pop`

---

### Task 2.1: Add Security Headers (Flask-Talisman)

**Files:**
- Modify: `requirements.txt`
- Modify: `app.py`
- Modify: `tests/test_api_security.py`

**Step 1: Write failing tests first**

Add to `tests/test_api_security.py`:

```python
def test_security_headers_present(client):
    """Verify security headers are set on all responses."""
    token = 'test-token'
    _create_auth_cookie(client, token, 'testuser')
    resp = client.get('/health')
    # HSTS
    assert 'Strict-Transport-Security' in resp.headers
    # Clickjacking protection
    assert resp.headers.get('X-Frame-Options') in ('DENY', 'SAMEORIGIN')
    # MIME sniffing protection
    assert resp.headers.get('X-Content-Type-Options') == 'nosniff'

def test_content_security_policy_present(client):
    """Verify CSP header is set."""
    resp = client.get('/health')
    assert 'Content-Security-Policy' in resp.headers
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_security.py::test_security_headers_present \
       tests/test_api_security.py::test_content_security_policy_present -v
```

Expected: FAIL (headers not present yet)

**Step 3: Install Flask-Talisman**

Add to `requirements.txt`:
```
flask-talisman>=1.1.0,<2.0.0
```

```bash
pip install flask-talisman
```

**Step 4: Add Talisman to app.py**

After Flask app initialization (find `app = Flask(__name__)` in `app.py`), add:

```python
from flask_talisman import Talisman

# Security headers - SOC2 CC6.1
# force_https=False because Render handles TLS termination
# CSP allows inline scripts/styles needed for existing UI (tighten in Phase 3+)
talisman = Talisman(
    app,
    force_https=False,  # Render handles TLS; don't redirect in app
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,
    content_security_policy={
        'default-src': ["'self'"],
        'script-src': ["'self'", "'unsafe-inline'"],   # UI uses inline JS - tighten later
        'style-src': ["'self'", "'unsafe-inline'"],    # UI uses inline CSS - tighten later
        'img-src': ["'self'", "data:"],
        'connect-src': ["'self'"],
    },
    frame_options='DENY',
    content_type_options=True,
    referrer_policy='strict-origin-when-cross-origin',
)
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_api_security.py -v
```

Expected: ALL PASS (including existing auth tests)

**Step 6: Run full test suite to check no regressions**

```bash
pytest tests/ -v
```

Expected: ALL PASS

**Step 7: Manually verify UI still works**

Start app locally: `python app.py`
Open browser: navigate to login and perform a test analysis.
Verify no CSP violations in browser console.

**Step 8: Commit**

```bash
git add requirements.txt app.py tests/test_api_security.py
git commit -m "feat: add security headers via Flask-Talisman (SOC2 CC6.1)"
```

---

### Task 2.2: Add Rate Limiting (Flask-Limiter)

**Files:**
- Modify: `requirements.txt`
- Modify: `app.py`
- Modify: `tests/test_api_security.py`

**Step 1: Write failing tests**

Add to `tests/test_api_security.py`:

```python
def test_login_rate_limit_enforced(client):
    """After N failed login attempts, endpoint returns 429."""
    # Make 10 rapid login attempts with wrong credentials
    for i in range(10):
        client.post('/auth/login', data={
            'email': 'wrong@test.com',
            'password': 'wrongpassword'
        })
    # 11th attempt should be rate limited
    resp = client.post('/auth/login', data={
        'email': 'wrong@test.com',
        'password': 'wrongpassword'
    })
    assert resp.status_code == 429

def test_upload_rate_limit_enforced(client):
    """Upload endpoint enforces per-minute rate limit."""
    token = 'upload-rate-token'
    _create_auth_cookie(client, token, 'testuser')
    # Make many rapid requests (without actual files - just checking rate limiting)
    for i in range(20):
        client.post('/api/upload', headers={'Cookie': f'bidbrief_auth={token}'})
    resp = client.post('/api/upload', headers={'Cookie': f'bidbrief_auth={token}'})
    assert resp.status_code == 429
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_security.py::test_login_rate_limit_enforced \
       tests/test_api_security.py::test_upload_rate_limit_enforced -v
```

Expected: FAIL

**Step 3: Install Flask-Limiter**

Add to `requirements.txt`:
```
Flask-Limiter>=3.5.0,<4.0.0
```

```bash
pip install Flask-Limiter
```

**Step 4: Add rate limiting to app.py**

After Flask app initialization, add limiter setup:

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Rate limiting - SOC2 CC6.1, CC6.6
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri="memory://",  # Phase 3: switch to Redis URI for distributed limiting
)
```

Then add decorators to specific routes. Find the login route (`/auth/login`) and add:
```python
@limiter.limit("10 per minute")  # Brute force protection
```

Find the upload route (`/api/upload`) and add:
```python
@limiter.limit("20 per minute")  # Prevent upload flooding
```

Find the analyze route (`/api/analyze`) and add:
```python
@limiter.limit("10 per minute")  # Prevent analysis API abuse
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_api_security.py -v
```

**Step 6: Run full test suite**

```bash
pytest tests/ -v
```

Expected: ALL PASS

**Step 7: Commit**

```bash
git add requirements.txt app.py tests/test_api_security.py
git commit -m "feat: add rate limiting on auth/upload/analyze endpoints (SOC2 CC6.1, CC6.6)"
```

---

### Task 2.3: Add File Upload Validation

**Files:**
- Modify: `app.py`
- Modify: `tests/test_api_security.py`

**Step 1: Write failing tests**

Add to `tests/test_api_security.py`:

```python
def test_upload_rejects_oversized_file(client):
    """Files over the size limit are rejected with 413."""
    token = 'size-test-token'
    _create_auth_cookie(client, token, 'testuser')
    # Create a fake 60MB file (over 50MB limit)
    large_file = io.BytesIO(b'x' * (60 * 1024 * 1024))
    resp = client.post('/api/upload',
        data={'file': (large_file, 'large.pdf', 'application/pdf')},
        headers={'Cookie': f'bidbrief_auth={token}'},
        content_type='multipart/form-data'
    )
    assert resp.status_code == 413

def test_upload_rejects_disallowed_file_types(client):
    """Non-document file types are rejected with 400."""
    token = 'type-test-token'
    _create_auth_cookie(client, token, 'testuser')
    fake_exe = io.BytesIO(b'MZ\x90\x00')  # PE header
    resp = client.post('/api/upload',
        data={'file': (fake_exe, 'malware.exe', 'application/octet-stream')},
        headers={'Cookie': f'bidbrief_auth={token}'},
        content_type='multipart/form-data'
    )
    assert resp.status_code == 400
    data = resp.get_json()
    assert 'not allowed' in data.get('error', '').lower()
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_api_security.py::test_upload_rejects_oversized_file \
       tests/test_api_security.py::test_upload_rejects_disallowed_file_types -v
```

**Step 3: Add file size limit to app.py**

Find `app = Flask(__name__)` and after it add:
```python
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload
```

**Step 4: Harden upload handler**

Find `upload_file()` function in `app.py`. Add explicit extension + MIME validation:

```python
ALLOWED_EXTENSIONS = {'.pdf', '.docx', '.doc', '.txt', '.rtf'}
ALLOWED_MIME_TYPES = {
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/msword',
    'text/plain',
    'application/rtf',
    'text/rtf',
}

def allowed_file(filename, mimetype):
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS and mimetype in ALLOWED_MIME_TYPES
```

In the upload handler, add the check after getting the file:
```python
if not allowed_file(file.filename, file.content_type):
    return jsonify({'success': False, 'error': 'File type not allowed'}), 400
```

**Step 5: Run tests and full suite**

```bash
pytest tests/ -v
```

Expected: ALL PASS

**Step 6: Commit**

```bash
git add app.py tests/test_api_security.py
git commit -m "feat: enforce file size limit and type validation on uploads (SOC2 CC6.8)"
```

---

### Task 2.4: Add CI/CD Security Pipeline (GitHub Actions)

**Files:**
- Create: `.github/workflows/security.yml`
- Create: `.github/workflows/tests.yml`

**Step 1: Create test runner workflow**

Create `.github/workflows/tests.yml`:

```yaml
name: Tests

on:
  push:
    branches: [ master ]
  pull_request:
    branches: [ master ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest

      - name: Run tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY_TEST }}
          SECRET_KEY: test-secret-key-for-ci
        run: pytest tests/ -v --tb=short
```

**Step 2: Create security scan workflow**

Create `.github/workflows/security.yml`:

```yaml
name: Security Scans

on:
  push:
    branches: [ master ]
  pull_request:
    branches: [ master ]
  schedule:
    - cron: '0 9 * * 1'  # Every Monday 9am UTC

jobs:
  dependency-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install pip-audit
        run: pip install pip-audit

      - name: Run dependency vulnerability audit
        run: pip-audit -r requirements.txt --format=json --output=pip-audit-report.json || true

      - name: Upload audit report
        uses: actions/upload-artifact@v4
        with:
          name: pip-audit-report
          path: pip-audit-report.json

      - name: Fail on critical vulnerabilities
        run: pip-audit -r requirements.txt --severity=critical

  sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Bandit
        run: pip install bandit[toml]

      - name: Run Bandit SAST scan
        run: |
          bandit -r app.py services/ \
            --severity-level medium \
            --format json \
            --output bandit-report.json || true

      - name: Upload SAST report
        uses: actions/upload-artifact@v4
        with:
          name: bandit-report
          path: bandit-report.json

      - name: Fail on high-severity findings
        run: bandit -r app.py services/ --severity-level high --exit-zero
```

**Step 3: Add GitHub Actions secret**

In GitHub: `Settings → Secrets and variables → Actions → New repository secret`
- Name: `OPENAI_API_KEY_TEST`
- Value: A test API key (can be the real one for CI, or a limited test key)

**Step 4: Verify workflows run**

Push the files and check:
`GitHub → Actions → Security Scans` — should show green (or yellow with findings to review)
`GitHub → Actions → Tests` — should show green

**Step 5: Review initial Bandit findings**

Download the bandit-report.json artifact. Review any HIGH findings in `app.py` or `services/`. Add to the Risk Register if any require remediation.

**Step 6: Commit**

```bash
git add .github/workflows/
git commit -m "feat: add CI/CD security pipeline with pip-audit and Bandit SAST (SOC2 CC7.1, CC8.1)"
```

---

### Task 2.5: Configure Render Log Drain

**This is a Render dashboard configuration, not a code change.**

**Step 1: Choose a log aggregation service**

Recommended free/low-cost options:
- **Logtail (Better Stack)** — free tier 1GB/month, 3 day retention. Upgrade for 30+ days.
- **Papertrail** — free tier 50MB/day, 7 days retention
- **Datadog** — free tier 5GB/day, 1 day retention (upgrade for compliance-grade retention)

For SOC 2 compliance, you need **minimum 90 days** retention. Factor this into service selection or budget for a paid tier.

**Step 2: Create account and get drain URL**

Sign up → Create a log destination → Copy the syslog/drain URL

**Step 3: Configure in Render**

```
Render Dashboard → [Service] → Logs → Log Streams → Add Log Stream
```
- Enter drain endpoint URL
- Save

**Step 4: Verify logs are flowing**

Generate some app activity (login, upload) then check the log aggregation dashboard.
Expected: Log entries appearing in real time.

**Step 5: Set up retention**

In log service: configure retention to 90 days minimum.

**Step 6: Document**

Add to `docs/soc2/system_description.md`:
```
Log aggregation: [Service name]. Logs shipped via Render log drain.
Retention: 90 days. Alert rules: [see CC7.2 controls].
```

**Step 7: Commit docs**

```bash
git add docs/soc2/system_description.md
git commit -m "docs: record log drain configuration (SOC2 CC2.1, CC7.2)"
```

---

### Task 2.6: Phase 2 Audit Pass

**Step 1: Run full test suite**

```bash
pytest tests/ -v
```

Expected: ALL PASS

**Step 2: Update SOC2_TYPE1_REQUIREMENTS.md**

Walk all CC6 and CC7 (partial) checklist items. Update statuses for:
- CC6.1 security headers (✅ PASS with Talisman)
- CC6.1 rate limiting on auth (✅ PASS)
- CC6.6 rate limiting on all API endpoints (✅ PASS)
- CC6.8 upload type/size validation (✅ PASS)
- CC7.1 Dependabot + pip-audit CI (✅ PASS)
- CC8.1 branch protection + CI/CD (✅ PASS)

**Step 3: Commit updated checklist**

```bash
git add docs/soc2/SOC2_TYPE1_REQUIREMENTS.md
git commit -m "docs: update SOC2 checklist after Phase 2 completion"
```

---

---

## PHASE 3 — Persistent Audit Logging and User Management
*Requires Neon DB setup. Longest phase — database migration is involved.*
*Estimated: 3–4 weeks*

**CRITICAL: Before starting Phase 3:**
- Phases 1 and 2 must be complete
- Create a `phase-3-neon-db` branch from master
- All work happens in that branch; merge via PR when phase complete

---

### Task 3.1: Provision Neon DB (PostgreSQL)

**Step 1: Create Neon account and database**

1. Go to neon.tech → Sign up → Create project: `bidbrief-production`
2. Create two databases:
   - `bidbrief_production` — for production
   - `bidbrief_test` — for test suite
3. Copy connection strings for both

**Step 2: Add Neon to dependencies**

Add to `requirements.txt`:
```
psycopg2-binary>=2.9.0,<3.0.0
```

**Step 3: Add environment variables to Render**

In Render dashboard → Environment → Add:
- `NEON_DATABASE_URL` = `postgresql://...` (production connection string)

Add to `.env.example`:
```
NEON_DATABASE_URL=postgresql://user:password@host/database
NEON_TEST_DATABASE_URL=postgresql://user:password@host/test_database
```

**Step 4: Write database connection module**

Create `services/database.py`:

```python
"""
PostgreSQL database connection for BidBrief.
Uses Neon DB (serverless PostgreSQL) for audit logs and user management.
"""
import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

logger = logging.getLogger(__name__)

def get_connection():
    """Return a new database connection."""
    url = os.getenv('NEON_DATABASE_URL')
    if not url:
        raise RuntimeError("NEON_DATABASE_URL environment variable not set")
    return psycopg2.connect(url, cursor_factory=RealDictCursor)

@contextmanager
def get_db():
    """Context manager for database connections with auto-commit/rollback."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

**Step 5: Write failing test**

Create `tests/test_database.py`:

```python
import os
import pytest
import psycopg2

def test_database_connection():
    """Verify Neon DB is reachable."""
    url = os.getenv('NEON_TEST_DATABASE_URL') or os.getenv('NEON_DATABASE_URL')
    if not url:
        pytest.skip("No database URL configured")
    conn = psycopg2.connect(url)
    assert conn is not None
    conn.close()
```

**Step 6: Run test**

```bash
NEON_TEST_DATABASE_URL="[test connection string]" pytest tests/test_database.py -v
```

Expected: PASS

**Step 7: Commit**

```bash
git add requirements.txt services/database.py tests/test_database.py .env.example
git commit -m "feat: add Neon DB connection module (SOC2 CC1.5 - persistent audit logs)"
```

---

### Task 3.2: Create Audit Log Schema and Service

**Files:**
- Create: `services/audit_log.py`
- Modify: `app.py`
- Create: `migrations/001_audit_log.sql`

**Step 1: Write migration SQL**

Create `migrations/001_audit_log.sql`:

```sql
-- SOC 2 CC1.5: Persistent audit log for user actions
-- Retention: 12 months minimum (auto-delete via scheduled job or pg_partman)

CREATE TABLE IF NOT EXISTS audit_log (
    id          BIGSERIAL PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    username    VARCHAR(255) NOT NULL,
    action      VARCHAR(100) NOT NULL,
    resource    VARCHAR(500),
    ip_address  INET,
    session_id  VARCHAR(255),
    status      VARCHAR(20) NOT NULL DEFAULT 'success',  -- success / failure / error
    details     JSONB,
    CONSTRAINT audit_log_status_check CHECK (status IN ('success', 'failure', 'error'))
);

CREATE INDEX idx_audit_log_username ON audit_log(username);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
CREATE INDEX idx_audit_log_action ON audit_log(action);

-- Auto-delete entries older than 12 months (run via pg_cron or app-level job)
-- CREATE EXTENSION IF NOT EXISTS pg_cron;
-- SELECT cron.schedule('delete-old-audit-logs', '0 2 * * *',
--   'DELETE FROM audit_log WHERE created_at < NOW() - INTERVAL ''12 months''');
```

**Step 2: Run migration**

```bash
psql $NEON_DATABASE_URL < migrations/001_audit_log.sql
```

**Step 3: Write failing test**

Add to `tests/test_database.py`:

```python
from services.audit_log import log_event, get_recent_events

def test_audit_log_write_and_read():
    """Audit events are persisted and retrievable."""
    url = os.getenv('NEON_TEST_DATABASE_URL')
    if not url:
        pytest.skip("No test database URL")

    log_event(
        username='test_user',
        action='test.action',
        resource='/api/test',
        ip_address='127.0.0.1',
        session_id='test-session',
        status='success',
        details={'test': True}
    )

    events = get_recent_events(username='test_user', limit=1)
    assert len(events) == 1
    assert events[0]['action'] == 'test.action'
    assert events[0]['status'] == 'success'
```

**Step 4: Write AuditLog service**

Create `services/audit_log.py`:

```python
"""
SOC 2 CC1.5: Persistent audit logging service.
Logs all security-relevant user actions to Neon DB.
Falls back to stderr logging if DB unavailable (non-blocking).
"""
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from services.database import get_db

logger = logging.getLogger(__name__)

# Actions to log
ACTIONS = {
    'auth.login_success': 'User logged in successfully',
    'auth.login_failure': 'Failed login attempt',
    'auth.logout': 'User logged out',
    'upload.file': 'File uploaded for analysis',
    'analysis.start': 'Document analysis started',
    'analysis.complete': 'Document analysis completed',
    'export.excel': 'Excel report exported',
    'admin.session_view': 'Admin viewed session data',
    'admin.user_create': 'Admin created user',
    'admin.user_delete': 'Admin deleted user',
}

def log_event(
    username: str,
    action: str,
    resource: Optional[str] = None,
    ip_address: Optional[str] = None,
    session_id: Optional[str] = None,
    status: str = 'success',
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Persist an audit event to the database.
    Non-blocking: logs error and continues if DB write fails.
    """
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO audit_log
                       (username, action, resource, ip_address, session_id, status, details)
                       VALUES (%s, %s, %s, %s::inet, %s, %s, %s)""",
                    (username, action, resource, ip_address,
                     session_id, status, json.dumps(details) if details else None)
                )
    except Exception as e:
        # Non-blocking: never let audit log failure break the app
        logger.error(f"Audit log write failed: {e} | event={action} user={username}")

def get_recent_events(
    username: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100
) -> List[Dict]:
    """Retrieve recent audit events, optionally filtered."""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                query = "SELECT * FROM audit_log WHERE 1=1"
                params = []
                if username:
                    query += " AND username = %s"
                    params.append(username)
                if action:
                    query += " AND action = %s"
                    params.append(action)
                query += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
    except Exception as e:
        logger.error(f"Audit log read failed: {e}")
        return []
```

**Step 5: Run tests**

```bash
pytest tests/test_database.py -v
```

Expected: ALL PASS

**Step 6: Add audit log calls to app.py**

Find each of these locations in `app.py` and add the corresponding `log_event()` call:

- After successful login → `log_event(username, 'auth.login_success', ip_address=request.remote_addr)`
- After failed login → `log_event(email, 'auth.login_failure', status='failure', ip_address=request.remote_addr)`
- After file upload → `log_event(session['username'], 'upload.file', resource=filename, session_id=session_id)`
- After analysis start → `log_event(username, 'analysis.start', session_id=session_id)`
- After Excel export → `log_event(username, 'export.excel', session_id=session_id)`

**Step 7: Run full test suite**

```bash
pytest tests/ -v
```

Expected: ALL PASS

**Step 8: Commit**

```bash
git add services/audit_log.py services/database.py migrations/ app.py tests/test_database.py
git commit -m "feat: persistent audit logging to Neon DB (SOC2 CC1.5, CC6.3, C1.1)"
```

---

### Task 3.3: User Management UI

> *Replaces env-var-only user management. Admin can add/remove/disable users without a server restart.*

**Files:**
- Create: `migrations/002_users.sql`
- Create: `services/user_manager.py`
- Modify: `app.py` (new admin endpoints)
- Modify: `admin_sessions.html` (add user management tab)

**Step 1: Write migration**

Create `migrations/002_users.sql`:

```sql
CREATE TABLE IF NOT EXISTS users (
    id          BIGSERIAL PRIMARY KEY,
    email       VARCHAR(255) UNIQUE NOT NULL,
    name        VARCHAR(255) NOT NULL,
    role        VARCHAR(20) NOT NULL DEFAULT 'user',
    password_hash VARCHAR(255) NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by  VARCHAR(255),
    last_login  TIMESTAMPTZ,
    CONSTRAINT users_role_check CHECK (role IN ('admin', 'user'))
);

-- Seed initial admin from environment variable during migration
-- (handled in app startup, not SQL)
```

**Step 2–N:** *(Full implementation details to be specified in a dedicated task session when Phase 3 begins — scope is significant and merits its own planning pass)*

**Step N: Commit**

```bash
git commit -m "feat: database-backed user management (SOC2 CC6.2, CC1.5)"
```

---

### Task 3.4: Phase 3 Audit Pass

Update `docs/soc2/SOC2_TYPE1_REQUIREMENTS.md` for newly passing controls:
- CC1.5: Audit logs persisted (✅)
- CC6.2: User provisioning records (✅)
- CC6.3: Access reviews enabled by user management UI (✅)

```bash
git add docs/soc2/SOC2_TYPE1_REQUIREMENTS.md
git commit -m "docs: update SOC2 checklist after Phase 3 completion"
```

---

---

## PHASE 4 — Monitoring and Incident Response Operationalization
*Estimated: 2–3 weeks*

---

### Task 4.1: Auth Failure Alerting

**Files:**
- Modify: `services/audit_log.py` (add alert threshold check)
- Create: `services/alerting.py`

**Step 1: Create alerting service**

Create `services/alerting.py` with a `send_security_alert()` function that:
- Takes: alert_type, message, details dict
- Sends email via configured SMTP (or Render email service)
- Logs the alert itself to audit_log with action `security.alert_sent`
- Is non-blocking (logs failure, does not raise)

**Step 2: Add threshold check to login failure logging**

After each `auth.login_failure` event, query audit_log for failures from the same IP in the last 5 minutes. If count ≥ 5: call `send_security_alert('brute_force_suspected', ...)`.

**Step 3: Write test**

```python
def test_alert_triggered_on_brute_force(client, monkeypatch):
    """Security alert fires after N failed logins from same IP."""
    alerts_sent = []
    monkeypatch.setattr('services.alerting.send_security_alert',
                        lambda *a, **k: alerts_sent.append(a))
    for i in range(6):
        client.post('/auth/login', data={'email': 'x@x.com', 'password': 'wrong'})
    assert len(alerts_sent) >= 1
```

**Step 4: Commit**

```bash
git commit -m "feat: brute-force detection and alerting (SOC2 CC7.2, CC7.3)"
```

---

### Task 4.2: Incident Response Tabletop Exercise

**This is a process task, not a code task.**

**Step 1: Schedule 1-hour tabletop exercise**

Walk through IRP using Scenario A (API key leaked):
- Act out each phase of the IRP
- Note gaps in the runbook
- Update `docs/policies/incident_response_plan.md` with any improvements

**Step 2: Document completion**

Create `docs/soc2/tabletop_exercises.md`:

```markdown
# Incident Response Tabletop Exercises

| Date | Scenario | Participants | Findings | Actions Taken |
|------|----------|-------------|---------|---------------|
| 2026-[date] | Runbook A: API Key Leaked | [Names] | [Findings] | [PR/commit ref] |
```

**Step 3: Commit**

```bash
git add docs/soc2/tabletop_exercises.md docs/policies/incident_response_plan.md
git commit -m "docs: record IRP tabletop exercise (SOC2 CC7.4)"
```

---

---

## PHASE 5 — Audit Readiness
*Estimated: 1–2 weeks*

---

### Task 5.1: Final Gap Review

**Step 1: Open `docs/soc2/SOC2_TYPE1_REQUIREMENTS.md`**

Walk EVERY checklist item. For each remaining ❌ GAP:
- Confirm it is truly addressed or document accepted risk with justification
- No P1 gaps should remain unclosed

**Step 2: Produce evidence package**

Create `docs/soc2/evidence_package/` directory containing:

| Evidence Item | Source |
|---------------|--------|
| Policy documents (7 PDFs) | `docs/policies/` → export to PDF |
| Risk Register | `docs/soc2/risk_register.md` |
| System Description | `docs/soc2/system_description.md` |
| Vendor inventory + DPAs | `docs/soc2/vendor_inventory.md` + certs |
| Access Grant Log | `docs/soc2/access_grant_log.md` |
| Branch protection screenshot | GitHub settings screenshot |
| CI/CD pipeline run screenshots | GitHub Actions |
| Log drain configuration screenshot | Render + log service |
| Uptime monitoring screenshot | UptimeRobot |
| Dependabot alert list | GitHub Security tab |
| Test suite passing | CI run screenshot |
| Audit log sample | Export from Neon DB |

**Step 3: Commit evidence package index**

```bash
git add docs/soc2/evidence_package/
git commit -m "docs: assemble audit evidence package (SOC2 Type I readiness)"
```

---

### Task 5.2: Engage Auditor

**Step 1: Identify SOC 2 auditors**

Recommended firms for startups (lower cost):
- Prescient Assurance
- A-LIGN
- Johanson Group
- Sensiba San Filippo

**Step 2: Pre-audit call**

Share:
- System Description (`docs/soc2/system_description.md`)
- Scope (CC + C criteria)
- Evidence package index

Request a readiness assessment before committing to full audit.

**Step 3: Address auditor feedback**

Any gaps identified by auditor: create GitHub Issues with `soc2-gap` label, prioritize, and remediate before audit begins.

---

---

## Appendix: Phase Summary

| Phase | Scope | App Changes | Duration | Key Deliverables |
|-------|-------|------------|----------|-----------------|
| 1 | Policies + repo settings | None | 4 weeks | 7 policy docs, risk register, system description, vendor inventory, branch protection, Dependabot |
| 2 | Technical controls | Flask-Limiter, Flask-Talisman, upload validation, CI/CD | 3 weeks | Rate limiting, security headers, SAST/SCA pipeline, log drain |
| 3 | Persistence + user mgmt | Neon DB, audit log table, user management | 4 weeks | Persistent audit logs, database-backed users, access provisioning UI |
| 4 | Monitoring + IR | Alerting service | 2 weeks | Brute-force alerting, IRP tabletop complete |
| 5 | Audit readiness | None | 2 weeks | Evidence package, auditor engaged |

**Total estimated path to Type I audit submission: ~15 weeks from Phase 1 start**

---

## Appendix: Running the Full Security Test Suite

```bash
# Run all tests including security tests
pytest tests/ -v

# Run only security tests
pytest tests/test_api_security.py -v

# Run dependency audit
pip-audit -r requirements.txt

# Run SAST
bandit -r app.py services/ --severity-level medium

# Check for secrets in git history
git log --all --full-history -p | grep -iE "(api_key|password|secret|token)" | grep "^\+" | grep -v "example\|placeholder\|your_"
```
