import os
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.actions import router as actions_router
from backend.api.agent import router as agent_router
from backend.api.auth import router as auth_router
from backend.api.case_responses import router as case_responses_router
from backend.api.cases import router as cases_router
from backend.api.config import router as config_router
from backend.api.history import router as history_router
from backend.services.legacy_ownership import migrate_legacy_ownership_default

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

load_dotenv()


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_legacy_ownership_default()
    yield


app = FastAPI(
    title="RESOLVE API",
    version="0.5.0",
    lifespan=lifespan,
)

app.include_router(agent_router)
app.include_router(auth_router)
app.include_router(cases_router)
app.include_router(case_responses_router)
app.include_router(actions_router)
app.include_router(config_router)
app.include_router(history_router)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5174").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict:
    return {"service": "RESOLVE API", "status": "ok"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "RESOLVE API"}