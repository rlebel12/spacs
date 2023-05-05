import datetime
import json
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Awaitable, ClassVar, Self, Type

import aiohttp
from aiohttp import ClientConnectorError, ClientResponse
from pydantic import BaseModel

from spacs.conf import logger

ResponseModel = Type[BaseModel] | None
ModelContent = BaseModel | list[BaseModel]
JsonContent = dict[str, Any] | list[dict[str, Any]]
RequestContent = JsonContent | ModelContent | None
SpacsResponse = str | JsonContent | ModelContent


class ContentType(StrEnum):
    JSON = "application/json"
    FORM = "application/x-www-form-urlencoded"
    HTML = "text/html"


class SpacsRequest(BaseModel):
    path: str
    params: RequestContent = None
    body: RequestContent = None
    headers: dict[str, str] = None
    content_type: ContentType = ContentType.JSON
    response_model: ResponseModel = None


class SpacsClient:
    base_url: str | None
    path_prefix: str

    _sessions: ClassVar[list[Self]] = []
    _session: aiohttp.ClientSession | None = None

    def __init__(
        self,
        *,
        base_url: str | None = None,
        path_prefix: str = "",
    ) -> None:
        """

        Keyword Args:
            base_url (str | None): Base url to be used for all requests
            path_prefix (str): Path partial to be prepended to paths for all requests
        """
        self._sessions.append(self)
        self.base_url = base_url
        self.path_prefix = path_prefix.strip("/")

    def __del__(self) -> None:
        self._sessions.remove(self)

    @property
    def session(self) -> aiohttp.ClientSession:
        if not self.is_open:
            self._session = aiohttp.ClientSession(base_url=self.base_url)
        return self._session

    @property
    def is_open(self) -> bool:
        """Returns `True` if a session exists and is open."""
        return self._session and not self._session.closed

    async def close(self) -> None:
        if not self.is_open:
            return logger.warning("No session to close")
        await self._session.close()
        self._session = None

    async def get(self, request: SpacsRequest) -> SpacsResponse:
        return await self._request(self.session.get, request)

    async def post(self, request: SpacsRequest) -> SpacsResponse:
        return await self._request(self.session.post, request)

    async def put(self, request: SpacsRequest) -> SpacsResponse:
        return await self._request(self.session.put, request)

    async def delete(self, request: SpacsRequest) -> SpacsResponse:
        return await self._request(self.session.delete, request)

    async def _request(
        self,
        action: Callable[..., Awaitable[ClientResponse]],
        request: SpacsRequest,
    ) -> SpacsResponse:
        """Generic function for issuing requests"""
        request = self._prepare_request(request)

        start_time = datetime.datetime.now(tz=datetime.timezone.utc)
        base_log_info = {
            "method": action.__name__,
            "base_url": self.base_url,
            "path": request.path,
        }

        try:
            response = await action(
                request.path,
                params=request.params,
                data=request.body,
                headers=request.headers,
            )
            end_time = datetime.datetime.now(tz=datetime.timezone.utc)
            logger.debug(
                {
                    "msg": "Request completed",
                    **base_log_info,
                    "status": response.status,
                    "duration": str(end_time - start_time),
                }
            )
            if response.ok:
                return await self._handle_ok_response(response, request.response_model)
            else:
                raise SpacsRequestError(
                    status_code=response.status,
                    reason=response.reason,
                )
        except ClientConnectorError as error:
            logger.error("Failed to connect to server.")
            raise error
        except Exception as error:
            logger.error(
                {
                    "msg": "Request error",
                    **base_log_info,
                    "error": repr(error),
                }
            )
            raise error

    def _prepare_request(self, request: SpacsRequest) -> SpacsRequest:
        # Copy content to not modify inputs to `SpacsClient` actions
        result = request.copy(deep=True)

        if result.headers is None:
            result.headers = {}

        result.headers["Content-Type"] = result.content_type.value
        result.path = self._build_path(result.path)
        result.params = self._prepare_content(result.params)
        result.body = self._prepare_content(result.body)

        # All request actions pass the `data` kwarg instead of `json` to
        # simplify the API, so when we specify that `application/json` is the
        # `content-type`, automatically stringify/encode the payload.
        if result.body is not None and result.content_type == ContentType.JSON:
            result.body = json.dumps(result.body).encode("utf-8")

        return result

    def _build_path(self, path: str) -> str:
        prepend_slash = "/" if self.base_url else ""
        result = f"{prepend_slash}{path.strip('/')}"
        if self.path_prefix:
            result = f"{prepend_slash}{self.path_prefix}{result}"
        return result

    @classmethod
    async def close_all(cls) -> None:
        for session in cls._sessions:
            if not session.is_open:
                continue
            await session.close()

    @classmethod
    async def _handle_ok_response(
        cls, response: ClientResponse, model: Type[BaseModel] | None
    ) -> str | JsonContent | ModelContent:
        content = await cls._parse_response(response)
        if model is not None and not isinstance(response, str):
            content = cls._response_content_to_model(content, model)
        return content

    @classmethod
    def _prepare_content(cls, content: RequestContent) -> RequestContent:
        """Ensures input objects are in acceptable formats for requests"""

        if content is None:
            return

        if isinstance(content, list):
            return [cls._prepare_content(item) for item in content]

        if isinstance(content, BaseModel):
            content = content.dict()

        # At this point, `content` is a regular dictionary
        for key in content:
            value = content[key]
            if isinstance(value, datetime.datetime):
                # Convert `datetime` items to ISO 8601 strings
                content[key] = value.isoformat()
            elif isinstance(value, datetime.timedelta):
                # `timedelta` items represented as seconds (float)
                content[key] = value.total_seconds()
            elif isinstance(value, bool):
                content[key] = str(value)
        return content

    @staticmethod
    async def _parse_response(response: ClientResponse) -> str | JsonContent:
        match response.content_type:
            case ContentType.HTML:
                return await response.text()
            case _:
                return await response.json()

    @staticmethod
    def _response_content_to_model(
        content: JsonContent, model: Type[BaseModel]
    ) -> ModelContent:
        if isinstance(content, list):
            return [model(**item) for item in content]
        return model(**content)


class SpacsRequestError(Exception):
    def __init__(self, status_code: int, reason: str):
        self.status_code = status_code
        self.reason = reason

    def __repr__(self) -> str:
        return f"SpacsRequestError(status_code={self.status_code}, reason={self.reason}"
