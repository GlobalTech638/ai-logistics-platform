from fastapi import FastAPI

from app.routes import fleet_router
from app.routes.analytics import router as analytics_router
from app.routes.alerts import router as alerts_router
from app.routes.control_tower import router as control_tower_router
from app.routes.corridors import router as corridors_router
from app.routes.load_matching import router as load_matching_router
from app.routes.operations import router as operations_router
from app.routes.organizations import router as organizations_router
from app.routes.recommendations import router as recommendations_router

app = FastAPI(
    title="Pan-African Logistics AI Platform",
    version="0.1.0",
    description="AI-powered operational intelligence for African logistics companies.",
)

app.include_router(fleet_router)
app.include_router(analytics_router)
app.include_router(organizations_router)
app.include_router(operations_router)
app.include_router(alerts_router)
app.include_router(control_tower_router)
app.include_router(load_matching_router)
app.include_router(corridors_router)
app.include_router(recommendations_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "logistics-api", "version": app.version}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Pan-African Logistics AI Platform",
        "version": app.version,
        "status": "development",
    }
