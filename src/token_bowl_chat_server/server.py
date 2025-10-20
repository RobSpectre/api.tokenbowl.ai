"""Main server application."""

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .api import router
from .config import settings
from .webhook import webhook_delivery

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log HTTP requests and responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Log request and response with status codes.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in the chain

        Returns:
            Response from the next handler
        """
        # Skip logging for health check endpoint to reduce noise
        if request.url.path == "/health":
            return await call_next(request)

        # Record start time
        start_time = time.time()

        # Get request details
        method = request.method
        path = request.url.path
        client_host = request.client.host if request.client else "unknown"

        # Process request
        try:
            response = await call_next(request)
            status_code = response.status_code
            duration_ms = (time.time() - start_time) * 1000

            # Log based on status code
            if 200 <= status_code < 300:
                logger.info(
                    f"{method} {path} - {status_code} - {duration_ms:.2f}ms - {client_host}"
                )
            elif 400 <= status_code < 500:
                logger.warning(
                    f"{method} {path} - {status_code} - {duration_ms:.2f}ms - {client_host}"
                )
            elif 500 <= status_code < 600:
                logger.error(
                    f"{method} {path} - {status_code} - {duration_ms:.2f}ms - {client_host}"
                )

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"{method} {path} - EXCEPTION - {duration_ms:.2f}ms - {client_host} - {str(e)}"
            )
            raise


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
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

    # Add request logging middleware
    app.add_middleware(RequestLoggingMiddleware)

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
