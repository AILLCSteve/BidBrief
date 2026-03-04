# SOC 2 Type I Requirements & BidBrief Audit Checklist
## Trust Service Criteria: Security (CC) + Confidentiality (C)
## AICPA Trust Services Criteria 2017 (Updated 2022)

**Product:** BidBrief — AI Document Analysis Platform
**Standard:** SOC 2 Type I
**Scope:** Security (Common Criteria CC1–CC9) + Confidentiality (C1)
**Last Audited:** _Not yet audited_
**Auditor:** _TBD_
**Prepared by:** Claude Code / Additional Intelligence LLC

---

## How to Use This Document

This file serves two purposes:
1. **Requirements Reference** — the authoritative list of what SOC 2 Type I demands
2. **Live Audit Checklist** — current status of BidBrief controls against each requirement

Run an audit session by walking each checklist item, updating statuses, and reviewing the Gap Summary at the bottom. Each criterion has three levels below it:

- **What This Means** — plain-English translation of the AICPA criterion
- **Required Controls** — specific controls that satisfy the criterion
- **BidBrief Audit Checklist** — how to verify each control in this codebase

### Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ PASS | Control exists and is implemented |
| ⚠️ PARTIAL | Control exists but needs improvement |
| ❌ GAP | Control is missing — must be built |
| 📋 POLICY | Requires a written policy document |
| 🔍 VERIFY | Needs manual verification before marking |

### Priority Legend

| Level | Meaning |
|-------|---------|
| 🔴 P1 | Auditor will flag — fix before Type I attempt |
| 🟠 P2 | Required for Type I but lower audit risk |
| 🟡 P3 | Best practice; Type I can pass without, but Type II will require |

---

## Quick Gap Dashboard

> Update this table after each audit pass.

| Criterion | Status | P1 Gaps | P2 Gaps | P3 Gaps |
|-----------|--------|---------|---------|---------|
| CC1 Control Environment | ❌ | 4 | 1 | 0 |
| CC2 Communication | ❌ | 2 | 2 | 1 |
| CC3 Risk Assessment | ❌ | 3 | 1 | 1 |
| CC4 Monitoring | ⚠️ | 1 | 2 | 0 |
| CC5 Control Activities | ⚠️ | 1 | 2 | 1 |
| CC6 Logical Access | ⚠️ | 4 | 3 | 2 |
| CC7 System Operations | ❌ | 3 | 2 | 1 |
| CC8 Change Management | ⚠️ | 1 | 2 | 1 |
| CC9 Risk Mitigation | ❌ | 2 | 2 | 0 |
| C1 Confidentiality | ⚠️ | 2 | 2 | 1 |
| **TOTAL** | | **23** | **19** | **8** |

---

---

# PART 1: COMMON CRITERIA (CC) — SECURITY

---

## CC1 — Control Environment

> The control environment sets the tone of the organization and provides foundational discipline and structure for all other controls. Auditors assess whether the entity has the governance, accountability structures, and ethical culture necessary to operate secure systems.

---

### CC1.1 — Commitment to Integrity and Ethical Values

**Official Criterion:** *"The entity demonstrates a commitment to integrity and ethical values."*

#### What This Means
The organization must have documented, communicated, and enforced standards for ethical behavior and integrity. This isn't just "we're honest people" — auditors look for written codes of conduct, security policies that employees acknowledge, and evidence that leadership enforces these standards. For a small team or solo operation, this means having a written policy that you follow, not just intend to follow.

#### Required Controls
- Written Code of Conduct or Acceptable Use Policy
- Security Policy document defining expected behaviors
- Evidence that all users/personnel have acknowledged these policies (signature, dated email, or access-gated acknowledgment)
- Process for handling policy violations

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Code of Conduct / Acceptable Use Policy exists as a written document | Expected location: `docs/policies/acceptable_use_policy.md` | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Information Security Policy exists and is dated | Expected location: `docs/policies/information_security_policy.md` | 🔴 P1
- [ ] 📋 ❌ **[GAP]** User acknowledgment process documented (e.g., onboarding checklist) | 🟠 P2
- [ ] 🔍 ⚠️ **[VERIFY]** No hardcoded credentials or secrets in source code | Check: `git log --all -S "password\|secret\|api_key" --source` | 🔴 P1

---

### CC1.2 — Board / Management Oversight

**Official Criterion:** *"The board of directors demonstrates independence from management and exercises oversight of the development and performance of internal control."*

#### What This Means
For enterprise organizations this is about board governance. For a small software company or startup, auditors interpret this as: does leadership (owner/founders) actively oversee security controls? Is there a designated person responsible for security? Is security reviewed periodically rather than just when something breaks? Evidence here is meeting notes, security review records, or a documented Security Officer designation.

#### Required Controls
- Designated Security Officer role (can be the founder/developer)
- Documented periodic security review cadence (quarterly minimum)
- Evidence of security review (meeting notes, dated review records)
- Security responsibilities defined in job/role descriptions

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Security Officer designation documented with name and responsibilities | Expected: `docs/policies/security_roles.md` | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Quarterly security review process defined and evidenced | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Security responsibilities included in any employee/contractor agreements | 🟠 P2

---

### CC1.3 — Organizational Structure and Authority

**Official Criterion:** *"Management establishes, with board oversight, structures, reporting lines, and appropriate authorities and responsibilities in the pursuit of objectives."*

#### What This Means
Who is authorized to make what decisions about the system? Who can create users, change configurations, deploy code, or access production? Auditors want to see that these authorities are defined and not ad-hoc. For BidBrief, this means: who can approve new user accounts, who can push to production, and who can change the OpenAI API key or access the server.

#### Required Controls
- Defined roles and responsibilities for system administration
- Authorization matrix: who can do what (create users, deploy, access DB, rotate secrets)
- Documented approval process for elevated access
- Separation of duties where feasible

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Authorization matrix documented (role → capabilities → approval required) | 🔴 P1
- [ ] 🔍 ⚠️ **[VERIFY]** Admin role in app is properly restricted | Check: `app.py` `require_admin` decorator usage on all admin routes | 🟠 P2
- [ ] 🔍 ⚠️ **[VERIFY]** Production deployment access is restricted | Check: Render dashboard access controls | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Documented process for granting/revoking system access | 🟠 P2

---

### CC1.4 — Commitment to Competence

**Official Criterion:** *"The entity demonstrates a commitment to attract, develop, and retain competent individuals in alignment with objectives."*

