# Data Classification Policy

**Version:** 1.0
**Effective Date:** 2026-03-03
**Owner:** Stephen Bartlett, C.E.O., Security Officer
**Company:** Additional Intelligence LLC
**Review Cycle:** Annual
**Next Review:** 2027-03-03

---

## 1. Purpose

This policy defines how Additional Intelligence LLC classifies information
assets, specifies the handling requirements for each classification level,
and establishes data retention and disposal rules. Proper classification
ensures that confidential client data — particularly uploaded bid documents,
inspection reports, and analysis results — receives protection proportional
to its sensitivity.

## 2. Scope

This policy applies to all data created, received, processed, or stored
by BidBrief and any associated systems, regardless of format (digital,
printed, or verbal).

## 3. Classification Levels

### PUBLIC

Information explicitly intended for public distribution.

**Examples:**
- Marketing website content and product descriptions
- Published documentation and help articles
- Open-source code contributions
- Press releases

**Handling requirements:**
- No restrictions on access or distribution
- No special transmission or storage controls required

---

### INTERNAL

Information intended for internal business use. Not sensitive, but not
intended for public distribution.

**Examples:**
- Internal process documentation and runbooks
- Non-sensitive meeting notes and planning documents
- Development environment configuration (non-secret)
- Internal status updates and project plans

**Handling requirements:**
- Do not share externally without business justification
- Transmit over encrypted channels (HTTPS) when sending electronically
- No special storage encryption required, but avoid public storage locations

---

### CONFIDENTIAL

Sensitive information whose unauthorized disclosure could cause harm to
Additional Intelligence LLC, its clients, or third parties.

**Examples:**
- Client uploaded documents (bid specs, inspection reports, PACP data, project files)
- Analysis results generated from client documents
- User account information and session data
- Audit logs and access logs
- Source code and proprietary algorithms
- Contract terms and pricing information
- Internal financial information

**Handling requirements:**
- Encrypt in transit using TLS 1.2 or higher at all times
- Encrypt at rest when stored in any persistent system
- Access restricted to personnel with explicit business need
- All access logged with user identity, timestamp, and resource accessed
- Do not transmit to third-party services without a Data Processing Agreement (DPA)
  in place and client disclosure in Terms of Service
- Do not store beyond the defined retention period (see Section 5)
- Do not print or export to personal devices without Security Officer approval

---

### RESTRICTED

Highest sensitivity. Unauthorized disclosure could cause serious harm to the
business, clients, or individuals, including system compromise, financial loss,
or regulatory violation.

**Examples:**
- Production authentication secrets and session signing keys (`SECRET_KEY`)
- API keys for all third-party services (OpenAI, Tavily, Render deploy keys)
- Production database credentials
- Private encryption keys
- User password hashes

**Handling requirements:**
- All CONFIDENTIAL requirements apply
- Stored exclusively in environment variables or a secrets manager — **never** in source code, config files, or version control
- Access limited to Stephen Bartlett, C.E.O. unless a specific technical necessity requires delegation
- Rotated immediately upon any suspected compromise or personnel departure
- Rotated on a scheduled basis (annually minimum)
- Never logged, printed, or transmitted in cleartext under any circumstances
- Dual-person awareness recommended: a second person should know how to rotate/recover each key in an emergency

---

## 4. Data Inventory

The following table documents all known data types processed by BidBrief.
This inventory is reviewed and updated annually or when new data types are introduced.

