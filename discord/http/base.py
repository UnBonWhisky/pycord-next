# The MIT License (MIT)
#
# Copyright (c) 2015-2021 Rapptz
# Copyright (c) 2021-present Pycord Development
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

"""HTTP transport: session handling, request execution and CDN access."""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any, NoReturn, TypeVar, cast
from urllib.parse import quote as _uriquote

import aiohttp

from .. import __version__, utils
from ..errors import (
    DiscordServerError,
    Forbidden,
    HTTPException,
    InvalidArgument,
    LoginFailure,
    NotFound,
)
from ..gateway import DiscordClientWebSocketResponse
from ..utils import MISSING, _get_event_loop
from .multipart import message_payload, multipart_form
from .ratelimit import CONNECTION_RESET, MaybeUnlock, RateLimiter
from .route import Route

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Iterable, Sequence

    from ..file import File
    from ..types import (
        components as components_,
        embed,
        message,
        poll as poll_,
        user,
    )
    from ..types.snowflake import Snowflake

__all__ = ("HTTPBase", "Response", "parse_response")

_log = logging.getLogger(__name__)

T = TypeVar("T")
Response = Coroutine[Any, Any, T]

_RETRY: Any = object()


async def parse_response(
    response: aiohttp.ClientResponse,
) -> dict[str, Any] | str | bytes:
    """Decode a response according to its content type."""
    try:
        if response.headers["content-type"] == "application/json":
            return cast(
                "dict[str, Any]",
                utils._from_json(await response.text(encoding="utf-8")),
            )
        if response.headers["content-type"] == "text/csv":
            return await response.read()
    except KeyError:
        # Thanks Cloudflare
        pass

    return await response.text(encoding="utf-8")


def _raise_for_asset(response: aiohttp.ClientResponse) -> NoReturn:
    if response.status == 404:
        raise NotFound(response, "asset not found")
    if response.status == 403:
        raise Forbidden(response, "cannot retrieve asset")
    raise HTTPException(response, "failed to get asset")


# For some reason, the Discord voice websocket expects this header to be
# completely lowercase while aiohttp respects spec and does it as case-insensitive
cast("Any", aiohttp.hdrs).WEBSOCKET = "websocket"


