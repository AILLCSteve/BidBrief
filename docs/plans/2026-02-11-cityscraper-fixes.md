# CityScraper Reliability & Live Display Table Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three critical CityScraper bugs (Tavily rate limiting, PF-3 validation strictness, failed-as-completed status bug) and add a live-updating data table that shows preflight info and extracted data points in real time.

**Architecture:** The fixes target four layers: (1) HTTP client rate limiting in `base.py`, (2) validation relaxation in `source_discovery.py`, (3) status propagation fix in `app.py`, (4) frontend error handling + new live table in `index.html`. The live table follows the existing BidBrief unitary table pattern — initialize skeleton rows, update incrementally via polling events.

**Tech Stack:** Python/Flask backend, vanilla JS frontend, httpx async HTTP client, Tavily API, OpenAI API

---

## Root Cause Analysis

### Bug 1: Tavily 432 Rate Limit → 15+ Rapid-Fire Calls
- **File:** `services/scraper/agents/base.py:248-334`
- **Problem:** `search_tavily()` has ZERO rate limit handling. On 432, it logs the error and returns `[]`. No backoff, no delay, no circuit breaker. When an agent fires 16 queries (PF-3 does this), they all hit Tavily near-simultaneously, triggering rate limits. Each failed query returns empty, so the agent retries the whole stage (up to 3x via preflight orchestrator), amplifying 16 calls to 48+.
- **Config has `requests_per_minute: 30` but it's never enforced.**

### Bug 2: PF-3 Validation Too Strict
- **File:** `services/scraper/agents/preflight/source_discovery.py:395-452`
- **Problem:** Line 414: `if official is not None and not official.get('url')` — if the AI returns `official_website: {}` (present but empty), validation fails with "official_website present but missing 'url' field". This causes the entire PF-3 stage to fail validation, triggering retries, which fire MORE Tavily queries, which hit MORE rate limits.

### Bug 3: Research "Completes" With Error → Frontend Resets
- **File:** `app.py:3067-3070`
- **Problem:** The background thread sets `status = 'completed'` after `orchestrator.run()` returns, regardless of `result['success']`. The orchestrator catches its own exceptions and returns `{'success': False, ...}` — it doesn't raise. So the thread never hits the `except` block. Frontend sees `status: 'completed'`, calls `loadCityScraperResults()`, which checks `data.success` — it's False, so it logs "No result in response" and the UI appears to reset to initial state.

### "Double Calls" Explained
- Not duplicate orchestrator runs. It's the **retry amplification**: PF-3 fires 16 Tavily queries → rate limited → returns empty → validation fails → preflight retries → 16 MORE queries → rate limited again → retries again → 16 MORE. That's 48 Tavily calls for one stage, most returning 432 errors in rapid succession.

---

## Task 1: Add Tavily Rate Limiter & Backoff to BaseAgent

**Files:**
- Modify: `services/scraper/agents/base.py:248-334`
- Modify: `services/scraper/config.py` (add backoff config)

**Step 1: Add rate limiter config to TavilyConfig**

In `services/scraper/config.py`, add fields to `TavilyConfig`:

```python
@dataclass
class TavilyConfig:
    """Tavily API configuration."""
    api_key: str
    search_depth: str = "advanced"
    max_results_per_query: int = 20
    include_raw_content: bool = True
    include_answer: bool = True
    timeout_seconds: int = 60
    preferred_domains: List[str] = field(default_factory=lambda: [".gov", ".us", ".org"])
    requests_per_minute: int = 30
    # NEW: Backoff settings
    max_retries_per_query: int = 3
    initial_backoff_seconds: float = 2.0
    max_backoff_seconds: float = 30.0
    circuit_breaker_threshold: int = 5  # consecutive failures before circuit opens
    circuit_breaker_cooldown: float = 60.0  # seconds before retrying after circuit opens
```

**Step 2: Add rate limiter and circuit breaker to BaseAgent**

In `services/scraper/agents/base.py`, add class-level rate limiter state and modify `search_tavily()`:

