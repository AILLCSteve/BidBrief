// ============================================================================
// CIPP ANALYZER - CLEAN REBUILD FOR HOTDOG AI
// ============================================================================

// Global State
let currentFile = null;
let currentSessionId = null;
let currentAnalysisResult = null;
let currentKeyRequirements = null;  // Store key document details from analysis
let currentOptimizedScanData = null;  // Store optimized scan data from V2 pipeline
let currentUnansweredPassData = null;  // Store unanswered pass data from V2 pipeline
let currentRagData = null;  // Store RAG data from V2 pipeline
let activeEventSource = null;  // LEGACY: Kept for backward compatibility
let pollingInterval = null;  // NEW: Polling interval
let lastEventIndex = 0;  // NEW: Track which events we've already processed
let questionConfig = { sections: [], totalQuestions: 0 };
let liveAnswers = {}; // Store answers as they come in: { question_id: { question, answer, pages } }
let currentAnalysisMode = 'bid_spec';  // NEW: Analysis mode (bid_spec or bestprep)

// NEW: Unitary Table State
let allQuestions = {};  // { question_id: { section_name, question_text, status, answer, pages, footnote } }
let allFootnotes = [];  // Array of unique footnotes

// NEW: Question selection state for multi-pass processing
let selectedQuestionsForProcessing = new Set();  // User-selected for additional processing

// ============================================================================
// ANALYSIS MODE SELECTION
// ============================================================================

function setAnalysisMode(mode) {
    currentAnalysisMode = mode;
    Logger.info(`Analysis mode set to: ${mode}`);

    // Update UI styling
    const bidSpecLabel = document.getElementById('modeLabel_bid_spec');
    const bestprepLabel = document.getElementById('modeLabel_bestprep');
    const modeHint = document.getElementById('modeHint');

    if (mode === 'bestprep') {
        bidSpecLabel.style.borderColor = '#ddd';
        bestprepLabel.style.borderColor = '#28a745';
        modeHint.textContent = 'BestPrep: Every answer fragment preserved, synthesis at end';
        modeHint.style.color = '#22c55e';
    } else {
        bidSpecLabel.style.borderColor = '#28a745';
        bestprepLabel.style.borderColor = '#ddd';
        modeHint.textContent = isUserAdmin ? 'Bid/Spec: Smart deduplication, optimized for specs' : 'Contracts/RFPs/Spec: Optimized for contracts, bids, and large PDFs';
        modeHint.style.color = '#28a745';
    }
}

// ============================================================================
// LOGGER - Simple, Working
// ============================================================================

class Logger {
    static log(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logContainer = document.getElementById('logContent');
        const entry = document.createElement('div');
        entry.className = `log-entry log-${type}`;
        entry.textContent = `[${timestamp}] ${message}`;
        logContainer.appendChild(entry);
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    static info(msg) { this.log(msg, 'info'); }
    static success(msg) { this.log(msg, 'success'); }
    static error(msg) { this.log(msg, 'error'); }
    static warning(msg) { this.log(msg, 'warning'); }
}

// ============================================================================
// PROGRESS TRACKER
// ============================================================================

class ProgressTracker {
    static show() {
        document.getElementById('progressContainer').style.display = 'block';
    }

    static hide() {
        document.getElementById('progressContainer').style.display = 'none';
    }

    static update(percentage, text) {
        document.getElementById('progressFill').style.width = `${percentage}%`;
        document.getElementById('progressText').textContent = text;
    }
}

// ============================================================================
// UI UTILITIES
// ============================================================================

function toggleDebugTools() {
    const content = document.getElementById('debugToolsContent');
    const icon = document.getElementById('debugToggleIcon');

    if (content.style.display === 'none') {
        content.style.display = 'block';
        icon.textContent = '▼';
    } else {
        content.style.display = 'none';
        icon.textContent = '▶';
    }
}

// ============================================================================
// POLLING - Event Streaming (Replaces SSE)
// ============================================================================

function startPolling(sessionId) {
    // Stop any existing polling first (prevents multiple intervals)
    stopPolling();

    Logger.info(`📡 Starting event polling for session: ${sessionId}`);
    lastEventIndex = 0;  // Reset event counter

    // Poll immediately, then every 1 second
    pollForEvents();
    pollingInterval = setInterval(pollForEvents, 1000);
}

function stopPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
        Logger.info('📡 Stopped event polling');
    }
}

async function pollForEvents() {
    if (!currentSessionId) return;

    try {
        const resp = await fetch(`/api/events/${currentSessionId}?last_index=${lastEventIndex}`);
        const data = await resp.json();

        if (!data.success) {
            Logger.error('Polling failed: ' + (data.error || 'Unknown error'));
            return;
        }

        // Process new events
        if (data.events && data.events.length > 0) {
            console.log(`[POLLING] Received ${data.events.length} new events (total: ${data.total_events})`);
            data.events.forEach(event => handleEvent(event));
        }

        // Update last index
        lastEventIndex = data.last_index;

    } catch (error) {
        console.error('[POLLING] Error:', error);
        // Don't spam the log - polling will retry in 1 second
    }
}

