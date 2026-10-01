from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, List


class EquipmentBase(BaseModel):
    tag: str
    name: str
    equipment_type: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    location: Optional[str] = None
    status: str = "operational"
    pressure_rating: Optional[float] = None
    temperature_rating: Optional[float] = None
    material: Optional[str] = None
    confidence_score: float = 0.0


class EquipmentCreate(EquipmentBase):
    project_id: int


class EquipmentUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    confidence_score: Optional[float] = None


class Equipment(EquipmentBase):
    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConnectionBase(BaseModel):
    source_equipment_id: int
    target_equipment_id: int
    connection_type: str = "pipe"
    flow_direction: Optional[str] = None


class ConnectionCreate(ConnectionBase):
    pass


class Connection(ConnectionBase):
    id: int

    class Config:
        from_attributes = True


class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class Project(ProjectBase):
    id: int
    status: str
    created_at: datetime
    updated_at: datetime
    equipment: List[Equipment] = []

    class Config:
        from_attributes = True


class BOMItem(BaseModel):
    item_number: int
    tag: str
    name: str
    equipment_type: str
    quantity: int = 1
    unit: str = "ea"
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    unit_cost: float = 0.0
    total_cost: float = 0.0


class BOMResponse(BaseModel):
    project_id: int
    total_items: int
    estimated_total_cost: float
    materials: List[BOMItem]
