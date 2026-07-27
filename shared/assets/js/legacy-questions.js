// ============================================================================
// QUESTION MANAGER - Full CRUD functionality
// ============================================================================

let questionManagerOpen = false;
let editingQuestionId = null;

function openQuestionManager() {
    questionManagerOpen = true;
    renderQuestionManager();
    document.getElementById('questionManagerModal').style.display = 'flex';
}

function closeQuestionManager() {
    questionManagerOpen = false;
    document.getElementById('questionManagerModal').style.display = 'none';
    editingQuestionId = null;
    // Refresh main question sections display
    displayQuestionSections();
    updateActiveQuestionCount();
}

function renderQuestionManager() {
    const container = document.getElementById('questionManagerContent');

    let html = `
        <div style="margin-bottom: 20px; display: flex; gap: 10px; flex-wrap: wrap;">
            <button class="btn" onclick="showUploadDialog()">📤 Upload from Spreadsheet</button>
            <button class="btn btn-secondary" onclick="showAddSectionDialog()">➕ Add Section</button>
            <button class="btn btn-secondary" onclick="downloadQuestionsTemplate()">📥 Download Template</button>
        </div>

        <div id="uploadArea" style="display: none; margin-bottom: 20px; padding: 20px; border: 2px dashed #5B7FCC; border-radius: 8px; background: #f8f9ff;">
            <h4 style="margin-bottom: 10px;">Upload Questions from Spreadsheet</h4>
            <p style="color: #666; margin-bottom: 10px;">Upload a CSV or Excel file with columns: section_id, section_name, question_id, question_text, required, expected_type, enabled</p>
            <input type="file" id="questionUploadInput" accept=".csv,.xlsx,.xls" onchange="handleQuestionUpload(event)" style="margin-bottom: 10px;">
            <button class="btn btn-secondary" onclick="document.getElementById('uploadArea').style.display='none'">Cancel</button>
        </div>
    `;

    // Render sections
    questionConfig.sections.forEach((section, sectionIndex) => {
        const enabledCount = section.questions.filter(q => q.enabled !== false).length;
        const totalCount = section.questions.length;

        html += `
            <div class="qm-section" style="margin-bottom: 15px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden;">
                <div class="qm-section-header" style="background: linear-gradient(135deg, #1E3A8A, #5B7FCC); color: white; padding: 15px; display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <button onclick="toggleSectionExpand('${section.section_id}')" style="background: none; border: none; color: white; cursor: pointer; font-size: 1.2em;">
                            <span id="expand-${section.section_id}">▶</span>
                        </button>
                        <strong>${section.section_name}</strong>
                        <span style="background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 12px; font-size: 12px;">${enabledCount}/${totalCount} enabled</span>
                    </div>
                    <div style="display: flex; gap: 5px;">
                        <button onclick="showAddQuestionDialog('${section.section_id}')" style="background: rgba(255,255,255,0.2); border: none; color: white; padding: 5px 10px; border-radius: 4px; cursor: pointer;">➕ Add Q</button>
                        <button onclick="editSection('${section.section_id}')" style="background: rgba(255,255,255,0.2); border: none; color: white; padding: 5px 10px; border-radius: 4px; cursor: pointer;">✏️</button>
                        <button onclick="deleteSection('${section.section_id}')" style="background: rgba(220,53,69,0.8); border: none; color: white; padding: 5px 10px; border-radius: 4px; cursor: pointer;">🗑️</button>
                    </div>
                </div>
                <div id="questions-${section.section_id}" style="display: none; background: white;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <thead>
                            <tr style="background: #f8f9fa;">
                                <th style="padding: 10px; text-align: center; width: 60px;">Enabled</th>
                                <th style="padding: 10px; text-align: left; width: 60px;">ID</th>
                                <th style="padding: 10px; text-align: left;">Question</th>
                                <th style="padding: 10px; text-align: center; width: 80px;">Required</th>
                                <th style="padding: 10px; text-align: center; width: 100px;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
        `;

        section.questions.forEach((q, qIndex) => {
            const isEnabled = q.enabled !== false;
            html += `
                <tr style="border-bottom: 1px solid #eee; ${!isEnabled ? 'opacity: 0.5; background: #f5f5f5;' : ''}">
                    <td style="padding: 10px; text-align: center;">
                        <input type="checkbox" ${isEnabled ? 'checked' : ''} onchange="toggleQuestionEnabled('${q.id}')" style="width: 18px; height: 18px; cursor: pointer;">
                    </td>
                    <td style="padding: 10px; font-weight: bold; color: #5B7FCC;">${q.id}</td>
                    <td style="padding: 10px;" id="qtext-${q.id}">
                        ${editingQuestionId === q.id ? `
                            <input type="text" id="edit-input-${q.id}" value="${q.text.replace(/"/g, '&quot;')}" style="width: 100%; padding: 8px; border: 2px solid #5B7FCC; border-radius: 4px;">
                        ` : q.text}
                    </td>
                    <td style="padding: 10px; text-align: center;">
                        <span style="color: ${q.required ? '#28a745' : '#6c757d'};">${q.required ? 'Yes' : 'No'}</span>
                    </td>
                    <td style="padding: 10px; text-align: center;">
                        ${editingQuestionId === q.id ? `
                            <button onclick="saveQuestionEdit('${q.id}')" style="background: #28a745; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; margin-right: 5px;">Save</button>
                            <button onclick="cancelQuestionEdit()" style="background: #6c757d; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;">Cancel</button>
                        ` : `
                            <button onclick="startEditQuestion('${q.id}')" style="background: #5B7FCC; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; margin-right: 5px;">✏️</button>
                            <button onclick="deleteQuestion('${q.id}')" style="background: #dc3545; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer;">🗑️</button>
                        `}
                    </td>
                </tr>
            `;
        });

        html += `
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
}

function toggleSectionExpand(sectionId) {
    const questionsDiv = document.getElementById(`questions-${sectionId}`);
    const expandIcon = document.getElementById(`expand-${sectionId}`);

    if (questionsDiv.style.display === 'none') {
        questionsDiv.style.display = 'block';
        expandIcon.textContent = '▼';
    } else {
        questionsDiv.style.display = 'none';
        expandIcon.textContent = '▶';
    }
}

async function toggleQuestionEnabled(questionId) {
    try {
        const resp = await fetch(`/api/config/questions/question/${questionId}/toggle`, { method: 'POST' });
        const data = await resp.json();

        if (data.success) {
            // Update local state
            for (const section of questionConfig.sections) {
                const q = section.questions.find(q => q.id === questionId);
                if (q) {
                    q.enabled = data.enabled;
                    break;
                }
            }
            renderQuestionManager();
            Logger.info(`Question ${questionId} ${data.enabled ? 'enabled' : 'disabled'}`);
        } else {
            Logger.error(`Failed to toggle question: ${data.error}`);
        }
    } catch (error) {
        Logger.error(`Error toggling question: ${error.message}`);
    }
}

function startEditQuestion(questionId) {
    editingQuestionId = questionId;
    renderQuestionManager();
    // Focus the input
    setTimeout(() => {
        const input = document.getElementById(`edit-input-${questionId}`);
        if (input) input.focus();
    }, 50);
}

function cancelQuestionEdit() {
    editingQuestionId = null;
    renderQuestionManager();
}

async function saveQuestionEdit(questionId) {
    const input = document.getElementById(`edit-input-${questionId}`);
    if (!input) return;

    const newText = input.value.trim();
    if (!newText) {
        alert('Question text cannot be empty');
        return;
    }

    try {
        const resp = await fetch(`/api/config/questions/question/${questionId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: newText })
        });
        const data = await resp.json();

        if (data.success) {
            // Update local state
            for (const section of questionConfig.sections) {
                const q = section.questions.find(q => q.id === questionId);
                if (q) {
                    q.text = newText;
                    break;
                }
            }
            editingQuestionId = null;
            renderQuestionManager();
            Logger.success(`Question ${questionId} updated`);
        } else {
            Logger.error(`Failed to update question: ${data.error}`);
        }
    } catch (error) {
        Logger.error(`Error updating question: ${error.message}`);
    }
}

