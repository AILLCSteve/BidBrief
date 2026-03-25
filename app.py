"""
BidBrief - AI Document Analysis Platform
HOTDOG AI Document Analysis with Real-Time Progress Tracking

Architecture: Threading-based (simple, proven, works)
Powered by Additional Intelligence LLC
"""
# GEVENT MONKEY PATCHING DISABLED
# Previously used for SSE streaming, but now using polling-based progress updates.
# Gevent monkey patching conflicts with gunicorn's sync+threaded workers, causing
# "greenlet.error: Cannot switch to a different thread" on file uploads.
# See: https://github.com/gevent/gevent/issues/1697
#
# If SSE streaming is re-enabled in the future, switch gunicorn to gevent workers:
#   worker_class = 'gevent' (not 'sync' with threads)
GEVENT_PATCHED = False

import os
import sys
import logging
import threading
import queue
import json
import tempfile
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()  # CRITICAL: Must be called before any os.getenv() usage

from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory, send_file, redirect, make_response
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Import HOTDOG orchestrator
from services.hotdog import HotdogOrchestrator
# Excel dashboard import moved to lazy load (only when endpoint is called)
# This prevents app crash if openpyxl isn't installed
import asyncio

# CityScraper imports (lazy loaded to prevent startup failures if modules not installed)
# These will be imported when endpoints are called
CITYSCRAPER_AVAILABLE = False
try:
    from services.scraper.orchestrators import (
        StandaloneResearchOrchestrator,
        DocumentEnrichmentOrchestrator,
        ComparativeIntelligenceOrchestrator,
        BidDownloadOrchestrator
    )
    from services.scraper.agents.analysis import (
        SummaryGeneratorAgent,
        BrainstormerAgent,
        DeepResearcherAgent,
        BidAnalyzerAgent
    )
    from services.scraper.models import AgentRequest
    CITYSCRAPER_AVAILABLE = True
except ImportError as e:
    # CityScraper modules not installed - endpoints will return 503
    pass

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Diagnostic: Log Python environment
logger.info(f"🐍 Python {sys.version.split()[0]} at {sys.executable}")
logger.info("✅ Using sync workers with threading (gevent patching disabled)")
logger.info("📡 Progress updates via polling (/api/events/<session_id>)")

# Configuration
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB
    BASE_DIR = Path(__file__).parent

# Create Flask app
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

# ============================================================================
# MODULE RELOAD DETECTION
# ============================================================================
# Track module reloads to diagnose session disappearance issue
import uuid
import time

MODULE_LOAD_ID = str(uuid.uuid4())[:8]
MODULE_LOAD_TIME = time.time()
logger.info("="*80)
logger.info(f"🔄 MODULE LOADED: ID={MODULE_LOAD_ID}, PID={os.getpid()}, TIME={datetime.now().isoformat()}")
logger.info("="*80)

# Global state
progress_queues = {}  # session_id -> Queue for SSE progress (legacy)
session_events = {}  # session_id -> [events] for polling (NEW)
analysis_threads = {}  # session_id -> Thread for cancellation
analysis_results = {}  # session_id -> result data (legacy, kept for backward compatibility)
active_analyses = {}  # session_id -> {'orchestrator': HotdogOrchestrator, 'config_path': str, 'pdf_path': str, 'status': 'running'} (in-progress)
completed_analyses = {}  # session_id -> {'orchestrator': ..., 'result': ..., 'config_path': ..., 'completed_at': datetime, 'status': 'completed'}
partial_analyses = {}  # session_id -> {'orchestrator': ..., 'config_path': ..., 'stopped_at': datetime, 'status': 'stopped'}
session_timestamps = {}  # session_id -> last_access_time (for cleanup)

# Upload store: mapping upload_id -> {'path','filename','uploaded_at','expires_at','owner','encrypted'}
UPLOAD_STORE: dict = {}
UPLOAD_RETENTION_SECONDS = int(os.getenv('UPLOAD_RETENTION_SECONDS', '3600'))  # default 1 hour

# ============================================================================
# AUDIT LOGGING
# ============================================================================
# Dedicated audit logger for security-relevant events (who did what, when)
audit_logger = logging.getLogger('bidbrief.audit')
audit_logger.setLevel(logging.INFO)

# Create audit log handler (separate file for security audits)
_audit_log_path = os.getenv('AUDIT_LOG_PATH', 'logs/audit.log')
os.makedirs(os.path.dirname(_audit_log_path) if os.path.dirname(_audit_log_path) else '.', exist_ok=True)
_audit_handler = logging.FileHandler(_audit_log_path)
_audit_handler.setFormatter(logging.Formatter('%(asctime)s - AUDIT - %(message)s'))
audit_logger.addHandler(_audit_handler)

def audit_log(action: str, user: str = None, details: dict = None):
    """Log security-relevant events for audit trail.

    Args:
        action: Action being performed (e.g., 'upload', 'analyze', 'export', 'login')
        user: Username performing the action (None for anonymous)
        details: Additional context (session_id, filename, etc.)
    """
    details = details or {}
    # Sanitize details - never log full file paths or sensitive content
    safe_details = {k: v for k, v in details.items() if k not in ('path', 'content', 'pdf_path')}
    # Add request metadata
    safe_details['ip'] = request.remote_addr if request else 'unknown'
    safe_details['user_agent'] = request.headers.get('User-Agent', 'unknown')[:100] if request else 'unknown'

    audit_logger.info(f"action={action} user={user or 'anonymous'} {' '.join(f'{k}={v}' for k, v in safe_details.items())}")

# ============================================================================
# ENCRYPTED EPHEMERAL STORAGE
# ============================================================================
# Uses Fernet symmetric encryption for uploads at rest
from cryptography.fernet import Fernet

# Generate or load encryption key (persistent across restarts via env var)
_UPLOAD_ENCRYPTION_KEY = os.getenv('UPLOAD_ENCRYPTION_KEY')
if not _UPLOAD_ENCRYPTION_KEY:
    # Generate new key if not provided (will be different each restart - that's OK for ephemeral data)
    _UPLOAD_ENCRYPTION_KEY = Fernet.generate_key().decode()
    logger.warning("⚠️  UPLOAD_ENCRYPTION_KEY not set - generated ephemeral key (uploads won't survive restart)")

_fernet = Fernet(_UPLOAD_ENCRYPTION_KEY.encode() if isinstance(_UPLOAD_ENCRYPTION_KEY, str) else _UPLOAD_ENCRYPTION_KEY)

def _encrypt_file(plaintext_path: str) -> str:
    """Encrypt a file and return path to encrypted version. Deletes original."""
    with open(plaintext_path, 'rb') as f:
        plaintext = f.read()

    encrypted = _fernet.encrypt(plaintext)
    encrypted_path = plaintext_path + '.enc'

    with open(encrypted_path, 'wb') as f:
        f.write(encrypted)

    # Securely delete original plaintext file
    os.unlink(plaintext_path)

    return encrypted_path

def _decrypt_file(encrypted_path: str) -> str:
    """Decrypt a file and return path to decrypted temp file."""
    with open(encrypted_path, 'rb') as f:
        encrypted = f.read()

    plaintext = _fernet.decrypt(encrypted)

    # Create temp file for decrypted content
    fd, decrypted_path = tempfile.mkstemp(suffix='.pdf')
    with os.fdopen(fd, 'wb') as f:
        f.write(plaintext)

    return decrypted_path

def _secure_delete_upload(upload_id: str):
    """Securely delete an upload and its files."""
    if upload_id not in UPLOAD_STORE:
        return

    info = UPLOAD_STORE[upload_id]
    path = info.get('path')

    try:
        if path and os.path.exists(path):
            os.unlink(path)
            logger.info(f"🔐 Securely deleted upload file: upload_id={upload_id}")
    except Exception as e:
        logger.warning(f"Failed to delete upload file {upload_id}: {e}")

    UPLOAD_STORE.pop(upload_id, None)

# CityScraper session management
cityscraper_sessions = {}  # session_id -> {'orchestrator': ..., 'status': 'running'|'completed'|'cancelled'}
cityscraper_events = {}  # session_id -> [AgentActivityEvent list]
cityscraper_results = {}  # session_id -> result dict


# Background cleanup thread for expired uploads
def _upload_cleanup_loop():
    """Background loop that deletes expired uploaded files and removes them from UPLOAD_STORE."""
    while True:
        try:
            now = datetime.now()
            expired = []
            for uid, info in list(UPLOAD_STORE.items()):
                if info.get('expires_at') and info['expires_at'] < now:
                    expired.append((uid, info))

            for uid, info in expired:
                path = info.get('path')
                try:
                    if path and os.path.exists(path):
                        os.unlink(path)
                        logger.info(f"🧹 Cleanup: deleted expired upload file: {path}")
                except Exception as e:
                    logger.warning(f"Failed to delete upload file {path}: {e}")
                UPLOAD_STORE.pop(uid, None)

            time.sleep(60)
        except Exception:
            # Ensure the loop continues on unexpected errors
            logger.exception("Upload cleanup loop encountered an error")
            time.sleep(60)

# Start cleanup thread as daemon
_cleanup_thread = threading.Thread(target=_upload_cleanup_loop, name='upload-cleanup', daemon=True)
_cleanup_thread.start()

logger.info(f"📊 Session dicts initialized: module_id={MODULE_LOAD_ID}, pid={os.getpid()}")

# ============================================================================
# THREAD SAFETY
# ============================================================================
# Global lock for all session dict access to prevent race conditions
# See: ADMIN_SESSION_FLICKERING_DIAGNOSIS.md and STOP_ANALYSIS_RACE_CONDITION.md
session_lock = threading.Lock()
logger.info("🔒 Session lock initialized for thread-safe dict access")

# Authentication - Load from environment variables
def load_authorized_users():
    """
    Load authorized users from environment variables for security.

    Roles:
    - AUTH_USER1 = Admin (full access including /admin/sessions)
    - AUTH_USER2 = User (basic app access only)
    - AUTH_USER3 = User (basic app access only)
    """
    users = {}

    # User 1 - ADMIN role (full access)
    user1_email = os.getenv('AUTH_USER1_EMAIL')
    user1_password = os.getenv('AUTH_USER1_PASSWORD')
    user1_name = os.getenv('AUTH_USER1_NAME', 'Admin')

    if user1_email and user1_password:
        users[user1_email.lower()] = {
            'password_hash': hashlib.sha256(user1_password.encode()).hexdigest(),
            'name': user1_name,
            'role': 'admin'
        }

    # User 2 - USER role (basic access only)
    user2_email = os.getenv('AUTH_USER2_EMAIL')
    user2_password = os.getenv('AUTH_USER2_PASSWORD')
    user2_name = os.getenv('AUTH_USER2_NAME', 'User')

    if user2_email and user2_password:
        users[user2_email.lower()] = {
            'password_hash': hashlib.sha256(user2_password.encode()).hexdigest(),
            'name': user2_name,
            'role': 'user'
        }

    # User 3 - USER role (basic access only)
    user3_email = os.getenv('AUTH_USER3_EMAIL')
    user3_password = os.getenv('AUTH_USER3_PASSWORD')
    user3_name = os.getenv('AUTH_USER3_NAME', 'User 3')

    if user3_email and user3_password:
        users[user3_email.lower()] = {
            'password_hash': hashlib.sha256(user3_password.encode()).hexdigest(),
            'name': user3_name,
            'role': 'user'
        }

    if not users:
        print("WARNING: No authorized users configured. Set AUTH_USER*_EMAIL and AUTH_USER*_PASSWORD environment variables.")

    return users

AUTHORIZED_USERS = load_authorized_users()
active_sessions = {}

# Log loaded users on startup
logger.info("="*60)
logger.info("AUTHORIZED USERS LOADED:")
for email, data in AUTHORIZED_USERS.items():
    logger.info(f"  User: {email} | Name: {data.get('name', 'N/A')}")
logger.info("="*60)


# ============================================================================
# SESSION CLEANUP (Memory Management)
# ============================================================================

def cleanup_expired_sessions():
    """
    Remove TEMPORARY session data older than 30 days.
    KEEPS completed/partial analyses for 30 days.
    Reschedules itself every 15 minutes using threading.Timer.

    THREAD SAFETY: Uses session_lock to prevent race conditions with
    concurrent admin requests and analysis completion.
    """
    try:
        # CRITICAL: Atomic cleanup with lock
        # Prevents race with admin endpoint and analysis threads
        with session_lock:
            cutoff = datetime.now() - timedelta(days=30)
            expired = [
                sid for sid, ts in session_timestamps.items()
                if ts < cutoff
            ]

            for sid in expired:
                # Clean up temporary/transient data (safe to delete)
                progress_queues.pop(sid, None)
                session_events.pop(sid, None)
                analysis_threads.pop(sid, None)

                # ONLY delete if not in completed/partial (preserve valuable analysis results)
                if sid not in completed_analyses and sid not in partial_analyses:
                    analysis_results.pop(sid, None)
                    active_analyses.pop(sid, None)
                    session_timestamps.pop(sid, None)
                    logger.info(f"✅ Cleaned up expired session: {sid}")
                else:
                    logger.info(f"⏳ Keeping completed/partial session: {sid}")

        # Log outside lock
        if expired:
            logger.info(f"🧹 Cleaned up {len(expired)} expired sessions")

    except Exception as e:
        logger.error(f"❌ Session cleanup failed: {e}")

    # Reschedule cleanup in 15 minutes (900 seconds)
    timer = threading.Timer(900, cleanup_expired_sessions)
    timer.daemon = True
    timer.start()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _transform_to_legacy_format(hotdog_output: dict) -> dict:
    """
    Transform HOTDOG's modern output format to legacy frontend format.

    This backwards-compatibility layer ensures the old frontend can display
    HOTDOG's results without requiring a complete frontend rewrite.

    HOTDOG Format:
        {
            "sections": [{
                "questions": [{
                    "question_text": "...",
                    "primary_answer": {"text": "...", "pages": [1,2,3]}
                }]
            }]
        }

    Legacy Format:
        {
            "sections": [{
                "questions": [{
                    "question": "...",
                    "answer": "...",
                    "page_citations": [1,2,3]
                }]
            }]
        }
    """
    legacy_sections = []

    for section in hotdog_output.get('sections', []):
        legacy_section = {
            'section_name': section.get('section_name', ''),
            'section_id': section.get('section_id', ''),
            'description': section.get('description', ''),
            'questions': []
        }

        for q in section.get('questions', []):
            legacy_question = {
                'question_id': q.get('question_id', ''),
                'question': q.get('question_text', ''),  # Transform: question_text → question
            }

            # Transform: primary_answer{text, pages, footnote} → answer, page_citations, footnote
            primary_answer = q.get('primary_answer')
            # Check if answer exists: either has_answer=True OR primary_answer is not None
            has_answer = q.get('has_answer', primary_answer is not None)
            if primary_answer and has_answer:
                legacy_question['answer'] = primary_answer.get('text', '')
                legacy_question['page_citations'] = primary_answer.get('pages', [])
                legacy_question['confidence'] = primary_answer.get('confidence', 0.0)
                legacy_question['footnote'] = primary_answer.get('footnote', '')  # Include footnote
            else:
                legacy_question['answer'] = None
                legacy_question['page_citations'] = []
                legacy_question['confidence'] = 0.0
                legacy_question['footnote'] = None

            legacy_section['questions'].append(legacy_question)

        legacy_sections.append(legacy_section)

    return {
        'sections': legacy_sections,
        'document_name': hotdog_output.get('document_name', ''),
        'total_pages': hotdog_output.get('total_pages', 0),
        'questions_answered': hotdog_output.get('questions_answered', 0),
        'total_questions': hotdog_output.get('total_questions', 0),
        'metadata': hotdog_output.get('metadata', {}),
        'key_requirements': hotdog_output.get('key_requirements', {}),  # Preserve key requirements
        'footnotes': hotdog_output.get('footnotes', [])  # Preserve compiled footnotes array
    }


# ============================================================================
# COOKIE-BASED AUTHENTICATION HELPERS
# ============================================================================

