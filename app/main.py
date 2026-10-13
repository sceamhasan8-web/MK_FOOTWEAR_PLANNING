import os
import time
import uuid
import logging
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
from app.database import engine, Base
from app.db_migration import verify_and_sync_schema, print_startup_banner
from app.api import (
    auth, admin, buyers, orders, production, calendar, dashboard, exports, audit, departments, diagnostics, settings as settings_api
)

# Configure server logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("erp.main")

# Automatic schema sync and startup validation
migration_results = verify_and_sync_schema(engine, Base)
print_startup_banner(migration_results)


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Generate or capture correlation request ID (e.g. ERP-20261007-a1b2c3)
        today_str = datetime.now().strftime("%Y%m%d")
        short_id = uuid.uuid4().hex[:6].upper()
        req_id = request.headers.get("X-Request-ID") or f"ERP-{today_str}-{short_id}"
        request.state.request_id = req_id

        start_time = time.time()
        try:
            response = await call_next(request)
            duration_ms = round((time.time() - start_time) * 1000, 2)
            response.headers["X-Request-ID"] = req_id
            # Prevent browser caching of web portal static assets during active development
            if request.url.path.endswith((".js", ".html", ".css")) or request.url.path.startswith("/portal"):
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
            # Log requests
            if not request.url.path.startswith("/portal") and not request.url.path.endswith((".css", ".js", ".png", ".ico")):
                logger.info(
                    "[%s] %s %s -> %s (%sms)",
                    req_id, request.method, request.url.path, response.status_code, duration_ms
                )
            return response
        except Exception as exc:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.error("[%s] ERROR processing %s %s: %s", req_id, request.method, request.url.path, exc, exc_info=True)
            return JSONResponse(
                status_code=500,
                headers={"X-Request-ID": req_id},
                content={
                    "detail": f"Internal Server Error: {str(exc)}",
                    "error_code": "INTERNAL_SERVER_ERROR",
                    "request_id": req_id
                }
            )


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=f"{settings.PROJECT_NAME} - Centralized Production Planning, WIP Flow Tracking, Daily Entry, and Delivery Replanning ERP",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Correlation ID Middleware
app.add_middleware(RequestCorrelationMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"]
)

# Include Routers under API_V1_PREFIX
prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=prefix)
app.include_router(admin.router, prefix=prefix)
app.include_router(buyers.router, prefix=prefix)
app.include_router(orders.router, prefix=prefix)
app.include_router(production.router, prefix=prefix)
app.include_router(calendar.router, prefix=prefix)
app.include_router(dashboard.router, prefix=prefix)
app.include_router(exports.router, prefix=prefix)
app.include_router(audit.router, prefix=prefix)
app.include_router(departments.router, prefix=prefix)
app.include_router(diagnostics.router, prefix=prefix)
app.include_router(settings_api.router, prefix=prefix)


@app.get("/health", tags=["Health"])
def health_check(request: Request):
    req_id = getattr(request.state, "request_id", "ERP-HEALTH")
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "database": "connected",
        "request_id": req_id
    }


# Mount web portal static files
web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "web-portal")
if os.path.exists(web_dir):
    app.mount("/portal", StaticFiles(directory=web_dir, html=True), name="portal")
    # Also mount at root so http://localhost:8000/ directly serves index.html, styles.css, app.js
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web_root")
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"message": "MK Footwear Planning API is running. Visit /docs for API documentation."}
