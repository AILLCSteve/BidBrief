// ============================================================================
// ABOUT MODAL
// ============================================================================

function openAboutModal() {
    document.getElementById('aboutModal').style.display = 'flex';
}

function closeAboutModal() {
    document.getElementById('aboutModal').style.display = 'none';
}

// Close modal on outside click
window.addEventListener('click', function(event) {
    const aboutModal = document.getElementById('aboutModal');
    if (event.target === aboutModal) {
        closeAboutModal();
    }
    const answerModal = document.getElementById('answerDetailModal');
    if (event.target === answerModal) {
        closeAnswerDetailModal();
    }
    // fullViewModal has its own onclick handler in the HTML
});

// ============================================================================
// ANSWER DETAIL MODAL - View full answer details during analysis
// ============================================================================

function openAnswerDetailModal(questionId) {
    const q = allQuestions[questionId];
    if (!q) {
        Logger.warning(`Question ${questionId} not found`);
        return;
    }

    document.getElementById('answerDetailTitle').textContent = `Q${q.question_number}: ${q.section_name}`;

    // Build content with all available details
    let pagesHtml = q.pages && q.pages.length > 0
        ? q.pages.map(p => `<span style="background: #e3f2fd; padding: 2px 8px; border-radius: 4px; margin: 2px; display: inline-block;">Page ${p}</span>`).join('')
        : '<em style="color: #999;">No pages yet</em>';

    let fragmentInfo = '';
    if (currentAnalysisMode === 'bestprep' && q.fragment_count) {
        fragmentInfo = `<div style="margin-top: 10px; padding: 8px 12px; background: #fff3e0; border-radius: 4px; border-left: 3px solid #ff9800;">
            <strong>Fragments Found:</strong> ${q.fragment_count} answer fragment(s) accumulated
        </div>`;
    }

    let answerHtml = q.answer
        ? `<div style="white-space: pre-wrap; line-height: 1.6;">${q.answer}</div>`
        : '<em style="color: #999;">Analysis in progress...</em>';

    let footnoteHtml = q.footnote && q.footnote.trim()
        ? `<div style="margin-top: 15px; padding: 12px; background: #fffaeb; border-radius: 6px; border-left: 3px solid #ff9800;">
            <strong>Citations:</strong> ${q.footnote}
           </div>`
        : '';

    let content = `
        <div style="margin-bottom: 20px;">
            <div style="font-size: 1.1em; color: #1E3A8A; margin-bottom: 10px;"><strong>Question:</strong></div>
            <div style="padding: 12px; background: #f5f5f5; border-radius: 6px; border-left: 3px solid #1E3A8A;">
                ${q.question_text}
            </div>
        </div>

        <div style="margin-bottom: 15px;">
            <div style="font-size: 1.1em; color: #1E3A8A; margin-bottom: 10px;"><strong>PDF Pages:</strong></div>
            <div>${pagesHtml}</div>
            ${fragmentInfo}
        </div>

        <div style="margin-bottom: 15px;">
            <div style="font-size: 1.1em; color: #1E3A8A; margin-bottom: 10px;"><strong>Answer:</strong></div>
            <div style="padding: 15px; background: #e8f5e9; border-radius: 6px; border-left: 3px solid #4CAF50; max-height: 400px; overflow-y: auto;">
                ${answerHtml}
            </div>
        </div>

        ${q.answer_summary ? `
        <div style="margin-bottom: 15px;">
            <div style="font-size: 1.1em; color: #1E3A8A; margin-bottom: 10px;"><strong>Answer Summary:</strong></div>
            <div style="padding: 15px; background: #eef2ff; border-radius: 6px; border-left: 3px solid #5B7FCC;">
                ${q.answer_summary}
            </div>
        </div>` : ''}

        ${footnoteHtml}

        <div style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #eee; color: #666; font-size: 12px;">
            <strong>Status:</strong> ${q.status === 'found' ? '✅ Answer Found' : '⏳ Analyzing...'}
            ${currentAnalysisMode === 'bestprep' ? ' | <strong>Mode:</strong> BestPrep (Cumulative)' : ' | <strong>Mode:</strong> Bid/Spec'}
        </div>
    `;

    document.getElementById('answerDetailContent').innerHTML = content;
    document.getElementById('answerDetailModal').style.display = 'flex';
}

function closeAnswerDetailModal() {
    document.getElementById('answerDetailModal').style.display = 'none';
}

// ============================================================================
// VIEW MODAL - Comprehensive results view (identical to admin modal)
// ============================================================================

