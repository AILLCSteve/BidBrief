// ============================================================================
// UNITARY TABLE FUNCTIONS - Live Analysis Display
// ============================================================================

function initializeUnitaryTableState() {
    allQuestions = {};
    allFootnotes = [];

    if (!questionConfig || !questionConfig.sections) {
        Logger.warning('Question config not loaded yet');
        return;
    }

    // Build master question registry with ONLY ENABLED questions from ENABLED sections
    // This ensures statistics reflect actual questions being analyzed
    questionConfig.sections.filter(s => s.enabled).forEach(section => {
        // Filter to only enabled questions within the section
        const enabledQuestions = section.questions.filter(q => q.enabled !== false);
        enabledQuestions.forEach((q, idx) => {
            allQuestions[q.id] = {
                question_id: q.id,
                section_name: section.section_name,
                question_number: idx + 1,
                question_text: q.text,
                status: 'pending',  // pending | found
                answer: null,
                pages: [],
                footnote: null
            };
        });
    });

    Logger.info(`📊 Initialized unitary table: ${Object.keys(allQuestions).length} questions`);

    // Render initial table with all pending questions
    renderUnitaryTable();
}

function updateUnitaryTableWithNewAnswers(newAnswers, stage = 'classic') {
    const updatedQuestionIds = [];

    // Stage labels and colors for v2 pipeline display
    const stageLabels = {
        'optimized_scan': 'Quick-Scan',
        'exhaustive': 'Exhaustive',
        'second_pass': 'Second Pass',
        'deep_rag': 'Deep RAG',
        'classic': ''  // No badge for classic mode
    };

    const stageColors = {
        'optimized_scan': '#8b5cf6',  // Purple
        'exhaustive': '#3b82f6',  // Blue
        'second_pass': '#f59e0b', // Amber
        'deep_rag': '#10b981',    // Green
        'classic': '#6b7280'      // Gray (unused - no badge)
    };

    newAnswers.forEach(answer => {
        if (allQuestions[answer.question_id]) {
            const q = allQuestions[answer.question_id];
            q.status = 'found';

            // BestPrep mode with cumulative data from backend
            if (currentAnalysisMode === 'bestprep' && answer.is_cumulative) {
                // Data is already cumulative from backend - use directly
                q.answer = answer.answer_text;
                q.pages = answer.pages;
                q.footnote = answer.footnote;
                q.fragment_count = answer.fragment_count || 1;
            } else {
                // Bid/Spec mode: Replace behavior (existing)
                q.answer = answer.answer_text;
                q.answer_summary = answer.answer_summary || q.answer_summary || null;
                q.pages = answer.pages;
                q.footnote = answer.footnote;
            }

            // Store stage info for display (v2 pipeline only)
            if (stage !== 'classic') {
                q.stage = stage;
                q.stageLabel = stageLabels[stage] || stage;
                q.stageColor = stageColors[stage] || '#6b7280';
            }

            updatedQuestionIds.push(answer.question_id);

            // Add footnote to global list if it exists and is not empty
            if (answer.footnote && answer.footnote.trim()) {
                if (!allFootnotes.includes(answer.footnote)) {
                    allFootnotes.push(answer.footnote);
                }
            }
        }
    });

    // Update only the changed rows for efficiency
    updateUnitaryTableRows(updatedQuestionIds);

    // Log with stage info for v2 pipeline
    const stageInfo = stage !== 'classic' ? ` [${stageLabels[stage] || stage}]` : '';
    Logger.info(`📊 Updated ${updatedQuestionIds.length} questions in unitary table${stageInfo}`);
}

