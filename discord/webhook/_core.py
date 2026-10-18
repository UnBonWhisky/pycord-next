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

"""The transport independent core shared by every webhook implementation."""

from __future__ import annotations

import logging
import re
import threading
import time
import weakref
from typing import TYPE_CHECKING, Any, Generic, NamedTuple, NoReturn, TypeVar, cast
from urllib.parse import quote as urlquote

from .. import utils
from ..enums import WebhookType
from ..errors import (
    DiscordServerError,
    Forbidden,
    HTTPException,
    InvalidArgument,
    NotFound,
)
from ..file import VoiceMessage
from ..flags import MessageFlags
from ..http import Route
from ..http.multipart import multipart_form
from ..http.ratelimit import (
    MAX_TRIES,
    backoff,
    exhausted_delay,
    is_connection_reset,
)
from ..user import BaseUser

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from ..abc import Snowflake
    from ..embeds import Embed
    from ..file import File
    from ..mentions import AllowedMentions
    from ..message import Attachment
    from ..poll import Poll
    from ..state import ConnectionState
    from ..ui.view import BaseView

__all__ = (
    "Done",
    "ExecuteWebhookParameters",
    "Execution",
    "Retry",
    "SendPlan",
    "WebhookLimits",
    "WebhookRequest",
    "WebhookRequests",
    "execute_request",
    "handle_message_parameters",
    "interaction_response_request",
    "message_request",
    "original_response_request",
    "parse_webhook_url",
    "partial_webhook_data",
    "webhook_request",
)

_log = logging.getLogger(__name__)

MISSING: Any = utils.MISSING

_LockT = TypeVar("_LockT")

_WEBHOOK = "/webhooks/{webhook_id}"
_WEBHOOK_SCOPED = "/webhooks/{webhook_id}/{webhook_token}"
_MESSAGE = "/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}"
_ORIGINAL = "/webhooks/{webhook_id}/{webhook_token}/messages/@original"
_NOT_USABLE = "This webhook does not have a token associated with it"
_URL = re.compile(
    r"discord(?:app)?.com/api/webhooks/(?P<id>\d{17,20})/(?P<token>[\w\.\-_]{60,68})"
)


class WebhookRequest(NamedTuple):
    """Everything a transport needs to send one webhook request."""

    route: Route
    payload: dict[str, Any] | None = None
    multipart: list[dict[str, Any]] | None = None
    files: list[File] | None = None
    reason: str | None = None
    auth_token: str | None = None
    params: dict[str, Any] | None = None


class Done(NamedTuple):
    """The request succeeded with this decoded body."""

    data: Any


class Retry(NamedTuple):
    """The request must be sent again after this many seconds."""

    delay: float


class WebhookLimits(Generic[_LockT]):
    """Serialises the requests of one webhook and tracks global rate limits.

    The limits do not depend on asyncio or on threads: the lock type is given
    by the transport.
    """

    def __init__(self, lock_factory: Callable[[], _LockT]) -> None:
        self._factory: Callable[[], _LockT] = lock_factory
        self._locks: weakref.WeakValueDictionary[tuple[Any, ...], Any] = (
            weakref.WeakValueDictionary()
        )
        self._guard: threading.Lock = threading.Lock()
        self._global_until: float = 0.0

    def lock_for(self, route: Route) -> _LockT:
        """Return the lock shared by every request of the webhook of ``route``."""
        key = (route.webhook_id, route.webhook_token)
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = self._locks[key] = self._factory()
            return lock

    def global_delay(self) -> float:
        """Return how long every request must still wait for a global limit."""
        return max(0.0, self._global_until - time.monotonic())

    def block(self, delay: float) -> None:
        """Hold back every request for ``delay`` seconds."""
        self._global_until = max(self._global_until, time.monotonic() + delay)


def _decode(headers: Mapping[str, str], text: str) -> dict[str, Any] | str | None:
    if not text:
        return None
    content_type = headers.get("Content-Type", "").partition(";")[0].strip().lower()
    if content_type == "application/json":
        return cast("dict[str, Any] | str | None", utils._from_json(text))
    return text