```python
import asyncio
import time

class BaseAgent:
    # Class-level shared state for rate limiting across all agents
    _tavily_last_call_time: float = 0.0
    _tavily_min_interval: float = 2.0  # seconds between calls (30/min)
    _tavily_consecutive_failures: int = 0
    _tavily_circuit_open_until: float = 0.0

    async def search_tavily(
        self,
        query: str,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        max_results: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        if not self.config.tavily:
            logger.warning(f"Agent {self.AGENT_ID} attempted search without Tavily config")
            return []

        # --- CIRCUIT BREAKER CHECK ---
        now = time.monotonic()
        if now < BaseAgent._tavily_circuit_open_until:
            wait = BaseAgent._tavily_circuit_open_until - now
            logger.warning(f"Agent {self.AGENT_ID} Tavily circuit breaker open, waiting {wait:.1f}s")
            await asyncio.sleep(wait)

        # --- RATE LIMITER (token bucket: 1 call per min_interval) ---
        elapsed = now - BaseAgent._tavily_last_call_time
        if elapsed < BaseAgent._tavily_min_interval:
            delay = BaseAgent._tavily_min_interval - elapsed
            logger.debug(f"Agent {self.AGENT_ID} rate limiting: waiting {delay:.1f}s")
            await asyncio.sleep(delay)
        BaseAgent._tavily_last_call_time = time.monotonic()

        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.config.tavily.timeout_seconds)

        if include_domains is None:
            include_domains = self.config.tavily.preferred_domains

        request_data = {
            "api_key": self.config.tavily.api_key,
            "query": query,
            "search_depth": self.config.tavily.search_depth,
            "max_results": max_results or self.config.tavily.max_results_per_query,
            "include_answer": self.config.tavily.include_answer,
            "include_raw_content": self.config.tavily.include_raw_content
        }
        if include_domains:
            request_data["include_domains"] = include_domains
        if exclude_domains:
            request_data["exclude_domains"] = exclude_domains

        # --- RETRY WITH EXPONENTIAL BACKOFF ---
        max_retries = self.config.tavily.max_retries_per_query
        backoff = self.config.tavily.initial_backoff_seconds

        for attempt in range(max_retries + 1):
            try:
                self.emit_event("searching", f"Searching: {query[:50]}...")
                logger.debug(f"Agent {self.AGENT_ID} searching (attempt {attempt+1}): {query}")

                response = await self._http_client.post(
                    "https://api.tavily.com/search",
                    json=request_data
                )

                if response.status_code == 200:
                    # Success — reset circuit breaker
                    BaseAgent._tavily_consecutive_failures = 0
                    data = response.json()
                    results = []
                    for item in data.get('results', []):
                        results.append({
                            'title': item.get('title', ''),
                            'url': item.get('url', ''),
                            'content': item.get('content', ''),
                            'raw_content': item.get('raw_content', ''),
                            'score': item.get('score', 0),
                            'query': query
                        })
                    if data.get('answer'):
                        results.append({
                            'title': 'Tavily AI Summary',
                            'url': 'tavily:ai-summary',
                            'content': data['answer'],
                            'score': 1.0,
                            'query': query,
                            'is_ai_summary': True
                        })
                    logger.debug(f"Agent {self.AGENT_ID} found {len(results)} results")
                    return results

                elif response.status_code == 429 or response.status_code == 432:
                    # Rate limited — backoff and retry
                    BaseAgent._tavily_consecutive_failures += 1
                    logger.warning(
                        f"Agent {self.AGENT_ID} Tavily rate limited ({response.status_code}), "
                        f"attempt {attempt+1}/{max_retries+1}, backing off {backoff:.1f}s"
                    )

                    # Open circuit breaker if too many consecutive failures
                    if BaseAgent._tavily_consecutive_failures >= self.config.tavily.circuit_breaker_threshold:
                        BaseAgent._tavily_circuit_open_until = time.monotonic() + self.config.tavily.circuit_breaker_cooldown
                        logger.error(
                            f"Agent {self.AGENT_ID} Tavily circuit breaker OPEN — "
                            f"{BaseAgent._tavily_consecutive_failures} consecutive failures, "
                            f"cooling down {self.config.tavily.circuit_breaker_cooldown}s"
                        )
                        return []

                    if attempt < max_retries:
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, self.config.tavily.max_backoff_seconds)
                        continue
                    else:
                        logger.error(f"Agent {self.AGENT_ID} Tavily exhausted retries after rate limiting")
                        return []

                else:
                    # Other HTTP error — don't retry
                    logger.error(f"Tavily API error: {response.status_code} - {response.text}")
                    return []

            except Exception as e:
                logger.error(f"Agent {self.AGENT_ID} Tavily search failed: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, self.config.tavily.max_backoff_seconds)
                    continue
                return []

        return []
```

