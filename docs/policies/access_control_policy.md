# Access Control Policy

**Version:** 1.0
**Effective Date:** 2026-03-03
**Owner:** Stephen Bartlett, C.E.O., Security Officer
**Company:** Additional Intelligence LLC
**Review Cycle:** Annual
**Next Review:** 2027-03-03

---

## 1. Purpose

This policy defines how access to BidBrief systems and data is granted,
managed, reviewed, and revoked. It enforces the principle of least privilege
across all systems operated by Additional Intelligence LLC.

## 2. Scope

This policy applies to all accounts with access to any of the following:

- BidBrief web application (production)
- Render hosting dashboard
- GitHub repository (source code)
- OpenAI API account
- Tavily API account
- Neon DB / any production database (when implemented)
- Log aggregation service
- Any other system that processes BidBrief data

## 3. Access Roles

### Application Roles

| Role | Description | Default? | Who May Assign |
|------|-------------|----------|----------------|
| `admin` | Full system access: user management, all sessions, all configuration, all exports | No | Security Officer only |
| `user` | Analysis and export only; cannot access admin functions, other users' sessions, or system configuration | Yes | Admin |

New accounts are always provisioned as `user` unless the Security Officer
explicitly approves `admin` role in writing.

### Infrastructure Roles

| System | Role | Who Has Access |
|--------|------|---------------|
| Render dashboard | Owner/Admin | Security Officer only |
| GitHub repository | Admin | Security Officer |
| GitHub repository | Write | Authorized developers |
| OpenAI API | Key holder | Security Officer |
| Tavily API | Key holder | Security Officer |

## 4. Provisioning Process

No account shall be created without following these steps:

**Step 1 — Request**
Requester submits access request to Security Officer via email to
stephen@additionalintel.com including:
- Full name and role/title
- Business justification
- Required role (`admin` or `user`)
- Expected access duration (permanent or temporary)

**Step 2 — Review**
Security Officer evaluates:
- Is this person authorized to access BidBrief?
- Does the requested role match their responsibilities?
- Is there a legitimate business need?

**Step 3 — Approval**
Security Officer approves or denies in writing (email reply is sufficient).
Denied requests include a reason.

**Step 4 — Provisioning**
Upon approval, account is created with the approved role. Temporary access
includes an expiry date set at time of creation.

**Step 5 — Onboarding**
New user receives:
- Account credentials via secure channel (never plain email)
- Link to Acceptable Use Policy with acknowledgment required before first login
- Contact for security questions

**Step 6 — Logging**
Access grant recorded in `docs/soc2/access_grant_log.md`.

## 5. Password Requirements

All passwords for BidBrief-related systems must meet:

- **Minimum length:** 16 characters
- **Complexity:** Mix of uppercase, lowercase, numbers, and symbols
- **Uniqueness:** Not reused from any other service
- **Storage:** Password manager recommended; never stored in plaintext
- **Rotation:** Changed immediately upon suspected compromise
- **Sharing:** Never shared under any circumstances

## 6. Multi-Factor Authentication (MFA)

MFA is **required** for access to:
- Render hosting dashboard
- GitHub repository (admin and write access)
- Any `admin`-role BidBrief account (when MFA is implemented in-app — Phase 3)
- Log aggregation service
- Any production database console

MFA method: authenticator app (TOTP) preferred. SMS-based MFA accepted
as a fallback but not preferred.

## 7. Access Reviews

The Security Officer conducts a **quarterly access review**:

1. Pull the Access Grant Log (`docs/soc2/access_grant_log.md`)
2. For each active account, verify:
   - Person is still employed/engaged with Additional Intelligence LLC
   - Role assignment still matches current responsibilities
   - No excess permissions accumulated over time
3. Revoke or downgrade any access that fails verification
4. Document review completion in `docs/soc2/access_grant_log.md` with date

**Quarterly review months:** March, June, September, December

## 8. Access Grant Log

All access grants, changes, and revocations are recorded in:
`docs/soc2/access_grant_log.md`

Required fields for each entry:
- Date of action
- Username / account identifier
- System (BidBrief app / Render / GitHub / etc.)
- Role assigned or action taken (grant / modify / revoke)
- Approved by (Security Officer name)
- Business justification
- Expiry date (if temporary)

## 9. Offboarding / Access Revocation

Access revocation timelines:

| Trigger | Revocation Required By |
|---------|----------------------|
| Termination (voluntary or involuntary) | **Same day** — within hours of notification |
| Suspected credential compromise | **Immediately** — within 1 hour |
| Role change (reduced responsibilities) | Within 2 business days |
| Contractor engagement end | By last day of engagement |
| Temporary access expiry | Automatically on expiry date; verified within 1 business day |

**Offboarding checklist (complete for every departure):**

- [ ] BidBrief application account disabled or deleted
- [ ] Render dashboard access removed
- [ ] GitHub repository access removed
- [ ] OpenAI API key rotated if person had access
- [ ] Tavily API key rotated if person had access
- [ ] Any shared credentials the person knew rotated
- [ ] Active sessions invalidated (app restart if necessary for in-memory sessions)
- [ ] Completion logged in Access Grant Log with date and confirming person

## 10. Service Accounts and API Keys

Service accounts (deployment keys, CI/CD tokens, API keys) must:

- Be named to describe their purpose (never generic like `key1`)
- Never be used for human interactive login
- Be stored exclusively in environment variables or secrets managers — never in source code
- Be rotated annually at minimum, or immediately on any suspected exposure
- Be documented in the vendor inventory (`docs/soc2/vendor_inventory.md`)
- Be accessible only to the Security Officer unless a specific business need requires broader access

---

*Approved by: Stephen Bartlett, C.E.O., Security Officer*
*Approval date: 2026-03-03*
*Document location: `docs/policies/access_control_policy.md`*
