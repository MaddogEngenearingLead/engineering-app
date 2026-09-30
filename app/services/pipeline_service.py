from app.models.pipeline import PipelineModel


def create_default_pipeline() -> PipelineModel:
    return PipelineModel(
        id="pipe-001",
        name="Primary Process Line",
        description="Default pipeline model for initial project setup.",
        assets=[],
    )


def get_pipeline_status(pipeline: PipelineModel) -> dict:
    return {
        "pipeline_id": pipeline.id,
        "pipeline_name": pipeline.name,
        "asset_count": len(pipeline.assets),
        "status": "initialized",
    }
