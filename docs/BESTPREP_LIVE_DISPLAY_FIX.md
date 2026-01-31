# BestPrep Live Display Fix - Investigation & Implementation Plan

## Issue Summary

**Observed Behavior:** During BestPrep mode live analysis, answers/pages are being REPLACED instead of ACCUMULATED across windows. Screenshots show:
- Earlier: Q8 page 58, Q9 page 25, Q10 page 58
- Later: Q8 page 179, Q9 page 172, Q10 page 145 (completely different, NOT accumulated)

**Expected Behavior:** Questions should show ALL pages accumulated across windows:
- Q8 should show pages: 58, 179 (both)
- Q9 should show pages: 25, 172 (both)
- Q10 should show pages: 58, 145 (both)

---

## Root Cause Analysis

### Issue 1: Backend - Wrong data sent in `window_complete` event

**File:** `services/hotdog/orchestrator.py` (lines 414-469)

**Problem:** For BestPrep mode, the backend sends:
1. `accumulated_so_far` - Only contains the **best single fragment** (highest confidence), not all fragments
2. `new_answers` - Only contains **current window's answers**, not cumulative data

```python
# Lines 414-434 - Only sends BEST fragment, not all
accumulated_so_far = {}
for qid, ca in self.bestprep_accumulator.get_all_cumulative_answers().items():
    if ca.fragments:
        best_frag = max(ca.fragments, key=lambda f: f.confidence)  # <-- ONLY BEST!
        mock_answer = Answer(
            text=best_frag.text,       # Only one fragment's text
            pages=best_frag.pages,     # Only one fragment's pages
            ...
        )

# Lines 446-460 - Only sends CURRENT WINDOW's answers
new_answers = []
for answer in window_result.answers.values():  # <-- ONLY THIS WINDOW!
    new_answers.append({
        'answer_text': answer.text,
        'pages': answer.pages,  # Only current window's pages
        ...
    })
```

### Issue 2: Frontend - Replaces instead of accumulates

**File:** `index.html` (lines 1536-1539)

**Problem:** The `updateUnitaryTableWithNewAnswers()` function REPLACES data:

```javascript
// Current code - REPLACES everything
allQuestions[answer.question_id].answer = answer.answer_text;  // REPLACES!
allQuestions[answer.question_id].pages = answer.pages;         // REPLACES!
allQuestions[answer.question_id].footnote = answer.footnote;   // REPLACES!
```

---

## Implementation Plan

### Fix 1: Backend - Send cumulative data for BestPrep mode

**File:** `services/hotdog/orchestrator.py`

**Changes needed in `window_complete` event (around line 445-469):**

For BestPrep mode, modify `new_answers` array to include CUMULATIVE data:

```python
# Build new_answers array - MODE AWARE
new_answers = []
if self.mode == AnalysisMode.BESTPREP:
    # BestPrep: Send CUMULATIVE data for each question
    for qid, ca in self.bestprep_accumulator.get_all_cumulative_answers().items():
        if ca.fragments:
            question = config.question_map.get(qid)
            if question:
                section = config.section_map.get(question.section_id)
                # Combine all fragment texts with separator
                combined_text = " [...] ".join([f.text for f in ca.fragments])
                new_answers.append({
                    'question_id': qid,
                    'question_text': question.text,
                    'section_id': question.section_id,
                    'section_name': section.name if section else question.section_id,
                    'answer_text': combined_text,  # All fragments combined
                    'pages': ca.all_pages,         # ALL pages across all fragments
                    'confidence': ca.highest_confidence,
                    'footnote': f"{ca.footnote_count} citations",  # Citation count
                    'fragment_count': ca.fragment_count,  # NEW: fragment count for display
                    'is_cumulative': True  # NEW: Flag for frontend
                })
else:
    # Bid/Spec: Send current window's answers (existing behavior)
    for answer in window_result.answers.values():
        # ... existing code ...
```

### Fix 2: Frontend - Handle cumulative data properly

**File:** `index.html`

**Option A: Backend sends cumulative (preferred)**
If backend sends cumulative data with `is_cumulative: true`, frontend just uses it directly:

```javascript
function updateUnitaryTableWithNewAnswers(newAnswers) {
    const updatedQuestionIds = [];

    newAnswers.forEach(answer => {
        if (allQuestions[answer.question_id]) {
            allQuestions[answer.question_id].status = 'found';

            if (currentAnalysisMode === 'bestprep' && answer.is_cumulative) {
                // BestPrep: Data is already cumulative from backend
                allQuestions[answer.question_id].answer = answer.answer_text;
                allQuestions[answer.question_id].pages = answer.pages;
                allQuestions[answer.question_id].footnote = answer.footnote;
                allQuestions[answer.question_id].fragment_count = answer.fragment_count;
            } else {
                // Bid/Spec: Replace behavior (current behavior)
                allQuestions[answer.question_id].answer = answer.answer_text;
                allQuestions[answer.question_id].pages = answer.pages;
                allQuestions[answer.question_id].footnote = answer.footnote;
            }

            updatedQuestionIds.push(answer.question_id);
            // ... rest of footnote handling
        }
    });
    // ... rest of function
}
```