function openViewModal() {
    const modal = document.getElementById('fullViewModal');
    modal.style.display = 'flex';

    // Render all tabs
    renderFullViewSummaryTab();
    renderFullViewDetailedTab();
    renderFullViewBySectionTab();
    if (currentAnalysisMode === 'bestprep') {
        document.getElementById('fullViewFragmentsTabBtn').style.display = 'inline-block';
        document.getElementById('fullViewPageIndexTabBtn').style.display = 'inline-block';
        renderFullViewFragmentsTab();
        renderFullViewPageIndexTab();
    } else {
        document.getElementById('fullViewFragmentsTabBtn').style.display = 'none';
        document.getElementById('fullViewPageIndexTabBtn').style.display = 'none';
    }
    renderFullViewFootnotesTab();

    // Show V2 Pipeline tabs (HOTDOG7ATE)
    const isV2Pipeline = currentOptimizedScanData && Object.keys(currentOptimizedScanData).length > 0;

    // Optimized Scan tab
    if (isV2Pipeline) {
        document.getElementById('fullViewQuickScanTabBtn').style.display = 'inline-block';
        renderFullViewOptimizedScanTab();
    } else {
        document.getElementById('fullViewQuickScanTabBtn').style.display = 'none';
    }

    // Unanswered Pass tab
    if (isV2Pipeline) {
        document.getElementById('fullViewUnansweredPassTabBtn').style.display = 'inline-block';
        renderFullViewUnansweredPassTab();
    } else {
        document.getElementById('fullViewUnansweredPassTabBtn').style.display = 'none';
    }

    // RAG tab
    if (isV2Pipeline) {
        document.getElementById('fullViewRagTabBtn').style.display = 'inline-block';
        renderFullViewRagTab();
    } else {
        document.getElementById('fullViewRagTabBtn').style.display = 'none';
    }

    // Set default tab
    switchFullViewTab('summary');
}

function closeFullViewModal() {
    document.getElementById('fullViewModal').style.display = 'none';
}

function switchFullViewTab(tabName) {
    // Remove active class from all tab buttons
    document.querySelectorAll('.fv-tab-btn').forEach(btn => {
        btn.classList.remove('active');
        btn.style.background = 'transparent';
        btn.style.color = '#6b7280';
        btn.style.borderBottomColor = 'transparent';
    });

    // Hide all tab content
    document.querySelectorAll('.fv-tab-content').forEach(content => {
        content.classList.remove('active');
        content.style.display = 'none';
    });

    // Activate selected tab button
    const activeBtn = document.querySelector(`[onclick="switchFullViewTab('${tabName}')"]`);
    if (activeBtn) {
        activeBtn.classList.add('active');
        activeBtn.style.background = 'white';
        activeBtn.style.color = '#1E3A8A';
        activeBtn.style.borderBottomColor = '#1E3A8A';
    }

    // Show selected tab content
    const activeContent = document.getElementById(`fv-tab-${tabName}`);
    if (activeContent) {
        activeContent.classList.add('active');
        activeContent.style.display = 'block';
    }
}

