# Information Security Policy

**Version:** 1.0
**Effective Date:** 2026-03-03
**Owner:** Stephen Bartlett, C.E.O., Security Officer
**Company:** Additional Intelligence LLC
**Review Cycle:** Annual
**Next Review:** 2027-03-03

---

## 1. Purpose and Scope

This policy establishes the information security requirements for BidBrief,
an AI-powered document analysis platform operated by Additional Intelligence LLC.
It applies to all personnel, contractors, and systems that access, process, or
store BidBrief data or infrastructure.

BidBrief processes confidential client documents including bid specifications,
CIPP project files, inspection reports, and municipal infrastructure data.
The protection of this information is both a business obligation and a trust
commitment to every client.

## 2. Security Objectives

BidBrief is committed to maintaining the following properties for all
information it processes or stores:

- **Confidentiality:** Protecting client documents and data from unauthorized
  disclosure to any party not explicitly authorized by the client
- **Integrity:** Ensuring data accuracy and completeness, and preventing
  unauthorized creation, modification, or deletion
- **Availability:** Maintaining system availability sufficient to meet client
  operational needs, particularly time-sensitive bid preparation workflows

## 3. Roles and Responsibilities

| Role | Person | Responsibilities |
|------|--------|-----------------|
| Security Officer | Stephen Bartlett, C.E.O. | Owns this policy; conducts quarterly security reviews; approves exceptions; leads incident response |
| Developer / Engineer | Stephen Bartlett, C.E.O. | Follows secure development standards; reports vulnerabilities immediately; maintains system security controls |
| All Personnel | Everyone with system access | Completes annual security awareness review; reports suspected incidents within 1 hour; follows all policies in this directory |

## 4. Asset Classification

All information assets are classified per the Data Classification Policy
(`data_classification_policy.md`). Client documents uploaded to BidBrief
are classified as **Confidential** by default. Authentication credentials
and API keys are classified as **Restricted**.

No Confidential or Restricted data shall be transmitted, stored, or processed
outside of the controls defined in this policy without explicit Security Officer
approval.

## 5. Access Control

Access to BidBrief systems is governed by the Access Control Policy
(`access_control_policy.md`). Key principles enforced at all times:

- **Least privilege:** Users receive the minimum access required for their role
- **Unique accounts:** No shared credentials; every person has their own account
- **Access reviews:** Conducted quarterly by the Security Officer
- **Immediate revocation:** Access revoked same-day on termination or compromise

## 6. Acceptable Use

All personnel must comply with the Acceptable Use Policy (`acceptable_use_policy.md`).
BidBrief systems and client data are authorized for legitimate business purposes
only. Violations are handled per Section 9 of this document.

## 7. Incident Response

Security incidents are handled per the Incident Response Plan
(`incident_response_plan.md`). All personnel must:

- Report suspected incidents within **1 hour** of discovery
- Contact: stephen@additionalintel.com
- Do NOT attempt to investigate or remediate independently
- Do NOT discuss the incident publicly or on unsecured channels

## 8. Change Management

All changes to BidBrief production systems — including code, configuration,
infrastructure, and third-party integrations — follow the Change Management
Policy (`change_management_policy.md`).

Key requirements:
- No direct commits to the `master` branch (pull request required)
- Full test suite must pass before any deployment
- Security-impacting changes require Security Officer review
- Emergency changes receive retrospective approval within 24 hours

## 9. Violation Enforcement

Policy violations are reviewed by the Security Officer upon discovery. Response
is proportional to severity:

| Severity | Examples | Response |
|----------|---------|---------|
| Minor | Late policy acknowledgment, procedural shortcut | Retraining, corrective action |
| Moderate | Sharing credentials, bypassing access controls | Formal warning, access restriction |
| Severe | Unauthorized data disclosure, intentional policy bypass | Contract termination, legal action |

Violations that result in or risk client data exposure are treated as P1
security incidents and follow the full Incident Response Plan.

## 10. Exceptions

Exceptions to this policy require:
1. Written request to the Security Officer with justification
2. Documented compensating controls
3. Defined expiry date (maximum 90 days without re-approval)
4. Security Officer written approval

All approved exceptions are logged at `docs/soc2/policy_exceptions.md`.

## 11. Policy Review

This policy is reviewed:
- **Annually** (minimum): Security Officer conducts full review
- **After any significant security incident**: Review triggered within 30 days
- **After major system changes**: Review triggered if new risks are introduced

Changes require Security Officer approval and are communicated to all
personnel within 5 business days of the updated version being published.

---

*Approved by: Stephen Bartlett, C.E.O., Security Officer*
*Approval date: 2026-03-03*
*Document location: `docs/policies/information_security_policy.md`*
