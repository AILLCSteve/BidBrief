# Acceptable Use Policy

**Version:** 1.0
**Effective Date:** 2026-03-03
**Owner:** Stephen Bartlett, C.E.O., Security Officer
**Company:** Additional Intelligence LLC
**Review Cycle:** Annual
**Next Review:** 2027-03-03

---

## 1. Purpose

This policy defines the acceptable use of BidBrief systems, infrastructure,
and client data by all personnel and authorized users of Additional Intelligence
LLC. It protects clients, the company, and individuals from misuse, legal
liability, and security incidents.

## 2. Scope

This policy applies to:
- All employees, contractors, and consultants of Additional Intelligence LLC
- Any individual with access to BidBrief systems, infrastructure, or client data
- All devices used to access BidBrief systems (company-owned or personal)

## 3. Authorized Use

BidBrief systems, infrastructure, and client data are provided solely for
legitimate business purposes in support of Additional Intelligence LLC's
services. Authorized uses include:

- Developing, testing, maintaining, and improving the BidBrief platform
- Providing client support and resolving technical issues
- Conducting authorized security assessments and monitoring
- Accessing client data when directly required to fulfill a client request or resolve a reported issue

## 4. Prohibited Activities

The following activities are strictly prohibited and may result in immediate
termination of access and, where applicable, legal action:

### Data Handling Prohibitions
- Accessing, copying, or transmitting client data for any purpose not directly
  related to providing BidBrief services to that client
- Storing client data (documents, analysis results, credentials) on personal
  devices, personal cloud storage (Google Drive, Dropbox, etc.), or any system
  outside of BidBrief's authorized infrastructure
- Sharing client data with any third party not explicitly authorized in the
  Data Classification Policy or client agreement
- Using client data to train personal AI models or for personal research

### Security Prohibitions
- Sharing login credentials with any other person under any circumstances
- Logging in with another person's account credentials, even with their permission
- Disabling, bypassing, or circumventing any security control without Security
  Officer written authorization
- Installing unauthorized software, scripts, or tools in the production environment
- Introducing code with intentional vulnerabilities, backdoors, or data exfiltration
- Accessing systems, accounts, or data beyond what is required for your current role
- Attempting to access other users' sessions, data, or accounts

### Infrastructure Prohibitions
- Using BidBrief infrastructure for personal projects, cryptocurrency mining,
  or any activity unrelated to Additional Intelligence LLC business
- Modifying production environment variables, infrastructure settings, or
  security configurations without following the Change Management Policy
- Deploying code directly to production without following the PR review process
- Deleting or modifying audit logs or security-relevant records

### Communication Prohibitions
- Publicly disclosing client information, security vulnerabilities, or internal
  system details on social media, forums, or any public channel
- Discussing active security incidents with unauthorized parties
- Making public claims about BidBrief's security posture without Security
  Officer approval

## 5. Personal Device Usage

When accessing BidBrief systems from personal devices:

- Device must have full-disk encryption enabled
- Device must require a password or biometric to unlock (auto-lock within 15 minutes of inactivity)
- Device must have up-to-date operating system patches applied
- Do not leave sessions open and unattended on personal devices
- Report lost or stolen devices immediately to stephen@additionalintel.com

## 6. Monitoring

Additional Intelligence LLC may monitor activity on BidBrief systems for
security purposes. This includes:
- Authentication events (logins, failed logins, logouts)
- Data access events (file uploads, analysis runs, exports)
- API calls and system operations
- Network traffic patterns

**There is no expectation of privacy** when using BidBrief systems for any
purpose. Monitoring data may be used in security investigations and, where
appropriate, legal proceedings.

## 7. Reporting Violations

If you become aware of a policy violation — including accidental violations by
yourself — report it immediately to:

**Email:** stephen@additionalintel.com
**What to include:** What you observed, when, what systems were involved, any
actions already taken.

Good-faith reporting is protected. Individuals who report violations are not
subject to retaliation. Self-reported accidental violations receive more
favorable treatment than discovered violations.

## 8. Consequences of Violation

Policy violations are reviewed by the Security Officer. Consequences depend on
severity, intent, and impact:

| Severity | Examples | Consequence |
|----------|---------|------------|
| Minor — Accidental | Accessing wrong data by mistake, late policy acknowledgment | Documented warning, retraining |
| Moderate — Negligent | Storing client data in unauthorized location, sharing passwords | Formal warning, temporary access restriction, corrective action plan |
| Severe — Intentional or Reckless | Unauthorized data access/disclosure, bypassing security controls | Immediate access revocation, contract termination, potential legal action |

Violations that expose client data are simultaneously treated as security
incidents under the Incident Response Plan.

## 9. Annual Acknowledgment

All personnel with access to BidBrief systems must acknowledge this policy
annually. Acknowledgment is recorded at `docs/soc2/policy_acknowledgments.md`.

New personnel must acknowledge this policy **before** receiving system access.

**Acknowledgment statement:**
> "I have read and understand the BidBrief Acceptable Use Policy. I agree to
> comply with all requirements and understand that violations may result in
> disciplinary action up to and including termination."

---

*Approved by: Stephen Bartlett, C.E.O., Security Officer*
*Approval date: 2026-03-03*
*Document location: `docs/policies/acceptable_use_policy.md`*
