"""FastAPI main application for Research Agent."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.agents import router as agents_router
from src.api.routes.analyze import router as analyze_router
from src.api.routes.budget import router as budget_router
from src.api.routes.channel import router as channel_router
from src.api.routes.discover import router as discover_router
from src.api.routes.models import router as models_router
from src.core.config import settings
from src.database import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan handler."""
    # Startup
    init_db()
    yield
    # Shutdown (cleanup if needed)


app = FastAPI(
    title="Research Agent API",
    description="AI-powered news research and political bias analysis for YouTube creators",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for frontend
# CORS middleware for frontend
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://frontend:3000",
]

# Allow all origins in development for easier testing
if settings.app_env == "development":
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for Docker."""
    return {"status": "healthy", "service": "research-agent"}


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint with API info."""
    return {
        "name": "Research Agent API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/api/config")
async def get_config() -> dict[str, str]:
    """Get current LLM configuration (without sensitive keys)."""
    return {
        "llm_provider": settings.llm_provider,
        "selected_model": settings.selected_model,
        "analysis_model": settings.analysis_model,
        "environment": settings.app_env,
    }


# Include routers

app.include_router(channel_router, prefix="/api", tags=["channel"])
app.include_router(agents_router, prefix="/api", tags=["agents"])
app.include_router(models_router, prefix="/api", tags=["models"])
app.include_router(discover_router, prefix="/api", tags=["discovery"])
app.include_router(analyze_router, prefix="/api", tags=["analysis"])
app.include_router(budget_router, prefix="/api", tags=["budget"])