| Data Type | Classification | Primary Location | Retention Period | Sent to Third Parties |
|-----------|---------------|-----------------|-----------------|----------------------|
| Client uploaded documents (PDF, DOCX, etc.) | CONFIDENTIAL | Encrypted temp storage (`/tmp`) | Session duration, max 24 hours | OpenAI API (document text only, for analysis) |
| Document text extracted for analysis | CONFIDENTIAL | In-memory only during processing | Session duration, cleared on expiry | OpenAI API |
| Analysis results (Q&A, fragments, footnotes) | CONFIDENTIAL | In-memory session storage | Session duration, max 24 hours | None |
| Excel export files | CONFIDENTIAL | `/exports/` directory | Until manually deleted or session cleanup | None |
| User credentials (email + password hash) | RESTRICTED | Environment variables | Until account deactivated | None |
| Session tokens | RESTRICTED | In-memory dict + client cookie | 24-hour TTL | None |
| OpenAI API key | RESTRICTED | Environment variable (`OPENAI_API_KEY`) | Until rotated | OpenAI (as auth header) |
| Tavily API key | RESTRICTED | Environment variable (`TAVILY_API_KEY`) | Until rotated | Tavily (as auth header) |
| Application logs | CONFIDENTIAL | Local log files / log drain service | 12 months | Log aggregation service (see vendor inventory) |
| Audit logs | CONFIDENTIAL | Application logs / Neon DB (Phase 3) | 12 months minimum | Log aggregation service |
| Municipal research data (CityScraper) | CONFIDENTIAL | In-memory session | Session duration | Tavily (search queries) |
| Source code | INTERNAL | GitHub repository | Indefinite (version controlled) | GitHub |
| Policy documents | INTERNAL | Git repository (`docs/policies/`) | Indefinite | None |

## 5. Data Retention Schedule

| Data Type | Retention Period | Disposal Trigger | Disposal Method |
|-----------|-----------------|-----------------|----------------|
| Uploaded documents | Session duration (max 24h) | Session expiry or manual cleanup | Encrypted temp file deletion |
| In-memory session data | Session duration (max 24h) | Session expiry (`cleanup_old_sessions`) | Python garbage collection + dict removal |
| Application logs | 12 months | Rolling expiry in log service | Log service auto-deletion |
| Audit logs | 12 months minimum | Rolling expiry | Log service / DB scheduled deletion |
| Export files | Until next session cleanup | Session expiry | File system deletion |
| Source code history | Indefinite | N/A — version history preserved | N/A |
| Policy documents | Indefinite (superseded versions archived) | New version published | Archive old version with date suffix |

## 6. Third-Party Data Sharing

Before sending CONFIDENTIAL or RESTRICTED data to any external service:

1. Verify a Data Processing Agreement (DPA) exists with the vendor and is current
2. Verify the vendor holds relevant security certifications (SOC 2, ISO 27001)
3. Ensure clients are notified of the data sharing in BidBrief Terms of Service
4. Document the sharing relationship in the vendor inventory (`docs/soc2/vendor_inventory.md`)

**Current approved third-party data flows:**

| Vendor | Data Sent | Classification | DPA Status | Client Disclosure |
|--------|-----------|----------------|-----------|------------------|
| OpenAI | Document text extracted from client uploads | CONFIDENTIAL | Via OpenAI API Terms — review date: 2026-03-03 | Required in ToS — see CC2.3 gap |
| Tavily | Web search query strings (municipal research) | INTERNAL | Via Tavily ToS | Not required (no client document content) |
| Log service (TBD) | Application and audit log entries | CONFIDENTIAL | Required before enabling log drain | Required in Privacy Policy |
| Render | All data in transit through hosting platform | CONFIDENTIAL | Via Render ToS — review date: 2026-03-03 | Required in Privacy Policy |

## 7. Data Disposal

All CONFIDENTIAL and RESTRICTED data must be disposed of securely when no
longer required per the retention schedule.

**Digital disposal methods by classification:**

| Classification | Acceptable Disposal Method |
|---------------|---------------------------|
| CONFIDENTIAL | Secure file deletion (overwrite); or cryptographic erasure (destroy encryption key) |
| RESTRICTED | Cryptographic erasure preferred; secure overwrite minimum; physical destruction for any hardware media |

**Disposal records:**
Every disposal event for CONFIDENTIAL or RESTRICTED data in persistent storage
must be logged with: data type, quantity/scope, date, disposal method, and the
name of the person or automated process that performed disposal.

**Customer data deletion requests:**
Clients may request deletion of their data by contacting stephen@additionalintel.com.
Requests must be fulfilled within 30 days and confirmed in writing to the requestor.
Given BidBrief's current ephemeral architecture, most client data is automatically
deleted within 24 hours; this fulfillment timeline covers any edge cases.

---

*Approved by: Stephen Bartlett, C.E.O., Security Officer*
*Approval date: 2026-03-03*
*Document location: `docs/policies/data_classification_policy.md`*