async function deleteQuestion(questionId) {
    if (!confirm(`Delete question ${questionId}? This cannot be undone.`)) return;

    try {
        const resp = await fetch(`/api/config/questions/question/${questionId}`, { method: 'DELETE' });
        const data = await resp.json();

        if (data.success) {
            // Update local state
            for (const section of questionConfig.sections) {
                section.questions = section.questions.filter(q => q.id !== questionId);
            }
            renderQuestionManager();
            Logger.success(`Question ${questionId} deleted`);
        } else {
            Logger.error(`Failed to delete question: ${data.error}`);
        }
    } catch (error) {
        Logger.error(`Error deleting question: ${error.message}`);
    }
}

async function deleteSection(sectionId) {
    const section = questionConfig.sections.find(s => s.section_id === sectionId);
    if (!confirm(`Delete section "${section?.section_name}" and all its questions? This cannot be undone.`)) return;

    try {
        const resp = await fetch(`/api/config/questions/section/${sectionId}`, { method: 'DELETE' });
        const data = await resp.json();

        if (data.success) {
            questionConfig.sections = questionConfig.sections.filter(s => s.section_id !== sectionId);
            renderQuestionManager();
            Logger.success(`Section ${sectionId} deleted`);
        } else {
            Logger.error(`Failed to delete section: ${data.error}`);
        }
    } catch (error) {
        Logger.error(`Error deleting section: ${error.message}`);
    }
}

