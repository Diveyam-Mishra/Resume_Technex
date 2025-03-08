import logging
import time
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.database.db import init_db
from app.api import auth, user, resume, storage, health, feature, contributors, translation


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Reactive Resume",
    description="Reactive Resume is a free and open source resume builder that's built to make the mundane tasks of creating, updating and sharing your resume as easy as 1, 2, 3.",
    version="4.0.0",
    docs_url=None,
    redoc_url=None,
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
app.include_router(storage.router, prefix="/api/storage", tags=["Storage"])
app.include_router(health.router, prefix="/api/health", tags=["Health"])
app.include_router(feature.router, prefix="/api/feature", tags=["Feature"])
app.include_router(contributors.router, prefix="/api/contributors", tags=["Contributors"])
app.include_router(translation.router, prefix="/api/translation", tags=["Translation"])

# Custom OpenAPI documentation
@app.get("/api/docs", include_in_schema=False)
async def get_documentation():
    return get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="Reactive Resume API",
        swagger_favicon_url="",
    )

# Serve static files
app.mount("/artboard", StaticFiles(directory="static/artboard"), name="artboard")
app.mount("/", StaticFiles(directory="static/client"), name="client")

# Startup event to initialize database
@app.on_event("startup")
def startup_event():
    logger.info("Initializing database...")
    init_db()
    logger.info("🚀 Server is up and running on port %s", settings.PORT)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=settings.NODE_ENV == "development")