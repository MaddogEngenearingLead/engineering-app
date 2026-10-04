"""
Auto-Detection Setup for Real P&ID and Scope-of-Work Files

This module provides automatic file discovery and loading from the uploads directory.
It detects:
- P&ID files (PDF, PNG, JPG, etc.)
- Scope-of-work files (ANY text-readable format: TXT, MD, DOCX, PDF, CSV, JSON, LOG, etc.)

File naming patterns:
- P&ID: *.pdf, *.png, *.jpg (case-insensitive, binary image/document formats)
- Scope: Detected by content analysis, file naming heuristics, and text extraction

Scope detection strategy:
1. Keyword-based: Check filename for scope-related keywords
2. Content-based: Extract and analyze text content for scope indicators
3. Format-agnostic: Support any readable text format (TXT, MD, DOCX, PDF, RTF, JSON, CSV, etc.)
"""

from pathlib import Path
from typing import Optional, Tuple
import logging
import mimetypes
import re

logger = logging.getLogger(__name__)


class FileDetector:
    """Automatically detects P&ID and scope-of-work files from upload directory."""

    # P&ID file extensions (image/document formats)
    PID_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.svg', '.gif', '.bmp', '.tiff'}

    # Scope-related keywords (filename-based detection)
    SCOPE_KEYWORDS = {
        'scope', 'work', 'requirements', 'specification',
        'spec', 'sow', 'statement', 'job', 'statement_of_work',
        'contract', 'scope_of_work', 'project', 'task', 'description',
        'objective', 'deliverable', 'scope_document', 'brief',
        'proposal', 'statement_work', 'sow_document'
    }

    # Content keywords to identify scope-of-work text
    SCOPE_CONTENT_KEYWORDS = {
        'scope', 'work', 'requirements', 'specification', 'shall',
        'deliverable', 'objective', 'task', 'installation', 'replacement',
        'new work', 'existing', 'removal', 'demolition', 'equipment',
        'materials', 'job', 'phase', 'milestone', 'exclusion'
    }

    def __init__(self, upload_dir: str = "backend/uploads"):
        """
        Initialize file detector.

        Args:
            upload_dir: Path to uploads directory (default: backend/uploads)
        """
        self.upload_dir = Path(upload_dir)
        if not self.upload_dir.exists():
            logger.warning(f"Upload directory does not exist: {self.upload_dir}")

    def find_pid_files(self) -> list[Path]:
        """
        Find all P&ID files (images/PDFs) in upload directory.

        Returns:
            List of P&ID file paths, sorted by modification time (newest first)
        """
        if not self.upload_dir.exists():
            return []

        pid_files = [
            f for f in self.upload_dir.iterdir()
            if f.is_file() and f.suffix.lower() in self.PID_EXTENSIONS
        ]
        # Sort by modification time, newest first
        return sorted(pid_files, key=lambda f: f.stat().st_mtime, reverse=True)

    def extract_text_from_file(self, file_path: Path) -> str:
        """
        Extract readable text from any file format.

        Supports: TXT, MD, JSON, CSV, LOG, YAML, XML, RTF, PDF, DOCX, and more.

        Args:
            file_path: Path to file

        Returns:
            Extracted text content, or empty string if extraction fails
        """
        if not file_path.exists():
            return ""

        try:
            suffix = file_path.suffix.lower()

            # Plain text formats
            if suffix in {'.txt', '.md', '.log', '.csv', '.json', '.yaml', '.yml', '.xml', '.html', '.htm'}:
                return file_path.read_text(encoding='utf-8', errors='ignore').strip()

            # DOCX (Microsoft Word)
            if suffix == '.docx':
                try:
                    from docx import Document
                    doc = Document(file_path)
                    return '\n'.join([p.text for p in doc.paragraphs]).strip()
                except Exception as e:
                    logger.debug(f"Could not extract DOCX {file_path}: {e}")
                    return ""

            # PDF
            if suffix == '.pdf':
                try:
                    import pdfplumber
                    with pdfplumber.open(file_path) as pdf:
                        text = '\n'.join([page.extract_text() or "" for page in pdf.pages])
                        return text.strip()
                except Exception as e:
                    logger.debug(f"Could not extract PDF {file_path}: {e}")
                    return ""

            # RTF (Rich Text Format)
            if suffix == '.rtf':
                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    # Simple RTF stripping: remove control sequences
                    text = re.sub(r'\\[a-z0-9]+\s?', '', content)
                    return text.strip()
                except Exception as e:
                    logger.debug(f"Could not extract RTF {file_path}: {e}")
                    return ""

            # XLSX (Excel)
            if suffix in {'.xlsx', '.xls'}:
                try:
                    import openpyxl
                    wb = openpyxl.load_workbook(file_path)
                    rows = []
                    for sheet in wb.sheetnames:
                        ws = wb[sheet]
                        for row in ws.iter_rows(values_only=True):
                            rows.append('\t'.join(str(cell) if cell else '' for cell in row))
                    return '\n'.join(rows).strip()
                except Exception as e:
                    logger.debug(f"Could not extract XLSX {file_path}: {e}")
                    return ""

            # Fallback: try reading as text
            try:
                return file_path.read_text(encoding='utf-8', errors='ignore').strip()
            except Exception:
                return ""

        except Exception as e:
            logger.error(f"Error extracting text from {file_path}: {e}")
            return ""

    def score_file_as_scope(self, file_path: Path) -> float:
        """
        Score a file's likelihood of being a scope-of-work document.

        Scoring factors:
        - Filename keywords (high weight)
        - File extension (medium weight)
        - Content analysis (high weight)
        - File size (small weight)

        Args:
            file_path: Path to file

        Returns:
            Score 0.0-1.0 (higher = more likely to be scope document)
        """
        score = 0.0

        # 1. Filename-based scoring (0.0-0.4)
        name_lower = file_path.stem.lower()
        keyword_matches = sum(1 for kw in self.SCOPE_KEYWORDS if kw in name_lower)
        filename_score = min(0.4, keyword_matches * 0.1)
        score += filename_score

        # 2. File extension scoring (0.0-0.2)
        # Prefer text-based formats, penalize binary image formats
        suffix = file_path.suffix.lower()
        if suffix in {'.pdf', '.docx', '.txt', '.md', '.rtf'}:
            score += 0.15
        elif suffix in {'.json', '.csv', '.xml', '.yaml'}:
            score += 0.10
        elif suffix in {'.xlsx', '.xls', '.log'}:
            score += 0.05

        # 3. Content-based scoring (0.0-0.6)
        content = self.extract_text_from_file(file_path)
        if content:
            content_lower = content.lower()[:2000]  # First 2000 chars
            content_matches = sum(1 for kw in self.SCOPE_CONTENT_KEYWORDS if kw in content_lower)
            content_score = min(0.6, content_matches * 0.08)
            score += content_score

            # Bonus for structured scope-like content
            if any(pattern in content_lower for pattern in [
                'shall', 'requirement', 'deliverable', 'task', 'phase',
                'job #', 'project #', 'scope of work'
            ]):
                score += 0.1

        # 4. File size penalty (very small/empty = not scope)
        # (0.0-0.05)
        file_size = file_path.stat().st_size
        if file_size < 50:  # Too small to be meaningful
            score -= 0.2

        return max(0.0, min(1.0, score))

    def find_scope_files(self) -> list[Path]:
        """
        Find all potential scope-of-work files in upload directory.

        Uses intelligent scoring to rank by likelihood.

        Returns:
            List of scope file paths, sorted by relevance score (highest first)
        """
        if not self.upload_dir.exists():
            return []

        # Find all non-P&ID files (text-readable formats)
        candidate_files = [
            f for f in self.upload_dir.iterdir()
            if f.is_file() and f.suffix.lower() not in self.PID_EXTENSIONS
        ]

        # Score each file
        scored = []
        for f in candidate_files:
            score = self.score_file_as_scope(f)
            mtime = f.stat().st_mtime
            scored.append((f, score, mtime))

        # Sort by score (desc), then by modification time (desc)
        scored.sort(key=lambda x: (x[1], x[2]), reverse=True)

        result = [f[0] for f in scored if f[1] > 0.0]  # Only return files with positive score
        return result

    def get_latest_pid(self) -> Optional[Path]:
        """
        Get the most recently modified P&ID file.

        Returns:
            Path to latest P&ID file, or None if not found
        """
        files = self.find_pid_files()
        return files[0] if files else None

    def get_latest_scope(self) -> Optional[Path]:
        """
        Get the most relevant scope-of-work file.

        Uses intelligent content analysis to find best match.

        Returns:
            Path to scope file (prioritizes by score and keywords), or None if not found
        """
        files = self.find_scope_files()
        return files[0] if files else None

    def detect_files(self) -> Tuple[Optional[Path], Optional[Path], dict]:
        """
        Automatically detect P&ID and scope-of-work files.

        Returns:
            Tuple of (pid_path, scope_path, metadata)
            - pid_path: Path to detected P&ID, or None
            - scope_path: Path to detected scope file, or None
            - metadata: Dict with detection scores and file info
        """
        pid = self.get_latest_pid()
        scope = self.get_latest_scope()

        metadata = {
            'pid_file': pid.name if pid else None,
            'pid_path': str(pid) if pid else None,
            'scope_file': scope.name if scope else None,
            'scope_path': str(scope) if scope else None,
            'scope_score': self.score_file_as_scope(scope) if scope else 0.0,
            'pid_count': len(self.find_pid_files()),
            'scope_candidates': len(self.find_scope_files()),
        }

        logger.info(f"Detected P&ID: {pid.name if pid else 'None'}")
        logger.info(f"Detected Scope: {scope.name if scope else 'None'} (score: {metadata['scope_score']:.2f})")

        return pid, scope, metadata

    def read_scope_text(self, scope_path: Optional[Path]) -> str:
        """
        Read scope-of-work text from file.

        Uses intelligent text extraction supporting multiple formats.

        Args:
            scope_path: Path to scope file

        Returns:
            Scope text content
        """
        if not scope_path:
            return ""

        text = self.extract_text_from_file(scope_path)
        if not text:
            logger.warning(f"Could not extract text from scope file: {scope_path}")
            return ""

        return text

    def list_all_files(self) -> dict:
        """
        List all detected files for debugging.

        Returns:
            Dictionary with file lists and scores
        """
        pid_files = self.find_pid_files()
        scope_files = self.find_scope_files()

        scope_details = []
        for f in scope_files:
            scope_details.append({
                'path': str(f),
                'name': f.name,
                'score': self.score_file_as_scope(f),
            })

        return {
            'pid_files': [f.name for f in pid_files],
            'pid_count': len(pid_files),
            'scope_files': scope_details,
            'scope_count': len(scope_files),
            'upload_dir': str(self.upload_dir.absolute()),
        }


