"""Token Bowl Chat Server - A chat server designed for large language model consumption."""

from .server import app, create_app

__version__ = "2.0.0"

__all__ = ["__version__", "app", "create_app"]
