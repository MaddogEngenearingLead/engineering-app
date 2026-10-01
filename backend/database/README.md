# PostgreSQL + MongoDB + Neo4j Multi-Database Setup

## Overview

This engineering P&ID platform uses a polyglot database approach:

### PostgreSQL (Relational)
- **Purpose**: Core application data and transactional consistency
- **Tables**: Projects, Equipment, Connections, Maintenance Records, Pipelines, PID Files
- **Advantages**: ACID compliance, complex joins, referential integrity

### MongoDB (Document Database)
- **Purpose**: Storing raw OCR, AI detection results, and processing job metadata
- **Collections**: ocr_results, symbol_detections, processing_jobs, ai_annotations
- **Advantages**: Flexible schema, easy versioning, native JSON storage

### Neo4j (Graph Database)
- **Purpose**: Equipment topology and flow relationships
- **Nodes**: Equipment, Pipelines
- **Relationships**: CONNECTED_TO, FLOWS_TO, CONTAINS
- **Advantages**: Efficient path finding, relationship traversal

## Local Setup (Docker Compose)

See docker-compose.yml for orchestrated setup of all three databases.

## Migration & Schema

PostgreSQL schemas are managed via Alembic migrations.
Neo4j and MongoDB are schema-flexible but documented in their respective schema files.
