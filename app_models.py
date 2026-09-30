from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String, nullable=False) # e.g., "LOGIN", "ANALYZE_FILES", "EXPORT_BOM"
    blueprint_name = Column(String, nullable=True)
    index_name = Column(String, nullable=True)
    sow_name = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
