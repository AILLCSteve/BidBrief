# Vendor Certificates and DPA Reviews

This directory stores compliance documentation for BidBrief's critical vendors.

## Required Files (obtain before audit)

| File | Vendor | What to Download | Where to Get It |
|------|--------|-----------------|----------------|
| `render_soc2_[DATE].pdf` | Render | SOC 2 Type II report | render.com/security |
| `render_tos_reviewed_[DATE].md` | Render | DPA review notes | Review ToS at render.com/terms |
| `openai_soc2_[DATE].pdf` | OpenAI | SOC 2 Type II report | openai.com/security |
| `openai_dpa_reviewed_[DATE].md` | OpenAI | DPA review notes | Review at openai.com/policies/api-data-usage-policies |
| `github_soc2_[DATE].pdf` | GitHub | SOC 2 report | githubtrustcenter.com |
| `tavily_compliance_[DATE].md` | Tavily | Compliance assessment | tavily.com (check security/compliance page) |

## File Naming Convention

`[vendor]_[doc_type]_[YYYY-MM-DD].[ext]`

Examples:
- `openai_soc2_2026-03-15.pdf`
- `render_dpa_reviewed_2026-03-15.md`

## Important

Do NOT commit actual SOC 2 reports if they are marked confidential by the vendor.
Store them locally and reference them by filename in the vendor inventory.
The DPA review notes (`.md` files) summarizing the key terms ARE safe to commit.
