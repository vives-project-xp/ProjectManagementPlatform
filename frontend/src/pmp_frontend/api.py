"""The only way the frontend talks to the backend: its REST API over HTTP (ADR 0003)."""

from dataclasses import dataclass

import httpx

from pmp_frontend.settings import Settings

_transport: httpx.AsyncBaseTransport | None = None


def use_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Send API calls through `transport` instead of the network (used by tests)."""
    global _transport
    _transport = transport


def _client() -> httpx.AsyncClient:
    base_url = "http://backend" if _transport else Settings().backend_url
    return httpx.AsyncClient(base_url=base_url, transport=_transport, timeout=5)


@dataclass(frozen=True)
class Health:
    backend_online: bool
    database_online: bool


async def get_health() -> Health:
    try:
        async with _client() as client:
            response = await client.get("/api/health")
    except httpx.HTTPError:
        return Health(backend_online=False, database_online=False)
    return Health(
        backend_online=True,
        database_online=response.json().get("database") == "ok",
    )
