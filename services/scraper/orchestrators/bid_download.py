"""
Bid Download Orchestrator (UC-4)

Orchestrates the downloading of bid documents from extraction results.
Parses document URLs from EX-5 results and attempts downloads using EX-6
pattern, tracking status for each document.

Pipeline:
1. Validate extraction result contains public bid data
2. Parse document URLs from public_bid_rows
3. Attempt downloads for each document
4. Track success/failure/blocked status
5. Return download report with statistics

CRITICAL: This orchestrator handles documents that may be behind authentication
walls. Auth-blocked documents are tracked separately from failures.

Version: 1.0.0
"""

import asyncio
import logging
import os
import re
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Callable, List
from urllib.parse import urlparse, unquote

import httpx

from services.scraper.config import get_config, ScraperConfig
from services.scraper.models import (
    AgentActivityEvent,
    ExtractionResult,
    MunicipalPublicBidRow,
)

logger = logging.getLogger(__name__)


# Supported file types for download
SUPPORTED_FILE_TYPES = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt', 'rtf', 'zip']


class BidDownloadOrchestrator:
    """
    UC-4: Bid Download Orchestrator

    Orchestrates downloading bid documents from extraction results.
    Parses downloadable document URLs from EX-5 public bid data and
    attempts downloads, tracking status for each document.

    Flow:
        Extraction Result (with public_bid_rows)
                     |
            Parse bid documents from EX-5 results
                     |
            For each document: attempt download
                     |
            Track success/failure per document
                     |
        Download Report with accessible files
    """

    ORCHESTRATOR_ID = "uc-4"
    ORCHESTRATOR_NAME = "Bid Downloads"
    ORCHESTRATOR_VERSION = "1.0.0"

    # Download configuration defaults
    DEFAULT_MAX_FILE_SIZE_MB = 50
    DEFAULT_TIMEOUT_SECONDS = 30
    DEFAULT_DOWNLOAD_DIR = "scraper_downloads"
    RATE_LIMIT_DELAY = 0.5  # seconds between downloads

    # User-agent for downloads
    USER_AGENT = "BidBrief CityScraper/1.0 (Municipal Research Tool)"

    def __init__(
        self,
        config: Optional[ScraperConfig] = None,
        event_callback: Optional[Callable[[AgentActivityEvent], None]] = None
    ):
        """
        Initialize the Bid Download Orchestrator.

        Args:
            config: Optional scraper configuration
            event_callback: Optional callback for progress events (for UI feed)
        """
        self.config = config or get_config()
        self.event_callback = event_callback

        # Track pipeline state
        self.session_id: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self._cancelled = False

        # Download tracking
        self.documents_found: List[Dict[str, Any]] = []
        self.documents_downloaded: List[Dict[str, Any]] = []
        self.documents_failed: List[Dict[str, Any]] = []
        self.documents_blocked: List[Dict[str, Any]] = []

        logger.info(f"Initialized {self.ORCHESTRATOR_NAME} v{self.ORCHESTRATOR_VERSION}")

    def emit_event(
        self,
        status: str,
        message: str,
        is_completed: bool = False
    ):
        """
        Emit a progress event for the UI agent activity feed.

        Args:
            status: Event status type (processing, completed, failed, etc.)
            message: Human-readable status message
            is_completed: Whether this event marks completion
        """
        if self.event_callback:
            event = AgentActivityEvent(
                agent_id=self.ORCHESTRATOR_ID,
                agent_name=self.ORCHESTRATOR_NAME,
                status=status,
                message=message,
                is_active=not is_completed,
                is_completed=is_completed,
                timestamp=datetime.now()
            )
            self.event_callback(event)
        logger.info(f"UC-4: [{status}] {message}")

    def cancel(self):
        """Request cancellation of the pipeline."""
        self._cancelled = True
        logger.info("UC-4: Cancellation requested")

    def _safe_filename(self, title: str, url: str, file_type: str) -> str:
        """
        Generate a safe filename from title and URL.

        Args:
            title: Document title
            url: Document URL
            file_type: File type/extension

        Returns:
            Safe filename string
        """
        # Start with title, fallback to URL path
        if title and title.strip():
            base_name = title.strip()
        else:
            # Extract filename from URL path
            parsed = urlparse(url)
            path = unquote(parsed.path)
            base_name = os.path.basename(path) or "document"

        # Normalize unicode characters
        safe = unicodedata.normalize('NFKD', base_name)
        safe = safe.encode('ascii', 'ignore').decode('ascii')

        # Remove special characters, keep alphanumeric, spaces, dots, hyphens
        safe = re.sub(r'[^\w\s.-]', '', safe)

        # Replace multiple spaces/underscores with single underscore
        safe = re.sub(r'[\s_]+', '_', safe)

        # Trim to reasonable length (leave room for extension)
        safe = safe[:100]

        # Remove leading/trailing underscores and dots
        safe = safe.strip('_.')

        # Ensure we have something
        if not safe:
            safe = "document"

        # Determine extension
        ext = file_type.lower().strip('.') if file_type else ''
        if not ext:
            # Try to extract from URL
            url_ext = url.split('.')[-1].lower()[:10]
            if url_ext in SUPPORTED_FILE_TYPES:
                ext = url_ext
            else:
                ext = 'bin'  # Unknown binary

        return f"{safe}.{ext}"

    def _get_file_type_from_url(self, url: str) -> Optional[str]:
        """
        Extract file type from URL.

        Args:
            url: Document URL

        Returns:
            File type string or None
        """
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()
            for ext in SUPPORTED_FILE_TYPES:
                if path.endswith(f'.{ext}'):
                    return ext
        except Exception:
            pass
        return None

    def _get_file_type_from_content_type(self, content_type: str) -> Optional[str]:
        """
        Extract file type from Content-Type header.

        Args:
            content_type: Content-Type header value

        Returns:
            File type string or None
        """
        if not content_type:
            return None

        content_type = content_type.lower()

        # Common MIME type mappings
        mime_map = {
            'application/pdf': 'pdf',
            'application/msword': 'doc',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
            'application/vnd.ms-excel': 'xls',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
            'text/csv': 'csv',
            'text/plain': 'txt',
            'application/rtf': 'rtf',
            'text/rtf': 'rtf',
            'application/zip': 'zip',
            'application/x-zip-compressed': 'zip',
        }

        for mime, ext in mime_map.items():
            if mime in content_type:
                return ext

        return None

    def _is_supported_file_type(self, file_type: str) -> bool:
        """
        Check if file type is supported.

        Args:
            file_type: File type string

        Returns:
            True if supported
        """
        if not file_type:
            return False
        return file_type.lower().strip('.') in SUPPORTED_FILE_TYPES

    async def _download_file(
        self,
        url: str,
        local_path: str,
        timeout_seconds: int,
        max_file_size_bytes: int
    ) -> Dict[str, Any]:
        """
        Download a single file.

        Args:
            url: URL to download
            local_path: Local path to save file
            timeout_seconds: Timeout for download
            max_file_size_bytes: Maximum file size in bytes

        Returns:
            Dict with status, size, error_message, content_type, is_blocked
        """
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(timeout_seconds),
                follow_redirects=True,
                headers={'User-Agent': self.USER_AGENT}
            ) as client:
                # First, do a HEAD request to check size and type
                try:
                    head_response = await client.head(url)

                    # Check for auth-blocked (401/403)
                    if head_response.status_code in (401, 403):
                        return {
                            'status': 'blocked',
                            'size': 0,
                            'error_message': f'Authentication required (HTTP {head_response.status_code})',
                            'content_type': head_response.headers.get('content-type', ''),
                            'is_blocked': True
                        }

                    # Check content length
                    content_length = head_response.headers.get('content-length')
                    if content_length:
                        size = int(content_length)
                        if size > max_file_size_bytes:
                            return {
                                'status': 'failed',
                                'size': size,
                                'error_message': f'File too large ({size / (1024*1024):.1f}MB > {max_file_size_bytes / (1024*1024):.0f}MB)',
                                'content_type': head_response.headers.get('content-type', ''),
                                'is_blocked': False
                            }
                except httpx.HTTPError:
                    # HEAD not supported, proceed with GET
                    pass

                # Download the file
                response = await client.get(url)

                # Check for auth-blocked
                if response.status_code in (401, 403):
                    return {
                        'status': 'blocked',
                        'size': 0,
                        'error_message': f'Authentication required (HTTP {response.status_code})',
                        'content_type': response.headers.get('content-type', ''),
                        'is_blocked': True
                    }

                if response.status_code != 200:
                    return {
                        'status': 'failed',
                        'size': 0,
                        'error_message': f'HTTP {response.status_code}',
                        'content_type': response.headers.get('content-type', ''),
                        'is_blocked': False
                    }

                content = response.content
                content_size = len(content)

                # Check size after download
                if content_size > max_file_size_bytes:
                    return {
                        'status': 'failed',
                        'size': content_size,
                        'error_message': f'File too large ({content_size / (1024*1024):.1f}MB)',
                        'content_type': response.headers.get('content-type', ''),
                        'is_blocked': False
                    }

                # Check if we got HTML instead of document (login page)
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' in content_type:
                    # Check if content looks like HTML (login/error page)
                    sample = content[:1000].decode('utf-8', errors='ignore').lower()
                    if '<html' in sample or '<!doctype' in sample:
                        # Could be a login page or error page
                        if 'login' in sample or 'sign in' in sample or 'password' in sample:
                            return {
                                'status': 'blocked',
                                'size': content_size,
                                'error_message': 'Authentication required (login page returned)',
                                'content_type': content_type,
                                'is_blocked': True
                            }

                # Ensure parent directory exists
                os.makedirs(os.path.dirname(local_path), exist_ok=True)

                # Write file
                with open(local_path, 'wb') as f:
                    f.write(content)

                return {
                    'status': 'downloaded',
                    'size': content_size,
                    'error_message': None,
                    'content_type': content_type,
                    'is_blocked': False
                }

        except httpx.TimeoutException:
            return {
                'status': 'failed',
                'size': 0,
                'error_message': f'Timeout after {timeout_seconds}s',
                'content_type': '',
                'is_blocked': False
            }
        except httpx.ConnectError as e:
            return {
                'status': 'failed',
                'size': 0,
                'error_message': f'Connection error: {str(e)[:100]}',
                'content_type': '',
                'is_blocked': False
            }
        except Exception as e:
            logger.exception(f"UC-4 download error for {url}: {e}")
            return {
                'status': 'failed',
                'size': 0,
                'error_message': f'{type(e).__name__}: {str(e)[:100]}',
                'content_type': '',
                'is_blocked': False
            }

    def _parse_documents_from_extraction(
        self,
        extraction_result: Any
    ) -> List[Dict[str, Any]]:
        """
        Parse downloadable documents from extraction result.

        Args:
            extraction_result: ExtractionResult or dict with public bid data

        Returns:
            List of document dicts with title, url, file_type, bid_title
        """
        documents = []

        # Handle ExtractionResult dataclass
        if isinstance(extraction_result, ExtractionResult):
            for bid_row in extraction_result.public_bid_rows:
                if not isinstance(bid_row, MunicipalPublicBidRow):
                    continue

                bid_title = bid_row.bid_contract_title or 'Unknown Bid'
                downloadable_docs = bid_row.downloadable_documents or []

                for doc in downloadable_docs:
                    if isinstance(doc, dict) and doc.get('url'):
                        documents.append({
                            'title': doc.get('title', 'Unknown Document'),
                            'url': doc.get('url'),
                            'file_type': doc.get('file_type', ''),
                            'bid_title': bid_title,
                            'status': 'pending',
                            'file_size_bytes': None,
                            'download_path': None,
                            'error': None
                        })

        # Handle dict format (from serialized results)
        elif isinstance(extraction_result, dict):
            # Try public_bid_rows
            public_bid_rows = extraction_result.get('public_bid_rows', [])
            for bid_row in public_bid_rows:
                if not isinstance(bid_row, dict):
                    continue

                bid_title = bid_row.get('bid_contract_title', 'Unknown Bid')
                downloadable_docs = bid_row.get('downloadable_documents', [])

                for doc in downloadable_docs:
                    if isinstance(doc, dict) and doc.get('url'):
                        documents.append({
                            'title': doc.get('title', 'Unknown Document'),
                            'url': doc.get('url'),
                            'file_type': doc.get('file_type', ''),
                            'bid_title': bid_title,
                            'status': 'pending',
                            'file_size_bytes': None,
                            'download_path': None,
                            'error': None
                        })

            # Also try documents already extracted by EX-6 (from downloaded_documents)
            downloaded_docs = extraction_result.get('downloaded_documents', [])
            for doc in downloaded_docs:
                if isinstance(doc, dict) and doc.get('original_url'):
                    # These are already downloaded, just track them
                    documents.append({
                        'title': doc.get('title', 'Unknown Document'),
                        'url': doc.get('original_url'),
                        'file_type': doc.get('file_type', ''),
                        'bid_title': doc.get('bid_title', 'Unknown Bid'),
                        'status': 'downloaded',
                        'file_size_bytes': doc.get('file_size_bytes', 0),
                        'download_path': doc.get('local_path', ''),
                        'error': None
                    })

        return documents

    async def run(
        self,
        extraction_result: Any,
        session_id: Optional[str] = None,
        max_file_size_mb: int = DEFAULT_MAX_FILE_SIZE_MB,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    ) -> Dict[str, Any]:
        """
        Run the bid download pipeline.

        Args:
            extraction_result: ExtractionResult or dict containing public bid data
            session_id: Optional session ID for tracking (generated if not provided)
            max_file_size_mb: Maximum file size to download in MB
            timeout_seconds: Timeout per download in seconds

        Returns:
            Dict containing:
                - documents_found: Total documents identified
                - documents_downloaded: Successfully downloaded list with file info
                - documents_failed: Failed downloads with reasons
                - documents_blocked: Authentication-blocked documents
                - statistics: { found, downloaded, failed, blocked, total_size_bytes }
                - download_directory: Path to downloads
                - success: bool
                - error: Optional error message if failed
        """
        start_time = time.time()
        self.session_id = session_id or f"uc4-{uuid.uuid4().hex[:12]}"
        self.started_at = datetime.now()
        self._cancelled = False

        # Reset tracking
        self.documents_found = []
        self.documents_downloaded = []
        self.documents_failed = []
        self.documents_blocked = []

        # Input validation
        validation_errors = self._validate_inputs(extraction_result)
        if validation_errors:
            return self._create_error_result(
                f"Input validation failed: {'; '.join(validation_errors)}",
                start_time
            )

        self.emit_event("processing", "Starting bid document download...")

        try:
            # =================================================================
            # STAGE 1: Parse documents from extraction result
            # =================================================================
            self.emit_event("processing", "Stage 1/2: Parsing documents from extraction results...")

            self.documents_found = self._parse_documents_from_extraction(extraction_result)

            if not self.documents_found:
                self.emit_event(
                    "completed",
                    "No downloadable documents found in extraction results",
                    is_completed=True
                )
                return self._create_success_result(start_time, no_documents=True)

            # Count already-downloaded documents
            already_downloaded = [d for d in self.documents_found if d.get('status') == 'downloaded']
            pending_documents = [d for d in self.documents_found if d.get('status') == 'pending']

            self.emit_event(
                "completed",
                f"Stage 1/2: Found {len(self.documents_found)} documents "
                f"({len(already_downloaded)} already downloaded, {len(pending_documents)} to download)"
            )

            # Track already-downloaded as successful
            for doc in already_downloaded:
                self.documents_downloaded.append(doc)

            if self._cancelled:
                return self._create_cancelled_result(start_time)

            # =================================================================
            # STAGE 2: Download pending documents
            # =================================================================
            if pending_documents:
                self.emit_event(
                    "processing",
                    f"Stage 2/2: Downloading {len(pending_documents)} documents..."
                )

                # Create download directory
                download_dir = Path(self.DEFAULT_DOWNLOAD_DIR) / self.session_id
                download_dir.mkdir(parents=True, exist_ok=True)

                max_file_size_bytes = max_file_size_mb * 1024 * 1024
                total_downloaded = 0

                for i, doc in enumerate(pending_documents):
                    if self._cancelled:
                        # Mark remaining as pending
                        break

                    url = doc.get('url', '')
                    title = doc.get('title', 'Unknown')
                    file_type = doc.get('file_type', '') or self._get_file_type_from_url(url)

                    self.emit_event(
                        "downloading",
                        f"Downloading {i+1}/{len(pending_documents)}: {title[:50]}..."
                    )

                    # Generate safe filename
                    safe_name = self._safe_filename(title, url, file_type or '')
                    local_path = download_dir / safe_name

                    # SECURITY: Verify path stays within download_dir
                    try:
                        resolved_path = local_path.resolve()
                        base_dir = download_dir.resolve()
                        if not str(resolved_path).startswith(str(base_dir)):
                            logger.warning(f"UC-4 path traversal attempt detected: {safe_name}")
                            doc['status'] = 'failed'
                            doc['error'] = 'Invalid filename: path traversal detected'
                            self.documents_failed.append(doc)
                            continue
                    except Exception as e:
                        doc['status'] = 'failed'
                        doc['error'] = f'Path validation error: {str(e)[:50]}'
                        self.documents_failed.append(doc)
                        continue

                    local_path_str = str(local_path)

                    # Handle duplicate filenames
                    base_path = local_path_str
                    counter = 1
                    while os.path.exists(local_path_str):
                        name_parts = base_path.rsplit('.', 1)
                        if len(name_parts) == 2:
                            local_path_str = f"{name_parts[0]}_{counter}.{name_parts[1]}"
                        else:
                            local_path_str = f"{base_path}_{counter}"
                        counter += 1

                    # Download the file
                    result = await self._download_file(
                        url=url,
                        local_path=local_path_str,
                        timeout_seconds=timeout_seconds,
                        max_file_size_bytes=max_file_size_bytes
                    )

                    # Update file type from content-type if not already known
                    if not file_type and result.get('content_type'):
                        file_type = self._get_file_type_from_content_type(result['content_type'])
                        doc['file_type'] = file_type

                    # Update document with result
                    doc['file_size_bytes'] = result['size']

                    if result['status'] == 'downloaded':
                        doc['status'] = 'downloaded'
                        doc['download_path'] = local_path_str
                        self.documents_downloaded.append(doc)
                        total_downloaded += 1
                    elif result.get('is_blocked'):
                        doc['status'] = 'blocked'
                        doc['error'] = result.get('error_message', 'Authentication required')
                        self.documents_blocked.append(doc)
                    else:
                        doc['status'] = 'failed'
                        doc['error'] = result.get('error_message', 'Download failed')
                        self.documents_failed.append(doc)

                    # Rate limiting
                    if i < len(pending_documents) - 1:
                        await asyncio.sleep(self.RATE_LIMIT_DELAY)

                self.emit_event(
                    "completed",
                    f"Stage 2/2: Downloaded {total_downloaded}/{len(pending_documents)} documents"
                )

            if self._cancelled:
                return self._create_cancelled_result(start_time)

            self.completed_at = datetime.now()
            return self._create_success_result(start_time)

        except (SystemExit, KeyboardInterrupt):
            # Re-raise critical exceptions
            raise
        except Exception as e:
            logger.exception(f"UC-4 unexpected error: {e}")
            return self._create_error_result(
                f"Unexpected error: {type(e).__name__}: {str(e)[:200]}",
                start_time
            )

    def _validate_inputs(self, extraction_result: Any) -> List[str]:
        """
        Validate all inputs with type checks.

        Args:
            extraction_result: Expected ExtractionResult or dict

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        # Validate extraction_result
        if extraction_result is None:
            errors.append("extraction_result cannot be None")
        elif not isinstance(extraction_result, (ExtractionResult, dict)):
            errors.append(
                f"extraction_result must be ExtractionResult or dict, got {type(extraction_result).__name__}"
            )

        return errors

    def _create_success_result(
        self,
        start_time: float,
        no_documents: bool = False
    ) -> Dict[str, Any]:
        """
        Create a successful result.

        Args:
            start_time: Pipeline start time
            no_documents: True if no documents were found

        Returns:
            Success result dict
        """
        self.completed_at = datetime.now()
        elapsed = time.time() - start_time

        # Calculate statistics
        total_size = sum(
            d.get('file_size_bytes', 0) or 0
            for d in self.documents_downloaded
        )

        statistics = {
            'found': len(self.documents_found),
            'downloaded': len(self.documents_downloaded),
            'failed': len(self.documents_failed),
            'blocked': len(self.documents_blocked),
            'total_size_bytes': total_size,
            'processing_time_seconds': elapsed
        }

        # Determine download directory
        download_dir = ''
        if self.documents_downloaded:
            for doc in self.documents_downloaded:
                if doc.get('download_path'):
                    download_dir = str(Path(doc['download_path']).parent)
                    break

        if not no_documents:
            self.emit_event(
                "completed",
                f"Bid download complete: {statistics['downloaded']} downloaded, "
                f"{statistics['failed']} failed, {statistics['blocked']} blocked "
                f"({total_size / (1024*1024):.1f}MB)",
                is_completed=True
            )

        return {
            'success': True,
            'session_id': self.session_id,
            'documents_found': len(self.documents_found),
            'documents_downloaded': self.documents_downloaded,
            'documents_failed': self.documents_failed,
            'documents_blocked': self.documents_blocked,
            'statistics': statistics,
            'download_directory': download_dir,
            'processing_time_seconds': elapsed,
            'completed_at': self.completed_at.isoformat()
        }

    def _create_error_result(
        self,
        error_message: str,
        start_time: float
    ) -> Dict[str, Any]:
        """
        Create an error result.

        Args:
            error_message: Error description
            start_time: Pipeline start time

        Returns:
            Error result dict
        """
        self.completed_at = datetime.now()
        elapsed = time.time() - start_time

        self.emit_event("failed", f"Bid download failed: {error_message}", is_completed=True)

        return {
            'success': False,
            'session_id': self.session_id,
            'documents_found': len(self.documents_found),
            'documents_downloaded': self.documents_downloaded,
            'documents_failed': self.documents_failed,
            'documents_blocked': self.documents_blocked,
            'statistics': {
                'found': len(self.documents_found),
                'downloaded': len(self.documents_downloaded),
                'failed': len(self.documents_failed),
                'blocked': len(self.documents_blocked),
                'total_size_bytes': 0,
                'processing_time_seconds': elapsed
            },
            'download_directory': '',
            'error': error_message,
            'processing_time_seconds': elapsed,
            'completed_at': self.completed_at.isoformat()
        }

    def _create_cancelled_result(self, start_time: float) -> Dict[str, Any]:
        """
        Create a cancelled result.

        Args:
            start_time: Pipeline start time

        Returns:
            Cancelled result dict
        """
        self.completed_at = datetime.now()
        elapsed = time.time() - start_time

        self.emit_event("cancelled", "Bid download cancelled by user", is_completed=True)

        # Calculate statistics for partial results
        total_size = sum(
            d.get('file_size_bytes', 0) or 0
            for d in self.documents_downloaded
        )

        return {
            'success': False,
            'session_id': self.session_id,
            'documents_found': len(self.documents_found),
            'documents_downloaded': self.documents_downloaded,
            'documents_failed': self.documents_failed,
            'documents_blocked': self.documents_blocked,
            'statistics': {
                'found': len(self.documents_found),
                'downloaded': len(self.documents_downloaded),
                'failed': len(self.documents_failed),
                'blocked': len(self.documents_blocked),
                'total_size_bytes': total_size,
                'processing_time_seconds': elapsed
            },
            'download_directory': '',
            'error': 'Download cancelled by user',
            'processing_time_seconds': elapsed,
            'completed_at': self.completed_at.isoformat()
        }

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get pipeline execution statistics.

        Returns:
            Dict with execution statistics
        """
        total_size = sum(
            d.get('file_size_bytes', 0) or 0
            for d in self.documents_downloaded
        )

        duration = 0.0
        if self.started_at and self.completed_at:
            duration = (self.completed_at - self.started_at).total_seconds()

        return {
            'orchestrator': self.ORCHESTRATOR_NAME,
            'orchestrator_id': self.ORCHESTRATOR_ID,
            'version': self.ORCHESTRATOR_VERSION,
            'session_id': self.session_id,
            'documents_found': len(self.documents_found),
            'documents_downloaded': len(self.documents_downloaded),
            'documents_failed': len(self.documents_failed),
            'documents_blocked': len(self.documents_blocked),
            'total_size_bytes': total_size,
            'total_duration_seconds': duration,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }
