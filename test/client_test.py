from test.conftest import BASE_URL, ClientFactory, ResponseConfig

import pytest
from pydantic import BaseModel
from yarl import URL

from spacs.client import SpacsClient, SpacsRequest


@pytest.mark.asyncio
async def test_base_url():
    assert SpacsClient(base_url=BASE_URL).session._base_url == URL(BASE_URL)
    assert SpacsClient().session._base_url is None


@pytest.mark.asyncio
async def test_close():
    ...


@pytest.mark.asyncio
async def test_close_all():
    ...


@pytest.mark.asyncio
async def test_get(make_client: ClientFactory):
    conf = ResponseConfig(status_code=200, body={"foo": "bar"})
    client = make_client(conf)
    request = SpacsRequest(path="/test")

    result = await client.get(request)

    assert result == {"foo": "bar"}
    client.session._request.assert_called_once_with(
        "GET",
        "/test",
        allow_redirects=True,
        params=None,
        data=None,
        headers={"Content-Type": "application/json"},
    )


@pytest.mark.asyncio
async def test_post_model(make_client: ClientFactory):
    class TestModel(BaseModel):
        name: str
        age: int

    conf = ResponseConfig(status_code=201, body={"name": "James", "age": 25})
    client = make_client(conf)
    object = TestModel(name="James", age=25)
    request = SpacsRequest(path="/test", body=object, response_model=TestModel)

    result = await client.post(request)

    assert result == object
    client.session._request.assert_called_once_with(
        "POST",
        "/test",
        params=None,
        data=b'{"name": "James", "age": 25}',
        headers={"Content-Type": "application/json"},
    )
