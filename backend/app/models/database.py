from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database.postgres import Base


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(String(1000))
    status = Column(String(50), default="active")  # active, archived, processing
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    pid_files = relationship("PIDFile", back_populates="project")
    equipment = relationship("Equipment", back_populates="project")
    pipelines = relationship("Pipeline", back_populates="project")


class PIDFile(Base):
    __tablename__ = "pid_files"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(10))  # pdf, png, jpg, svg
    file_size_bytes = Column(Integer)
    processing_status = Column(String(50), default="pending")  # pending, processing, completed, failed
    job_id = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime)

    # Relationship
    project = relationship("Project", back_populates="pid_files")


class Equipment(Base):
    __tablename__ = "equipment"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    tag = Column(String(50), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    equipment_type = Column(String(100))  # pump, valve, vessel, instrument, compressor, etc.
    manufacturer = Column(String(255))
    model = Column(String(255))
    location = Column(String(255))
    status = Column(String(50), default="operational")  # operational, warning, offline
    pressure_rating = Column(Float)  # PSI
    temperature_rating = Column(Float)  # Fahrenheit
    material = Column(String(255))
    installation_date = Column(DateTime)
    confidence_score = Column(Float, default=0.0)  # AI detection confidence
    bbox_x = Column(Float)  # Bounding box in original image
    bbox_y = Column(Float)
    bbox_width = Column(Float)
    bbox_height = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="equipment")
    connections_from = relationship("Connection", foreign_keys="Connection.source_equipment_id", back_populates="source")
    connections_to = relationship("Connection", foreign_keys="Connection.target_equipment_id", back_populates="target")
    maintenance_records = relationship("MaintenanceRecord", back_populates="equipment")


class Connection(Base):
    __tablename__ = "connections"

    id = Column(Integer, primary_key=True)
    source_equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    target_equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    connection_type = Column(String(50), default="pipe")  # pipe, signal, electrical, etc.
    flow_direction = Column(String(20))  # forward, backward, bidirectional
    line_number = Column(String(50))  # P&ID line numbering

    # Relationships
    source = relationship("Equipment", foreign_keys=[source_equipment_id], back_populates="connections_from")
    target = relationship("Equipment", foreign_keys=[target_equipment_id], back_populates="connections_to")


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id = Column(Integer, primary_key=True)
    equipment_id = Column(Integer, ForeignKey("equipment.id"), nullable=False)
    maintenance_type = Column(String(100))  # preventive, corrective, inspection
    description = Column(String(1000))
    performed_at = Column(DateTime)
    next_due_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    equipment = relationship("Equipment", back_populates="maintenance_records")


class Pipeline(Base):
    __tablename__ = "pipelines"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(1000))
    line_number = Column(String(50))
    fluid = Column(String(100))  # water, steam, gas, oil, etc.
    pressure_rating = Column(Float)
    temperature_rating = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship
    project = relationship("Project", back_populates="pipelines")
