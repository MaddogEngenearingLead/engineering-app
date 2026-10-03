from __future__ import annotations

import json
import csv
from pathlib import Path
from datetime import datetime


def export_bom_to_json(job_id: str, materials: list[dict], output_dir: str = "bom_exports") -> str:
    """
    Export BOM to JSON file with job ID in filename.
    
    Args:
        job_id: Job identifier (e.g., "job-9a1edce8")
        materials: List of material dictionaries from generate_bom_from_tags()
        output_dir: Directory to save the export file
    
    Returns:
        Path to the generated file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"BOM_{job_id}_{timestamp}.json"
    file_path = output_path / filename
    
    bom_data = {
        "job_id": job_id,
        "generated_at": datetime.now().isoformat(),
        "total_items": len(materials),
        "materials": materials,
    }
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(bom_data, f, indent=2)
    
    return str(file_path)


def export_bom_to_csv(job_id: str, materials: list[dict], output_dir: str = "bom_exports") -> str:
    """
    Export BOM to CSV file with job ID in filename.
    
    Args:
        job_id: Job identifier (e.g., "job-9a1edce8")
        materials: List of material dictionaries from generate_bom_from_tags()
        output_dir: Directory to save the export file
    
    Returns:
        Path to the generated file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"BOM_{job_id}_{timestamp}.csv"
    file_path = output_path / filename
    
    if not materials:
        # Write empty CSV with headers only
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Item Number", "Tag ID", "Description", "Type", "Quantity", "Unit", "Confidence"])
        return str(file_path)
    
    # Extract fieldnames from first material
    fieldnames = ["item_number", "tag_id", "description", "type", "quantity", "unit", "confidence"]
    
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for material in materials:
            writer.writerow(material)
    
    return str(file_path)


def export_bom_to_html(job_id: str, source_file: str, materials: list[dict], output_dir: str = "bom_exports") -> str:
    """
    Export BOM to HTML file with job ID in filename.
    
    Args:
        job_id: Job identifier (e.g., "job-9a1edce8")
        source_file: Original P&ID filename
        materials: List of material dictionaries from generate_bom_from_tags()
        output_dir: Directory to save the export file
    
    Returns:
        Path to the generated file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"BOM_{job_id}_{timestamp}.html"
    file_path = output_path / filename
    
    # Generate table rows
    table_rows = ""
    for material in materials:
        table_rows += f"""    <tr>
      <td>{material['item_number']}</td>
      <td>{material['tag_id']}</td>
      <td>{material['description']}</td>
      <td>{material['type']}</td>
      <td>{material['quantity']}</td>
      <td>{material['unit']}</td>
      <td>{material['confidence']:.2f}</td>
    </tr>
"""
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BOM Export - {job_id}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }}
        .metadata {{
            margin-bottom: 20px;
            padding: 10px;
            background-color: #f9f9f9;
            border-left: 4px solid #007bff;
            border-radius: 4px;
        }}
        .metadata p {{
            margin: 5px 0;
            color: #666;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        th {{
            background-color: #007bff;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background-color: #f9f9f9;
        }}
        .total {{
            font-weight: bold;
            background-color: #e9ecef;
        }}
        .footer {{
            margin-top: 30px;
            text-align: center;
            color: #999;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Bill of Materials (BOM)</h1>
        <div class="metadata">
            <p><strong>Job ID:</strong> {job_id}</p>
            <p><strong>Source File:</strong> {source_file}</p>
            <p><strong>Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
            <p><strong>Total Items:</strong> {len(materials)}</p>
        </div>
        <table>
            <thead>
                <tr>
                    <th>Item #</th>
                    <th>Tag ID</th>
                    <th>Description</th>
                    <th>Type</th>
                    <th>Quantity</th>
                    <th>Unit</th>
                    <th>Confidence</th>
                </tr>
            </thead>
            <tbody>
{table_rows}            </tbody>
        </table>
        <div class="footer">
            <p>This BOM was automatically generated from P&ID scan data.</p>
        </div>
    </div>
</body>
</html>"""
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return str(file_path)
