from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from app.config import settings
from app.database import create_tables
from app.elasticsearch_service import ensure_index
from app.routers.auth import router as auth_router
from app.routers.doctors import router as doctors_router
from app.routers.appointments import router as appointments_router
from app.routers.misc import notif_router, admin_router


# ─────────────────────────────────────────────
#  Lifespan
# ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────
    try:
        await create_tables()
        print("✅  Database tables ready")
    except Exception as e:
        print(f"❌  Database connection failed: {e}")
        print("    Check DATABASE_URL in your .env file")
        raise  # DB is required — stop if it fails

    try:
        await ensure_index()   # ES is optional — never raises
    except Exception as e:
        print(f"⚠️   Elasticsearch setup skipped: {e}")

    yield

    # ── Shutdown ─────────────────────────────
    print("👋  DoctorFinder API shutting down")


# ─────────────────────────────────────────────
#  App
# ─────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## DoctorFinder API

A high-performance doctor search & appointment booking platform.

### Key Features
- ⚡ **Ultra-fast search** via Elasticsearch (with PostgreSQL fallback)
- 🔒 **JWT Authentication** — access & refresh tokens
- 📅 **Smart slot management** — auto-generate slots from weekly schedule
- 🌍 **Geo-based search** — lat/lng + radius
- 🗑️ **Redis caching** — sub-millisecond repeat queries
- 💊 **Full appointment lifecycle** — book → confirm → complete → review

### Roles
| Role    | Capabilities                                   |
|---------|------------------------------------------------|
| patient | Search, book, cancel, review                   |
| doctor  | Manage profile / slots, confirm, prescription  |
| admin   | Verify doctors, view stats                     |
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ─── Exception Handlers ──────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        errors.append({
            "field":   " → ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type":    error["type"],
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": errors},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# ─── Routers ─────────────────────────────────────────────────────────────────

PREFIX = "/api/v1"

app.include_router(auth_router,         prefix=PREFIX)
app.include_router(doctors_router,      prefix=PREFIX)
app.include_router(appointments_router, prefix=PREFIX)
app.include_router(notif_router,        prefix=PREFIX)
app.include_router(admin_router,        prefix=PREFIX)


# ─── Health / Root ───────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME}",
        "docs":    "/docs",
        "version": settings.APP_VERSION,
    }