function updateUnitaryTableAsFinal(result, isPartial) {
    /**
     * Update unitary table with final/complete results
     * Called when analysis completes or is stopped
     *
     * IMPORTANT: For BestPrep mode, we preserve live accumulated data and only
     * update from final results if they have MORE information (not less).
     */
    Logger.info('📊 Updating unitary table with final results...');

    // Update allQuestions state from final result
    result.sections.forEach(section => {
        section.questions.forEach(q => {
            const questionId = q.question_id;
            if (allQuestions[questionId]) {
                const existing = allQuestions[questionId];

                // For BestPrep mode: DON'T overwrite existing live data with empty/less data
                // Only update if final has actual data OR existing is empty
                if (currentAnalysisMode === 'bestprep') {
                    // Only update if final result has an answer
                    if (q.answer && q.answer.trim()) {
                        existing.status = 'found';
                        existing.answer = q.synthesized_answer || q.answer;
                        // Merge pages (keep all accumulated + any new from final)
                        const finalPages = q.page_citations || [];
                        const allPages = [...new Set([...(existing.pages || []), ...finalPages])].sort((a,b) => a-b);
                        existing.pages = allPages;
                    }
                    // Preserve existing footnote if final is empty
                    if (q.footnote && q.footnote.trim()) {
                        existing.footnote = q.footnote;
                    }
                    // Preserve fragment count
                    if (q.fragment_count) {
                        existing.fragment_count = q.fragment_count;
                    }
                } else {
                    // Bid/Spec mode: Standard replace behavior
                    existing.status = q.answer ? 'found' : 'pending';
                    existing.answer = q.answer || null;
                    existing.answer_summary = q.answer_summary || null;
                    existing.pages = q.page_citations || [];
                    existing.footnote = q.footnote || null;
                }

                // Add footnote to global list if not already there
                if (q.footnote && q.footnote.trim() && !allFootnotes.includes(q.footnote)) {
                    allFootnotes.push(q.footnote);
                }
            }
        });
    });

    // Add completion banner to results container
    const container = document.getElementById('resultsContent');
    const bannerColor = isPartial ? '#FFA500' : '#4CAF50';
    const bannerIcon = isPartial ? '⚠️' : '✅';
    const bannerText = isPartial ? 'Partial Results (Analysis Stopped)' : 'Analysis Complete';

    const banner = `
        <div style="background: ${bannerColor}; color: white; padding: 12px 20px; margin-bottom: 15px; border-radius: 6px; font-weight: 600; text-align: center;">
            ${bannerIcon} ${bannerText}
        </div>
    `;

    // Re-render unitary table (will include the data updates)
    renderUnitaryTable();

    // Prepend banner to container
    container.innerHTML = banner + container.innerHTML;

    Logger.success(`✅ Final results display updated${isPartial ? ' (partial)' : ''}`);
}

