# PF-5 Code Patterns Reference

This document highlights the best practices and patterns used in the Readiness Validator Agent (PF-5) that other agents should follow.

---

## 1. Variable Initialization for Exception Safety

**Pattern: Initialize variables BEFORE try block that exception handlers will reference**

### ✅ CORRECT (Used in PF-5)

```python
async def process(self, request: AgentRequest) -> AgentResponse:
    start_time = time.time()
    content = ''  # Initialize before try block
    json_str = ''  # Initialize before try block

    # ... validation ...

    try:
        # ... processing ...
        content = result.get('content', '')
        json_str = self._extract_json_from_response(content)
        # ...

    except ValueError as e:
        # Safe to reference content and json_str - they're initialized
        return AgentResponse(
            ...,
            output_data={
                'extraction_error': str(e),
                'raw_response': content[:1000] if content else ''  # No NameError
            }
        )

    except json.JSONDecodeError as e:
        # Safe to reference json_str
        return AgentResponse(
            ...,
            output_data={
                'parse_error': str(e),
                'attempted_json': json_str[:500] if json_str else ''  # No NameError
            }
        )
```

**Why This Matters:**
- Exception handlers can safely reference variables
- Prevents `NameError: name 'content' is not defined` in error paths
- Makes code more predictable and debuggable

---

## 2. JSON Extraction with Multiple Strategies

**Pattern: Try multiple extraction approaches, validate each candidate**

### ✅ Implementation (PF-5)

```python
def _extract_json_from_response(self, content: str) -> str:
    """Safely extract JSON from LLM response with validation.

    Raises:
        ValueError: If no valid JSON found in response
    """
    candidates = []

    # Strategy 1: Markdown JSON code block
    if '```json' in content:
        parts = content.split('```json', 1)
        if len(parts) > 1:
            end_parts = parts[1].split('```', 1)
            if len(end_parts) > 0:
                candidates.append(end_parts[0].strip())

    # Strategy 2: Generic markdown code block
    if '```' in content:
        parts = content.split('```', 2)
        if len(parts) >= 3:
            candidates.append(parts[1].strip())

    # Strategy 3: Raw JSON (find first { and last })
    start = content.find('{')
    end = content.rfind('}')
    if start != -1 and end > start:
        candidates.append(content[start:end+1])

    # Validate each candidate
    for candidate in candidates:
        try:
            json.loads(candidate)  # Validate it parses
            return candidate
        except json.JSONDecodeError:
            continue

    raise ValueError(f"No valid JSON found in response: {content[:200]}...")
```

**Key Points:**
1. Multiple extraction strategies increase success rate
2. Only valid JSON candidates returned (validated with `json.loads()`)
3. Clear error message on complete failure includes response preview
4. Strategies ordered by likelihood (most specific first)

**Use Cases:**
- LLM might return JSON with markdown formatting
- LLM might return JSON without code block markers
- Different LLM providers format responses differently

---

## 3. Input Validation Progression

**Pattern: Type → Existence → Length → Enum validation with early returns**

### ✅ Implementation (PF-5)

```python
async def process(self, request: AgentRequest) -> AgentResponse:
    start_time = time.time()
    content = ''
    json_str = ''

    municipality_name = request.input_data.get('municipality_name', '')
    state = request.input_data.get('state', '')
    table_mode = request.input_data.get('table_mode', 'Municipal Systems Information')

    # 1. TYPE VALIDATION
    if not isinstance(municipality_name, str):
        return AgentResponse(
            agent_id=self.AGENT_ID,
            task=request.task,
            success=False,
            output_data={},
            errors=[f"municipality_name must be string, got {type(municipality_name).__name__}"]
        )

    if not isinstance(state, str):
        return AgentResponse(
            agent_id=self.AGENT_ID,
            task=request.task,
            success=False,
            output_data={},
            errors=[f"state must be string, got {type(state).__name__}"]
        )

    # 2. STRIP WHITESPACE (safe after type check)
    municipality_name = municipality_name.strip()
    state = state.strip()

    # 3. EXISTENCE VALIDATION
    if not municipality_name:
        return AgentResponse(
            agent_id=self.AGENT_ID,
            task=request.task,
            success=False,
            output_data={},
            errors=["municipality_name is required"]
        )

    if not state:
        return AgentResponse(
            agent_id=self.AGENT_ID,
            task=request.task,
            success=False,
            output_data={},
            errors=["state is required"]
        )

    # 4. LENGTH VALIDATION
    if len(municipality_name) > 200:
        return AgentResponse(
            agent_id=self.AGENT_ID,
            task=request.task,
            success=False,
            output_data={},
            errors=[f"municipality_name too long ({len(municipality_name)} chars, max 200)"]
        )

    if len(state) > 50:
        return AgentResponse(
            agent_id=self.AGENT_ID,
            task=request.task,
            success=False,
            output_data={},
            errors=[f"state too long ({len(state)} chars, max 50)"]
        )

    # 5. ENUM VALIDATION
    valid_table_modes = ["Municipal Systems Information", "Municipal Public Bids"]
    if table_mode not in valid_table_modes:
        return AgentResponse(
            agent_id=self.AGENT_ID,
            task=request.task,
            success=False,
            output_data={},
            errors=[f"Invalid table_mode: {table_mode}. Must be one of: {valid_table_modes}"]
        )

    # All validation passed - proceed to processing
    try:
        # ... main processing logic ...