class Execution:
    """The rate limit and retry policy of one request, whatever the transport.

    A transport sends the request ``MAX_TRIES`` times at most, handing every
    response to :meth:`handle` and every connection error to
    :meth:`connection_error`, and sleeps for the delay of each :class:`Retry`.
    Once it is done it sleeps for :attr:`hold` if the bucket is exhausted.
    """

    def __init__(self, request: WebhookRequest, limits: WebhookLimits[Any]) -> None:
        self.request: WebhookRequest = request
        self.limits: WebhookLimits[Any] = limits
        self.hold: float = 0.0
        self.body: str | None = None
        self.headers: dict[str, str] = {}
        if request.payload is not None:
            self.headers["Content-Type"] = "application/json"
            self.body = utils._to_json(request.payload)
        if request.auth_token is not None:
            self.headers["Authorization"] = f"Bot {request.auth_token}"
        if request.reason is not None:
            self.headers["X-Audit-Log-Reason"] = urlquote(request.reason, safe="/ ")
        self._last: tuple[Any, dict[str, Any] | str | None] | None = None

    def begin(self, attempt: int) -> None:
        """Rewind the files of the request before sending it again."""
        for file in self.request.files or ():
            file.reset(seek=attempt)

    def handle(self, response: Any, text: str, attempt: int) -> Done | Retry:
        """Decide what to do with a response whose status is ``response.status``."""
        route = self.request.route
        status: int = response.status
        _log.debug(
            "Webhook ID %s with %s %s has returned status code %s",
            route.webhook_id,
            route.method,
            route.url,
            status,
        )
        data = _decode(response.headers, text)
        self._last = (response, data)

        delta = exhausted_delay(response, status)
        if delta is not None:
            _log.debug(
                "Webhook ID %s has been pre-emptively rate limited, waiting %.2f seconds",
                route.webhook_id,
                delta,
            )
            self.hold = delta

        if 300 > status >= 200:
            return Done(data)

        if status == 429:
            if not response.headers.get("Via") or not isinstance(data, dict):
                raise HTTPException(response, data)
            retry_after = float(data["retry_after"])
            if data.get("global"):
                self.limits.block(retry_after)
            _log.warning(
                "Webhook ID %s is rate limited. Retrying in %.2f seconds",
                route.webhook_id,
                retry_after,
            )
            return self._retry(retry_after, attempt)

        if status >= 500:
            return self._retry(backoff(attempt), attempt)

        if status == 403:
            raise Forbidden(response, data)
        if status == 404:
            raise NotFound(response, data)
        raise HTTPException(response, data)

    def connection_error(self, exc: BaseException, attempt: int) -> Retry | None:
        """Return the retry for a connection error, or ``None`` if it is fatal."""
        if attempt < MAX_TRIES - 1 and is_connection_reset(exc):
            return Retry(backoff(attempt))
        return None

    def _retry(self, delay: float, attempt: int) -> Retry:
        if attempt >= MAX_TRIES - 1:
            self.give_up()
        return Retry(delay)

    def give_up(self) -> NoReturn:
        """Raise the error of the last response."""
        if self._last is None:
            raise RuntimeError("Unreachable code in HTTP handling.")
        response, data = self._last
        if response.status >= 500:
            raise DiscordServerError(response, data)
        raise HTTPException(response, data)


def webhook_request(
    method: str,
    webhook_id: int,
    token: str,
    *,
    authenticated: bool,
    payload: dict[str, Any] | None = None,
    reason: str | None = None,
) -> WebhookRequest:
    """Build a request on the webhook itself, with the bot or the webhook token."""
    if authenticated:
        return WebhookRequest(
            Route(method, _WEBHOOK, webhook_id=webhook_id),
            payload=payload,
            reason=reason,
            auth_token=token,
        )
    return WebhookRequest(
        Route(method, _WEBHOOK_SCOPED, webhook_id=webhook_id, webhook_token=token),
        payload=payload,
        reason=reason,
    )