function renderUnitaryTable() {
    const container = document.getElementById('resultsContent');
    const resultsSection = document.getElementById('resultsSection');
    resultsSection.style.display = 'block';

    const questionsList = Object.values(allQuestions);
    const answeredCount = questionsList.filter(q => q.status === 'found').length;
    const totalCount = questionsList.length;
    const totalFragments = questionsList.reduce((sum, q) => sum + (q.fragment_count || 0), 0);

    let html = `
        <div style="background: white; padding: 20px; border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h3 style="color: #1E3A8A; margin: 0;">📊 Unitary Log - Live Analysis</h3>
                <button onclick="openViewModal()" style="background: linear-gradient(135deg, #1E3A8A, #5B7FCC); color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;">
                    View
                </button>
            </div>

            <!-- Progress Stats -->
            <div class="unitary-stats" style="background: #f0f4ff; padding: 15px; border-radius: 6px; margin-bottom: 20px;">
                <div style="font-weight: 600; color: #1E3A8A;">
                    Answered: ${answeredCount}/${totalCount} questions (${((answeredCount/totalCount)*100).toFixed(1)}%)
                </div>
                <div style="margin-top: 5px; color: #666;">
                    Footnotes: ${allFootnotes.length}${currentAnalysisMode === 'bestprep' ? ` | Fragments: ${totalFragments}` : ''}
                </div>
            </div>

            <!-- Selection Actions Panel (hidden until selections made) -->
            <div id="selectionActionsPanel" style="background: #fff3cd; padding: 15px; border-radius: 6px; margin-bottom: 20px; display: none;">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                    <div>
                        <strong style="color: #856404;">📋 <span id="selectionSummary">0 questions selected</span></strong>
                    </div>
                    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
                        <button onclick="runSecondPassOnSelected()" style="background: #1E3A8A; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                            🔄 Run Second Pass
                        </button>
                        <button onclick="runRAGOnSelected()" style="background: #047857; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                            🔍 Run Deep RAG
                        </button>
                        <button onclick="clearQuestionSelection()" style="background: #6b7280; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px;">
                            ✕ Clear
                        </button>
                    </div>
                </div>
            </div>

            <!-- Unitary Table -->
            <div style="overflow-x: auto;">
                <table class="unitary-table" style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <thead>
                        <tr style="background: #1E3A8A; color: white;">
                            <th style="padding: 12px; text-align: center; border: 1px solid #ddd; width: 40px;">
                                <input type="checkbox" id="selectAllQuestions" onchange="toggleAllQuestionSelection(this)" title="Select all for additional processing">
                            </th>
                            <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Section</th>
                            <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 50px;">#</th>
                            <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Question</th>
                            <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Answer</th>
                            <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 220px;">Answer Summary</th>
                            <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 100px;">PDF Pages</th>
                            <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 80px;">Footnote</th>
                        </tr>
                    </thead>
                    <tbody id="unitaryTableBody">
    `;

    // Group by section
    const sections = {};
    questionsList.forEach(q => {
        if (!sections[q.section_name]) {
            sections[q.section_name] = [];
        }
        sections[q.section_name].push(q);
    });

    // Render rows grouped by section
    Object.entries(sections).forEach(([sectionName, questions]) => {
        questions.forEach((q, idx) => {
            const isPending = q.status === 'pending';
            const rowColor = isPending ? '#fafafa' : '#e8f5e9';

            // Build answer cell content - clickable when has answer
            let answerContent;
            if (isPending) {
                answerContent = '<span style="color: #999; font-style: italic;">Analyzing...</span>';
            } else {
                const truncatedAnswer = (q.answer && q.answer.length > 150) ? q.answer.substring(0, 150) + '...' : (q.answer || '');
                const fragmentBadge = (currentAnalysisMode === 'bestprep' && q.fragment_count > 1)
                    ? `<span style="background: #ff9800; color: white; padding: 1px 6px; border-radius: 10px; font-size: 10px; margin-left: 5px;">${q.fragment_count} frags</span>`
                    : '';
                answerContent = `<span onclick="openAnswerDetailModal('${q.question_id}')" style="cursor: pointer; color: #1E3A8A;" title="Click to view full answer">${truncatedAnswer}${fragmentBadge}</span>`;
            }

            // Determine if this should be auto-selected (unanswered or low confidence)
            const isUnanswered = isPending || !q.answer;
            const isLowConfidence = q.confidence && q.confidence < 0.9;
            const isSelected = selectedQuestionsForProcessing.has(q.question_id);

            html += `
                <tr id="row-${q.question_id}" style="background: ${rowColor};">
                    <td style="padding: 10px; text-align: center; border: 1px solid #ddd;">
                        <input type="checkbox"
                               class="question-select-checkbox"
                               data-question-id="${q.question_id}"
                               ${isSelected ? 'checked' : ''}
                               onchange="handleQuestionSelectionChange('${q.question_id}', this.checked)"
                               title="${isUnanswered ? 'Unanswered question' : (isLowConfidence ? 'Low confidence answer' : 'Select for additional processing')}">
                    </td>
                    <td style="padding: 10px; border: 1px solid #ddd;">${idx === 0 ? sectionName : ''}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${q.question_number}</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">${q.question_text}</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">
                        ${answerContent}
                    </td>
                    <td style="padding: 10px; border: 1px solid #ddd; font-style: ${q.answer_summary ? 'normal' : 'italic'}; color: ${q.answer_summary ? '#1f2937' : '#999'};">${isPending ? '-' : (q.answer_summary || '-')}</td>
                    <td style="padding: 10px; border: 1px solid #ddd;">${isPending ? '-' : q.pages.join(', ')}</td>
                    <td style="padding: 10px; border: 1px solid #ddd; text-align: center;">${q.footnote ? '✓' : '-'}</td>
                </tr>
            `;
        });
    });

    html += `
                    </tbody>
                </table>
            </div>

            <!-- Footnotes Section -->
            ${renderFootnotesSection()}
        </div>
    `;

    container.innerHTML = html;
}