```

**Benefits:**
- Each validation concern in isolation
- Early returns prevent cascade failures
- Informative error messages for each failure mode
- Type safety ensures string methods are available

---

## 4. Comprehensive Exception Handling

**Pattern: Specific exceptions first, generic catch-all last**

### ✅ Implementation (PF-5)

```python
try:
    # Call OpenAI
    result = await self.call_openai(user_message=user_message, system_prompt=prompt)

    # Parse JSON from response
    content = result.get('content', '')
    json_str = self._extract_json_from_response(content)
    output_data = json.loads(json_str)

    # Validate output
    errors = self.validate_output(output_data)

    if errors:
        logger.warning(f"PF-5 validation failed: {errors}")
        self.emit_event("warning", f"Validation errors: {'; '.join(errors)}")
        return AgentResponse(
            agent_id=self.AGENT_ID,
            task=request.task,
            success=False,
            output_data={'validation_errors': errors, 'raw_output': output_data},
            errors=errors,
            tokens_used=result.get('tokens_used', 0),
            processing_time_seconds=time.time() - start_time
        )

    elapsed = time.time() - start_time

    # Emit completion event with summary
    status = output_data.get('status', 'UNKNOWN')
    can_proceed = output_data.get('extraction_guidance', {}).get('can_proceed', False)
    gaps_count = len(output_data.get('gaps', []))

    self.emit_event(
        "completed",
        f"Readiness: {status} | Can Proceed: {can_proceed} | Gaps: {gaps_count}",
        is_completed=True
    )

    return AgentResponse(
        agent_id=self.AGENT_ID,
        task=request.task,
        success=True,
        output_data=output_data,
        errors=[],
        tokens_used=result.get('tokens_used', 0),
        processing_time_seconds=elapsed
    )

except ValueError as e:
    # JSON extraction failed - specific handler
    logger.error(f"PF-5 JSON extraction failed: {e}")
    return AgentResponse(
        agent_id=self.AGENT_ID,
        task=request.task,
        success=False,
        output_data={'extraction_error': str(e), 'raw_response': content[:1000] if content else ''},
        errors=[f"JSON extraction error: {str(e)[:100]}"],
        processing_time_seconds=time.time() - start_time
    )

except json.JSONDecodeError as e:
    # JSON parsing failed - specific handler with position info
    logger.error(f"PF-5 JSON parse failed: {e}")
    return AgentResponse(
        agent_id=self.AGENT_ID,
        task=request.task,
        success=False,
        output_data={'parse_error': str(e), 'attempted_json': json_str[:500] if json_str else ''},
        errors=[f"JSON parse error at position {e.pos}: {e.msg}"],
        processing_time_seconds=time.time() - start_time
    )

