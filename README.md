# SPACS: Simple Pydantic AIOHTTP Client Sessions

A package to assist in managing and using long-lived AIOHTTP client sessions with simplicity. Built to handle Pydantic objects.

## Features

- Handles request params and bodies as either Pydantic objects or native Python dictionaries, converting items to JSON-safe format.
- Abstracts away internals of managing the request/response objects, instead either returning parsed response content on success, or raising a specialized error object.
- Automatically manages persistent connections to be shared over extended lifespan across application, cleaning up all open connections on teardown.
- Utilizes modern Python type hinting.

## Installation

Using poetry (preferred):

```bash
poetry add spacs
```

Using pip:

```bash
pip install spacs
```

## Basic Usage
SPACS currently supports the HTTP methods GET, POST, PUT, and DELETE. All methods take the same, singular `SpacsRequest` argument. The following are some common patterns to be utilized when working with SPACS.
### Request With Params
```python
import asyncio
from spacs import SpacsClient, SpacsRequest

async def example():
    client = SpacsClient(base_url="https://httpbin.org")
    request = SpacsRequest(path="/get", params={"foo": "bar"})
    result = await client.get(request)
    print(result)
    await client.close()


asyncio.new_event_loop().run_until_complete(example())
```

### Sending Pydantic objects via request body
```python
import asyncio
from spacs import SpacsClient, SpacsRequest
from pydantic import BaseModel

class Person(BaseModel):
    name: str
    age: int

async def example():
    client = SpacsClient(base_url="https://httpbin.org")
    person = Person(name="James", age=25)
    request = SpacsRequest(path="/post", body=person)
    response = await client.post(request)
    print(response)
    await client.close()


asyncio.new_event_loop().run_until_complete(example())
```

#### Tip: Response Model
For all examples here, if the API declares that response bodies will *only* contain json data representing a Pydantic object, the payload can be deserialized into an object by specifying a Pydantic class in the request. For example, using our above `Person` model:
```python
request = SpacsRequest(path="/post", body=person, response_model=Person)
response = await client.post(request)
assert isinstance(response, Person)
```

## Handling Errors
### Manual Error Handling
```python
import asyncio
from spacs import SpacsClient, SpacsRequest, SpacsRequestError

async def example():
    client = SpacsClient(base_url="https://httpbin.org")
    request = SpacsRequest(path="/status/404")
    try:
        await client.get(request)
    except SpacsRequestError as error:
        print({"code": error.status, "reason": error.reason})
    await client.close()


asyncio.new_event_loop().run_until_complete(example())
```

### Injecting Error Handler
```python
import asyncio
from spacs import SpacsClient, SpacsRequest, SpacsRequestError

async def error_handler(error: SpacsRequestError) -> None:
    print(f"It blew up: {error.reason}")

async def example():
    client = SpacsClient(base_url="https://httpbin.org", error_handler=error_handler)
    request = SpacsRequest(path="/status/504")
    response = await client.get(request)
    await client.close()
    assert response is None


asyncio.new_event_loop().run_until_complete(example())
```

### Closing sessions
In the above examples, a `client.close()` call is made. This is to ensure that the underlying AIOHTTP session
is properly cleaned up, and is a step that should always be performed on application teardown. Alternatively, the following can be used to close all open sessions without having to
directly reference a client instance:
```python
await SpacsClient.close_all()
```
> SPACS is not affiliated with httpbin.org.

## Building

```
poetry build
```
