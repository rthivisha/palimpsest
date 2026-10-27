"""FastAPI Application Entry Point for PALIMPSEST.

Architecture:
- Single uvicorn worker binding strictly to 127.0.0.1.
- Middleware:
  1. Host-header check middleware: Allows only localhost, 127.0.0.1, and testserver.
  2. CORS middleware: Restricted strictly to local dev origins.
- Lifespan management:
  Starts the telemetry background writer thread on startup, cleanly drains and stops on shutdown.
"""
from contextlib import asynccontextmanager
from typing import Set

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.api.routes_history import router as history_router
from backend.app.api.routes_meta import router as meta_router
from backend.app.api.routes_run import router as run_router
from backend.app.config import settings
from backend.app.telemetry.db import telemetry_db

# Allowed hostname whitelist (port is stripped prior to matching)
ALLOWED_HOSTNAMES: Set[str] = {"localhost", "127.0.0.1", "testserver"}


class HostHeaderValidationMiddleware(BaseHTTPMiddleware):
    """Protects against DNS rebinding and malicious Host header spoofing.

    Allows requests only when the Host header resolves to localhost, 127.0.0.1,
    or testserver (used by Starlette / pytest TestClient).
    Works seamlessly with the Vite dev proxy.
    """

    async def dispatch(self, request: Request, call_next):
        host_header = request.headers.get("host")
        if host_header:
            hostname = host_header.split(":")[0].strip().lower()
            if hostname not in ALLOWED_HOSTNAMES:
                return Response(
                    content=f"Bad Request: Disallowed Host '{host_header}'",
                    status_code=400,
                    media_type="text/plain",
                )
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI application."""
    # 1. Initialize and start telemetry database writer thread
    telemetry_db.init_db()
    telemetry_db.start_writer()
    try:
        yield
    finally:
        # 2. Flush and cleanly stop telemetry writer thread on shutdown
        telemetry_db.stop_writer(wait=True)


app = FastAPI(
    title="PALIMPSEST",
    version="0.1.0",
    description="Local Neurosymbolic MBA Expression De-obfuscator (CEGIS + Z3 64-bit QF_BV)",
    lifespan=lifespan,
)

# 1. Host header validation middleware
app.add_middleware(HostHeaderValidationMiddleware)

# 2. CORS middleware (Localhost only)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# 3. Mount API Routers
app.include_router(run_router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(meta_router, prefix="/api")
