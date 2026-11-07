"""Extractive scope summaries and reviewed, drawing-derived scope drafts."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pdfplumber

from app.job_manager import JobManager


def summarize_scope(text: str) -> list[str]:
    """Extract distinct work and qualification statements without rewriting them."""
    statements = []
    seen = set()
    for line in (text or "").splitlines():
        line = re.sub(r"^\s*(?:[•*-]|\d+[.)])\s*", "", line).strip()
        line = re.sub(r"\s+", " ", line)
        if not line:
            continue
        for statement in re.split(r"(?<=[.!?])\s+(?=[A-Z])", line):
            key = statement.casefold()
            if key not in seen:
                statements.append(statement)
                seen.add(key)
    work_terms = re.compile(
        r"\b(?:install\w*|provid\w*|supply|suppl\w*|furnish\w*|fabricat\w*|"
        r"remov\w*|demol\w*|replac\w*|add\w*|connect\w*|construct\w*|"
        r"repair\w*|modif\w*|relocat\w*|test\w*|inspect\w*|commission\w*|"
        r"shall|must|required?|responsib\w*|include\w*|exclud\w*|except\w*|"
        r"existing|retain\w*|scope|work|contractor|specification\w*|"
        r"subject to|prior to|after|before|unless|only|not)\b", re.I)
    selected = []
    heading = None
    for statement in statements:
        if statement.endswith(":"):
            heading = statement
        elif work_terms.search(statement):
            if heading and heading not in selected:
                selected.append(heading)
            selected.append(statement)
    return selected or statements


def _draft_path(jm: JobManager, job_number: str) -> Path:
    job_dir, _, _ = jm.get_job_dirs(job_number)
    if job_dir is None:
        raise ValueError("Job not found.")
    return job_dir / "scope_draft.json"


def _digest(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


_WORK_NOTE = re.compile(
    r"\b(?:install\w*|remov\w*|demol\w*|replac\w*|fabricat\w*|"
    r"provid\w*|furnish\w*|relocat\w*|modif\w*|repair\w*|"
    r"connect\w*|test\w*|commission\w*|new work)\b", re.I)


def _note_refers_to_item(note: str, material: dict) -> bool:
    """Use explicit identifiers only; never infer work from proximity or material type."""
    tag = str(material.get("tag_id") or "").strip()
    if not tag or tag == "-":
        return False
    if material.get("origin") in ("drawing_bom", "drawing_bom_ai"):
        return bool(re.search(rf"\bITEM\s*(?:NO\.?|#)?\s*{re.escape(tag)}(?!\w)", note, re.I))
    parts = re.fullmatch(r"([A-Za-z]+)[\s-]*(\d+[A-Za-z]?)", tag)
    if not parts:
        return False
    return bool(re.search(rf"(?<![A-Za-z0-9]){re.escape(parts[1])}[\s-]*"
                          rf"{re.escape(parts[2])}(?![A-Za-z0-9])", note, re.I))


def create_scope_draft(jm: JobManager, job_number: str, pid_path: Path, result: dict) -> dict:
    """Save evidence for review, never as an approved scope file."""
    if jm.get_scope_files(job_number):
        raise ValueError("A scope file already exists; it will not be replaced.")
    notes = []
    with pdfplumber.open(pid_path) as pdf:
        pages = sorted(set(result.get("demo_pages", []) + result.get("new_work_pages", [])))
        pages = pages or list(range(1, len(pdf.pages) + 1))
        for page_no in pages:
            for raw in (pdf.pages[page_no - 1].extract_text() or "").splitlines():
                note = re.sub(r"\s+", " ", raw).strip()
                if 12 <= len(note) <= 400 and _WORK_NOTE.search(note):
                    notes.append((page_no, note))
    lines = []
    used_notes = set()
    for material in result.get("materials", []):
        tag = str(material.get("tag_id") or "").strip()
        description = str(material.get("description") or "").strip()
        if not tag and not description:
            continue
        item = " - ".join(part for part in (tag if tag != "-" else "", description) if part)
        location = str(material.get("location") or "").strip()
        quantity, unit = material.get("quantity"), material.get("unit") or ""
        quantity_text = f"; drawing quantity: {quantity} {unit}".rstrip() if quantity is not None else "; quantity unknown"
        responsibility = []
        for key, label in (("supplied_by", "supplied by"), ("installed_by", "installed by")):
            value = str(material.get(key) or "").strip()
            if value and value not in ("-", "--"):
                responsibility.append(f"{label}: {value}")
        responsibility_text = "; " + "; ".join(responsibility) if responsibility else ""
        evidence = [(page, note) for page, note in notes if _note_refers_to_item(note, material)]
        if evidence:
            refs = " | ".join(f"page {page}: {note}" for page, note in evidence)
            used_notes.update(evidence)
            work = f"Drawing instruction(s) to verify: {refs}"
        else:
            work = "Confirm intended work; no item-specific instruction was identified"
            basis = str(material.get("basis") or "").strip()
            if material.get("origin") == "drawing" and basis:
                work += f"; drawing selection evidence: {basis}"
        lines.append(f"- {item}" + (f" ({location})" if location else "")
                     + f"{quantity_text}{responsibility_text}. {work}.")
    for page, note in notes:
        if (page, note) not in used_notes:
            lines.append(f"- Drawing page {page}, possible work note (item association unconfirmed): {note}")
    if not lines:
        lines.append("- No reliable work instructions were extracted. Define the scope from the P&ID.")
    draft = {
        "pid_file": str(pid_path.resolve()),
        "pid_sha256": _digest(pid_path),
        "primary_pid_file": str(jm.get_pid_files(job_number)[0].resolve()),
        "text": "\n".join(lines),
        "demo_pages": result.get("demo_pages", []),
        "new_work_pages": result.get("new_work_pages", []),
    }
    _draft_path(jm, job_number).write_text(json.dumps(draft, indent=2), encoding="utf-8")
    return draft


def load_scope_draft(jm: JobManager, job_number: str) -> dict:
    path = _draft_path(jm, job_number)
    if not path.is_file():
        raise ValueError("No scope draft is awaiting review. Scan the job first.")
    return json.loads(path.read_text(encoding="utf-8"))


def approve_scope_draft(jm: JobManager, job_number: str, text: str) -> Path:
    """Save only explicit user-approved text; refuse stale drafts and existing scopes."""
    text = text.strip()
    if not text:
        raise ValueError("The reviewed scope cannot be empty.")
    draft = load_scope_draft(jm, job_number)
    pid_files = jm.get_pid_files(job_number)
    source = Path(draft["pid_file"])
    _, pid_dir, _ = jm.get_job_dirs(job_number)
    if (not pid_files or str(pid_files[0].resolve()) != draft["primary_pid_file"]
            or source.resolve().parent != pid_dir.resolve() or not source.is_file()
            or _digest(source) != draft["pid_sha256"]):
        raise ValueError("The P&ID changed since the draft was prepared; scan again.")
    if jm.get_scope_files(job_number):
        raise ValueError("A scope file already exists; it will not be replaced.")
    job_dir, _, scope_dir = jm.get_job_dirs(job_number)
    scope_dir.mkdir(parents=True, exist_ok=True)
    path = scope_dir / "reviewed_scope.txt"
    with path.open("x", encoding="utf-8") as f:
        f.write(text + "\n")
    jm._record_path(job_number, job_dir, "scope_file", path.resolve())
    from app.services.job_scan import _store
    _store(jm, job_number, {"bom_status": "scope_approved",
                            "bom_message": "Scope approved; regenerate the BOM."})
    _draft_path(jm, job_number).unlink()
    return path
