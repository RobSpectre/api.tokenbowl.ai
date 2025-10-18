"""Entry point for running the server as a module."""

import uvicorn

from .config import settings

if __name__ == "__main__":
    # When reload is enabled, pass app as string path for proper reloading
    # When reload is disabled, import app object for better performance
    if settings.reload:
        uvicorn.run(
            "token_bowl_chat_server.server:app",
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level,
            reload=True,
        )
    else:
        from .server import app

        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level,
        )
