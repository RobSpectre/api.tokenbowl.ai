"""Entry point for running the server as a module."""

import logging

import uvicorn

from .config import settings

if __name__ == "__main__":
    # Configure logging with timestamps
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    log_config["formatters"]["access"]["fmt"] = '%(asctime)s - %(levelname)s - %(client_addr)s - "%(request_line)s" %(status_code)s'

    # When reload is enabled, pass app as string path for proper reloading
    # When reload is disabled, import app object for better performance
    if settings.reload:
        uvicorn.run(
            "token_bowl_chat_server.server:app",
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level,
            reload=True,
            log_config=log_config,
        )
    else:
        from .server import app

        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            log_level=settings.log_level,
            log_config=log_config,
        )
