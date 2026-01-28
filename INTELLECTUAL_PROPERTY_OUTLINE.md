# BidBrief Intellectual Property Outline
## For NDA Drafting Purposes
### Prepared: January 28, 2026
### Owner: Additional Intelligence, LLC

---

## EXECUTIVE SUMMARY

**Product Name**: BidBrief
**Patent Status**: Pending - U.S. Provisional Application No. 63/892,871 (371(c) Date: October 3, 2025)
**Patent Title**: "System and Method for Automated Analysis of Construction Specification Documents in Various Domains Including CIPP Pipe Rehabilitation and Other Construction Using Large Language Models"
**Total Proprietary Codebase**: ~6,749 lines of Python
**Core Innovation**: HOTDOG AI - 7-Layer Hierarchical Document Analysis Architecture

---

## 1. CORE TECHNOLOGY ARCHITECTURE

### 1.1 HOTDOG AI System (Hierarchical Orchestrated Thorough Document Oversight & Guidance)

**Seven-Layer Proprietary Architecture:**

| Layer | Name | Function | Key Innovation |
|-------|------|----------|----------------|
| 0 | Document Ingestion | PDF extraction with page preservation | Immutable PageData objects, 3-page windowing |
| 1 | Configuration Loader | Dynamic question configuration | Hierarchical section/question mapping |
| 2 | Expert Persona Generator | AI generates specialized AI experts | Meta-prompting, SHA256 caching |
| 3 | Multi-Expert Processor | Parallel expert execution | AsyncIO coordination, mandatory citations |
| 3.5 | Second-Pass Processor | Targeted re-analysis | Enhanced prompts for unanswered questions |
| 4 | Smart Accumulator | Answer deduplication | Jaccard similarity merging algorithm |
| 5 | Token Budget Manager | Cost optimization | Model-specific limits, safety buffers |
| 6 | Output Compiler | Final result formatting | Multi-format export with citation preservation |

### 1.2 Layer Details

**Layer 0 - Document Ingestion (`DocumentIngestionLayer`)**
- Advanced PDF text extraction using PyMuPDF with fallback strategies
- Perfect page number preservation (1-indexed, immutable `PageData` objects)
- Multi-format support: PDF, DOCX, TXT, RTF
- 3-page sliding window system maintaining semantic continuity
- Blank page detection and intelligent logging

**Layer 1 - Configuration Loader (`ConfigurationLoader`)**
- Dynamic JSON-based question configuration parsing
- Hierarchical structure: Sections → Questions with metadata
- Runtime configuration hot-loading capability
- Validates 50-500+ question configurations

**Layer 2 - Expert Persona Generator (`ExpertPersonaGenerator`)**
- **PROPRIETARY AI-TO-AI ARCHITECTURE**: Uses GPT-4o to dynamically generate specialized AI experts
- Meta-prompting system constructs expert personas based on section metadata
- Generates: expert_name, specialization, system_prompt, citation_strategy, answer_format
- In-memory caching with SHA256-based cache keys (30-day reuse)
- Context guardrails application for domain-specific constraints

**Layer 3 - Multi-Expert Processor (`MultiExpertProcessor`)**
- **PARALLEL EXPERT EXECUTION**: AsyncIO-based concurrent processing (5+ experts simultaneously)
- Questions routed by section_id to appropriate expert personas
- Mandatory PDF page citation requirements enforced
- JSON response format validation
- Confidence scoring system (0.0-1.0 scale)
- Footnote generation with contextual metadata

**Layer 3.5 - Second-Pass Specialized Processor (`SecondPassProcessor`)**
- Targets only unanswered questions from first pass
- Enhanced prompts with creative interpretation strategies
- Lower confidence thresholds for tentative answers
- Context expansion and broader semantic searching

**Layer 4 - Smart Accumulator (`SmartAccumulator`)**
- **PROPRIETARY SEMANTIC SIMILARITY DEDUPLICATION ENGINE**
- Jaccard similarity algorithm (token-based, 0.75 threshold)
- Intelligently merges duplicate answers while aggregating ALL page citations
- Tracks answer variants (multiple different answers to same question)
- Never loses information through merging process
- Confidence-based answer ranking

**Layer 5 - Token Budget Manager (`TokenBudgetManager`)**
- Conservative token accounting with 80% safety buffer
- Per-window tracking and cumulative usage
- Intelligent context truncation (preserves start 60%, end 40%)
- Model-specific limits: GPT-4o supports 128K context, 75K prompt
- Cost estimation: $0.00003 per token

