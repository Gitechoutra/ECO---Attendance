import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.api.router import api_router
from app.core.config import settings
from app.core.ratelimit import limiter
from app.db.session import SessionLocal, engine

log = logging.getLogger("echoutra")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.bootstrap import seed_reference_data

    try:
        with SessionLocal() as db:
            seed_reference_data(db)
    except OperationalError as exc:
        log.error("Database unavailable at startup: %s", exc.orig)
    scheduler = None
    if settings.SCHEDULER_ENABLED and settings.ENVIRONMENT != "test":
        from app.jobs.scheduler import start_scheduler

        scheduler = start_scheduler()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="ECHOUTRA ONE API",
    description="Company management platform for ECHOUTRA IT SOLUTIONS.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.state.limiter = limiter

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse({"detail": "Too many requests. Please slow down and try again shortly."}, status_code=429)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = []
    for e in exc.errors():
        loc = [str(x) for x in e.get("loc", []) if x not in ("body", "query", "path")]
        msg = e.get("msg", "Invalid value").removeprefix("Value error, ")
        errors.append({"field": ".".join(loc), "message": msg})
    first = errors[0] if errors else {"field": "", "message": "Invalid request"}
    detail = f"{first['field'].replace('_', ' ').capitalize()}: {first['message']}" if first["field"] else first["message"]
    return JSONResponse({"detail": detail, "errors": errors}, status_code=422)


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError):
    log.warning("Integrity error: %s", exc.orig)
    msg = "This record conflicts with existing data (duplicate or invalid reference)."
    if "Duplicate entry" in str(exc.orig):
        msg = "A record with these details already exists."
    elif "foreign key constraint fails" in str(exc.orig):
        msg = "This record is referenced by other data or refers to a missing record."
    return JSONResponse({"detail": msg}, status_code=409)


@app.exception_handler(OperationalError)
async def db_down(request: Request, exc: OperationalError):
    log.error("Database error: %s", exc.orig)
    return JSONResponse({"detail": "The database is temporarily unavailable. Please try again."}, status_code=503)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "An unexpected error occurred. The issue has been logged."}, status_code=500)


@app.get("/api/health", tags=["System"])
def health():
    db_ok = True
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "app": settings.APP_NAME}


app.include_router(api_router, prefix=settings.API_PREFIX)