function handleEvent(data) {
    // This function processes a single event (same logic as SSE onmessage)
    try {
        console.log('[EVENT] Processing:', data.event, data);

        // Route events to Logger with DETAILED logging
        if (data.event === 'connected') {
            Logger.success('✅ Progress stream connected');
            ProgressTracker.update(5, 'Connected to server');
        }
        else if (data.event === 'diagnostic_test') {
            Logger.info(`🔬 DIAGNOSTIC: Received test event`);
        }
        else if (data.event === 'analysis_started') {
            Logger.info(`🔥 HOTDOG AI analysis started for: ${data.document || 'document'}`);
            ProgressTracker.update(10, 'Analysis starting...');
        }
        else if (data.event === 'layer_0_start') {
            Logger.info(`📊 Layer 0: ${data.layer} - Starting PDF extraction...`);
            ProgressTracker.update(12, 'Reading PDF...');
        }
        else if (data.event === 'document_ingested') {
            Logger.success(`📄 Document ingested: ${data.total_pages} pages extracted`);
            Logger.info(`   ↳ Created ${data.window_count} windows (${data.window_size} pages each)`);
            ProgressTracker.update(20, `Extracted ${data.total_pages} pages`);
        }
        else if (data.event === 'layer_1_start') {
            Logger.info(`📊 Layer 1: ${data.layer} - Loading question configuration...`);
            ProgressTracker.update(22, 'Loading questions...');
        }
        else if (data.event === 'config_loaded') {
            Logger.success(`⚙️ Configuration loaded: ${data.total_questions} questions in ${data.section_count} sections`);
            if (data.sections) {
                Logger.info(`   ↳ Sections: ${data.sections.join(', ')}`);
            }
            ProgressTracker.update(25, `Loaded ${data.total_questions} questions`);
        }
        else if (data.event === 'layer_2_start') {
            Logger.info(`📊 Layer 2: ${data.layer} - Generating AI expert personas...`);
            ProgressTracker.update(27, 'Creating AI experts...');
        }
        else if (data.event === 'expert_generated') {
            Logger.info(`🤖 AI Expert created: ${data.expert_name}`);
            if (data.section) {
                Logger.info(`   ↳ Specialization: ${data.section}`);
            }
            ProgressTracker.update(30, `Generating experts...`);
        }
        else if (data.event === 'processing_start') {
            Logger.success(`🚀 Multi-expert processing started: ${data.total_windows} windows to analyze`);
            ProgressTracker.update(35, 'Starting window processing...');
        }
        else if (data.event === 'window_processing') {
            Logger.info(`🔍 Window ${data.window_num}/${data.total_windows}: Analyzing pages ${data.pages}`);
            const progress = 40 + ((data.window_num / data.total_windows) * 45);
            ProgressTracker.update(progress, `Window ${data.window_num}/${data.total_windows}`);
        }
        else if (data.event === 'experts_dispatched') {
            Logger.info(`   ↳ Dispatched ${data.expert_count} experts for ${data.question_count} questions`);
        }
        else if (data.event === 'experts_complete') {
            Logger.success(`   ↳ Experts returned ${data.answers_returned} answers`);
            Logger.info(`   ↳ Tokens used: ${data.tokens_used} | Cost: $${data.cost || '0.00'}`);
        }
        else if (data.event === 'window_complete') {
            const procTime = data.processing_time ? data.processing_time.toFixed(1) : '?';
            Logger.success(`✅ Window ${data.window_num || '?'} complete: ${data.answers_found || 0} answers found in ${procTime}s`);
            if (data.unitary_log) {
                Logger.info(`   ↳ ${data.unitary_log}`);
            }

            // NEW: Update unitary table with new answers (include stage for v2 pipeline)
            if (data.new_answers && data.new_answers.length > 0) {
                const stage = data.stage || 'classic';
                updateUnitaryTableWithNewAnswers(data.new_answers, stage);
            }
        }
        else if (data.event === 'progress_milestone') {
            Logger.info(`📊 Milestone: ${data.progress_summary}`);
        }
        else if (data.event === 'layer_6_start') {
            Logger.info(`📊 Layer 6: ${data.layer} - Compiling final output...`);
            ProgressTracker.update(90, 'Compiling results...');
        }
        else if (data.event === 'layer_6_complete') {
            Logger.success(`✅ Output compiled: ${data.questions_answered} questions answered`);
            ProgressTracker.update(90, 'Output compiled...');
        }
        else if (data.event === 'layer_7_start') {
            Logger.info(`📊 Layer 7: ${data.layer} - Synthesizing ${data.questions_to_synthesize} answers...`);
            ProgressTracker.update(92, 'Synthesizing answers...');
        }
        else if (data.event === 'layer_7_complete') {
            Logger.success(`✅ Synthesis complete: ${data.synthesized_count} answers synthesized`);
            ProgressTracker.update(95, 'Synthesis complete...');
        }
        // V2 Pipeline Lifecycle Events
        else if (data.event === 'pipeline_start') {
            Logger.info(`🚀 ${data.pipeline || 'HOTDOG7ATE'} Pipeline started`);
            if (data.stages) {
                Logger.info(`   ↳ Stages: ${data.stages.join(' → ')}`);
            }
            ProgressTracker.update(20, `Starting ${data.pipeline || 'HOTDOG7ATE'} Pipeline...`);
        }
        else if (data.event === 'pipeline_complete') {
            Logger.success(`✅ Pipeline complete!`);
            if (data.summary) {
                Logger.info(`   ↳ Stages completed: ${data.summary.stages_completed?.length || 0}`);
                Logger.info(`   ↳ Questions answered: ${data.summary.answered_questions || 0}/${data.summary.total_questions || 0}`);
            }
        }
        // Pre-scan Events (Document Navigator)
        else if (data.event === 'prescan_start') {
            Logger.info(`🗺️ Document Navigator analyzing structure...`);
            Logger.info(`   ↳ Pages: ${data.total_pages || 0}, Questions: ${data.total_questions || 0}, Experts: ${data.total_experts || 0}`);
            ProgressTracker.update(22, 'Analyzing document structure (TOC, index, headers)...');
        }
        else if (data.event === 'prescan_complete') {
            Logger.success(`✅ Document structure analyzed`);
            Logger.info(`   ↳ TOC: ${data.has_toc ? 'Found' : 'Not found'}, Index: ${data.has_index ? 'Found' : 'Not found'}`);
            if (data.expert_assignments && data.expert_assignments.length > 0) {
                data.expert_assignments.forEach(a => {
                    Logger.info(`   ↳ ${a.expert}: ${a.total_pages} pages targeted`);
                });
            }
            if (data.estimated_reduction) {
                Logger.info(`   ↳ Estimated scan reduction: ${data.estimated_reduction}`);
            }
            // Store optimized scan data for display in modal and export
            currentOptimizedScanData = {
                structure: {
                    has_toc: data.has_toc,
                    has_index: data.has_index,
                    has_appendix: data.has_appendix,
                    toc_entries_count: data.toc_entries,
                    index_terms_count: data.index_terms
                },
                expert_assignments: data.expert_assignments || [],
                all_keywords_by_section: data.all_keywords_by_section || {},
                estimated_reduction: data.estimated_reduction,
                unassigned_questions: data.unassigned_questions || []
            };
            ProgressTracker.update(25, 'Document structure mapped...');
        }
        // V2 Stage 1: Quick-Scan
        else if (data.event === 'stage_1_start' || (data.event === 'stage_start' && data.stage === 'optimized_scan')) {
            Logger.info(`🔍 Stage 1: Comprehensive Quick-Scan starting...`);
            Logger.info(`   ↳ ${data.questions_count || 0} questions to analyze`);
            ProgressTracker.update(28, 'Optimized Scan: Targeted extraction...');
        }
        else if (data.event === 'stage_1_complete' || (data.event === 'stage_complete' && data.stage === 'optimized_scan')) {
            Logger.success(`✅ Optimized Scan complete: ${data.high_confidence_count || data.answers_found || 0} high-confidence answers`);
            if (data.questions_for_exhaustive !== undefined) {
                Logger.info(`   ↳ ${data.questions_for_exhaustive} questions need exhaustive pass`);
            }
            ProgressTracker.update(40, 'Optimized Scan complete...');
        }
        // V2 Stage 2: Exhaustive Pass
        else if (data.event === 'stage_2_start' || (data.event === 'stage_start' && data.stage === 'exhaustive')) {
            Logger.info(`🔄 Exhaustive Analysis starting...`);
            Logger.info(`   ↳ ${data.questions_count || 0} questions, ${data.windows_count || 0} windows`);
            ProgressTracker.update(42, `Exhaustive: 0/${data.windows_count || 0} windows...`);
        }
        else if (data.event === 'stage_2_progress') {
            const pct = 42 + Math.round(((data.window || 0) / (data.total_windows || 1)) * 25);
            ProgressTracker.update(pct, `Exhaustive: Window ${data.window}/${data.total_windows} (${data.answers_so_far || 0} answers)...`);
        }
        else if (data.event === 'stage_2_complete' || (data.event === 'stage_complete' && data.stage === 'exhaustive')) {
            Logger.success(`✅ Exhaustive analysis complete: ${data.answers_found || 0} answers`);
            ProgressTracker.update(70, 'Exhaustive pass complete...');
        }
        // V2 Stage 3: Second Pass (Unanswered Only)
        else if (data.event === 'stage_3_start' || data.event === 'second_pass_start' || (data.event === 'stage_start' && data.stage === 'second_pass')) {
            Logger.info(`🔍 Second Pass: Enhanced scrutiny for unanswered...`);
            Logger.info(`   ↳ Targeting ${data.unanswered_count || 0} unanswered questions`);
            ProgressTracker.update(72, 'Second pass: Enhanced scrutiny...');
        }
        else if (data.event === 'stage_3_complete' || data.event === 'second_pass_complete' || (data.event === 'stage_complete' && data.stage === 'second_pass')) {
            Logger.success(`✅ Second pass complete: ${data.answers_found || 0} new answers`);
            if (data.still_unanswered > 0) {
                Logger.warn(`   ↳ Still unanswered: ${data.still_unanswered}`);
            }
            ProgressTracker.update(85, 'Second pass complete...');
        }
        // V2 Stage 4: Deep RAG
        else if (data.event === 'stage_4_start' || (data.event === 'stage_start' && data.stage === 'deep_rag')) {
            Logger.info(`🌐 Deep RAG: External search via TAVILY...`);
            Logger.info(`   ↳ Searching for ${data.questions_count || 0} questions`);
            ProgressTracker.update(87, 'Deep RAG: Searching external sources...');
        }
        else if (data.event === 'stage_4_complete' || (data.event === 'stage_complete' && data.stage === 'deep_rag')) {
            Logger.success(`✅ Deep RAG complete: ${data.answers_found || 0} external answers`);
            if (data.disclaimer) {
                Logger.warn(`   ↳ ${data.disclaimer}`);
            }
            ProgressTracker.update(92, 'Deep RAG complete...');
        }
        // Stage Pause Event (Interactive Pipeline)
        else if (data.event === 'stage_pause') {
            Logger.info(`⏸️ Pausing for user review: ${data.stage_name || 'Stage complete'}`);
            // Show pause modal for user interaction
            if (typeof showStagePauseModal === 'function') {
                showStagePauseModal(data);
            }
        }
        else if (data.event === 'recheck_start') {
            Logger.info(`🔄 Rechecking ${data.empty_window_count} empty windows...`);
            ProgressTracker.update(80, 'Rechecking empty windows...');
        }
        else if (data.event === 'recheck_complete') {
            Logger.success(`✅ Recheck complete: ${data.total_new_answers} additional answers from ${data.windows_rechecked} windows`);
            ProgressTracker.update(85, 'Recheck complete...');
        }
        // Key Document Details Events
        else if (data.event === 'key_requirements_start') {
            Logger.info(`🔑 Extracting Key Document Details...`);
            ProgressTracker.update(18, 'Extracting key document details...');
        }
        else if (data.event === 'key_requirements_complete') {
            Logger.success(`✅ Key Document Details extracted: ${data.count} items`);
            // Store key details for later use in modals
            if (data.requirements) {
                currentKeyRequirements = data.requirements;
            }
            ProgressTracker.update(20, 'Key document details extracted...');
        }
        else if (data.event === 'key_requirements_failed') {
            Logger.warning(`⚠️ Key document details extraction failed: ${data.error}`);
        }
        else if (data.event === 'results_ready') {
            // Store the complete result from polling (no need for separate fetch)
            // CRITICAL: Store just the result object, not the whole event wrapper
            currentAnalysisResult = data.result;
            // Also extract key requirements from result if available
            if (data.result && data.result.key_requirements) {
                currentKeyRequirements = data.result.key_requirements;
            }
            // Extract optimized scan data for V2 pipeline if available
            if (data.result && data.result.optimized_scan_data) {
                currentOptimizedScanData = data.result.optimized_scan_data;
                Logger.info(`📊 Quick scan data received (V2 pipeline)`);
            }
            Logger.info(`✅ Results received via polling (${data.result.sections?.length || 0} sections)`);
        }
        else if (data.event === 'analysis_complete' || data.event === 'done') {
            Logger.success(`🎉 HOTDOG AI analysis complete!`);
            if (data.statistics) {
                Logger.info(`   ↳ Questions answered: ${data.statistics.questions_answered}`);
                Logger.info(`   ↳ Processing time: ${data.statistics.processing_time}s`);
                Logger.info(`   ↳ Total cost: ${data.statistics.estimated_cost || 'N/A'}`);
            }
            ProgressTracker.update(100, 'Displaying results...');
            stopPolling();

            // Use result from polling instead of fetching
            if (currentAnalysisResult && currentAnalysisResult.sections) {
                displayResults(currentAnalysisResult);

                // CRITICAL: Update UI button states (fetchResults does this, but displayResults doesn't)
                // Without this, Stop button stays enabled and Export button stays disabled
                document.getElementById('exportBtn').disabled = false;
                document.getElementById('smartAnalysisBtn').disabled = false;
                document.getElementById('analyzeBtn').disabled = false;
                document.getElementById('stopBtn').disabled = true;
                ProgressTracker.hide();

                Logger.success('✅ Results displayed and UI updated');
            } else {
                // Fallback: fetch if results weren't in polling events
                fetchResults();
            }
        }
        else if (data.event === 'analysis_failed' || data.event === 'error') {
            const errorMsg = data.error || data.error_type || 'Unknown error';

            if (errorMsg === 'Analysis stopped by user') {
                Logger.warning(`⏹️ Analysis stopped by user`);
                Logger.info('📊 Fetching partial results...');
                stopPolling();
                fetchResults();
            } else {
                Logger.error(`❌ Analysis failed: ${errorMsg}`);
                stopPolling();
                throw new Error(errorMsg);
            }
        }
        else {
            // Log unknown events for debugging
            Logger.warning(`⚠️ Unknown event: ${data.event}`);
            console.log('Unknown event data:', data);
        }

    } catch (err) {
        Logger.error('Failed to process event: ' + err.message);
        console.error('Event processing error:', err, data);
    }
}