def check_auth_cookie():
    """
    Check if user has valid authentication cookie.
    Returns session data if valid, None if invalid/missing.
    """
    token = request.cookies.get('bidbrief_auth')
    if not token:
        return None

    session = active_sessions.get(token)
    if not session:
        return None

    # Check expiration
    if session.get('expires_at') and session['expires_at'] < datetime.now():
        active_sessions.pop(token, None)
        return None

    return session


def require_auth(f):
    """
    Decorator to require authentication for a route.
    For API routes (/api/*): returns JSON 401 error.
    For page routes: redirects to /login.
    """
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session = check_auth_cookie()
        if not session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function


def require_admin(f):
    """
    Decorator to require admin role for a route.
    For API routes (/api/*): returns JSON 401/403 errors.
    For page routes: redirects to /login or /.
    """
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        session = check_auth_cookie()
        is_api = request.path.startswith('/api/')

        if not session:
            if is_api:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            return redirect('/login')

        if session.get('role') != 'admin':
            logger.warning(f"Non-admin user '{session.get('username')}' attempted to access admin route")
            if is_api:
                return jsonify({'success': False, 'error': 'Admin access required'}), 403
            return redirect('/')  # Redirect non-admins to home

        return f(*args, **kwargs)
    return decorated_function


def _current_user_info():
    """Return (username, role) or (None, None) if unauthenticated."""
    s = check_auth_cookie()
    if not s:
        return None, None
    return s.get('username'), s.get('role')


def _is_authorized_for_session(session_id: str) -> bool:
    """Return True if current request is authorized to access results/exports for session_id.

    Policy: If session has an owner, only that owner or an admin can access. If session has no owner (anonymous), access is allowed.
    """
    with session_lock:
        session_data = None
        if session_id in completed_analyses:
            session_data = completed_analyses[session_id]
        elif session_id in partial_analyses:
            session_data = partial_analyses[session_id]
        elif session_id in active_analyses:
            session_data = active_analyses[session_id]
        elif session_id in analysis_results:
            session_data = analysis_results[session_id]
        else:
            logger.warning(
                f"[AUTH-403] Session {session_id[:12]} not found in any dict. "
                f"active_keys={[k[:8] for k in list(active_analyses.keys())[:5]]}, "
                f"completed_keys={[k[:8] for k in list(completed_analyses.keys())[:5]]}, "
                f"partial_keys={[k[:8] for k in list(partial_analyses.keys())[:5]]}"
            )
            return False

    owner = session_data.get('owner') if session_data else None
    if not owner:
        return True

    username, role = _current_user_info()
    if role == 'admin':
        return True
    if username and username == owner:
        return True

    # Log why ownership check failed — critical for diagnosing permanent 403s
    cookie_present = bool(request.cookies.get('bidbrief_auth'))
    logger.warning(
        f"[AUTH-403] Ownership check failed for {session_id[:12]}: "
        f"owner={owner}, username={username}, cookie_present={cookie_present}, "
        f"session_status={session_data.get('status', 'unknown')}"
    )
    return False


# ============================================================================
# BASIC ROUTES
# ============================================================================

@app.route('/')
@require_auth
def index():
    return send_from_directory(Config.BASE_DIR, 'index.html')


@app.route('/login')
def login_page():
    """Serve the login page."""
    # If already logged in, redirect to home
    if check_auth_cookie():
        return redirect('/')
    return send_from_directory(Config.BASE_DIR, 'login.html')


@app.route('/auth/login', methods=['POST'])
def form_login():
    """Handle form-based login submission."""
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')

    logger.info(f"Form login attempt - Username: '{username}'")

    if username not in AUTHORIZED_USERS:
        logger.warning(f"Form login failed - user not found: {username}")
        audit_log('login_failed', username, {'reason': 'user_not_found'})
        return redirect('/login?error=invalid')

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    expected_hash = AUTHORIZED_USERS[username]['password_hash']

    if password_hash != expected_hash:
        logger.warning(f"Form login failed - password mismatch for: {username}")
        audit_log('login_failed', username, {'reason': 'invalid_password'})
        return redirect('/login?error=invalid')

    # Create session token
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=24)
    user_role = AUTHORIZED_USERS[username].get('role', 'user')

    active_sessions[token] = {
        'username': username,
        'name': AUTHORIZED_USERS[username]['name'],
        'role': user_role,
        'expires_at': expires_at
    }

    logger.info(f"Form login successful for: {username} (role: {user_role})")

    # Audit log successful login
    audit_log('login', username, {'role': user_role})

    # Create response with auth cookie
    response = make_response(redirect('/'))
    response.set_cookie(
        'bidbrief_auth',
        token,
        httponly=True,
        secure=os.getenv('FLASK_ENV') == 'production',
        samesite='Lax',
        max_age=24 * 60 * 60  # 24 hours
    )
    return response


@app.route('/auth/logout')
def logout():
    """Log out user and clear session."""
    token = request.cookies.get('bidbrief_auth')
    username = None
    if token:
        session = active_sessions.pop(token, None)
        if session:
            username = session.get('username')
        logger.info(f"User logged out: {username}")
        audit_log('logout', username)

    response = make_response(redirect('/login'))
    response.delete_cookie('bidbrief_auth')
    return response


@app.route('/shared/<path:filename>')
def serve_shared_assets(filename):
    """Serve shared assets (images, CSS, etc.)"""
    return send_from_directory(Config.BASE_DIR / 'shared', filename)

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'BidBrief - AI Document Analysis',
        'version': '2.0.0'
    })

@app.route('/pics/<path:filename>')
def serve_pics(filename):
    """Serve pics assets (logo, favicon, etc.)"""
    return send_from_directory(Config.BASE_DIR / 'pics', filename)


# ============================================================================
# AUTHENTICATION
# ============================================================================

@app.route('/api/authenticate', methods=['POST'])
def authenticate():
    data = request.get_json()
    username = data.get('username', '').strip().lower()
    password = data.get('password', '')

    # Simple debug logging
    user_agent = request.headers.get('User-Agent', 'Unknown')
    logger.info(f"Auth attempt - Username (raw): '{data.get('username', '')}' length={len(data.get('username', ''))}")
    logger.info(f"Auth attempt - Username (normalized): '{username}' length={len(username)}")
    logger.info(f"Auth attempt - Password length: {len(password)}")
    logger.info(f"Auth attempt - User agent: {user_agent[:50]}")
    logger.info(f"Loaded users in dict: {list(AUTHORIZED_USERS.keys())}")

    if username not in AUTHORIZED_USERS:
        logger.warning(f"User not found: {username}")
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

    password_hash = hashlib.sha256(password.encode()).hexdigest()
    expected_hash = AUTHORIZED_USERS[username]['password_hash']

    if password_hash != expected_hash:
        logger.warning(f"Password mismatch for {username}")
        logger.warning(f"  Received hash: {password_hash[:20]}...")
        logger.warning(f"  Expected hash: {expected_hash[:20]}...")
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=24)
    user_role = AUTHORIZED_USERS[username].get('role', 'user')

    active_sessions[token] = {
        'username': username,
        'name': AUTHORIZED_USERS[username]['name'],
        'role': user_role,
        'expires_at': expires_at
    }

    return jsonify({
        'success': True,
        'token': token,
        'user': {'email': username, 'name': AUTHORIZED_USERS[username]['name'], 'role': user_role}
    })

@app.route('/api/verify-session', methods=['POST'])
def verify_session():
    data = request.get_json()
    token = data.get('token', '')

    if token not in active_sessions:
        return jsonify({'valid': False}), 401

    session = active_sessions[token]
    if datetime.now() > session['expires_at']:
        del active_sessions[token]
        return jsonify({'valid': False}), 401

    return jsonify({'valid': True, 'user': {'email': session['username'], 'name': session['name']}})


# ============================================================================
# USER INFO
# ============================================================================

@app.route('/api/user/info', methods=['GET'])
@require_auth
def get_user_info():
    """Get current user info including admin status"""
    session = check_auth_cookie()
    if not session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    return jsonify({
        'success': True,
        'username': session.get('username', 'unknown'),
        'role': session.get('role', 'user'),
        'is_admin': session.get('role') == 'admin'
    })


# API KEY
# ============================================================================

@app.route('/api/config/apikey', methods=['GET'])
@require_admin
def get_api_key():
    api_key = os.getenv('OPENAI_API_KEY', '')
    if not api_key:
        return jsonify({'success': False, 'error': 'API key not configured'}), 500

    return jsonify({
        'success': True,
        'masked': api_key[:10] + '...' + api_key[-4:]
    })


@app.route('/api/health/sse', methods=['GET'])
def sse_health():
    """Diagnostic endpoint for SSE environment status"""
    import platform

    # Check gevent installation and version
    try:
        import gevent
        gevent_version = gevent.__version__
        gevent_installed = True
    except ImportError:
        gevent_version = None
        gevent_installed = False

    # Check gunicorn worker availability
    try:
        from gunicorn.workers.ggevent import GeventWorker
        gevent_worker_available = True
    except ImportError:
        gevent_worker_available = False

    return jsonify({
        'python_version': platform.python_version(),
        'python_executable': sys.executable,
        'gevent_installed': gevent_installed,
        'gevent_version': gevent_version,
        'gevent_patched': GEVENT_PATCHED,
        'gevent_worker_available': gevent_worker_available,
        'server_software': os.environ.get('SERVER_SOFTWARE', 'unknown'),
        'active_sessions': len(progress_queues),
        'active_analyses': len(active_analyses)
    })


# ============================================================================
# FILE UPLOAD
# ============================================================================