**Layer 6 - Output Compiler (`OutputCompiler`)**
- Compiles final AnalysisResult from accumulated answers
- Footnote compilation from all answer variants
- Browser-ready format transformation
- Preserves PDF page citations in ALL output formats
- Confidence classification: HIGH (≥0.7), MEDIUM (0.4-0.7), LOW (<0.4)

---

## 2. PROPRIETARY ALGORITHMS

### 2.1 Answer Deduplication Algorithm (Layer 4)

```
ALGORITHM: Jaccard Similarity-Based Answer Merging

INPUT: New answer A, Existing answers [B1, B2, ... Bn]
OUTPUT: Updated answer collection (merged or added as variant)

1. NORMALIZE text: lowercase, collapse whitespace, remove punctuation
2. TOKENIZE: Split into word tokens
3. FOR each existing answer Bi:
   a. Calculate Jaccard similarity: |A ∩ Bi| / |A ∪ Bi|
   b. IF similarity ≥ 0.75: MERGE
      - Keep longer/more detailed text
      - Aggregate unique pages: sorted(set(pages_A + pages_Bi))
      - Use highest confidence
      - Merge footnotes with pipe delimiter
      - Increment merge_count
   c. IF similarity < 0.75 for all: ADD as new variant
4. RETURN updated collection
```

### 2.2 Mandatory Citation Validation

```
VALIDATION RULES:
- Every Answer object MUST contain pages[] array with length > 0
- All page numbers must be integers > 0
- Page numbers must fall within document range
- Citation marker <PDF pg X> must appear in answer text
- Multi-page format supported: <PDF pg 5, 6, 7> or <PDF pg 5-7>

FALLBACK EXTRACTION (if pages array missing):
- Regex Pattern 1: <PDF pg ([0-9, ]+)> → comma-separated
- Regex Pattern 2: <PDF pg (\d+)-(\d+)> → range expansion
- Regex Pattern 3: <PDF pg (\d+)> → single page
```

### 2.3 Expert Persona Generation Algorithm

```
ALGORITHM: Meta-Prompting for Dynamic Expert Generation

INPUT: Section metadata (name, description, sample questions), Context guardrails
OUTPUT: ExpertPersona object with system_prompt

1. CONSTRUCT meta-prompt with:
   - Section name and description
   - Sample questions (up to 5)
   - Context guardrails (if provided)
   - Required output schema

2. CALL GPT-4o with temperature=0.7 (creative generation)

3. PARSE JSON response:
   - expert_name: Creative, descriptive name
   - specialization: 2-3 sentence expertise description
   - system_prompt: Detailed instructions with citation format
   - citation_strategy: Page number extraction approach
   - answer_format: Structure and style requirements

4. CACHE with SHA256(section_name)[:16] key
5. RETURN immutable ExpertPersona object
```

---

## 3. PROPRIETARY DATA STRUCTURES

### 3.1 Core Data Models

```python
# Immutable Page Data
PageData(frozen=True):
    page_num: int          # 1-indexed for user display
    text: str              # Extracted text content
    char_count: int        # Character count
    has_content: bool      # True if meaningful content exists

# Question Definition
Question(frozen=True):
    id: str                # Unique identifier (e.g., "Q1")
    text: str              # Question text
    section_id: str        # Parent section reference
    required: bool         # Mandatory answer flag
    expected_type: str     # string|number|date|technical_spec

# Answer with Citation
Answer:
    question_id: str       # Reference to Question.id
    text: str              # Answer with <PDF pg X> citation
    pages: List[int]       # MANDATORY: Page numbers (validated)
    confidence: float      # 0.0-1.0 confidence score
    expert: str            # Expert persona name
    window: int            # Source window number
    footnote: str          # Additional context
    windows: List[int]     # All windows where found
    merge_count: int       # Number of merges
    created_at: datetime
    updated_at: datetime

# Expert Persona (AI-generated)
ExpertPersona(frozen=True):
    id: str                # Unique identifier
    name: str              # Creative expert name
    section_id: str        # Section assignment
    specialization: str    # Expertise description
    system_prompt: str     # AI instructions
    citation_strategy: str # How to extract pages
    answer_format: str     # Response structure
    cache_key: str         # SHA256 hash for caching
    created_at: datetime
```

### 3.2 Configuration Schema

```json
{
  "config_name": "CIPP Bid Specification Analysis",
  "version": "1.0",
  "sections": [
    {
      "section_id": "general_info",
      "section_name": "General Project Information",
      "description": "Basic project identification and scope",
      "questions": [
        {
          "id": "Q1",
          "text": "What is the project name and location?",
          "required": true,
          "expected_type": "string"
        }
      ]
    }
  ]
}
```

---

## 4. UNIQUE FEATURES