except Exception as e:
    # Unexpected error - catch-all with full context
    logger.exception(f"PF-5 unexpected error: {e}")
    return AgentResponse(
        agent_id=self.AGENT_ID,
        task=request.task,
        success=False,
        output_data={'raw_response': content[:500] if content else ''},
        errors=[f"Unexpected error: {type(e).__name__}: {str(e)[:100]}"],
        processing_time_seconds=time.time() - start_time
    )
```

**Exception Hierarchy:**
1. **ValueError** - JSON extraction failed (specific)
2. **json.JSONDecodeError** - JSON parsing failed (more specific than ValueError)
3. **Exception** - Anything else (generic catch-all)

**Each Handler Provides:**
- ✅ Specific error context (`extraction_error`, `parse_error`)
- ✅ Debugging info (raw response, attempted JSON)
- ✅ Appropriate logging level
- ✅ Complete AgentResponse object
- ✅ Processing time for monitoring

---

## 5. Safe Dictionary Access Pattern

**Pattern: Always use `.get()` with sensible defaults**

### ✅ Implementation (PF-5)

```python
# Extract input data safely
municipality_name = request.input_data.get('municipality_name', '')  # Default: empty string
state = request.input_data.get('state', '')  # Default: empty string
table_mode = request.input_data.get('table_mode', 'Municipal Systems Information')  # Default: first mode
pf1_result = request.input_data.get('pf1_result', {})  # Default: empty dict
pf2_result = request.input_data.get('pf2_result', {})  # Default: empty dict

# Nested access with safe defaults
normalized_name = pf1_result.get('normalized_name', 'NOT PROVIDED')
state = pf1_result.get('state', 'NOT PROVIDED')
confidence = pf1_result.get('confidence', 'UNKNOWN')
validation_status = pf1_result.get('validation_status', 'unknown')

# Deep nested access
source_map = pf3_result.get('source_map', {})
cip_docs = source_map.get('cip_documents', [])  # Returns [] if missing

terminology = pf4_result.get('terminology', {})
sanitary_locked = bool(terminology.get('sanitary_sewer', {}).get('primary_term'))