@app.route('/api/upload', methods=['POST'])
@require_auth
def upload_file():
    """Upload PDF file, encrypt at rest, return an opaque upload_id. Requires authentication."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'success': False, 'error': 'Only PDF files supported'}), 400

    # Determine owner from auth cookie (required by @require_auth)
    owner, role = _current_user_info()

    # Save to temp file first
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', mode='wb') as temp_file:
        temp_path = temp_file.name
        file.save(temp_path)

    # Encrypt the file at rest and delete plaintext
    try:
        encrypted_path = _encrypt_file(temp_path)
    except Exception as e:
        # Clean up on encryption failure
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        logger.error(f"File encryption failed: {e}")
        return jsonify({'success': False, 'error': 'File processing failed'}), 500

    # Create opaque upload ID (cryptographically random)
    upload_id = secrets.token_hex(16)  # 32 hex chars, 128 bits of entropy
    uploaded_at = datetime.now()
    expires_at = uploaded_at + timedelta(seconds=UPLOAD_RETENTION_SECONDS)

    UPLOAD_STORE[upload_id] = {
        'path': encrypted_path,
        'filename': file.filename,
        'uploaded_at': uploaded_at,
        'expires_at': expires_at,
        'owner': owner,
        'encrypted': True
    }

    # Audit log the upload
    audit_log('upload', owner, {
        'upload_id': upload_id,
        'filename': file.filename,
        'size_bytes': os.path.getsize(encrypted_path)
    })

    logger.info(f"🔐 File uploaded and encrypted: {file.filename} -> upload_id={upload_id} (owner={owner})")

    return jsonify({
        'success': True,
        'upload_id': upload_id,
        'filename': file.filename,
        'expires_at': expires_at.isoformat()
    })


# ============================================================================
# SSE PROGRESS STREAM (SIMPLE - Like Test That Worked!)
# ============================================================================

@app.route('/api/progress/<session_id>')
def progress_stream(session_id):
    """SSE endpoint for real-time progress updates. Requires session ownership."""

    # Validate session ownership before allowing progress streaming
    if not _is_authorized_for_session(session_id):
        # For SSE, return a JSON error since we can't redirect
        return jsonify({'success': False, 'error': 'Unauthorized access to session'}), 403

    def generate():
        import time

        # Create or get queue (atomic to prevent race condition)
        progress_queues.setdefault(session_id, queue.Queue(maxsize=1000))
        q = progress_queues[session_id]

        # DIAGNOSTIC: Log SSE connection with timestamp
        start_time = time.time()
        logger.info(f"🔵 SSE connection opened: {session_id} at {datetime.now().isoformat()}")

        # Send connection event
        yield f"data: {json.dumps({'event': 'connected', 'session_id': session_id})}\n\n"
        logger.info(f"📤 Sent 'connected' event to client: {session_id}")

        # DIAGNOSTIC: Immediate test yield (should appear instantly in browser if no buffering)
        time.sleep(0.5)
        test_timestamp = time.time()
        yield f"data: {json.dumps({'event': 'diagnostic_test', 'message': 'Immediate yield test', 'timestamp': test_timestamp})}\n\n"
        logger.info(f"📤 Sent diagnostic test event: {session_id} (delta: {test_timestamp - start_time:.2f}s)")

        # Stream events
        while True:
            try:
                # Get next event (15 second timeout for keepalive)
                event_type, data = q.get(timeout=15)
                logger.info(f"📡 SSE sending: {event_type} at {datetime.now().isoformat()}")  # Changed to INFO

                # Check for done/error signals
                if event_type == 'done':
                    logger.info(f"✅ SSE sending 'done' event: {session_id}")
                    yield f"data: {json.dumps({'event': 'done'})}\n\n"
                    break

                if event_type == 'error':
                    logger.info(f"❌ SSE sending 'error' event: {session_id}")
                    yield f"data: {json.dumps({'event': 'error', 'error': data})}\n\n"
                    break

                # Send progress event
                yield f"data: {json.dumps({'event': event_type, **data})}\n\n"

            except queue.Empty:
                # Send keepalive
                logger.info(f"💓 SSE keepalive: {session_id} at {datetime.now().isoformat()}")  # Changed to INFO
                yield ": keepalive\n\n"

        # Cleanup
        if session_id in progress_queues:
            del progress_queues[session_id]

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


# ============================================================================
# POLLING ENDPOINT (NEW - Primary Progress Method)
# ============================================================================

@app.route('/api/events/<session_id>')
def get_events(session_id):
    """Get new events since last poll (replaces SSE streaming). Requires session ownership."""

    # Validate session ownership before returning events
    if not _is_authorized_for_session(session_id):
        return jsonify({'success': False, 'error': 'Unauthorized access to session'}), 403

    last_index = int(request.args.get('last_index', 0))

    # Get events for this session
    events = session_events.get(session_id, [])

    # Return only new events since last_index
    new_events = events[last_index:]

    logger.info(f"📡 Polling: session={session_id[:8]}..., last_index={last_index}, new_events={len(new_events)}")

    return jsonify({
        'success': True,
        'events': new_events,
        'last_index': len(events),  # Next index to request
        'total_events': len(events)
    })


# ============================================================================
# HOTDOG ANALYSIS (NON-BLOCKING with Threading)
# ============================================================================

@app.route('/api/analyze', methods=['POST'])
def analyze_document():
    """Start HOTDOG AI analysis in background thread. Uses cryptographically secure session IDs."""

    # Get request data
    data = request.json
    upload_id = data.get('upload_id')
    pdf_filename = data.get('pdf_filename', 'Unknown.pdf')  # Original filename for display
    context_guardrails = data.get('context_guardrails', '')
    enabled_sections = data.get('enabled_sections', None)  # NEW: Optional list of enabled section IDs
    analysis_mode = data.get('mode', 'bid_spec')  # Analysis mode (bid_spec or bestprep)
    recheck_empty_windows = data.get('recheck_empty_windows', False)  # Retry windows with 0 answers
    enable_second_pass = data.get('enable_second_pass', False)  # Retry unanswered questions
    enable_deep_rag = data.get('enable_deep_rag', False)  # External search for remaining
    pipeline_mode = data.get('pipeline_mode', 'classic')  # 'classic' or 'v2_pipeline'

    # SECURITY: Generate cryptographically secure session ID (ignore client-provided for security)
    session_id = f"sess_{secrets.token_hex(16)}"  # 32 hex chars + prefix = unguessable

    # Validate analysis mode
    if analysis_mode not in ['bid_spec', 'bestprep']:
        return jsonify({'success': False, 'error': 'Invalid mode. Must be "bid_spec" or "bestprep"'}), 400

    # Track session timestamp for cleanup
    session_timestamps[session_id] = datetime.now()

    # Validate upload_id
    if not upload_id or upload_id not in UPLOAD_STORE:
        return jsonify({'success': False, 'error': 'Upload not found or expired'}), 404

    upload_info = UPLOAD_STORE.get(upload_id)
    encrypted_path = upload_info.get('path')
    is_encrypted = upload_info.get('encrypted', False)

    # Ownership enforcement for uploads: if upload has owner, only that owner or admin may start analysis
    upload_owner = upload_info.get('owner')
    username, role = _current_user_info()
    if upload_owner and not (role == 'admin' or username == upload_owner):
        logger.warning(f"Unauthorized analysis start attempt by {username} for upload {upload_id[:8]}... owned by {upload_owner}")
        return jsonify({'success': False, 'error': 'Unauthorized: upload ownership mismatch'}), 403

    # Validate file exists
    if not encrypted_path or not os.path.exists(encrypted_path):
        return jsonify({'success': False, 'error': 'PDF file not found'}), 404

    # Decrypt the file for processing (creates temp decrypted copy)
    if is_encrypted:
        try:
            pdf_path = _decrypt_file(encrypted_path)
            logger.info(f"🔓 Decrypted upload for analysis: upload_id={upload_id[:8]}...")
        except Exception as e:
            logger.error(f"Failed to decrypt upload {upload_id[:8]}...: {e}")
            return jsonify({'success': False, 'error': 'Failed to process uploaded file'}), 500
    else:
        pdf_path = encrypted_path  # Legacy unencrypted upload

    # Get API key
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        # Clean up decrypted file if we created one
        if is_encrypted and pdf_path != encrypted_path:
            try:
                os.unlink(pdf_path)
            except:
                pass
        return jsonify({'success': False, 'error': 'API key not configured'}), 500

    # Audit log the analysis start
    audit_log('analyze_start', username, {
        'session_id': session_id,
        'upload_id': upload_id[:8] + '...',
        'filename': pdf_filename,
        'mode': analysis_mode
    })

    # Create progress queue for this session (atomic to prevent race condition)
    progress_queues.setdefault(session_id, queue.Queue(maxsize=1000))
    progress_q = progress_queues[session_id]

    # Create event list for polling (NEW)
    session_events.setdefault(session_id, [])

    # Define progress callback - stores events for BOTH SSE (legacy) and polling (NEW)
    def progress_callback(event_type: str, event_data: dict):
        # Store in list for polling (NEW - primary method)
        event_obj = {'event': event_type, **event_data, 'timestamp': datetime.now().isoformat()}
        session_events[session_id].append(event_obj)
        logger.info(f"📥 Event stored: {event_type} (total: {len(session_events[session_id])})")

        # Also queue for SSE (legacy compatibility)
        try:
            progress_q.put_nowait((event_type, event_data))
        except queue.Full:
            logger.warning(f"Progress queue full, dropping SSE event: {event_type}")

    # Track paths for cleanup (captured in closure)
    decrypted_pdf_path = pdf_path  # Path to decrypted temp file (if encrypted)
    source_upload_id = upload_id   # Upload ID for cleanup after completion
    source_encrypted = is_encrypted

    def _cleanup_temp_files():
        """Clean up decrypted temp file and optionally the encrypted upload."""
        # Always delete the decrypted temp file
        if source_encrypted and decrypted_pdf_path and os.path.exists(decrypted_pdf_path):
            try:
                os.unlink(decrypted_pdf_path)
                logger.info(f"🧹 Deleted decrypted temp file for session: {session_id[:12]}...")
            except Exception as e:
                logger.warning(f"Failed to delete decrypted temp file: {e}")

        # Delete the encrypted upload (analysis complete, no longer needed)
        _secure_delete_upload(source_upload_id)

    # Define analysis function to run in thread
    def run_analysis():
        try:
            logger.info(f"Starting analysis in thread: {session_id[:12]}...")
            if enabled_sections:
                logger.info(f"Enabled sections: {enabled_sections}")

            # Get config path
            config_path = str(Config.BASE_DIR / 'config' / 'cipp_questions_default.json')

            # Initialize orchestrator with mode and options
            orchestrator = HotdogOrchestrator(
                openai_api_key=openai_key,
                config_path=config_path,
                context_guardrails=context_guardrails,
                progress_callback=progress_callback,
                mode=analysis_mode,
                recheck_empty_windows=recheck_empty_windows,
                enable_second_pass=enable_second_pass,
                enable_deep_rag=enable_deep_rag,
                use_pipeline_v2=(pipeline_mode == 'v2_pipeline')
            )

            # Update pre-registered active_analyses entry with the now-ready orchestrator
            owner = username if username else None
            active_analyses[session_id].update({
                'orchestrator': orchestrator,
                'config_path': config_path,
                'status': 'running'
            })
            logger.info(f"Orchestrator ready in active_analyses: {session_id} (mode: {analysis_mode}, owner={owner})")

            # Run analysis (blocking in THIS thread, not main Flask thread)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    orchestrator.analyze_document(pdf_path, config_path, enabled_sections)
                )

                # Move to completed results
                analysis_results[session_id] = {
                    'result': result,
                    'orchestrator': orchestrator,
                    'config_path': config_path
                }

                # Format result for browser and store in session_events for polling
                from services.hotdog.layers import ConfigurationLoader
                config_loader = ConfigurationLoader()
                parsed_config = config_loader.load_from_json(config_path)
                browser_output = orchestrator.get_browser_output(result, parsed_config)
                legacy_result = _transform_to_legacy_format(browser_output)

                # Store full result in session_events so frontend can access via polling
                progress_callback('results_ready', {
                    'result': legacy_result,
                    'statistics': {
                        'processing_time': result.processing_time_seconds,
                        'total_tokens': result.total_tokens,
                        'estimated_cost': f"${result.estimated_cost:.4f}",
                        'questions_answered': result.questions_answered,
                        'total_questions': parsed_config.total_questions,
                        'average_confidence': f"{result.average_confidence:.0%}"
                    }
                })

                # CRITICAL: Atomic session movement with lock
                # Prevents admin panel from seeing mid-transition state
                with session_lock:
                    # Move from active to completed (preserve session data)
                    if session_id in active_analyses:
                        completed_analyses[session_id] = {
                            'result': result,
                            'orchestrator': orchestrator,
                            'config_path': config_path,
                            'pdf_path': '[CLEANED]',  # File is deleted after analysis - don't store actual path
                            'pdf_filename': pdf_filename,
                            'mode': analysis_mode,
                            'owner': owner,
                            'completed_at': datetime.now(),
                            'status': 'completed'
                        }
                        del active_analyses[session_id]
                        # Update timestamp so cleanup doesn't delete recently completed analyses
                        session_timestamps[session_id] = datetime.now()
                        logger.info(f"✅ Session moved to completed_analyses: {session_id[:12]}... (mode: {analysis_mode})")

                # Signal done
                progress_q.put(('done', {}))

                logger.info(f"Analysis complete: {session_id[:12]}...")

                # Audit log successful completion
                audit_log('analyze_complete', owner, {
                    'session_id': session_id,
                    'questions_answered': result.questions_answered,
                    'processing_time': f"{result.processing_time_seconds:.1f}s"
                })

            finally:
                loop.close()
                # Clean up temp files after analysis completes
                _cleanup_temp_files()

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            error_msg = str(e)
            progress_q.put(('error', error_msg))

            # Handle stopped vs failed analyses differently
            if 'stopped by user' in error_msg.lower():
                # CRITICAL: Atomic session movement with lock
                # Prevents /api/results from getting 404 before session moves to partial_analyses
                with session_lock:
                    # Move stopped analysis to partial_analyses (preserve partial data)
                    if session_id in active_analyses:
                        partial_analyses[session_id] = {
                            'orchestrator': active_analyses[session_id]['orchestrator'],
                            'config_path': active_analyses[session_id]['config_path'],
                            'pdf_path': '[CLEANED]',  # Don't store actual path
                            'pdf_filename': active_analyses[session_id].get('pdf_filename', 'Unknown.pdf'),
                            'mode': active_analyses[session_id].get('mode', 'bid_spec'),
                            'stopped_at': datetime.now(),
                            'status': 'stopped',
                            'error': error_msg,
                            'owner': active_analyses[session_id].get('owner')
                        }
                        del active_analyses[session_id]
                        # Update timestamp so cleanup doesn't delete stopped analyses
                        session_timestamps[session_id] = datetime.now()
                        logger.info(f"✅ Session moved to partial_analyses: {session_id[:12]}...")

                # Audit log user stop
                audit_log('analyze_stopped', username, {
                    'session_id': session_id
                })
            else:
                # FIX: Move failed analysis to partial_analyses instead of deleting.
                # Deleting caused permanent 403s — session vanished from all dicts,
                # so ownership checks failed and polling returned 403 instead of an error.
                with session_lock:
                    if session_id in active_analyses:
                        partial_analyses[session_id] = {
                            'orchestrator': active_analyses[session_id].get('orchestrator'),
                            'config_path': active_analyses[session_id].get('config_path', config_path),
                            'pdf_path': '[CLEANED]',
                            'pdf_filename': active_analyses[session_id].get('pdf_filename', pdf_filename),
                            'mode': active_analyses[session_id].get('mode', analysis_mode),
                            'stopped_at': datetime.now(),
                            'status': 'error',
                            'error': error_msg,
                            'owner': active_analyses[session_id].get('owner')
                        }
                        del active_analyses[session_id]
                        session_timestamps[session_id] = datetime.now()
                        logger.info(f"Session moved to partial_analyses (error): {session_id[:12]}...")

                # Audit log failure (don't include full error message - may contain sensitive info)
                audit_log('analyze_failed', username, {
                    'session_id': session_id,
                    'error_type': type(e).__name__
                })

            # Always clean up temp files on failure
            _cleanup_temp_files()

    # FIX: Pre-register session in active_analyses BEFORE starting thread to eliminate
    # race condition where early polls arrive before thread has inited the orchestrator.
    owner = username if username else None
    active_analyses[session_id] = {
        'orchestrator': None,  # Populated by thread once orchestrator is ready
        'config_path': None,
        'pdf_path': pdf_path,
        'pdf_filename': pdf_filename,
        'mode': analysis_mode,
        'owner': owner,
        'status': 'initializing'
    }
    logger.info(f"Session pre-registered in active_analyses (main thread): {session_id[:12]}... owner={owner}")

    # Start analysis thread
    thread = threading.Thread(target=run_analysis, daemon=True)
    analysis_threads[session_id] = thread
    thread.start()

    logger.info(f"Analysis thread started: {session_id}")

    # Return immediately (don't wait for analysis)
    return jsonify({
        'success': True,
        'session_id': session_id,
        'message': 'Analysis started in background'
    })


# ============================================================================
# GET RESULTS
# ============================================================================

def _extract_bestprep_data(orchestrator):
    """Extract BestPrep accumulator data (fragments, footnotes) for API responses."""
    from services.hotdog.mode_config import AnalysisMode

    if orchestrator.mode != AnalysisMode.BESTPREP or not orchestrator.bestprep_accumulator:
        return None

    accumulator = orchestrator.bestprep_accumulator
    bestprep_data = {
        'fragments': [],
        'footnotes': [],
        'statistics': {
            'total_fragments': 0,
            'total_footnotes': 0,
            'questions_with_fragments': 0
        }
    }

    # Extract all fragments and footnotes
    for qid, ca in accumulator.get_all_cumulative_answers().items():
        if ca.fragments:
            bestprep_data['statistics']['questions_with_fragments'] += 1
            for frag in ca.fragments:
                bestprep_data['fragments'].append({
                    'question_id': qid,
                    'question_text': ca.question_text,
                    'text': frag.text,
                    'pages': frag.pages,
                    'confidence': frag.confidence,
                    'expert': frag.expert_name,
                    'window': frag.window_index
                })
                bestprep_data['statistics']['total_fragments'] += 1

        if ca.footnotes:
            for fn in ca.footnotes:
                bestprep_data['footnotes'].append({
                    'question_id': qid,
                    'footnote_id': fn.footnote_id,
                    'quote': fn.quote,
                    'page': fn.page,
                    'text': fn.text
                })
                bestprep_data['statistics']['total_footnotes'] += 1

    return bestprep_data

@app.route('/api/results/<session_id>', methods=['GET'])
def get_results(session_id):
    """
    Get analysis results (supports completed, partial, and in-progress analyses).

    THREAD SAFETY: Uses session_lock to prevent race conditions when checking
    which dict contains the session (completed vs partial vs active).
    """

    # CRITICAL: Atomic session lookup with lock
    # Prevents race where session moves between dicts during lookup
    with session_lock:
        # Check completed_analyses first (NEW - primary storage)
        if session_id in completed_analyses:
            # Touch timestamp to keep session alive
            session_timestamps[session_id] = datetime.now()
            session_data = completed_analyses[session_id]
            session_type = 'completed'
        elif session_id in partial_analyses:
            # Touch timestamp to keep session alive
            session_timestamps[session_id] = datetime.now()
            session_data = partial_analyses[session_id]
            session_type = 'partial'
        elif session_id in analysis_results:
            session_data = analysis_results[session_id]
            session_type = 'legacy'
        elif session_id in active_analyses:
            session_data = active_analyses[session_id]
            session_type = 'active'
        else:
            # Session not found in any dict
            logger.warning(f"Session not found: {session_id}")
            logger.info(f"Active: {list(active_analyses.keys())}")
            logger.info(f"Completed: {list(completed_analyses.keys())}")
            logger.info(f"Partial: {list(partial_analyses.keys())}")
            return jsonify({
                'success': False,
                'error': 'Session not found',
                'message': 'Analysis session does not exist or has been cleaned up'
            }), 404

    # Enforce ownership / admin access for session results
    if not _is_authorized_for_session(session_id):
        return jsonify({'success': False, 'error': 'Unauthorized access to session results'}), 403

    # Audit log results access
    username, _ = _current_user_info()
    audit_log('get_results', username, {
        'session_id': session_id,
        'session_type': session_type
    })

    # Process results based on session type (outside lock to avoid long hold)
    from services.hotdog.layers import ConfigurationLoader
    config_loader = ConfigurationLoader()

    if session_type == 'completed':
        result = session_data['result']
        orchestrator = session_data['orchestrator']

        # CRITICAL: Use cached_config from orchestrator (filtered to analyzed sections/questions)
        # NOT the full config from JSON file
        parsed_config = orchestrator.cached_config
        if not parsed_config:
            # Fallback to loading from file if cached_config not available
            parsed_config = config_loader.load_from_json(session_data['config_path'])

        browser_output = orchestrator.get_browser_output(result, parsed_config)
        legacy_result = _transform_to_legacy_format(browser_output)

        # Get mode for response
        mode = session_data.get('mode', 'bid_spec')

        # Build response
        response = {
            'success': True,
            'result': legacy_result,
            'mode': mode,
            'statistics': {
                'processing_time': result.processing_time_seconds,
                'total_tokens': result.total_tokens,
                'estimated_cost': f"${result.estimated_cost:.4f}",
                'questions_answered': result.questions_answered,
                'total_questions': parsed_config.total_questions,
                'average_confidence': f"{result.average_confidence:.0%}"
            }
        }

        # Add key requirements from orchestrator (for bid_spec mode)
        # Use get_summary_data() for JSON-serializable output (extracted_key_requirements contains dataclass objects)
        if hasattr(orchestrator, 'key_requirements_extractor') and orchestrator.key_requirements_extractor:
            key_reqs = orchestrator.key_requirements_extractor.get_summary_data()
            if key_reqs:
                response['key_requirements'] = key_reqs

        # Add BestPrep-specific data if available
        bestprep_data = _extract_bestprep_data(orchestrator)
        if bestprep_data:
            response['bestprep_data'] = bestprep_data

        # Add V2 pipeline data (document navigator audit, unanswered pass, RAG)
        if hasattr(orchestrator, 'optimized_scan_data') and orchestrator.optimized_scan_data:
            response['optimized_scan_data'] = orchestrator.optimized_scan_data
            response['use_pipeline_v2'] = True
        if hasattr(orchestrator, 'unanswered_pass_data') and orchestrator.unanswered_pass_data:
            response['unanswered_pass_data'] = orchestrator.unanswered_pass_data
        if hasattr(orchestrator, 'rag_data') and orchestrator.rag_data:
            response['rag_data'] = orchestrator.rag_data

        return jsonify(response)

    elif session_type == 'legacy':
        result = session_data['result']
        orchestrator = session_data['orchestrator']

        # CRITICAL: Use cached_config from orchestrator (filtered to analyzed sections/questions)
        parsed_config = orchestrator.cached_config
        if not parsed_config:
            parsed_config = config_loader.load_from_json(session_data['config_path'])

        browser_output = orchestrator.get_browser_output(result, parsed_config)
        legacy_result = _transform_to_legacy_format(browser_output)

        mode = session_data.get('mode', 'bid_spec')

        # Build response
        response = {
            'success': True,
            'result': legacy_result,
            'mode': mode,
            'statistics': {
                'processing_time': result.processing_time_seconds,
                'total_tokens': result.total_tokens,
                'estimated_cost': f"${result.estimated_cost:.4f}",
                'questions_answered': result.questions_answered,
                'total_questions': parsed_config.total_questions,
                'average_confidence': f"{result.average_confidence:.0%}"
            }
        }

        # Add key requirements from orchestrator (for bid_spec mode)
        # Use get_summary_data() for JSON-serializable output (extracted_key_requirements contains dataclass objects)
        if hasattr(orchestrator, 'key_requirements_extractor') and orchestrator.key_requirements_extractor:
            key_reqs = orchestrator.key_requirements_extractor.get_summary_data()
            if key_reqs:
                response['key_requirements'] = key_reqs

        # Add BestPrep-specific data if available
        bestprep_data = _extract_bestprep_data(orchestrator)
        if bestprep_data:
            response['bestprep_data'] = bestprep_data

        # Add V2 pipeline data (document navigator audit, unanswered pass, RAG)
        if hasattr(orchestrator, 'optimized_scan_data') and orchestrator.optimized_scan_data:
            response['optimized_scan_data'] = orchestrator.optimized_scan_data
            response['use_pipeline_v2'] = True
        if hasattr(orchestrator, 'unanswered_pass_data') and orchestrator.unanswered_pass_data:
            response['unanswered_pass_data'] = orchestrator.unanswered_pass_data
        if hasattr(orchestrator, 'rag_data') and orchestrator.rag_data:
            response['rag_data'] = orchestrator.rag_data

        return jsonify(response)

    elif session_type == 'partial':
        logger.info(f"Fetching results for partial analysis: {session_id}")
        orchestrator = session_data['orchestrator']
        config_path = session_data['config_path']
        mode = session_data.get('mode', 'bid_spec')

        # Get accumulated answers based on mode
        from services.hotdog.mode_config import AnalysisMode
        if orchestrator.mode == AnalysisMode.BESTPREP and orchestrator.bestprep_accumulator:
            # Build accumulated_answers from BestPrep accumulator
            accumulated_answers = {}
            for qid, ca in orchestrator.bestprep_accumulator.get_all_cumulative_answers().items():
                if ca.fragments:
                    from services.hotdog.models import Answer
                    best_frag = max(ca.fragments, key=lambda f: f.confidence)
                    try:
                        mock_answer = Answer(
                            question_id=qid,
                            text=best_frag.text,
                            pages=best_frag.pages,
                            confidence=best_frag.confidence,
                            expert=best_frag.expert_name,
                            window=best_frag.window_index
                        )
                        accumulated_answers[qid] = [mock_answer]
                    except ValueError:
                        pass
        else:
            accumulated_answers = orchestrator.layer4_accumulator.get_accumulated_answers()

        # CRITICAL: Use cached_config (filtered) instead of full config from JSON
        parsed_config = orchestrator.cached_config
        if not parsed_config:
            parsed_config = config_loader.load_from_json(config_path)

        # Build partial browser output
        partial_browser_output = orchestrator._build_partial_browser_output(
            accumulated_answers,
            parsed_config
        )

        # Transform to legacy format
        legacy_result = _transform_to_legacy_format(partial_browser_output)

        # Build response
        response = {
            'success': True,
            'result': legacy_result,
            'partial': True,  # Flag indicating partial results
            'mode': mode,
            'statistics': {
                'processing_time': 0,  # Not yet available
                'total_tokens': orchestrator.layer5_token_manager.total_tokens_used,
                'estimated_cost': 'Stopped',
                'questions_answered': len([a for answers in accumulated_answers.values() for a in answers]),
                'total_questions': parsed_config.total_questions,
                'average_confidence': 'Partial'
            }
        }

        # Add key requirements from orchestrator (for bid_spec mode)
        # Use get_summary_data() for JSON-serializable output (extracted_key_requirements contains dataclass objects)
        if hasattr(orchestrator, 'key_requirements_extractor') and orchestrator.key_requirements_extractor:
            key_reqs = orchestrator.key_requirements_extractor.get_summary_data()
            if key_reqs:
                response['key_requirements'] = key_reqs

        # Add BestPrep-specific data if available
        bestprep_data = _extract_bestprep_data(orchestrator)
        if bestprep_data:
            response['bestprep_data'] = bestprep_data

        # Add V2 pipeline data (document navigator audit, unanswered pass, RAG)
        if hasattr(orchestrator, 'optimized_scan_data') and orchestrator.optimized_scan_data:
            response['optimized_scan_data'] = orchestrator.optimized_scan_data
            response['use_pipeline_v2'] = True
        if hasattr(orchestrator, 'unanswered_pass_data') and orchestrator.unanswered_pass_data:
            response['unanswered_pass_data'] = orchestrator.unanswered_pass_data
        if hasattr(orchestrator, 'rag_data') and orchestrator.rag_data:
            response['rag_data'] = orchestrator.rag_data

        return jsonify(response)

    elif session_type == 'active':
        logger.info(f"Fetching partial results for active analysis: {session_id}")
        orchestrator = session_data['orchestrator']
        config_path = session_data['config_path']
        mode = session_data.get('mode', 'bid_spec')

        # Get accumulated answers based on mode
        from services.hotdog.mode_config import AnalysisMode
        if orchestrator.mode == AnalysisMode.BESTPREP and orchestrator.bestprep_accumulator:
            # Build accumulated_answers from BestPrep accumulator
            accumulated_answers = {}
            for qid, ca in orchestrator.bestprep_accumulator.get_all_cumulative_answers().items():
                if ca.fragments:
                    from services.hotdog.models import Answer
                    best_frag = max(ca.fragments, key=lambda f: f.confidence)
                    try:
                        mock_answer = Answer(
                            question_id=qid,
                            text=best_frag.text,
                            pages=best_frag.pages,
                            confidence=best_frag.confidence,
                            expert=best_frag.expert_name,
                            window=best_frag.window_index
                        )
                        accumulated_answers[qid] = [mock_answer]
                    except ValueError:
                        pass
        else:
            accumulated_answers = orchestrator.layer4_accumulator.get_accumulated_answers()

        # CRITICAL: Use cached_config (filtered) instead of full config from JSON
        parsed_config = orchestrator.cached_config
        if not parsed_config:
            parsed_config = config_loader.load_from_json(config_path)

        # Build partial browser output
        partial_browser_output = orchestrator._build_partial_browser_output(
            accumulated_answers,
            parsed_config
        )

        # Transform to legacy format
        legacy_result = _transform_to_legacy_format(partial_browser_output)

        # Build response
        response = {
            'success': True,
            'result': legacy_result,
            'partial': True,  # Flag indicating in-progress
            'mode': mode,
            'statistics': {
                'processing_time': 0,  # Not yet available
                'total_tokens': orchestrator.layer5_token_manager.total_tokens_used,
                'estimated_cost': 'In progress',
                'questions_answered': len([a for answers in accumulated_answers.values() for a in answers]),
                'total_questions': parsed_config.total_questions,
                'average_confidence': 'In progress'
            }
        }

        # Add BestPrep-specific data if available
        bestprep_data = _extract_bestprep_data(orchestrator)
        if bestprep_data:
            response['bestprep_data'] = bestprep_data

        # Add V2 pipeline data (document navigator audit, unanswered pass, RAG)
        if hasattr(orchestrator, 'optimized_scan_data') and orchestrator.optimized_scan_data:
            response['optimized_scan_data'] = orchestrator.optimized_scan_data
            response['use_pipeline_v2'] = True
        if hasattr(orchestrator, 'unanswered_pass_data') and orchestrator.unanswered_pass_data:
            response['unanswered_pass_data'] = orchestrator.unanswered_pass_data
        if hasattr(orchestrator, 'rag_data') and orchestrator.rag_data:
            response['rag_data'] = orchestrator.rag_data

        return jsonify(response)

    # Should never reach here due to lock check above
    return jsonify({'success': False, 'error': 'Internal error'}), 500


# ============================================================================
# EXCEL DASHBOARD EXPORT
# ============================================================================

@app.route('/api/export/excel-dashboard/<session_id>', methods=['GET'])
def export_excel_dashboard(session_id):
    """Generate executive Excel dashboard with charts (supports partial results)"""

    browser_output = None
    is_partial = False

    # Authorization check
    if not _is_authorized_for_session(session_id):
        return jsonify({'success': False, 'error': 'Unauthorized access to export'}), 403

    # Check completed_analyses first (NEW - primary storage)
    if session_id in completed_analyses:
        logger.info(f"Exporting completed analysis: {session_id}")
        session_data = completed_analyses[session_id]
        result = session_data['result']
        orchestrator = session_data['orchestrator']
        config_path = session_data['config_path']

        # CRITICAL: Use cached_config (filtered to analyzed sections) not full config file
        from services.hotdog.layers import ConfigurationLoader
        parsed_config = orchestrator.cached_config
        if not parsed_config:
            # Fallback to loading from file if cached_config not available
            config_loader = ConfigurationLoader()
            parsed_config = config_loader.load_from_json(config_path)
        browser_output = orchestrator.get_browser_output(result, parsed_config)
        is_partial = False

    # Check legacy analysis_results (LEGACY - backward compatibility)
    elif session_id in analysis_results:
        logger.info(f"Exporting completed analysis (legacy): {session_id}")
        session_data = analysis_results[session_id]
        result = session_data['result']
        orchestrator = session_data['orchestrator']
        config_path = session_data['config_path']

        # CRITICAL: Use cached_config (filtered to analyzed sections) not full config file
        from services.hotdog.layers import ConfigurationLoader
        parsed_config = orchestrator.cached_config
        if not parsed_config:
            config_loader = ConfigurationLoader()
            parsed_config = config_loader.load_from_json(config_path)
        browser_output = orchestrator.get_browser_output(result, parsed_config)
        is_partial = False

    # Check partial_analyses (stopped by user)
    elif session_id in partial_analyses:
        logger.info(f"Exporting partial analysis: {session_id}")
        session_data = partial_analyses[session_id]
        orchestrator = session_data['orchestrator']
        config_path = session_data['config_path']

        # Get accumulated answers so far
        accumulated_answers = orchestrator.layer4_accumulator.get_accumulated_answers()

        # CRITICAL: Use cached_config (filtered to analyzed sections) not full config file
        from services.hotdog.layers import ConfigurationLoader
        parsed_config = orchestrator.cached_config
        if not parsed_config:
            config_loader = ConfigurationLoader()
            parsed_config = config_loader.load_from_json(config_path)

        # Build partial browser output
        browser_output = orchestrator._build_partial_browser_output(
            accumulated_answers,
            parsed_config
        )
        is_partial = True

    # Check active analyses (in-progress)
    elif session_id in active_analyses:
        logger.info(f"Exporting partial/stopped analysis: {session_id}")
        session_data = active_analyses[session_id]
        orchestrator = session_data['orchestrator']
        config_path = session_data['config_path']

        # Get accumulated answers so far
        accumulated_answers = orchestrator.layer4_accumulator.get_accumulated_answers()

        # CRITICAL: Use cached_config (filtered to analyzed sections) not full config file
        from services.hotdog.layers import ConfigurationLoader
        parsed_config = orchestrator.cached_config
        if not parsed_config:
            config_loader = ConfigurationLoader()
            parsed_config = config_loader.load_from_json(config_path)

        # Build partial browser output
        browser_output = orchestrator._build_partial_browser_output(
            accumulated_answers,
            parsed_config
        )
        is_partial = True

    else:
        return jsonify({'success': False, 'error': 'Session not found'}), 404

    try:
        # Lazy import to prevent app crash if openpyxl not installed
        from services.excel_dashboard import ExcelDashboardGenerator

        # CRITICAL: Transform to legacy format for Excel generator
        # The Excel generator expects {'question': ..., 'answer': ..., 'page_citations': ...}
        # but browser_output has {'question_text': ..., 'primary_answer': {'text': ..., 'pages': ...}}
        legacy_result = _transform_to_legacy_format(browser_output)

        # Extract API key requirements if available (from KeyRequirementsExtractor)
        api_key_requirements = browser_output.get('key_requirements', {})

        # Extract V2 pipeline data (document navigator audit, unanswered pass, RAG)
        optimized_scan_data = None
        unanswered_pass_data = None
        rag_data = None
        if hasattr(orchestrator, 'optimized_scan_data') and orchestrator.optimized_scan_data:
            optimized_scan_data = orchestrator.optimized_scan_data
        if hasattr(orchestrator, 'unanswered_pass_data') and orchestrator.unanswered_pass_data:
            unanswered_pass_data = orchestrator.unanswered_pass_data
        if hasattr(orchestrator, 'rag_data') and orchestrator.rag_data:
            rag_data = orchestrator.rag_data

        # Generate Excel dashboard (now works with both complete and partial)
        generator = ExcelDashboardGenerator(
            legacy_result,
            is_partial=is_partial,
            api_key_requirements=api_key_requirements,
            optimized_scan_data=optimized_scan_data,
            unanswered_pass_data=unanswered_pass_data,
            rag_data=rag_data
        )
        excel_file = generator.generate()

        # Build filename from project name (KRP) + date + mode
        from datetime import datetime
        import re

        # Try to get project name from key requirements first
        project_name = None
        if api_key_requirements:
            project_name = api_key_requirements.get('project_name') or api_key_requirements.get('Project Name')

        # Fallback to document name
        if not project_name:
            project_name = legacy_result.get('document_name', 'Analysis')

        # Clean the name for filename use
        project_name = re.sub(r'\.pdf$', '', project_name, flags=re.IGNORECASE)
        project_name = re.sub(r'<PDF pg[^>]+>', '', project_name)  # Remove PDF citations
        project_name = re.sub(r'[^\w\s-]', '', project_name).strip()
        project_name = re.sub(r'\s+', '_', project_name)[:50]  # Limit length

        date_str = datetime.now().strftime('%Y-%m-%d')
        partial_suffix = '_PARTIAL' if is_partial else ''
        mode_suffix = '_bidspec'  # This endpoint is for bid/spec mode
        filename = f'{project_name}_{date_str}{mode_suffix}{partial_suffix}.xlsx'

        # Audit log export
        username, _ = _current_user_info()
        audit_log('export_excel_dashboard', username, {
            'session_id': session_id,
            'filename': filename,
            'is_partial': is_partial
        })

        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"Excel export failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# BESTPREP EXCEL EXPORT
# ============================================================================

@app.route('/api/export/bestprep-excel/<session_id>', methods=['GET'])
def export_bestprep_excel(session_id):
    """Generate comprehensive BestPrep Excel report with all fragments and footnotes"""
    from services.hotdog.mode_config import AnalysisMode

    logger.info(f"BestPrep Excel export requested for session: {session_id}")

    # Authorization check
    if not _is_authorized_for_session(session_id):
        return jsonify({'success': False, 'error': 'Unauthorized access to export'}), 403

    # Find session in completed, partial, active, or legacy analyses
    session_data = None
    is_partial = False
    session_type = None

    with session_lock:
        if session_id in completed_analyses:
            session_data = completed_analyses[session_id]
            session_type = 'completed'
        elif session_id in partial_analyses:
            session_data = partial_analyses[session_id]
            is_partial = True
            session_type = 'partial'
        elif session_id in active_analyses:
            session_data = active_analyses[session_id]
            is_partial = True
            session_type = 'active'
        elif session_id in analysis_results:
            session_data = analysis_results[session_id]
            session_type = 'legacy'

    if not session_data:
        logger.error(f"BestPrep export failed: Session not found: {session_id}")
        return jsonify({'success': False, 'error': 'Session not found'}), 404

    logger.info(f"Found session in {session_type} analyses")

    orchestrator = session_data.get('orchestrator')
    if not orchestrator:
        logger.error(f"BestPrep export failed: No orchestrator in session data")
        return jsonify({'success': False, 'error': 'Session data incomplete - no orchestrator'}), 400

    # Verify this is a BestPrep analysis
    try:
        if orchestrator.mode != AnalysisMode.BESTPREP:
            logger.warning(f"Not a BestPrep analysis - mode is: {orchestrator.mode}")
            return jsonify({
                'success': False,
                'error': 'Not a BestPrep analysis. Use standard Excel export instead.'
            }), 400
    except Exception as e:
        logger.error(f"Error checking mode: {e}")
        return jsonify({'success': False, 'error': f'Could not determine analysis mode: {e}'}), 400

    if not orchestrator.bestprep_accumulator:
        logger.error(f"BestPrep export failed: No accumulator data")
        return jsonify({'success': False, 'error': 'No BestPrep accumulator data available. Analysis may not have collected any answers yet.'}), 400

    try:
        from services.bestprep_excel import BestPrepExcelGenerator

        # Get accumulator data
        accumulator_data = orchestrator.bestprep_accumulator.to_dict()
        logger.info(f"Accumulator data retrieved: {len(accumulator_data.get('cumulative_answers', {}))} questions")


        # Build result dict for generator
        result_dict = {
            'document_name': session_data.get('pdf_filename', 'Unknown'),
            'mode': 'bestprep'
        }

        generator = BestPrepExcelGenerator(
            analysis_result=result_dict,
            accumulator_data=accumulator_data
        )

        excel_file = generator.generate()

        # Build filename from project name (KRP) + date + mode
        import re

        # Try to get project name from key requirements first
        project_name = None
        if hasattr(orchestrator, 'extracted_key_requirements') and orchestrator.extracted_key_requirements:
            project_name = orchestrator.extracted_key_requirements.get('project_name') or orchestrator.extracted_key_requirements.get('Project Name')

        # Fallback to document name
        if not project_name:
            project_name = session_data.get('pdf_filename', 'BestPrep_Analysis')

        # Clean the name for filename use
        project_name = re.sub(r'\.pdf$', '', project_name, flags=re.IGNORECASE)
        project_name = re.sub(r'<PDF pg[^>]+>', '', project_name)  # Remove PDF citations
        project_name = re.sub(r'[^\w\s-]', '', project_name).strip()
        project_name = re.sub(r'\s+', '_', project_name)[:50]

        date_str = datetime.now().strftime('%Y-%m-%d')
        partial_suffix = '_PARTIAL' if is_partial else ''
        filename = f'{project_name}_{date_str}_bestprep{partial_suffix}.xlsx'

        logger.info(f"BestPrep Excel export successful: {filename}")

        # Audit log export
        username, _ = _current_user_info()
        audit_log('export_bestprep_excel', username, {
            'session_id': session_id,
            'filename': filename,
            'is_partial': is_partial
        })

        return send_file(
            excel_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"BestPrep Excel export failed: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# STOP ANALYSIS
# ============================================================================

@app.route('/api/stop/<session_id>', methods=['POST'])
def stop_analysis(session_id):
    """
    Stop ongoing analysis and wait for session to move to partial_analyses.
    Requires session ownership.

    CRITICAL FIX: This endpoint now WAITS for the analysis thread to move
    the session from active_analyses to partial_analyses before returning.
    This prevents race condition where frontend calls fetchResults() before
    session is available.

    See: STOP_ANALYSIS_RACE_CONDITION.md
    """
    # Validate session ownership before allowing stop
    if not _is_authorized_for_session(session_id):
        return jsonify({'success': False, 'error': 'Unauthorized access to session'}), 403

    logger.info(f"⏹️  Stop requested for: {session_id[:12]}...")

    # Check if session exists (with lock for thread safety)
    with session_lock:
        # Already completed or stopped?
        if session_id in completed_analyses:
            logger.info(f"Analysis already complete: {session_id}")
            return jsonify({'success': True, 'message': 'Analysis already complete'})

        if session_id in partial_analyses:
            logger.info(f"Analysis already stopped: {session_id}")
            return jsonify({'success': True, 'message': 'Analysis already stopped'})

        if session_id in analysis_results:
            logger.info(f"Analysis already complete (legacy): {session_id}")
            return jsonify({'success': True, 'message': 'Analysis already complete'})

        # Is it active?
        if session_id not in active_analyses:
            logger.warning(f"Session not found: {session_id}")
            logger.info(f"Active: {list(active_analyses.keys())}")
            return jsonify({'success': False, 'error': 'Session not found'}), 404

        # Set stop flag on orchestrator (may be None if still initializing — safe to skip)
        orchestrator = active_analyses[session_id].get('orchestrator')
        if orchestrator:
            orchestrator.stop_requested = True
            logger.info(f"✅ Stop flag set on orchestrator: {session_id}")
        else:
            logger.info(f"⏳ Stop requested but orchestrator still initializing: {session_id}")

    # Send error event to progress queue
    if session_id in progress_queues:
        try:
            progress_queues[session_id].put_nowait(('error', 'Analysis stopped by user'))
            logger.info(f"Stop event queued: {session_id}")
        except:
            pass  # Queue might be full

    # CRITICAL: Wait for session to move to partial_analyses
    # The analysis thread will catch the exception and move the session
    max_wait = 10.0  # 10 seconds timeout
    start_time = time.time()
    check_interval = 0.1  # Check every 100ms

    logger.info(f"⏳ Waiting for session to move to partial_analyses (max {max_wait}s)...")

    while time.time() - start_time < max_wait:
        with session_lock:
            # Check if session moved to partial_analyses or completed
            if session_id in partial_analyses:
                elapsed = time.time() - start_time
                logger.info(f"✅ Session moved to partial_analyses ({elapsed:.2f}s): {session_id}")
                return jsonify({
                    'success': True,
                    'message': 'Analysis stopped',
                    'status': 'partial',
                    'wait_time': f"{elapsed:.2f}s"
                })

            if session_id in completed_analyses:
                elapsed = time.time() - start_time
                logger.info(f"✅ Session completed before stop ({elapsed:.2f}s): {session_id}")
                return jsonify({
                    'success': True,
                    'message': 'Analysis completed',
                    'status': 'completed',
                    'wait_time': f"{elapsed:.2f}s"
                })

            # Still in active_analyses - keep waiting
            if session_id not in active_analyses:
                # Session disappeared (unexpected)
                logger.warning(f"⚠️ Session vanished during stop: {session_id}")
                return jsonify({
                    'success': False,
                    'error': 'Session disappeared during stop'
                }), 500

        time.sleep(check_interval)

    # Timeout - session still in active_analyses
    logger.error(f"❌ Timeout waiting for session to stop ({max_wait}s): {session_id}")
    return jsonify({
        'success': False,
        'error': f'Stop timeout - session still active after {max_wait}s',
        'message': 'Try refreshing the page or check analysis logs'
    }), 504


# ============================================================================
# ON-DEMAND PROCESSING ENDPOINTS (HOTDOG7ATE)
# ============================================================================

@app.route('/api/analyze/second-pass/<session_id>', methods=['POST'])
@require_auth
def run_second_pass_on_selected(session_id):
    """
    Run second pass on selected questions for a completed/partial analysis.

    POST body:
    {
        "question_ids": ["Q1", "Q5", "Q12"]  // Questions to reprocess
    }
    """
    import asyncio
    from openai import AsyncOpenAI

    data = request.get_json()
    question_ids = data.get('question_ids', [])

    if not question_ids:
        return jsonify({'error': 'No questions specified'}), 400

    # Get analysis from completed or partial
    with session_lock:
        session_data = completed_analyses.get(session_id) or partial_analyses.get(session_id)
        if not session_data:
            return jsonify({'error': 'Analysis not found'}), 404

        orchestrator = session_data.get('orchestrator')
        result = session_data.get('result')

    if not orchestrator or not orchestrator.cached_config:
        return jsonify({'error': 'Analysis config not available'}), 400

    config = orchestrator.cached_config

    # Filter to requested questions
    questions = [
        config.question_map[qid]
        for qid in question_ids
        if qid in config.question_map
    ]

    if not questions:
        return jsonify({'error': 'No valid questions found'}), 400

    logger.info(f"Running second pass on {len(questions)} questions for session {session_id}")

    try:
        # Run second pass using the orchestrator's second pass processor
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        second_pass_answers = loop.run_until_complete(
            orchestrator.layer3_5_second_pass.process_unanswered_questions(
                windows=orchestrator.cached_windows if hasattr(orchestrator, 'cached_windows') else [],
                unanswered_questions=questions,
                experts=orchestrator.cached_experts if hasattr(orchestrator, 'cached_experts') else {}
            )
        )
        loop.close()

        # Update the result with new answers
        answers_found = 0
        for qid, answer in second_pass_answers.items():
            if result and 'answers' in result:
                if qid not in result['answers']:
                    result['answers'][qid] = []
                result['answers'][qid].append({
                    'text': answer.text,
                    'pages': answer.pages,
                    'confidence': answer.confidence,
                    'expert': answer.expert,
                    'source': 'second_pass'
                })
                answers_found += 1

        logger.info(f"Second pass complete: {answers_found} new answers")

        return jsonify({
            'status': 'complete',
            'answers_found': answers_found,
            'questions_processed': len(questions)
        })

    except Exception as e:
        logger.error(f"Second pass failed: {str(e)}", exc_info=True)
        return jsonify({'error': f'Second pass failed: {str(e)}'}), 500


@app.route('/api/analyze/rag/<session_id>', methods=['POST'])
@require_auth
def run_deep_rag_on_selected(session_id):
    """
    Run Deep RAG on selected questions for a completed/partial analysis.
    Searches external sources (TAVILY) for similar projects.

    POST body:
    {
        "question_ids": ["Q1", "Q5", "Q12"]  // Questions to search externally
    }
    """
    import asyncio
    from openai import AsyncOpenAI

    data = request.get_json()
    question_ids = data.get('question_ids', [])

    if not question_ids:
        return jsonify({'error': 'No questions specified'}), 400

    # Check if TAVILY API key is available
    tavily_key = os.environ.get('TAVILY_API_KEY')
    if not tavily_key:
        return jsonify({
            'error': 'Deep RAG not available',
            'message': 'TAVILY_API_KEY not configured. Contact administrator to enable external search.'
        }), 503

    # Get analysis from completed or partial
    with session_lock:
        session_data = completed_analyses.get(session_id) or partial_analyses.get(session_id)
        if not session_data:
            return jsonify({'error': 'Analysis not found'}), 404

        orchestrator = session_data.get('orchestrator')
        result = session_data.get('result')

    if not orchestrator or not orchestrator.cached_config:
        return jsonify({'error': 'Analysis config not available'}), 400

    config = orchestrator.cached_config

    # Filter to requested questions
    questions = [
        config.question_map[qid]
        for qid in question_ids
        if qid in config.question_map
    ]

    if not questions:
        return jsonify({'error': 'No valid questions found'}), 400

    logger.info(f"Running Deep RAG on {len(questions)} questions for session {session_id}")

    try:
        from services.hotdog.deep_rag_processor import DeepRAGProcessor

        # Initialize RAG processor
        rag_processor = DeepRAGProcessor()

        if not rag_processor.is_available:
            return jsonify({
                'error': 'Deep RAG not available',
                'message': 'TAVILY service not configured properly'
            }), 503

        # Extract project context from key requirements
        key_reqs = orchestrator.extracted_key_requirements if hasattr(orchestrator, 'extracted_key_requirements') else {}

        # Run RAG search with project context and questions
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        rag_results = loop.run_until_complete(
            rag_processor.search_similar_projects(
                owner=key_reqs.get('owner'),
                engineer=key_reqs.get('engineer'),
                project_type=key_reqs.get('project_name'),
                location=key_reqs.get('location'),
                unanswered_questions=[
                    {'id': q.id, 'text': q.text} for q in questions
                ]
            )
        )
        loop.close()

        # Format results for response
        formatted_results = {}
        answers_found = 0

        for qid, answer_data in rag_results.get('answers', {}).items():
            if answer_data.get('text'):
                formatted_results[qid] = {
                    'answer': answer_data.get('text', ''),
                    'confidence': answer_data.get('confidence', 0.3),
                    'source': answer_data.get('source', 'External'),
                    'source_type': 'external_rag',
                    'disclaimer': '⚠️ This answer is from EXTERNAL sources and may not apply to this project. Always verify with official documents.'
                }
                answers_found += 1

        logger.info(f"Deep RAG complete: {answers_found} potential answers found")

        return jsonify({
            'status': 'complete',
            'answers_found': answers_found,
            'questions_processed': len(questions),
            'results': formatted_results
        })

    except Exception as e:
        logger.error(f"Deep RAG failed: {str(e)}", exc_info=True)
        return jsonify({'error': f'Deep RAG failed: {str(e)}'}), 500


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@app.route('/api/admin/sessions', methods=['GET'])
@require_admin
def get_all_sessions():
    """Admin endpoint: Get all active, completed, and partial analyses"""
    from datetime import datetime

    # DIAGNOSTIC LOGGING (with module reload detection)
    logger.info("="*60)
    logger.info(f"ADMIN SESSIONS REQUEST | Module: {MODULE_LOAD_ID} | PID: {os.getpid()}")
    logger.info(f"Active analyses keys: {list(active_analyses.keys())}")
    logger.info(f"Completed analyses keys: {list(completed_analyses.keys())}")
    logger.info(f"Partial analyses keys: {list(partial_analyses.keys())}")
    logger.info(f"Legacy results keys: {list(analysis_results.keys())}")
    logger.info(f"Session timestamps keys: {list(session_timestamps.keys())}")
    logger.info("="*60)

    def format_session_info(session_id, session_data, status):
        """Helper to format session data for admin view"""
        try:
            info = {
                'session_id': session_id,
                'status': status,
                # Do not expose internal file paths; show filename and owner only
                'pdf_path': '[REDACTED]',
                'pdf_filename': session_data.get('pdf_filename', 'Unknown.pdf'),
                'owner': session_data.get('owner', None),
                'config_path': session_data.get('config_path', 'N/A'),
                'mode': session_data.get('mode', 'bid_spec'),  # Include analysis mode for export routing
            }

            # Add timestamp if available
            if 'completed_at' in session_data:
                info['completed_at'] = session_data['completed_at'].isoformat()
            if 'stopped_at' in session_data:
                info['stopped_at'] = session_data['stopped_at'].isoformat()
            if 'started_at' in session_data:
                info['started_at'] = session_data['started_at'].isoformat()

            # Add result statistics if available (with error handling)
            if 'result' in session_data:
                result = session_data['result']
                # Check if result has the expected attributes (it's a dataclass)
                info['questions_answered'] = getattr(result, 'questions_answered', 'N/A')
                info['total_pages'] = getattr(result, 'total_pages', 'N/A')
                info['total_tokens'] = getattr(result, 'total_tokens', 'N/A')
                info['processing_time'] = getattr(result, 'processing_time_seconds', 'N/A')

            return info
        except Exception as e:
            # Log the error but still return basic info
            logger.error(f"Error formatting session {session_id}: {e}", exc_info=True)
            return {
                'session_id': session_id,
                'status': f'error_{status}',
                'pdf_path': 'Error formatting',
                'config_path': 'Error formatting',
                'error': str(e)
            }

    # CRITICAL: Atomic snapshot of all session dicts with lock
    # Prevents race conditions where sessions appear/disappear during iteration
    with session_lock:
        # Touch all session timestamps to keep them alive when admin views them
        all_session_ids = (
            list(active_analyses.keys()) +
            list(completed_analyses.keys()) +
            list(partial_analyses.keys()) +
            list(analysis_results.keys())
        )
        for sid in all_session_ids:
            session_timestamps[sid] = datetime.now()

        # ENHANCED DIAGNOSTIC: Log what we see INSIDE the lock
        logger.info("🔍 INSIDE LOCK:")
        logger.info(f"🔍   Module ID: {MODULE_LOAD_ID} | PID: {os.getpid()} | Uptime: {time.time() - MODULE_LOAD_TIME:.1f}s")
        logger.info(f"🔍   Active keys: {list(active_analyses.keys())}")
        logger.info(f"🔍   Completed keys: {list(completed_analyses.keys())}")
        logger.info(f"🔍   Partial keys: {list(partial_analyses.keys())}")
        logger.info(f"🔍   Legacy keys: {list(analysis_results.keys())}")
        logger.info(f"🔍   Timestamps keys: {list(session_timestamps.keys())}")
        logger.info(f"🔍   Dict memory IDs - completed={id(completed_analyses)}, partial={id(partial_analyses)}")
        logger.info(f"🔍   Thread: {threading.current_thread().name}")
        logger.info(f"🔍   Total session IDs collected: {len(all_session_ids)}")

        # Gather all sessions (single atomic snapshot)
        sessions = {
            'active': [
                format_session_info(sid, data, 'active')
                for sid, data in active_analyses.items()
            ],
            'completed': [
                format_session_info(sid, data, 'completed')
                for sid, data in completed_analyses.items()
            ],
            'partial': [
                format_session_info(sid, data, 'partial')
                for sid, data in partial_analyses.items()
            ],
            'legacy': [
                format_session_info(sid, data, 'legacy_completed')
                for sid, data in analysis_results.items()
            ]
        }

    # Summary counts (can be done outside lock using snapshot)
    summary = {
        'total_sessions': sum(len(v) for v in sessions.values()),
        'active_count': len(sessions['active']),
        'completed_count': len(sessions['completed']),
        'partial_count': len(sessions['partial']),
        'legacy_count': len(sessions['legacy'])
    }

    # ENHANCED DIAGNOSTIC: Log what we're returning
    logger.info(f"📤 RETURNING: {summary}")
    logger.info(f"📤   Active sessions count: {len(sessions['active'])}")
    logger.info(f"📤   Completed sessions count: {len(sessions['completed'])}")
    logger.info(f"📤   Partial sessions count: {len(sessions['partial'])}")

    return jsonify({
        'success': True,
        'summary': summary,
        'sessions': sessions,
        'diagnostics': {
            'module_id': MODULE_LOAD_ID,
            'pid': os.getpid(),
            'module_uptime': round(time.time() - MODULE_LOAD_TIME, 2)
        }
    })


# ============================================================================
# CIPP ANALYZER FRONTEND
# ============================================================================

@app.route('/cipp-analyzer')
def cipp_analyzer():
    """Serve CIPP Analyzer application (REBUILT for HOTDOG AI)"""
    return send_from_directory(Config.BASE_DIR, 'analyzer_rebuild.html')

@app.route('/admin/sessions')
@require_admin
def admin_sessions():
    """Serve admin session monitoring page (requires admin role)"""
    return send_from_directory(Config.BASE_DIR, 'admin_sessions.html')

@app.route('/api/config/questions', methods=['GET'])
def get_question_config():
    """Load question configuration from JSON file"""
    try:
        config_path = Config.BASE_DIR / 'config' / 'cipp_questions_default.json'

        if not config_path.exists():
            return jsonify({
                'success': False,
                'error': 'Question configuration file not found'
            }), 404

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        # Transform to frontend format
        sections = config_data.get('sections', [])
        total_questions = sum(len(section.get('questions', [])) for section in sections)

        return jsonify({
            'success': True,
            'config': {
                'sections': sections,
                'totalQuestions': total_questions
            }
        })

    except Exception as e:
        logger.error(f'Failed to load question config: {str(e)}')
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/config/questions', methods=['PUT'])
def save_question_config():
    """Save entire question configuration to JSON file"""
    try:
        data = request.get_json()
        if not data or 'sections' not in data:
            return jsonify({'success': False, 'error': 'Invalid configuration data'}), 400

        config_path = Config.BASE_DIR / 'config' / 'cipp_questions_default.json'

        # Build config structure
        config_data = {
            "config_name": data.get('config_name', 'BidBrief Document Analysis'),
            "version": data.get('version', '1.0'),
            "description": data.get('description', 'Question configuration for document analysis'),
            "sections": data['sections']
        }

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        total_questions = sum(len(s.get('questions', [])) for s in data['sections'])
        logger.info(f'✅ Question config saved: {len(data["sections"])} sections, {total_questions} questions')

        return jsonify({
            'success': True,
            'message': f'Saved {len(data["sections"])} sections with {total_questions} questions'
        })

    except Exception as e:
        logger.error(f'Failed to save question config: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/questions/upload', methods=['POST'])
def upload_questions_from_spreadsheet():
    """Upload questions from CSV or Excel spreadsheet"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        filename = file.filename.lower()

        # Read spreadsheet based on format
        if filename.endswith('.csv'):
            import csv
            import io
            content = file.read().decode('utf-8-sig')  # Handle BOM
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
        elif filename.endswith(('.xlsx', '.xls')):
            import pandas as pd
            df = pd.read_excel(file)
            rows = df.to_dict('records')
        else:
            return jsonify({'success': False, 'error': 'Unsupported file format. Use CSV or Excel (.xlsx)'}), 400

        # Parse rows into sections and questions
        # Expected columns: section_id, section_name, question_id, question_text, required, expected_type
        sections_map = {}

        for row in rows:
            section_id = str(row.get('section_id', '')).strip()
            section_name = str(row.get('section_name', '')).strip()
            question_id = str(row.get('question_id', row.get('id', ''))).strip()
            question_text = str(row.get('question_text', row.get('text', ''))).strip()
            required = str(row.get('required', 'false')).lower() in ('true', '1', 'yes')
            expected_type = str(row.get('expected_type', 'string')).strip() or 'string'
            enabled = str(row.get('enabled', 'true')).lower() in ('true', '1', 'yes', '')

            if not section_id or not question_text:
                continue  # Skip invalid rows

            if section_id not in sections_map:
                sections_map[section_id] = {
                    'section_id': section_id,
                    'section_name': section_name or section_id,
                    'description': str(row.get('section_description', '')).strip(),
                    'questions': []
                }

            sections_map[section_id]['questions'].append({
                'id': question_id or f"Q{len(sections_map[section_id]['questions']) + 1}",
                'text': question_text,
                'required': required,
                'expected_type': expected_type,
                'enabled': enabled
            })

        sections = list(sections_map.values())
        total_questions = sum(len(s['questions']) for s in sections)

        logger.info(f'📤 Uploaded questions: {len(sections)} sections, {total_questions} questions from {file.filename}')

        return jsonify({
            'success': True,
            'config': {
                'sections': sections,
                'totalQuestions': total_questions
            },
            'message': f'Parsed {total_questions} questions in {len(sections)} sections'
        })

    except Exception as e:
        logger.error(f'Failed to parse question spreadsheet: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/questions/section/<section_id>', methods=['PUT'])