**Step 3: Run tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All existing tests pass (Tavily changes are additive, no test breakage)

**Step 4: Commit**

```bash
git add services/scraper/agents/base.py services/scraper/config.py
git commit -m "fix: Add Tavily rate limiter, exponential backoff, and circuit breaker"
```

---

## Task 2: Relax PF-3 Source Discovery Validation

**Files:**
- Modify: `services/scraper/agents/preflight/source_discovery.py:412-415`

**Step 1: Fix validation to gracefully handle missing url field**

Change line 412-415 from:

```python
# Validate official_website has URL if not null
official = source_map.get('official_website')
if official is not None and not official.get('url'):
    errors.append("official_website present but missing 'url' field")
```

To:

```python
# Validate official_website - warn but don't fail if URL is missing
official = source_map.get('official_website')
if official is not None and not official.get('url'):
    # Downgrade to warning — AI may return the category without a URL
    # This shouldn't block the entire research pipeline
    logger.warning("PF-3: official_website present but missing 'url' field — continuing with degraded data")
    # Set to None so downstream code doesn't try to use a URL-less entry
    source_map['official_website'] = None
```

Also relax `sewer_utility_page` the same way (line 419):

```python
sewer = source_map.get('sewer_utility_page')
if sewer is not None and not isinstance(sewer, dict):
    logger.warning("PF-3: sewer_utility_page is not a dict — setting to None")
    source_map['sewer_utility_page'] = None
```

**Step 2: Commit**

```bash
git add services/scraper/agents/preflight/source_discovery.py
git commit -m "fix: Relax PF-3 validation - degrade gracefully on missing source URLs"
```

---

## Task 3: Fix Status Propagation — Failed Results Must Set 'failed' Status

**Files:**
- Modify: `app.py:3067-3072`

**Step 1: Check result.success before setting status**

Change `app.py` lines 3067-3072 from:

```python
with session_lock:
    if session_id in cityscraper_sessions:
        cityscraper_sessions[session_id]['status'] = 'completed'
        cityscraper_results[session_id] = result

logger.info(f"CityScraper research completed: {session_id}")
```

To:

```python
with session_lock:
    if session_id in cityscraper_sessions:
        if isinstance(result, dict) and result.get('success') is False:
            cityscraper_sessions[session_id]['status'] = 'failed'
            cityscraper_sessions[session_id]['error'] = result.get('error', 'Research returned unsuccessful result')
            logger.warning(f"CityScraper research failed (result.success=False): {session_id} - {result.get('error', 'unknown')}")
        else:
            cityscraper_sessions[session_id]['status'] = 'completed'
            logger.info(f"CityScraper research completed: {session_id}")
        cityscraper_results[session_id] = result
```

**Step 2: Commit**

```bash
git add app.py
git commit -m "fix: Set scraper session status to 'failed' when result.success is False"
```

---

## Task 4: Fix Frontend Error State — Show Error Instead of Resetting

**Files:**
- Modify: `index.html` (~lines 4069-4085, 4127-4148)

**Step 1: Improve the 'failed' status handler in pollCityScraperEvents**

Change lines 4079-4081 from:

```javascript
} else if (data.status === 'failed') {
    document.getElementById('cs-progress-phase').textContent = 'Failed';
    addCSDebugLog('Research failed: ' + (data.error || 'Unknown error'));
}
```