def execute_request(
    webhook_id: int,
    token: str,
    *,
    payload: dict[str, Any] | None = None,
    multipart: list[dict[str, Any]] | None = None,
    files: list[File] | None = None,
    thread_id: int | None = None,
    with_components: bool | None = None,
    wait: bool = False,
) -> WebhookRequest:
    """Build the request executing a webhook."""
    params: dict[str, Any] = {"wait": int(wait)}
    if thread_id:
        params["thread_id"] = thread_id
    if with_components is not None:
        params["with_components"] = int(with_components)
    return WebhookRequest(
        Route(
            "POST",
            _WEBHOOK_SCOPED,
            webhook_id=webhook_id,
            webhook_token=token,
        ),
        payload=payload,
        multipart=multipart,
        files=files,
        params=params,
    )


def message_request(
    method: str,
    webhook_id: int,
    token: str,
    message_id: int,
    *,
    thread_id: int | None = None,
    payload: dict[str, Any] | None = None,
    multipart: list[dict[str, Any]] | None = None,
    files: list[File] | None = None,
    with_components: bool | None = None,
) -> WebhookRequest:
    """Build a request on a message sent by a webhook."""
    params: dict[str, Any] = {}
    if thread_id:
        params["thread_id"] = thread_id
    if with_components is not None:
        params["with_components"] = int(with_components)
    return WebhookRequest(
        Route(
            method,
            _MESSAGE,
            webhook_id=webhook_id,
            webhook_token=token,
            message_id=message_id,
        ),
        payload=payload,
        multipart=multipart,
        files=files,
        params=params,
    )


def original_response_request(
    method: str,
    application_id: int,
    token: str,
    *,
    payload: dict[str, Any] | None = None,
    multipart: list[dict[str, Any]] | None = None,
    files: list[File] | None = None,
) -> WebhookRequest:
    """Build a request on the original response of an interaction."""
    return WebhookRequest(
        Route(
            method,
            _ORIGINAL,
            webhook_id=application_id,
            webhook_token=token,
        ),
        payload=payload,
        multipart=multipart,
        files=files,
    )


def interaction_response_request(
    interaction_id: int,
    token: str,
    *,
    type: int,
    data: dict[str, Any] | None = None,
    files: list[File] | None = None,
) -> WebhookRequest:
    """Build the request responding to an interaction."""
    files = files or []
    payload: dict[str, Any] = {"type": type, "data": data if data is not None else {}}
    return WebhookRequest(
        Route(
            "POST",
            "/interactions/{webhook_id}/{webhook_token}/callback",
            webhook_id=interaction_id,
            webhook_token=token,
        ),
        multipart=multipart_form(payload, files, section="data", attach=bool(files)),
        files=files,
        params={"with_response": "true"},
    )


def parse_webhook_url(url: str) -> Any:
    """Return the data of the partial webhook that ``url`` points to."""
    match = _URL.search(url)
    if match is None:
        raise InvalidArgument("Invalid webhook URL given.")
    data: dict[str, Any] = match.groupdict()
    data["type"] = 1
    return data


def partial_webhook_data(id: int, token: str) -> Any:
    """Return the data of the partial webhook with this ``id`` and ``token``."""
    return {"id": id, "type": 1, "token": token}


class ExecuteWebhookParameters(NamedTuple):
    """The body of a message request, as JSON or as a multipart form."""

    payload: dict[str, Any] | None
    multipart: list[dict[str, Any]] | None
    files: list[File] | None


