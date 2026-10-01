"""Database initialization and utilities."""
from sqlalchemy.orm import Session
from app.models.database import (
    Project,
    Equipment,
    Connection,
    MaintenanceRecord,
    Pipeline,
    PIDFile,
)
from typing import List, Optional


class ProjectRepository:
    @staticmethod
    def create_project(db: Session, name: str, description: Optional[str] = None) -> Project:
        project = Project(name=name, description=description)
        db.add(project)
        db.commit()
        db.refresh(project)
        return project

    @staticmethod
    def get_project(db: Session, project_id: int) -> Optional[Project]:
        return db.query(Project).filter(Project.id == project_id).first()

    @staticmethod
    def list_projects(db: Session) -> List[Project]:
        return db.query(Project).all()


class EquipmentRepository:
    @staticmethod
    def create_equipment(db: Session, project_id: int, tag: str, name: str, equipment_type: str, **kwargs) -> Equipment:
        equipment = Equipment(
            project_id=project_id,
            tag=tag,
            name=name,
            equipment_type=equipment_type,
            **kwargs,
        )
        db.add(equipment)
        db.commit()
        db.refresh(equipment)
        return equipment

    @staticmethod
    def get_equipment_by_tag(db: Session, tag: str) -> Optional[Equipment]:
        return db.query(Equipment).filter(Equipment.tag == tag).first()

    @staticmethod
    def list_equipment_by_project(db: Session, project_id: int) -> List[Equipment]:
        return db.query(Equipment).filter(Equipment.project_id == project_id).all()

    @staticmethod
    def update_equipment(db: Session, equipment_id: int, **kwargs) -> Optional[Equipment]:
        db.query(Equipment).filter(Equipment.id == equipment_id).update(kwargs)
        db.commit()
        return db.query(Equipment).filter(Equipment.id == equipment_id).first()


class ConnectionRepository:
    @staticmethod
    def create_connection(
        db: Session,
        source_equipment_id: int,
        target_equipment_id: int,
        connection_type: str = "pipe",
        flow_direction: Optional[str] = None,
        line_number: Optional[str] = None,
    ) -> Connection:
        connection = Connection(
            source_equipment_id=source_equipment_id,
            target_equipment_id=target_equipment_id,
            connection_type=connection_type,
            flow_direction=flow_direction,
            line_number=line_number,
        )
        db.add(connection)
        db.commit()
        db.refresh(connection)
        return connection

    @staticmethod
    def list_connections_by_equipment(db: Session, equipment_id: int) -> List[Connection]:
        return db.query(Connection).filter(
            (Connection.source_equipment_id == equipment_id) | (Connection.target_equipment_id == equipment_id)
        ).all()