function renderFullViewSummaryTab() {
    const questionsList = Object.values(allQuestions);
    const totalQuestions = questionsList.length;
    const answeredQuestions = questionsList.filter(q => q.status === 'found').length;
    const answerRate = totalQuestions > 0 ? Math.round((answeredQuestions / totalQuestions) * 100) : 0;
    const totalFragments = questionsList.reduce((sum, q) => sum + (q.fragment_count || 0), 0);
    const avgFragsPerQ = answeredQuestions > 0 ? (totalFragments / answeredQuestions).toFixed(1) : '0';

    // Collect all pages
    const allPages = new Set();
    questionsList.forEach(q => {
        if (q.pages) q.pages.forEach(p => allPages.add(p));
    });

    let html = '';

    if (currentAnalysisMode === 'bestprep') {
        html = `
            <div style="background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%); color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px;">
                <h3 style="margin: 0 0 8px 0; font-size: 16px;">BestPrep/TestPrep Analysis</h3>
                <p style="margin: 0; opacity: 0.9; font-size: 13px;">Exhaustive analysis mode - all answer fragments preserved</p>
            </div>

            <h3 style="margin: 0 0 15px 0; color: #1E3A8A; font-size: 16px;">Analysis Info</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                <tbody>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb; width: 220px;">Analysis Mode</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb;"><span style="background: #22c55e; color: white; padding: 2px 10px; border-radius: 4px; font-size: 12px;">BestPrep</span></td></tr>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Generated</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb;">${new Date().toLocaleString()}</td></tr>
                </tbody>
            </table>

            <h3 style="margin: 0 0 15px 0; color: #1E3A8A; font-size: 16px;">Document Statistics</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                <tbody>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb; width: 220px;">Total Pages Referenced</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb;">${allPages.size}</td></tr>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Page Range</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb;">${allPages.size > 0 ? Math.min(...allPages) + ' - ' + Math.max(...allPages) : 'N/A'}</td></tr>
                </tbody>
            </table>

            <h3 style="margin: 0 0 15px 0; color: #1E3A8A; font-size: 16px;">Question & Answer Statistics</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                <tbody>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb; width: 220px;">Total Questions</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb;">${totalQuestions}</td></tr>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Questions Answered</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb; color: #22c55e; font-weight: 600;">${answeredQuestions}</td></tr>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Answer Rate</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb;">${answerRate}%</td></tr>
                </tbody>
            </table>

            <h3 style="margin: 0 0 15px 0; color: #e65100; font-size: 16px;">Fragment & Citation Statistics</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                <tbody>
                    <tr><td style="padding: 10px; font-weight: 600; background: #fff3e0; color: #e65100; border: 1px solid #e5e7eb; width: 220px;">Total Fragments Collected</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb; font-weight: 600; color: #e65100;">${totalFragments}</td></tr>
                    <tr><td style="padding: 10px; font-weight: 600; background: #fff3e0; color: #e65100; border: 1px solid #e5e7eb;">Total Citations/Footnotes</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb; font-weight: 600; color: #e65100;">${allFootnotes.length}</td></tr>
                    <tr><td style="padding: 10px; font-weight: 600; background: #fff3e0; color: #e65100; border: 1px solid #e5e7eb;">Avg Fragments/Question</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb; font-weight: 600; color: #e65100;">${avgFragsPerQ}</td></tr>
                </tbody>
            </table>
        `;
    } else {
        // Build Key Document Details section
        let krpHtml = '';
        if (currentKeyRequirements && Object.keys(currentKeyRequirements).length > 0) {
            krpHtml = `
                <h3 style="margin: 25px 0 15px 0; color: #1E3A8A; font-size: 16px;">🔑 Key Document Details</h3>
                <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                    <tbody>
            `;
            for (const [key, value] of Object.entries(currentKeyRequirements)) {
                if (value && value.trim()) {
                    const label = key;
                    krpHtml += `
                        <tr>
                            <td style="padding: 10px; font-weight: 600; background: #fef3c7; border: 1px solid #e5e7eb; width: 200px;">${label}</td>
                            <td style="padding: 10px; border: 1px solid #e5e7eb;">${value}</td>
                        </tr>
                    `;
                }
            }
            krpHtml += '</tbody></table>';
        }

        html = `
            <h3 style="margin: 0 0 15px 0; color: #1E3A8A; font-size: 16px;">Analysis Statistics</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                <tbody>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb; width: 200px;">Analysis Mode</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb;"><span style="background: #3b82f6; color: white; padding: 2px 10px; border-radius: 4px; font-size: 12px;">Bid/Spec</span></td></tr>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Total Questions</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb;">${totalQuestions}</td></tr>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Questions Answered</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb; color: #22c55e; font-weight: 600;">${answeredQuestions}</td></tr>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Answer Rate</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb;">${answerRate}%</td></tr>
                    <tr><td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Total Pages Referenced</td>
                        <td style="padding: 10px; border: 1px solid #e5e7eb;">${allPages.size}</td></tr>
                </tbody>
            </table>
            ${krpHtml}
        `;
    }

    document.getElementById('fv-summaryContent').innerHTML = html;
}