function showUploadDialog() {
    document.getElementById('uploadArea').style.display = 'block';
}

async function handleQuestionUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        Logger.info(`Uploading questions from ${file.name}...`);
        const resp = await fetch('/api/config/questions/upload', {
            method: 'POST',
            body: formData
        });
        const data = await resp.json();

        if (data.success) {
            // Preview the uploaded config
            if (confirm(`Parsed ${data.config.totalQuestions} questions in ${data.config.sections.length} sections. Replace current configuration?`)) {
                // Save the uploaded config
                const saveResp = await fetch('/api/config/questions', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sections: data.config.sections })
                });
                const saveData = await saveResp.json();

                if (saveData.success) {
                    questionConfig = data.config;
                    renderQuestionManager();
                    Logger.success(`Uploaded and saved ${data.config.totalQuestions} questions`);
                } else {
                    Logger.error(`Failed to save: ${saveData.error}`);
                }
            }
        } else {
            Logger.error(`Upload failed: ${data.error}`);
            alert(`Upload failed: ${data.error}`);
        }
    } catch (error) {
        Logger.error(`Error uploading: ${error.message}`);
        alert(`Error uploading: ${error.message}`);
    }

    document.getElementById('uploadArea').style.display = 'none';
    event.target.value = '';
}

function showAddSectionDialog() {
    const sectionId = prompt('Enter Section ID (e.g., "custom_section"):');
    if (!sectionId) return;

    const sectionName = prompt('Enter Section Name (e.g., "Custom Questions"):');
    if (!sectionName) return;

    addSection(sectionId.trim(), sectionName.trim());
}

async function addSection(sectionId, sectionName) {
    try {
        const resp = await fetch('/api/config/questions/section', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                section_id: sectionId,
                section_name: sectionName,
                description: '',
                questions: []
            })
        });
        const data = await resp.json();

        if (data.success) {
            questionConfig.sections.push({
                section_id: sectionId,
                section_name: sectionName,
                description: '',
                questions: []
            });
            renderQuestionManager();
            Logger.success(`Section "${sectionName}" added`);
        } else {
            Logger.error(`Failed to add section: ${data.error}`);
            alert(`Failed to add section: ${data.error}`);
        }
    } catch (error) {
        Logger.error(`Error adding section: ${error.message}`);
    }
}

