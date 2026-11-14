"""TradeOps Reconciler API.

Run: uv run uvicorn app.main:app --port 8000

The API never calls the custodian PATCH. It reads systems for evidence, records approvals and
execution requests, and exposes demo controls; the workflow worker performs the mutation.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import router as auth_router
from app.errors import ApiError, api_error_handler, simulator_error_handler
from app.routes import cases, demo, health, sources
from app.services.simulator_clients import SimulatorError

app = FastAPI(
    title="TradeOps Reconciler API",
    version="0.1.0",
    description=(
        "Control layer for AI-agent actions in bank operations (hackathon MVP, synthetic data)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(SimulatorError, simulator_error_handler)

app.include_router(health.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(demo.router, prefix="/api")
app.include_router(cases.router, prefix="/api")
app.include_router(auth_router, prefix="/api")
