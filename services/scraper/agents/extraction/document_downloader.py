"""
Document Downloader Agent (EX-6)

Downloads accessible bid documents from URLs found by EX-5.
Tracks download status and stores files in scraper_downloads directory.

This agent is DIFFERENT from EX-1 through EX-5:
- Does NOT use OpenAI for parsing (no LLM needed)
- Uses httpx to download files directly
- Stores files in scraper_downloads/{session_id}/ directory
- Tracks success/failure for each URL
- Respects rate limits and timeouts

Responsibilities:
- Download PDF, DOC, DOCX, XLS, XLSX files
- Generate safe filenames
- Track download status (success, failed, skipped)
- Report file metadata (size, type)
- Handle redirects, auth walls, timeouts gracefully
"""

import asyncio
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse, unquote

import httpx

from services.scraper.agents.base import BaseAgent
from services.scraper.models import AgentRequest, AgentResponse
from services.scraper.prompts.ex6_download import get_config, SUPPORTED_FILE_TYPES

logger = logging.getLogger(__name__)


class DocumentDownloaderAgent(BaseAgent):
    """
    EX-6: Document Downloader Agent

    Downloads bid documents from URLs found by EX-5 (Bid Extractor).

    This agent is mechanical - it does NOT use LLM parsing.
    It uses httpx to download files directly and tracks status.

    Key Features:
    - Downloads PDF, DOC, DOCX, XLS, XLSX, CSV, TXT, RTF, ZIP files
    - Stores in scraper_downloads/{session_id}/ directory
    - Generates safe filenames from document titles
    - Tracks download status: success, failed, skipped
    - Reports file metadata: size, type, download time
    - Handles redirects, auth walls, timeouts gracefully
    - Rate-limited to avoid server strain (0.5s delay between downloads)
    """

    AGENT_ID = "ex-6"
    AGENT_NAME = "Document Downloader"
    AGENT_VERSION = "1.0.0"
    PROMPT_VERSION = "1.0.0"  # Not used - no LLM prompt
    PROMPT_LAST_REFINED = "2026-02-03"

    # Download configuration defaults
    DEFAULT_MAX_FILE_SIZE_MB = 50
    DEFAULT_TIMEOUT_SECONDS = 30
    DEFAULT_DOWNLOAD_DIR = "scraper_downloads"
    RATE_LIMIT_DELAY = 0.5  # seconds between downloads

    # User-agent for downloads
    USER_AGENT = "BidBrief CityScraper/1.0 (Municipal Research Tool)"

    def __init__(self, *args, **kwargs):
        """Initialize the Document Downloader agent."""
        super().__init__(*args, **kwargs)
        self._download_config = get_config()

    def get_system_prompt(self) -> str:
        """
        Get system prompt - not used for this agent.

        This agent does NOT use LLM parsing. This method exists
        for interface compliance with BaseAgent.
        """
        return "Document Downloader Agent - No LLM prompt required."

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
            Dict with status, size, error_message, content_type
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

                    # Check content length
                    content_length = head_response.headers.get('content-length')
                    if content_length:
                        size = int(content_length)
                        if size > max_file_size_bytes:
                            return {
                                'status': 'skipped',
                                'size': size,
                                'error_message': f'File too large ({size / (1024*1024):.1f}MB > {max_file_size_bytes / (1024*1024):.0f}MB)',
                                'content_type': head_response.headers.get('content-type', '')
                            }
                except httpx.HTTPError:
                    # HEAD not supported, proceed with GET
                    pass

                # Download the file
                response = await client.get(url)

                # Check status code
                if response.status_code == 401 or response.status_code == 403:
                    return {
                        'status': 'failed',
                        'size': 0,
                        'error_message': f'Authentication required (HTTP {response.status_code})',
                        'content_type': response.headers.get('content-type', '')
                    }

                if response.status_code != 200:
                    return {
                        'status': 'failed',
                        'size': 0,
                        'error_message': f'HTTP {response.status_code}',
                        'content_type': response.headers.get('content-type', '')
                    }

                content = response.content
                content_size = len(content)

                # Check size after download
                if content_size > max_file_size_bytes:
                    return {
                        'status': 'skipped',
                        'size': content_size,
                        'error_message': f'File too large ({content_size / (1024*1024):.1f}MB)',
                        'content_type': response.headers.get('content-type', '')
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
                                'status': 'failed',
                                'size': content_size,
                                'error_message': 'Authentication required (login page returned)',
                                'content_type': content_type
                            }

                # Ensure parent directory exists
                os.makedirs(os.path.dirname(local_path), exist_ok=True)

                # Write file
                with open(local_path, 'wb') as f:
                    f.write(content)

                return {
                    'status': 'success',
                    'size': content_size,
                    'error_message': None,
                    'content_type': content_type
                }

        except httpx.TimeoutException:
            return {
                'status': 'failed',
                'size': 0,
                'error_message': f'Timeout after {timeout_seconds}s',
                'content_type': ''
            }
        except httpx.ConnectError as e:
            return {
                'status': 'failed',
                'size': 0,
                'error_message': f'Connection error: {str(e)[:100]}',
                'content_type': ''
            }
        except Exception as e:
            logger.exception(f"EX-6 download error for {url}: {e}")
            return {
                'status': 'failed',
                'size': 0,
                'error_message': f'{type(e).__name__}: {str(e)[:100]}',
                'content_type': ''
            }

    async def process(self, request: AgentRequest) -> AgentResponse:
        """
        Process document download request.

        Expected input_data:
        - session_id: str - For organizing downloads
        - documents: list - Documents from EX-5.get_downloadable_documents()
            Each document: {title, url, file_type, bid_title}
        - max_file_size_mb: int - Optional, default 50MB
        - timeout_seconds: int - Optional, default 30

        Returns AgentResponse with:
        - downloads: List of download results
        - summary: Counts and totals
        - download_directory: Path to download directory
        """
        start_time = time.time()

        # Extract input parameters
        session_id = request.input_data.get('session_id', '')
        documents = request.input_data.get('documents', [])
        max_file_size_mb = request.input_data.get(
            'max_file_size_mb',
            self.DEFAULT_MAX_FILE_SIZE_MB
        )
        timeout_seconds = request.input_data.get(
            'timeout_seconds',
            self.DEFAULT_TIMEOUT_SECONDS
        )

        # Validate session_id
        if not session_id:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["session_id is required"]
            )

        # Validate documents
        if not isinstance(documents, list):
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=False,
                output_data={},
                errors=["documents must be a list"]
            )

        # Handle empty document list
        if not documents:
            return AgentResponse(
                agent_id=self.AGENT_ID,
                task=request.task,
                success=True,
                output_data={
                    'downloads': [],
                    'summary': {
                        'total_documents': 0,
                        'successful': 0,
                        'failed': 0,
                        'skipped': 0,
                        'total_size_bytes': 0
                    },
                    'download_directory': ''
                },
                errors=[],
                processing_time_seconds=time.time() - start_time
            )

        # Calculate max file size in bytes
        max_file_size_bytes = max_file_size_mb * 1024 * 1024

        # Create download directory
        download_dir = Path(self.DEFAULT_DOWNLOAD_DIR) / session_id
        download_dir.mkdir(parents=True, exist_ok=True)

        self.emit_event(
            "processing",
            f"Downloading {len(documents)} documents to {download_dir}"
        )

        # Process each document
        downloads = []
        summary = {
            'total_documents': len(documents),
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'total_size_bytes': 0
        }

        for i, doc in enumerate(documents):
            if not isinstance(doc, dict):
                logger.warning(f"Skipping non-dict document at index {i}")
                continue

            url = doc.get('url', '').strip()
            title = doc.get('title', '')
            bid_title = doc.get('bid_title', '')
            file_type = doc.get('file_type', '')

            # Skip empty URLs
            if not url:
                downloads.append({
                    'original_url': '',
                    'title': title,
                    'bid_title': bid_title,
                    'status': 'skipped',
                    'local_path': '',
                    'file_size_bytes': 0,
                    'file_type': file_type,
                    'error_message': 'Empty URL',
                    'download_time_seconds': 0.0
                })
                summary['skipped'] += 1
                continue

            # Determine file type
            detected_type = file_type or self._get_file_type_from_url(url)

            # Check if file type is supported
            if detected_type and not self._is_supported_file_type(detected_type):
                downloads.append({
                    'original_url': url,
                    'title': title,
                    'bid_title': bid_title,
                    'status': 'skipped',
                    'local_path': '',
                    'file_size_bytes': 0,
                    'file_type': detected_type,
                    'error_message': f'Unsupported file type: {detected_type}',
                    'download_time_seconds': 0.0
                })
                summary['skipped'] += 1
                continue

            # Generate safe filename
            safe_name = self._safe_filename(title, url, detected_type or '')
            local_path = str(download_dir / safe_name)

            # Handle duplicate filenames
            base_path = local_path
            counter = 1
            while os.path.exists(local_path):
                name_parts = base_path.rsplit('.', 1)
                if len(name_parts) == 2:
                    local_path = f"{name_parts[0]}_{counter}.{name_parts[1]}"
                else:
                    local_path = f"{base_path}_{counter}"
                counter += 1

            # Emit progress event
            self.emit_event(
                "downloading",
                f"Downloading {i+1}/{len(documents)}: {title[:50] or url[:50]}..."
            )

            # Download the file
            download_start = time.time()
            result = await self._download_file(
                url=url,
                local_path=local_path,
                timeout_seconds=timeout_seconds,
                max_file_size_bytes=max_file_size_bytes
            )
            download_time = time.time() - download_start

            # Update file type from content-type if not already known
            if not detected_type and result.get('content_type'):
                detected_type = self._get_file_type_from_content_type(
                    result['content_type']
                )

            # Build download result
            download_result = {
                'original_url': url,
                'title': title,
                'bid_title': bid_title,
                'status': result['status'],
                'local_path': local_path if result['status'] == 'success' else '',
                'file_size_bytes': result['size'],
                'file_type': detected_type or 'unknown',
                'error_message': result.get('error_message', ''),
                'download_time_seconds': round(download_time, 2)
            }
            downloads.append(download_result)

            # Update summary
            if result['status'] == 'success':
                summary['successful'] += 1
                summary['total_size_bytes'] += result['size']
            elif result['status'] == 'failed':
                summary['failed'] += 1
            else:
                summary['skipped'] += 1

            # Rate limiting - small delay between downloads
            if i < len(documents) - 1:
                await asyncio.sleep(self.RATE_LIMIT_DELAY)

        elapsed = time.time() - start_time

        # Emit completion event
        self.emit_event(
            "completed",
            f"Downloaded {summary['successful']}/{summary['total_documents']} documents "
            f"({summary['total_size_bytes'] / (1024*1024):.1f}MB)",
            is_completed=True
        )

        return AgentResponse(
            agent_id=self.AGENT_ID,
            task=request.task,
            success=True,
            output_data={
                'downloads': downloads,
                'summary': summary,
                'download_directory': str(download_dir)
            },
            errors=[],
            tokens_used=0,  # No LLM usage
            processing_time_seconds=elapsed
        )

    def validate_output(self, output: Dict[str, Any]) -> List[str]:
        """
        Validate download output.

        Args:
            output: The output data to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check required fields
        if 'downloads' not in output:
            errors.append("Missing 'downloads' list")

        if 'summary' not in output:
            errors.append("Missing 'summary' dict")

        if 'download_directory' not in output:
            errors.append("Missing 'download_directory'")

        if errors:
            return errors

        # Validate downloads is a list
        downloads = output.get('downloads', [])
        if not isinstance(downloads, list):
            errors.append("'downloads' must be a list")
            return errors

        # Validate each download result
        for i, dl in enumerate(downloads):
            if not isinstance(dl, dict):
                errors.append(f"Download {i} must be a dictionary")
                continue

            # Required fields
            if 'original_url' not in dl:
                errors.append(f"Download {i} missing 'original_url'")
            if 'status' not in dl:
                errors.append(f"Download {i} missing 'status'")
            elif dl['status'] not in ['success', 'failed', 'skipped']:
                errors.append(f"Download {i} invalid status: {dl['status']}")

            # If success, must have local_path
            if dl.get('status') == 'success' and not dl.get('local_path'):
                errors.append(f"Download {i} success but missing 'local_path'")

        # Validate summary
        summary = output.get('summary', {})
        if not isinstance(summary, dict):
            errors.append("'summary' must be a dictionary")
        else:
            required_summary_fields = [
                'total_documents', 'successful', 'failed', 'skipped', 'total_size_bytes'
            ]
            for field in required_summary_fields:
                if field not in summary:
                    errors.append(f"Summary missing '{field}'")

        return errors

    def get_download_summary(self, output: Dict[str, Any]) -> str:
        """
        Get human-readable download summary.

        Args:
            output: Validated output from process()

        Returns:
            Summary string
        """
        summary = output.get('summary', {})
        total = summary.get('total_documents', 0)
        success = summary.get('successful', 0)
        failed = summary.get('failed', 0)
        skipped = summary.get('skipped', 0)
        size_mb = summary.get('total_size_bytes', 0) / (1024 * 1024)

        return (
            f"Downloaded {success}/{total} documents ({size_mb:.1f}MB). "
            f"Failed: {failed}, Skipped: {skipped}"
        )

    def get_successful_downloads(self, output: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Get list of successfully downloaded files.

        Args:
            output: Validated output from process()

        Returns:
            List of dicts with local_path, title, bid_title, file_type
        """
        downloads = output.get('downloads', [])
        return [
            {
                'local_path': dl['local_path'],
                'title': dl.get('title', ''),
                'bid_title': dl.get('bid_title', ''),
                'file_type': dl.get('file_type', ''),
                'file_size_bytes': dl.get('file_size_bytes', 0)
            }
            for dl in downloads
            if dl.get('status') == 'success'
        ]

    def get_failed_downloads(self, output: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Get list of failed downloads with error messages.

        Args:
            output: Validated output from process()

        Returns:
            List of dicts with original_url, title, error_message
        """
        downloads = output.get('downloads', [])
        return [
            {
                'original_url': dl.get('original_url', ''),
                'title': dl.get('title', ''),
                'bid_title': dl.get('bid_title', ''),
                'error_message': dl.get('error_message', 'Unknown error')
            }
            for dl in downloads
            if dl.get('status') == 'failed'
        ]