function showAddQuestionDialog(sectionId) {
    const questionText = prompt('Enter the question text:');
    if (!questionText) return;

    const isRequired = confirm('Is this question required?');

    addQuestion(sectionId, questionText.trim(), isRequired);
}

async function addQuestion(sectionId, text, required) {
    try {
        const resp = await fetch('/api/config/questions/question', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                section_id: sectionId,
                text: text,
                required: required,
                expected_type: 'string',
                enabled: true
            })
        });
        const data = await resp.json();

        if (data.success) {
            // Find section and add question
            const section = questionConfig.sections.find(s => s.section_id === sectionId);
            if (section) {
                section.questions.push({
                    id: data.question_id,
                    text: text,
                    required: required,
                    expected_type: 'string',
                    enabled: true
                });
            }
            renderQuestionManager();
            Logger.success(`Question ${data.question_id} added to ${sectionId}`);
        } else {
            Logger.error(`Failed to add question: ${data.error}`);
            alert(`Failed to add question: ${data.error}`);
        }
    } catch (error) {
        Logger.error(`Error adding question: ${error.message}`);
    }
}

function editSection(sectionId) {
    const section = questionConfig.sections.find(s => s.section_id === sectionId);
    if (!section) return;

    const newName = prompt('Enter new section name:', section.section_name);
    if (!newName || newName === section.section_name) return;

    updateSection(sectionId, { section_name: newName.trim() });
}

