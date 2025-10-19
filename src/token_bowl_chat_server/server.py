"""Main server application."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import settings
from .webhook import webhook_delivery

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for startup and shutdown events.

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Startup
    logger.info("Starting Token Bowl Chat Server...")
    await webhook_delivery.start()
    logger.info("Server started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Token Bowl Chat Server...")
    await webhook_delivery.stop()
    logger.info("Server shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title="Token Bowl Chat Server",
        description="A chat server designed for large language model consumption",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS - allow all origins for easy developer integration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router
    app.include_router(router)

    # Mount static files in dev mode only
    if settings.reload:
        public_dir = Path(__file__).parent.parent.parent / "public"
        if public_dir.exists():
            app.mount("/public", StaticFiles(directory=str(public_dir)), name="public")
            logger.info(f"Static files mounted at /public from {public_dir}")

    return app


# Create app instance
app = create_app()