def update_section(section_id):
    """Update a specific section"""
    try:
        data = request.get_json()
        config_path = Config.BASE_DIR / 'config' / 'cipp_questions_default.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        # Find and update section
        for i, section in enumerate(config_data['sections']):
            if section['section_id'] == section_id:
                config_data['sections'][i] = {**section, **data}
                break
        else:
            return jsonify({'success': False, 'error': 'Section not found'}), 404

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        logger.info(f'✅ Updated section: {section_id}')
        return jsonify({'success': True, 'message': f'Section {section_id} updated'})

    except Exception as e:
        logger.error(f'Failed to update section: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/questions/section/<section_id>', methods=['DELETE'])
def delete_section(section_id):
    """Delete a section"""
    try:
        config_path = Config.BASE_DIR / 'config' / 'cipp_questions_default.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        original_count = len(config_data['sections'])
        config_data['sections'] = [s for s in config_data['sections'] if s['section_id'] != section_id]

        if len(config_data['sections']) == original_count:
            return jsonify({'success': False, 'error': 'Section not found'}), 404

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        logger.info(f'🗑️ Deleted section: {section_id}')
        return jsonify({'success': True, 'message': f'Section {section_id} deleted'})

    except Exception as e:
        logger.error(f'Failed to delete section: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/questions/question/<question_id>', methods=['PUT'])
