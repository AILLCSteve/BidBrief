# SOC 2 Setup Checklist — Manual Actions Required

These items require manual configuration in external dashboards and cannot
be automated via code commits. Complete each before the Phase 1 audit pass.

**Owner:** Stephen Bartlett, C.E.O.
**Target completion:** Before Phase 2 begins

---

## GitHub — Branch Protection on `master`

**Why:** SOC 2 CC8.1 — change management requires no direct pushes to production branch.

**Steps:**
1. Go to: `github.com/[your-repo] → Settings → Branches`
2. Click **Add branch protection rule**
3. Branch name pattern: `master`
4. Enable:
   - [x] **Require a pull request before merging**
     - [x] Require approvals: `1`
     - [x] Dismiss stale pull request approvals when new commits are pushed
   - [x] **Do not allow bypassing the above settings**
5. Click **Save changes**

**Verify:** Try `git push origin master` directly (should be rejected with "protected branch" error)

- [ ] **DONE** — Date completed: ___________

---

## GitHub — Enable MFA on Account

**Why:** SOC 2 CC6.6 — MFA required on all admin infrastructure access.

**Steps:**
1. GitHub → Settings → Password and authentication
2. Enable two-factor authentication
3. Use authenticator app (not SMS)
4. Save recovery codes in a secure location (password manager)

- [ ] **DONE** — Date completed: ___________

---

## Render — Enable MFA on Account

**Why:** SOC 2 CC6.6 — MFA required on production hosting dashboard.

**Steps:**
1. Render Dashboard → Account Settings → Security
2. Enable Two-Factor Authentication
3. Use authenticator app
4. Save recovery codes

- [ ] **DONE** — Date completed: ___________

---

## Render — Configure Log Drain

**Why:** SOC 2 CC2.1, CC7.2 — logs must be persisted to a tamper-resistant external service with 90-day retention.

**Recommended services (free tiers available):**
- Better Stack Logtail: logs.betterstack.com (free: 1GB/month, 3-day retention; upgrade for 90 days)
- Papertrail: papertrail.com (free: 50MB/day, 7-day retention; upgrade for 90 days)
- Datadog: datadoghq.com (free tier available)

**Steps:**
1. Sign up for chosen log service
2. Get the syslog/drain endpoint URL from the service
3. Render Dashboard → [BidBrief Service] → Logs → Log Streams → Add Log Stream
4. Enter the drain endpoint URL → Save
5. Generate some app activity and verify logs appear in the external service
6. Configure retention to 90 days minimum (may require paid tier)

- [ ] **DONE** — Service chosen: ___________ Date completed: ___________
- [ ] **RETENTION CONFIGURED** — Retention period: ___________ days

---

## UptimeRobot — Configure Uptime Monitoring

**Why:** SOC 2 CC4.1, CC7.2 — system availability must be monitored with alerting.

**Steps:**
1. Create free account at: uptimerobot.com
2. Add Monitor:
   - Monitor Type: HTTP(s)
   - Friendly Name: `BidBrief Production`
   - URL: `https://[your-render-domain]/health`
   - Monitoring Interval: 5 minutes
3. Add Alert Contact: stephen@additionalintel.com
4. Verify monitor shows as "Up"

- [ ] **DONE** — Date completed: ___________ Monitor URL: ___________

---

## OpenAI — Review and Document DPA

**Why:** SOC 2 CC9.2, C1.1 — vendor DPA must be reviewed for client data protection.

**Steps:**
1. Review OpenAI API Data Usage Policies: platform.openai.com/docs/models/how-we-use-your-data
2. Confirm: API inputs are NOT used to train models (Zero Data Retention for API customers)
3. Note data retention period (currently: 30 days by default; 0 days with ZDR option)
4. Consider enabling Zero Data Retention if available for your plan
5. Document findings in: `docs/soc2/vendor_certs/openai_dpa_reviewed_2026-03-03.md`
6. Download OpenAI SOC 2 report from: openai.com/security → save to `vendor_certs/`

- [ ] **DPA REVIEWED** — Date: ___________ ZDR enabled: ☐ Yes ☐ No
- [ ] **SOC 2 REPORT DOWNLOADED** — Date: ___________

---

## Render — Download SOC 2 Report

**Why:** SOC 2 CC6.4 — must evidence subservice organization physical security controls.

**Steps:**
1. Go to: render.com/security (or render.com/trust)
2. Download their SOC 2 Type II report
3. Save to: `docs/soc2/vendor_certs/render_soc2_[DATE].pdf`
4. Note the report period covered and any exceptions

- [ ] **DONE** — Date downloaded: ___________ Report period: ___________

---

## Terms of Service / Privacy Policy — Publish

**Why:** SOC 2 CC2.3, C1.1 — clients must be informed of data handling including OpenAI processing.

**Required disclosures:**
- What data BidBrief collects and processes
- That uploaded documents are processed by OpenAI's API
- Data retention period (session duration, max 24 hours)
- How to request data deletion (email stephen@additionalintel.com)
- Contact for security questions

**Steps:**
1. Draft Privacy Policy (use `docs/policies/` content as source material)
2. Publish at a public URL (e.g., your domain/privacy or a simple page)
3. Link from BidBrief login page and footer
4. Draft Terms of Service with data handling disclosures
5. Record URL in `docs/soc2/system_description.md`

- [ ] **PRIVACY POLICY PUBLISHED** — URL: ___________ Date: ___________
- [ ] **TERMS OF SERVICE PUBLISHED** — URL: ___________ Date: ___________

---

## Summary Status

| Item | Status | Date |
|------|--------|------|
| GitHub branch protection on master | ☐ | |
| GitHub MFA | ☐ | |
| Render MFA | ☐ | |
| Render log drain | ☐ | |
| UptimeRobot monitoring | ☐ | |
| OpenAI DPA reviewed | ☐ | |
| Render SOC 2 report downloaded | ☐ | |
| Privacy Policy published | ☐ | |
| Terms of Service published | ☐ | |

_All items must be checked before Phase 1 audit pass (Task 1.13)._
