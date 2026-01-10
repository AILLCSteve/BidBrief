# Universal Document Intelligence Platform
## AI-Powered Document Analysis with HOTDOG AI

A sophisticated, production-ready document analysis platform built on the **HOTDOG AI architecture** (Hierarchical Orchestrated Thorough Document Oversight & Guidance). This is a clean, unbranded version ready for customization and deployment.

---

## 🚀 Features

### Core Capabilities

- **AI-Powered Analysis:** GPT-4o powered document intelligence with dynamic expert generation
- **Multi-Format Support:** PDF, DOCX, TXT, RTF document processing
- **Configurable Questions:** JSON-based question sets (50-500+ questions supported)
- **Smart Deduplication:** Semantic similarity-based answer merging (0.75 threshold)
- **Perfect Citations:** Mandatory PDF page number preservation throughout analysis
- **Real-Time Progress:** Polling-based event streaming with live updates
- **Multi-Format Export:** Excel dashboards with charts, CSV, JSON, HTML reports
- **Session Management:** Thread-safe concurrent analysis with graceful cancellation
- **Production Ready:** Authentication, health checks, comprehensive error handling

### HOTDOG AI Architecture (7 Layers)

1. **Layer 0:** Document Ingestion (PDF extraction with PyMuPDF + fallbacks)
2. **Layer 1:** Configuration Loading (dynamic question sets)
3. **Layer 2:** Expert Persona Generation (AI-generated specialists per section)
4. **Layer 3:** Multi-Expert Processing (parallel GPT-4o calls, 3-5sec/window)
5. **Layer 4:** Smart Accumulation (semantic answer deduplication)
6. **Layer 5:** Token Budget Management (GPT-4o 128K context optimization)
7. **Layer 6:** Output Compilation (multi-format exports)

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Documentation](#api-documentation)
- [Deployment](#deployment)
- [Customization](#customization)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

---

## 🏁 Quick Start

### Prerequisites

- **Python 3.9+** with pip
- **OpenAI API Key** (GPT-4o access required)
- **Virtual Environment** (recommended)

### Installation

```bash
# 1. Clone the repository (or extract archive)
cd UniversalDocInt

# 2. Create virtual environment
python -m venv venv

# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your OpenAI API key

# 5. Run the application
python app.py
```

### Access the Application

Open your browser and navigate to:
```
http://localhost:5000
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file with the following variables:

```bash
# Required
OPENAI_API_KEY=sk-your-openai-api-key-here

# Optional
SECRET_KEY=your-secret-key-here
DEBUG=false
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=5000

# Authentication (Optional - leave blank to disable)
AUTH_USER1_EMAIL=admin@example.com
AUTH_USER1_PASSWORD=secure-password
AUTH_USER1_NAME=Admin User
```

### Question Configuration

Questions are defined in `config/default_questions.json`:

```json
{
  "config_name": "Document Analysis - Default Configuration",
  "sections": [
    {
      "section_id": "general_info",
      "section_name": "General Project Information",
      "questions": [
        {
          "id": "Q1",
          "text": "What is the project name?",
          "required": true
        }
      ]
    }
  ]
}
```

**Customization:**
- Add/remove sections
- Modify questions
- Change required fields
- Update section descriptions

---

## 💻 Usage

### Web Interface

1. **Upload Document:** Drag & drop or click to upload PDF
2. **Configure Analysis:** Select question sections to enable
3. **Add Context (Optional):** Provide analysis guardrails
4. **Start Analysis:** Process document with HOTDOG AI
5. **View Results:** Real-time progress and live results display
6. **Export:** Download Excel dashboard, CSV, JSON, or HTML

### API Usage

#### Upload Document
```bash
curl -X POST http://localhost:5000/api/upload \
  -F "file=@document.pdf"
```

Response:
```json
{
  "success": true,
  "session_id": "abc123",
  "filepath": "/tmp/document.pdf",
  "filename": "document.pdf"
}
```

#### Start Analysis
```bash
curl -X POST http://localhost:5000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc123",
    "pdf_path": "/tmp/document.pdf",
    "enabled_sections": ["general_info", "materials_standards"]
  }'
```

#### Poll for Progress
```bash
curl "http://localhost:5000/api/events/abc123?last_event_id=0"
```

#### Retrieve Results
```bash
curl http://localhost:5000/api/results/abc123
```

---

## 📡 API Documentation

### Endpoints

#### Analysis Flow

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/upload` | POST | Upload PDF file |
| `/api/analyze` | POST | Start background analysis |
| `/api/events/<session_id>` | GET | Poll for progress events |
| `/api/results/<session_id>` | GET | Retrieve analysis results |
| `/api/stop/<session_id>` | POST | Stop ongoing analysis |
| `/api/export/excel-dashboard/<session_id>` | GET | Download Excel dashboard |

#### Configuration

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/config/questions` | GET | Load question configuration |
| `/api/config/apikey` | GET | Get masked API key status |

#### Authentication

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/authenticate` | POST | User authentication |
| `/api/verify-session` | POST | Verify session token |

#### Admin

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/admin/sessions` | GET | List all analysis sessions |

#### Health

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Application health check |
| `/api/health/sse` | GET | SSE environment diagnostic |

---

## 🌐 Deployment

### Option 1: Render.com (Recommended)

1. **Create `render.yaml`:**
```yaml
services:
  - type: web
    name: universal-doc-intelligence
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn --config gunicorn_config.py app:app
    envVars:
      - key: PYTHON_VERSION
        value: 3.9
      - key: OPENAI_API_KEY
        sync: false
```

2. **Push to GitHub** and connect to Render
3. **Set environment variables** in Render dashboard
4. **Deploy** - Render will auto-build and deploy

### Option 2: Heroku

```bash
# 1. Install Heroku CLI
# 2. Login
heroku login

# 3. Create app
heroku create universal-doc-intelligence

# 4. Set environment variables
heroku config:set OPENAI_API_KEY=sk-your-key

# 5. Deploy
git push heroku main

# 6. Open app
heroku open
```

### Option 3: Docker

```bash
# Build image
docker build -t universal-doc-intelligence .

# Run container
docker run -p 5000:5000 \
  -e OPENAI_API_KEY=sk-your-key \
  -e SECRET_KEY=your-secret \
  universal-doc-intelligence
```

**Dockerfile** (create if needed):
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--config", "gunicorn_config.py", "app:app"]
```

---

## 🎨 Customization

### Branding

See `shared/BRANDING_README.md` for detailed branding instructions.

**Quick Steps:**

1. **Update Colors** in `shared/assets/css/common.css`:
```css
:root {
    --brand-primary: #667eea;    /* Your primary color */
    --brand-secondary: #764ba2;  /* Your secondary color */
}
```

2. **Replace Logo** at `shared/assets/images/logo.png`

3. **Update Text** in `index.html`:
   - Page title (line 6)
   - Header H1 (line 326)
   - Navbar title (line 319)

4. **Update Service Name** in `app.py` (line 296)

### Question Sets

Create custom question configurations:

```json
{
  "config_name": "Custom Analysis",
  "sections": [
    {
      "section_id": "custom_section",
      "section_name": "Custom Section",
      "questions": [...]
    }
  ]
}
```

Load with:
```bash
curl "http://localhost:5000/api/config/questions?path=config/custom.json"
```

---

## 🏗️ Architecture

### HOTDOG AI Flow

```
PDF Upload → Document Ingestion → Question Loading →
Expert Generation → Multi-Expert Processing →
Smart Accumulation → Token Management →
Output Compilation → Export
```

### Key Components

**Backend (`app.py`):**
- Flask application (1,449 lines)
- 25+ API endpoints
- Thread-safe session management
- Background analysis threading
- Event polling system

**HOTDOG Engine (`services/hotdog/`):**
- 9 Python modules (3,732 total lines)
- Async AI processing with asyncio
- Parallel expert execution
- Semantic answer deduplication

**Frontend (`index.html`):**
- Single-page application (1,050+ lines)
- Drag & drop file upload
- Real-time progress tracking
- Multi-format export

**Document Processing (`services/`):**
- Multi-format extraction (PDF, DOCX, RTF, TXT)
- Strategy pattern with fallbacks
- Page-level text tracking

---

## 🐛 Troubleshooting

### Common Issues

#### 1. OpenAI API Errors

**Problem:** `AuthenticationError` or `RateLimitError`

**Solution:**
- Verify API key in `.env` file
- Check OpenAI account status
- Ensure GPT-4o access enabled
- Review rate limits (Tier 1+ required)

#### 2. PDF Extraction Fails

**Problem:** "Unable to extract text from PDF"

**Solution:**
```bash
pip install --upgrade PyMuPDF pdfplumber PyPDF2
```

#### 3. Port Already in Use

**Problem:** `Address already in use`

**Solution:**
```bash
# Change port
export PORT=8000
python app.py
```

#### 4. Memory Issues

**Problem:** Analysis crashes on large PDFs

**Solution:**
- Increase server memory
- Process PDFs in smaller batches
- Adjust `MAX_UPLOAD_SIZE_MB` in `.env`

### Logs

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
python app.py
```

View logs location:
- **Development:** Console output
- **Production (Render/Heroku):** Platform logs dashboard

---

## 📊 Performance

### Benchmarks

| Document Size | Processing Time | API Cost |
|--------------|----------------|----------|
| 10 pages | 2-3 minutes | $0.50-$1.00 |
| 50 pages | 6-8 minutes | $2.00-$4.00 |
| 100 pages | 12-15 minutes | $5.00-$8.00 |

*Estimates based on GPT-4o pricing and 105-question analysis*

### Optimization

- **Parallel Execution:** 9-10 experts run simultaneously (6-10x speedup)
- **Token Management:** Conservative 75K prompt budget (58% of 128K context)
- **Smart Caching:** Expert personas cached for 30 days
- **Async Processing:** Non-blocking background threads

---

## 🔒 Security

### Best Practices

- ✅ Use environment variables for API keys
- ✅ Enable HTTPS in production (handled by Render/Heroku)
- ✅ Set strong `SECRET_KEY` for Flask sessions
- ✅ Use bcrypt for password hashing (upgrade from SHA256)
- ✅ Implement rate limiting (add Flask-Limiter)
- ✅ Validate file uploads (size, type)
- ✅ Regular security audits

### Authentication

Optional password protection:

```bash
# Enable in .env
AUTH_USER1_EMAIL=admin@example.com
AUTH_USER1_PASSWORD=secure-password
```

Access with login form at `/` before analysis.

---

## 📝 License

**Proprietary - All Rights Reserved**

This software is provided for evaluation and deployment purposes only. Modification, redistribution, or reverse engineering requires explicit written permission.

For licensing inquiries, contact: [your-email@example.com]

---

## 🤝 Contributing

### Development Setup

```bash
# Install dev dependencies
pip install -r requirements-dev.txt  # Create this if needed

# Run tests
pytest tests/

# Check code style
flake8 services/ app.py
```

### Code Guidelines

- Follow **SOLID principles** (see `claude.md`)
- Write **clean, documented code**
- Add **type hints** where possible
- **Test locally** before committing
- Use **meaningful commit messages**

---

## 📞 Support

### Getting Help

- **Documentation:** See `SPEC_ANALYZER_DIGEST.md` for technical details
- **Issues:** Report bugs via GitHub Issues (if open-sourced)
- **Email:** support@example.com
- **Discord:** Join our community (link TBD)

### Resources

- **HOTDOG Architecture:** See `docs/architecture/HOTDOG_AI_ARCHITECTURE.md` (if included)
- **API Reference:** See inline documentation in `app.py`
- **Branding Guide:** See `shared/BRANDING_README.md`

---

## 🎯 Roadmap

### Planned Features

- [ ] Database integration (PostgreSQL/MongoDB)
- [ ] Redis caching for expert personas
- [ ] WebSocket support (replace polling)
- [ ] PDF preview with highlighted citations
- [ ] Custom question editor UI
- [ ] Multi-language support (i18n)
- [ ] Batch document processing
- [ ] Advanced analytics dashboard
- [ ] API authentication with JWT
- [ ] Rate limiting

---

## 📈 Version History

### v1.0.0 (2026-01-10)
- ✅ Initial release - Clean, unbranded version
- ✅ HOTDOG AI 7-layer architecture
- ✅ GPT-4o integration with token optimization
- ✅ Multi-format document extraction
- ✅ Real-time progress tracking
- ✅ Excel dashboard exports with charts
- ✅ Session management and authentication
- ✅ Production-ready deployment configs

---

## 👏 Acknowledgments

Built with:
- **Flask** - Web framework
- **OpenAI GPT-4o** - AI processing
- **PyMuPDF** - PDF extraction
- **openpyxl** - Excel generation
- **asyncio** - Async processing

Inspired by domain-driven design principles and clean architecture patterns.

---

**Universal Document Intelligence Platform**
*Powered by HOTDOG AI - Hierarchical Orchestrated Thorough Document Oversight & Guidance*

© 2026 - Ready for customization and deployment