function renderFullViewDetailedTab() {
    const questionsList = Object.values(allQuestions);

    let html = `
        <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
            <thead>
                <tr style="background: #1E3A8A; color: white;">
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 40px;">#</th>
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 150px;">Section</th>
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 220px;">Question</th>
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Answer</th>
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 220px;">Answer Summary</th>
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 100px;">Pages</th>
                    ${currentAnalysisMode === 'bestprep' ? '<th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 70px;">Frags</th>' : ''}
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd; width: 60px;">Status</th>
                </tr>
            </thead>
            <tbody>
    `;

    let num = 1;
    questionsList.forEach(q => {
        const hasAnswer = q.answer && q.answer.trim();
        const pages = q.pages && q.pages.length > 0 ? q.pages.join(', ') : '-';
        const fragCount = q.fragment_count || 0;

        html += `
            <tr style="background: ${num % 2 === 0 ? '#f9fafb' : 'white'};">
                <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center;">${num}</td>
                <td style="padding: 10px; border: 1px solid #e5e7eb;">${q.section_name}</td>
                <td style="padding: 10px; border: 1px solid #e5e7eb;">${q.question_text}</td>
                <td style="padding: 10px; border: 1px solid #e5e7eb; max-width: 400px; word-wrap: break-word;">${hasAnswer ? q.answer : '<em style="color: #999;">Not found</em>'}</td>
                <td style="padding: 10px; border: 1px solid #e5e7eb; word-wrap: break-word;">${q.answer_summary || '<em style="color: #999;">-</em>'}</td>
                <td style="padding: 10px; border: 1px solid #e5e7eb; font-weight: 600; color: #1E3A8A; text-align: center;">${pages}</td>
                ${currentAnalysisMode === 'bestprep' ? `<td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center;"><span style="background: ${fragCount > 1 ? '#ff9800' : '#e0e0e0'}; color: ${fragCount > 1 ? 'white' : '#666'}; padding: 2px 8px; border-radius: 10px; font-size: 11px;">${fragCount}</span></td>` : ''}
                <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center; background: ${hasAnswer ? '#d4edda' : '#f8d7da'}; color: ${hasAnswer ? '#155724' : '#721c24'}; font-weight: 600;">${hasAnswer ? 'Yes' : 'No'}</td>
            </tr>
        `;
        num++;
    });

    html += '</tbody></table>';
    document.getElementById('fv-detailedContent').innerHTML = html;
}

function renderFullViewBySectionTab() {
    const questionsList = Object.values(allQuestions);

    // Group by section
    const sections = {};
    questionsList.forEach(q => {
        if (!sections[q.section_name]) {
            sections[q.section_name] = [];
        }
        sections[q.section_name].push(q);
    });

    let html = '';

    Object.entries(sections).forEach(([sectionName, questions]) => {
        const answered = questions.filter(q => q.status === 'found').length;
        const totalFrags = questions.reduce((sum, q) => sum + (q.fragment_count || 0), 0);

        html += `
            <div style="margin-bottom: 30px;">
                <h3 style="color: #1E3A8A; margin-bottom: 15px; padding: 10px 15px; background: #e8eef7; border-radius: 6px;">
                    ${sectionName}
                    <span style="float: right; font-size: 14px; color: #5B7FCC;">
                        ${answered}/${questions.length} answered
                        ${currentAnalysisMode === 'bestprep' ? `<span style="margin-left: 10px; background: #ff9800; color: white; padding: 2px 8px; border-radius: 4px;">${totalFrags} frags</span>` : ''}
                    </span>
                </h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 10px; text-align: left; border: 1px solid #e5e7eb; width: 40px;">#</th>
                            <th style="padding: 10px; text-align: left; border: 1px solid #e5e7eb;">Question</th>
                            <th style="padding: 10px; text-align: left; border: 1px solid #e5e7eb;">Answer</th>
                            <th style="padding: 10px; text-align: left; border: 1px solid #e5e7eb; width: 200px;">Answer Summary</th>
                            <th style="padding: 10px; text-align: left; border: 1px solid #e5e7eb; width: 100px;">Pages</th>
                            <th style="padding: 10px; text-align: center; border: 1px solid #e5e7eb; width: 60px;">Status</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        questions.forEach((q, idx) => {
            const hasAnswer = q.answer && q.answer.trim();
            const pages = q.pages && q.pages.length > 0 ? q.pages.join(', ') : '-';

            html += `
                <tr style="background: ${idx % 2 === 0 ? 'white' : '#f9fafb'};">
                    <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center;">${idx + 1}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">${q.question_text}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">${hasAnswer ? q.answer : '<em style="color: #999;">Not found</em>'}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">${q.answer_summary || '<em style="color: #999;">-</em>'}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb; font-weight: 600; color: #1E3A8A; text-align: center;">${pages}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center; background: ${hasAnswer ? '#d4edda' : '#f8d7da'}; color: ${hasAnswer ? '#155724' : '#721c24'}; font-weight: 600;">${hasAnswer ? 'Yes' : 'No'}</td>
                </tr>
            `;
        });

        html += '</tbody></table></div>';
    });

    document.getElementById('fv-bySectionContent').innerHTML = html;
}

