from fastapi import FastAPI

from app.api.wells import router as wells_router
from app.api.investigation import router as investigation_router


app = FastAPI(
    title="Well Delay AI",
    version="1.0.0"
)

app.include_router(wells_router)
app.include_router(investigation_router)


@app.get("/")
def root():
    return {
        "success": True,
        "message": "Well Delay AI API is running"
    }