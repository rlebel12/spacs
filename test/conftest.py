import datetime
from typing import Any, Awaitable, Callable, Literal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp import ClientResponse
from pydantic import BaseModel

from spacs.client import ContentType, SpacsClient, SpacsRequestError

BASE_URL = "http://127.0.0.1"
FROZEN_TIME = datetime.datetime(2023, 5, 5, 8, 0, 0, 0)


class ExpectedRequest(BaseModel):
    method: Literal["GET", "POST"]
    path: str
    allow_redirects: bool = True
    params: dict[str, str] | None = None
    data: bytes | None = None
    headers: dict[str, str] = {"Content-Type": "application/json"}


class ResponseConfig(BaseModel):
    status: int = 200
    body: dict[str, Any] | None = None
    content_type: ContentType = ContentType.JSON


ResponseFactory = Callable[[ResponseConfig], ClientResponse]
ClientFactory = Callable[
    [ResponseConfig, Callable[[SpacsRequestError], Awaitable[None]] | None], SpacsClient
]


@pytest_asyncio.fixture(autouse=True)
async def close_sessions():
    yield
    await SpacsClient.close_all()


@pytest.fixture
def make_response() -> ResponseFactory:
    def _make_response(conf: ResponseConfig) -> ClientResponse:
        response = AsyncMock()
        response.ok = conf.status in range(200, 300)
        response.status = conf.status
        response.json = AsyncMock(return_value=conf.body)
        response.content_type = conf.content_type.value
        return response

    return _make_response


@pytest.fixture
def make_client(
    make_response: ResponseFactory,
) -> ClientFactory:
    def _make_client(
        conf: ResponseConfig,
        error_handler: Callable[[SpacsRequestError], Awaitable[None]] | None = None,
    ) -> SpacsClient:
        _client = SpacsClient(base_url=BASE_URL, error_handler=error_handler)
        response = make_response(conf)
        _client.session._request = AsyncMock(return_value=response)
        return _client

    return _make_client