### 4.1 Real-Time Progress Streaming
- Polling-based event system with last_index tracking
- Atomic event storage during analysis
- Session lifecycle management (active → completed/partial)
- Thread-safe transitions using global lock

### 4.2 Excel Dashboard Generation
- 3-sheet professional format (Summary, Detailed Results, By Section)
- Conditional formatting with brand colors
- Charts for confidence distribution and answer coverage
- Supports partial results with visual indicators

### 4.3 Role-Based Authentication
- Environment-based user configuration
- Role hierarchy: 'admin' (full access), 'user' (basic access)
- SHA256 password hashing with 24-hour session tokens
- Decorator-based route protection

### 4.4 Context Guardrails System
- Global constraint injection throughout analysis pipeline
- Domain-specific focus (e.g., "Only CIPP lining context")
- Applied in expert generation and processing layers

---

## 5. BUSINESS-CRITICAL INNOVATIONS

### Patent-Worthy Concepts:

1. **Meta-Prompting for Expert Generation**: Using AI to dynamically generate specialized AI experts based on document section metadata

2. **Semantic Smart Accumulation**: Jaccard similarity-based answer deduplication with complete information preservation through intelligent merging

3. **Mandatory Citation Architecture**: Enforced PDF page number tracking through entire 7-layer processing pipeline with validation at every stage

4. **Multi-Expert Orchestration**: Parallel expert coordination (5-10 simultaneous) with window-based context management achieving 6-10x performance improvement

5. **Second-Pass Specialized Processing**: Targeted re-analysis of unanswered questions with enhanced creative prompts

6. **Token Budget Optimization**: Conservative accounting for parallel processing with model-specific limits and safety buffers

7. **Context Guardrails System**: Global constraint injection enabling domain-specific analysis without deviation

---

## 6. TECHNICAL SPECIFICATIONS

### 6.1 Backend Stack
- **Framework**: Flask 2.2+ with CORS
- **API Endpoints**: 25+ REST endpoints
- **Concurrency**: Threading with AsyncIO event loops
- **Session Management**: Thread-safe with global lock

### 6.2 AI Integration
- **Provider**: OpenAI API
- **Model**: GPT-4o (128K context)
- **Response Format**: JSON with validation
- **Temperature**: 0.3 (extraction), 0.7 (generation)

### 6.3 Document Processing
- **Primary**: PyMuPDF (fitz) for PDF
- **Fallback**: Multiple extraction strategies
- **Formats**: PDF, DOCX, TXT, RTF

### 6.4 Performance Metrics
- **Parallelization**: 5-10 experts simultaneously
- **Speed Improvement**: 6-10x over sequential processing
- **Token Efficiency**: 80% utilization with safety buffer

---

## 7. TRADE SECRETS

The following constitute trade secrets requiring protection:

1. **Expert Persona Generation Prompts**: The specific meta-prompts used to generate specialized AI experts

2. **Answer Merging Thresholds**: The 0.75 Jaccard similarity threshold and merge strategies

3. **Token Budget Formulas**: The specific calculations for model-specific limits and safety buffers

4. **Citation Validation Rules**: The complete set of validation rules and fallback extraction patterns

5. **Window Processing Strategy**: The 3-page window size and overlap configuration

6. **Second-Pass Enhancement Prompts**: The specific prompts used for re-analyzing unanswered questions

7. **Confidence Classification Thresholds**: The specific breakpoints (0.7, 0.4) for HIGH/MEDIUM/LOW

---

## 8. RECOMMENDED NDA PROVISIONS

Based on this IP outline, the NDA should specifically protect:

### 8.1 Technical Information
- All source code, algorithms, and data structures
- The 7-layer HOTDOG architecture design
- Expert persona generation methodology
- Answer deduplication algorithms
- Citation validation systems

### 8.2 Business Information
- Customer lists and usage data
- Pricing models and cost calculations
- Performance benchmarks
- Roadmap and planned features

### 8.3 Specific Exclusions from Disclosure
- Meta-prompts for expert generation
- Similarity thresholds and merging logic
- Token budget calculations
- Configuration schemas and question sets

### 8.4 Term Recommendations
- **Duration**: 5 years minimum for technical secrets
- **Survival**: Trade secrets protected indefinitely
- **Scope**: All derivative works and improvements
- **Jurisdiction**: Delaware or applicable state law

---

## DOCUMENT PREPARED FOR:
Additional Intelligence, LLC

## CONFIDENTIALITY NOTICE:
This document itself contains confidential information about BidBrief intellectual property. Distribution should be limited to parties who have already executed appropriate NDAs or are in the process of NDA negotiation.

---

*Generated: January 28, 2026*
*Version: 1.0*
