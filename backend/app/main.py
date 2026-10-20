import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api import routes_admin, routes_admin_catalog, routes_auth, routes_bot, routes_imports, routes_media, routes_rights, routes_worker, routes_catalog, routes_titles
from app.core.config import get_settings
from app.core.db import Base, engine
from app.core.errors import install_error_handlers
import app.models  # noqa: F401

@asynccontextmanager
async def lifespan(_):
    # Development convenience only. Production must use Alembic migrations (pending).
    if get_settings().app_env == "development":
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Shofly API", version="0.1.0", openapi_url="/openapi.json", lifespan=lifespan)
install_error_handlers(app)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(message)s")
_log = logging.getLogger("shofly.http")
_RID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


@app.middleware("http")
async def request_context(request, call_next):
    """Request id in/out + one JSON log line per request. Query strings, headers and bodies are never logged."""
    h = request.headers.get("x-request-id", "")
    rid = h if _RID.match(h) else f"req_{uuid.uuid4().hex[:12]}"
    request.state.request_id = rid
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    _log.info(json.dumps({"request_id": rid, "method": request.method, "path": request.url.path,
                          "status": response.status_code, "ms": round((time.perf_counter() - t0) * 1000, 1)}))
    return response
if get_settings().cors_list:  # Mini App / Admin origins only; Bearer tokens, so no cookies/credentials
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_list, allow_credentials=False,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])
app.include_router(routes_auth.router, prefix="/api/v1")
app.include_router(routes_catalog.router, prefix="/api/v1")
app.include_router(routes_titles.router, prefix="/api/v1")
app.include_router(routes_admin.router, prefix="/api/v1")
app.include_router(routes_bot.router, prefix="/api/v1")
for _r in (routes_admin_catalog, routes_imports, routes_media, routes_rights, routes_worker):
    app.include_router(_r.router, prefix="/api/v1")


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready():
    from sqlalchemy import text
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    return {"status": "ready"}
