from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import os

from src.core.config import get_settings
from src.core.logging_config import setup_logging
from src.data.database import db_manager
from src.api.routes import router as api_router

# Setup Logging
setup_logging()
settings = get_settings()

app = FastAPI(title=settings.APP_NAME)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database Initialization
@app.on_event("startup")
def on_startup():
    db_manager.init_db()

# Include API Routes
app.include_router(api_router, prefix="/api")

# Serve Static Files (Dashboard)
# Ensure web-ui exists
if not os.path.exists("web-ui"):
    os.makedirs("web-ui")

app.mount("/static", StaticFiles(directory="web-ui"), name="static")

@app.get("/")
def read_root():
    return FileResponse("web-ui/index.html")

def start():
    """Entry point for running the app."""
    uvicorn.run("src.main:app", host="0.0.0.0", port=9000, reload=settings.DEBUG)

if __name__ == "__main__":
    start()
