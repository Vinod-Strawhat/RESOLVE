import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.actions import router as actions_router
from backend.api.agent import router as agent_router
from backend.api.cases import router as cases_router

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

load_dotenv()

app = FastAPI(
    title="RESOLVE API",
    version="0.5.0",
)

app.include_router(agent_router)
app.include_router(cases_router)
app.include_router(actions_router)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
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