def update_question(question_id):
    """Update a specific question"""
    try:
        data = request.get_json()
        config_path = Config.BASE_DIR / 'config' / 'cipp_questions_default.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        # Find and update question
        found = False
        for section in config_data['sections']:
            for i, question in enumerate(section['questions']):
                if question['id'] == question_id:
                    section['questions'][i] = {**question, **data}
                    found = True
                    break
            if found:
                break

        if not found:
            return jsonify({'success': False, 'error': 'Question not found'}), 404

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        logger.info(f'✅ Updated question: {question_id}')
        return jsonify({'success': True, 'message': f'Question {question_id} updated'})

    except Exception as e:
        logger.error(f'Failed to update question: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/questions/question/<question_id>', methods=['DELETE'])
def delete_question(question_id):
    """Delete a question"""
    try:
        config_path = Config.BASE_DIR / 'config' / 'cipp_questions_default.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        found = False
        for section in config_data['sections']:
            original_count = len(section['questions'])
            section['questions'] = [q for q in section['questions'] if q['id'] != question_id]
            if len(section['questions']) < original_count:
                found = True
                break

        if not found:
            return jsonify({'success': False, 'error': 'Question not found'}), 404

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        logger.info(f'🗑️ Deleted question: {question_id}')
        return jsonify({'success': True, 'message': f'Question {question_id} deleted'})

    except Exception as e:
        logger.error(f'Failed to delete question: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/questions/question/<question_id>/toggle', methods=['POST'])