#### What This Means
People operating the system must have the skills to do so securely. For software, this means: are developers following secure coding practices? Is there evidence of security awareness? For a small team, this can be satisfied with documented security training completion (even free resources like OWASP awareness) and coding standards.

#### Required Controls
- Documented secure development training/awareness program
- Secure coding standards documented and followed
- Background check process for personnel with system access
- Security awareness training completion records

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Secure development guidelines documented | Expected: `docs/policies/secure_development_policy.md` | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Annual security awareness training completion tracked | 🟡 P3
- [ ] 🔍 🔍 **[VERIFY]** No known OWASP Top 10 vulnerabilities in codebase | Run: SAST scan (Bandit for Python) | 🔴 P1

---

### CC1.5 — Accountability

**Official Criterion:** *"The entity holds individuals accountable for their internal control responsibilities in the pursuit of objectives."*

#### What This Means
Actions in the system must be attributable to specific individuals. You can't have shared accounts. Audit logs must tie activity to a named user. Performance evaluations or accountability mechanisms must include security responsibilities. This is where having named user accounts (not generic logins) matters for the audit trail.

#### Required Controls
- Unique user accounts — no shared credentials
- Audit log that ties all significant actions to a specific user identity
- User activity logs retained for minimum 90 days (12 months preferred for Type II)
- Process for addressing security policy violations

#### BidBrief Audit Checklist
- [ ] 🔍 ⚠️ **[VERIFY]** Each user has a unique account; no shared admin credentials | Check: `app.py` auth config, env vars `AUTH_USER*` | 🟠 P2
- [ ] 🔍 ⚠️ **[PARTIAL]** Audit logging implemented (added in commit `0bc5d47`) | Verify: log format includes username + timestamp + action | `app.py` audit log functions | 🟠 P2
- [ ] ❌ **[GAP]** Audit logs persisted beyond process lifetime (currently in-memory / log files) | Needs: persistent log storage or log shipping | 🔴 P1
- [ ] ❌ **[GAP]** Log retention policy defined and enforced (minimum 90 days) | 🟠 P2

---

---

## CC2 — Communication and Information

> The entity must have clear internal and external communication channels about security objectives, responsibilities, and relevant security information. Auditors look for evidence that security isn't siloed — it's communicated to everyone who needs to know.

---

### CC2.1 — Quality Information

**Official Criterion:** *"The entity obtains or generates and uses relevant, quality information to support the functioning of internal control."*

#### What This Means
The organization must collect accurate, timely information to run its security controls. This includes: system logs that are complete and accurate, monitoring dashboards, vulnerability scan results, and any security metrics used to make decisions. Garbage-in/garbage-out in audit logs is a failure here.

#### Required Controls
- Centralized, tamper-resistant logging system
- Log completeness monitoring (alert on log gaps)
- Regular review of security-relevant information (vulnerability reports, access reviews)
- Data quality checks on security-critical inputs

#### BidBrief Audit Checklist
- [ ] ⚠️ **[PARTIAL]** Application logs capture security events | Check: `app.py` logging config, log format | 🟠 P2
- [ ] ❌ **[GAP]** Logs are shipped to a persistent, tamper-resistant store (not just local files) | Options: Render log drain → Papertrail/Logtail/CloudWatch | 🔴 P1
- [ ] ❌ **[GAP]** Log completeness monitored (no silent failures or dropped events) | 🟠 P2
- [ ] ❌ **[GAP]** Security metrics reviewed on a defined cadence | 🟡 P3

---

### CC2.2 — Internal Communication

**Official Criterion:** *"The entity internally communicates information, including objectives and responsibilities for internal control, necessary to support the functioning of internal control."*

#### What This Means
Security policies, procedures, and responsibilities must be communicated to everyone who works on or with the system. Developers must know what they can and can't do. If there's ever a contractor or new team member, there must be an onboarding process that covers security responsibilities.

#### Required Controls
- Security policy distribution and acknowledgment process
- Security responsibilities documented in roles
- Incident reporting process communicated to all personnel
- Regular security updates/communications cadence

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Security onboarding checklist for new personnel | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Incident reporting procedure communicated to all personnel | 🟠 P2
- [ ] 📋 ⚠️ **[PARTIAL]** `CLAUDE.md` documents some engineering standards | Does not constitute a security policy | 🟡 P3

---

### CC2.3 — External Communication

**Official Criterion:** *"The entity communicates with external parties regarding matters affecting the functioning of internal control."*

#### What This Means
Clients and users must be able to understand your security posture. This means: a Privacy Policy, a Security page or Security FAQ, a way for customers to report security issues (vulnerability disclosure policy), and a process for notifying customers of security incidents or breaches.