def auto_detect_and_process(upload_dir: str = "backend/uploads") -> Tuple[Optional[Path], str, dict]:
    """
    Main function: Auto-detect files and return paths + scope text.

    Usage:
        pid_path, scope_text, metadata = auto_detect_and_process()
        if pid_path:
            print(f"P&ID: {pid_path}")
        if scope_text:
            print(f"Scope (first 100 chars): {scope_text[:100]}...")
        print(f"Detection metadata: {metadata}")

    Args:
        upload_dir: Path to uploads directory

    Returns:
        Tuple of (pid_path, scope_text, metadata)
    """
    detector = FileDetector(upload_dir)
    pid_path, scope_path, metadata = detector.detect_files()
    scope_text = detector.read_scope_text(scope_path)

    return pid_path, scope_text, metadata


# Example usage script
if __name__ == "__main__":
    import sys
    import json

    # Use default or custom upload directory
    upload_dir = sys.argv[1] if len(sys.argv) > 1 else "backend/uploads"

    detector = FileDetector(upload_dir)
    print(f"\n📁 Scanning directory: {detector.upload_dir.absolute()}\n")

    files_info = detector.list_all_files()

    print(f"Found {files_info['pid_count']} P&ID file(s):")
    for f in files_info['pid_files']:
        print(f"  ✓ {f}")

    print(f"\nFound {files_info['scope_count']} potential scope file(s):")
    for item in files_info['scope_files']:
        print(f"  ✓ {item['name']} (score: {item['score']:.2f})")

    pid, scope, metadata = detector.detect_files()
    print(f"\n✅ Auto-detected:")
    print(f"  P&ID: {pid.name if pid else 'None'}")
    print(f"  Scope: {scope.name if scope else 'None'}")

    if scope:
        scope_text = detector.read_scope_text(scope)
        print(f"\n📄 Scope content (first 300 chars):")
        print(f"  {scope_text[:300]}...")

    print(f"\n📊 Detection metadata:")
    print(json.dumps(metadata, indent=2, default=str))