def handle_message_parameters(
    content: str | None = MISSING,
    *,
    username: str = MISSING,
    avatar_url: Any = MISSING,
    tts: bool = False,
    ephemeral: bool = False,
    file: File = MISSING,
    files: list[File] = MISSING,
    attachments: list[Attachment] = MISSING,
    embed: Embed | None = MISSING,
    embeds: list[Embed] = MISSING,
    view: BaseView | None = MISSING,
    poll: Poll | None = MISSING,
    applied_tags: list[Snowflake] = MISSING,
    allowed_mentions: AllowedMentions | None = MISSING,
    previous_allowed_mentions: AllowedMentions | None = None,
    suppress: bool | None = None,
    thread_name: str | None = None,
    suppress_embeds: bool | None = None,
    silent: bool = False,
) -> ExecuteWebhookParameters:
    """Validate the arguments of a message and build its body."""
    if files is not MISSING and file is not MISSING:
        raise TypeError("Cannot mix file and files keyword arguments.")
    if embeds is not MISSING and embed is not MISSING:
        raise TypeError("Cannot mix embed and embeds keyword arguments.")

    payload: dict[str, Any] = {}
    if embeds is not MISSING:
        if len(embeds) > 10:
            raise InvalidArgument("embeds has a maximum of 10 elements.")
        payload["embeds"] = [e.to_dict() for e in embeds]

    if embed is not MISSING:
        payload["embeds"] = [] if embed is None else [embed.to_dict()]
    if content is not MISSING:
        payload["content"] = str(content) if content is not None else None
    if attachments is not MISSING:
        payload["attachments"] = [a.to_dict() for a in attachments]
    if suppress is not None:
        utils.warn_deprecated("suppress", "suppress_embeds", "2.8")
        if suppress_embeds is None:
            suppress_embeds = suppress
    elif suppress_embeds is None:
        suppress_embeds = False
    flags = MessageFlags(
        suppress_embeds=suppress_embeds,
        ephemeral=ephemeral,
        suppress_notifications=silent,
    )

    if view is not MISSING:
        payload["components"] = view.to_components() if view is not None else []
        if view and view.is_components_v2():
            if payload.get("content") or payload.get("embeds"):
                raise TypeError(
                    "cannot send embeds or content with a view using v2 component logic"
                )
            flags.is_components_v2 = True
    if poll is not MISSING and poll is not None:
        payload["poll"] = poll.to_dict()
    payload["tts"] = tts
    if avatar_url:
        payload["avatar_url"] = str(avatar_url)
    if username:
        payload["username"] = username

    if applied_tags is not MISSING:
        payload["applied_tags"] = applied_tags

    if allowed_mentions:
        if previous_allowed_mentions is not None:
            payload["allowed_mentions"] = previous_allowed_mentions.merge(
                allowed_mentions
            ).to_dict()
        else:
            payload["allowed_mentions"] = allowed_mentions.to_dict()
    elif previous_allowed_mentions is not None:
        payload["allowed_mentions"] = previous_allowed_mentions.to_dict()

    if file is not MISSING:
        files = [file]

    if files and any(isinstance(f, VoiceMessage) for f in files):
        flags = flags + MessageFlags(is_voice_message=True)

    payload["flags"] = flags.value

    if thread_name:
        payload["thread_name"] = thread_name

    if files:
        return ExecuteWebhookParameters(
            payload=None, multipart=multipart_form(payload, files), files=files
        )
    return ExecuteWebhookParameters(payload=payload, multipart=[], files=files)


class _FriendlyHttpAttributeErrorHelper:
    __slots__ = ()

    def __getattr__(self, attr: str) -> Any:
        raise AttributeError("PartialWebhookState does not support http methods.")


class _NoCache:
    supports_sync = False