class HTTPBase:
    """The transport of the HTTP client: session, rate limits and requests."""

    def __init__(
        self,
        connector: aiohttp.BaseConnector | None = None,
        *,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        unsync_clock: bool = True,
        max_ratelimit_timeout: float | None = None,
    ) -> None:
        self.loop: asyncio.AbstractEventLoop = (
            _get_event_loop() if loop is None else loop
        )
        self.connector = connector
        self._session: aiohttp.ClientSession = MISSING  # filled in static_login
        self._ratelimiter: RateLimiter = RateLimiter(
            use_clock=not unsync_clock, max_timeout=max_ratelimit_timeout
        )
        self.token: str | None = None
        self.bot_token: bool = False
        self.proxy: str | None = proxy
        self.proxy_auth: aiohttp.BasicAuth | None = proxy_auth
        self.use_clock: bool = not unsync_clock

        user_agent = (
            "DiscordBot (https://pycord.dev, {0}) Python/{1[0]}.{1[1]} aiohttp/{2}"
        )
        self.user_agent: str = user_agent.format(
            __version__, sys.version_info, aiohttp.__version__
        )

    def _create_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            connector=self.connector, ws_response_class=DiscordClientWebSocketResponse
        )

    def recreate(self) -> None:
        """Create a new session if there is none or it was closed."""
        if self._session is MISSING or self._session.closed:
            self._session = self._create_session()

    async def ws_connect(self, url: str, *, compress: int = 0) -> Any:
        """Open a gateway websocket connection."""
        timeout = aiohttp.ClientWSTimeout(ws_close=30.0)  # pyright: ignore[reportCallIssue]
        kwargs: dict[str, Any] = {
            "proxy_auth": self.proxy_auth,
            "proxy": self.proxy,
            "max_msg_size": 0,
            "timeout": timeout,
            "autoclose": False,
            "headers": {
                "User-Agent": self.user_agent,
            },
            "compress": compress,
        }

        return await self._session.ws_connect(url, **kwargs)

    def _prepare(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        options = dict(kwargs)
        headers: dict[str, str] = {
            "User-Agent": self.user_agent,
        }

        if self.token is not None:
            headers["Authorization"] = f"Bot {self.token}"
        # some checking if it's a JSON request
        if "json" in options:
            headers["Content-Type"] = "application/json"
            options["data"] = utils._to_json(options.pop("json"))

        if reason := options.pop("reason", None):
            headers["X-Audit-Log-Reason"] = _uriquote(reason, safe="/ ")

        if locale := options.pop("locale", None):
            headers["X-Discord-Locale"] = locale

        options["headers"] = headers
        # Proxy support
        if self.proxy is not None:
            options["proxy"] = self.proxy
        if self.proxy_auth is not None:
            options["proxy_auth"] = self.proxy_auth
        return options

    async def _send(
        self,
        route: Route,
        options: dict[str, Any],
        maybe_lock: MaybeUnlock,
        tries: int,
    ) -> tuple[aiohttp.ClientResponse, dict[str, Any] | str | bytes, Any]:
        async with self._session.request(
            route.method, route.url, **options
        ) as response:
            _log.debug(
                "%s %s with %s has returned %s",
                route.method,
                route.url,
                options.get("data"),
                response.status,
            )

            # even errors have text involved in them so this is safe to call
            data = await parse_response(response)
            result = await self._handle_response(
                route, response, data, maybe_lock, tries
            )
            return response, data, result

    async def _handle_response(
        self,
        route: Route,
        response: aiohttp.ClientResponse,
        data: dict[str, Any] | str | bytes,
        maybe_lock: MaybeUnlock,
        tries: int,
    ) -> Any:
        await self._ratelimiter.observe(route, response, maybe_lock)

        # the request was successful so just return the text/json
        if 300 > response.status >= 200:
            _log.debug("%s %s has received %s", route.method, route.url, data)
            return data

        error = None if isinstance(data, bytes) else data

        # we are being rate limited
        if response.status == 429:
            if not response.headers.get("Via") or not isinstance(error, dict):
                # Banned by Cloudflare more than likely.
                raise HTTPException(response, error)

            await self._ratelimiter.wait(
                route,
                float(error["retry_after"]),
                is_global=bool(error.get("global", False)),
            )
            return _RETRY

        # we've received a 500, 502, 503, or 504, unconditional retry
        if response.status in {500, 502, 503, 504}:
            await asyncio.sleep(1 + tries * 2)
            return _RETRY

        # the usual error cases
        if response.status == 403:
            raise Forbidden(response, error)
        if response.status == 404:
            raise NotFound(response, error)
        if response.status >= 500:
            raise DiscordServerError(response, error)
        raise HTTPException(response, error)

    async def request(
        self,
        route: Route,
        *,
        files: Sequence[File] | None = None,
        form: Iterable[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Send a request to ``route``, honouring rate limits and retrying."""
        options = self._prepare(kwargs)
        maybe_lock = await self._ratelimiter.acquire(route)

        response: aiohttp.ClientResponse | None = None
        data: dict[str, Any] | str | bytes | None = None
        with maybe_lock:
            for tries in range(5):
                if files:
                    for f in files:
                        f.reset(seek=tries)

                if form:
                    form_data = aiohttp.FormData(quote_fields=False)
                    for params in form:
                        form_data.add_field(**params)
                    options["data"] = form_data

                try:
                    response, data, result = await self._send(
                        route, options, maybe_lock, tries
                    )
                # This is handling exceptions from the request
                except OSError as e:
                    # Connection reset by peer
                    if tries < 4 and e.errno in CONNECTION_RESET:
                        await asyncio.sleep(1 + tries * 2)
                        continue
                    raise

                if result is not _RETRY:
                    return result

            if response is not None:
                # We've run out of retries, raise.
                error = None if isinstance(data, bytes) else data
                if response.status >= 500:
                    raise DiscordServerError(response, error)

                raise HTTPException(response, error)

            raise RuntimeError("Unreachable code in HTTP handling")

    async def get_from_cdn(self, url: str) -> bytes:
        """Download an asset from the CDN."""
        async with self._session.get(url) as resp:
            if resp.status == 200:
                return await resp.read()
            _raise_for_asset(resp)

    async def stream_from_cdn(self, url: str, chunksize: int) -> AsyncGenerator[bytes]:
        """Stream an asset from the CDN in chunks."""
        if not isinstance(cast("object", chunksize), int) or chunksize < 1:
            raise InvalidArgument("The chunksize must be a positive integer.")

        async with self._session.get(url) as resp:
            if resp.status != 200:
                _raise_for_asset(resp)
            async for chunk in resp.content.iter_chunked(chunksize):
                yield chunk

    # state management

    async def close(self) -> None:
        """Close the session."""
        if self._session:
            await self._session.close()
            self._session = MISSING

    # login management

    async def static_login(self, token: str) -> user.User:
        """Log in with a token and return the current user."""
        await self.close()
        # Necessary to get aiohttp to stop complaining about session creation
        self._session = self._create_session()
        old_token = self.token
        self.token = token

        try:
            data = await self.request(Route("GET", "/users/@me"))
        except HTTPException as exc:
            self.token = old_token
            if exc.status == 401:
                raise LoginFailure("Improper token has been passed.") from exc
            raise

        return cast("user.User", data)

    def send_multipart_helper(
        self,
        route: Route,
        *,
        files: Sequence[File],
        content: str | None = None,
        tts: bool = False,
        embed: embed.Embed | None = None,
        embeds: Iterable[embed.Embed | None] | None = None,
        nonce: int | str | None = None,
        enforce_nonce: bool | None = None,
        allowed_mentions: message.AllowedMentions | None = None,
        message_reference: message.MessageReference | None = None,
        stickers: Sequence[Snowflake] | None = None,
        components: list[components_.Component] | None = None,
        flags: int | None = None,
        poll: poll_.Poll | None = None,
        shared_client_theme: message.SharedClientTheme | None = None,
    ) -> Response[message.Message]:
        """Send a new message with attachments."""
        payload = message_payload(
            content=content,
            embed=embed,
            embeds=embeds,
            nonce=nonce,
            enforce_nonce=enforce_nonce,
            allowed_mentions=allowed_mentions,
            message_reference=message_reference,
            stickers=stickers,
            components=components,
            flags=flags,
            poll=poll,
            shared_client_theme=shared_client_theme,
        )
        payload["tts"] = tts
        return self.request(route, form=multipart_form(payload, files), files=files)

    def edit_multipart_helper(
        self,
        route: Route,
        files: Sequence[File],
        **payload: Any,
    ) -> Response[message.Message]:
        """Send an edit request with new attachments."""
        return self.request(route, form=multipart_form(payload, files), files=files)

    def _edit_webhook_helper(
        self,
        route: Route,
        file: File | None = None,
        content: str | None = None,
        embeds: list[embed.Embed] | None = None,
        allowed_mentions: message.AllowedMentions | None = None,
    ) -> Response[message.Message]:
        payload: dict[str, Any] = {}
        if content:
            payload["content"] = content
        if embeds:
            payload["embeds"] = embeds
        if allowed_mentions:
            payload["allowed_mentions"] = allowed_mentions

        files = [file] if file else []
        form = multipart_form(payload, files, field="file", attach=False)
        return self.request(route, form=form, files=files or None)
