// ═══════════════════════════════════════════════════════════════════════════
// MAIN TAB SWITCHING
// ═══════════════════════════════════════════════════════════════════════════

function switchMainTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.main-tab-btn').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        }
    });

    // Update tab content
    document.querySelectorAll('.main-tab-content').forEach(content => {
        content.classList.remove('active');
        content.style.display = 'none';
    });

    const targetTab = document.getElementById(tabName + '-tab');
    if (targetTab) {
        targetTab.classList.add('active');
        targetTab.style.display = 'block';
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// CITYSCRAPER EVENT HANDLING
// ═══════════════════════════════════════════════════════════════════════════

let csSessionId = null;
let csPollingInterval = null;
let csEventIndex = 0;
let csResearchInProgress = false;  // Debounce flag to prevent double-clicks

async function startCityScraperResearch() {
    // Debounce: prevent double-clicks from starting multiple research sessions
    if (csResearchInProgress) {
        console.log('[CityScraper] Research already in progress, ignoring duplicate click');
        return;
    }
    csResearchInProgress = true;

    const municipality = document.getElementById('cs-municipality').value;
    const tableMode = document.getElementById('cs-table-mode').value;

    if (!municipality) {
        alert('Please enter a municipality');
        csResearchInProgress = false;
        return;
    }

    // Reset state
    csEventIndex = 0;
    document.getElementById('cs-progress-section').classList.remove('hidden');
    document.getElementById('cs-results-section').classList.add('hidden');
    document.getElementById('cs-agent-feed').innerHTML = '';
    document.getElementById('cs-debug-log').innerHTML = '';
    document.getElementById('cs-start-research').disabled = true;
    document.getElementById('cs-stop-research').disabled = false;
    document.getElementById('cs-progress-phase').textContent = 'Initializing...';
    document.getElementById('cs-progress-percent').textContent = '0%';
    document.getElementById('cs-progress-fill').style.width = '0%';

    // Initialize live data table
    initCSLiveTable();

    try {
        const response = await fetch('/api/scraper/research', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin',
            body: JSON.stringify({municipality, table_mode: tableMode})
        });

        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to start research');
        }

        csSessionId = data.session_id;
        addCSDebugLog('Session started: ' + csSessionId);
        csPollingInterval = setInterval(pollCityScraperEvents, 1000);
    } catch (error) {
        alert('Error starting research: ' + error.message);
        document.getElementById('cs-start-research').disabled = false;
        document.getElementById('cs-stop-research').disabled = true;
        csResearchInProgress = false;  // Reset debounce flag on error
    }
}