// ============================================================================
// FILE UPLOAD HANDLING
// ============================================================================

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    currentFile = file;

    document.getElementById('fileName').textContent = file.name;
    document.getElementById('fileSize').textContent = formatFileSize(file.size);
    document.getElementById('fileInfo').style.display = 'block';
    document.getElementById('analyzeBtn').disabled = false;

    Logger.info(`📄 PDF file selected: ${file.name} (${formatFileSize(file.size)})`);
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

// ============================================================================
// QUESTION CONFIGURATION LOADING
// ============================================================================

async function loadQuestionConfig() {
    try {
        const resp = await fetch('/api/config/questions');
        const data = await resp.json();

        if (!data.success) {
            throw new Error(data.error || 'Failed to load questions');
        }

        questionConfig = data.config;

        // Initialize 'enabled' field for all sections (default to true)
        questionConfig.sections.forEach(section => {
            if (section.enabled === undefined) {
                section.enabled = true;
            }
        });

        displayQuestionSections();
        updateActiveQuestionCount();

        Logger.success(`✅ Loaded ${questionConfig.totalQuestions} questions in ${questionConfig.sections.length} sections`);

    } catch (error) {
        Logger.error('Failed to load question configuration: ' + error.message);
    }
}

function displayQuestionSections() {
    const container = document.getElementById('questionSections');
    if (!questionConfig.sections || questionConfig.sections.length === 0) {
        container.innerHTML = '<p style="color: #888; font-size: 13px; margin: 8px 0;">No questions loaded. Click the button below to load or generate a question set.</p>';
        return;
    }
    container.innerHTML = questionConfig.sections.map(section => `
        <div class="question-section ${section.enabled ? 'enabled' : 'disabled'}"
             onclick="toggleSection('${section.section_id}')">
            <div class="section-header">
                <span>${section.section_name}</span>
                <span class="section-count">${section.questions.length}</span>
            </div>
        </div>
    `).join('');
}

