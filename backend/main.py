"""
Secretary Partner AI - Main Application Entry Point

Brain Dump Partner: ADHD向け自律型秘書AI
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    settings = get_settings()
    print(f"Starting Secretary Partner AI in {settings.ENVIRONMENT} mode...")

    # Initialize database if needed
    if settings.ENVIRONMENT == "local":
        from app.infrastructure.local.database import init_db
        await init_db()

    yield

    # Shutdown
    print("Shutting down Secretary Partner AI...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Secretary Partner AI",
        description="Brain Dump Partner - ADHD向け自律型秘書AI (外付け前頭葉)",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    from app.api import chat, tasks, projects, captures, agent_tasks, memories, heartbeat, today

    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
    app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
    app.include_router(captures.router, prefix="/api/captures", tags=["captures"])
    app.include_router(agent_tasks.router, prefix="/api/agent-tasks", tags=["agent_tasks"])
    app.include_router(memories.router, prefix="/api/memories", tags=["memories"])
    app.include_router(heartbeat.router, prefix="/api/heartbeat", tags=["heartbeat"])
    app.include_router(today.router, prefix="/api/today", tags=["today"])

    # Mount storage for local development
    storage_path = settings.STORAGE_BASE_PATH
    if not os.path.isabs(storage_path):
        storage_path = os.path.join(os.getcwd(), storage_path)
    
    if os.path.exists(storage_path):
        app.mount("/storage", StaticFiles(directory=storage_path), name="storage")

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "environment": settings.ENVIRONMENT,
            "version": "0.1.0"
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
