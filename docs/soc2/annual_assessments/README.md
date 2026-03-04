# Annual Security Assessments

This directory stores results of annual vulnerability assessments and
penetration test reports.

## Schedule

| Year | Type | Scheduled | Completed | Report File |
|------|------|-----------|-----------|-------------|
| 2026 | Internal vulnerability assessment | Q4 2026 | — | — |
| 2027 | External penetration test (Type II prep) | Q1 2027 | — | — |

## Assessment Scope

Annual internal assessment covers:
1. Full dependency audit (`pip-audit -r requirements.txt`)
2. SAST scan (`bandit -r app.py services/ --severity-level low`)
3. Authentication and access control review
4. Review of all accepted risks in `vulnerability_exceptions.md`
5. Infrastructure configuration review (Render settings)
6. Review of security headers and API protections

Results documented as: `[YYYY]-annual-assessment.md`