async function updateSection(sectionId, updates) {
    try {
        const resp = await fetch(`/api/config/questions/section/${sectionId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updates)
        });
        const data = await resp.json();

        if (data.success) {
            // Update local state
            const section = questionConfig.sections.find(s => s.section_id === sectionId);
            if (section) {
                Object.assign(section, updates);
            }
            renderQuestionManager();
            Logger.success(`Section ${sectionId} updated`);
        } else {
            Logger.error(`Failed to update section: ${data.error}`);
        }
    } catch (error) {
        Logger.error(`Error updating section: ${error.message}`);
    }
}

function downloadQuestionsTemplate() {
    const template = `section_id,section_name,question_id,question_text,required,expected_type,enabled
general_info,General Project Information,Q1,What is the project name and location?,true,string,true
general_info,General Project Information,Q2,What is the total project duration?,true,string,true
materials,Materials & Standards,Q11,What material specifications are required?,true,technical_spec,true
materials,Materials & Standards,Q12,What ASTM standards apply?,false,technical_spec,true`;

    const blob = new Blob([template], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'questions_template.csv';
    a.click();
    URL.revokeObjectURL(url);
    Logger.info('Template downloaded');
}

// ============================================================================
// QUESTION SET HUB - Load / Generate / Manage
// ============================================================================

let pendingAdditionalSections = [];
let pendingAIInput = '';

function openQuestionSetHub() {
    document.getElementById('questionSetHubModal').style.display = 'flex';
    showHubHome();
}

function closeQuestionSetHub() {
    document.getElementById('questionSetHubModal').style.display = 'none';
    displayQuestionSections();
    updateActiveQuestionCount();
}

function showHubHome() {
    document.getElementById('hubContent').innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 15px;">
            <button class="hub-option-btn" onclick="showAIGenerateView()">
                <span style="font-size: 2em;">🤖</span>
                <div>
                    <strong>Generate AI Question Set</strong>
                    <p>Type or paste your questions and context — AI converts them into a structured question set instantly.</p>
                </div>
            </button>
            <button class="hub-option-btn" onclick="loadCIPPQuestionSet()">
                <span style="font-size: 2em;">📋</span>
                <div>
                    <strong>CIPP Sample Set</strong>
                    <p>Load the built-in 100-question CIPP lining / municipal infrastructure question set.</p>
                </div>
            </button>
            <button class="hub-option-btn" onclick="closeQuestionSetHub(); openQuestionManager();">
                <span style="font-size: 2em;">✏️</span>
                <div>
                    <strong>Manage / Edit Questions</strong>
                    <p>Add, edit, delete, or upload sections and questions manually.</p>
                </div>
            </button>
        </div>
    `;
}

function showAIGenerateView() {
    document.getElementById('hubContent').innerHTML = `
        <div style="margin-bottom: 15px;">
            <button onclick="showHubHome()" style="background: none; border: none; color: #5B7FCC; cursor: pointer; font-size: 14px;">← Back</button>
        </div>
        <h3 style="margin: 0 0 10px; color: #1E3A8A;">🤖 Generate AI Question Set</h3>
        <p style="color: #555; margin-bottom: 10px; font-size: 14px;">
            Paste your questions, describe what you're looking for, or provide a mix of both. The AI will preserve every specific question you provide and organize everything into a structured set ready to use immediately.
        </p>
        ${currentFile ? `<div style="background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; padding: 8px 12px; margin-bottom: 12px; font-size: 13px; color: #1e40af;">
            📄 <strong>${currentFile.name}</strong> is loaded — the AI will scan its title, table of contents, glossary, and appendix to improve question relevance.
        </div>` : ''}
        <textarea id="aiQuestionInput"
            placeholder="Examples:&#10;- What are the payment terms and penalty clauses?&#10;- Who are the parties and what are their obligations?&#10;- I need questions for reviewing a commercial real estate lease agreement, covering rent, maintenance, termination, and liability&#10;- Generate questions for a vendor services contract focusing on deliverables, SLAs, IP ownership, and dispute resolution&#10;&#10;Paste your own questions, a description of what you need, or both — the AI will organize everything into sections automatically."
            style="width: 100%; min-height: 160px; padding: 12px; border: 2px solid #ddd; border-radius: 8px; font-size: 14px; resize: vertical; box-sizing: border-box; font-family: inherit; color: #222;"
        ></textarea>
        <div style="margin-top: 12px; display: flex; gap: 10px; align-items: center;">
            <button class="btn" id="generateAIBtn" onclick="generateAIQuestions()" style="min-width: 160px;">
                🤖 Generate Question Set
            </button>
            <span id="aiGenerateStatus" style="font-size: 13px; color: #666;"></span>
        </div>
        <div id="aiGenerateResult" style="margin-top: 15px;"></div>
    `;
}

async function loadCIPPQuestionSet() {
    const btn = event.currentTarget;
    btn.disabled = true;
    btn.style.opacity = '0.7';
    try {
        const resp = await fetch('/api/config/questions');
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Failed to load');
        questionConfig = data.config;
        questionConfig.sections.forEach(s => { if (s.enabled === undefined) s.enabled = true; });
        displayQuestionSections();
        updateActiveQuestionCount();
        Logger.success(`✅ Loaded CIPP question set: ${questionConfig.totalQuestions} questions in ${questionConfig.sections.length} sections`);
        closeQuestionSetHub();
    } catch (e) {
        Logger.error('Failed to load CIPP question set: ' + e.message);
        btn.disabled = false;
        btn.style.opacity = '1';
    }
}

async function generateAIQuestions() {
    const input = document.getElementById('aiQuestionInput').value.trim();
    if (!input) {
        document.getElementById('aiGenerateStatus').textContent = 'Please enter your questions or context first.';
        return;
    }

    const btn = document.getElementById('generateAIBtn');
    const status = document.getElementById('aiGenerateStatus');
    const resultDiv = document.getElementById('aiGenerateResult');

    btn.disabled = true;
    btn.textContent = '⏳ Generating...';
    status.textContent = 'BidBrief is building your question set…';
    resultDiv.innerHTML = '';
    pendingAIInput = input;

    try {
        let resp;
        if (currentFile) {
            // Ask for a one-line description of what the doc should shape —
            // it feeds the Persona Architect and per-section rationale.
            const sourceIntent = (window.prompt(
                'In one short line: what should this file be used for when creating the question set?\n' +
                '(e.g. "derive questions from this inspection standard") — leave blank to skip.', '') || '').trim();
            // Send file alongside user input so backend can extract doc context
            const formData = new FormData();
            formData.append('user_input', input);
            formData.append('file', currentFile);
            if (sourceIntent) formData.append('source_intent', sourceIntent);
            resp = await fetch('/api/config/questions/generate', {
                method: 'POST',
                body: formData
            });
            status.textContent = 'BidBrief is reading your document and building the question set…';
        } else {
            resp = await fetch('/api/config/questions/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_input: input })
            });
        }
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Generation failed');

        // Import immediately into question config
        const generated = data.config;
        questionConfig = generated;
        questionConfig.sections.forEach(s => { if (s.enabled === undefined) s.enabled = true; });

        // Save to backend (PUT — the correct method for this route)
        await fetch('/api/config/questions', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sections: questionConfig.sections })
        });

        displayQuestionSections();
        updateActiveQuestionCount();

        btn.disabled = false;
        btn.textContent = '🤖 Generate Question Set';
        status.textContent = '';

        const qCount = questionConfig.sections.reduce((s, sec) => s + sec.questions.length, 0);
        const sCount = questionConfig.sections.length;

        // Build inline preview of generated sections/questions.
        // The bespoke expert panel (Persona Architect) leads the preview.
        let previewHtml = '';
        if (data.generation_personas && data.generation_personas.length) {
            previewHtml += `
                <div style="margin-bottom: 10px; padding: 8px 12px; background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 6px;">
                    <strong style="color: #3730a3; font-size: 12px;">Built by your expert panel:</strong>
                    <span style="color: #4338ca; font-size: 12px;">
                        ${data.generation_personas.map(p => p.name).join(' · ')}
                    </span>
                </div>`;
        }
        questionConfig.sections.forEach(sec => {
            previewHtml += `
                <div style="margin-bottom: 10px; border: 1px solid #d1fae5; border-radius: 6px; overflow: hidden;">
                    <div style="background: #ecfdf5; padding: 8px 12px; border-bottom: 1px solid #d1fae5;">
                        <strong style="color: #065f46; font-size: 13px;">${sec.section_name}</strong>
                        <span style="color: #6b7280; font-size: 11px; margin-left: 8px;">${sec.questions.length} question${sec.questions.length !== 1 ? 's' : ''}</span>
                        ${sec.section_summary ? `<div style="color: #047857; font-size: 12px; font-style: italic; margin-top: 4px;">${sec.section_summary}</div>` : ''}
                    </div>
                    <ul style="margin: 0; padding: 8px 12px 8px 28px; list-style: disc;">
                        ${sec.questions.map(q => `<li style="color: #222; font-size: 13px; margin-bottom: 3px;">${q.text}</li>`).join('')}
                    </ul>
                </div>`;
        });

        resultDiv.innerHTML = `
            <div style="background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 15px;">
                <p style="margin: 0 0 10px; color: #166534; font-weight: 600;">
                    ✅ Imported ${qCount} questions across ${sCount} section${sCount !== 1 ? 's' : ''}.
                </p>
                <div style="max-height: 240px; overflow-y: auto; margin-bottom: 12px; border-radius: 6px;">
                    ${previewHtml}
                </div>
                <p style="margin: 0 0 12px; color: #444; font-size: 14px; border-top: 1px solid #86efac; padding-top: 12px;">
                    Would you also like to see AI-suggested additional questions based on your context?
                    (Up to 3 extra sections with 10 questions each, all relevant to your topic.)
                </p>
                <div style="display: flex; gap: 10px;">
                    <button class="btn" id="yesAdditionalBtn" onclick="fetchAdditionalQuestions()">
                        Yes, show me more questions
                    </button>
                    <button class="btn btn-secondary" onclick="closeQuestionSetHub()">
                        No thanks, use these
                    </button>
                </div>
                <div id="additionalQuestionsArea" style="margin-top: 15px;"></div>
            </div>
        `;
    } catch (e) {
        btn.disabled = false;
        btn.textContent = '🤖 Generate Question Set';
        status.textContent = '';
        resultDiv.innerHTML = `<div style="color: #dc2626; padding: 10px;">❌ Error: ${e.message}</div>`;
        Logger.error('AI generation failed: ' + e.message);
    }
}