def toggle_question(question_id):
    """Toggle a question's enabled status"""
    try:
        config_path = Config.BASE_DIR / 'config' / 'cipp_questions_default.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        found = False
        new_status = None
        for section in config_data['sections']:
            for question in section['questions']:
                if question['id'] == question_id:
                    # Toggle enabled status (default to True if not set)
                    current = question.get('enabled', True)
                    question['enabled'] = not current
                    new_status = question['enabled']
                    found = True
                    break
            if found:
                break

        if not found:
            return jsonify({'success': False, 'error': 'Question not found'}), 404

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        logger.info(f'🔄 Toggled question {question_id}: enabled={new_status}')
        return jsonify({'success': True, 'enabled': new_status, 'message': f'Question {question_id} {"enabled" if new_status else "disabled"}'})

    except Exception as e:
        logger.error(f'Failed to toggle question: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/questions/section', methods=['POST'])
def add_section():
    """Add a new section"""
    try:
        data = request.get_json()
        if not data.get('section_id') or not data.get('section_name'):
            return jsonify({'success': False, 'error': 'section_id and section_name are required'}), 400

        config_path = Config.BASE_DIR / 'config' / 'cipp_questions_default.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        # Check if section_id already exists
        if any(s['section_id'] == data['section_id'] for s in config_data['sections']):
            return jsonify({'success': False, 'error': 'Section ID already exists'}), 400

        new_section = {
            'section_id': data['section_id'],
            'section_name': data['section_name'],
            'description': data.get('description', ''),
            'questions': data.get('questions', [])
        }

        config_data['sections'].append(new_section)

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        logger.info(f'➕ Added section: {data["section_id"]}')
        return jsonify({'success': True, 'message': f'Section {data["section_id"]} added'})

    except Exception as e:
        logger.error(f'Failed to add section: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/questions/question', methods=['POST'])
def add_question():
    """Add a new question to a section"""
    try:
        data = request.get_json()
        section_id = data.get('section_id')
        if not section_id or not data.get('text'):
            return jsonify({'success': False, 'error': 'section_id and text are required'}), 400

        config_path = Config.BASE_DIR / 'config' / 'cipp_questions_default.json'

        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)

        # Find section
        found = False
        for section in config_data['sections']:
            if section['section_id'] == section_id:
                # Generate ID if not provided
                question_id = data.get('id')
                if not question_id:
                    existing_ids = [q['id'] for q in section['questions']]
                    max_num = 0
                    for eid in existing_ids:
                        if eid.startswith('Q'):
                            try:
                                max_num = max(max_num, int(eid[1:]))
                            except ValueError:
                                pass
                    question_id = f'Q{max_num + 1}'

                new_question = {
                    'id': question_id,
                    'text': data['text'],
                    'required': data.get('required', False),
                    'expected_type': data.get('expected_type', 'string'),
                    'enabled': data.get('enabled', True)
                }

                section['questions'].append(new_question)
                found = True
                break

        if not found:
            return jsonify({'success': False, 'error': 'Section not found'}), 404

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        logger.info(f'➕ Added question {question_id} to section {section_id}')
        return jsonify({'success': True, 'question_id': question_id, 'message': f'Question added to {section_id}'})

    except Exception as e:
        logger.error(f'Failed to add question: {str(e)}')
        return jsonify({'success': False, 'error': str(e)}), 500