**Option B: Frontend accumulates locally**
If backend sends per-window data, frontend accumulates:

```javascript
function updateUnitaryTableWithNewAnswers(newAnswers) {
    newAnswers.forEach(answer => {
        if (allQuestions[answer.question_id]) {
            const q = allQuestions[answer.question_id];
            q.status = 'found';

            if (currentAnalysisMode === 'bestprep') {
                // BestPrep: ACCUMULATE pages
                const existingPages = q.pages || [];
                const newPages = answer.pages || [];
                q.pages = [...new Set([...existingPages, ...newPages])].sort((a,b) => a-b);

                // Append answer fragment
                if (q.answer) {
                    q.answer = q.answer + ' [...] ' + answer.answer_text;
                } else {
                    q.answer = answer.answer_text;
                }

                // Track fragment count
                q.fragment_count = (q.fragment_count || 0) + 1;
            } else {
                // Bid/Spec: REPLACE (existing behavior)
                q.answer = answer.answer_text;
                q.pages = answer.pages;
            }
            // ... footnote handling
        }
    });
}
```

**Recommendation:** Use Option A (backend sends cumulative) because:
1. Backend already has the `AppendOnlyAccumulator` with `all_pages` property
2. Avoids duplicating accumulation logic
3. Ensures consistency between live display and final results

---

## Additional Requested Changes

### Change 1: Move mode selector to top (under PDF upload)

**File:** `index.html`

**Current location:** Lines 461-481 (under "Question Configuration" section)
**New location:** Lines 425-430 (after "Document Upload" section, before "Question Configuration")

Move the entire mode selector `<div class="section">...</div>` block.

### Change 2: Add view modal on analysis page

**File:** `index.html`

**Implementation:**
1. Add a "View Details" button/link in each row of the unitary table
2. Create a modal similar to `questionManagerModal` pattern
3. Modal shows:
   - Question text
   - All answer fragments (for BestPrep)
   - All page citations with links
   - All footnotes with context
   - Confidence levels per fragment

```html
<!-- Add modal HTML near other modals (line ~2191) -->
<div id="answerDetailModal" style="display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 2000; justify-content: center; align-items: center;">
    <div style="background: white; padding: 30px; border-radius: 10px; max-width: 800px; max-height: 90vh; overflow-y: auto; width: 95%;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <h3 id="answerDetailTitle" style="color: #1E3A8A; margin: 0;">Answer Details</h3>
            <button onclick="closeAnswerDetailModal()" style="background: none; border: none; font-size: 1.5em; cursor: pointer;">&times;</button>
        </div>
        <div id="answerDetailContent"></div>
    </div>
</div>
```

Add JavaScript:
```javascript
function openAnswerDetailModal(questionId) {
    const q = allQuestions[questionId];
    if (!q) return;

    document.getElementById('answerDetailTitle').textContent = `Q${q.question_number}: ${q.question_text}`;

    let content = `
        <div style="margin-bottom: 15px; padding: 15px; background: #f5f5f5; border-radius: 8px;">
            <strong>Section:</strong> ${q.section_name}<br>
            <strong>Pages:</strong> ${q.pages.join(', ')}<br>
            <strong>Status:</strong> ${q.status}
            ${q.fragment_count ? `<br><strong>Fragments:</strong> ${q.fragment_count}` : ''}
        </div>
        <div style="padding: 15px; background: #e8f5e9; border-radius: 8px; border-left: 4px solid #4CAF50;">
            <strong>Answer:</strong><br>
            ${q.answer || '<em>No answer yet</em>'}
        </div>
    `;

    document.getElementById('answerDetailContent').innerHTML = content;
    document.getElementById('answerDetailModal').style.display = 'flex';
}

function closeAnswerDetailModal() {
    document.getElementById('answerDetailModal').style.display = 'none';
}
```

Add click handler in `renderUnitaryTable`:
```javascript
// Add a "View" link in the answer cell
cells[3].innerHTML = isPending
    ? '<span style="color: #999; font-style: italic;">Analyzing...</span>'
    : `<span onclick="openAnswerDetailModal('${q.question_id}')" style="cursor: pointer; text-decoration: underline; color: #1E3A8A;">${truncateText(q.answer, 100)}</span>`;
```

---

## Files to Modify

1. **`services/hotdog/orchestrator.py`** - Send cumulative data for BestPrep mode
2. **`index.html`**:
   - Update `updateUnitaryTableWithNewAnswers()` for BestPrep handling
   - Move mode selector section
   - Add answer detail modal HTML
   - Add modal JavaScript functions
   - Update table row rendering for "View" links

---

## Testing Checklist

- [ ] BestPrep mode: Pages accumulate across windows (not replaced)
- [ ] BestPrep mode: Answers show all fragments or fragment count
- [ ] BestPrep mode: Footnotes accumulate
- [ ] Bid/Spec mode: Existing behavior unchanged (smart deduplication)
- [ ] Mode selector appears under PDF upload
- [ ] View modal opens with correct question details
- [ ] View modal shows accumulated data for BestPrep
- [ ] Export still works correctly for both modes
