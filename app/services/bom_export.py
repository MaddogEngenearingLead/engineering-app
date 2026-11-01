from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT


def export_bom_to_pdf(
    job_id: str,
    source_file: str,
    materials: list[dict],
    scope_of_work: str = "",
    review_notes: list[str] = None,
    output_dir: str = "bom_exports",
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
    
    # Scope of Work
    if scope_of_work:
        elements.append(Paragraph("Scope of Work", heading_style))
        elements.append(Paragraph(scope_of_work, normal_style))
        elements.append(Spacer(1, 0.2*inch))
    
    # Materials Table
    elements.append(Paragraph("Equipment & Materials", heading_style))
    
    # Build materials table
    materials_data = [
        ["Item #", "Tag ID", "Description", "Type", "Qty", "Unit", "Confidence"]
    ]
    
    for material in materials:
        materials_data.append([
            str(material['item_number']),
            material['tag_id'],
            material['description'],
            material['type'].replace('_', ' ').title(),
            str(material['quantity']),
            material['unit'],
            f"{material['confidence']:.0%}",
        ])
    
    materials_table = Table(
        materials_data,
        colWidths=[0.5*inch, 0.8*inch, 2.2*inch, 1.2*inch, 0.4*inch, 0.4*inch, 0.6*inch]
    )
    materials_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#007bff')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'LEFT'),
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
    
    # Review Notes / Items Requiring Attention
    if review_notes:
        elements.append(Paragraph("⚠ Items Requiring Review/Clarification", warning_style))
        for i, note in enumerate(review_notes, 1):
            elements.append(Paragraph(f"• {note}", normal_style))
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
        "detected_assets": detected_assets,
        "materials": materials,
        "total_items": len(materials),
        "review_notes": review_notes,
    }

    file_path.write_text(json.dumps(bom_data, indent=2))
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
        file_path.write_text("")
        return str(file_path)

    with open(file_path, "w", newline="") as f:
        fieldnames = list(dict.fromkeys(k for m in materials for k in m))
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(materials)

    return str(file_path)