# Output access with null coalescing pattern
status = output.get('status')  # None if missing (for validation checking)
status_str = output.get('status', 'FAIL')  # Default to FAIL if missing
can_proceed = output_data.get('extraction_guidance', {}).get('can_proceed', False)  # Nested with defaults
```

**Benefits:**
- No KeyError exceptions
- Clear default values
- Null-safe nested access
- Predictable behavior when data is missing

---

## 6. Validation Output Structure

**Pattern: Collect all errors, return them all together**

### ✅ Implementation (PF-5)

```python
def validate_output(self, output: Dict[str, Any]) -> List[str]:
    """Validate readiness assessment output against spec."""
    errors = []

    # Check required status field
    status = output.get('status')
    if not status:
        errors.append("Missing required 'status' field")
    elif status not in ['PASS', 'PARTIAL', 'FAIL']:
        errors.append(f"Invalid status: {status}. Must be PASS, PARTIAL, or FAIL")

    # Check source_assessment section
    if 'source_assessment' not in output:
        errors.append("Missing required 'source_assessment' section")
    else:
        sa = output['source_assessment']
        if 'critical' not in sa:
            errors.append("source_assessment missing 'critical' subsection")
        else:
            critical = sa['critical']
            if 'required' not in critical:
                errors.append("critical sources missing 'required' list")
            if 'found' not in critical:
                errors.append("critical sources missing 'found' list")
            if 'missing' not in critical:
                errors.append("critical sources missing 'missing' list")

        if 'important' not in sa:
            errors.append("source_assessment missing 'important' subsection")

    # Check gaps section
    if 'gaps' not in output:
        errors.append("Missing required 'gaps' section")
    elif not isinstance(output['gaps'], list):
        errors.append("'gaps' must be a list")
    else:
        for i, gap in enumerate(output['gaps']):
            if not isinstance(gap, dict):
                errors.append(f"Gap {i} must be a dictionary")
                continue
            if 'source' not in gap:
                errors.append(f"Gap {i} missing 'source' field")
            if 'severity' not in gap:
                errors.append(f"Gap {i} missing 'severity' field")
            elif gap['severity'] not in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
                errors.append(f"Gap {i} has invalid severity: {gap['severity']}")

    # Check recommendations section
    if 'recommendations' not in output:
        errors.append("Missing required 'recommendations' section")
    elif not isinstance(output['recommendations'], list):
        errors.append("'recommendations' must be a list")

    # Check extraction_guidance section
    if 'extraction_guidance' not in output:
        errors.append("Missing required 'extraction_guidance' section")
    else:
        eg = output['extraction_guidance']
        if 'can_proceed' not in eg:
            errors.append("extraction_guidance missing 'can_proceed' field")
        elif not isinstance(eg['can_proceed'], bool):
            errors.append("'can_proceed' must be a boolean")
        if 'confidence_level' not in eg:
            errors.append("extraction_guidance missing 'confidence_level' field")

    # Check risk_assessment section
    if 'risk_assessment' not in output:
        errors.append("Missing required 'risk_assessment' section")
    else:
        ra = output['risk_assessment']
        if 'overall_risk' not in ra:
            errors.append("risk_assessment missing 'overall_risk' field")
        elif ra['overall_risk'] not in ['LOW', 'MEDIUM', 'HIGH']:
            errors.append(f"Invalid overall_risk: {ra['overall_risk']}")

    # Check preflight_summary section
    if 'preflight_summary' not in output:
        errors.append("Missing required 'preflight_summary' section")

    # Validate FAIL status logic - CRITICAL CONSTRAINT
    if status == 'FAIL':
        eg = output.get('extraction_guidance', {})
        if eg.get('can_proceed', False):
            errors.append("FAIL status cannot have can_proceed=true")

    return errors
```

**Key Pattern:**
1. Collect ALL errors into a list
2. Return complete list (don't fail on first error)
3. Caller can see all issues at once
4. Enables comprehensive error messages for user

**Critical Business Rule:**
The final check `"FAIL status cannot have can_proceed=true"` enforces a critical business constraint that gates the extraction phase.

---

## 7. Event Emission Pattern

**Pattern: Emit events at key lifecycle points for UI feedback**

### ✅ Implementation (PF-5)

```python
try:
    # Emit START event
    self.emit_event("processing", f"Validating readiness for {municipality_name}, {state}")

    # Build summary of all pre-flight results
    preflight_summary = self._build_preflight_summary(
        pf1_result, pf2_result, pf3_result, pf4_result
    )

    # Emit INTERMEDIATE event
    self.emit_event("processing", "Analyzing pre-flight completeness...")

    # Call OpenAI
    result = await self.call_openai(...)

    # Parse response
    content = result.get('content', '')
    json_str = self._extract_json_from_response(content)
    output_data = json.loads(json_str)

    # Validate output
    errors = self.validate_output(output_data)

    if errors:
        # Emit WARNING event
        self.emit_event("warning", f"Validation errors: {'; '.join(errors)}")

    # Extract summary data
    status = output_data.get('status', 'UNKNOWN')
    can_proceed = output_data.get('extraction_guidance', {}).get('can_proceed', False)
    gaps_count = len(output_data.get('gaps', []))

    # Emit COMPLETION event
    self.emit_event(
        "completed",
        f"Readiness: {status} | Can Proceed: {can_proceed} | Gaps: {gaps_count}",
        is_completed=True
    )

    return AgentResponse(...)

except ValueError as e:
    logger.error(f"PF-5 JSON extraction failed: {e}")
    # Note: Could emit error event here if needed
    return AgentResponse(...)
