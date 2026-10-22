import logging
import re
import time
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.db.database import get_connection

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

# Process-local metrics; aggregate across workers in external monitoring.
_metrics_lock = Lock()
_request_metrics: dict[tuple[str, str, str], dict[str, float]] = {}

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
        duration_seconds = time.perf_counter() - started
        route = request.scope.get("route")
        route_template = getattr(route, "path", None) or "unmatched"
        metric_key = (request.method, route_template, f"{status_code // 100}xx")
        with _metrics_lock:
            metric = _request_metrics.setdefault(metric_key, {"count": 0.0, "duration_seconds": 0.0})
            metric["count"] += 1
            metric["duration_seconds"] += duration_seconds
        logger.info(
            "http_request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": round(duration_seconds * 1000, 2),
            },
        )


@app.get("/metrics", tags=["system"], include_in_schema=False)
def metrics() -> PlainTextResponse:
    """Expose low-cardinality Prometheus metrics for this API process."""
    with _metrics_lock:
        snapshot = [(key, values.copy()) for key, values in _request_metrics.items()]
    lines = [
        "# HELP logistics_http_requests_total Completed HTTP requests by method, route template, and status class.",
        "# TYPE logistics_http_requests_total counter",
    ]
    for (method, route, status_class), values in sorted(snapshot):
        labels = 'method="' + method + '",route="' + route + '",status_class="' + status_class + '"'
        lines.append('logistics_http_requests_total{' + labels + '} ' + str(int(values["count"])))
    lines.extend([
        "# HELP logistics_http_request_duration_seconds_sum Total observed HTTP request duration in seconds.",
        "# TYPE logistics_http_request_duration_seconds_sum counter",
    ])
    for (method, route, status_class), values in sorted(snapshot):
        labels = 'method="' + method + '",route="' + route + '",status_class="' + status_class + '"'
        lines.append('logistics_http_request_duration_seconds_sum{' + labels + '} ' + format(values["duration_seconds"], ".6f"))
    lines.extend([
        "# HELP logistics_http_request_duration_seconds_count Number of HTTP request duration observations.",
        "# TYPE logistics_http_request_duration_seconds_count counter",
    ])
    for (method, route, status_class), values in sorted(snapshot):
        labels = 'method="' + method + '",route="' + route + '",status_class="' + status_class + '"'
        lines.append('logistics_http_request_duration_seconds_count{' + labels + '} ' + str(int(values["count"])))
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "logistics-api", "version": app.version}


@app.get("/ready", tags=["system"])
def readiness():
    """Report whether the API can reach its required PostgreSQL database."""
    try:
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
    except Exception:
        logger.exception("readiness_check_failed")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "dependency": "database"},
        )

    return {"status": "ready", "database": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": "Pan-African Logistics AI Platform",
        "version": app.version,
        "status": "development",
    }
