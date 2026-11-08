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
_WORK_EVIDENCE = re.compile(
    r"\b(?:install\w*|remov\w*|demol\w*|replac\w*|fabricat\w*|provid\w*|furnish\w*|"
    r"relocat\w*|modif\w*|repair\w*|upgrad\w*|connect\w*|test\w*|inspect\w*|"
    r"examin\w*|commission\w*|contractor|shall|must|required|existing|retain\w*|reuse|new work|"
    r"material test|weld map|wps|pqr|excavat\w*|hydrovac|soft dig|one.?call|"
    r"call before|utility|contaminat\w*|roll.?off|scrap|vacuum truck|grout|"
    r"lock.?out|loto|drain.?down|"
    r"concrete|support|coating|paint\w*|radiograph\w*|magnetic particle|"
    r"hydrostatic|pressure test|electrical|instrumentation|housekeep\w*|restore|turnover)\b", re.I)


def _drawing_evidence(pdf_path: Path) -> tuple[str, set[str], list[tuple[int, str]]]:
    """Collect work-related drawing text with PDF page references for AI review."""
    pages = []
    notes = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, 1):
            page_text = page.extract_text() or ""
            if not _WORK_EVIDENCE.search(page_text):
                continue
            lines = [re.sub(r"\s+", " ", line).strip() for line in page_text.splitlines()]
            selected = []
            for index, line in enumerate(lines):
                if not line or not _WORK_EVIDENCE.search(line):
                    continue
                start, end = max(0, index - 1), min(len(lines), index + 2)
                selected.extend(lines[start:end])
            excerpt = " ".join(dict.fromkeys(selected))
            excerpt = excerpt[:3500]
            if excerpt:
                pages.append((page_no, excerpt))
            for line in lines:
                if 12 <= len(line) <= 400 and _WORK_NOTE.search(line):
                    notes.append((page_no, line))
    # Keep context bounded while retaining evidence from the whole drawing set.
    chosen = []
    chosen_pages = set()
    char_count = 0
    for page_no, excerpt in pages:
        block = f"P{page_no}: {excerpt}"
        if char_count + len(block) > 40000:
            continue
        chosen.append(block)
        chosen_pages.add(f"P{page_no}")
        char_count += len(block)
    evidence = "\n".join(chosen) or "(No work-related drawing text was extracted.)"
    return evidence, chosen_pages, notes


def _bom_evidence(materials: list[dict]) -> tuple[str, set[str], dict[str, str]]:
    rows = []
    ids = set()
    labels = {}
    for material in materials:
        tag = str(material.get("tag_id") or "-").strip()
        description = str(material.get("description") or "").strip()
        if not description:
            continue
        origin = material.get("origin")
        page_ref = material.get("page") or material.get("pages") or ""
        if origin in ("drawing_bom", "drawing_bom_ai") and tag != "-":
            source_id = f"{'AI-BOM' if origin == 'drawing_bom_ai' else 'BOM'}-{tag}"
            ids.add(source_id)
            page_text = f", drawing page {page_ref}" if str(page_ref).isdigit() else ""
            row_label = "AI-transcribed BOM" if origin == "drawing_bom_ai" else "BOM"
            labels[source_id] = f"{row_label} item {tag}{page_text}"
        else:
            pages = material.get("pages") or material.get("page") or ""
            source_id = f"P{pages}" if str(pages).isdigit() else "P&ID candidate"
            if source_id.startswith("P") and source_id[1:].isdigit():
                ids.add(source_id)
        quantity = material.get("quantity")
        unit = str(material.get("unit") or "").strip()
        qty_text = f"; quantity: {quantity} {unit}".rstrip() if quantity is not None else ""
        location = (f" | drawing page {page_ref}" if origin in ("drawing_bom", "drawing_bom_ai")
                    and str(page_ref).isdigit() else "")
        rows.append(f"{source_id} | {tag} | {description}{qty_text}{location}")
    return "\n".join(rows) or "(No BOM or material rows were extracted.)", ids, labels


def _format_ai_scope(reply: dict, valid_sources: set[str], source_labels: dict[str, str] | None = None) -> str:
    sections = reply.get("sections")
    if not isinstance(sections, list):
        raise ValueError("AI returned an invalid scope structure.")
    lines = ["Draft Scope of Work (AI-assisted; review and approve before use)."]
    task_count = 0
    for section in sections[:12]:
        if not isinstance(section, dict):
            continue
        title = section.get("title")
        tasks = section.get("tasks")
        if not isinstance(title, str) or not title.strip() or len(title) > 140 or not isinstance(tasks, list):
            continue
        section_lines = []
        for task in tasks[:50]:
            if not isinstance(task, dict):
                continue
            text = task.get("text")
            sources = task.get("sources")
            if not isinstance(text, str) or not text.strip() or len(text) > 800 or not isinstance(sources, list):
                continue
            source_ids = list(dict.fromkeys(source for source in sources
                                           if isinstance(source, str) and source in valid_sources))
            if not source_ids:
                continue
            references = []
            for source in source_ids:
                if source.startswith("AI-BOM-"):
                    references.append((source_labels or {}).get(source, f"AI-transcribed BOM item {source[7:]}"))
                elif source.startswith("BOM-"):
                    references.append((source_labels or {}).get(source, f"BOM item {source[4:]}"))
                else:
                    references.append(f"drawing page {source[1:]}")
            section_lines.append(f"- {text.strip()} [VERIFY] [Sources: {'; '.join(references)}]")
            task_count += 1
        if section_lines:
            lines.extend(["", title.strip(), *section_lines])
    if not task_count:
        raise ValueError("AI returned no tasks with traceable drawing or BOM references.")
    return "\n".join(lines)


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
    from app.services import ai_review

    ai_review.require_provider()
    drawing_evidence, page_sources, notes = _drawing_evidence(pid_path)
    review_pages = set(result.get("demo_pages", []) + result.get("new_work_pages", []))
    if review_pages:
        notes = [(page, note) for page, note in notes if page in review_pages]
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
    text = "\n".join(lines)
    bom_evidence, bom_sources, bom_labels = _bom_evidence(result.get("materials", []))
    ai_draft = ai_review.draft_scope_with_ai(drawing_evidence, bom_evidence, review_index=text)
    text = _format_ai_scope(ai_draft, page_sources | bom_sources, bom_labels)
    draft_info = {"generation_method": "ai",
                  "ai_provider": ai_draft["provider"], "ai_model": ai_draft["model"]}
    draft = {
        "pid_file": str(pid_path.resolve()),
        "pid_sha256": _digest(pid_path),
        "primary_pid_file": str(jm.get_pid_files(job_number)[0].resolve()),
        "text": text,
        "demo_pages": result.get("demo_pages", []),
        "new_work_pages": result.get("new_work_pages", []),
        **draft_info,
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