To:

```javascript
} else if (data.status === 'failed') {
    document.getElementById('cs-progress-phase').textContent = 'Research Failed';
    document.getElementById('cs-progress-percent').textContent = '';
    document.getElementById('cs-progress-fill').style.width = '0%';
    addCSDebugLog('Research failed: ' + (data.error || 'Unknown error'));

    // Show error UI in the progress section (don't hide it)
    const feed = document.getElementById('cs-agent-feed');
    const errorDiv = document.createElement('div');
    errorDiv.className = 'agent-activity failed';
    errorDiv.innerHTML = `
        <div style="padding: 15px; background: #ffebee; border-left: 4px solid #d32f2f; border-radius: 4px; margin-top: 10px;">
            <strong style="color: #d32f2f;">Research Failed</strong>
            <p style="color: #666; margin: 8px 0 0 0;">${escapeHtml(data.error || 'An error occurred during research. Please try again.')}</p>
            <button onclick="document.getElementById('cs-start-research').click()"
                    style="margin-top: 10px; padding: 8px 16px; background: #1E3A8A; color: white; border: none; border-radius: 4px; cursor: pointer;">
                Retry Research
            </button>
        </div>
    `;
    feed.appendChild(errorDiv);

    // Also try to load partial results if available
    loadCityScraperResults();
}
```

**Step 2: Fix loadCityScraperResults to handle failure results**

Change lines 4138-4143 from:

```javascript
if (data.success && data.result) {
    addCSDebugLog('Calling displayCityScraperResults');
    displayCityScraperResults(data.result);
} else {
    addCSDebugLog('No result in response');
}
```

To:

```javascript
if (data.success && data.result) {
    addCSDebugLog('Calling displayCityScraperResults');
    displayCityScraperResults(data.result);
} else if (data.result && data.result.success === false) {
    // Research returned but with errors — show partial results if any
    addCSDebugLog('Research failed: ' + (data.result.error || 'Unknown error'));
    if (data.result.preflight_result || data.result.extraction_result) {
        addCSDebugLog('Displaying partial results...');
        displayCityScraperResults(data.result);
    }
} else {
    addCSDebugLog('No result in response');
}
```

**Step 3: Commit**

```bash
git add index.html
git commit -m "fix: Show error state and partial results when scraper research fails"
```

---

## Task 5: Add Live Data Table to CityScraper (Preflight Info + System Info Table)

This is the largest task. The live table should:
- Appear in the progress section as soon as research starts
- Show **two sections**: (1) Preflight validation info, (2) System info data table
- Update cells live as events arrive from polling
- Follow the BidBrief unitary table pattern (skeleton → fill in → confidence colors)

**Files:**
- Modify: `index.html` (HTML structure + JS functions)
- Modify: `services/scraper/orchestrators/standalone_research.py` (emit data events)
- Modify: `services/scraper/orchestrators/extraction.py` (emit per-field events)
- Modify: `app.py` (include data_updates in events endpoint response)

### Step 1: Add live table HTML to progress section

In `index.html`, after the debug log `</details>` (line 820) and before `</div>` closing `cs-progress-section` (line 821), add:

```html
<!-- Live Data Table -->
<div id="cs-live-table-section" class="hidden" style="margin-top: 20px;">
    <!-- Preflight Info Panel -->
    <div id="cs-preflight-panel" style="background: white; padding: 15px; border-radius: 8px; margin-bottom: 15px; border: 1px solid #e0e0e0;">
        <h4 style="color: #1E3A8A; margin: 0 0 12px 0; border-bottom: 2px solid #5B7FCC; padding-bottom: 8px;">
            Pre-Flight Validation
            <span id="cs-preflight-status" style="float: right; font-size: 13px; padding: 2px 10px; border-radius: 12px; background: #e0e0e0; color: #666;">Pending</span>
        </h4>
        <div id="cs-preflight-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 13px;">
            <div class="pf-field"><strong>Municipality:</strong> <span id="pf-municipality" class="pf-value pending">Resolving...</span></div>
            <div class="pf-field"><strong>County:</strong> <span id="pf-county" class="pf-value pending">—</span></div>
            <div class="pf-field"><strong>Region:</strong> <span id="pf-region" class="pf-value pending">—</span></div>
            <div class="pf-field"><strong>Sanitary Sewer Owner:</strong> <span id="pf-sanitary-owner" class="pf-value pending">—</span></div>
            <div class="pf-field"><strong>Storm Sewer Owner:</strong> <span id="pf-storm-owner" class="pf-value pending">—</span></div>
            <div class="pf-field"><strong>Official Website:</strong> <span id="pf-official-url" class="pf-value pending">—</span></div>
            <div class="pf-field"><strong>Sources Found:</strong> <span id="pf-sources-count" class="pf-value pending">—</span></div>
            <div class="pf-field"><strong>Readiness:</strong> <span id="pf-readiness" class="pf-value pending">—</span></div>
        </div>
    </div>

    <!-- Live System Info Table -->
    <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0;">
        <h4 style="color: #1E3A8A; margin: 0 0 12px 0; border-bottom: 2px solid #5B7FCC; padding-bottom: 8px;">
            Extracted Data
            <span id="cs-live-field-count" style="float: right; font-size: 13px; color: #666;">0 / 9 fields</span>
        </h4>
        <div style="overflow-x: auto;">
            <table id="cs-live-data-table" style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <thead>
                    <tr style="background: linear-gradient(135deg, #1E3A8A, #5B7FCC); color: white;">
                        <th style="padding: 10px; text-align: left; border: 1px solid #ddd; width: 180px;">Field</th>
                        <th style="padding: 10px; text-align: left; border: 1px solid #ddd;">Value</th>
                        <th style="padding: 10px; text-align: center; border: 1px solid #ddd; width: 90px;">Confidence</th>
                        <th style="padding: 10px; text-align: left; border: 1px solid #ddd; width: 120px;">Source</th>
                    </tr>
                </thead>
                <tbody id="cs-live-data-body">
                    <!-- Rows initialized by JS -->
                </tbody>
            </table>
        </div>
    </div>
</div>
```

### Step 2: Add CSS for live table (in existing `<style>` block)

```css
.pf-value {
    color: #333;
}
.pf-value.pending {
    color: #999;
    font-style: italic;
}
.pf-value.resolved {
    color: #1E3A8A;
    font-weight: 500;
    font-style: normal;
}
.live-row-pending td {
    color: #bbb;
    font-style: italic;
}
.live-row-found td {
    color: #333;
    font-style: normal;
}
.confidence-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}
.confidence-high { background: #e8f5e9; color: #2e7d32; }
.confidence-medium { background: #fff3e0; color: #ed6c02; }
.confidence-low { background: #ffebee; color: #d32f2f; }
.confidence-unknown { background: #f5f5f5; color: #999; }
```

### Step 3: Add JS to initialize and update live table

Add these functions near the existing CityScraper JS:

```javascript
// System Info field definitions for live table
const CS_SYSTEM_INFO_FIELDS = [
    { id: 'agency_scope', label: 'Agency Scope', agent: 'EX-1' },
    { id: 'sanitary_sewer_pipe', label: 'Sanitary Sewer Pipe', agent: 'EX-1' },
    { id: 'storm_drain_pipe', label: 'Storm Drain Pipe', agent: 'EX-1' },
    { id: 'storm_drain_assets', label: 'Storm Drain Assets', agent: 'EX-1' },
    { id: 'system_age_history', label: 'System Age & History', agent: 'EX-2' },
    { id: 'equipment_owned', label: 'Equipment Owned', agent: 'EX-2' },
    { id: 'maintenance_practices', label: 'Maintenance Practices', agent: 'EX-3' },
    { id: 'sewage_incidents', label: 'Sewage Incidents', agent: 'EX-4' },
    { id: 'storm_incidents', label: 'Storm Incidents', agent: 'EX-4' }
];

// Live table state
let csLiveData = {};

function initCSLiveTable() {
    csLiveData = {};
    const tbody = document.getElementById('cs-live-data-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    CS_SYSTEM_INFO_FIELDS.forEach(field => {
        csLiveData[field.id] = { status: 'pending', value: null, confidence: null, source: null };
        const tr = document.createElement('tr');
        tr.id = `cs-live-row-${field.id}`;
        tr.className = 'live-row-pending';
        tr.innerHTML = `
            <td style="padding: 10px; border: 1px solid #eee; font-weight: 500;">${field.label} <span style="font-size:10px;color:#999;">(${field.agent})</span></td>
            <td style="padding: 10px; border: 1px solid #eee;" class="live-cell-value">Analyzing...</td>
            <td style="padding: 10px; border: 1px solid #eee; text-align: center;" class="live-cell-confidence">—</td>
            <td style="padding: 10px; border: 1px solid #eee;" class="live-cell-source">—</td>
        `;
        tbody.appendChild(tr);
    });

    document.getElementById('cs-live-field-count').textContent = '0 / ' + CS_SYSTEM_INFO_FIELDS.length + ' fields';
    document.getElementById('cs-live-table-section').classList.remove('hidden');
}

function updateCSLiveField(fieldId, value, confidence, sourceUrl) {
    const state = csLiveData[fieldId];
    if (!state) return;

    state.status = 'found';
    state.value = value;
    state.confidence = confidence;
    state.source = sourceUrl;

    const row = document.getElementById(`cs-live-row-${fieldId}`);
    if (!row) return;

    row.className = 'live-row-found';
    const cells = row.querySelectorAll('td');

    // Value cell
    cells[1].textContent = value || 'NOT FOUND';
    cells[1].style.color = (value && value !== 'NOT FOUND') ? '#333' : '#999';

    // Confidence badge
    const conf = (confidence || 'unknown').toLowerCase();
    cells[2].innerHTML = `<span class="confidence-badge confidence-${conf}">${conf}</span>`;

    // Source link
    if (sourceUrl && sourceUrl !== 'NOT FOUND') {
        const domain = sourceUrl.replace(/^https?:\/\//, '').split('/')[0];
        cells[3].innerHTML = `<a href="${escapeHtml(sourceUrl)}" target="_blank" style="color:#1E3A8A;font-size:12px;">${escapeHtml(domain)}</a>`;
    }

    // Update field count
    const foundCount = Object.values(csLiveData).filter(d => d.status === 'found').length;
    document.getElementById('cs-live-field-count').textContent = foundCount + ' / ' + CS_SYSTEM_INFO_FIELDS.length + ' fields';
}

function updateCSPreflightPanel(preflightData) {
    if (!preflightData) return;

    const setField = (id, value) => {
        const el = document.getElementById(id);
        if (el && value) {
            el.textContent = value;
            el.className = 'pf-value resolved';
        }
    };

    const muni = preflightData.municipality || {};
    setField('pf-municipality', muni.full_name || muni.city);
    setField('pf-county', muni.county);
    setField('pf-region', muni.region);

    const jurisdiction = preflightData.jurisdiction || {};
    setField('pf-sanitary-owner', jurisdiction.sanitary_sewer_owner);
    setField('pf-storm-owner', jurisdiction.storm_sewer_owner);

    const sourceMap = preflightData.source_map || {};
    const official = sourceMap.official_website;
    if (official && official.url) {
        const el = document.getElementById('pf-official-url');
        if (el) {
            el.innerHTML = `<a href="${escapeHtml(official.url)}" target="_blank" style="color:#1E3A8A;">${escapeHtml(official.url)}</a>`;
            el.className = 'pf-value resolved';
        }
    }

    setField('pf-sources-count', preflightData.sources_discovered_count);
    setField('pf-readiness', preflightData.status);

    // Update status badge
    const statusEl = document.getElementById('cs-preflight-status');
    if (statusEl && preflightData.status) {
        const status = preflightData.status;
        const colors = { 'GO': '#e8f5e9', 'CONDITIONAL': '#fff3e0', 'FAIL': '#ffebee' };
        const textColors = { 'GO': '#2e7d32', 'CONDITIONAL': '#ed6c02', 'FAIL': '#d32f2f' };
        statusEl.textContent = status;
        statusEl.style.background = colors[status] || '#e0e0e0';
        statusEl.style.color = textColors[status] || '#666';
    }
}
```