async function fetchAdditionalQuestions() {
    const btn = document.getElementById('yesAdditionalBtn');
    const area = document.getElementById('additionalQuestionsArea');
    btn.disabled = true;
    btn.textContent = '⏳ Generating additional questions…';

    try {
        const resp = await fetch('/api/config/questions/generate-additional', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_input: pendingAIInput,
                existing_sections: questionConfig.sections
            })
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Generation failed');

        const extra = data.additional_sections;
        if (!extra || extra.length === 0) {
            area.innerHTML = '<p style="color: #666; font-size: 14px;">No additional questions were generated.</p>';
            return;
        }

        // Store for applyAdditionalQuestions()
        pendingAdditionalSections = extra;

        // Render preview with select-all checkboxes per section
        let html = `<h4 style="margin: 0 0 10px; color: #1E3A8A;">Additional Suggested Questions</h4>
            <p style="color: #444; font-size: 13px; margin-bottom: 12px;">Select the sections and questions you'd like to add:</p>`;

        extra.forEach((sec, si) => {
            html += `
                <div style="margin-bottom: 12px; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; background: #fff;">
                    <div style="background: #f0f4ff; padding: 10px 14px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid #ddd;">
                        <input type="checkbox" id="addSec_${si}" checked style="width: 16px; height: 16px; flex-shrink: 0;">
                        <strong style="color: #1E3A8A;">${sec.section_name}</strong>
                        <span style="color: #666; font-size: 12px;">(${sec.questions.length} questions)</span>
                    </div>
                    <div style="padding: 10px 14px; background: #fff;">`;
            sec.questions.forEach((q, qi) => {
                html += `
                        <label style="display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; font-size: 13px; cursor: pointer; color: #222;">
                            <input type="checkbox" class="addQ_${si}" data-qi="${qi}" checked style="margin-top: 2px; flex-shrink: 0;">
                            <span style="color: #222;">${q.text}</span>
                        </label>`;
            });
            html += `</div></div>`;
        });

        html += `
            <div style="display: flex; gap: 10px; margin-top: 10px;">
                <button class="btn" onclick="applyAdditionalQuestions()">
                    Add Selected Questions
                </button>
                <button class="btn btn-secondary" onclick="closeQuestionSetHub()">
                    Skip & use current set
                </button>
            </div>`;

        area.innerHTML = html;
        btn.style.display = 'none';
    } catch (e) {
        area.innerHTML = `<div style="color: #dc2626;">❌ Error: ${e.message}</div>`;
        btn.disabled = false;
        btn.textContent = 'Yes, show me more questions';
    }
}

