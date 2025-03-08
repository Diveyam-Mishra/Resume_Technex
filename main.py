import logging
import time
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import os
from app.config.settings import settings
from app.database.db import init_db
from app.api import auth, user, resume, health, feature, contributors


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app with standard docs enabled
app = FastAPI(
    title="Reactive Resume",
    description="Reactive Resume is a free and open source resume builder that's built to make the mundane tasks of creating, updating and sharing your resume as easy as 1, 2, 3.",
    version="4.0.0",
    # Enable standard docs instead of custom
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
origins = [settings.PUBLIC_URL]
if settings.NODE_ENV == "development":
    origins.append("http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add request processing time middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Mount API routes
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(user.router, prefix="/api/user", tags=["User"])
app.include_router(resume.router, prefix="/api/resume", tags=["Resume"])
app.include_router(health.router, prefix="/api/health", tags=["Health"])
app.include_router(feature.router, prefix="/api/feature", tags=["Feature"])
app.include_router(contributors.router, prefix="/api/contributors", tags=["Contributors"])

# Add a root endpoint for quick testing
@app.get("/", tags=["Root"])
async def root():
    return {"message": "Welcome to Reactive Resume API - Visit /docs for API documentation"}

# Create necessary directories before mounting static files
directories = [
    "static/artboard",
    "static/client",
    settings.LOCAL_STORAGE_PATH  # This comes from your settings
]

# Ensure all directories exist
for directory in directories:
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

# Only mount static directories if they exist and have content
from fastapi.staticfiles import StaticFiles

# Mount storage path only if it exists
storage_path = settings.LOCAL_STORAGE_PATH
if os.path.exists(storage_path):
    app.mount("/storage", StaticFiles(directory=storage_path), name="storage")

# Mount artboard static files
if os.path.exists("static/artboard") and os.listdir("static/artboard"):
    app.mount("/artboard", StaticFiles(directory="static/artboard"), name="artboard")

# Mount client static files - mount this last to avoid path conflicts
if os.path.exists("static/client") and os.listdir("static/client"):
    app.mount("/static", StaticFiles(directory="static/client"), name="client")

# Startup event to initialize database
@app.on_event("startup")
def startup_event():
    logger.info("Initializing database...")
    init_db()
    logger.info("🚀 Server is up and running on port %s", settings.PORT)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=settings.NODE_ENV == "development")