### Step 4: Modify event handling to process live data events

In `pollCityScraperEvents()` (around line 4060), after `updateCSAgentFeed()`, add handling for new event types:

```javascript
// Process data events for live table
if (data.events) {
    data.events.forEach(event => {
        // Preflight complete — update preflight panel
        if (event.agent_id === 'uc-2' && event.message && event.message.includes('Pre-flight complete')) {
            // Preflight data will come in a special event
        }

        // Check for data_update events (new extraction data)
        if (event.data_update) {
            const du = event.data_update;
            if (du.type === 'preflight') {
                updateCSPreflightPanel(du.preflight_data);
            } else if (du.type === 'field_extracted') {
                updateCSLiveField(du.field_id, du.value, du.confidence, du.source_url);
            }
        }
    });
}
```

### Step 5: Initialize live table when research starts

In the `startCityScraperResearch()` function, after showing the progress section and before starting polling, add:

```javascript
initCSLiveTable();
```

### Step 6: Emit data events from standalone_research.py

In `standalone_research.py`, after preflight completes successfully (around line 248-252), emit a data event with preflight info:

```python
# After line 246 (municipality = preflight_result.municipality)
# Emit preflight data for live table
self.emit_data_event("preflight", {
    'municipality': {
        'city': municipality.city,
        'state': municipality.state,
        'county': municipality.county,
        'region': municipality.region,
        'full_name': municipality.full_name,
    },
    'jurisdiction': {
        'sanitary_sewer_owner': getattr(preflight_result, 'sanitary_sewer_owner', None),
        'storm_sewer_owner': getattr(preflight_result, 'storm_sewer_owner', None),
    },
    'source_map': self._serialize_source_map(preflight_result),
    'sources_discovered_count': getattr(preflight_result, 'sources_discovered_count', 0),
    'status': preflight_result.status.value if preflight_result.status else 'UNKNOWN'
})
```

Add the `emit_data_event` method to `StandaloneResearchOrchestrator`:

```python
def emit_data_event(self, data_type: str, data: Dict[str, Any]):
    """Emit a data update event for live table updates."""
    event = AgentActivityEvent(
        agent_id=self.ORCHESTRATOR_ID,
        agent_name=self.ORCHESTRATOR_NAME,
        status="data_update",
        message=f"Data update: {data_type}",
        is_active=True,
        is_completed=False,
        timestamp=datetime.now()
    )
    # Attach data payload
    event.data_update = {
        'type': data_type,
        **({data_type + '_data': data} if data_type == 'preflight' else data)
    }
    self.agent_events.append(event)
    if self.event_callback:
        self.event_callback(event)
```

### Step 7: Emit per-field events from extraction agents

In the extraction orchestrator (`extraction.py`), after each agent returns results, emit field-level events. Add to the `_process_agent_result` or `_run_systems_info_extraction` method:

```python
def _emit_field_events(self, row: 'MunicipalSystemsInfoRow'):
    """Emit events for each extracted data field for live table updates."""
    fields = [
        ('agency_scope', row.agency_scope),
        ('sanitary_sewer_pipe', row.sanitary_sewer_pipe),
        ('storm_drain_pipe', row.storm_drain_pipe),
        ('storm_drain_assets', row.storm_drain_assets),
        ('system_age_history', row.system_age_history),
        ('equipment_owned', row.equipment_owned),
        ('maintenance_practices', row.maintenance_practices),
        ('sewage_incidents', row.sewage_incidents),
        ('storm_incidents', row.storm_incidents),
    ]
    for field_id, data_point in fields:
        if data_point and data_point.value and data_point.value != 'NOT FOUND':
            event = AgentActivityEvent(
                agent_id=self.ORCHESTRATOR_ID,
                agent_name=self.ORCHESTRATOR_NAME,
                status="data_update",
                message=f"Extracted: {field_id}",
                timestamp=datetime.now()
            )
            event.data_update = {
                'type': 'field_extracted',
                'field_id': field_id,
                'value': data_point.value[:200],  # Truncate for event stream
                'confidence': data_point.confidence.value if data_point.confidence else 'UNKNOWN',
                'source_url': data_point.source_url or ''
            }
            if self.event_callback:
                self.event_callback(event)
```

