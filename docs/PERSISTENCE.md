# Durable Session Storage (Neon / Postgres)

Backend/admin concern only — nothing about this appears in the user-facing UI.

Before this, every dict lived in one gunicorn worker's memory: a Render deploy or
restart wiped logins, entitlements and every completed analysis. Now memory stays
the hot path and Postgres is the durable mirror.

## Setup (three steps)

**1. Get the Neon connection string.** Neon Console → your project → *Connection
Details* → copy the **pooled** connection string (the host contains `-pooler`).
It looks like:

```
postgresql://USER:PASSWORD@ep-xxxx-pooler.REGION.aws.neon.tech/DBNAME?sslmode=require
```

Use the pooled one — a web app opens and closes connections constantly, and the
direct endpoint will exhaust its connection limit.

**2. Set it on Render.** Dashboard → your service → *Environment* → add:

| Variable | Value | Required |
|---|---|---|
| `DATABASE_URL` | the pooled Neon string above | **yes** — this is the on/off switch |
| `BIDBRIEF_DB_RETENTION_DAYS` | how long analyses are kept (default `90`) | no |
| `BIDBRIEF_DB_POOL_MAX` | max pooled connections (default `4`) | no |

Nothing else changes. The tables are created automatically on first boot.

**3. Verify.** Locally, with the same string:

```bash
DATABASE_URL='postgresql://...' python -m services.persistence
```

That creates the schema, writes a row, reads it back, exercises the settings
table and cleans up after itself. Every line should print `OK`.

After deploying, confirm from the admin session dashboard: `/api/admin/sessions`
now returns `diagnostics.persistence` → `{"enabled": true, "reachable": true}`.
It is deliberately **not** on the public `/health` — that would leak
infrastructure detail to anonymous callers.

## What survives a restart

| State | Survives | Notes |
|---|---|---|
| Completed analyses | ✅ | Served from a stored snapshot |
| Stopped / failed analyses | ✅ | Whatever they accumulated |
| Excel / CSV / HTML exports | ✅ | Regenerated from the snapshot |
| Smart Analysis results | ✅ | Cached — never re-billed after a restart |
| Signed-in sessions | ✅ | Users stay logged in across a deploy |
| Bonus Features grants | ✅ | |
| Beta testers + their quota | ✅ | Spent documents can't be reset by a restart |
| Free-beta on/off switch | ✅ | No longer reverts to `BETA_LOGIN_ENABLED` |
| **In-flight analyses** | ❌ | Marked `interrupted` — their thread died with the process |
| **Second pass / Deep RAG** | ❌ | Needs the live in-memory analysis state; returns a clear 409 |

## Why analyses are stored as a snapshot

A completed analysis holds a live `HotdogOrchestrator` — an OpenAI client, cached
windows, accumulators. That cannot be serialized. So rather than trying, we store
the **snapshot the API already derives from it**: the legacy result payload,
statistics, key details, document type and BestPrep data, all plain JSON in one
`JSONB` column.

That is enough for everything a user reads after the fact, because those paths
consume the dict, not the orchestrator — `ExcelDashboardGenerator` takes the
legacy result, and `_build_smart_analysis_data` needs only the fields above.
Second pass and Deep RAG are the exceptions: they need cached windows and
experts, so a restored session refuses them with an explanation.

One `JSONB` blob rather than a wide table is deliberate — payload shapes change
most releases, and a blob means new fields need no migration.

## Design rules (do not break)

1. **No `DATABASE_URL` → every store call is a no-op** and the app behaves
   exactly as it did before. This module may never be load-bearing.
2. **Every operation is failure-safe.** A Neon outage logs and returns a default.
   It must never fail a 15-minute analysis or a login.
3. **Recovered rows fold into the existing admin buckets** (`active` /
   `completed` / `partial` / `legacy`) with `restored: true` on the row. Those
   four names are a client contract the iOS dashboard decodes — do not add a
   fifth bucket.
4. **A live session always wins** over a recovered copy of the same id.
5. **Revocation must outlive the process.** Logout and tester deletion delete
   the stored token too, or a restart would resurrect it.

## Cost

Analyses are the only large rows (a full Q&A payload, typically tens to a few
hundred KB). At the default 90-day retention this sits comfortably inside Neon's
free tier for normal usage. Lower `BIDBRIEF_DB_RETENTION_DAYS` if storage grows.

## Rollback

Remove `DATABASE_URL` and restart. The app returns to in-memory behaviour
immediately; the stored data is left untouched and comes back if you set the
variable again.