function toggleSection(sectionId) {
    const section = questionConfig.sections.find(s => s.section_id === sectionId);
    if (section) {
        section.enabled = !section.enabled;
        displayQuestionSections();
        updateActiveQuestionCount();
    }
}

function updateActiveQuestionCount() {
    const count = questionConfig.sections
        .filter(s => s.enabled)
        .reduce((sum, s) => sum + s.questions.length, 0);

    document.getElementById('activeQuestionCount').textContent = count;
}

// ============================================================================
// ANALYSIS - Main Flow (CLEAN, SIMPLE SSE)
// ============================================================================

async function startAnalysis() {
    if (!currentFile) {
        Logger.error('Please upload a PDF file first');
        alert('Please upload a PDF file first');
        return;
    }

    try {
        Logger.info('🔥 Starting HOTDOG AI analysis...');

        const contextGuardrails = document.getElementById('contextGuardrails').value.trim();
        if (contextGuardrails) {
            Logger.info(`📋 Context Guardrails: ${contextGuardrails}`);
        }

        // Reset live answers
        liveAnswers = {};

        // Hide live summary
        document.getElementById('liveResults').style.display = 'none';

        // Disable/enable buttons
        document.getElementById('analyzeBtn').disabled = true;
        document.getElementById('stopBtn').disabled = false;

        // Show progress
        ProgressTracker.show();
        ProgressTracker.update(10, 'Uploading document...');

        // STEP 1: Upload PDF
        const formData = new FormData();
        formData.append('file', currentFile);

        const uploadResp = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });

        if (!uploadResp.ok) {
            throw new Error('File upload failed');
        }

        const uploadData = await uploadResp.json();
        const uploadId = uploadData.upload_id;
        const pdfFilename = uploadData.filename || currentFile.name;

        Logger.success(`✅ File uploaded: ${pdfFilename} (upload id: ${uploadId})`);
        ProgressTracker.update(20, 'Connecting to HOTDOG AI...');

        // STEP 2: Get enabled section IDs
        const enabledSectionIds = questionConfig.sections
            .filter(s => s.enabled)
            .map(s => s.section_id);

        Logger.info(`📊 Analyzing ${enabledSectionIds.length} enabled sections`);

        // STEP 3: Start analysis (returns immediately - runs in background)
        // NOTE: Server generates cryptographically secure session ID - we use the one returned
        const recheckEmpty = document.getElementById('recheckEmptyWindows').checked;
        const enableSecondPass = document.getElementById('enableSecondPass').checked;
        const enableDeepRAG = document.getElementById('enableDeepRAG').checked;
        const pipelineMode = document.querySelector('input[name="pipelineMode"]:checked').value;

        Logger.info(`📊 Analysis mode: ${currentAnalysisMode}, Pipeline: ${pipelineMode}`);
        Logger.info(`   Options: Recheck empty=${recheckEmpty}, Second pass=${enableSecondPass}, Deep RAG=${enableDeepRAG}`);

        const analyzeResp = await fetch('/api/analyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                upload_id: uploadId,
                pdf_filename: pdfFilename,  // Include original filename
                context_guardrails: contextGuardrails || undefined,
                enabled_sections: enabledSectionIds,  // Only analyze enabled sections
                mode: currentAnalysisMode,  // Analysis mode
                recheck_empty_windows: recheckEmpty,  // Retry windows with 0 answers
                enable_second_pass: enableSecondPass,  // Retry unanswered questions
                enable_deep_rag: enableDeepRAG,  // External search for remaining
                pipeline_mode: pipelineMode  // 'classic' or 'v2_pipeline'
            })
        });

        if (!analyzeResp.ok) {
            const errData = await analyzeResp.json().catch(() => ({}));
            throw new Error(errData.error || 'Analysis failed to start');
        }

        const analyzeData = await analyzeResp.json();

        // STEP 4: Use server-generated session ID and start polling
        currentSessionId = analyzeData.session_id;
        startPolling(currentSessionId);

        Logger.success(`✅ Analysis started in background (Session: ${currentSessionId})`);
        Logger.info(`📊 HOTDOG AI is now processing your document...`);

        // NOW initialize unitary table (after analysis successfully started)
        initializeUnitaryTableState();

    } catch (error) {
        Logger.error('Analysis failed: ' + error.message);
        alert('Analysis failed: ' + error.message);
        ProgressTracker.hide();
        document.getElementById('analyzeBtn').disabled = false;
        document.getElementById('stopBtn').disabled = true;
        stopPolling();  // NEW: Stop polling on error
    }
}

// ============================================================================
// FETCH RESULTS (Called when 'done' event received)
// ============================================================================

async function fetchResults(maxRetries = 5) {
    /**
     * Fetch analysis results with retry logic and exponential backoff.
     *
     * CRITICAL FIX: This function now retries with exponential backoff to handle
     * race conditions where /api/stop returns before session moves to partial_analyses.
     *
     * Retry schedule:
     * - Attempt 1: Immediate
     * - Attempt 2: Wait 500ms
     * - Attempt 3: Wait 1000ms
     * - Attempt 4: Wait 1500ms
     * - Attempt 5: Wait 2000ms
     * Total max wait: ~5 seconds
     *
     * See: STOP_ANALYSIS_RACE_CONDITION.md
     */
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            const resp = await fetch(`/api/results/${currentSessionId}`);
            const data = await resp.json();

            if (!data.success) {
                // Check if this is a "not found" error that we should retry
                if (data.error && data.error.includes('not found') && attempt < maxRetries) {
                    const waitMs = 500 * attempt;  // Exponential backoff
                    Logger.info(`⏳ Results not ready yet, retrying in ${waitMs}ms (attempt ${attempt}/${maxRetries})...`);
                    await new Promise(resolve => setTimeout(resolve, waitMs));
                    continue;  // Retry
                }
                throw new Error(data.error);
            }

            // Success! Display results
            currentAnalysisResult = data.result;
            const isPartial = data.partial || false;

            Logger.success(`✅ Results fetched successfully (attempt ${attempt})`);
            Logger.success(`Questions answered: ${data.statistics.questions_answered}/${data.statistics.total_questions}`);
            if (data.statistics.processing_time) {
                Logger.success(`Processing time: ${data.statistics.processing_time.toFixed(2)}s`);
            }

            // Update unitary table with final results (instead of separate display)
            updateUnitaryTableAsFinal(data.result, isPartial);

            // Enable export and smart analysis
            document.getElementById('exportBtn').disabled = false;
            document.getElementById('smartAnalysisBtn').disabled = false;

            ProgressTracker.hide();
            document.getElementById('analyzeBtn').disabled = false;
            document.getElementById('stopBtn').disabled = true;

            return;  // Success - exit function

        } catch (error) {
            if (attempt === maxRetries) {
                // Final attempt failed
                Logger.error(`❌ Failed to fetch results after ${maxRetries} attempts: ${error.message}`);
                Logger.error('Try refreshing the page or check analysis logs');
            }
            // Continue to next retry
        }
    }
}