async function pollCityScraperEvents() {
    if (!csSessionId) return;

    try {
        const response = await fetch(`/api/scraper/events/${csSessionId}?since=${csEventIndex}`, {
            credentials: 'same-origin'
        });

        // Handle auth errors - session may have expired
        if (response.status === 401) {
            addCSDebugLog('Authentication expired - trying to load results directly');
            clearInterval(csPollingInterval);
            csResearchInProgress = false;
            // Try to load results anyway (research may have completed)
            loadCityScraperResults();
            return;
        }

        if (response.status === 404) {
            addCSDebugLog('Session not found - research may have completed');
            clearInterval(csPollingInterval);
            csResearchInProgress = false;
            loadCityScraperResults();
            return;
        }

        const data = await response.json();

        // Update event index
        csEventIndex = data.total_events || csEventIndex;

        // Update agent feed
        updateCSAgentFeed(data.events || []);

        // Process data_update events for live table
        (data.events || []).forEach(function(event) {
            if (event.data_update) {
                var du = event.data_update;
                if (du.type === 'preflight') {
                    updateCSPreflightPanel(du.preflight_data);
                } else if (du.type === 'field_extracted') {
                    updateCSLiveField(du.field_id, du.value, du.confidence, du.source_url);
                }
            }
        });

        // Update progress if available
        if (data.progress) {
            updateCSProgress(data.progress);
        }

        // Check if complete
        if (data.status === 'completed' || data.status === 'failed' || data.status === 'cancelled') {
            clearInterval(csPollingInterval);
            csResearchInProgress = false;  // Reset debounce flag when research ends
            document.getElementById('cs-start-research').disabled = false;
            document.getElementById('cs-stop-research').disabled = true;
            if (data.status === 'completed') {
                document.getElementById('cs-progress-phase').textContent = 'Complete!';
                document.getElementById('cs-progress-percent').textContent = '100%';
                document.getElementById('cs-progress-fill').style.width = '100%';
                loadCityScraperResults();
            } else if (data.status === 'failed') {
                document.getElementById('cs-progress-phase').textContent = 'Research Failed';
                document.getElementById('cs-progress-percent').textContent = '';
                document.getElementById('cs-progress-fill').style.width = '0%';
                addCSDebugLog('Research failed: ' + (data.error || 'Unknown error'));

                // Show error UI in the agent feed
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

                // Try to load partial results if available
                loadCityScraperResults();
            } else if (data.status === 'cancelled') {
                document.getElementById('cs-progress-phase').textContent = 'Cancelled';
            }
        }
    } catch (error) {
        console.error('Polling error:', error);
        addCSDebugLog('Polling error: ' + error.message);
    }
}

function updateCSAgentFeed(events) {
    const feed = document.getElementById('cs-agent-feed');
    events.forEach(event => {
        const div = document.createElement('div');
        div.className = 'agent-activity ' + (event.status || 'processing');
        div.innerHTML = `
            <span class="agent-id">${event.agent_id || 'SYS'}</span>
            <span class="agent-name">${event.agent_name || ''}</span>
            <span class="agent-status">${event.message || ''}</span>
        `;
        feed.appendChild(div);
        feed.scrollTop = feed.scrollHeight;

        // Also add to debug log
        addCSDebugLog(`[${event.agent_id || 'SYS'}] ${event.message || ''}`);
    });
}

function updateCSProgress(progress) {
    if (progress.phase) {
        document.getElementById('cs-progress-phase').textContent = progress.phase;
    }
    if (progress.percent !== undefined) {
        document.getElementById('cs-progress-percent').textContent = progress.percent + '%';
        document.getElementById('cs-progress-fill').style.width = progress.percent + '%';
    }
}

// ═══════════════════════════════════════════════════════════════════
// LIVE DATA TABLE - Preflight Info + System Info (updates in real-time)
// ═══════════════════════════════════════════════════════════════════

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

let csLiveData = {};

function initCSLiveTable() {
    csLiveData = {};
    const tbody = document.getElementById('cs-live-data-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    CS_SYSTEM_INFO_FIELDS.forEach(field => {
        csLiveData[field.id] = { status: 'pending', value: null, confidence: null, source: null };
        const tr = document.createElement('tr');
        tr.id = 'cs-live-row-' + field.id;
        tr.className = 'live-row-pending';
        tr.innerHTML =
            '<td style="padding: 10px; border: 1px solid #eee; font-weight: 500;">' + escapeHtml(field.label) + ' <span style="font-size:10px;color:#999;">(' + field.agent + ')</span></td>' +
            '<td style="padding: 10px; border: 1px solid #eee;" class="live-cell-value">Analyzing...</td>' +
            '<td style="padding: 10px; border: 1px solid #eee; text-align: center;" class="live-cell-confidence">&mdash;</td>' +
            '<td style="padding: 10px; border: 1px solid #eee;" class="live-cell-source">&mdash;</td>';
        tbody.appendChild(tr);
    });

    document.getElementById('cs-live-field-count').textContent = '0 / ' + CS_SYSTEM_INFO_FIELDS.length + ' fields';
    document.getElementById('cs-live-table-section').classList.remove('hidden');

    // Reset preflight panel
    ['pf-municipality','pf-county','pf-region','pf-sanitary-owner','pf-storm-owner','pf-official-url','pf-sources-count','pf-readiness'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.textContent = id === 'pf-municipality' ? 'Resolving...' : '\u2014'; el.className = 'pf-value pending'; }
    });
    const statusEl = document.getElementById('cs-preflight-status');
    if (statusEl) { statusEl.textContent = 'Pending'; statusEl.style.background = '#e0e0e0'; statusEl.style.color = '#666'; }
}

