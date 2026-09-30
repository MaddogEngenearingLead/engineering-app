import io
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import pypdf
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from .database import engine, Base, get_db
from .models import User, AuditLog
from .schemas import Token, AnalysisOutput, MaterialItem, UserProfile
from .auth import verify_password, get_password_hash, create_access_token, get_current_user

# Create database tables automatically
Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Seed sample user into database if not exists
@app.on_event("startup")
def seed_user():
    db = next(get_db())
    try:
        user = db.query(User).filter(User.username == "engineer@company.com").first()
        if not user:
            new_user = User(
                username="engineer@company.com",
                full_name="Project Engineer",
                hashed_password=get_password_hash("password123")
            )
            db.add(new_user)
            db.commit()
    finally:
        db.close()

def extract_text_from_file(upload_file: UploadFile) -> str:
    filename = upload_file.filename.lower()
    content = upload_file.file.read()
    upload_file.file.seek(0) # reset stream
    
    if filename.endswith('.pdf'):
        pdf_reader = pypdf.PdfReader(io.BytesIO(content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text
    elif filename.endswith(('.xlsx', '.xls')):
        df = pd.read_excel(io.BytesIO(content))
        return df.to_string()
    return content.decode('utf-8', errors='ignore')

@app.post("/api/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    # Log login action
    log = AuditLog(user_id=user.id, action="LOGIN")
    db.add(log)
    db.commit()

    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/api/analyze", response_model=AnalysisOutput)
async def analyze_documents(
    blueprint: Optional[UploadFile] = File(None),
    index_doc: UploadFile = File(...),
    sow_doc: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Extract text context layers
        index_text = extract_text_from_file(index_doc)
        sow_text = extract_text_from_file(sow_doc)
        
        # Write record tracking details directly into AuditLog database table
        log = AuditLog(
            user_id=current_user.id,
            action="ANALYZE_FILES",
            blueprint_name=blueprint.filename if blueprint else None,
            index_name=index_doc.filename,
            sow_name=sow_doc.filename
        )
        db.add(log)
        db.commit()

        # Simulated parsed pipeline structural output payload
        return {
            "tasks": [
                {
                    "id": "T-101",
                    "tag": "VLV-204",
                    "equipment_type": "3-Inch Gate Valve",
                    "action_required": "Replace internal gate wedge packing.",
                    "steps": ["Lockout-tagout line", "Bleed line pressure", "Replace packing rings"]
                }
            ],
            "materials": [
                {
                    "associated_tag": "VLV-204",
                    "item_name": "Teflon V-Ring Packing Set",
                    "quantity": 1,
                    "specifications": "Class 300 High-Temperature Variant"
                }
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/export-bom")
async def export_bom(
    materials: List[MaterialItem], 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Log export transaction
    log = AuditLog(user_id=current_user.id, action="EXPORT_BOM")
    db.add(log)
    db.commit()

    wb = Workbook()
    ws = wb.active
    ws.title = "BOM Export"
    ws.views.sheetView.showGridLines = True

    headers = ["Associated Tag", "Item Name / Material", "Quantity", "Specifications"]
    ws.append(headers)
    
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for mat in materials:
        ws.append([mat.associated_tag, mat.item_name, mat.quantity, mat.specifications])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col.column_letter].width = max(max_len + 3, 12)

    file_stream = io.BytesIO()
    wb.save(file_stream)
    file_stream.seek(0)

    return StreamingResponse(
        file_stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=bom.xlsx"}
    )