// ============================================================================
// FETCH PARTIAL RESULTS (Live Updates)
// ============================================================================

async function fetchPartialResults() {
    try {
        Logger.info('📊 Fetching partial results...');
        const resp = await fetch(`/api/results/${currentSessionId}`);
        const data = await resp.json();

        if (data.success && data.result) {
            Logger.success(`✅ Partial results received - updating live display`);
            updateLiveSummary(data.result);
        } else {
            Logger.warning('⚠️ Partial results not ready yet');
        }
    } catch (error) {
        Logger.warning(`⚠️ Could not fetch partial results: ${error.message}`);
    }
}

// ============================================================================
// LIVE SUMMARY UPDATE - Shows actual answers as they're found
// ============================================================================

function updateLiveSummary(result) {
    const liveResultsDiv = document.getElementById('liveResults');
    const liveContent = document.getElementById('liveResultsContent');
    const resultsSection = document.getElementById('resultsSection');

    // Show sections
    resultsSection.style.display = 'block';
    liveResultsDiv.style.display = 'block';

    // Count answers
    let totalAnswers = 0;
    let totalQuestions = 0;

    result.sections.forEach(section => {
        section.questions.forEach(q => {
            totalQuestions++;
            if (q.answer && q.answer.trim()) {
                totalAnswers++;
            }
        });
    });

    // Build live table
    let html = `
        <div style="margin-bottom: 15px; padding: 12px; background: #f0f7ff; border-radius: 6px; border-left: 4px solid #5B7FCC;">
            <strong style="color: #1E3A8A;">Live Progress:</strong>
            <span style="color: #28a745; font-weight: 600;">${totalAnswers}</span> answers found
            (${totalQuestions} questions analyzed so far)
        </div>
        <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
            <thead>
                <tr style="background: #f8f9fa; color: #333;">
                    <th style="padding: 10px; text-align: left; border: 1px solid #ddd; width: 25%;">Question</th>
                    <th style="padding: 10px; text-align: left; border: 1px solid #ddd; width: 60%;">Answer Found</th>
                    <th style="padding: 10px; text-align: center; border: 1px solid #ddd; width: 15%;">PDF Pages</th>
                </tr>
            </thead>
            <tbody>
    `;

    result.sections.forEach(section => {
        section.questions.forEach(q => {
            if (q.answer && q.answer.trim()) {
                const pdfPages = (q.page_citations && q.page_citations.length > 0)
                    ? q.page_citations.join(', ')
                    : '—';

                html += `
                    <tr style="border-bottom: 1px solid #e0e0e0;">
                        <td style="padding: 8px; border: 1px solid #ddd; vertical-align: top; font-size: 12px;">
                            ${q.question}
                        </td>
                        <td style="padding: 8px; border: 1px solid #ddd; vertical-align: top; white-space: pre-wrap;">
                            ${q.answer.substring(0, 200)}${q.answer.length > 200 ? '...' : ''}
                        </td>
                        <td style="padding: 8px; border: 1px solid #ddd; text-align: center; vertical-align: top; font-weight: 600; color: #5B7FCC;">
                            ${pdfPages}
                        </td>
                    </tr>
                `;
            }
        });
    });

    html += `
            </tbody>
        </table>
        <p style="margin-top: 12px; color: #666; font-size: 12px; font-style: italic;">
            ⚡ Updating live as analysis progresses... Full results will display when complete.
        </p>
    `;

    liveContent.innerHTML = html;
}

// ============================================================================
// DISPLAY RESULTS (LEGACY TABLE FORMAT)
// ============================================================================

function displayResults(result) {
    const resultsSection = document.getElementById('resultsSection');
    const resultsContent = document.getElementById('resultsContent');
    const liveResultsDiv = document.getElementById('liveResults');

    if (!result || !result.sections) {
        Logger.error('No results to display');
        return;
    }

    // Hide live summary, show final results
    liveResultsDiv.style.display = 'none';

    let html = '<div style="background: white; padding: 20px; border-radius: 8px; overflow-x: auto;">';

    html += `
        <h2 style="color: #1E3A8A; margin-bottom: 20px;">Analysis Results</h2>
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
            <thead>
                <tr style="background: linear-gradient(135deg, #1E3A8A, #5B7FCC); color: white;">
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd; min-width: 180px;">Section</th>
                    <th style="padding: 12px; text-align: center; border: 1px solid #ddd; width: 40px;">#</th>
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd; min-width: 250px;">Question</th>
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd; min-width: 300px;">Answer</th>
                    <th style="padding: 12px; text-align: center; border: 1px solid #ddd; width: 100px;">PDF Pages</th>
                </tr>
            </thead>
            <tbody>
    `;

    // Populate table rows
    result.sections.forEach(section => {
        section.questions.forEach((q, index) => {
            const questionNumber = index + 1;
            const answer = q.answer || '<em style="color: #999;">Not found in document</em>';
            const pdfPages = (q.page_citations && q.page_citations.length > 0)
                ? q.page_citations.join(', ')
                : '—';

            html += `
                <tr style="border-bottom: 1px solid #e0e0e0;">
                    <td style="padding: 10px; border: 1px solid #ddd; vertical-align: top; background: #f8f9fa;">
                        <strong>${section.section_name}</strong>
                    </td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: center; vertical-align: top;">
                        ${questionNumber}
                    </td>
                    <td style="padding: 10px; border: 1px solid #ddd; vertical-align: top;">
                        ${q.question}
                    </td>
                    <td style="padding: 10px; border: 1px solid #ddd; vertical-align: top; white-space: pre-wrap;">
                        ${answer}
                    </td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: center; vertical-align: top; font-weight: 600; color: #5B7FCC;">
                        ${pdfPages}
                    </td>
                </tr>
            `;
        });
    });

    html += `
            </tbody>
        </table>
    </div>`;

    resultsContent.innerHTML = html;
    resultsSection.style.display = 'block';
}

// ============================================================================
// STOP ANALYSIS
// ============================================================================

