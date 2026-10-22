import logging
import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request

from app.routes import fleet_router
from app.routes.analytics import router as analytics_router
from app.routes.alerts import router as alerts_router
from app.routes.control_tower import router as control_tower_router
from app.routes.corridors import router as corridors_router
from app.routes.load_matching import router as load_matching_router
from app.routes.operations import router as operations_router
from app.routes.organizations import router as organizations_router
from app.routes.recommendation_actions import router as recommendation_actions_router
from app.routes.recommendations import router as recommendations_router
from app.routes.route_plans import router as route_plans_router

logger = logging.getLogger("logistics_api.http")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")

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
app.include_router(recommendation_actions_router)
app.include_router(route_plans_router)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    supplied_id = request.headers.get("X-Request-ID", "")
    request_id = supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else str(uuid4())
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        logger.exception(
            "http_request_failed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
            },
        )
        raise
    finally:
        logger.info(
            "http_request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            },
        )


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