class _WebhookState:
    __slots__ = ("_parent", "_webhook")

    def __init__(
        self, webhook: Any, parent: ConnectionState | _WebhookState | None
    ) -> None:
        self._webhook: Any = webhook

        self._parent: ConnectionState | None
        self._parent = None if isinstance(parent, _WebhookState) else parent

    async def _get_guild(self, guild_id: int) -> Any:
        if self._parent is not None:
            return await self._parent._get_guild(guild_id)
        return None

    async def get_channel(self, id: int) -> Any:
        if self._parent is not None:
            return await self._parent.get_channel(id)
        return None

    async def store_user(self, data: Any) -> Any:
        if self._parent is not None:
            return await self._parent.store_user(data)
        return BaseUser(state=cast("ConnectionState", self), data=data)

    async def _populate_message(self, message: Any, data: Any) -> None:
        if self._parent is not None:
            await self._parent._populate_message(message, data)

    def create_user(self, data: Any) -> Any:
        return BaseUser(state=cast("ConnectionState", self), data=data)

    async def store_poll(self, poll: Poll, message_id: int) -> Any:
        if self._parent is not None:
            return await self._parent.store_poll(poll, message_id)
        return None

    @property
    def _messages(self) -> Any:
        if self._parent is not None:
            return self._parent._messages
        return None

    @property
    def cache(self) -> Any:
        if self._parent is not None:
            return self._parent.cache
        return _NoCache()

    @property
    def http(self) -> Any:
        if self._parent is not None:
            return self._parent.http
        return _FriendlyHttpAttributeErrorHelper()

    def __getattr__(self, attr: str) -> Any:
        if self._parent is not None:
            return getattr(self._parent, attr)

        raise AttributeError(f"PartialWebhookState does not support {attr!r}.")


def _thread_id(thread: Snowflake | None) -> int | None:
    if thread is None or thread is MISSING:
        return None
    return thread.id


class SendPlan(NamedTuple):
    """A prepared ``send``: its request and whether it returns the message."""

    request: WebhookRequest
    wait: bool


