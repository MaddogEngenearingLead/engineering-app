from fastapi import FastAPI
from app.api.routes import router

app = FastAPI(
    title="Engineering App",
    description="P&ID dashboard and pipeline engineering API",
    version="0.1.0",
)

app.include_router(router)

@app.get("/")
def read_root():
    return {"message": "Engineering App API is running"}
