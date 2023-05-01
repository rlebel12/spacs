import datetime
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Any, ClassVar, Self, Awaitable, Type

import aiohttp
from aiohttp import ClientConnectorError, ClientResponse
from pydantic import BaseModel

ResponseModel = Type[BaseModel] | None
RequestContent = dict[str, Any] | BaseModel | None
JsonResponseContent = dict[str, Any] | list[dict[str, Any]]
ModelResponse = BaseModel | list[BaseModel]
SpacsResponse = str | JsonResponseContent | ModelResponse

_logger = logging.getLogger(__name__)


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
    _logger: logging.Logger
    _session: aiohttp.ClientSession | None = None

    def __init__(
        self,
        *,
        base_url: str | None = None,
        path_prefix: str = "",
        logger: logging.Logger | None = None,
    ) -> None:
        """

        Keyword Args:
            base_url (str | None): Base url to be used for all requests
            path_prefix (str): Path partial to be prepended to paths for all requests
            logger (logging.Logger | None): Override for logger
        """
        self._sessions.append(self)
        self.base_url = base_url
        self.path_prefix = path_prefix.strip("/")
        self._logger = logger
        if self._logger is None:
            self._logger = logging.getLogger(__name__)

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
            return _logger.warning("No session to close")
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
            async with action(
                request.path,
                params=request.params,
                json=request.body,
                headers=request.headers,
            ) as response:
                end_time = datetime.datetime.now(tz=datetime.timezone.utc)
                self._logger.debug(
                    {
                        "msg": "Request completed",
                        **base_log_info,
                        "status": response.status,
                        "duration": str(end_time - start_time),
                    }
                )
                if response.ok:
                    return await self._handle_ok_response(
                        response, request.response_model
                    )
                else:
                    raise SpacsRequestError(
                        status_code=response.status,
                        reason=response.reason,
                    )
        except ClientConnectorError as error:
            self._logger.error("Failed to connect to server.")
            raise error
        except SpacsRequestError as error:
            raise error
        except Exception as error:
            self._logger.error(
                {
                    "msg": "Request error",
                    **base_log_info,
                    "error": str(error),
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
        return result

    def _build_path(self, path: str) -> str:
        result = f"/{path.strip('/')}"
        if self.path_prefix:
            result = f"/{self.path_prefix}{result}"
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
    ) -> str | JsonResponseContent | ModelResponse:
        content = await cls._parse_response(response)
        if model is not None and not isinstance(response, str):
            content = cls._response_content_to_model(content, model)
        return content

    @staticmethod
    def _prepare_content(content: RequestContent) -> RequestContent:
        """Ensures input objects are in acceptable formats for requests"""

        if content is None:
            return

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
    async def _parse_response(response: ClientResponse) -> str | JsonResponseContent:
        match response.content_type:
            case ContentType.HTML:
                return await response.text()
            case _:
                return await response.json()

    @staticmethod
    def _response_content_to_model(
        content: JsonResponseContent, model: Type[BaseModel]
    ) -> ModelResponse:
        if isinstance(content, list):
            return [model(**item) for item in content]
        return model(**content)


class SpacsRequestError(Exception):
    def __init__(self, status_code: int, reason: str):
        self.status_code = status_code
        self.reason = reason

    def __repr__(self) -> str:
        return super().__repr__()
