"""Test fixtures: a local stand-in for the FMI service."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from aiohttp import ClientSession, web
from aiohttp.test_utils import TestServer

from aiofmi import FmiClient

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> bytes:
    """Return the contents of a recorded response."""
    return (FIXTURES / name).read_bytes()


@dataclass
class FakeFmi:
    """What the stand-in service answers, and what it was asked."""

    body: bytes = b""
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    requests: list[dict[str, str]] = field(default_factory=list)

    def respond(self, fixture: str, status: int = 200) -> None:
        """Answer the next requests with a recorded response."""
        self.body = load_fixture(fixture)
        self.status = status

    async def handle(self, request: web.Request) -> web.Response:
        """Record the query and send the configured response."""
        self.requests.append(dict(request.query))
        return web.Response(body=self.body, status=self.status, headers=self.headers)


@pytest.fixture
def fmi() -> FakeFmi:
    """Return the state of the stand-in service."""
    return FakeFmi()


@pytest.fixture
async def session() -> AsyncIterator[ClientSession]:
    """Return a client session, as the caller of the library would own it."""
    async with ClientSession() as session:
        yield session


@pytest.fixture
async def client(fmi: FakeFmi, session: ClientSession) -> AsyncIterator[FmiClient]:
    """Return a client that talks to the stand-in service."""
    app = web.Application()
    app.router.add_get("/wfs", fmi.handle)
    async with TestServer(app) as server:
        yield FmiClient(session, url=str(server.make_url("/wfs")))
