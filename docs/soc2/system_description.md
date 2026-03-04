# BidBrief System Description

> This document becomes Section III of the SOC 2 Type I audit report.
> It must be accurate, complete, and reviewed by the auditor before the audit begins.

**Company:** Additional Intelligence LLC
**Product:** BidBrief
**Version:** Current (see git log for latest commit)
**Prepared by:** Stephen Bartlett, C.E.O.
**Date:** 2026-03-03
**SOC 2 Scope:** Security (CC1–CC9) + Confidentiality (C1)

---

## 1. Nature of Services

BidBrief is a web-based AI document analysis platform that enables contractors,
engineers, and project managers to extract structured information from complex
project documents including bid specifications, CIPP (Cured-In-Place Pipe) project
files, NASSCO PACP inspection reports, and municipal infrastructure documents.

The platform processes uploaded documents through a multi-pass AI analysis pipeline
(HOTDOG — Hierarchical Orchestrated Thorough Document Oversight & Guidance) powered
by OpenAI's GPT-4o model. Analysis results are returned to authenticated users via
the web interface and can be exported as professional Excel reports.

BidBrief also includes CityScraper, a municipal data research tool that searches
public sources for infrastructure project data and bid information.

**Primary users:**
- CIPP and sewer infrastructure contractors
- Municipal engineers and project managers
- Infrastructure project consultants

**Data processed:**
- Bid specification documents (PDF, DOCX)
- Inspection reports (PDF, XML — NASSCO PACP format)
- Municipal infrastructure project files
- Publicly available municipal bid and project data

---

## 2. Infrastructure Components

### 2.1 Hosting Platform

| Component | Provider | Description |
|-----------|---------|-------------|
| Application hosting | Render (render.com) | Flask application deployed as a web service |
| TLS termination | Render | HTTPS enforced; TLS 1.2+ for all client connections |
| Process model | Gunicorn (sync worker) | Single worker, 10 threads; `worker_class = sync` |
| Deployment | Render auto-deploy from GitHub `master` branch | CI/CD triggered on merge to master |

**Render service configuration:**
- Region: [Render region — e.g., Oregon (US West)]
- Instance type: [Render plan tier]
- Environment: Production
- Health check endpoint: `/health`

### 2.2 Application Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.x |
| Web framework | Flask | 2.2.x |
| WSGI server | Gunicorn | 22.x |
| PDF extraction | PyMuPDF (fitz) | Primary |
| PDF extraction fallback | pdfplumber, PyPDF2 | Fallback chain |
| AI inference | OpenAI GPT-4o | Via OpenAI Python SDK |
| Web search | Tavily AI | CityScraper only |
| Export | openpyxl, xlsxwriter | Excel report generation |
| Frontend | Vanilla JavaScript, HTML5, CSS3 | No frontend framework |

### 2.3 Data Storage

BidBrief currently uses a **stateless, ephemeral storage model**:

| Data Type | Storage Location | Persistence | Encryption |
|-----------|----------------|-------------|-----------|
| Uploaded documents | OS temp directory (`/tmp`) with encryption | Session duration (max 24h) | Yes — `cryptography` library AES |
| Analysis sessions | In-memory Python dictionaries | Process lifetime | N/A (in-memory) |
| Analysis results | In-memory session storage | Session duration | N/A (in-memory) |
| Excel exports | `/exports/` directory on Render filesystem | Until session cleanup | No (filesystem only) |
| Application logs | Render log stream | Configurable via log drain | No |

> **Phase 3 note:** Neon DB (PostgreSQL) will be added for persistent audit logs,
> user management, and session storage. This section will be updated at that time.

### 2.4 External Service Integrations

| Service | Purpose | Data Transmitted | Auth Method |
|---------|---------|-----------------|------------|
| OpenAI API (GPT-4o) | Document analysis AI inference | Document text (extracted from uploads) | API key in HTTP Authorization header |
| Tavily API | Web search for CityScraper | Search query strings | API key in HTTP header |
| Render | Application hosting and deployment | Full application and environment | Deploy key / Render dashboard auth |
| GitHub | Source code repository | Source code (no client data) | GitHub authentication |

---

## 3. Personnel

| Name | Role | System Access | Responsibilities |
|------|------|--------------|----------------|
| Stephen Bartlett | C.E.O., Security Officer | Full admin (all systems) | System development, security oversight, client relationships, incident response |

> Additional personnel will be added to this table as team grows. Each addition
> requires Access Control Policy provisioning process.

---

## 4. Data Flows

### 4.1 Document Analysis Flow

```
User Browser (HTTPS)
        │
        │  POST /api/upload (multipart/form-data)
        ▼
Render Platform — Flask Application
        │
        │  PyMuPDF/pdfplumber extract text from PDF
        │  File encrypted and stored in /tmp (AES)
        ▼
HOTDOG Orchestrator (in-memory processing)
        │
        │  Document text (NOT raw file) sent via HTTPS
        ▼
OpenAI API (GPT-4o)
        │
        │  Analysis results returned via HTTPS
        ▼
HOTDOG Orchestrator — accumulates answers in memory
        │
        │  Results stored in active_analyses dict (session-scoped)
        ▼
User Browser — retrieves results via polling GET /api/results/<session_id>
        │
        │  Optional: POST /api/export/excel-dashboard/<session_id>
        ▼
Excel Report — generated and served as file download
        │
        │  /exports/ directory cleaned up on session expiry
        ▼
Session Expiry (24h TTL, 5-min cleanup thread)
        │
        ▼
All session data and encrypted temp files deleted
```

