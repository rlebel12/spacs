import datetime
import json
from collections.abc import Callable
from enum import StrEnum
from typing import Any, Awaitable, ClassVar, Type

import aiohttp
from aiohttp import ClientConnectorError, ClientResponse
from pydantic import BaseModel

from spacs.conf import logger

ResponseModel = Type[BaseModel] | None
ModelContent = BaseModel | list[BaseModel]
JsonContent = dict[str, Any] | list[dict[str, Any]]
RequestContent = JsonContent | ModelContent | bytes | None
SpacsResponse = str | JsonContent | ModelContent | None


class ContentType(StrEnum):
    JSON = "application/json"
    FORM = "application/x-www-form-urlencoded"
    HTML = "text/html"


class SpacsRequest(BaseModel):
    path: str
    params: RequestContent = None
    body: RequestContent = None
    headers: dict[str, str] | None = None
    content_type: ContentType = ContentType.JSON
    response_model: ResponseModel = None


class SpacsRequestError(Exception):
    status: int
    reason: str
    client: "SpacsClient"
    request: SpacsRequest

    def __init__(
        self, status: int, reason: str, client: "SpacsClient", request: SpacsRequest
    ):
        self.status = status
        self.reason = reason
        self.client = client
        self.request = request

    def __repr__(self) -> str:
        return f"SpacsRequestError(status={self.status}, reason={self.reason}"


class SpacsClient:
    base_url: str | None
    path_prefix: str
    error_handler: Callable[[SpacsRequestError], Awaitable[None]] | None
    close_on_error: bool | list[int]

    _sessions: ClassVar[list["SpacsClient"]] = []
    _session: aiohttp.ClientSession | None = None

    def __init__(
        self,
        *,
        base_url: str | None = None,
        path_prefix: str = "",
        error_handler: Callable[[SpacsRequestError], Awaitable[None]] | None = None,
        close_on_error: bool | list[int] = False,
    ) -> None:
        """

        Keyword Args:
            base_url (str | None): Base url to be used for all requests
            path_prefix (str): Path partial to be prepended to paths for all requests
        """
        self._sessions.append(self)
        self.base_url = base_url
        self.path_prefix = path_prefix.strip("/")
        self.error_handler = error_handler
        self.close_on_error = close_on_error

    def __del__(self) -> None:
        self._sessions.remove(self)

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or not self.is_open:
            self._session = aiohttp.ClientSession(base_url=self.base_url)
        return self._session

    @property
    def is_open(self) -> bool:
        """Returns `True` if a session exists and is open."""
        return bool(self._session and not self._session.closed)

    async def close(self) -> None:
        if self._session is None or not self.is_open:
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

        base_log_info = {
            "method": action.__name__,
            "base_url": self.base_url,
            "path": request.path,
        }

        try:
            return await self._make_request(request, action, base_log_info)
        except ClientConnectorError as error:
            logger.error("Failed to connect to server.")
            raise error
        except Exception as error:
            await self._handle_request_failure(error, base_log_info)
            return None

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

    async def _make_request(
        self,
        request: SpacsRequest,
        action: Callable[..., Awaitable[ClientResponse]],
        base_log_info: dict,
    ) -> str | JsonContent | ModelContent:
        start_time = datetime.datetime.now(tz=datetime.timezone.utc)
        response = await action(
            request.path,
            params=request.params,
            data=request.body,
            headers=request.headers,
        )
        duration = datetime.datetime.now(tz=datetime.timezone.utc) - start_time
        logger.debug(
            {
                "msg": "Request completed",
                **base_log_info,
                "status": response.status,
                "duration": str(duration),
            }
        )
        if response.ok:
            return await self._handle_ok_response(response, request.response_model)
        raise SpacsRequestError(
            status=response.status,
            reason=str(response.reason),
            client=self,
            request=request,
        )

    async def _handle_request_failure(
        self, error: Exception, base_log_info: dict
    ) -> None:
        logger.error(
            {
                "msg": "Request error",
                **base_log_info,
                "error": repr(error),
            }
        )

        if not isinstance(error, SpacsRequestError):
            raise error

        if self.close_on_error is True or (
            isinstance(self.close_on_error, list)
            and error.status in self.close_on_error
        ):
            await self.close()

        if self.error_handler is not None:
            return await self.error_handler(error)
        raise error

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
        if model is not None and not isinstance(content, str):
            return cls._response_content_to_model(content, model)
        return content

    @classmethod
    def _prepare_content(cls, content: RequestContent) -> RequestContent:
        """Ensures input objects are in acceptable formats for requests"""

        if content is None or isinstance(content, bytes):
            return content

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