#### Required Controls
- Published Privacy Policy (accessible to all users)
- Security/Trust page or documentation available to customers
- Vulnerability Disclosure Policy (VDP) — how to report a bug
- Data Breach Notification Policy and process
- Vendor communication process for security issues

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Privacy Policy published and accessible | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Vulnerability Disclosure Policy (security@... email or HackerOne) | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Data Breach Notification process documented (who to notify, within what timeframe) | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Customer-facing security documentation (what data you store, how it's protected) | 🟠 P2
- [ ] 🔍 ⚠️ **[VERIFY]** Terms of Service exist and cover data handling | 🟡 P3

---

---

## CC3 — Risk Assessment

> The entity must systematically identify, analyze, and manage risks to its security objectives. Auditors want to see that risk management is a documented, repeatable process — not just reacting to incidents.

---

### CC3.1 — Specify Objectives

**Official Criterion:** *"The entity specifies objectives with sufficient clarity to enable the identification and assessment of risks relating to objectives."*

#### What This Means
You must have clearly defined system objectives that security risks are assessed against. For BidBrief: what is the system supposed to do, what data does it process, what are the uptime/confidentiality expectations? Without defined objectives, you can't assess what threatens them.

#### Required Controls
- Documented system description (what it does, what data it processes, who uses it)
- Defined security objectives (confidentiality commitments, availability targets)
- Data inventory / data flow diagram
- System boundaries defined

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Formal system description document (SOC 2 System Description) | This becomes Section III of the audit report | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Data inventory: what data types are processed, where they flow, how long retained | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Data flow diagram showing: user → app → OpenAI API → storage | 🟠 P2
- [ ] 🔍 ⚠️ **[PARTIAL]** `digestsynopsisSUMMARY.md` describes system architecture | Not audit-formatted | 🟡 P3

---

### CC3.2 — Risk Identification and Analysis

**Official Criterion:** *"The entity identifies risks to the achievement of its objectives across the entity and analyzes risks as a basis for determining how the risks should be managed."*

#### What This Means
You must have a formal Risk Register — a documented list of identified risks, their likelihood, their potential impact, and what you're doing about each one. Auditors look for this to exist, to be current, and to show that you actually respond to the risks you identify.

#### Required Controls
- Formal Risk Register (document identifying threats, vulnerabilities, likelihood, impact)
- Risk scoring methodology (e.g., likelihood × impact matrix)
- Risk owner assigned to each identified risk
- Annual (minimum) risk assessment review
- Risk treatment decisions documented (accept, mitigate, transfer, avoid)

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Risk Register document created and maintained | Expected: `docs/soc2/risk_register.md` | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Risk scoring methodology documented | 🟠 P2
- [ ] 🔍 ⚠️ **[PARTIAL]** `digestsynopsisSUMMARY.md` §5 lists known risks | Not in Risk Register format; lacks likelihood/impact scores | 🟠 P2

---

### CC3.3 — Fraud Risk Assessment

**Official Criterion:** *"The entity considers the potential for fraud in assessing risks to the achievement of objectives."*

#### What This Means
You must specifically assess fraud risks — not just accidents or external attacks. For BidBrief this means: could an employee misuse client data? Could someone abuse the analysis API to extract data? Could credentials be stolen and used to access client documents? These must be identified and controlled.

#### Required Controls
- Fraud risk scenarios documented in the Risk Register
- Segregation of duties controls where fraud risk is high
- Access controls preventing unauthorized data exfiltration
- Monitoring for anomalous access patterns

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Fraud risk scenarios documented (insider threat, API abuse, credential theft) | 🔴 P1
- [ ] ❌ **[GAP]** Anomalous usage detection (e.g., large-volume exports, after-hours access) | 🟠 P2
- [ ] ⚠️ **[PARTIAL]** RBAC limits what regular users can access | Admin role separation exists | `app.py` `require_admin` | 🟡 P3

---

### CC3.4 — Change Risk Assessment

**Official Criterion:** *"The entity identifies and assesses changes that could significantly impact the system of internal control."*

#### What This Means
When significant changes happen — new features, new vendors, infrastructure changes, key personnel departures — you must assess the security impact of those changes before they take effect. Deploying a new AI model or integrating a new third-party API without a security review violates this criterion.

#### Required Controls
- Change impact assessment process (security review before deployment)
- Process for assessing new vendor security impact
- Documentation of change risk assessments
- Change notification to affected parties

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Change risk assessment checklist (used before each deployment) | 🟠 P2
- [ ] 📋 ❌ **[GAP]** New vendor security assessment process (before adding OpenAI-equivalent services) | 🟠 P2
- [ ] 🔍 ❌ **[GAP]** Evidence that recent major changes (CityScraper, security hardening) had security reviews | Check: git PR history for review comments | 🟡 P3

---

---

## CC4 — Monitoring Activities

> The entity must continuously monitor its controls to verify they are working as designed. Auditors look for automated and manual monitoring processes with documented review cadences.

---

### CC4.1 — Ongoing and Separate Evaluations

**Official Criterion:** *"The entity selects, develops, and performs ongoing and/or separate evaluations to ascertain whether the components of internal control are present and functioning."*

#### What This Means
Controls don't just get implemented and forgotten. You must continuously verify they're working. Ongoing evaluation = automated monitoring (log alerts, dependency scanning, uptime monitoring). Separate evaluations = periodic manual reviews (quarterly access reviews, annual penetration test, internal audits).

#### Required Controls
- Automated monitoring of critical security controls (auth failures, rate limit hits, error spikes)
- Periodic access review (quarterly — who has access and should they still have it)
- Annual vulnerability/penetration assessment
- Dependency vulnerability scanning in CI/CD pipeline
- Control testing documentation

#### BidBrief Audit Checklist
- [ ] ❌ **[GAP]** Automated alerting on auth failures / anomalous login patterns | 🔴 P1
- [ ] ❌ **[GAP]** Dependency vulnerability scanning in CI/CD (e.g., GitHub Dependabot, Safety, pip-audit) | 🔴 P1
- [ ] ❌ **[GAP]** Quarterly access review process defined | 🟠 P2
- [ ] ❌ **[GAP]** Annual vulnerability assessment scheduled / evidenced | 🟠 P2
- [ ] ⚠️ **[PARTIAL]** Application health endpoint `/health` exists | Basic liveness check only; no security monitoring | 🟡 P3

---

### CC4.2 — Evaluating and Communicating Deficiencies

**Official Criterion:** *"The entity evaluates and communicates internal control deficiencies in a timely manner to those parties responsible for taking corrective action."*

#### What This Means
When a control gap or failure is found — through monitoring, audit, or incident — there must be a documented process for escalating it, tracking it to resolution, and communicating it to the right people. Bugs in security controls must be treated as formally as production bugs.

#### Required Controls
- Deficiency tracking process (can be GitHub Issues with a security label)
- Defined escalation path for critical security deficiencies
- SLA for remediating P1 security deficiencies (e.g., 24 hours for critical)
- Evidence that identified deficiencies were remediated

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Security deficiency tracking process documented | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Remediation SLAs defined by severity | 🟠 P2
- [ ] 🔍 ⚠️ **[VERIFY]** This document itself (SOC2_TYPE1_REQUIREMENTS.md) can serve as deficiency tracker | Needs: owner assigned, dates, remediation notes per item | 🟡 P3

---

---

## CC5 — Control Activities

> The entity must select, develop, and deploy specific control activities — both general controls and technology-specific controls — and back them with documented policies and procedures.

---

### CC5.1 — Select and Develop Controls

**Official Criterion:** *"The entity selects and develops control activities that contribute to the mitigation of risks to the achievement of objectives to acceptable levels."*

#### What This Means
Controls must be intentionally chosen based on the risks identified in CC3 — not just whatever happened to get built. Auditors look for evidence that controls map back to specific risks and that there are no obvious unmitigated risks left over. A risk register with no corresponding controls is a red flag.

#### Required Controls
- Mapping of identified risks to implemented controls
- Evidence that control selection was deliberate (documented rationale)
- Gap analysis showing no unmitigated high-priority risks
- Control effectiveness reviews

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Risk-to-control mapping matrix | Maps each risk from Risk Register to the control that mitigates it | 🔴 P1
- [ ] 🔍 ⚠️ **[PARTIAL]** Encrypted uploads, RBAC, session management are implemented controls | Not documented as risk responses | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Annual control effectiveness review documented | 🟡 P3

---

### CC5.2 — General Technology Controls

**Official Criterion:** *"The entity also selects and develops general control activities over technology to support the achievement of objectives."*

#### What This Means
Technology-level controls that apply across the whole system: infrastructure hardening, network controls, encryption standards, backup procedures, and software security controls. These are the "default on" security controls that everything else depends on.

#### Required Controls
- Encryption at rest for sensitive data
- Encryption in transit (TLS 1.2+ enforced)
- Network-level access controls (firewall rules, security groups)
- Secure configuration baselines for infrastructure
- Backup and recovery procedures
- Software composition analysis (know what libraries you depend on)

#### BidBrief Audit Checklist
- [ ] ✅ **[PASS]** Encryption in transit via HTTPS (Render provides TLS termination) | Verify TLS version ≥1.2 | 🟠 P2
- [ ] ✅ **[PASS]** File upload encryption implemented | `cryptography` library, see `app.py` `UPLOAD_STORE` | 🟠 P2
- [ ] ❌ **[GAP]** Encryption at rest for persistent data (no DB yet; needed when Neon DB implemented) | 🔴 P1
- [ ] ❌ **[GAP]** Render environment hardening documented (env var security, no debug in prod) | Check: `app.py` `DEBUG` env var | 🟠 P2
- [ ] ❌ **[GAP]** Software Bill of Materials (SBOM) or `requirements.txt` pinned with hash verification | 🟡 P3
- [ ] ❌ **[GAP]** Backup/recovery procedure documented (currently stateless — but once DB added this is critical) | 🟡 P3

---

### CC5.3 — Policies and Procedures

**Official Criterion:** *"The entity deploys control activities through policies that establish what is expected and procedures that put policies into action."*

#### What This Means
Controls must be backed by written policies. A control that exists in code but has no policy document saying it's required is harder to audit and easier to accidentally remove. Every major control category needs a corresponding policy. Policies don't need to be long — a one-page policy is fine — but they must exist and be current.

#### Required Controls
- Information Security Policy (master policy)
- Access Control Policy
- Incident Response Policy
- Change Management Policy
- Data Classification and Handling Policy
- Acceptable Use Policy
- Vulnerability Management Policy

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Information Security Policy | `docs/policies/information_security_policy.md` | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Access Control Policy | `docs/policies/access_control_policy.md` | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Incident Response Policy | `docs/policies/incident_response_policy.md` | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Data Classification and Handling Policy | `docs/policies/data_classification_policy.md` | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Change Management Policy | `docs/policies/change_management_policy.md` | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Vulnerability Management Policy | `docs/policies/vulnerability_management_policy.md` | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Acceptable Use Policy | `docs/policies/acceptable_use_policy.md` | 🟠 P2

---

---

## CC6 — Logical and Physical Access Controls

> The largest and most technically detailed section. Auditors spend the most time here. Controls must cover who gets access, how they authenticate, what they can do, and how access is revoked. Physical access applies to any co-located infrastructure.

---

### CC6.1 — Logical Access Architecture

**Official Criterion:** *"The entity implements logical access security software, infrastructure, and architectures over protected information assets to protect them from security events."*

#### What This Means
The fundamental security architecture must be sound: authentication enforced on all protected routes, sessions managed securely, sensitive data not exposed in URLs or logs, least-privilege by default. Auditors will look at the auth implementation in detail.

#### Required Controls
- Authentication required on all non-public endpoints
- Session tokens cryptographically random and sufficiently long
- Session timeout enforced (idle and absolute)
- Sensitive data not logged or exposed in error messages
- HTTPS enforced — no HTTP fallback for authenticated routes
- Security headers (HSTS, CSP, X-Frame-Options, etc.)

#### BidBrief Audit Checklist
- [ ] ✅ **[PASS]** Authentication enforced via `@require_auth` decorator | `app.py` | 🔴 P1
- [ ] ✅ **[PASS]** Session tokens use `secrets` module (cryptographically random) | `app.py` | 🔴 P1
- [ ] ⚠️ **[PARTIAL]** Session expiry implemented (24-hour TTL + 5-min cleanup thread) | Verify absolute timeout is enforced, not just cleanup | `app.py` `cleanup_old_sessions` | 🔴 P1
- [ ] ❌ **[GAP]** Idle session timeout (currently only absolute TTL, no inactivity timeout) | 🟠 P2
- [ ] ❌ **[GAP]** Security headers not verified: HSTS, CSP, X-Frame-Options, X-Content-Type-Options | Run: `curl -I https://[domain]` and check headers | 🔴 P1
- [ ] ❌ **[GAP]** No rate limiting on authentication endpoints (brute force protection) | 🔴 P1
- [ ] 🔍 ⚠️ **[VERIFY]** Error messages don't leak stack traces or sensitive data to clients | Check `app.py` error handlers | 🟠 P2

---

### CC6.2 — User Registration and Authorization

**Official Criterion:** *"Prior to issuing system credentials and granting system access, the entity registers and authorizes new internal and external users whose access is administered by the entity."*

#### What This Means
You can't just create accounts without an approval process. Every new user must be explicitly authorized by someone with authority to do so. The process must be documented. Auditors will ask: how does a new user get access? Who approves it? Is there a record of that approval?

#### Required Controls
- Documented user provisioning process
- Approval required before account creation
- User identity verification before access granted
- Record of who approved each user's access and when
- New user access limited to least-privilege by default

#### BidBrief Audit Checklist
- [ ] ❌ **[GAP]** Formal user provisioning process documented | Currently: users hardcoded in env vars with no approval trail | 🔴 P1
- [ ] ❌ **[GAP]** User provisioning request + approval records | 🔴 P1
- [ ] ❌ **[GAP]** Admin UI for user management (add/remove/disable users) | Currently env-var only | `app.py` auth config | 🟠 P2
- [ ] ⚠️ **[PARTIAL]** New users default to 'user' role (not admin) | `app.py` | 🟡 P3

---

### CC6.3 — Least Privilege and Role-Based Access

**Official Criterion:** *"The entity authorizes, modifies, or removes access based on roles and responsibilities, giving consideration to least privilege and segregation of duties."*

#### What This Means
Users only get the access they need to do their job — nothing more. Role assignments must be reviewed periodically. When a user's role changes, access is updated. When they leave, access is revoked immediately. Auditors will test whether non-admin users can access admin functions.

#### Required Controls
- RBAC implemented with distinct role definitions
- Least-privilege: default role is most restrictive
- Access review process (quarterly) to verify role assignments are still appropriate
- Immediate access revocation process when user leaves or changes roles
- Segregation of duties for critical functions

#### BidBrief Audit Checklist
- [ ] ✅ **[PASS]** RBAC implemented with admin/user roles | `app.py` `require_admin` | 🔴 P1
- [ ] ✅ **[PASS]** Non-admin users cannot access admin endpoints (returns 403) | `tests/test_api_security.py` | 🔴 P1
- [ ] ❌ **[GAP]** Quarterly access review process | 🟠 P2
- [ ] ❌ **[GAP]** Offboarding checklist — immediate account deactivation process | 🟠 P2
- [ ] ❌ **[GAP]** Role change process documented | 🟡 P3

---

### CC6.4 — Physical Access Controls

**Official Criterion:** *"The entity restricts physical access to facilities and protected information assets to authorized personnel."*

#### What This Means
For cloud-hosted applications like BidBrief, physical access to servers is handled by the cloud provider (Render). You must document this reliance, obtain and retain Render's SOC 2 report, and verify their physical security controls satisfy this criterion. You inherit their physical controls.

#### Required Controls
- Documented reliance on cloud provider for physical security
- Vendor assessment: obtain Render's SOC 2 / security attestation
- No sensitive data stored on developer laptops unencrypted
- Developer workstation security (disk encryption, screen lock)

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Render SOC 2 report obtained and retained | Download from: render.com/security | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Documented reliance on Render for physical security | In vendor assessment doc | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Developer workstation policy (disk encryption required, screen lock) | 🟠 P2

---

### CC6.5 — Decommissioning / Media Disposal

**Official Criterion:** *"The entity discontinues logical and physical protections over physical assets only after the ability to read or recover data has been diminished and is no longer required."*

#### What This Means
When you stop using a server, storage volume, or decommission a system, you must ensure data is securely wiped before disposal or transfer. For BidBrief's ephemeral upload model, this means the secure deletion of temp files must be verified. For any future database, decommissioning procedures must exist.

#### Required Controls
- Secure deletion of uploaded files after processing (verified)
- Data disposal procedures for any persistent storage
- Decommissioning checklist for retired infrastructure
- Record of data destruction events

#### BidBrief Audit Checklist
- [ ] ✅ **[PASS]** Uploaded files encrypted and deleted after session expiry | `app.py` `UPLOAD_STORE` cleanup | 🟠 P2
- [ ] 🔍 ⚠️ **[VERIFY]** Secure deletion actually removes files (not just unlinks) | Check `app.py` temp file cleanup code | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Data disposal procedure for when persistent DB is added | 🟡 P3

---

### CC6.6 — External Threat Protection

**Official Criterion:** *"The entity implements logical access security measures to protect against threats from sources outside its system boundaries."*

#### What This Means
Protection from external attackers: DDoS mitigation, firewall rules, WAF, input validation, injection prevention, brute-force protection, and secure API design. Auditors look for defense in depth against external threats, not just internal access controls.

#### Required Controls
- Rate limiting on all public endpoints
- Input validation on all user-supplied data
- Protection against injection attacks (SQL, command, prompt injection)
- DDoS protection (via CDN or cloud provider)
- Firewall / network access control
- API authentication required on all sensitive endpoints

#### BidBrief Audit Checklist
- [ ] ❌ **[GAP]** Rate limiting on API endpoints (especially `/api/analyze`, `/auth/login`) | 🔴 P1
- [ ] ❌ **[GAP]** Rate limiting on file upload endpoint | 🔴 P1
- [ ] 🔍 ⚠️ **[VERIFY]** Input validation on all user-supplied data before processing | Check: `app.py` upload handler, analyze endpoint | 🔴 P1
- [ ] 🔍 ⚠️ **[VERIFY]** No path traversal vulnerability in file handling | Check: `secure_filename` usage in `app.py` | 🟠 P2
- [ ] ❌ **[GAP]** Render DDoS protection / WAF configured | Check Render dashboard | 🟠 P2
- [ ] ❌ **[GAP]** AI prompt injection mitigations documented (user content passed to LLM) | 🟠 P2

---

### CC6.7 — Data Transmission Controls

**Official Criterion:** *"The entity restricts the transmission, movement, and removal of information to authorized users and processes, and protects it during transmission."*

#### What This Means
Data moving between the user's browser and BidBrief, between BidBrief and OpenAI/Tavily, and between system components must be encrypted and authenticated. Sensitive data must not be transmitted in URLs (query strings), headers that get logged, or unencrypted channels.

#### Required Controls
- TLS 1.2+ for all data transmission
- No sensitive data in URL query strings
- API keys transmitted only in headers (never in URLs or logs)
- Outbound API calls authenticated (OpenAI, Tavily)
- Data minimization: only send what's needed to third-party APIs

#### BidBrief Audit Checklist
- [ ] ✅ **[PASS]** HTTPS enforced for all client communication (Render TLS) | 🔴 P1
- [ ] 🔍 ⚠️ **[VERIFY]** No sensitive data (session tokens, file content) in query parameters | Check `app.py` route parameters | 🔴 P1
- [ ] ✅ **[PASS]** OpenAI API key transmitted via Authorization header | `openai` Python SDK default | 🟠 P2
- [ ] ❌ **[GAP]** Data minimization policy for OpenAI API calls documented (what content is sent, why) | 🟠 P2
- [ ] ❌ **[GAP]** API call logging does not capture request/response bodies containing PII | 🟠 P2

---

### CC6.8 — Malware Prevention

**Official Criterion:** *"The entity implements controls to prevent or detect and act upon the introduction of unauthorized or malicious software."*

#### What This Means
Malicious code must not enter the system through uploads, dependencies, or development processes. File uploads must be validated and sandboxed. Dependencies must be scanned for known vulnerabilities. Developer machines must not introduce malware via compromised development environments.

#### Required Controls
- File type validation and size limits on uploads
- Dependency vulnerability scanning (pip-audit, Safety, Snyk)
- SAST (static analysis) in CI/CD pipeline
- No execution of uploaded files
- Malware scanning on uploaded files (optional but recommended)

#### BidBrief Audit Checklist
- [ ] ⚠️ **[PARTIAL]** File upload type validation exists | Verify: what types are allowed, are MIME types checked? `app.py` upload handler | 🔴 P1
- [ ] ❌ **[GAP]** File size limits enforced on uploads | 🟠 P2
- [ ] ❌ **[GAP]** `pip-audit` or `safety` run in CI/CD | 🔴 P1
- [ ] ❌ **[GAP]** Bandit (Python SAST) run in CI/CD | 🟠 P2
- [ ] ✅ **[PASS]** Uploaded files are parsed/read only — not executed | `services/document_extractor.py` | 🔴 P1

---

---

## CC7 — System Operations

> Ongoing operational security: detecting threats, monitoring events, responding to incidents, and recovering from them. Auditors look for evidence of active security operations, not just implemented controls.

---

### CC7.1 — Vulnerability Detection

**Official Criterion:** *"To detect and monitor for new vulnerabilities, the entity utilizes detection tools or techniques."*

#### What This Means
You must actively look for vulnerabilities, not wait for them to be exploited. This includes: dependency scanning for CVEs, SAST scans for code vulnerabilities, infrastructure misconfiguration scanning, and tracking of security advisories for technologies you use (Python, Flask, gunicorn, etc.).

#### Required Controls
- Automated dependency vulnerability scanning (weekly minimum)
- SAST in CI/CD pipeline
- Subscription to security advisories for key dependencies
- Infrastructure security configuration scanning
- Penetration test or vulnerability assessment (annually)

#### BidBrief Audit Checklist
- [ ] ❌ **[GAP]** `pip-audit` or `safety check` integrated into CI/CD | 🔴 P1
- [ ] ❌ **[GAP]** GitHub Dependabot alerts enabled on repository | 🔴 P1
- [ ] ❌ **[GAP]** Bandit SAST scan on each commit/PR | 🟠 P2
- [ ] ❌ **[GAP]** Process for reviewing and acting on Dependabot/pip-audit findings | 🟠 P2
- [ ] ❌ **[GAP]** Annual vulnerability assessment / pen test scheduled | 🟡 P3

---

### CC7.2 — Security Event Monitoring

**Official Criterion:** *"The entity monitors system components and the operation of those components for anomalies that are indicative of malicious acts, natural disasters, and errors."*

#### What This Means
Passive logging is not enough — there must be active monitoring that detects and alerts on anomalies. Failed login bursts, unusual API call volumes, errors spiking, or access from unexpected locations should trigger alerts. Auditors want to see alerting rules, not just log files.

#### Required Controls
- Centralized log aggregation (log drain to persistent service)
- Alerting on: authentication failures (> threshold), error rate spikes, API quota anomalies
- Uptime monitoring with alerting
- Log retention: minimum 90 days accessible, 12 months archived
- Review of security logs on defined cadence

#### BidBrief Audit Checklist
- [ ] ❌ **[GAP]** Log drain configured on Render (ship logs to Papertrail, Datadog, Logtail, etc.) | 🔴 P1
- [ ] ❌ **[GAP]** Alert rule: N failed logins in M minutes | 🔴 P1
- [ ] ❌ **[GAP]** Uptime monitoring (UptimeRobot, Render health checks, or similar) | 🟠 P2
- [ ] ❌ **[GAP]** Log retention policy enforced (logs kept ≥ 90 days) | 🟠 P2
- [ ] ❌ **[GAP]** Weekly security log review process defined | 🟡 P3

---

### CC7.3 — Incident Identification and Classification

**Official Criterion:** *"The entity evaluates security events to determine whether they could or have resulted in a failure of the entity to meet its objectives (security incidents) and, if so, takes actions to prevent or address such failures."*

#### What This Means
Not every security event is an incident, but there must be a documented process for triaging events, classifying them by severity, and escalating appropriately. What's the threshold for declaring an incident? Who decides? How fast must they act?

#### Required Controls
- Incident severity classification matrix (P1/P2/P3 definitions)
- Documented triage process: event → analysis → classification → response
- On-call/escalation contact list
- Incident log/tracker

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Incident severity classification matrix | What makes something a P1 vs P2? | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Incident triage process documented | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Incident log (can be a GitHub Issues board with `security-incident` label) | 🟠 P2

---

### CC7.4 — Incident Response Plan

**Official Criterion:** *"The entity responds to identified security incidents by executing a defined incident-response program to understand, contain, remediate, and communicate security incidents."*

#### What This Means
When something goes wrong, there must be a written playbook to follow. Auditors will ask to see the Incident Response Plan and evidence it has been tested (tabletop exercise or actual incident handled per the plan). The plan must cover: detection, containment, eradication, recovery, and post-incident review.

#### Required Controls
- Written Incident Response Plan (IRP)
- Defined roles in IRP (Incident Commander, Communications Lead, Technical Lead)
- Containment procedures for common incident types (data breach, compromised credentials, DDoS)
- Customer notification procedures within regulatory timeframes
- Post-incident review / lessons learned process

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Incident Response Plan document | `docs/policies/incident_response_plan.md` | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Containment runbook for: credential compromise, data breach, API key leak | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Customer breach notification template and timeline (72 hours per GDPR if applicable) | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Annual IRP tabletop exercise documented | 🟡 P3

---

### CC7.5 — Recovery

**Official Criterion:** *"The entity identifies, develops, and implements activities to recover from identified security incidents."*

#### What This Means
After an incident is contained, there must be a recovery plan: restore service, verify integrity, communicate resolution to stakeholders, and do a post-mortem. Recovery also means having tested backups so you can restore to a known-good state if needed.

#### Required Controls
- Recovery time objective (RTO) and recovery point objective (RPO) defined
- Backup and restore procedures documented and tested
- Post-incident review process (blameless post-mortem)
- Service restoration checklist
- Communication plan for notifying customers after incident resolved

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** RTO and RPO defined for BidBrief | Currently stateless so RTO = redeploy time | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Recovery runbook | Steps to restore service after a compromise | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Post-incident review template | 🟡 P3

---

---

## CC8 — Change Management

> Every change to the production system must be controlled, tested, approved, and documented. Unauthorized or untested changes are a primary source of security incidents.

---

### CC8.1 — Change Management Process

**Official Criterion:** *"The entity authorizes, designs, develops or acquires, configures, documents, tests, approves, and implements changes to infrastructure, data, software, and procedures to meet its change management objectives."*

#### What This Means
Changes to code, infrastructure, configuration, and third-party integrations must follow a controlled process. Auditors look for: no direct pushes to main without review, tested changes, documented approvals, and rollback capability. For a small team, this can be Git branch protection + PR review.

#### Required Controls
- Branch protection on main/production branch (require PR + review)
- No direct commits to production
- Change testing requirement before deployment
- Change approval process documented
- Rollback procedure for failed changes
- Configuration changes tracked (IaC or documented)
- Emergency change process defined

#### BidBrief Audit Checklist
- [ ] 🔍 ❌ **[GAP]** Branch protection enabled on `master` branch (require PR review before merge) | Check: GitHub repo Settings → Branches | 🔴 P1
- [ ] ❌ **[GAP]** CI/CD pipeline runs tests before deployment (currently manual deploys?) | Check: `.github/workflows/` or Render deploy hooks | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Change management policy documented (what requires a PR, what requires approval) | 🟠 P2
- [ ] ⚠️ **[PARTIAL]** Git history provides change audit trail | All commits visible | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Emergency change process (hotfix procedure) documented | 🟡 P3

---

---

## CC9 — Risk Mitigation

> Beyond identifying risks (CC3), the entity must actively mitigate them — especially risks from business disruptions and from third-party vendors.

---

### CC9.1 — Business Continuity and Disruption Risk

**Official Criterion:** *"The entity identifies, selects, and develops risk mitigation activities for risks arising from potential business disruptions."*

#### What This Means
What happens if Render goes down? What if OpenAI has an outage? What if the API key is compromised? There must be documented responses to foreseeable disruption scenarios. Business Continuity Planning doesn't require a massive document for a SaaS startup — but it does require defined responses to key failure scenarios.

#### Required Controls
- Business Continuity Plan (BCP) addressing key disruption scenarios
- Single points of failure identified and mitigated or accepted
- Vendor redundancy plan (what if OpenAI is unavailable)
- Defined communication plan during outages

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Business Continuity Plan | Key scenarios: Render outage, OpenAI outage, API key compromise, data breach | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Single point of failure analysis | Currently: single Gunicorn worker, in-memory sessions | 🟠 P2
- [ ] ⚠️ **[PARTIAL]** Graceful degradation when Tavily unavailable (commit `a3427de`) | Good pattern — extend to OpenAI fallback | 🟡 P3

---

### CC9.2 — Vendor / Third-Party Risk Management

**Official Criterion:** *"The entity assesses and manages risks associated with vendors and business partners."*

#### What This Means
Every third-party service you use is a risk. If OpenAI is breached, your client's document content could be exposed. You must have a vendor inventory, assess each vendor's security posture, review their compliance certifications (SOC 2, ISO 27001), and have contractual data protection agreements (DPAs) where required.

#### Required Controls
- Vendor inventory with security classification
- Vendor security assessment for each critical vendor
- Data Processing Agreements (DPAs) with vendors that handle personal/confidential data
- Annual vendor security review
- Vendor SOC 2 reports obtained and reviewed

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Vendor inventory documented | At minimum: OpenAI, Render, Tavily, GitHub | 🔴 P1
- [ ] 📋 ❌ **[GAP]** OpenAI DPA / data processing terms reviewed and signed | OpenAI API terms address this — document it | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Render security posture documented (obtain their compliance certs) | 🟠 P2
- [ ] 📋 ❌ **[GAP]** Annual vendor security review process | 🟠 P2

---

---

# PART 2: CONFIDENTIALITY (C)

---

## C1 — Confidentiality

> The entity must identify, protect, and properly dispose of information designated as confidential. For BidBrief, this directly covers the client bid documents and inspection reports processed through the platform.

---

### C1.1 — Identifying and Protecting Confidential Information

**Official Criterion:** *"The entity identifies and maintains confidential information to meet the entity's objectives related to confidentiality."*

#### What This Means
You must have a data classification scheme that identifies what is confidential. All data flowing through BidBrief that clients designate as confidential must be tagged, handled according to the classification policy, encrypted in transit and at rest, and accessible only to authorized users. Auditors will ask: how do you know what's confidential, and how do you prove it's protected?

#### Required Controls
- Data classification policy (Public / Internal / Confidential / Restricted)
- All uploaded client documents classified as Confidential by default
- Confidential data encrypted in transit (TLS) and at rest (storage encryption)
- Access to confidential data logged
- Confidentiality commitments in customer contracts / ToS
- Employee/contractor NDAs covering client data

#### BidBrief Audit Checklist
- [ ] 📋 ❌ **[GAP]** Data classification policy documenting what constitutes "Confidential" | `docs/policies/data_classification_policy.md` | 🔴 P1
- [ ] ✅ **[PASS]** Uploaded files encrypted during temporary storage | `app.py` `UPLOAD_STORE`, `cryptography` library | 🔴 P1
- [ ] ✅ **[PASS]** Client documents accessible only to authenticated sessions | `@require_auth` on all analysis routes | 🔴 P1
- [ ] ❌ **[GAP]** Confidentiality commitments in customer-facing Terms of Service | 🔴 P1
- [ ] ❌ **[GAP]** Access to client documents logged with user identity | Audit log must include: who accessed what document when | 🟠 P2
- [ ] ❌ **[GAP]** Employee/contractor NDAs that cover client data | 🟠 P2
- [ ] ❌ **[GAP]** Confidential data is not sent to third-party services without disclosure | OpenAI receives document content — this must be disclosed to clients | 🔴 P1

---

### C1.2 — Disposal of Confidential Information

**Official Criterion:** *"The entity disposes of confidential information to meet the entity's objectives related to confidentiality."*

#### What This Means
Confidential data must be deleted when it's no longer needed — and that deletion must be verified. Data retention schedules must exist. For BidBrief's ephemeral model, uploaded documents are auto-deleted after session expiry — but this must be documented as a policy, verified in code, and communicated to clients.

#### Required Controls
- Data retention schedule (how long each data type is kept)
- Automated data deletion verified in code
- Data disposal policy communicated to clients
- Disposal records for any long-term storage
- Process for customer data deletion requests

#### BidBrief Audit Checklist
- [ ] ✅ **[PASS]** Uploaded files deleted after session expiry (cleanup thread) | `app.py` `cleanup_old_sessions` | 🔴 P1
- [ ] 🔍 ⚠️ **[VERIFY]** Session data (in-memory) cleared on expiry, not just files | Check `app.py` cleanup code | 🔴 P1
- [ ] 📋 ❌ **[GAP]** Data Retention Policy documented and customer-facing | How long is data kept? When is it deleted? | 🔴 P1
- [ ] ❌ **[GAP]** Customer data deletion request process (right to erasure) | 🟠 P2
- [ ] ❌ **[GAP]** Deletion logging: record that data was deleted, when, by what process | 🟡 P3

---

---

# PART 3: GAP SUMMARY

> All items marked ❌ GAP, organized by priority. This is your to-do list for achieving SOC 2 Type I readiness.

## P1 — Must Fix Before Audit (23 items)

| # | Criterion | Gap | Owner | Target Date | Status |
|---|-----------|-----|-------|-------------|--------|
| 1 | CC1.1 | Code of Conduct / Acceptable Use Policy | | | ❌ |
| 2 | CC1.1 | Information Security Policy | | | ❌ |
| 3 | CC1.1 | No secrets/credentials in source code (verify) | | | 🔍 |
| 4 | CC1.2 | Security Officer designation documented | | | ❌ |
| 5 | CC1.3 | Authorization matrix documented | | | ❌ |
| 6 | CC1.5 | Audit logs persisted beyond process lifetime | | | ❌ |
| 7 | CC2.1 | Logs shipped to persistent tamper-resistant store | | | ❌ |
| 8 | CC2.2 | Security onboarding checklist | | | ❌ |
| 9 | CC2.3 | Privacy Policy published | | | ❌ |
| 10 | CC2.3 | Vulnerability Disclosure Policy | | | ❌ |
| 11 | CC3.1 | Formal System Description document | | | ❌ |
| 12 | CC3.1 | Data inventory and data flow diagram | | | ❌ |
| 13 | CC3.2 | Risk Register created | | | ❌ |
| 14 | CC3.3 | Fraud risk scenarios documented | | | ❌ |
| 15 | CC5.1 | Risk-to-control mapping matrix | | | ❌ |
| 16 | CC5.3 | 7 policy documents (full list in CC5.3) | | | ❌ |
| 17 | CC6.1 | Security headers (HSTS, CSP, etc.) | | | ❌ |
| 18 | CC6.1 | Rate limiting on auth endpoints | | | ❌ |
| 19 | CC6.2 | User provisioning process documented | | | ❌ |
| 20 | CC6.2 | User provisioning approval records | | | ❌ |
| 21 | CC6.4 | Render SOC 2 report obtained | | | ❌ |
| 22 | CC6.6 | Rate limiting on all API endpoints | | | ❌ |
| 23 | CC6.8 | pip-audit / safety in CI/CD | | | ❌ |
| 24 | CC7.1 | GitHub Dependabot enabled | | | ❌ |
| 25 | CC7.2 | Log drain to persistent service | | | ❌ |
| 26 | CC7.2 | Alert on auth failure threshold | | | ❌ |
| 27 | CC7.3 | Incident severity classification matrix | | | ❌ |
| 28 | CC7.3 | Incident triage process | | | ❌ |
| 29 | CC7.4 | Incident Response Plan | | | ❌ |
| 30 | CC7.4 | Containment runbooks | | | ❌ |
| 31 | CC8.1 | Branch protection on master | | | ❌ |
| 32 | CC9.1 | Business Continuity Plan | | | ❌ |
| 33 | CC9.2 | Vendor inventory | | | ❌ |
| 34 | CC9.2 | OpenAI DPA reviewed | | | ❌ |
| 35 | C1.1 | Data classification policy | | | ❌ |
| 36 | C1.1 | Confidentiality commitments in ToS | | | ❌ |
| 37 | C1.1 | Disclosure that OpenAI receives document content | | | ❌ |
| 38 | C1.2 | Data Retention Policy published | | | ❌ |

## P2 — Required for Type I, Lower Audit Risk (19 items)

| # | Criterion | Gap | Owner | Target Date | Status |
|---|-----------|-----|-------|-------------|--------|
| 1 | CC1.5 | Log retention policy (90 days) | | | ❌ |
| 2 | CC2.2 | Incident reporting procedure communicated | | | ❌ |
| 3 | CC2.3 | Data breach notification process | | | ❌ |
| 4 | CC3.4 | Change risk assessment checklist | | | ❌ |
| 5 | CC4.1 | Quarterly access review process | | | ❌ |
| 6 | CC4.1 | Annual vulnerability assessment scheduled | | | ❌ |
| 7 | CC4.2 | Security deficiency tracking process | | | ❌ |
| 8 | CC5.2 | Render hardening documented (no debug in prod) | | | ❌ |
| 9 | CC6.1 | Idle session timeout | | | ❌ |
| 10 | CC6.3 | Quarterly access review | | | ❌ |
| 11 | CC6.3 | Offboarding checklist | | | ❌ |
| 12 | CC6.6 | Input validation on all user-supplied data | | | ❌ |
| 13 | CC6.7 | Data minimization policy for OpenAI calls | | | ❌ |
| 14 | CC7.2 | Uptime monitoring configured | | | ❌ |
| 15 | CC7.5 | Recovery runbook | | | ❌ |
| 16 | CC8.1 | CI/CD pipeline with pre-deploy tests | | | ❌ |
| 17 | CC9.2 | Annual vendor security review process | | | ❌ |
| 18 | C1.1 | Access to client documents logged | | | ❌ |
| 19 | C1.2 | Customer data deletion request process | | | ❌ |

## P3 — Best Practice / Required for Type II (8 items)

| # | Criterion | Gap | Owner | Target Date | Status |
|---|-----------|-----|-------|-------------|--------|
| 1 | CC1.4 | Security awareness training tracked | | | ❌ |
| 2 | CC4.1 | Control testing documentation | | | ❌ |
| 3 | CC5.2 | requirements.txt pinned with hash verification | | | ❌ |
| 4 | CC6.3 | Role change process documented | | | ❌ |
| 5 | CC7.5 | Post-incident review template | | | ❌ |
| 6 | CC8.1 | Emergency change (hotfix) procedure | | | ❌ |
| 7 | CC9.1 | OpenAI/Render outage graceful degradation | | | ❌ |
| 8 | C1.2 | Deletion logging / records | | | ❌ |

---

## What Passes Today

| Control | Evidence |
|---------|---------|
| Auth enforced on all protected routes | `app.py` `@require_auth` decorator |
| Cryptographically random session tokens | `secrets` module in `app.py` |
| RBAC (admin/user) implemented | `app.py` `@require_admin` |
| Non-admin gets 403 on admin routes | `tests/test_api_security.py` |
| File upload encryption | `cryptography` lib, `UPLOAD_STORE` in `app.py` |
| Uploaded files auto-deleted on session expiry | `app.py` `cleanup_old_sessions` |
| HTTPS via Render TLS | Render platform |
| OpenAI API key in env var (not hardcoded) | `.env` / `OPENAI_API_KEY` |
| Graceful Tavily fallback | Commit `a3427de` |
| Session TTL (24-hour absolute expiry) | `app.py` |

---

*Document version: 1.0.0*
*Created: 2026-03-03*
*Next review due: 2026-06-03*
*Standard reference: AICPA Trust Services Criteria 2017, updated 2022*
