from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["engineering"])

@router.get("/health")
def health_check():
    return {"status": "ok", "service": "engineering-app"}

@router.get("/pipeline")
def get_pipeline_summary():
    return {
        "asset_count": 0,
        "status": "initialized",
        "message": "Pipeline monitoring dashboard is ready for configuration."
    }