### 4.2 CityScraper Research Flow

```
User Browser (HTTPS)
        │
        │  POST /api/scraper/research
        ▼
Flask Application — CityScraper Orchestrator
        │
        │  Search queries (no client document content) sent via HTTPS
        ▼
Tavily API — web search
        │
        │  Public web results returned
        ▼
CityScraper Analysis Agents — GPT-4o processes public data
        │
        ▼
Results stored in-memory; exported to Excel on request
```

### 4.3 Authentication Flow

```
User → POST /auth/login (email + password)
     → Flask validates against hashed credentials in environment variables
     → On success: session token created (secrets.token_urlsafe(32))
     → Token stored in active_sessions dict (24h TTL)
     → Token set as HttpOnly cookie (bidbrief_auth)
     → All subsequent requests: cookie validated via check_auth_cookie()
```

---

## 5. Network Architecture

```
Internet
    │
    │  HTTPS (TLS 1.2+) — all client connections
    ▼
Render Edge Network (DDoS mitigation, TLS termination)
    │
    ▼
Render Web Service — BidBrief Flask Application
    │
    ├──► OpenAI API (HTTPS outbound — document text only)
    ├──► Tavily API (HTTPS outbound — search queries only)
    └──► [Phase 3] Neon DB (PostgreSQL over TLS — audit logs, users)
```

**No direct database access from the internet.** All data access is mediated
through the authenticated Flask application.

---

## 6. Logical Access Architecture

| Access Layer | Method | Controls |
|-------------|--------|---------|
| Web application | Cookie-based session auth | `@require_auth` decorator on all protected routes |
| Admin functions | Role-based (admin/user) | `@require_admin` decorator; returns 403 to non-admin |
| Production infrastructure (Render) | Render dashboard + MFA | Limited to Security Officer |
| Source code (GitHub) | GitHub auth + branch protection | Security Officer admin; PRs required for master |
| OpenAI API | API key in env var | Security Officer access only |

---

## 7. Change Management

All production changes follow the Change Management Policy
(`docs/policies/change_management_policy.md`):

- Feature branches for all changes
- Pull requests required to merge to `master`
- CI/CD pipeline runs tests and security scans on each PR
- Render auto-deploys from `master` after successful merge
- Rollback available via Render's previous deploy feature

---

## 8. Monitoring and Incident Response

| Monitoring Type | Tool | Coverage |
|----------------|------|---------|
| Uptime monitoring | UptimeRobot (to be configured — see `docs/soc2/setup_checklist.md`) | `/health` endpoint, 5-min intervals, alerts to stephen@additionalintel.com |
| Log aggregation | Render log drain (to be configured — see `docs/soc2/setup_checklist.md`) | All application logs, 90-day retention minimum |
| Dependency scanning | GitHub Dependabot (`.github/dependabot.yml`) | Weekly automated scans, labels: security/dependencies |
| SAST scanning | Bandit (annual assessment) | Python source — see `docs/soc2/annual_assessments/` |
| Incident response | Incident Response Plan | `docs/policies/incident_response_plan.md` |

---

## 9. Subservice Organizations

BidBrief relies on the following subservice organizations whose controls
are relevant to the SOC 2 audit scope:

| Subservice Organization | Service Provided | Relevant Controls | Attestation |
|------------------------|-----------------|------------------|------------|
| Render (render.com) | Cloud hosting, TLS, physical security | Physical access (CC6.4), network security, availability | SOC 2 Type II — obtain from render.com/security |
| OpenAI (openai.com) | AI model inference | Data processing, data retention, model security | SOC 2 Type II — obtain from openai.com/security |
| GitHub (github.com) | Source code repository, CI/CD | Change management, code security | SOC 2 Type II — obtain from github.com/security |
| Tavily (tavily.com) | Web search API | Data processing | Review current compliance status |

Additional Intelligence LLC relies on these organizations using the
**Carve-Out Method**: subservice organization controls are excluded from
the scope of this audit. Evidence of their SOC 2 reports is retained in
`docs/soc2/vendor_certs/`.

---

## 10. Trust Service Criteria in Scope

| Criteria | In Scope | Rationale |
|----------|---------|-----------|
| Security (CC1–CC9) | Yes | Required for all SOC 2 reports |
| Confidentiality (C1) | Yes | BidBrief processes confidential client documents |
| Availability (A) | No | Not included in this audit cycle |
| Processing Integrity (PI) | No | Not included in this audit cycle |
| Privacy (P) | No | Not included in this audit cycle |

---

_Document prepared by: Stephen Bartlett, C.E.O., Security Officer_
_Date: 2026-03-03_
_Next review: Prior to audit engagement / annually_
