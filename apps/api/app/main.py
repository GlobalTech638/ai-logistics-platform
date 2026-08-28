from fastapi import FastAPI

from app.routes import fleet_router
from app.routes.analytics import router as analytics_router

app = FastAPI(
    title="AI Logistics API",
    version="0.1.0",
    description="Fleet cost intelligence and logistics operations API.",
)

app.include_router(fleet_router)
app.include_router(analytics_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "logistics-api"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "AI Logistics API",
        "version": "0.1.0",
        "status": "development",
    }
