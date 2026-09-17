import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.wells import router as wells_router
from app.api.investigation import router as investigation_router
from app.api.schema import router as schema_router
from app.api.sql_agent import router as sql_agent_router


load_dotenv()

# The local Vite dev server is always allowed, so local development keeps working with no
# config; CORS_ALLOWED_ORIGINS (comma-separated) adds whatever a real deployment needs
# beyond that — a hardcoded localhost-only list would silently break any frontend that
# isn't running on a developer's own machine.
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
_EXTRA_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
ALLOWED_ORIGINS = _DEV_ORIGINS + _EXTRA_ORIGINS

app = FastAPI(
    title="Well Delay AI",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(wells_router)
app.include_router(investigation_router)
app.include_router(schema_router)
app.include_router(sql_agent_router)


@app.get("/")
def root():
    return {
        "success": True,
        "message": "Well Delay AI API is running"
    }