Call `_emit_field_events()` after each systems info row is assembled.

### Step 8: Update app.py event callback to pass data_update through

In `app.py`, modify the `on_event` callback (line 3039-3048) to pass through `data_update`:

```python
def on_event(event):
    with session_lock:
        if session_id in cityscraper_events:
            event_data = {
                'agent_id': getattr(event, 'agent_id', 'SYS'),
                'agent_name': getattr(event, 'agent_name', 'System'),
                'status': getattr(event, 'status', 'processing'),
                'message': getattr(event, 'message', ''),
                'timestamp': datetime.now().isoformat()
            }
            # Pass through data_update if present
            if hasattr(event, 'data_update'):
                event_data['data_update'] = event.data_update
            cityscraper_events[session_id].append(event_data)
```

### Step 9: Commit

```bash
git add index.html app.py services/scraper/orchestrators/standalone_research.py services/scraper/orchestrators/extraction.py
git commit -m "feat: Add live-updating data table to CityScraper with preflight info and per-field updates"
```

---

## Task 6: Add AgentActivityEvent.data_update field

**Files:**
- Modify: `services/scraper/models.py` (add `data_update` field to AgentActivityEvent)

**Step 1: Add optional data_update field**

Find the `AgentActivityEvent` dataclass and add:

```python
@dataclass
class AgentActivityEvent:
    agent_id: str
    agent_name: str
    status: str
    message: str
    timestamp: datetime
    is_active: bool = True
    is_completed: bool = False
    data_update: Optional[Dict[str, Any]] = None  # NEW: for live table updates
```

**Step 2: Commit**

```bash
git add services/scraper/models.py
git commit -m "feat: Add data_update field to AgentActivityEvent for live table events"
```

---

## Task 7: Integration Testing

**Step 1: Manual test the full flow**

1. Start the app locally: `python app.py`
2. Navigate to CityScraper tab
3. Enter a municipality (e.g., "Springfield, IL")
4. Select "Municipal Systems Information"
5. Click "Start Research"

**Expected behavior:**
- Live table appears immediately with 9 "Analyzing..." rows
- Preflight panel shows "Pending" status
- After ~30s, preflight panel populates with municipality info, sources, readiness status
- Table cells fill in one-by-one as extraction agents return data
- Confidence badges color-code each cell
- On completion, results section shows final table
- On failure, error message displays with retry button (no silent reset)

**Step 2: Test rate limiting**

- Watch logs for `rate limiting: waiting` messages
- Confirm no more than ~30 Tavily calls per minute
- Confirm 432 errors trigger exponential backoff
- Confirm circuit breaker opens after 5 consecutive failures

**Step 3: Test error state**

- Set an invalid TAVILY_API_KEY to force failures
- Confirm frontend shows "Research Failed" with error message
- Confirm retry button works
- Confirm partial results display if any data was gathered before failure

---

## Execution Order & Dependencies

```
Task 6 (AgentActivityEvent.data_update field)  ← FIRST (other tasks depend on this)
  ↓
Task 1 (Tavily rate limiter)  ← Can run independently
Task 2 (PF-3 validation fix)  ← Can run independently
Task 3 (Status propagation fix)  ← Can run independently
  ↓
Task 4 (Frontend error state)  ← Depends on Task 3
Task 5 (Live data table)  ← Depends on Task 6, integrates with Tasks 1-4
  ↓
Task 7 (Integration testing)  ← LAST
```
