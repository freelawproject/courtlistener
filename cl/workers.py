"""Uvicorn worker class for running CourtListener under Gunicorn."""

from typing import Any

from uvicorn.workers import UvicornWorker as BaseUvicornWorker


class UvicornWorker(BaseUvicornWorker):
    """Uvicorn worker with the ASGI lifespan protocol turned off."""

    CONFIG_KWARGS: dict[str, Any] = {
        "loop": "auto",
        "http": "auto",
        "lifespan": "off",
    }