class WebhookRequests:
    """Builds the requests of a webhook, for the sync and the async webhooks."""

    __slots__ = ()

    id: int
    type: WebhookType
    token: str | None
    auth_token: str | None
    _state: Any

    def _require_token(self) -> str:
        if self.token is None:
            raise InvalidArgument(_NOT_USABLE)
        return self.token

    def _credentials(self, prefer_auth: bool) -> tuple[str, bool]:
        if prefer_auth and self.auth_token:
            return self.auth_token, True
        if self.token:
            return self.token, False
        if self.auth_token:
            return self.auth_token, True
        raise InvalidArgument(_NOT_USABLE)

    def _fetch_request(self, prefer_auth: bool) -> WebhookRequest:
        token, authenticated = self._credentials(prefer_auth)
        return webhook_request("GET", self.id, token, authenticated=authenticated)

    def _delete_request(self, reason: str | None, prefer_auth: bool) -> WebhookRequest:
        token, authenticated = self._credentials(prefer_auth)
        return webhook_request(
            "DELETE", self.id, token, authenticated=authenticated, reason=reason
        )

    def _edit_request(
        self,
        *,
        reason: str | None,
        name: str | None,
        avatar: bytes | None,
        channel: Snowflake | None,
        prefer_auth: bool,
    ) -> WebhookRequest:
        token, authenticated = self._credentials(prefer_auth)
        payload: dict[str, Any] = {}
        if name is not MISSING:
            payload["name"] = str(name) if name is not None else None

        if avatar is not MISSING:
            payload["avatar"] = (
                utils._bytes_to_base64_data(avatar) if avatar is not None else None
            )

        if channel is not None:
            if self.auth_token is None:
                raise InvalidArgument("Editing channel requires authenticated webhook")
            payload["channel_id"] = channel.id
            token, authenticated = self.auth_token, True
        return webhook_request(
            "PATCH",
            self.id,
            token,
            authenticated=authenticated,
            payload=payload,
            reason=reason,
        )

    def _check_view(self, view: BaseView | None) -> None:
        if isinstance(self._state, _WebhookState) and view and view.is_dispatchable():
            raise InvalidArgument(
                "Dispatchable Webhook views require an associated state with the webhook"
            )

    def _send_plan(
        self,
        content: str | None,
        *,
        username: str = MISSING,
        avatar_url: Any = MISSING,
        tts: bool = False,
        ephemeral: bool = False,
        file: File = MISSING,
        files: list[File] = MISSING,
        embed: Embed | None = MISSING,
        embeds: list[Embed] = MISSING,
        allowed_mentions: AllowedMentions | None = MISSING,
        view: BaseView | None = MISSING,
        poll: Poll | None = MISSING,
        thread: Snowflake | None = MISSING,
        thread_name: str | None = None,
        applied_tags: list[Snowflake] = MISSING,
        wait: bool = False,
        silent: bool = False,
        suppress: bool | None = None,
        suppress_embeds: bool | None = None,
    ) -> SendPlan:
        token = self._require_token()
        previous_mentions: AllowedMentions | None = getattr(
            self._state, "allowed_mentions", None
        )
        if content is None:
            content = MISSING

        if thread and thread_name:
            raise InvalidArgument("You cannot specify both a thread and thread_name")

        if applied_tags and not (thread or thread_name):
            raise InvalidArgument("You cannot specify applied_tags without a thread")

        application_webhook = self.type is WebhookType.application
        if ephemeral and not application_webhook:
            raise InvalidArgument(
                "ephemeral messages can only be sent from application webhooks"
            )

        if application_webhook:
            wait = True

        with_components = False
        if view is not MISSING:
            self._check_view(view)
            if ephemeral is True and view is not None and view.timeout is None:
                view.timeout = 15 * 60.0
            with_components = not application_webhook

        if poll is None:
            poll = MISSING

        params = handle_message_parameters(
            content=content,
            username=username,
            avatar_url=avatar_url,
            tts=tts,
            file=file,
            files=files,
            embed=embed,
            embeds=embeds,
            ephemeral=ephemeral,
            view=view,
            poll=poll,
            applied_tags=applied_tags,
            allowed_mentions=allowed_mentions,
            previous_allowed_mentions=previous_mentions,
            thread_name=thread_name,
            silent=silent,
            suppress=suppress,
            suppress_embeds=suppress_embeds,
        )
        request = execute_request(
            self.id,
            token,
            payload=params.payload,
            multipart=params.multipart,
            files=params.files,
            thread_id=_thread_id(thread),
            with_components=with_components,
            wait=wait,
        )
        return SendPlan(request, wait)

    def _fetch_message_request(
        self, message_id: int, thread_id: int | None
    ) -> WebhookRequest:
        token = self._require_token()
        return message_request("GET", self.id, token, message_id, thread_id=thread_id)

    def _edit_message_request(
        self,
        message_id: int,
        *,
        content: str | None = MISSING,
        embeds: list[Embed] = MISSING,
        embed: Embed | None = MISSING,
        file: File = MISSING,
        files: list[File] = MISSING,
        attachments: list[Attachment] = MISSING,
        view: BaseView | None = MISSING,
        allowed_mentions: AllowedMentions | None = None,
        thread: Snowflake | None = MISSING,
        suppress: bool | None = None,
        suppress_embeds: bool | None = None,
    ) -> WebhookRequest:
        token = self._require_token()
        with_components = False
        if view is not MISSING:
            self._check_view(view)
            with_components = self.type is not WebhookType.application
        previous_mentions: AllowedMentions | None = getattr(
            self._state, "allowed_mentions", None
        )
        params = handle_message_parameters(
            content=content,
            file=file,
            files=files,
            attachments=attachments,
            embed=embed,
            embeds=embeds,
            view=view,
            allowed_mentions=allowed_mentions,
            previous_allowed_mentions=previous_mentions,
            suppress=suppress,
            suppress_embeds=suppress_embeds,
        )
        return message_request(
            "PATCH",
            self.id,
            token,
            message_id,
            thread_id=_thread_id(thread),
            payload=params.payload,
            multipart=params.multipart,
            files=params.files,
            with_components=with_components,
        )

    def _delete_message_request(
        self, message_id: int, thread_id: int | None
    ) -> WebhookRequest:
        token = self._require_token()
        return message_request(
            "DELETE", self.id, token, message_id, thread_id=thread_id
        )
