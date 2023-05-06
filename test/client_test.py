import datetime
from test.conftest import (
    BASE_URL,
    FROZEN_TIME,
    ClientFactory,
    ExpectedRequest,
    ResponseConfig,
)

import pytest
from pydantic import BaseModel
from yarl import URL

from spacs.client import SpacsClient, SpacsRequest


@pytest.mark.asyncio
async def test_base_url():
    assert SpacsClient(base_url=BASE_URL).session._base_url == URL(BASE_URL)
    assert SpacsClient().session._base_url is None


@pytest.mark.asyncio
async def test_close(make_client: ClientFactory):
    client = make_client(ResponseConfig())
    await client.get(SpacsRequest(path="/"))
    assert client.is_open
    await client.close()
    assert not client.is_open


@pytest.mark.asyncio
async def test_close_all(make_client: ClientFactory):
    clients = [make_client(ResponseConfig()) for _ in range(3)]
    for client in clients:
        await client.get(SpacsRequest(path="/"))
        assert client.is_open
    await SpacsClient.close_all()
    for client in clients:
        assert not client.is_open
    assert len(clients) == 3


@pytest.mark.asyncio
async def test_get(make_client: ClientFactory):
    client = make_client(ResponseConfig(status_code=200, body={"foo": "bar"}))

    result = await client.get(SpacsRequest(path="/test"))

    assert result == {"foo": "bar"}
    assert_request(client, ExpectedRequest(method="GET", path="/test"))


@pytest.mark.asyncio
async def test_post_model(make_client: ClientFactory):
    class TestModel(BaseModel):
        name: str
        age: int
        datetime: datetime.datetime
        timedelta: datetime.timedelta
        optional: str | None = None

    client = make_client(
        ResponseConfig(
            status_code=201,
            body={
                "name": "James",
                "age": 25,
                "datetime": "2023-05-05T08:00:00",
                "timedelta": 3600.0,
            },
        )
    )
    object = TestModel(
        name="James",
        age=25,
        datetime=FROZEN_TIME,
        timedelta=datetime.timedelta(hours=1.0),
    )

    result = await client.post(
        SpacsRequest(path="/test", body=object, response_model=TestModel)
    )

    assert result == object
    assert isinstance(result, TestModel)
    assert_request(
        client,
        ExpectedRequest(
            method="POST",
            path="/test",
            data=b'{"name": "James", "age": 25, "datetime": "2023-05-05T08:00:00", "timedelta": 3600.0, "optional": null}',  # noqa: E501
        ),
    )


def assert_request(client: SpacsClient, request: ExpectedRequest) -> None:
    kwargs = {
        "params": request.params,
        "data": request.data,
        "headers": request.headers,
    }
    if request.method in ["GET"]:
        kwargs["allow_redirects"] = request.allow_redirects
    client.session._request.assert_called_once_with(
        request.method, request.path, **kwargs
    )