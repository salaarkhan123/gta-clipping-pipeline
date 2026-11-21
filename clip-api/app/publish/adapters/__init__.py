"""One HTTP adapter per platform. Tests inject a fake transport; never post for real in CI."""
from .base import AdapterResult, PlatformAdapter, get_adapter
from . import youtube, tiktok, instagram, facebook  # noqa: F401 — register

__all__ = ["AdapterResult", "PlatformAdapter", "get_adapter"]