function updateUnitaryTableRows(questionIds) {
    questionIds.forEach(qid => {
        const row = document.getElementById(`row-${qid}`);
        if (row && allQuestions[qid]) {
            const q = allQuestions[qid];
            const isPending = q.status === 'pending';
            const rowColor = isPending ? '#fafafa' : '#e8f5e9';

            row.style.background = rowColor;

            // Update cells (skip section and number, update question/answer/summary/pages/footnote)
            const cells = row.cells;
            if (cells.length >= 7) {
                if (isPending) {
                    cells[3].innerHTML = '<span style="color: #999; font-style: italic;">Analyzing...</span>';
                    cells[3].style.cursor = 'default';
                } else {
                    // Truncate answer for display and make it clickable
                    const truncatedAnswer = truncateText(q.answer || '', 150);
                    const fragmentBadge = (currentAnalysisMode === 'bestprep' && q.fragment_count > 1)
                        ? `<span style="background: #ff9800; color: white; padding: 1px 6px; border-radius: 10px; font-size: 10px; margin-left: 5px;">${q.fragment_count} frags</span>`
                        : '';
                    // Stage badge for v2 pipeline answers (shows which stage found this answer)
                    const stageBadge = q.stageLabel
                        ? `<span style="background: ${q.stageColor || '#6b7280'}; color: white; padding: 1px 6px; border-radius: 10px; font-size: 10px; margin-left: 5px;">${q.stageLabel}</span>`
                        : '';
                    cells[3].innerHTML = `<span onclick="openAnswerDetailModal('${qid}')" style="cursor: pointer; color: #1E3A8A;" title="Click to view full answer">${truncatedAnswer}${fragmentBadge}${stageBadge}</span>`;
                    cells[3].style.cursor = 'pointer';
                }
                cells[3].style.color = isPending ? '#999' : '';
                cells[3].style.fontStyle = isPending ? 'italic' : '';
                cells[4].innerHTML = isPending ? '-' : (q.answer_summary || '-');
                cells[4].style.fontStyle = q.answer_summary ? 'normal' : 'italic';
                cells[4].style.color = q.answer_summary ? '#1f2937' : '#999';
                cells[5].innerHTML = isPending ? '-' : q.pages.join(', ');
                cells[6].innerHTML = q.footnote ? '✓' : '-';
            }
        }
    });

    // Update footnotes section
    const footnotesContainer = document.querySelector('.footnotes-section');
    if (footnotesContainer) {
        footnotesContainer.outerHTML = renderFootnotesSection();
    }

    // Update stats header with live counts
    updateUnitaryStats();
}

function updateUnitaryStats() {
    /**
     * Update the stats header in the Unitary Log with live counts.
     * Called after each row update to keep stats in sync with data.
     */
    const statsDiv = document.querySelector('.unitary-stats');
    if (!statsDiv) return;

    const questionsList = Object.values(allQuestions);
    const answeredCount = questionsList.filter(q => q.status === 'found').length;
    const totalCount = questionsList.length;
    const totalFragments = questionsList.reduce((sum, q) => sum + (q.fragment_count || 0), 0);

    statsDiv.innerHTML = `
        <div style="font-weight: 600; color: #1E3A8A;">
            Answered: ${answeredCount}/${totalCount} questions (${totalCount > 0 ? ((answeredCount/totalCount)*100).toFixed(1) : 0}%)
        </div>
        <div style="margin-top: 5px; color: #666;">
            Footnotes: ${allFootnotes.length}${currentAnalysisMode === 'bestprep' ? ` | Fragments: ${totalFragments}` : ''}
        </div>
    `;
}

function truncateText(text, maxLength) {
    if (!text) return '';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
}

function renderFootnotesSection() {
    if (allFootnotes.length === 0) return '';

    return `
        <div class="footnotes-section" style="margin-top: 30px; padding: 20px; background: #fffaeb; border-radius: 8px; border-left: 4px solid #ff9800;">
            <h4 style="color: #1E3A8A; margin-bottom: 15px;">📝 Footnotes (PDF Pages & Context)</h4>
            <ol style="margin: 0; padding-left: 20px;">
                ${allFootnotes.map(fn => `<li style="margin-bottom: 10px;">${fn}</li>`).join('')}
            </ol>
        </div>
    `;
}

// ============================================================================
// QUESTION SELECTION FOR MULTI-PASS PROCESSING
// ============================================================================

function handleQuestionSelectionChange(questionId, isSelected) {
    if (isSelected) {
        selectedQuestionsForProcessing.add(questionId);
    } else {
        selectedQuestionsForProcessing.delete(questionId);
    }
    updateSelectionSummary();
}

function toggleAllQuestionSelection(checkbox) {
    const checkboxes = document.querySelectorAll('.question-select-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = checkbox.checked;
        const qid = cb.dataset.questionId;
        if (checkbox.checked) {
            selectedQuestionsForProcessing.add(qid);
        } else {
            selectedQuestionsForProcessing.delete(qid);
        }
    });
    updateSelectionSummary();
}

