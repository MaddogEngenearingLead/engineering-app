from pydantic import BaseModel, Field
from typing import Optional


class EquipmentAsset(BaseModel):
    id: str = Field(..., description="Unique asset identifier")
    name: str = Field(..., description="Asset name")
    type: str = Field(..., description="Asset type, e.g. pump, valve, vessel")
    status: str = Field(default="unknown", description="Current operating status")
    location: Optional[str] = Field(default=None, description="Physical or logical location")


class PipelineModel(BaseModel):
    id: str = Field(..., description="Pipeline identifier")
    name: str = Field(..., description="Pipeline name")
    description: Optional[str] = Field(default=None, description="Pipeline description")
    assets: list[EquipmentAsset] = Field(default_factory=list)
