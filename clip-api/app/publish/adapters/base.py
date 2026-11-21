"""Platform adapter contract. Final publish call is at-most-once; resume from external_ref on retry."""
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

_REGISTRY: dict[str, type["PlatformAdapter"]] = {}


def register(platform: str):
    def wrap(cls: type["PlatformAdapter"]):
        _REGISTRY[platform] = cls
        return cls
    return wrap


def get_adapter(platform: str, client: httpx.Client | None = None) -> "PlatformAdapter":
    cls = _REGISTRY.get(platform)
    if cls is None:
        raise KeyError(f"no adapter for {platform}")
    return cls(client=client)


@dataclass
class AdapterResult:
    ok: bool
    step: str | None = None                 # last completed step name
    external_ref: str | None = None         # upload/session/container id for resume
    external_id: str | None = None          # published post id
    external_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    data: dict[str, Any] = field(default_factory=dict)


class PlatformAdapter(Protocol):
    platform: str

    def __init__(self, client: httpx.Client | None = None): ...

    def exchange_code(self, code: str, redirect_uri: str, code_verifier: str | None = None) -> dict:
        """Return access_token, refresh_token?, expires_in, refresh_expires_in?, scopes, external_id, display_name, avatar_url."""
        ...

    def refresh(self, refresh_token: str) -> dict:
        ...

    def revoke(self, access_token: str) -> None:
        ...

    def publish(
        self,
        *,
        access_token: str,
        media_path: str | None,
        media_url: str | None,
        title: str | None,
        caption: str,
        privacy: str | None,
        options: dict,
        step: str | None,
        external_ref: str | None,
    ) -> AdapterResult:
        """Transfer then finalize. Never repeat the final public call blindly; status-check external_ref first."""
        ...

    def status(self, *, access_token: str, external_ref: str) -> AdapterResult:
        ...
