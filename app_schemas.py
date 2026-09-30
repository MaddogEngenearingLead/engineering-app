from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Token(BaseModel):
    access_token: str
    token_type: str

class UserProfile(BaseModel):
    username: str
    full_name: str

    class Config:
        from_attributes = True

class MaterialItem(BaseModel):
    associated_tag: str
    item_name: str
    quantity: int
    specifications: str

class TaskItem(BaseModel):
    id: str
    tag: str
    equipment_type: str
    action_required: str
    steps: List[str]

class AnalysisOutput(BaseModel):
    tasks: List[TaskItem]
    materials: List[MaterialItem]

class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    action: str # Handled dynamically below
    blueprint_name: Optional[str]
    index_name: Optional[str]
    sow_name: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True