async function applyAdditionalQuestions() {
    const extraSections = pendingAdditionalSections;
    // Collect only selected sections/questions
    extraSections.forEach((sec, si) => {
        const secChecked = document.getElementById(`addSec_${si}`)?.checked;
        if (!secChecked) return;
        const selectedQs = [...document.querySelectorAll(`.addQ_${si}:checked`)].map(cb => {
            return sec.questions[parseInt(cb.dataset.qi)];
        });
        if (selectedQs.length === 0) return;
        // Merge into existing config or add as new section
        const existing = questionConfig.sections.find(s => s.section_id === sec.section_id);
        if (existing) {
            selectedQs.forEach(q => {
                if (!existing.questions.find(eq => eq.id === q.id)) {
                    existing.questions.push(q);
                }
            });
        } else {
            questionConfig.sections.push({ ...sec, questions: selectedQs, enabled: true });
        }
    });

    // Save merged config (PUT — the correct method for this route)
    await fetch('/api/config/questions', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sections: questionConfig.sections })
    });

    displayQuestionSections();
    updateActiveQuestionCount();
    const total = questionConfig.sections.reduce((s, sec) => s + sec.questions.length, 0);
    Logger.success(`✅ Question set finalized: ${total} questions across ${questionConfig.sections.length} sections`);
    closeQuestionSetHub();
}