async function stopAnalysis() {
    if (!currentSessionId) {
        Logger.warning('No active analysis to stop');
        return;
    }

    try {
        const resp = await fetch(`/api/stop/${currentSessionId}`, {
            method: 'POST'
        });

        const data = await resp.json();

        if (data.success) {
            Logger.warning('⏹️ Analysis stopped by user');
            stopPolling();  // NEW: Stop polling instead of closing SSE
            document.getElementById('stopBtn').disabled = true;
            document.getElementById('analyzeBtn').disabled = false;

            // Fetch partial results
            fetchResults();
        }

    } catch (error) {
        Logger.error('Failed to stop analysis: ' + error.message);
    }
}

// ============================================================================
// EXPORT FUNCTIONS
// ============================================================================

function showExportMenu() {
    const menu = document.getElementById('exportMenu');
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

function exportResults(format) {
    if (!currentAnalysisResult) {
        alert('No results to export');
        return;
    }

    Logger.info(`📤 Exporting as ${format}...`);

    if (format === 'json') {
        downloadJSON(currentAnalysisResult, 'bidbrief_analysis.json');
    }
    else if (format === 'csv') {
        downloadCSV(currentAnalysisResult);
    }
    else if (format === 'excel-simple') {
        // Use server-side Excel Report Package export
        exportExcelDashboard();
    }
    else if (format === 'html') {
        exportHTML(currentAnalysisResult);
    }

    document.getElementById('exportMenu').style.display = 'none';
}

function downloadJSON(data, filename) {
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
}

function downloadCSV(data) {
    let csv = 'Section,#,Question,Answer,Answer Summary,PDF Pages\n';

    data.sections.forEach(section => {
        section.questions.forEach((q, index) => {
            const answer = q.answer ? q.answer.replace(/"/g, '""') : 'Not found';
            const summary = q.answer_summary ? q.answer_summary.replace(/"/g, '""') : '';
            const pages = q.page_citations ? q.page_citations.join(';') : '';
            csv += `"${section.section_name}","${index + 1}","${q.question}","${answer}","${summary}","${pages}"\n`;
        });
    });

    const blob = new Blob([csv], {type: 'text/csv'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cipp_analysis.csv';
    a.click();
}

function exportExcelDashboard() {
    /**
     * Export using server-side Excel generator.
     * Uses mode-appropriate endpoint:
     * - bid_spec: 4-sheet Report Package (Executive Summary, Detailed, By Section, Footnotes)
     * - bestprep: 5-sheet Comprehensive Report (Summary, Synthesized, Fragments, Footnotes, Page Index)
     */
    if (!currentSessionId) {
        Logger.error('No session ID available for export');
        alert('No analysis session available. Please run an analysis first.');
        return;
    }

    Logger.info(`📊 Requesting Excel export for session: ${currentSessionId} (mode: ${currentAnalysisMode})`);

    // Use mode-appropriate export endpoint
    if (currentAnalysisMode === 'bestprep') {
        window.open(`/api/export/bestprep-excel/${currentSessionId}`, '_blank');
        Logger.success('✅ BestPrep Excel export initiated (5-sheet comprehensive report)');
    } else {
        window.open(`/api/export/excel-dashboard/${currentSessionId}`, '_blank');
        Logger.success('✅ Excel Report Package export initiated');
    }
}

function exportHTML(data) {
    let html = `<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>CIPP Analysis Report</title>
    <style>
        body { font-family: Calibri, Arial, sans-serif; font-size: 15pt; margin: 40px; }
        h1 { color: #1E3A8A; border-bottom: 4px solid #5B7FCC; padding-bottom: 15px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th { background: #1E3A8A; color: white; padding: 12px; text-align: left; }
        td { padding: 10px; border: 1px solid #ddd; }
    </style>
</head>
<body>
    <h1>Document Analysis Results</h1>
    <p>Generated: ${new Date().toLocaleString()}</p>
    <table>
        <thead>
            <tr>
                <th>Section</th>
                <th>#</th>
                <th>Question</th>
                <th>Answer</th>
                <th>Answer Summary</th>
                <th>PDF Pages</th>
            </tr>
        </thead>
        <tbody>
`;

    data.sections.forEach(section => {
        section.questions.forEach((q, index) => {
            html += `<tr>
                <td>${section.section_name}</td>
                <td>${index + 1}</td>
                <td>${q.question}</td>
                <td>${q.answer || 'Not found in document'}</td>
                <td>${q.answer_summary || ''}</td>
                <td>${q.page_citations ? q.page_citations.join(', ') : ''}</td>
            </tr>`;
        });
    });

    html += `
        </tbody>
    </table>
</body>
</html>`;

    const blob = new Blob([html], {type: 'text/html'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cipp_analysis_report.html';
    a.click();
    Logger.success('✅ HTML report downloaded');
}

// ============================================================================
// CLEAR RESULTS
// ============================================================================

function clearResults() {
    document.getElementById('resultsSection').style.display = 'none';
    document.getElementById('resultsContent').innerHTML = '';
    document.getElementById('logContent').innerHTML = '';
    document.getElementById('exportBtn').disabled = true;
    document.getElementById('smartAnalysisBtn').disabled = true;
    document.getElementById('smartAnalysisOutput').style.display = 'none';
    document.getElementById('smartAnalysisOutput').innerHTML = '';
    document.getElementById('smartAnalysisStatus').textContent = '';
    currentAnalysisResult = null;
    currentSessionId = null;
    ProgressTracker.hide();
    Logger.info('🗑️ Results cleared');
}

// ============================================================================
// SMART ANALYSIS
// ============================================================================

async function runSmartAnalysis() {
    if (!currentSessionId) {
        document.getElementById('smartAnalysisStatus').textContent = 'No active session — run an analysis first.';
        return;
    }

    const btn = document.getElementById('smartAnalysisBtn');
    const statusEl = document.getElementById('smartAnalysisStatus');
    const outputEl = document.getElementById('smartAnalysisOutput');
    const userInput = (document.getElementById('smartAnalysisInput').value || '').trim();

    btn.disabled = true;
    btn.textContent = '🧠 Running Smart Analysis...';
    statusEl.textContent = 'Smart Analysis is underway...';
    outputEl.style.display = 'none';
    outputEl.innerHTML = '';

    try {
        const resp = await fetch(`/api/smart-analysis/${currentSessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_input: userInput }),
        });
        const data = await resp.json();
        if (!resp.ok || !data.success) {
            throw new Error(data.error || `HTTP ${resp.status}`);
        }
        statusEl.textContent = '';
        outputEl.style.display = 'block';
        outputEl.innerHTML = renderSmartAnalysisResult(data.result);
    } catch (e) {
        statusEl.textContent = `Smart Analysis failed: ${e.message}`;
        Logger.error(`Smart Analysis error: ${e.message}`);
    } finally {
        btn.disabled = false;
        btn.textContent = '🧠 BidBrief Smart Analysis';
    }
}

function renderSmartAnalysisResult(r) {
    const sev = {
        critical: { bg: '#DC2626', fg: '#fff' },
        high:     { bg: '#EF4444', fg: '#fff' },
        medium:   { bg: '#F59E0B', fg: '#1F2937' },
        low:      { bg: '#22C55E', fg: '#fff' },
        info:     { bg: '#3B82F6', fg: '#fff' },
    };

    function badge(severity) {
        const s = sev[severity] || sev.medium;
        return `<span style="background:${s.bg};color:${s.fg};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;text-transform:uppercase;">${severity}</span>`;
    }

    function itemsHTML(items) {
        if (!items || !items.length) return '<p style="color:#888;font-size:13px;">None identified.</p>';
        return items.map(it => {
            const fud = it.follow_up_direction || {};
            // Support both v3 multi-step fields and v2 legacy fields
            const hasV3 = fud.what_to_ask || fud.why_unclear || fud.verification_step;
            const hasV2 = fud.action;
            const fudHTML = (hasV3 || hasV2) ? `
                <div style="margin-top:8px;padding:8px 10px;background:#f0f9ff;border-left:3px solid #3B82F6;border-radius:4px;font-size:12px;color:#1e40af;">
                    ${hasV3 ? `
                    ${fud.why_unclear ? `<div style="margin-bottom:3px;"><strong>Why unclear:</strong> ${fud.why_unclear}</div>` : ''}
                    ${fud.verification_step ? `<div style="margin-bottom:3px;"><strong>Check first:</strong> ${fud.verification_step}</div>` : ''}
                    ${fud.what_to_ask ? `<div style="margin-bottom:3px;"><strong>Ask:</strong> &ldquo;${fud.what_to_ask}&rdquo;</div>` : ''}
                    ${fud.who_to_ask ? `<div style="margin-bottom:3px;"><strong>Who:</strong> ${fud.who_to_ask}</div>` : ''}
                    ${fud.where_to_look ? `<div><strong>Where:</strong> ${fud.where_to_look}</div>` : ''}
                    ` : `
                    <strong>Follow-up:</strong> ${fud.action}
                    ${fud.target ? ` &rarr; <em>${fud.target}</em>` : ''}
                    ${fud.specific_question ? `<div style="margin-top:3px;color:#1e3a8a;">&ldquo;${fud.specific_question}&rdquo;</div>` : ''}
                    `}
                </div>` : '';
            return `
            <div style="border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;margin-bottom:10px;background:#fff;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                    ${badge(it.severity)}
                    <strong style="font-size:14px;color:#1e293b;">${it.title}</strong>
                </div>
                <p style="margin:0 0 6px;font-size:13px;color:#374151;">${it.description}</p>
                ${it.evidence && it.evidence.length ? `<ul style="margin:4px 0 0 16px;padding:0;font-size:12px;color:#64748b;">${it.evidence.map(e=>`<li>${e}</li>`).join('')}</ul>` : ''}
                ${fudHTML}
            </div>`;
        }).join('');
    }

    function section(title, content) {
        return `
        <div style="margin-bottom:20px;">
            <h4 style="margin:0 0 10px;padding:8px 14px;background:#1E3A8A;color:#fff;border-radius:6px;font-size:14px;">${title}</h4>
            ${content}
        </div>`;
    }

    const assessmentsHTML = (r.assessments || []).map(a => `
        <div style="display:flex;gap:10px;padding:8px 12px;background:#eff6ff;border-radius:6px;margin-bottom:6px;font-size:13px;">
            <strong style="min-width:160px;color:#1e40af;">${a.category}</strong>
            <span><strong>${a.rating}</strong> — ${a.rationale} <em style="color:#64748b;">(confidence: ${a.confidence})</em></span>
        </div>`).join('');

    const insightsHTML = (r.key_insights || []).map((ins, i) => `
        <div style="padding:8px 12px;background:${i%2?'#f1f5f9':'#fff'};border-radius:6px;margin-bottom:4px;font-size:13px;">${i+1}. ${ins}</div>`).join('');

    const userQHTML = (r.user_question_responses || []).length ? `
        ${section('Your Questions', (r.user_question_responses).map(q => {
            const fud = q.follow_up_direction || {};
            const fudHTML = fud.action ? `
                <div style="margin-top:8px;padding:6px 10px;background:#f0f9ff;border-left:3px solid #3B82F6;border-radius:4px;font-size:11px;color:#1e40af;">
                    <strong>Follow-up:</strong> ${fud.action}${fud.target ? ` &rarr; ${fud.target}` : ''}
                    ${fud.specific_question ? `<div style="margin-top:2px;">&ldquo;${fud.specific_question}&rdquo;</div>` : ''}
                </div>` : '';
            return `
            <div style="border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;margin-bottom:8px;background:#fff;">
                <p style="margin:0 0 6px;font-weight:700;font-size:13px;color:#1e293b;">${q.question}</p>
                <p style="margin:0 0 4px;font-size:13px;color:#374151;">${q.response}</p>
                <span style="font-size:11px;color:#64748b;">Confidence: ${q.confidence}</span>
                ${fudHTML}
            </div>`;
        }).join(''))}` : '';

    const recsHTML = (r.strategic_recommendations || []).map((rec, i) =>
        `<div style="display:flex;gap:10px;padding:8px 12px;background:${i%2?'#f1f5f9':'#fff'};border-radius:6px;margin-bottom:4px;font-size:13px;"><span style="min-width:22px;font-weight:700;color:#1e40af;">${i+1}.</span><span>${rec}</span></div>`).join('');

    const followHTML = (r.follow_up_questions || []).map((q, i) =>
        `<div style="display:flex;gap:10px;padding:8px 12px;background:${i%2?'#f1f5f9':'#fff'};border-radius:6px;margin-bottom:4px;font-size:13px;"><span style="min-width:22px;color:#64748b;">${i+1}.</span><span>${q}</span></div>`).join('');

    const completeness = r.analysis_completeness === 'partial'
        ? '<span style="background:#F59E0B;color:#1F2937;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;">PARTIAL ANALYSIS</span>'
        : '<span style="background:#22C55E;color:#fff;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;">FULL ANALYSIS</span>';

    return `
    <div class="section" style="background:#f8fafc;border:2px solid #1E3A8A;border-radius:10px;padding:20px;">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:10px;margin-bottom:18px;">
            <div>
                <h3 style="margin:0 0 4px;color:#1E3A8A;font-size:16px;">🧠 BidBrief Smart Analysis</h3>
                <p style="margin:0;font-size:12px;color:#64748b;">${r.document_name} &bull; ${completeness}</p>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <button class="btn btn-secondary" onclick="downloadSmartExcel()" style="font-size:12px;padding:6px 12px;">📊 Excel</button>
                <button class="btn btn-secondary" onclick="downloadSmartPDF()" style="font-size:12px;padding:6px 12px;">📄 PDF</button>
            </div>
        </div>

        ${r.document_understanding && r.document_understanding.document_overview ? section('Document Overview', `
            <div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;font-size:13px;">
                <p style="margin:0 0 10px;color:#374151;line-height:1.6;">${r.document_understanding.document_overview}</p>
                ${r.document_understanding.major_workstreams && r.document_understanding.major_workstreams.length ? `
                <div style="margin-bottom:8px;"><strong style="color:#1e40af;">Major Workstreams:</strong>
                <ul style="margin:4px 0 0 16px;padding:0;color:#374151;">${r.document_understanding.major_workstreams.map(w=>`<li>${w}</li>`).join('')}</ul></div>` : ''}
                ${r.document_understanding.key_obligations && r.document_understanding.key_obligations.length ? `
                <div style="margin-bottom:8px;"><strong style="color:#1e40af;">Key Obligations:</strong>
                <ul style="margin:4px 0 0 16px;padding:0;color:#374151;">${r.document_understanding.key_obligations.map(o=>`<li>${o}</li>`).join('')}</ul></div>` : ''}
                ${r.document_understanding.key_constraints && r.document_understanding.key_constraints.length ? `
                <div style="margin-bottom:8px;"><strong style="color:#1e40af;">Key Constraints:</strong>
                <ul style="margin:4px 0 0 16px;padding:0;color:#374151;">${r.document_understanding.key_constraints.map(c=>`<li>${c}</li>`).join('')}</ul></div>` : ''}
                ${r.document_understanding.structural_organization ? `
                <div style="color:#64748b;font-size:12px;font-style:italic;">${r.document_understanding.structural_organization}</div>` : ''}
            </div>`) : ''}
        ${r.assessments && r.assessments.length ? section('Professional Assessments', assessmentsHTML) : ''}
        ${r.executive_summary ? section('Executive Summary', `<p style="font-size:13px;line-height:1.7;color:#374151;white-space:pre-wrap;">${r.executive_summary}</p>`) : ''}
        ${r.key_insights && r.key_insights.length ? section('Key Insights', insightsHTML) : ''}
        ${userQHTML}
        ${r.risks && r.risks.length ? section('Risks', itemsHTML(r.risks)) : ''}
        ${r.opportunities && r.opportunities.length ? section('Opportunities', itemsHTML(r.opportunities)) : ''}
        ${r.ambiguities && r.ambiguities.length ? section('Ambiguities', itemsHTML(r.ambiguities)) : ''}
        ${r.contradictions && r.contradictions.length ? section('Contradictions', itemsHTML(r.contradictions)) : ''}
        ${recsHTML ? section('Strategic Recommendations', recsHTML) : ''}
        ${followHTML ? section('Follow-Up Questions', followHTML) : ''}
        ${r.evidence_classification && r.evidence_classification.confirmed_present_used && r.evidence_classification.confirmed_present_used.length ? section('Evidence Classification',
            `<div style="font-size:12px;color:#475569;">
                ${r.evidence_classification.confirmed_present_used && r.evidence_classification.confirmed_present_used.length ?
                    `<div style="margin-bottom:8px;"><strong style="color:#16a34a;">Confirmed Present:</strong> ${r.evidence_classification.confirmed_present_used.join(', ')}</div>` : ''}
                ${r.evidence_classification.confirmed_absent_flagged && r.evidence_classification.confirmed_absent_flagged.length ?
                    `<div style="margin-bottom:8px;"><strong style="color:#dc2626;">Confirmed Absent:</strong> ${r.evidence_classification.confirmed_absent_flagged.join(', ')}</div>` : ''}
                ${r.evidence_classification.unverified_flagged && r.evidence_classification.unverified_flagged.length ?
                    `<div style="margin-bottom:8px;"><strong style="color:#d97706;">Unverified/Partial:</strong> ${r.evidence_classification.unverified_flagged.join(', ')}</div>` : ''}
                ${r.evidence_classification.language_tiers_applied ?
                    `<div style="margin-bottom:4px;color:#475569;"><em>${r.evidence_classification.language_tiers_applied}</em></div>` : ''}
            </div>`
        ) : ''}
    </div>`;
}

function downloadSmartExcel() {
    if (!currentSessionId) return;
    window.location.href = `/api/smart-analysis/${currentSessionId}/export/excel`;
}

function downloadSmartPDF() {
    if (!currentSessionId) return;
    window.location.href = `/api/smart-analysis/${currentSessionId}/export/pdf`;
}

// ============================================================================
// ADMIN CHECK AND ADVANCED OPTIONS
// ============================================================================

let isUserAdmin = false;

async function checkAdminStatus() {
    try {
        const response = await fetch('/api/user/info');
        const data = await response.json();
        if (data.success && data.is_admin) {
            isUserAdmin = true;
            // Show Advanced Options section for admins
            document.getElementById('advancedOptionsSection').style.display = 'block';
            // Show BestPrep mode option for admins
            document.getElementById('modeLabel_bestprep').style.display = 'flex';
            // Show CityScraper tab for admins
            const cityscraperTabBtn = document.getElementById('cityscraperTabBtn');
            if (cityscraperTabBtn) {
                cityscraperTabBtn.style.display = 'inline-block';
            }
            // Restore admin-facing labels
            document.getElementById('bidSpecModeLabel').textContent = 'Bid/Spec/RFP Mode';
            document.getElementById('bidSpecModeDesc').textContent = 'Smart deduplication, merge similar answers. Best for construction bid specs and RFPs.';
            document.getElementById('modeHint').textContent = 'Bid/Spec: Smart deduplication, optimized for specs';
            // Pre-load question config so sections display on load
            loadQuestionConfig();
            Logger.info('🔐 Admin access granted - Advanced Options, BestPrep & CityScraper available');
        } else {
            isUserAdmin = false;
            // Keep hidden for non-admins
            document.getElementById('advancedOptionsSection').style.display = 'none';
            document.getElementById('modeLabel_bestprep').style.display = 'none';
            // Hide CityScraper tab for non-admins
            const cityscraperTabBtn = document.getElementById('cityscraperTabBtn');
            if (cityscraperTabBtn) {
                cityscraperTabBtn.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Failed to check admin status:', error);
        isUserAdmin = false;
    }
}

function toggleAdvancedOptions() {
    if (!isUserAdmin) {
        return; // Non-admins cannot toggle
    }
    const content = document.getElementById('advancedOptionsContent');
    const icon = document.getElementById('advancedToggleIcon');

    if (content.style.display === 'none') {
        content.style.display = 'block';
        icon.style.transform = 'rotate(90deg)';
    } else {
        content.style.display = 'none';
        icon.style.transform = 'rotate(0deg)';
    }
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    Logger.info('🚀 BidBrief initialized (HOTDOG AI)');
    Logger.info('✅ Ready for document analysis');

    // Check admin status to show/hide Advanced Options
    checkAdminStatus();

    // Show empty state for question sections on load
    displayQuestionSections();
    updateActiveQuestionCount();

    // Setup file input
    document.getElementById('fileInput').addEventListener('change', handleFileSelect);

    // Setup drag-and-drop
    const dropZone = document.getElementById('fileUpload');

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#5b7fcc';
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.style.borderColor = '#ddd';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = '#ddd';

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            document.getElementById('fileInput').files = files;
            handleFileSelect({target: {files: files}});
        }
    });
});

