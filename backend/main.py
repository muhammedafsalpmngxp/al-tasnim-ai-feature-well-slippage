import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.wells import router as wells_router
from app.api.investigation import router as investigation_router


app = FastAPI(
    title="Well Delay AI",
    version="1.0.0"
)


# ============================================================
# CORS
# ============================================================
#
# The React frontend (Vite dev server) runs on a different
# origin/port than this API, so the browser needs CORS headers.

allowed_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


app.include_router(wells_router)
app.include_router(investigation_router)


@app.get("/")
def root():
    return {
        "success": True,
        "message": "Well Delay AI API is running"
    }