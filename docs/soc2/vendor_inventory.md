# Vendor Inventory

**Owner:** Stephen Bartlett, C.E.O.
**Company:** Additional Intelligence LLC
**Last Updated:** 2026-03-03
**Review Cycle:** Annual (each March); updated when vendors are added or removed

Vendor certs and DPA documents saved to: `docs/soc2/vendor_certs/`

---

## Criticality Definitions

| Level | Definition |
|-------|-----------|
| **Critical** | Processes or stores CONFIDENTIAL/RESTRICTED client data; outage directly impacts service |
| **High** | Integral to service delivery; security breach could indirectly expose client data |
| **Standard** | Supporting role; breach would not directly expose client data |

---

## Active Vendors

### Render (render.com)

| Field | Details |
|-------|---------|
| **Service** | Application hosting, TLS termination, deployment infrastructure |
| **Criticality** | Critical |
| **Data Transmitted** | All BidBrief data in transit; environment variables (secrets) stored on platform |
| **Data Classification** | CONFIDENTIAL / RESTRICTED |
| **SOC 2 Report** | SOC 2 Type II — download from render.com/security |
| **Cert Location** | `docs/soc2/vendor_certs/render_soc2_[DATE].pdf` |
| **DPA Status** | Via Render Terms of Service (DPA embedded in ToS §[X]) |
| **DPA Review Date** | 2026-03-03 (initial review) |
| **DPA Location** | `docs/soc2/vendor_certs/render_tos_reviewed_2026-03-03.md` |
| **Key Security Terms** | Shared responsibility model: Render owns physical/infrastructure; Additional Intelligence owns application security |
| **MFA Configured** | ☐ TODO — enable MFA on Render dashboard before audit |
| **Annual Review Due** | 2027-03-03 |

**Action required:**
- [ ] Download Render SOC 2 report → save to `vendor_certs/render_soc2_[date].pdf`
- [ ] Review Render ToS/DPA and document relevant security terms
- [ ] Enable MFA on Render account

---

### OpenAI (openai.com / platform.openai.com)

| Field | Details |
|-------|---------|
| **Service** | GPT-4o AI model inference for document analysis |
| **Criticality** | Critical |
| **Data Transmitted** | Document text extracted from client uploads (CONFIDENTIAL) |
| **Data Classification** | CONFIDENTIAL |
| **SOC 2 Report** | SOC 2 Type II — available from openai.com/security |
| **Cert Location** | `docs/soc2/vendor_certs/openai_soc2_[DATE].pdf` |
| **DPA Status** | Via OpenAI API Terms of Service / Data Processing Addendum |
| **DPA Review Date** | 2026-03-03 (initial review) |
| **DPA Location** | `docs/soc2/vendor_certs/openai_dpa_reviewed_2026-03-03.md` |
| **Key DPA Terms to Verify** | (1) Data not used to train models for API customers; (2) Data retention period; (3) Data deletion on request; (4) Breach notification commitment |
| **Client Disclosure** | ☐ TODO — must disclose in BidBrief Terms of Service that documents are processed by OpenAI |
| **Annual Review Due** | 2027-03-03 |

**Action required:**
- [ ] Download OpenAI SOC 2 report → save to `vendor_certs/openai_soc2_[date].pdf`
- [ ] Review OpenAI API ToS / DPA and document key terms in `vendor_certs/openai_dpa_reviewed_2026-03-03.md`
- [ ] Confirm: does OpenAI use API input to train models? (Current answer: No, for API customers with Zero Data Retention option)
- [ ] Add disclosure to Terms of Service: "Document analysis is powered by OpenAI's API. Uploaded document content is transmitted to OpenAI for processing per OpenAI's API Data Usage Policy."

---

### GitHub (github.com)

| Field | Details |
|-------|---------|
| **Service** | Source code version control, CI/CD pipeline, Dependabot |
| **Criticality** | High |
| **Data Transmitted** | Source code (no client data) |
| **Data Classification** | INTERNAL |
| **SOC 2 Report** | SOC 2 Type II — via GitHub's Trust Center |
| **Cert Location** | `docs/soc2/vendor_certs/github_soc2_[DATE].pdf` |
| **DPA Status** | Via GitHub Terms of Service |
| **DPA Review Date** | 2026-03-03 |
| **MFA Configured** | ☐ TODO — enable MFA on GitHub account if not already active |
| **Branch Protection** | ☐ TODO — enable on `master` (Task 1.10) |
| **Annual Review Due** | 2027-03-03 |

**Action required:**
- [ ] Confirm MFA is active on GitHub account
- [ ] Enable branch protection on `master` (see Task 1.10)
- [ ] Download GitHub SOC 2 / compliance docs

---

### Tavily (tavily.com)

| Field | Details |
|-------|---------|
| **Service** | AI-powered web search for CityScraper municipal research |
| **Criticality** | Standard |
| **Data Transmitted** | Search query strings only (no client document content) |
| **Data Classification** | INTERNAL |
| **SOC 2 Report** | Unknown — review current compliance status at tavily.com |
| **DPA Status** | Via Tavily Terms of Service |
| **DPA Review Date** | 2026-03-03 |
| **Key Risk** | Query strings may contain project names, municipality names — assess sensitivity |
| **Annual Review Due** | 2027-03-03 |

**Action required:**
- [ ] Check Tavily's compliance page for SOC 2 or equivalent certification
- [ ] Review what data Tavily retains from search queries
- [ ] If search queries contain client-identifiable information, classify as CONFIDENTIAL and require DPA

---

## DPA Review Template

When reviewing a vendor DPA, document the following in `vendor_certs/[vendor]_dpa_reviewed_[date].md`:

```markdown
# [Vendor Name] DPA Review

**Review Date:** [DATE]
**Reviewed By:** Stephen Bartlett, C.E.O.
**Document Reviewed:** [URL or document title + version]

## Key Terms

| Requirement | Status | Notes |
|-------------|--------|-------|
| Data not used for training/improvement | ☑/☐ | |
| Data retention period defined | ☑/☐ | Retention: [X days/months] |
| Data deletion process available | ☑/☐ | Process: [description] |
| Breach notification commitment | ☑/☐ | Timeline: [X hours/days] |
| Subprocessors disclosed | ☑/☐ | |
| Data residency/geography | ☑/☐ | Location: [region] |
| Security measures described | ☑/☐ | |

## Assessment

[Overall assessment: does this DPA adequately protect BidBrief clients? Any gaps?]

## Follow-Up Required

- [ ] [Any action items from this review]
```

---

## Removed Vendors

| Vendor | Service | Removed Date | Reason | Data Deletion Confirmed |
|--------|---------|-------------|--------|------------------------|
| — | No removed vendors | — | — | — |

---

_Last updated: 2026-03-03_
_Next annual review: 2027-03-03_