function updateSelectionSummary() {
    const panel = document.getElementById('selectionActionsPanel');
    const summary = document.getElementById('selectionSummary');

    if (selectedQuestionsForProcessing.size > 0) {
        panel.style.display = 'flex';
        summary.textContent = `${selectedQuestionsForProcessing.size} questions selected`;
    } else {
        panel.style.display = 'none';
    }
}

function clearQuestionSelection() {
    selectedQuestionsForProcessing.clear();
    document.querySelectorAll('.question-select-checkbox').forEach(cb => cb.checked = false);
    const selectAll = document.getElementById('selectAllQuestions');
    if (selectAll) selectAll.checked = false;
    updateSelectionSummary();
}

function getSelectedQuestionIds() {
    return Array.from(selectedQuestionsForProcessing);
}

async function runSecondPassOnSelected() {
    const selectedIds = getSelectedQuestionIds();
    if (selectedIds.length === 0) {
        Logger.warning('No questions selected for second pass');
        alert('Please select questions first');
        return;
    }

    Logger.info(`🔄 Starting second pass on ${selectedIds.length} selected questions...`);

    try {
        const response = await fetch(`/api/analyze/second-pass/${currentSessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_ids: selectedIds })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Second pass request failed');
        }

        const result = await response.json();
        Logger.success(`✅ Second pass complete: ${result.answers_found} new answers found`);

        // Refresh results if answers were found
        if (result.answers_found > 0) {
            Logger.info('Refreshing results...');
            // The backend should have updated the session, so we can fetch fresh results
            await refreshResults();
        }
    } catch (error) {
        Logger.error('Second pass failed: ' + error.message);
        alert('Second pass failed: ' + error.message);
    }
}

async function runRAGOnSelected() {
    const selectedIds = getSelectedQuestionIds();
    if (selectedIds.length === 0) {
        Logger.warning('No questions selected for RAG search');
        alert('Please select questions first');
        return;
    }

    Logger.info(`🔍 Starting Deep RAG on ${selectedIds.length} selected questions...`);

    try {
        const response = await fetch(`/api/analyze/rag/${currentSessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_ids: selectedIds })
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'RAG request failed');
        }

        const result = await response.json();
        Logger.success(`✅ Deep RAG complete: ${result.answers_found} potential answers found (with disclaimers)`);

        // Show RAG results in a modal or update table
        if (result.answers_found > 0 && result.results) {
            showRAGResults(result.results);
        }
    } catch (error) {
        Logger.error('Deep RAG failed: ' + error.message);
        alert('Deep RAG failed: ' + error.message);
    }
}

function showRAGResults(results) {
    // Display RAG results with disclaimers
    let html = '<div style="max-height: 400px; overflow-y: auto;">';
    html += '<p style="color: #856404; background: #fff3cd; padding: 10px; border-radius: 6px; margin-bottom: 15px;">';
    html += '⚠️ These answers are from EXTERNAL sources and may not apply to this project. Always verify with official documents.';
    html += '</p>';

    for (const [qid, data] of Object.entries(results)) {
        const q = allQuestions[qid];
        html += `
            <div style="border: 1px solid #ddd; padding: 15px; margin-bottom: 10px; border-radius: 6px;">
                <strong>${q ? q.question_text : qid}</strong>
                <p style="margin: 10px 0;">${data.answer}</p>
                <small style="color: #666;">Source: ${data.source} (${data.source_type}) | Confidence: ${(data.confidence * 100).toFixed(0)}%</small>
            </div>
        `;
    }
    html += '</div>';

    // Show in a simple alert/modal (you can enhance this)
    const modal = document.createElement('div');
    modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 10000;';
    modal.innerHTML = `
        <div style="background: white; padding: 20px; border-radius: 8px; max-width: 600px; width: 90%;">
            <h3 style="color: #1E3A8A; margin-bottom: 15px;">🔍 Deep RAG Results</h3>
            ${html}
            <button onclick="this.parentElement.parentElement.remove()" style="margin-top: 15px; background: #1E3A8A; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer;">Close</button>
        </div>
    `;
    document.body.appendChild(modal);
}

async function refreshResults() {
    if (!currentSessionId) return;

    try {
        const response = await fetch(`/api/results/${currentSessionId}`);
        if (response.ok) {
            const data = await response.json();
            if (data.status === 'complete' || data.status === 'partial') {
                updateUnitaryTableAsFinal(data.result, data.status === 'partial');
            }
        }
    } catch (error) {
        Logger.warning('Could not refresh results: ' + error.message);
    }
}

