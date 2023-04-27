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

## Usage

```python
import spacs
from pydantic import BaseModel

...

example_client = spacs.SpacsClient(base_url="http://example.com")

# Basic request with error handling
try:
    apple_response = await example_client.get("fruit/apple", params={"cultivar": "honeycrisp"})
except spacs.SpacsRequestError as error:
    print({"code": error.status_code, "reason": error.reason})

# Sending Pydantic objects via HTTP POST
class MyModel(BaseModel):
    name: str
    age: int

example_object = MyModel(name="James", age=25)
person_response = await example_client.post("person", body=example_object)

# Manually closing a session
await example_client.close()
# Alternatively, to close all open sessions:
await spacs.SpacsClient.close_all()
```

## Building

```
poetry build
```