```

**Event Types Used:**
- **"processing"** - Task is running, update progress
- **"warning"** - Non-fatal issue detected
- **"completed"** - Task finished successfully, `is_completed=True`
- (Could add "error" event for failures if desired)

---

## 8. Aggregation Pattern

**Pattern: Consolidate results from multiple upstream agents safely**

### ✅ Implementation (PF-5)

```python
def _build_preflight_summary(
    self,
    pf1_result: Dict[str, Any],
    pf2_result: Dict[str, Any],
    pf3_result: Dict[str, Any],
    pf4_result: Dict[str, Any]
) -> str:
    """
    Compile results from PF-1 through PF-4 into a summary for evaluation.
    """
    summary_parts = ["## PRE-FLIGHT RESULTS SUMMARY\n"]

    # PF-1: Municipality Normalizer
    summary_parts.append("### PF-1: Municipality Normalizer")
    if pf1_result:  # Safe null check
        normalized_name = pf1_result.get('normalized_name', 'NOT PROVIDED')  # Safe get
        state = pf1_result.get('state', 'NOT PROVIDED')
        confidence = pf1_result.get('confidence', 'UNKNOWN')
        validation_status = pf1_result.get('validation_status', 'unknown')
        summary_parts.append(f"- Normalized Name: {normalized_name}")
        summary_parts.append(f"- State: {state}")
        summary_parts.append(f"- Confidence: {confidence}")
        summary_parts.append(f"- Validation Status: {validation_status}")
        if pf1_result.get('population'):  # Check before using
            summary_parts.append(f"- Population: {pf1_result['population']}")
        if pf1_result.get('county'):  # Check before using
            summary_parts.append(f"- County: {pf1_result['county']}")
    else:
        summary_parts.append("- **STATUS: NOT COMPLETED**")  # Graceful degradation
    summary_parts.append("")

    # PF-2: Jurisdiction Mapper
    summary_parts.append("### PF-2: Jurisdiction Mapper")
    if pf2_result:
        sanitary_owner = pf2_result.get('sanitary_sewer_owner', 'NOT FOUND')
        sanitary_operator = pf2_result.get('sanitary_sewer_operator', 'NOT FOUND')
        storm_owner = pf2_result.get('storm_drain_owner', 'NOT FOUND')
        storm_operator = pf2_result.get('storm_drain_operator', 'NOT FOUND')
        confidence = pf2_result.get('confidence', 'UNKNOWN')
        summary_parts.append(f"- Sanitary Sewer Owner: {sanitary_owner}")
        summary_parts.append(f"- Sanitary Sewer Operator: {sanitary_operator}")
        summary_parts.append(f"- Storm Drain Owner: {storm_owner}")
        summary_parts.append(f"- Storm Drain Operator: {storm_operator}")
        summary_parts.append(f"- Confidence: {confidence}")
        if pf2_result.get('sources'):
            summary_parts.append(f"- Sources Found: {len(pf2_result['sources'])}")
    else:
        summary_parts.append("- **STATUS: NOT COMPLETED**")
    summary_parts.append("")

    # ... similar for PF-3 and PF-4 ...

    return "\n".join(summary_parts)
```

**Key Patterns:**
1. **Null Check First** - `if pf1_result:` before accessing
2. **Safe Get with Defaults** - `pf1_result.get('normalized_name', 'NOT PROVIDED')`
3. **Conditional Fields** - `if pf1_result.get('population'):` before including
4. **Graceful Degradation** - "NOT COMPLETED" message if data missing
5. **Readable Format** - Formatted summary for LLM consumption

---

## Summary of Best Practices

1. ✅ **Initialize variables before try blocks** - Prevents NameError in exception handlers
2. ✅ **Multiple extraction strategies** - Increases robustness with LLM output
3. ✅ **Progressive validation** - Type → Existence → Length → Enum with early returns
4. ✅ **Layered exception handling** - Specific exceptions before generic catch-all
5. ✅ **Safe dictionary access** - Always use `.get()` with sensible defaults
6. ✅ **Comprehensive validation** - Collect all errors, return complete list
7. ✅ **Event emission** - Emit at key lifecycle points for UI feedback
8. ✅ **Aggregation with degradation** - Safely consolidate upstream results

---

**These patterns are recommended for all future agents in the pre-flight and extraction phases.**
