"""Database schema migrations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("status", sa.String(50), default="active"),
        sa.Column("created_at", sa.DateTime, default=func.now()),
        sa.Column("updated_at", sa.DateTime, default=func.now(), onupdate=func.now()),
    )

    op.create_table(
        "pid_files",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(10)),
        sa.Column("file_size_bytes", sa.Integer),
        sa.Column("processing_status", sa.String(50), default="pending"),
        sa.Column("job_id", sa.String(100)),
        sa.Column("uploaded_at", sa.DateTime, default=func.now()),
        sa.Column("processed_at", sa.DateTime),
    )

    op.create_table(
        "equipment",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("tag", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("equipment_type", sa.String(100)),
        sa.Column("manufacturer", sa.String(255)),
        sa.Column("model", sa.String(255)),
        sa.Column("location", sa.String(255)),
        sa.Column("status", sa.String(50), default="operational"),
        sa.Column("pressure_rating", sa.Float),
        sa.Column("temperature_rating", sa.Float),
        sa.Column("material", sa.String(255)),
        sa.Column("installation_date", sa.DateTime),
        sa.Column("confidence_score", sa.Float, default=0.0),
        sa.Column("bbox_x", sa.Float),
        sa.Column("bbox_y", sa.Float),
        sa.Column("bbox_width", sa.Float),
        sa.Column("bbox_height", sa.Float),
        sa.Column("created_at", sa.DateTime, default=func.now()),
        sa.Column("updated_at", sa.DateTime, default=func.now(), onupdate=func.now()),
    )

    op.create_table(
        "connections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_equipment_id", sa.Integer, sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("target_equipment_id", sa.Integer, sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("connection_type", sa.String(50), default="pipe"),
        sa.Column("flow_direction", sa.String(20)),
        sa.Column("line_number", sa.String(50)),
    )

    op.create_table(
        "maintenance_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("equipment_id", sa.Integer, sa.ForeignKey("equipment.id"), nullable=False),
        sa.Column("maintenance_type", sa.String(100)),
        sa.Column("description", sa.String(1000)),
        sa.Column("performed_at", sa.DateTime),
        sa.Column("next_due_date", sa.DateTime),
        sa.Column("created_at", sa.DateTime, default=func.now()),
    )

    op.create_table(
        "pipelines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("project_id", sa.Integer, sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1000)),
        sa.Column("line_number", sa.String(50)),
        sa.Column("fluid", sa.String(100)),
        sa.Column("pressure_rating", sa.Float),
        sa.Column("temperature_rating", sa.Float),
        sa.Column("created_at", sa.DateTime, default=func.now()),
    )


def downgrade():
    op.drop_table("pipelines")
    op.drop_table("maintenance_records")
    op.drop_table("connections")
    op.drop_table("equipment")
    op.drop_table("pid_files")
    op.drop_table("projects")
