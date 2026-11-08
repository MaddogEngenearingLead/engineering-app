from __future__ import annotations

import json
import csv
import logging
import re
import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from xml.sax.saxutils import escape

from pypdf import PdfReader

from app.services.scope_work import summarize_scope

logger = logging.getLogger(__name__)


def job_export_id(job_number: str) -> str:
    """Keep legacy names for ordinary job numbers without allowing path separators."""
    return "JOB-" + job_number.replace("/", "-").replace("\\", "-")


@contextmanager
def staged_job_exports(output_dir: str):
    """Keep unfinished job exports isolated from the published generation."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stage = directory / (".bom-stage-" + uuid.uuid4().hex)
    stage.mkdir()
    try:
        yield stage
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def publish_job_exports(job_id: str, stage: Path, paths: dict, output_dir: str, commit=None) -> dict:
    """Verify all formats, then publish a generation and remove matching old exports."""
    stage = stage.resolve()
    directory = Path(output_dir)
    sources = {}
    for key, ext in (("bom_pdf", "pdf"), ("bom_json", "json"), ("bom_csv", "csv")):
        value = paths.get(key)
        if not value:
            raise ValueError(f"Missing {key} export")
        source = Path(value)
        if source.is_symlink() or source.resolve().parent != stage or not source.is_file() or source.suffix != f".{ext}":
            raise ValueError(f"Invalid {key} export")
        sources[key] = source

    with sources["bom_pdf"].open("rb") as f:
        if f.read(5) != b"%PDF-":
            raise ValueError("Invalid BOM PDF")
        f.seek(0)
        if not PdfReader(f, strict=True).pages:
            raise ValueError("Empty BOM PDF")
    with sources["bom_json"].open(encoding="utf-8") as f:
        if not isinstance(json.load(f), dict):
            raise ValueError("Invalid BOM JSON")
    with sources["bom_csv"].open(encoding="utf-8", newline="") as f:
        list(csv.reader(f, strict=True))

    # A unique generation avoids overwriting a previous run within the same second.
    generation = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex
    published = {}
    try:
        for key, source in sources.items():
            target = directory / f"BOM_{job_id}_{generation}{source.suffix}"
            source.replace(target)
            published[key] = str(target.resolve())
        if commit:
            commit(published)
    except Exception:
        for path in published.values():
            Path(path).unlink(missing_ok=True)
        raise

    pattern = re.compile(rf"BOM_{re.escape(job_id)}_\d{{8}}_\d{{6}}(?:_[0-9a-f]{{32}})?\.(?:pdf|json|csv)\Z")
    keep = {Path(p).name for p in published.values()}
    for path in directory.iterdir():
        if path.name not in keep and pattern.fullmatch(path.name) and path.is_file() and not path.is_symlink():
            try:
                path.unlink()
            except OSError:
                logger.warning("Could not remove old BOM export %s", path, exc_info=True)
    return published


def export_bom_to_pdf(
    job_id: str,
    source_file: str,
    materials: list[dict],
    scope_of_work: str = "",
    review_notes: list[str] = None,
    output_dir: str = "bom_exports",
    clarifications: list[str] = None,
) -> str:
    """
    Export BOM to professional PDF file with job ID and timestamp in filename.
    PDF includes scope of work, materials table, review notes, and designations.
    
    Args:
        job_id: Job identifier (e.g., "JOB-001")
        source_file: Original P&ID filename
        materials: List of material dictionaries from generate_bom_from_tags()
        scope_of_work: Description of the scope of work
        review_notes: List of items/notes that need review or clarification
        output_dir: Directory to save the export file
    
    Returns:
        Path to the generated PDF file
    """
    if review_notes is None:
        review_notes = []
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"BOM_{job_id}_{timestamp}.pdf"
    file_path = output_path / filename
    
    # Create PDF document
    doc = SimpleDocTemplate(
        str(file_path),
        pagesize=letter,
        rightMargin=0.5*inch,
        leftMargin=0.5*inch,
        topMargin=0.75*inch,
        bottomMargin=0.75*inch,
    )
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Define styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#007bff'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#007bff'),
        spaceAfter=12,
        spaceBefore=12,
        fontName='Helvetica-Bold',
    )
    normal_style = ParagraphStyle(
        'CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
    )
    warning_style = ParagraphStyle(
        'Warning',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#d32f2f'),
        spaceAfter=6,
        fontName='Helvetica-Bold',
    )
    
    # Title
    elements.append(Paragraph("BILL OF MATERIALS (BOM)", title_style))
    elements.append(Spacer(1, 0.2*inch))
    
    # Job Information
    job_info_data = [
        ["Job ID:", job_id],
        ["Source P&ID:", source_file],
        ["Generated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ["Total Items:", str(len(materials))],
    ]
    
    job_table = Table(job_info_data, colWidths=[1.5*inch, 4.5*inch])
    job_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    elements.append(job_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # Materials Table
    elements.append(Paragraph("Equipment & Materials", heading_style))
    
    # Build materials table
    materials_data = [
        ["#", "Tag ID", "Description", "Type", "Qty", "Unit", "Location", "Conf."]
    ]
    cell = ParagraphStyle('Cell', parent=styles['Normal'], fontSize=8, leading=9.5)
    
    for material in materials:
        materials_data.append([
            str(material.get('item_number', '')),
            Paragraph(str(material.get('tag_id', '')), cell),
            Paragraph(str(material.get('description', '')), cell),
            Paragraph(str(material.get('type', '')).replace('_', ' ').title(), cell),
            str(material.get('quantity') if material.get('quantity') is not None else ''),
            material.get('unit', ''),
            Paragraph(str(material.get('location') or '-'), cell),
            f"{material.get('confidence', 0):.0%}",
        ])
    
    materials_table = Table(
        materials_data,
        colWidths=[0.35*inch, 0.8*inch, 1.9*inch, 0.9*inch, 0.4*inch, 0.4*inch, 1.9*inch, 0.5*inch], repeatRows=1
    )
    materials_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
    ]))
    elements.append(materials_table)
    elements.append(Spacer(1, 0.2*inch))

    # Scope of Work
    if scope_of_work:
        statements = summarize_scope(scope_of_work)
        limit = 12
        elements.append(Paragraph("Scope of Work - Summary", heading_style))
        notice = "Extracted summary; refer to the full scope for all requirements and exclusions."
        if len(statements) > limit:
            notice = (f"Showing {limit} of {len(statements)} extracted statements. "
                      "Refer to the full scope for all requirements and exclusions.")
        elements.append(Paragraph(notice, normal_style))
        for statement in statements[:limit]:
            elements.append(Paragraph(escape(statement), normal_style, bulletText="\u2022"))
        elements.append(Spacer(1, 0.2*inch))
    
    # Review Notes / Items Requiring Attention
    if review_notes:
        elements.append(Paragraph("⚠ Items Requiring Review/Clarification", warning_style))
        for i, note in enumerate(review_notes, 1):
            elements.append(Paragraph(f"• {escape(note)}", normal_style))
        elements.append(Spacer(1, 0.2*inch))
    
    if clarifications:
        elements.append(Paragraph("Clarifications", heading_style))
        for note in clarifications:
            elements.append(Paragraph(f"• {escape(note)}", normal_style))
        elements.append(Spacer(1, 0.2*inch))

    # Footer
    elements.append(Spacer(1, 0.1*inch))
    footer_text = "This Bill of Materials was automatically generated from P&ID scan data. " \
                  "All items should be reviewed for accuracy before procurement."
    elements.append(Paragraph(footer_text, ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        alignment=TA_CENTER,
    )))
    
    # Build PDF
    doc.build(elements)
    
    return str(file_path)


def export_bom_to_json(
    job_id: str,
    source_file: str,
    materials: list[dict],
    scope_of_work: str = "",
    review_notes: list[str] = None,
    detected_assets: list[dict] = None,
    output_dir: str = "bom_exports",
    clarifications: list[str] = None,
) -> str:
    """
    Export BOM to JSON file for programmatic access and archival.

    Args:
        job_id: Job identifier (e.g., "JOB-001")
        source_file: Original P&ID filename
        materials: List of material dictionaries
        scope_of_work: Description of the scope of work
        review_notes: List of items/notes that need review
        detected_assets: List of detected equipment tags
        output_dir: Directory to save the export file

    Returns:
        Path to the generated JSON file
    """
    if review_notes is None:
        review_notes = []
    if detected_assets is None:
        detected_assets = []

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"BOM_{job_id}_{timestamp}.json"
    file_path = output_path / filename

    bom_data = {
        "job_id": job_id,
        "source_file": source_file,
        "generated_at": datetime.now().isoformat(),
        "scope_of_work": scope_of_work,
        "scope_summary": summarize_scope(scope_of_work),
        "detected_assets": detected_assets,
        "materials": materials,
        "total_items": len(materials),
        "review_notes": review_notes,
        "clarifications": clarifications or [],
    }

    file_path.write_text(json.dumps(bom_data, indent=2), encoding="utf-8")
    return str(file_path)


def export_bom_to_csv(
    job_id: str,
    materials: list[dict],
    output_dir: str = "bom_exports",
) -> str:
    """
    Export BOM materials to CSV file for spreadsheet import.

    Args:
        job_id: Job identifier (e.g., "JOB-001")
        materials: List of material dictionaries
        output_dir: Directory to save the export file

    Returns:
        Path to the generated CSV file
    """
    import csv

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"BOM_{job_id}_{timestamp}.csv"
    file_path = output_path / filename

    if not materials:
        file_path.write_text("", encoding="utf-8")
        return str(file_path)

    with open(file_path, "w", encoding="utf-8", newline="") as f:
        fieldnames = list(dict.fromkeys(k for m in materials for k in m))
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(materials)

    return str(file_path)


def export_all(job_id: str, source_file: str, materials: list[dict], scope_of_work: str,
               review_notes: list[str], detected_assets: list[dict], output_dir: str,
               clarifications: list[str] | None = None) -> dict:
    """Write the PDF, JSON and CSV BOM; returns their paths."""
    return {
        "bom_pdf": export_bom_to_pdf(job_id, source_file, materials, scope_of_work, review_notes,
                                     output_dir, clarifications=clarifications),
        "bom_json": export_bom_to_json(job_id, source_file, materials, scope_of_work, review_notes,
                                       detected_assets, output_dir, clarifications=clarifications),
        "bom_csv": export_bom_to_csv(job_id, materials, output_dir),
    }