function updateCSLiveField(fieldId, value, confidence, sourceUrl) {
    const state = csLiveData[fieldId];
    if (!state) return;

    state.status = 'found';
    state.value = value;
    state.confidence = confidence;
    state.source = sourceUrl;

    const row = document.getElementById('cs-live-row-' + fieldId);
    if (!row) return;

    row.className = 'live-row-found';
    const cells = row.querySelectorAll('td');

    // Value cell
    cells[1].textContent = value || 'NOT FOUND';
    cells[1].style.color = (value && value !== 'NOT FOUND') ? '#333' : '#999';

    // Confidence badge
    const conf = (confidence || 'unknown').toLowerCase();
    cells[2].innerHTML = '<span class="confidence-badge confidence-' + conf + '">' + conf + '</span>';

    // Source link
    if (sourceUrl && sourceUrl !== 'NOT FOUND' && sourceUrl.startsWith('http')) {
        const domain = sourceUrl.replace(/^https?:\/\//, '').split('/')[0];
        cells[3].innerHTML = '<a href="' + escapeHtml(sourceUrl) + '" target="_blank" style="color:#1E3A8A;font-size:12px;">' + escapeHtml(domain) + '</a>';
    }

    // Update field count
    const foundCount = Object.values(csLiveData).filter(d => d.status === 'found').length;
    document.getElementById('cs-live-field-count').textContent = foundCount + ' / ' + CS_SYSTEM_INFO_FIELDS.length + ' fields';
}

function updateCSPreflightPanel(preflightData) {
    if (!preflightData) return;

    const setField = function(id, value) {
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
            el.innerHTML = '<a href="' + escapeHtml(official.url) + '" target="_blank" style="color:#1E3A8A;">' + escapeHtml(official.url) + '</a>';
            el.className = 'pf-value resolved';
        }
    }

    setField('pf-sources-count', String(preflightData.sources_discovered_count || 0));
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

function addCSDebugLog(message) {
    const log = document.getElementById('cs-debug-log');
    const timestamp = new Date().toLocaleTimeString();
    log.innerHTML += `[${timestamp}] ${message}\n`;
    log.scrollTop = log.scrollHeight;
}

async function loadCityScraperResults() {
    try {
        addCSDebugLog('Loading results...');
        const response = await fetch(`/api/scraper/research/${csSessionId}`, {
            credentials: 'same-origin'
        });
        const data = await response.json();

        console.log('CityScraper API Response:', data);
        addCSDebugLog('Got response, success=' + data.success);

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
    } catch (error) {
        console.error('Error loading results:', error);
        addCSDebugLog('Error loading results: ' + error.message);
    }
}

// Store current CityScraper result for exports
let currentCSResult = null;

function displayCityScraperResults(result) {
    try {
        console.log('displayCityScraperResults called with:', result);
        addCSDebugLog('Displaying results...');

        // Store for exports
        currentCSResult = result;

        // Hide progress, show results
        const progressSection = document.getElementById('cs-progress-section');
        const resultsSection = document.getElementById('cs-results-section');

        if (!progressSection || !resultsSection) {
            console.error('CityScraper sections not found!');
            addCSDebugLog('ERROR: CityScraper sections not found in DOM');
            return;
        }

        progressSection.classList.add('hidden');
        resultsSection.classList.remove('hidden');

        // Get data from result - check multiple paths
        const presentation = result.presentation_result || {};
    const extraction = result.extraction_result || {};
    const municipality = result.municipality || {};
    const statistics = result.statistics || {};

    console.log('Presentation:', presentation);
    console.log('Extraction:', extraction);

    addCSDebugLog(`Municipality: ${municipality.full_name || municipality.city || 'Unknown'}`);
    addCSDebugLog(`Stats: ${statistics.fields_extracted || 0} fields, ${statistics.sources_found || 0} sources`);

    // Build the results display
    const tableDiv = document.getElementById('cs-results-table');
    let html = '<div style="background: white; padding: 20px; border-radius: 8px;">';

    // Header with municipality info
    html += `
        <div style="margin-bottom: 20px; padding: 15px; background: linear-gradient(135deg, #1E3A8A, #5B7FCC); border-radius: 8px; color: white;">
            <h2 style="margin: 0 0 10px 0;">Municipal Research Results</h2>
            <div style="display: flex; gap: 20px; flex-wrap: wrap; font-size: 14px;">
                <span><strong>Municipality:</strong> ${escapeHtml(municipality.full_name || municipality.city || 'Unknown')}</span>
                <span><strong>Sources Found:</strong> ${statistics.sources_found || 0}</span>
                <span><strong>Data Points:</strong> ${statistics.fields_extracted || 0}</span>
                <span><strong>Processing Time:</strong> ${(result.processing_time_seconds || 0).toFixed(1)}s</span>
            </div>
        </div>
    `;

    // Check if we have presentation data with data_table
    const dataTable = presentation.data_table || {};
    if (dataTable.headers && dataTable.rows && dataTable.rows.length > 0) {
        addCSDebugLog(`Rendering table: ${dataTable.headers.length} columns, ${dataTable.rows.length} rows`);

        html += `
            <h3 style="color: #1E3A8A; margin: 20px 0 15px 0; border-bottom: 2px solid #5B7FCC; padding-bottom: 10px;">
                Extracted Data
            </h3>
            <div style="overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <thead>
                        <tr style="background: linear-gradient(135deg, #1E3A8A, #5B7FCC); color: white;">
        `;

        dataTable.headers.forEach(h => {
            html += `<th style="padding: 12px; text-align: left; border: 1px solid #ddd; white-space: nowrap;">${escapeHtml(h)}</th>`;
        });
        html += '</tr></thead><tbody>';

        dataTable.rows.forEach((row, idx) => {
            const rowBg = idx % 2 === 1 ? 'background: #f8f9fa;' : '';
            html += `<tr style="${rowBg} cursor: pointer;" onclick="toggleCSRowDetails(this)">`;

            if (row.cells && Array.isArray(row.cells)) {
                row.cells.forEach(cell => {
                    const value = cell.value || cell || '';
                    const conf = cell.confidence || 'medium';
                    const confColor = cell.confidence_color || getConfidenceColor(conf);
                    const borderStyle = `border-left: 4px solid ${confColor};`;
                    html += `<td style="padding: 10px; border: 1px solid #ddd; ${borderStyle} vertical-align: top;">${escapeHtml(String(value))}</td>`;
                });
            }
            html += '</tr>';
        });
        html += '</tbody></table></div>';

        // Summary stats
        const summary = presentation.summary || {};
        html += `
            <div style="margin-top: 15px; padding: 15px; background: #f5f5f5; border-radius: 8px; display: flex; gap: 20px; flex-wrap: wrap;">
                <div><strong>Total Data Points:</strong> ${summary.total_data_points || 0}</div>
                <div style="color: #2e7d32;"><strong>High Confidence:</strong> ${summary.high_confidence_count || 0}</div>
                <div style="color: #ed6c02;"><strong>Medium:</strong> ${summary.medium_confidence_count || 0}</div>
                <div style="color: #d32f2f;"><strong>Low:</strong> ${summary.low_confidence_count || 0}</div>
                <div style="color: #666;"><strong>Not Found:</strong> ${summary.not_found_count || 0}</div>
            </div>
        `;
    } else {
        // Fallback: Try to render extraction result directly
        addCSDebugLog('No data_table found, trying extraction_result');

        if (extraction.systems_info_rows && extraction.systems_info_rows.length > 0) {
            html += renderSystemsInfoTable(extraction.systems_info_rows);
        } else if (extraction.public_bid_rows && extraction.public_bid_rows.length > 0) {
            html += renderPublicBidsTable(extraction.public_bid_rows);
        } else {
            html += `
                <div style="padding: 40px; text-align: center; background: #fff3e0; border-radius: 8px;">
                    <h3 style="color: #ed6c02; margin-bottom: 10px;">Limited Data Available</h3>
                    <p style="color: #666;">The research found ${statistics.sources_found || 0} sources but could only extract ${statistics.fields_extracted || 0} data points.</p>
                    <p style="color: #666; font-size: 13px;">This may indicate the municipality has limited public data available online.</p>
                </div>
            `;
        }
    }

    // Data gaps and warnings
    if (presentation.data_gaps && presentation.data_gaps.length > 0) {
        html += `
            <div style="margin-top: 15px; padding: 15px; background: #fce4ec; border-left: 4px solid #d32f2f; border-radius: 4px;">
                <strong style="color: #d32f2f;">Data Gaps Identified:</strong>
                <ul style="margin: 10px 0 0 20px; padding: 0; color: #666;">
                    ${presentation.data_gaps.slice(0, 5).map(g => `<li>${escapeHtml(g)}</li>`).join('')}
                    ${presentation.data_gaps.length > 5 ? `<li><em>... and ${presentation.data_gaps.length - 5} more</em></li>` : ''}
                </ul>
            </div>
        `;
    }

    if (presentation.warnings && presentation.warnings.length > 0) {
        html += `
            <div style="margin-top: 15px; padding: 15px; background: #fff3e0; border-left: 4px solid #ed6c02; border-radius: 4px;">
                <strong style="color: #ed6c02;">Warnings:</strong>
                <ul style="margin: 10px 0 0 20px; padding: 0; color: #666;">
                    ${presentation.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}
                </ul>
            </div>
        `;
    }

    html += '</div>';
    tableDiv.innerHTML = html;

    // Display sources
    const sources = presentation.sources || [];
    const sourcesDiv = document.getElementById('cs-results-sources');
    if (sources.length > 0) {
        let sourcesHtml = `
            <div style="background: white; padding: 20px; border-radius: 8px;">
                <h3 style="color: #1E3A8A; margin: 0 0 15px 0;">${sources.length} Sources Referenced</h3>
                <div style="display: grid; gap: 10px;">
        `;
        sources.forEach((source, idx) => {
            const citationsText = source.citations_count > 0 ? `${source.citations_count} citations` : '';
            sourcesHtml += `
                <div style="padding: 12px; background: ${idx % 2 === 0 ? '#f8f9fa' : 'white'}; border-radius: 4px; border: 1px solid #eee;">
                    <a href="${escapeHtml(source.url || '#')}" target="_blank" style="color: #1E3A8A; text-decoration: none; font-weight: 500;">
                        ${escapeHtml(source.title || 'Untitled Source')}
                    </a>
                    <div style="margin-top: 5px; font-size: 12px; color: #666;">
                        <span style="background: #e3f2fd; padding: 2px 8px; border-radius: 4px; margin-right: 8px;">${escapeHtml(source.type || 'Unknown')}</span>
                        ${citationsText ? `<span>${citationsText}</span>` : ''}
                    </div>
                    <div style="margin-top: 5px; font-size: 11px; color: #999; word-break: break-all;">${escapeHtml(source.url || '')}</div>
                </div>
            `;
        });
        sourcesHtml += '</div></div>';
        sourcesDiv.innerHTML = sourcesHtml;
    } else {
        sourcesDiv.innerHTML = '<div style="padding: 20px; text-align: center; color: #666;">No sources available.</div>';
    }

    // Display downloads
    const exportUrls = presentation.export_urls || {};
    const downloadsDiv = document.getElementById('cs-results-downloads');
    let downloadsHtml = `
        <div style="background: white; padding: 20px; border-radius: 8px;">
            <h3 style="color: #1E3A8A; margin: 0 0 15px 0;">Export Options</h3>
            <div style="display: flex; gap: 15px; flex-wrap: wrap;">
    `;

    if (exportUrls.excel) {
        downloadsHtml += `<a href="${exportUrls.excel}" class="primary-btn" style="text-decoration: none;">📊 Download Excel</a>`;
    }
    if (exportUrls.markdown) {
        downloadsHtml += `<a href="${exportUrls.markdown}" class="primary-btn" style="text-decoration: none; background: linear-gradient(45deg, #666, #333);">📝 Download Markdown</a>`;
    }
    downloadsHtml += `
                <button onclick="exportCSResultsJSON()" class="primary-btn" style="background: linear-gradient(45deg, #2e7d32, #4caf50);">📄 Export JSON</button>
            </div>
        </div>
    `;
    downloadsDiv.innerHTML = downloadsHtml;

        addCSDebugLog('Results displayed successfully');
    } catch (error) {
        console.error('Error displaying results:', error);
        addCSDebugLog('ERROR displaying results: ' + error.message);

        // Show error in results section
        const tableDiv = document.getElementById('cs-results-table');
        if (tableDiv) {
            tableDiv.innerHTML = `
                <div style="padding: 20px; background: #ffebee; border-radius: 8px; margin: 10px;">
                    <h3 style="color: #c62828; margin-bottom: 10px;">Error Displaying Results</h3>
                    <p style="color: #666;">${escapeHtml(error.message)}</p>
                    <details style="margin-top: 15px;">
                        <summary style="cursor: pointer; color: #1E3A8A;">View Raw Data</summary>
                        <pre style="background: #f5f5f5; padding: 10px; margin-top: 10px; overflow-x: auto; font-size: 11px; max-height: 400px;">${escapeHtml(JSON.stringify(currentCSResult, null, 2))}</pre>
                    </details>
                </div>
            `;
        }
    }
}

function getConfidenceColor(confidence) {
    const colors = {
        'high': '#2e7d32',
        'medium': '#ed6c02',
        'low': '#d32f2f',
        'not_found': '#9e9e9e'
    };
    return colors[confidence] || colors.medium;
}

function toggleCSRowDetails(row) {
    // Future: expand row to show more details
    row.style.background = row.style.background === 'rgb(227, 242, 253)' ? '' : '#e3f2fd';
}

function renderSystemsInfoTable(rows) {
    let html = `
        <h3 style="color: #1E3A8A; margin: 20px 0 15px 0;">Municipal Systems Information</h3>
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <thead>
                    <tr style="background: linear-gradient(135deg, #1E3A8A, #5B7FCC); color: white;">
                        <th style="padding: 10px; border: 1px solid #ddd;">Municipality</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Agency</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Sanitary Sewer</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Storm Drain</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">System Age</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Maintenance</th>
                    </tr>
                </thead>
                <tbody>
    `;

    rows.forEach((row, idx) => {
        const bg = idx % 2 === 1 ? 'background: #f8f9fa;' : '';
        const getValue = (field) => {
            if (!field) return 'NOT FOUND';
            if (typeof field === 'object' && field.value) return field.value;
            return String(field);
        };

        html += `
            <tr style="${bg}">
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(row.municipality_city || '')} ${escapeHtml(row.state || '')}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(row.relevant_agency || '')}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(getValue(row.sanitary_sewer_pipe))}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(getValue(row.storm_drain_pipe))}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(getValue(row.system_age_history))}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(getValue(row.maintenance_practices))}</td>
            </tr>
        `;
    });

    html += '</tbody></table></div>';
    return html;
}

function renderPublicBidsTable(rows) {
    let html = `
        <h3 style="color: #1E3A8A; margin: 20px 0 15px 0;">Public Bids & Contracts</h3>
        <div style="overflow-x: auto;">
            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <thead>
                    <tr style="background: linear-gradient(135deg, #1E3A8A, #5B7FCC); color: white;">
                        <th style="padding: 10px; border: 1px solid #ddd;">Municipality</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Bid Title</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Scope</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Timeline</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Status</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Contact</th>
                    </tr>
                </thead>
                <tbody>
    `;

    rows.forEach((row, idx) => {
        const bg = idx % 2 === 1 ? 'background: #f8f9fa;' : '';
        const getValue = (field) => {
            if (!field) return 'NOT FOUND';
            if (typeof field === 'object' && field.value) return field.value;
            return String(field);
        };

        html += `
            <tr style="${bg}">
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(row.municipality_city || '')} ${escapeHtml(row.state || '')}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(row.bid_contract_title || '')}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(getValue(row.scope))}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(getValue(row.timeline_requirements))}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(row.status || '')}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">${escapeHtml(getValue(row.contacts))}</td>
            </tr>
        `;
    });

    html += '</tbody></table></div>';
    return html;
}

function exportCSResultsJSON() {
    if (!currentCSResult) {
        alert('No results to export');
        return;
    }
    const blob = new Blob([JSON.stringify(currentCSResult, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cityscraper_${currentCSResult.municipality?.city || 'research'}_${new Date().toISOString().split('T')[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function stopCityScraperResearch() {
    if (!csSessionId) return;

    try {
        await fetch(`/api/scraper/stop/${csSessionId}`, {
            method: 'POST',
            credentials: 'same-origin'
        });
        addCSDebugLog('Stop request sent');
        csResearchInProgress = false;  // Reset debounce flag when stopped
    } catch (error) {
        console.error('Stop error:', error);
        addCSDebugLog('Stop error: ' + error.message);
        csResearchInProgress = false;  // Reset debounce flag even on error
    }
}

function switchCSResultsTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('#cs-results-section .results-tab').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.results === tabName) {
            btn.classList.add('active');
        }
    });

    // Update tab content
    document.querySelectorAll('#cs-results-section .results-content').forEach(content => {
        content.classList.remove('active');
    });

    const targetContent = document.getElementById('cs-results-' + tabName);
    if (targetContent) {
        targetContent.classList.add('active');
    }
}

async function exportCityScraperResults(format) {
    if (!csSessionId) {
        alert('No research session to export');
        return;
    }

    try {
        const response = await fetch(`/api/scraper/export/${format}/${csSessionId}`, {
            credentials: 'same-origin'
        });

        if (!response.ok) {
            throw new Error('Export failed');
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `cityscraper_${csSessionId}.${format === 'excel' ? 'xlsx' : 'md'}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        alert('Export error: ' + error.message);
    }
}

// CityScraper event listeners initialization
document.addEventListener('DOMContentLoaded', function() {
    const startBtn = document.getElementById('cs-start-research');
    const stopBtn = document.getElementById('cs-stop-research');
    const exportExcelBtn = document.getElementById('cs-export-excel');
    const exportMdBtn = document.getElementById('cs-export-markdown');

    if (startBtn) startBtn.addEventListener('click', startCityScraperResearch);
    if (stopBtn) stopBtn.addEventListener('click', stopCityScraperResearch);
    if (exportExcelBtn) exportExcelBtn.addEventListener('click', () => exportCityScraperResults('excel'));
    if (exportMdBtn) exportMdBtn.addEventListener('click', () => exportCityScraperResults('markdown'));
});