def _extract_doc_context(pdf_path: str, max_chars: int = 4000) -> str:
    """
    Lightly extract context from a PDF for question generation guidance.
    Pulls title page, first few pages, and scans for TOC / glossary / appendix pages.
    Returns a compact text summary (capped at max_chars).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                pages_text = []
                total = len(pdf.pages)
                # First 4 pages + last 3 pages
                indices = list(range(min(4, total))) + list(range(max(0, total - 3), total))
                seen = set()
                for i in indices:
                    if i in seen:
                        continue
                    seen.add(i)
                    t = pdf.pages[i].extract_text() or ''
                    if t.strip():
                        pages_text.append(f"[Page {i+1}]\n{t.strip()}")
                raw = '\n\n'.join(pages_text)
                return raw[:max_chars]
        except Exception:
            return ''

    try:
        doc = fitz.open(pdf_path)
        total = doc.page_count
        context_pages = []

        # Always grab first 4 pages (title, intro, TOC)
        for i in range(min(4, total)):
            context_pages.append(i)

        # Scan up to first 20 pages for TOC / table of contents keywords
        toc_keywords = {'table of contents', 'contents', 'index', 'toc'}
        for i in range(min(20, total)):
            if i in context_pages:
                continue
            page_text_lower = doc[i].get_text('text').lower()
            if any(kw in page_text_lower for kw in toc_keywords):
                context_pages.append(i)
                if len(context_pages) >= 8:
                    break

        # Scan last 15 pages for glossary / appendix
        gloss_keywords = {'glossary', 'appendix', 'definitions', 'abbreviations'}
        for i in range(max(0, total - 15), total):
            if i in context_pages:
                continue
            page_text_lower = doc[i].get_text('text').lower()
            if any(kw in page_text_lower for kw in gloss_keywords):
                context_pages.append(i)
                if len(context_pages) >= 12:
                    break

        parts = []
        for i in sorted(set(context_pages)):
            t = doc[i].get_text('text').strip()
            if t:
                parts.append(f"[Page {i+1}]\n{t}")

        doc.close()
        raw = '\n\n'.join(parts)
        return raw[:max_chars]
    except Exception as e:
        logger.warning(f'Doc context extraction failed: {e}')
        return ''


@app.route('/api/config/questions/generate', methods=['POST'])
@require_auth
def generate_question_set():
    """
    AI Question Set Generator — Phase 1 (Initial).
    Accepts JSON (no file) or multipart/form-data (with optional PDF for context).
    Takes free-text user input (questions + context) and generates a structured
    question set JSON preserving every user-supplied question verbatim.
    """
    import requests as http_requests

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return jsonify({'success': False, 'error': 'OpenAI API key not configured'}), 500

    # Support both JSON and multipart/form-data
    if request.content_type and 'multipart' in request.content_type:
        user_input = request.form.get('user_input', '').strip()
        uploaded_file = request.files.get('file')
    else:
        data = request.get_json() or {}
        user_input = data.get('user_input', '').strip()
        uploaded_file = None

    if not user_input:
        return jsonify({'success': False, 'error': 'user_input is required'}), 400

    # Extract document context if a file was provided
    doc_context = ''
    doc_context_note = ''
    if uploaded_file:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                uploaded_file.save(tmp.name)
                tmp_path = tmp.name
            doc_context = _extract_doc_context(tmp_path)
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            if doc_context:
                doc_context_note = (
                    "\n\nDOCUMENT CONTEXT (extracted from title page, TOC, glossary, appendix):\n"
                    "Use this to better understand the document's domain and infer appropriate question sections "
                    "and terminology. Do NOT generate questions about the document structure itself — "
                    "use it only to inform relevance and domain language.\n\n"
                    f"{doc_context}"
                )
                logger.info(f'🗂️ Doc context extracted: {len(doc_context)} chars for question generation')
        except Exception as e:
            logger.warning(f'Could not extract doc context: {e}')

    system_prompt = (
        "You are a master expert question architect and specialist in creating structured question sets "
        "for BidBrief, an AI document analysis platform. Your job is to take a user's free-text input "
        "(which may contain specific questions, contextual descriptions, or both) and produce a clean "
        "JSON question set for document analysis.\n\n"
        "RULES:\n"
        "1. Preserve EVERY specific question the user wrote, word-for-word, without abridging or paraphrasing.\n"
        "2. Infer the domain/purpose from the user's context (and document context if provided) and organize "
        "questions into logical sections.\n"
        "3. Generate question IDs as Q1, Q2, Q3... sequentially across all sections.\n"
        "4. Each section needs: section_id (snake_case), section_name (human-readable), section_description.\n"
        "5. Each question needs: id, text, required (true/false), expected_type (string/number/date/technical_spec), enabled (true).\n"
        "6. Return ONLY valid JSON — no markdown fences, no commentary, nothing else.\n\n"
        "Output format:\n"
        '{"sections": [{"section_id": "...", "section_name": "...", "section_description": "...", '
        '"questions": [{"id": "Q1", "text": "...", "required": true, "expected_type": "string", "enabled": true}]}]}'
        + doc_context_note
    )

    try:
        resp = http_requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': 'gpt-4o',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_input}
                ],
                'temperature': 0.3,
                'max_tokens': 4000
            },
            timeout=60
        )
        resp.raise_for_status()
        raw = resp.json()['choices'][0]['message']['content'].strip()

        # Strip markdown fences if present
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]

        parsed = json.loads(raw)
        sections = parsed.get('sections', [])
        total_questions = sum(len(s.get('questions', [])) for s in sections)

        logger.info(f'🤖 AI generated question set: {len(sections)} sections, {total_questions} questions')
        return jsonify({
            'success': True,
            'config': {
                'sections': sections,
                'totalQuestions': total_questions,
                'version': '1.0'
            }
        })

    except json.JSONDecodeError as e:
        logger.error(f'AI question generation: JSON parse error: {e}')
        return jsonify({'success': False, 'error': 'AI returned invalid JSON. Please try again or rephrase your input.'}), 500
    except Exception as e:
        logger.error(f'AI question generation failed: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/config/questions/generate-additional', methods=['POST'])
@require_auth
def generate_additional_questions():
    """
    AI Question Set Generator — Phase 2 (Additional suggestions).
    Given the user's original context and existing sections, generates up to
    3 additional sections with up to 10 questions each.
    """
    import requests as http_requests

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        return jsonify({'success': False, 'error': 'OpenAI API key not configured'}), 500

    data = request.get_json()
    user_input = (data or {}).get('user_input', '').strip()
    existing_sections = (data or {}).get('existing_sections', [])

    if not user_input:
        return jsonify({'success': False, 'error': 'user_input is required'}), 400

    existing_summary = ', '.join(s.get('section_name', '') for s in existing_sections) if existing_sections else 'none'
    existing_q_texts = [q.get('text', '') for s in existing_sections for q in s.get('questions', [])]

    # Find the highest existing question number for sequential IDs
    max_q_num = 0
    for s in existing_sections:
        for q in s.get('questions', []):
            qid = q.get('id', '')
            if qid.startswith('Q'):
                try:
                    max_q_num = max(max_q_num, int(qid[1:]))
                except ValueError:
                    pass

    system_prompt = (
        "You are a master expert question architect specializing in document analysis question sets. "
        "The user already has a question set based on their input. Your job is to suggest ADDITIONAL "
        "valuable questions that complement what they already have.\n\n"
        "RULES:\n"
        "1. Create UP TO 3 new sections with UP TO 10 questions each.\n"
        "2. Do NOT repeat any questions that already exist in the set.\n"
        "3. Questions must be directly relevant and useful for the user's domain/context.\n"
        "4. Start question IDs from Q{next_id} (continue the existing sequence).\n"
        "5. Return ONLY valid JSON — no markdown fences, no commentary.\n\n"
        f"Existing sections already covered: {existing_summary}\n"
        f"Start new question IDs from Q{max_q_num + 1}.\n\n"
        "Output format:\n"
        '{"additional_sections": [{"section_id": "...", "section_name": "...", "section_description": "...", '
        '"questions": [{"id": "Q...", "text": "...", "required": false, "expected_type": "string", "enabled": true}]}]}'
    )

    try:
        resp = http_requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': 'gpt-4o',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': f"Original context:\n{user_input}\n\nAlready have these questions:\n" + '\n'.join(f'- {q}' for q in existing_q_texts)}
                ],
                'temperature': 0.5,
                'max_tokens': 3000
            },
            timeout=60
        )
        resp.raise_for_status()
        raw = resp.json()['choices'][0]['message']['content'].strip()

        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'):
                raw = raw[4:]

        parsed = json.loads(raw)
        additional = parsed.get('additional_sections', [])

        logger.info(f'🤖 AI generated {len(additional)} additional sections')
        return jsonify({'success': True, 'additional_sections': additional})

    except json.JSONDecodeError as e:
        logger.error(f'AI additional generation: JSON parse error: {e}')
        return jsonify({'success': False, 'error': 'AI returned invalid JSON. Please try again.'}), 500
    except Exception as e:
        logger.error(f'AI additional generation failed: {e}')
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/progress-estimator')
def progress_estimator():
    """Serve CIPP Production Estimator (Comprehensive - All Penalties/Boosts/Pipe Sizes)"""
    return send_from_directory(Config.BASE_DIR / 'legacy' / 'apps' / 'progress-estimator', 'CIPPEstimator_Comprehensive.html')


# ============================================================================
# OPENAI API PROXY (for Progress Estimator AI Insights)
# ============================================================================

@app.route('/api/openai/chat', methods=['POST'])
def openai_chat_proxy():
    """
    Proxy endpoint for OpenAI API calls
    Securely uses server-side OPENAI_API_KEY from environment
    """
    import requests

    # Get API key from environment
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        logger.error("OPENAI_API_KEY not configured in environment")
        return jsonify({
            'success': False,
            'error': 'OpenAI API key not configured on server. Contact administrator.'
        }), 500

    try:
        # Get request data from frontend
        data = request.get_json()

        # Validate required fields
        if 'messages' not in data:
            return jsonify({
                'success': False,
                'error': 'Missing required field: messages'
            }), 400

        # Prepare OpenAI API request
        openai_request = {
            'model': data.get('model', 'gpt-4'),
            'messages': data['messages'],
            'temperature': data.get('temperature', 0.7),
            'max_tokens': data.get('max_tokens', 600)
        }

        logger.info(f"Proxying OpenAI request: model={openai_request['model']}, messages={len(openai_request['messages'])}")

        # Call OpenAI API
        response = requests.post(
            'https://api.openai.com/v1/chat/completions',
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            },
            json=openai_request,
            timeout=30
        )

        # Check response status
        if response.status_code != 200:
            logger.error(f"OpenAI API error: {response.status_code} - {response.text}")
            return jsonify({
                'success': False,
                'error': f'OpenAI API returned {response.status_code}',
                'details': response.text
            }), response.status_code

        # Return successful response
        result = response.json()
        logger.info(f"OpenAI response received: {result['choices'][0]['finish_reason']}")

        return jsonify({
            'success': True,
            'data': result
        })

    except requests.exceptions.Timeout:
        logger.error("OpenAI API request timed out")
        return jsonify({
            'success': False,
            'error': 'Request timed out. Please try again.'
        }), 504

    except requests.exceptions.RequestException as e:
        logger.error(f"OpenAI API request failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to connect to OpenAI API',
            'details': str(e)
        }), 503

    except Exception as e:
        logger.error(f"Unexpected error in OpenAI proxy: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Internal server error',
            'details': str(e)
        }), 500


# ============================================================================
# VISUAL PROJECT SUMMARY (DASH APP INTEGRATION)
# ============================================================================

# Import and initialize Dash app
try:
    from services.cipp_dashboard.dash_app import create_dash_app
    dash_app = create_dash_app(app)
    logger.info("Visual Project Summary (Dash) integrated successfully")
except ImportError as e:
    logger.warning(f"Visual Project Summary not available: {e}")
    dash_app = None


# ===============================================================================
# CITYSCRAPER API ENDPOINTS (ADMIN-ONLY)
# ===============================================================================

def _check_scraper_admin():
    """
    Check if current request has admin access for CityScraper endpoints.
    Returns (user_data, None) on success, or (None, error_response) on failure.
    """
    auth_header = request.headers.get('Authorization', '')

    # Try Bearer token first (API calls)
    if auth_header.startswith('Bearer '):
        session_token = auth_header.split(' ')[1]
        if session_token not in active_sessions:
            return None, (jsonify({'error': 'Invalid session'}), 401)
        user_data = active_sessions[session_token]
        if user_data.get('role') != 'admin':
            return None, (jsonify({'error': 'Admin access required'}), 403)
        return user_data, None

    # Try cookie auth (browser requests)
    session = check_auth_cookie()
    if not session:
        return None, (jsonify({'error': 'Authentication required'}), 401)
    if session.get('role') != 'admin':
        return None, (jsonify({'error': 'Admin access required'}), 403)
    return session, None


def _check_scraper_available():
    """Check if CityScraper modules are available."""
    if not CITYSCRAPER_AVAILABLE:
        return jsonify({
            'error': 'CityScraper not available',
            'details': 'Required modules not installed'
        }), 503
    return None


@app.route('/api/scraper/admin-check', methods=['GET'])
def scraper_admin_check():
    """Check if current user has admin access for CityScraper features."""
    user_data, error = _check_scraper_admin()
    if error:
        # Return false instead of error for permission check
        return jsonify({
            'success': True,
            'is_admin': False,
            'scraper_available': CITYSCRAPER_AVAILABLE
        })

    return jsonify({
        'success': True,
        'is_admin': True,
        'username': user_data.get('username', 'unknown'),
        'scraper_available': CITYSCRAPER_AVAILABLE
    })


# ---------------------------------------------------------------------------
# STANDALONE RESEARCH ENDPOINTS
# ---------------------------------------------------------------------------

@app.route('/api/scraper/research', methods=['POST'])
def start_scraper_research():
    """
    Start a standalone municipal research session.

    Request body:
    {
        "municipality": "City of Example",
        "table_mode": true/false  (optional, default false)
    }
    """
    user_data, error = _check_scraper_admin()
    if error:
        return error

    unavailable = _check_scraper_available()
    if unavailable:
        return unavailable

    try:
        data = request.get_json() or {}
        municipality = data.get('municipality', '').strip()
        table_mode = data.get('table_mode', False)

        if not municipality:
            return jsonify({'error': 'Municipality name is required'}), 400

        # Generate session ID
        session_id = f"scraper_{secrets.token_hex(8)}"

        logger.info(f"Starting CityScraper research: {session_id} for '{municipality}'")

        # Initialize session state
        with session_lock:
            cityscraper_sessions[session_id] = {
                'orchestrator': None,
                'status': 'initializing',
                'municipality': municipality,
                'table_mode': table_mode,
                'started_at': datetime.now().isoformat(),
                'user': user_data.get('username', 'unknown')
            }
            cityscraper_events[session_id] = []
            cityscraper_results[session_id] = None

        def run_research():
            """Background thread for research execution."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Event callback to capture agent activity
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
                            # Pass through data_update for live table
                            if hasattr(event, 'data_update') and event.data_update is not None:
                                event_data['data_update'] = event.data_update
                            cityscraper_events[session_id].append(event_data)

                # Create orchestrator with event callback
                orchestrator = StandaloneResearchOrchestrator(
                    event_callback=on_event
                )

                with session_lock:
                    if session_id in cityscraper_sessions:
                        cityscraper_sessions[session_id]['orchestrator'] = orchestrator
                        cityscraper_sessions[session_id]['status'] = 'running'

                # Run the research with municipality and table_mode
                result = loop.run_until_complete(orchestrator.run(
                    municipality_input=municipality,
                    table_mode=table_mode,
                    session_id=session_id
                ))

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

            except Exception as e:
                logger.error(f"CityScraper research failed: {session_id} - {e}", exc_info=True)
                with session_lock:
                    if session_id in cityscraper_sessions:
                        cityscraper_sessions[session_id]['status'] = 'failed'
                        cityscraper_sessions[session_id]['error'] = str(e)
            finally:
                loop.close()

        # Start background thread
        thread = threading.Thread(target=run_research, daemon=True)
        thread.start()

        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': f'Research started for {municipality}'
        })

    except Exception as e:
        logger.error(f"Failed to start CityScraper research: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/scraper/research/<session_id>', methods=['GET'])
def get_scraper_research(session_id):
    """Get status and results of a research session.

    Auth: Uses session_id as authentication - the session_id is a cryptographically
    random string only returned to the authenticated user who started the research.
    """
    with session_lock:
        # Session ID itself serves as auth - it's secret and only known to the user who started research
        if session_id not in cityscraper_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session_data = cityscraper_sessions[session_id].copy()
        result = cityscraper_results.get(session_id)

    # Don't include orchestrator object in response
    session_data.pop('orchestrator', None)

    return jsonify({
        'success': True,
        'session': session_data,
        'result': result
    })


@app.route('/api/scraper/events/<session_id>', methods=['GET'])
def get_scraper_events(session_id):
    """Get agent activity events for a session (for UI display).

    Auth: Uses session_id as authentication - the session_id is a cryptographically
    random string only returned to the authenticated user who started the research.
    This avoids cookie-based auth issues with multi-worker deployments.
    """
    # Optional: get events since a specific index
    since_index = request.args.get('since', 0, type=int)

    with session_lock:
        # Session ID itself serves as auth - it's secret and only known to the user who started research
        if session_id not in cityscraper_events:
            return jsonify({'error': 'Session not found'}), 404

        events = cityscraper_events[session_id][since_index:]
        total_events = len(cityscraper_events[session_id])
        session_data = cityscraper_sessions.get(session_id, {})
        status = session_data.get('status', 'unknown')
        error = session_data.get('error')

    response = {
        'success': True,
        'events': events,
        'total_events': total_events,
        'status': status
    }
    # Include error message when research has failed so frontend can display it
    if error:
        response['error'] = error

    return jsonify(response)


@app.route('/api/scraper/stop/<session_id>', methods=['POST'])
def stop_scraper_research(session_id):
    """Cancel an in-progress research session.

    Auth: Uses session_id as authentication - only the user who started the research knows it.
    """
    with session_lock:
        # Session ID itself serves as auth
        if session_id not in cityscraper_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session_data = cityscraper_sessions[session_id]

        if session_data['status'] not in ('initializing', 'running'):
            return jsonify({
                'success': False,
                'message': f"Cannot stop session with status: {session_data['status']}"
            })

        orchestrator = session_data.get('orchestrator')
        if orchestrator and hasattr(orchestrator, 'cancel'):
            orchestrator.cancel()

        session_data['status'] = 'cancelled'

    logger.info(f"CityScraper research cancelled: {session_id}")

    return jsonify({
        'success': True,
        'message': 'Research session cancelled'
    })


# ---------------------------------------------------------------------------
# DOCUMENT ENRICHMENT ENDPOINTS
# ---------------------------------------------------------------------------

@app.route('/api/scraper/enrich/<hotdog_session>', methods=['POST'])
def enrich_hotdog_session(hotdog_session):
    """
    Enrich a completed HOTDOG analysis with municipal data.

    Request body (optional):
    {
        "municipality": "City of Example"  (auto-detected if not provided)
    }
    """
    user_data, error = _check_scraper_admin()
    if error:
        return error

    unavailable = _check_scraper_available()
    if unavailable:
        return unavailable

    try:
        # Get the completed HOTDOG session
        with session_lock:
            if hotdog_session not in completed_analyses:
                return jsonify({'error': 'HOTDOG session not found or not completed'}), 404

            hotdog_data = completed_analyses[hotdog_session]

        data = request.get_json() or {}
        municipality = data.get('municipality', '').strip()

        # Try to auto-detect municipality from HOTDOG results if not provided
        if not municipality:
            # Look for municipality in the analysis results
            result = hotdog_data.get('result', {})
            # This would need to be extracted from the document analysis
            municipality = result.get('detected_municipality', 'Unknown Municipality')

        # Generate enrichment session ID
        session_id = f"enrich_{secrets.token_hex(8)}"

        logger.info(f"Starting document enrichment: {session_id} for HOTDOG session {hotdog_session}")

        # Initialize session state
        with session_lock:
            cityscraper_sessions[session_id] = {
                'orchestrator': None,
                'status': 'initializing',
                'type': 'enrichment',
                'hotdog_session': hotdog_session,
                'municipality': municipality,
                'started_at': datetime.now().isoformat(),
                'user': user_data.get('username', 'unknown')
            }
            cityscraper_events[session_id] = []
            cityscraper_results[session_id] = None

        def run_enrichment():
            """Background thread for enrichment execution."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                orchestrator = DocumentEnrichmentOrchestrator(
                    hotdog_session_id=hotdog_session,
                    hotdog_data=hotdog_data,
                    municipality=municipality
                )

                with session_lock:
                    if session_id in cityscraper_sessions:
                        cityscraper_sessions[session_id]['orchestrator'] = orchestrator
                        cityscraper_sessions[session_id]['status'] = 'running'

                def on_event(event):
                    with session_lock:
                        if session_id in cityscraper_events:
                            cityscraper_events[session_id].append({
                                'agent': getattr(event, 'agent_name', 'unknown'),
                                'action': getattr(event, 'action', 'unknown'),
                                'message': getattr(event, 'message', ''),
                                'timestamp': datetime.now().isoformat()
                            })

                result = loop.run_until_complete(orchestrator.run(on_event=on_event))

                with session_lock:
                    if session_id in cityscraper_sessions:
                        cityscraper_sessions[session_id]['status'] = 'completed'
                        cityscraper_results[session_id] = result

                logger.info(f"Document enrichment completed: {session_id}")

            except Exception as e:
                logger.error(f"Document enrichment failed: {session_id} - {e}", exc_info=True)
                with session_lock:
                    if session_id in cityscraper_sessions:
                        cityscraper_sessions[session_id]['status'] = 'failed'
                        cityscraper_sessions[session_id]['error'] = str(e)
            finally:
                loop.close()

        thread = threading.Thread(target=run_enrichment, daemon=True)
        thread.start()

        return jsonify({
            'success': True,
            'session_id': session_id,
            'hotdog_session': hotdog_session,
            'message': f'Enrichment started for {municipality}'
        })

    except Exception as e:
        logger.error(f"Failed to start document enrichment: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# COMPARATIVE INTELLIGENCE ENDPOINTS
# ---------------------------------------------------------------------------

@app.route('/api/scraper/compare', methods=['POST'])
def compare_municipalities():
    """
    Start a comparative analysis of multiple municipalities.

    Request body:
    {
        "municipalities": ["City A", "City B", "City C"],
        "focus_areas": ["budgets", "contracts"]  (optional)
    }
    """
    user_data, error = _check_scraper_admin()
    if error:
        return error

    unavailable = _check_scraper_available()
    if unavailable:
        return unavailable

    try:
        data = request.get_json() or {}
        municipalities = data.get('municipalities', [])
        focus_areas = data.get('focus_areas', [])

        if not municipalities or len(municipalities) < 2:
            return jsonify({'error': 'At least 2 municipalities required for comparison'}), 400

        session_id = f"compare_{secrets.token_hex(8)}"

        logger.info(f"Starting comparative analysis: {session_id} for {len(municipalities)} municipalities")

        with session_lock:
            cityscraper_sessions[session_id] = {
                'orchestrator': None,
                'status': 'initializing',
                'type': 'comparison',
                'municipalities': municipalities,
                'focus_areas': focus_areas,
                'started_at': datetime.now().isoformat(),
                'user': user_data.get('username', 'unknown')
            }
            cityscraper_events[session_id] = []
            cityscraper_results[session_id] = None

        def run_comparison():
            """Background thread for comparison execution."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                orchestrator = ComparativeIntelligenceOrchestrator(
                    municipalities=municipalities,
                    focus_areas=focus_areas
                )

                with session_lock:
                    if session_id in cityscraper_sessions:
                        cityscraper_sessions[session_id]['orchestrator'] = orchestrator
                        cityscraper_sessions[session_id]['status'] = 'running'

                def on_event(event):
                    with session_lock:
                        if session_id in cityscraper_events:
                            cityscraper_events[session_id].append({
                                'agent': getattr(event, 'agent_name', 'unknown'),
                                'action': getattr(event, 'action', 'unknown'),
                                'message': getattr(event, 'message', ''),
                                'timestamp': datetime.now().isoformat()
                            })

                result = loop.run_until_complete(orchestrator.run(on_event=on_event))

                with session_lock:
                    if session_id in cityscraper_sessions:
                        cityscraper_sessions[session_id]['status'] = 'completed'
                        cityscraper_results[session_id] = result

                logger.info(f"Comparative analysis completed: {session_id}")

            except Exception as e:
                logger.error(f"Comparative analysis failed: {session_id} - {e}", exc_info=True)
                with session_lock:
                    if session_id in cityscraper_sessions:
                        cityscraper_sessions[session_id]['status'] = 'failed'
                        cityscraper_sessions[session_id]['error'] = str(e)
            finally:
                loop.close()

        thread = threading.Thread(target=run_comparison, daemon=True)
        thread.start()

        return jsonify({
            'success': True,
            'session_id': session_id,
            'municipalities': municipalities,
            'message': f'Comparison started for {len(municipalities)} municipalities'
        })

    except Exception as e:
        logger.error(f"Failed to start comparative analysis: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# ANALYSIS AGENT ENDPOINTS
# ---------------------------------------------------------------------------

@app.route('/api/scraper/analyze/summary', methods=['POST'])
def analyze_summary():
    """
    Generate a summary using the SummaryGeneratorAgent.

    Request body:
    {
        "data": {...},  // Data to summarize
        "context": "..."  // Optional context
    }
    """
    user_data, error = _check_scraper_admin()
    if error:
        return error

    unavailable = _check_scraper_available()
    if unavailable:
        return unavailable

    try:
        data = request.get_json() or {}
        input_data = data.get('data', {})
        context = data.get('context', '')

        if not input_data:
            return jsonify({'error': 'Data is required'}), 400

        # Run synchronously (these are quick operations)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            agent = SummaryGeneratorAgent()
            agent_request = AgentRequest(
                data=input_data,
                context=context
            )
            result = loop.run_until_complete(agent.run(agent_request))

            return jsonify({
                'success': True,
                'summary': result
            })
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Summary generation failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/scraper/analyze/brainstorm', methods=['POST'])
def analyze_brainstorm():
    """
    Generate brainstorming ideas using the BrainstormerAgent.

    Request body:
    {
        "topic": "...",
        "data": {...},  // Optional supporting data
        "context": "..."  // Optional context
    }
    """
    user_data, error = _check_scraper_admin()
    if error:
        return error

    unavailable = _check_scraper_available()
    if unavailable:
        return unavailable

    try:
        data = request.get_json() or {}
        topic = data.get('topic', '').strip()
        input_data = data.get('data', {})
        context = data.get('context', '')

        if not topic:
            return jsonify({'error': 'Topic is required'}), 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            agent = BrainstormerAgent()
            agent_request = AgentRequest(
                topic=topic,
                data=input_data,
                context=context
            )
            result = loop.run_until_complete(agent.run(agent_request))

            return jsonify({
                'success': True,
                'ideas': result
            })
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Brainstorming failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/scraper/analyze/research', methods=['POST'])
def analyze_research():
    """
    Perform deep research using the DeepResearcherAgent.

    Request body:
    {
        "query": "...",
        "data": {...},  // Optional supporting data
        "context": "..."  // Optional context
    }
    """
    user_data, error = _check_scraper_admin()
    if error:
        return error

    unavailable = _check_scraper_available()
    if unavailable:
        return unavailable

    try:
        data = request.get_json() or {}
        query = data.get('query', '').strip()
        input_data = data.get('data', {})
        context = data.get('context', '')

        if not query:
            return jsonify({'error': 'Query is required'}), 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            agent = DeepResearcherAgent()
            agent_request = AgentRequest(
                query=query,
                data=input_data,
                context=context
            )
            result = loop.run_until_complete(agent.run(agent_request))

            return jsonify({
                'success': True,
                'research': result
            })
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Deep research failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/api/scraper/analyze/bid', methods=['POST'])
def analyze_bid():
    """
    Analyze bid data using the BidAnalyzerAgent.

    Request body:
    {
        "bid_data": {...},  // Bid/RFP data to analyze
        "context": "..."  // Optional context
    }
    """
    user_data, error = _check_scraper_admin()
    if error:
        return error

    unavailable = _check_scraper_available()
    if unavailable:
        return unavailable

    try:
        data = request.get_json() or {}
        bid_data = data.get('bid_data', {})
        context = data.get('context', '')

        if not bid_data:
            return jsonify({'error': 'Bid data is required'}), 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            agent = BidAnalyzerAgent()
            agent_request = AgentRequest(
                data=bid_data,
                context=context
            )
            result = loop.run_until_complete(agent.run(agent_request))

            return jsonify({
                'success': True,
                'analysis': result
            })
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Bid analysis failed: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# CITYSCRAPER SESSION MANAGEMENT
# ---------------------------------------------------------------------------

@app.route('/api/scraper/sessions', methods=['GET'])
def list_scraper_sessions():
    """List all CityScraper sessions (admin only)."""
    user_data, error = _check_scraper_admin()
    if error:
        return error

    with session_lock:
        sessions = []
        for session_id, session_data in cityscraper_sessions.items():
            session_info = {
                'session_id': session_id,
                'status': session_data.get('status'),
                'type': session_data.get('type', 'research'),
                'municipality': session_data.get('municipality'),
                'municipalities': session_data.get('municipalities'),
                'started_at': session_data.get('started_at'),
                'user': session_data.get('user'),
                'error': session_data.get('error')
            }
            sessions.append(session_info)

    return jsonify({
        'success': True,
        'sessions': sessions,
        'total': len(sessions)
    })


@app.route('/api/scraper/sessions/<session_id>', methods=['DELETE'])
def delete_scraper_session(session_id):
    """Delete a CityScraper session (admin only)."""
    user_data, error = _check_scraper_admin()
    if error:
        return error

    with session_lock:
        if session_id not in cityscraper_sessions:
            return jsonify({'error': 'Session not found'}), 404

        # Cancel if running
        session_data = cityscraper_sessions[session_id]
        if session_data['status'] in ('initializing', 'running'):
            orchestrator = session_data.get('orchestrator')
            if orchestrator and hasattr(orchestrator, 'cancel'):
                orchestrator.cancel()

        # Clean up
        del cityscraper_sessions[session_id]
        cityscraper_events.pop(session_id, None)
        cityscraper_results.pop(session_id, None)

    logger.info(f"CityScraper session deleted: {session_id}")

    return jsonify({
        'success': True,
        'message': 'Session deleted'
    })


@app.route('/api/scraper/export/excel/<session_id>', methods=['GET'])
def export_scraper_excel(session_id):
    """Export CityScraper results as Excel workbook.

    Auth: Uses session_id as authentication.
    """
    unavailable = _check_scraper_available()
    if unavailable:
        return unavailable

    with session_lock:
        # Session ID itself serves as auth
        if session_id not in cityscraper_results:
            return jsonify({'error': 'Session not found or not completed'}), 404

        result = cityscraper_results[session_id]

    # Check if we have extraction data
    extraction_result = result.get('extraction_result') or result.get('presentation_result', {}).get('extraction_data')
    if not extraction_result:
        return jsonify({'error': 'No extraction data available for export'}), 400

    # Get municipality info
    municipality = result.get('municipality', {})

    try:
        # Use ExcelGeneratorAgent
        from services.scraper.agents.presentation import ExcelGeneratorAgent
        from services.scraper.models import AgentRequest

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            agent = ExcelGeneratorAgent()
            request = AgentRequest(
                agent_id="pr-2",
                task=f"export-excel-{session_id}",
                input_data={
                    'extraction_result': extraction_result,
                    'municipality': municipality,
                    'output_dir': 'exports'
                }
            )

            response = loop.run_until_complete(agent.process(request))

            if not response.success:
                return jsonify({
                    'success': False,
                    'error': 'Excel generation failed',
                    'details': response.errors
                }), 500

            file_path = response.output_data.get('file_path')
            if not file_path or not os.path.exists(file_path):
                return jsonify({'error': 'Generated file not found'}), 500

            # Send file
            return send_file(
                file_path,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=os.path.basename(file_path)
            )
        finally:
            loop.close()

    except Exception as e:
        logger.exception(f"Excel export error: {e}")
        return jsonify({
            'success': False,
            'error': 'Excel export failed',
            'details': str(e)
        }), 500


@app.route('/api/scraper/export/markdown/<session_id>', methods=['GET'])
def export_scraper_markdown(session_id):
    """Export CityScraper results as Markdown tables.

    Auth: Uses session_id as authentication.
    """
    unavailable = _check_scraper_available()
    if unavailable:
        return unavailable

    with session_lock:
        # Session ID itself serves as auth
        if session_id not in cityscraper_results:
            return jsonify({'error': 'Session not found or not completed'}), 404

        result = cityscraper_results[session_id]

    # Check if we have extraction data
    extraction_result = result.get('extraction_result') or result.get('presentation_result', {}).get('extraction_data')
    if not extraction_result:
        return jsonify({'error': 'No extraction data available for export'}), 400

    # Get municipality info
    municipality = result.get('municipality', {})

    try:
        # Use TableFormatterAgent
        from services.scraper.agents.presentation import TableFormatterAgent
        from services.scraper.models import AgentRequest

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            agent = TableFormatterAgent()
            request = AgentRequest(
                agent_id="pr-1",
                task=f"export-markdown-{session_id}",
                input_data={
                    'extraction_result': extraction_result,
                    'municipality': municipality
                }
            )

            response = loop.run_until_complete(agent.process(request))

            if not response.success:
                return jsonify({
                    'success': False,
                    'error': 'Markdown generation failed',
                    'details': response.errors
                }), 500

            # Get markdown content
            markdown_content = response.output_data.get('markdown_tables', '')
            if not markdown_content:
                markdown_content = response.output_data.get('systems_info_table', '')
                if response.output_data.get('public_bids_table'):
                    markdown_content += '\n\n' + response.output_data.get('public_bids_table', '')

            if not markdown_content:
                return jsonify({'error': 'No markdown content generated'}), 500

            # Generate filename
            city = municipality.get('city', 'Unknown') if isinstance(municipality, dict) else 'Unknown'
            state = municipality.get('state', 'XX') if isinstance(municipality, dict) else 'XX'
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"CityScraper_{city}_{state}_{timestamp}.md"

            # Return as downloadable file
            response = make_response(markdown_content)
            response.headers['Content-Type'] = 'text/markdown; charset=utf-8'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        finally:
            loop.close()

    except Exception as e:
        logger.exception(f"Markdown export error: {e}")
        return jsonify({
            'success': False,
            'error': 'Markdown export failed',
            'details': str(e)
        }), 500


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for Render monitoring"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'active_sessions': len(active_analyses),
        'completed_sessions': len(analysis_results)
    }), 200


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not Found'}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}", exc_info=True)
    return jsonify({'error': 'Internal Server Error'}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler - return JSON instead of HTML"""
    logger.error(f"Unhandled exception: {e}", exc_info=True)
    return jsonify({
        'success': False,
        'error': 'An unexpected error occurred. Please try again.'
    }), 500


# ============================================================================
# MAIN
# ============================================================================

# Start session cleanup scheduler
cleanup_expired_sessions()
logger.info("🧹 Session cleanup scheduler started (15-minute intervals)")

if __name__ == '__main__':
    logger.info("="*60)
    logger.info("BidBrief - AI Document Analysis Platform")
    logger.info("="*60)

    # Get port and debug from environment (Render compatibility)
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'

    logger.info(f"Starting server on port {port} (debug={debug})")
    app.run(host='0.0.0.0', port=port, debug=debug, threaded=True)
else:
    # For gunicorn
    logger.info("BidBrief loaded (gunicorn mode)")