function renderFullViewFragmentsTab() {
    const questionsList = Object.values(allQuestions);
    const questionsWithFragments = questionsList.filter(q => q.fragment_count > 0);

    if (questionsWithFragments.length === 0) {
        document.getElementById('fv-fragmentsContent').innerHTML = `
            <div style="text-align: center; padding: 60px; color: #9ca3af;">
                <p style="font-size: 18px; margin-bottom: 10px;">No fragment data available</p>
                <p style="font-size: 14px;">Fragment details are shown in the detailed answers.</p>
            </div>
        `;
        return;
    }

    let totalFrags = questionsList.reduce((sum, q) => sum + (q.fragment_count || 0), 0);

    let html = `
        <div style="margin-bottom: 20px; padding: 15px; background: #fff3e0; border-radius: 8px;">
            <strong style="color: #e65100;">${totalFrags} Answer Fragments</strong>
            <span style="color: #666; margin-left: 10px;">All answer fragments preserved with full provenance</span>
        </div>
        <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
            <thead>
                <tr style="background: #5B7FCC; color: white;">
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Question</th>
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Answer (with accumulated fragments)</th>
                    <th style="padding: 12px; text-align: center; border: 1px solid #ddd; width: 80px;">Pages</th>
                    <th style="padding: 12px; text-align: center; border: 1px solid #ddd; width: 70px;">Frags</th>
                </tr>
            </thead>
            <tbody>
    `;

    questionsWithFragments.forEach((q, idx) => {
        const pages = q.pages && q.pages.length > 0 ? q.pages.join(', ') : '-';

        html += `
            <tr style="background: ${idx % 2 === 0 ? 'white' : '#f9fafb'};">
                <td style="padding: 10px; border: 1px solid #e5e7eb; vertical-align: top; max-width: 200px;">${q.question_text}</td>
                <td style="padding: 10px; border: 1px solid #e5e7eb; vertical-align: top; max-width: 400px; word-wrap: break-word;">${q.answer || '-'}</td>
                <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center; font-weight: 600; color: #1E3A8A;">${pages}</td>
                <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center;">
                    <span style="background: #ff9800; color: white; padding: 2px 10px; border-radius: 10px; font-size: 12px;">${q.fragment_count || 0}</span>
                </td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    document.getElementById('fv-fragmentsContent').innerHTML = html;
}

function renderFullViewPageIndexTab() {
    const questionsList = Object.values(allQuestions);

    // Build page -> questions mapping
    const pageMap = {};
    questionsList.forEach(q => {
        if (q.pages) {
            q.pages.forEach(page => {
                if (!pageMap[page]) {
                    pageMap[page] = [];
                }
                if (!pageMap[page].includes(q.question_id)) {
                    pageMap[page].push(q.question_id);
                }
            });
        }
    });

    const sortedPages = Object.keys(pageMap).map(Number).sort((a, b) => a - b);

    if (sortedPages.length === 0) {
        document.getElementById('fv-pageIndexContent').innerHTML = `
            <div style="text-align: center; padding: 60px; color: #9ca3af;">
                <p style="font-size: 18px; margin-bottom: 10px;">No page references found</p>
            </div>
        `;
        return;
    }

    let html = `
        <div style="margin-bottom: 20px; padding: 15px; background: #e3f2fd; border-radius: 8px;">
            <strong style="color: #1565c0;">${sortedPages.length} Pages Referenced</strong>
            <span style="color: #666; margin-left: 10px;">Shows which questions cite each page</span>
        </div>
        <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
            <thead>
                <tr style="background: #1E3A8A; color: white;">
                    <th style="padding: 12px; text-align: center; border: 1px solid #ddd; width: 80px;">Page</th>
                    <th style="padding: 12px; text-align: left; border: 1px solid #ddd;">Questions Referencing This Page</th>
                    <th style="padding: 12px; text-align: center; border: 1px solid #ddd; width: 100px;">Count</th>
                </tr>
            </thead>
            <tbody>
    `;

    sortedPages.forEach((page, idx) => {
        const questionIds = pageMap[page];
        html += `
            <tr style="background: ${idx % 2 === 0 ? 'white' : '#f9fafb'};">
                <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center; font-weight: 600; color: #1E3A8A;">${page}</td>
                <td style="padding: 10px; border: 1px solid #e5e7eb;">${questionIds.join(', ')}</td>
                <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center;">${questionIds.length}</td>
            </tr>
        `;
    });

    html += '</tbody></table>';
    document.getElementById('fv-pageIndexContent').innerHTML = html;
}

function renderFullViewFootnotesTab() {
    if (allFootnotes.length === 0) {
        document.getElementById('fv-footnotesContent').innerHTML = `
            <div style="text-align: center; padding: 60px; color: #9ca3af;">
                <p style="font-size: 18px; margin-bottom: 10px;">No footnotes available</p>
            </div>
        `;
        return;
    }

    let html = `
        <div style="margin-bottom: 20px; padding: 15px; background: #E8EEF7; border-radius: 8px;">
            <strong style="color: #1E3A8A;">${allFootnotes.length} Footnotes</strong>
            <span style="color: #6b7280; margin-left: 10px;">Additional context and citations</span>
        </div>
        <ol style="margin: 0; padding-left: 25px; line-height: 1.8;">
    `;

    allFootnotes.forEach(fn => {
        html += `<li style="margin-bottom: 12px; padding: 10px; background: #fffaeb; border-radius: 4px; border-left: 3px solid #ff9800;">${fn}</li>`;
    });

    html += '</ol>';
    document.getElementById('fv-footnotesContent').innerHTML = html;
}

function renderFullViewOptimizedScanTab() {
    if (!currentOptimizedScanData || Object.keys(currentOptimizedScanData).length === 0) {
        document.getElementById('fv-optimizedScanContent').innerHTML = `
            <div style="text-align: center; padding: 60px; color: #9ca3af;">
                <p style="font-size: 18px; margin-bottom: 10px;">Stage not Processed by User</p>
                <p style="font-size: 14px;">Optimized Scan Pass was not run for this analysis</p>
            </div>
        `;
        return;
    }

    const data = currentOptimizedScanData;
    const structure = data.structure || {};
    const expertAssignments = data.expert_assignments || [];
    const allKeywords = data.all_keywords_by_section || {};
    const reduction = data.estimated_reduction || 'N/A';
    const unassigned = data.unassigned_questions || [];
    const hotspots = data.topic_hotspots_found || structure.topic_hotspots_count || 0;

    let html = `
        <div style="background: linear-gradient(135deg, #7c3aed, #a855f7); color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 8px 0; font-size: 16px;">V2 Pipeline - Optimized Scan Pass Audit</h3>
            <p style="margin: 0; opacity: 0.9; font-size: 13px;">Enhanced document analysis: TOC, Index, Headers, Footers, Topic Hotspots, Expert Keywords</p>
        </div>

        <h3 style="margin: 0 0 15px 0; color: #1E3A8A; font-size: 16px;">Document Structure Detected</h3>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
            <tbody>
                <tr>
                    <td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb; width: 200px;">Table of Contents</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">
                        <span style="background: ${structure.has_toc ? '#dcfce7' : '#fee2e2'}; color: ${structure.has_toc ? '#166534' : '#991b1b'}; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">
                            ${structure.has_toc ? 'Found' : 'Not Found'}
                        </span>
                        ${structure.toc_entries_count ? `<span style="color: #6b7280; margin-left: 8px;">(${structure.toc_entries_count} entries)</span>` : ''}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Index</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">
                        <span style="background: ${structure.has_index ? '#dcfce7' : '#fee2e2'}; color: ${structure.has_index ? '#166534' : '#991b1b'}; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">
                            ${structure.has_index ? 'Found' : 'Not Found'}
                        </span>
                        ${structure.index_terms_count ? `<span style="color: #6b7280; margin-left: 8px;">(${structure.index_terms_count} terms)</span>` : ''}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Appendix</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">
                        <span style="background: ${structure.has_appendix ? '#dcfce7' : '#fee2e2'}; color: ${structure.has_appendix ? '#166534' : '#991b1b'}; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">
                            ${structure.has_appendix ? 'Found' : 'Not Found'}
                        </span>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Running Headers</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">
                        ${structure.running_headers_count || 0} pages with detected running headers
                    </td>
                </tr>
                <tr>
                    <td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Spec Divisions</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">
                        ${structure.spec_divisions_count || 0} specification divisions found
                    </td>
                </tr>
                <tr>
                    <td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Topic Hotspots</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">
                        <span style="background: ${hotspots > 0 ? '#dcfce7' : '#fef3c7'}; color: ${hotspots > 0 ? '#166534' : '#92400e'}; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">
                            ${hotspots} keyword-dense regions detected
                        </span>
                    </td>
                </tr>
            </tbody>
        </table>

        <h3 style="margin: 0 0 15px 0; color: #1E3A8A; font-size: 16px;">Expert Page Assignments</h3>
    `;

    if (expertAssignments.length > 0) {
        html += `
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                <thead>
                    <tr style="background: #1E3A8A; color: white;">
                        <th style="padding: 12px; text-align: left; font-weight: 600;">Expert</th>
                        <th style="padding: 12px; text-align: left; font-weight: 600;">Section</th>
                        <th style="padding: 12px; text-align: left; font-weight: 600;">Primary Pages</th>
                        <th style="padding: 12px; text-align: left; font-weight: 600;">Context Pages</th>
                        <th style="padding: 12px; text-align: center; font-weight: 600;">Total</th>
                        <th style="padding: 12px; text-align: left; font-weight: 600;">Keywords Matched</th>
                    </tr>
                </thead>
                <tbody>
        `;

        expertAssignments.forEach((assignment, idx) => {
            const primaryPages = assignment.primary_pages || [];
            const contextPages = assignment.context_pages || [];
            const keywordsMatched = assignment.keywords_matched || [];
            const isAlt = idx % 2 === 1;

            html += `
                <tr style="${isAlt ? 'background: #f9fafb;' : ''}">
                    <td style="padding: 10px; border: 1px solid #e5e7eb; font-weight: 600;">${assignment.expert || 'Unknown'}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">${assignment.section_id || ''}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb; font-size: 12px;">${primaryPages.slice(0, 10).join(', ')}${primaryPages.length > 10 ? '...' : ''}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb; font-size: 12px;">${contextPages.slice(0, 10).join(', ')}${contextPages.length > 10 ? '...' : ''}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center; font-weight: 600; color: #1E3A8A;">${assignment.total_pages || (primaryPages.length + contextPages.length)}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb; font-size: 11px; color: #6b7280;">${keywordsMatched.slice(0, 3).join(', ')}${keywordsMatched.length > 3 ? '...' : ''}</td>
                </tr>
            `;
        });

        html += '</tbody></table>';
    } else {
        html += `
            <div style="padding: 20px; background: #fef3c7; border-radius: 8px; margin-bottom: 25px; color: #92400e;">
                <strong>No targeted assignments:</strong> Document structure not found or all questions require exhaustive scan.
            </div>
        `;
    }

    // Keywords by Section
    html += `<h3 style="margin: 25px 0 15px 0; color: #1E3A8A; font-size: 16px;">All Keywords Searched by Section</h3>`;

    if (Object.keys(allKeywords).length > 0) {
        html += `<div style="display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 25px;">`;

        for (const [sectionId, keywords] of Object.entries(allKeywords)) {
            html += `
                <div style="flex: 1; min-width: 300px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 15px;">
                    <h4 style="margin: 0 0 10px 0; color: #1E3A8A; font-size: 14px;">${sectionId}</h4>
                    <div style="display: flex; flex-wrap: wrap; gap: 5px;">
                        ${(keywords || []).map(kw => `<span style="background: #E8EEF7; color: #1E3A8A; padding: 2px 8px; border-radius: 4px; font-size: 11px;">${kw}</span>`).join('')}
                    </div>
                </div>
            `;
        }

        html += '</div>';
    } else {
        html += `<p style="color: #6b7280; font-style: italic;">No keyword data available</p>`;
    }

    // Expert Recommended Keywords section
    const expertKeywords = data.expert_recommended_keywords || {};
    if (Object.keys(expertKeywords).length > 0) {
        html += `<h3 style="margin: 25px 0 15px 0; color: #1E3A8A; font-size: 16px;">Expert Recommended Keywords</h3>`;
        html += '<div style="display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 25px;">';

        for (const [expertName, keywords] of Object.entries(expertKeywords)) {
            html += `
                <div style="flex: 1; min-width: 280px; background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 15px;">
                    <h4 style="margin: 0 0 10px 0; color: #92400e; font-size: 14px;">${expertName}</h4>
                    <div style="display: flex; flex-wrap: wrap; gap: 5px;">
                        ${(keywords || []).map(kw => `<span style="background: #fff; color: #92400e; padding: 2px 8px; border-radius: 4px; font-size: 11px; border: 1px solid #f59e0b;">${kw}</span>`).join('')}
                    </div>
                </div>
            `;
        }
        html += '</div>';
    }

    // Efficiency Summary
    html += `
        <h3 style="margin: 25px 0 15px 0; color: #1E3A8A; font-size: 16px;">Efficiency Summary</h3>
        <table style="width: 50%; border-collapse: collapse; margin-bottom: 25px;">
            <tbody>
                <tr>
                    <td style="padding: 10px; font-weight: 600; background: #dcfce7; border: 1px solid #e5e7eb; width: 200px;">Estimated Page Reduction</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb; font-weight: 600; color: #166534;">${reduction}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; font-weight: 600; background: #f9fafb; border: 1px solid #e5e7eb;">Questions Requiring Full Scan</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">${unassigned.length}</td>
                </tr>
            </tbody>
        </table>
    `;

    document.getElementById('fv-optimizedScanContent').innerHTML = html;
}

function renderFullViewUnansweredPassTab() {
    if (!currentUnansweredPassData || Object.keys(currentUnansweredPassData).length === 0) {
        document.getElementById('fv-unansweredPassContent').innerHTML = `
            <div style="text-align: center; padding: 60px; color: #9ca3af;">
                <p style="font-size: 18px; margin-bottom: 10px;">Stage not Processed by User</p>
                <p style="font-size: 14px;">Unanswered Questions Pass was not run for this analysis</p>
            </div>
        `;
        return;
    }

    const data = currentUnansweredPassData;
    const questionsProcessed = data.questions_processed || [];
    const answersFound = data.answers_found || 0;
    const totalQuestions = data.total_questions || questionsProcessed.length;

    let html = `
        <div style="background: linear-gradient(135deg, #f59e0b, #d97706); color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 8px 0; font-size: 16px;">V2 Pipeline - Unanswered Questions Pass</h3>
            <p style="margin: 0; opacity: 0.9; font-size: 13px;">Second pass focused on questions that remained unanswered after exhaustive scan</p>
        </div>

        <div style="background: #fef3c7; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <div style="display: flex; gap: 30px;">
                <div>
                    <span style="font-weight: 600; color: #92400e;">Questions Processed:</span>
                    <span style="margin-left: 5px;">${totalQuestions}</span>
                </div>
                <div>
                    <span style="font-weight: 600; color: #92400e;">New Answers Found:</span>
                    <span style="margin-left: 5px; color: #22c55e; font-weight: 600;">${answersFound}</span>
                </div>
            </div>
        </div>
    `;

    if (questionsProcessed.length > 0) {
        html += `
            <h3 style="margin: 0 0 15px 0; color: #1E3A8A; font-size: 16px;">Questions Reprocessed</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                <thead>
                    <tr style="background: #1E3A8A; color: white;">
                        <th style="padding: 12px; text-align: left; font-weight: 600;">Question</th>
                        <th style="padding: 12px; text-align: left; font-weight: 600;">Section</th>
                        <th style="padding: 12px; text-align: center; font-weight: 600;">Found Answer</th>
                    </tr>
                </thead>
                <tbody>
        `;

        questionsProcessed.forEach((q, idx) => {
            const isAlt = idx % 2 === 1;
            html += `
                <tr style="${isAlt ? 'background: #f9fafb;' : ''}">
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">${q.question || 'Unknown'}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">${q.section || ''}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center;">
                        <span style="background: ${q.found ? '#dcfce7' : '#fee2e2'}; color: ${q.found ? '#166534' : '#991b1b'}; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">
                            ${q.found ? 'Yes' : 'No'}
                        </span>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
    }

    document.getElementById('fv-unansweredPassContent').innerHTML = html;
}

function renderFullViewRagTab() {
    if (!currentRagData || Object.keys(currentRagData).length === 0) {
        document.getElementById('fv-ragContent').innerHTML = `
            <div style="text-align: center; padding: 60px; color: #9ca3af;">
                <p style="font-size: 18px; margin-bottom: 10px;">Stage not Processed by User</p>
                <p style="font-size: 14px;">Deep RAG analysis was not run for this analysis</p>
            </div>
        `;
        return;
    }

    const data = currentRagData;
    const questionsProcessed = data.questions_processed || [];
    const answersFound = data.answers_found || 0;
    const totalQuestions = data.total_questions || questionsProcessed.length;
    const chunksSearched = data.chunks_searched || 0;

    let html = `
        <div style="background: linear-gradient(135deg, #dc2626, #b91c1c); color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px;">
            <h3 style="margin: 0 0 8px 0; font-size: 16px;">V2 Pipeline - Deep RAG Analysis</h3>
            <p style="margin: 0; opacity: 0.9; font-size: 13px;">Final pass using Retrieval-Augmented Generation for remaining unanswered questions</p>
        </div>

        <div style="background: #fee2e2; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
            <div style="display: flex; gap: 30px; flex-wrap: wrap;">
                <div>
                    <span style="font-weight: 600; color: #991b1b;">Questions Processed:</span>
                    <span style="margin-left: 5px;">${totalQuestions}</span>
                </div>
                <div>
                    <span style="font-weight: 600; color: #991b1b;">New Answers Found:</span>
                    <span style="margin-left: 5px; color: #22c55e; font-weight: 600;">${answersFound}</span>
                </div>
                <div>
                    <span style="font-weight: 600; color: #991b1b;">Chunks Searched:</span>
                    <span style="margin-left: 5px;">${chunksSearched}</span>
                </div>
            </div>
        </div>
    `;

    if (questionsProcessed.length > 0) {
        html += `
            <h3 style="margin: 0 0 15px 0; color: #1E3A8A; font-size: 16px;">RAG Search Results</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                <thead>
                    <tr style="background: #1E3A8A; color: white;">
                        <th style="padding: 12px; text-align: left; font-weight: 600;">Question</th>
                        <th style="padding: 12px; text-align: left; font-weight: 600;">Section</th>
                        <th style="padding: 12px; text-align: center; font-weight: 600;">Similarity</th>
                        <th style="padding: 12px; text-align: center; font-weight: 600;">Found Answer</th>
                    </tr>
                </thead>
                <tbody>
        `;

        questionsProcessed.forEach((q, idx) => {
            const isAlt = idx % 2 === 1;
            const similarity = q.similarity ? (q.similarity * 100).toFixed(1) + '%' : 'N/A';
            html += `
                <tr style="${isAlt ? 'background: #f9fafb;' : ''}">
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">${q.question || 'Unknown'}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb;">${q.section || ''}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center;">${similarity}</td>
                    <td style="padding: 10px; border: 1px solid #e5e7eb; text-align: center;">
                        <span style="background: ${q.found ? '#dcfce7' : '#fee2e2'}; color: ${q.found ? '#166534' : '#991b1b'}; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600;">
                            ${q.found ? 'Yes' : 'No'}
                        </span>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
    }

    document.getElementById('fv-ragContent').innerHTML = html;
}

