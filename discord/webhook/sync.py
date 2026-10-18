"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz
Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Literal, cast, overload

from .. import utils
from ..channel import PartialMessageable
from ..http.ratelimit import MAX_TRIES
from ..message import Message
from ..object import Object
from ._core import (
    Done,
    Execution,
    WebhookLimits,
    WebhookRequest,
    _WebhookState,
    parse_webhook_url,
    partial_webhook_data,
)
from .async_ import BaseWebhook

__all__ = (
    "SyncWebhook",
    "SyncWebhookMessage",
)

from ..utils import warn_deprecated

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from requests import Session

    from ..abc import Snowflake
    from ..embeds import Embed
    from ..file import File
    from ..http import Route
    from ..mentions import AllowedMentions
    from ..state import ConnectionState
    from ..types.message import Message as MessagePayload
    from ..types.webhook import Webhook as WebhookPayload

MISSING = utils.MISSING


def _form(multipart: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    data: dict[str, Any] = {}
    files: dict[str, Any] = {}
    for field in multipart:
        if field["name"] == "payload_json":
            data["payload_json"] = field["value"]
        else:
            files[field["name"]] = (
                field["filename"],
                field["value"],
                field["content_type"],
            )
    return data, files


def _requests_session(session: Any) -> Session:
    import requests

    if session is MISSING:
        return cast("Session", requests)
    if not isinstance(session, requests.Session):
        raise TypeError(f"expected requests.Session not {session.__class__!r}")
    return session


class WebhookAdapter:
    def __init__(self) -> None:
        self._limits: WebhookLimits[threading.Lock] = WebhookLimits(threading.Lock)

    def execute(self, request: WebhookRequest, *, session: Session) -> Any:
        return self.request(
            request.route,
            session,
            payload=request.payload,
            multipart=request.multipart,
            files=request.files,
            reason=request.reason,
            auth_token=request.auth_token,
            params=request.params,
        )

    def request(
        self,
        route: Route,
        session: Session,
        *,
        payload: dict[str, Any] | None = None,
        multipart: list[dict[str, Any]] | None = None,
        files: list[File] | None = None,
        reason: str | None = None,
        auth_token: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        run = Execution(
            WebhookRequest(
                route, payload, multipart, files, reason, auth_token, params
            ),
            self._limits,
        )
        if delay := self._limits.global_delay():
            time.sleep(delay)

        with self._limits.lock_for(route):
            try:
                for attempt in range(MAX_TRIES):
                    run.begin(attempt)
                    data, file_data = (
                        _form(multipart) if multipart else (run.body, None)
                    )
                    try:
                        with session.request(
                            route.method,
                            route.url,
                            data=data,
                            files=file_data,
                            headers=run.headers,
                            params=params,
                        ) as response:
                            response.encoding = "utf-8"
                            cast("Any", response).status = response.status_code
                            step = run.handle(response, response.text, attempt)
                    except OSError as e:
                        step = run.connection_error(e, attempt)
                        if step is None:
                            raise
                    if isinstance(step, Done):
                        return step.data
                    time.sleep(step.delay)
                run.give_up()
            finally:
                if run.hold:
                    time.sleep(run.hold)


_adapter = WebhookAdapter()


class _NotAvailable:
    __slots__ = ("name",)

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        raise AttributeError(
            f"{(owner or type(instance)).__name__!r} object has no attribute {self.name!r}"
        )


class SyncWebhookMessage(Message):
    """Represents a message sent from your webhook.

    This allows you to edit or delete a message sent by your
    webhook.

    This inherits from :class:`discord.Message` with changes to
    :meth:`edit` and :meth:`delete` to work.

    .. versionadded:: 2.0
    """

    if TYPE_CHECKING:
        _thread_id: int

    get_channel: Any = _NotAvailable()
    get_guild: Any = _NotAvailable()
    get_poll: Any = _NotAvailable()
    get_channel_mentions: Any = _NotAvailable()
    get_role_mentions: Any = _NotAvailable()
    get_clean_content: Any = _NotAvailable()
    get_system_content: Any = _NotAvailable()
    search_replies: Any = _NotAvailable()

    def edit(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        content: str | None = MISSING,
        embeds: list[Embed] = MISSING,
        embed: Embed | None = MISSING,
        file: File = MISSING,
        files: list[File] = MISSING,
        allowed_mentions: AllowedMentions | None = None,
        suppress: bool | None = MISSING,
        suppress_embeds: bool | None = MISSING,
    ) -> SyncWebhookMessage:
        """Edits the message.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The content to edit the message with or ``None`` to clear it.
        embeds: List[:class:`Embed`]
            A list of embeds to edit the message with.
        embed: Optional[:class:`Embed`]
            The embed to edit the message with. ``None`` suppresses the embeds.
            This should not be mixed with the ``embeds`` parameter.
        file: :class:`File`
            The file to upload. This cannot be mixed with ``files`` parameter.
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        suppress: Optional[:class:`bool`]
            Whether to suppress embeds for the message.

            .. deprecated:: 2.8
        suppress_embeds: Optional[:class:`bool`]
            Whether to suppress embeds for the message.

            .. versionadded:: 2.8

        Returns
        -------
        :class:`SyncWebhookMessage`
            The newly edited message.

        Raises
        ------
        HTTPException
            Editing the message failed.
        Forbidden
            Edited a message that is not yours.
        TypeError
            You specified both ``embed`` and ``embeds`` or ``file`` and ``files``
        ValueError
            The length of ``embeds`` was invalid
        InvalidArgument
            There was no token associated with this webhook.
        """
        thread = MISSING
        if hasattr(self, "_thread_id"):
            thread = Object(self._thread_id)

        if suppress is not MISSING:
            warn_deprecated("suppress", "suppress_embeds", "2.8")
            if suppress_embeds is MISSING:
                suppress_embeds = suppress

        if suppress_embeds is MISSING:
            suppress_embeds = self.flags.suppress_embeds

        return cast("_WebhookState", self._state)._webhook.edit_message(
            self.id,
            content=content,
            embeds=embeds,
            embed=embed,
            file=file,
            files=files,
            allowed_mentions=allowed_mentions,
            thread=thread,
            suppress_embeds=suppress_embeds,
        )

    def delete(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, *, delay: float | None = None
    ) -> None:
        """Deletes the message.

        Parameters
        ----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait before deleting the message.
            This blocks the thread.

        Raises
        ------
        Forbidden
            You do not have proper permissions to delete the message.
        NotFound
            The message was deleted already.
        HTTPException
            Deleting the message failed.
        """
        thread_id: int | None = None
        if hasattr(self, "_thread_id"):
            thread_id = self._thread_id

        if delay is not None:
            time.sleep(delay)

        cast("_WebhookState", self._state)._webhook.delete_message(
            self.id, thread_id=thread_id
        )


class SyncWebhook(BaseWebhook):
    """Represents a synchronous Discord webhook.

    For an asynchronous counterpart, see :class:`Webhook`.

    .. container:: operations

        .. describe:: x == y

            Checks if two webhooks are equal.

        .. describe:: x != y

            Checks if two webhooks are not equal.

        .. describe:: hash(x)

            Returns the webhook's hash.

    .. versionchanged:: 1.4
        Webhooks are now comparable and hashable.

    Attributes
    ----------
    id: :class:`int`
        The webhook's ID
    type: :class:`WebhookType`
        The type of the webhook.

        .. versionadded:: 1.3

    token: Optional[:class:`str`]
        The authentication token of the webhook. If this is ``None``
        then the webhook cannot be used to make requests.
    guild_id: Optional[:class:`int`]
        The guild ID this webhook is for.
    channel_id: Optional[:class:`int`]
        The channel ID this webhook is for.
    user: Optional[:class:`abc.User`]
        The user this webhook was created by. If the webhook was
        received without authentication then this will be ``None``.
    name: Optional[:class:`str`]
        The default name of the webhook.
    source_guild: Optional[:class:`PartialWebhookGuild`]
        The guild of the channel that this webhook is following.
        Only given if :attr:`type` is :attr:`WebhookType.channel_follower`.

        .. versionadded:: 2.0

    source_channel: Optional[:class:`PartialWebhookChannel`]
        The channel that this webhook is following.
        Only given if :attr:`type` is :attr:`WebhookType.channel_follower`.

        .. versionadded:: 2.0
    """

    __slots__: tuple[str, ...] = ("session",)

    def __init__(
        self,
        data: WebhookPayload,
        session: Session,
        token: str | None = None,
        state: ConnectionState | _WebhookState | None = None,
    ) -> None:
        super().__init__(data, token, state)
        self.session = session

    def __repr__(self) -> str:
        return f"<Webhook id={self.id!r}>"

    @property
    def url(self) -> str:
        """Returns the webhook's url."""
        return f"https://discord.com/api/webhooks/{self.id}/{self.token}"

    @classmethod
    def partial(
        cls,
        id: int,
        token: str,
        *,
        session: Session = MISSING,
        bot_token: str | None = None,
    ) -> SyncWebhook:
        """Creates a partial :class:`Webhook`.

        Parameters
        ----------
        id: :class:`int`
            The ID of the webhook.
        token: :class:`str`
            The authentication token of the webhook.
        session: :class:`requests.Session`
            The session to use to send requests with. Note
            that the library does not manage the session and
            will not close it. If not given, the ``requests``
            auto session creation functions are used instead.
        bot_token: Optional[:class:`str`]
            The bot authentication token for authenticated requests
            involving the webhook.

        Returns
        -------
        :class:`Webhook`
            A partial :class:`Webhook`.
            A partial webhook is just a webhook object with an ID and a token.
        """
        data: WebhookPayload = partial_webhook_data(id, token)
        return cls(data, _requests_session(session), token=bot_token)

    @classmethod
    def from_url(
        cls, url: str, *, session: Session = MISSING, bot_token: str | None = None
    ) -> SyncWebhook:
        """Creates a partial :class:`Webhook` from a webhook URL.

        Parameters
        ----------
        url: :class:`str`
            The URL of the webhook.
        session: :class:`requests.Session`
            The session to use to send requests with. Note
            that the library does not manage the session and
            will not close it. If not given, the ``requests``
            auto session creation functions are used instead.
        bot_token: Optional[:class:`str`]
            The bot authentication token for authenticated requests
            involving the webhook.

        Returns
        -------
        :class:`Webhook`
            A partial :class:`Webhook`.
            A partial webhook is just a webhook object with an ID and a token.

        Raises
        ------
        InvalidArgument
            The URL is invalid.
        """
        data = parse_webhook_url(url)
        return cls(data, _requests_session(session), token=bot_token)

    def fetch(self, *, prefer_auth: bool = True) -> SyncWebhook:
        """Fetches the current webhook.

        This could be used to get a full webhook from a partial webhook.

        .. note::

            When fetching with an unauthenticated webhook, i.e.
            :meth:`is_authenticated` returns ``False``, then the
            returned webhook does not contain any user information.

        Parameters
        ----------
        prefer_auth: :class:`bool`
            Whether to use the bot token over the webhook token
            if available. Defaults to ``True``.

        Returns
        -------
        :class:`SyncWebhook`
            The fetched webhook.

        Raises
        ------
        HTTPException
            Could not fetch the webhook
        NotFound
            Could not find the webhook by this ID
        InvalidArgument
            This webhook does not have a token associated with it.
        """
        data = _adapter.execute(self._fetch_request(prefer_auth), session=self.session)
        return SyncWebhook(data, self.session, token=self.auth_token, state=self._state)

    def delete(self, *, reason: str | None = None, prefer_auth: bool = True) -> None:
        """Deletes this Webhook.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for deleting this webhook. Shows up on the audit log.

            .. versionadded:: 1.4
        prefer_auth: :class:`bool`
            Whether to use the bot token over the webhook token
            if available. Defaults to ``True``.

        Raises
        ------
        HTTPException
            Deleting the webhook failed.
        NotFound
            This webhook does not exist.
        Forbidden
            You do not have permissions to delete this webhook.
        InvalidArgument
            This webhook does not have a token associated with it.
        """
        _adapter.execute(
            self._delete_request(reason, prefer_auth), session=self.session
        )

    def edit(
        self,
        *,
        reason: str | None = None,
        name: str | None = MISSING,
        avatar: bytes | None = MISSING,
        channel: Snowflake | None = None,
        prefer_auth: bool = True,
    ) -> SyncWebhook:
        """Edits this Webhook.

        Parameters
        ----------
        name: Optional[:class:`str`]
            The webhook's new default name.
        avatar: Optional[:class:`bytes`]
            A :term:`py:bytes-like object` representing the webhook's new default avatar.
        channel: Optional[:class:`abc.Snowflake`]
            The webhook's new channel. This requires an authenticated webhook.
        reason: Optional[:class:`str`]
            The reason for editing this webhook. Shows up on the audit log.

            .. versionadded:: 1.4
        prefer_auth: :class:`bool`
            Whether to use the bot token over the webhook token
            if available. Defaults to ``True``.

        Returns
        -------
        :class:`SyncWebhook`
            The newly edited webhook.

        Raises
        ------
        HTTPException
            Editing the webhook failed.
        NotFound
            This webhook does not exist.
        InvalidArgument
            This webhook does not have a token associated with it, or
            it tried editing a channel without authentication.
        """
        data = _adapter.execute(
            self._edit_request(
                reason=reason,
                name=name,
                avatar=avatar,
                channel=channel,
                prefer_auth=prefer_auth,
            ),
            session=self.session,
        )
        return SyncWebhook(
            data=data, session=self.session, token=self.auth_token, state=self._state
        )

    def _create_message(self, data: MessagePayload) -> SyncWebhookMessage:
        state = _WebhookState(self, parent=self._state)
        # state may be artificial (unlikely at this point...)
        channel = PartialMessageable(
            state=cast("ConnectionState", self._state), id=int(data["channel_id"])
        )
        # state is artificial
        message = SyncWebhookMessage(
            data=data, state=cast("ConnectionState", state), channel=channel
        )
        if message.guild_id is None:
            message.guild_id = self.guild_id
        return message

    @overload
    def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Any = MISSING,
        tts: bool = MISSING,
        file: File = MISSING,
        files: list[File] = MISSING,
        embed: Embed = MISSING,
        embeds: list[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        thread: Snowflake = MISSING,
        thread_name: str | None = None,
        wait: Literal[True],
        suppress: bool | None = None,
        suppress_embeds: bool | None = None,
    ) -> SyncWebhookMessage: ...

    @overload
    def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Any = MISSING,
        tts: bool = MISSING,
        file: File = MISSING,
        files: list[File] = MISSING,
        embed: Embed = MISSING,
        embeds: list[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        thread: Snowflake = MISSING,
        thread_name: str | None = None,
        wait: Literal[False] = ...,
        suppress: bool | None = None,
        suppress_embeds: bool | None = None,
    ) -> None: ...

    def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Any = MISSING,
        tts: bool = False,
        file: File = MISSING,
        files: list[File] = MISSING,
        embed: Embed = MISSING,
        embeds: list[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        thread: Snowflake = MISSING,
        thread_name: str | None = None,
        wait: bool = False,
        suppress: bool | None = None,
        suppress_embeds: bool | None = None,
    ) -> SyncWebhookMessage | None:
        """Sends a message using the webhook.

        The content must be a type that can convert to a string through ``str(content)``.

        To upload a single file, the ``file`` parameter should be used with a
        single :class:`File` object.

        If the ``embed`` parameter is provided, it must be of type :class:`Embed` and
        it must be a rich embed type. You cannot mix the ``embed`` parameter with the
        ``embeds`` parameter, which must be a :class:`list` of :class:`Embed` objects to send.

        Parameters
        ----------
        content: :class:`str`
            The content of the message to send.
        wait: :class:`bool`
            Whether the server should wait before sending a response. This essentially
            means that the return type of this function changes from ``None`` to
            a :class:`WebhookMessage` if set to ``True``.
        username: :class:`str`
            The username to send with this message. If no username is provided
            then the default username for the webhook is used.
        avatar_url: :class:`str`
            The avatar URL to send with this message. If no avatar URL is provided
            then the default avatar for the webhook is used. If this is not a
            string then it is explicitly cast using ``str``.
        tts: :class:`bool`
            Indicates if the message should be sent using text-to-speech.
        file: :class:`File`
            The file to upload. This cannot be mixed with ``files`` parameter.
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.
        embed: :class:`Embed`
            The rich embed for the content to send. This cannot be mixed with
            ``embeds`` parameter.
        embeds: List[:class:`Embed`]
            A list of embeds to send with the content. Maximum of 10. This cannot
            be mixed with the ``embed`` parameter.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.

            .. versionadded:: 1.4
        thread: :class:`~discord.abc.Snowflake`
            The thread to send this message to.

            .. versionadded:: 2.0
        thread_name: :class:`str`
            The name of the thread to create. Only works for forum channels.

            .. versionadded:: 2.0
        suppress: :class:`bool`
            Whether to suppress embeds for the message.

            .. deprecated:: 2.8
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.

            .. versionadded:: 2.8

        Returns
        -------
        Optional[:class:`SyncWebhookMessage`]
            If ``wait`` is ``True`` then the message that was sent, otherwise ``None``.

        Raises
        ------
        HTTPException
            Sending the message failed.
        NotFound
            This webhook was not found.
        Forbidden
            The authorization token for the webhook is incorrect.
        TypeError
            You specified both ``embed`` and ``embeds`` or ``file`` and ``files``
        ValueError
            The length of ``embeds`` was invalid
        InvalidArgument
            There was no token associated with this webhook, or you specified both
            a thread to send to and a thread to create (the ``thread`` and ``thread_name`` parameters).
        """
        plan = self._send_plan(
            content,
            username=username,
            avatar_url=avatar_url,
            tts=tts,
            file=file,
            files=files,
            embed=embed,
            embeds=embeds,
            allowed_mentions=allowed_mentions,
            thread=thread,
            thread_name=thread_name,
            wait=wait,
            suppress=suppress,
            suppress_embeds=suppress_embeds,
        )
        data = _adapter.execute(plan.request, session=self.session)
        if plan.wait:
            return self._create_message(data)
        return None

    def fetch_message(
        self, id: int, *, thread_id: int | None = None
    ) -> SyncWebhookMessage:
        """Retrieves a single :class:`~discord.SyncWebhookMessage` owned by this webhook.

        .. versionadded:: 2.0

        Parameters
        ----------
        id: :class:`int`
            The message ID to look for.
        thread_id: Optional[:class:`int`]
            The ID of the thread that contains the message.

        Returns
        -------
        :class:`~discord.SyncWebhookMessage`
            The message asked for.

        Raises
        ------
        ~discord.NotFound
            The specified message was not found.
        ~discord.Forbidden
            You do not have the permissions required to get a message.
        ~discord.HTTPException
            Retrieving the message failed.
        InvalidArgument
            There was no token associated with this webhook.
        """
        data = _adapter.execute(
            self._fetch_message_request(id, thread_id), session=self.session
        )
        msg = self._create_message(data)
        if thread_id and isinstance(msg.channel, PartialMessageable):
            msg._thread_id = thread_id

        return msg

    def edit_message(
        self,
        message_id: int,
        *,
        content: str | None = MISSING,
        embeds: list[Embed] = MISSING,
        embed: Embed | None = MISSING,
        file: File = MISSING,
        files: list[File] = MISSING,
        allowed_mentions: AllowedMentions | None = None,
        thread: Snowflake | None = MISSING,
        suppress: bool | None = None,
        suppress_embeds: bool | None = None,
    ) -> SyncWebhookMessage:
        """Edits a message owned by this webhook.

        This is a lower level interface to :meth:`WebhookMessage.edit` in case
        you only have an ID.

        .. versionadded:: 1.6

        Parameters
        ----------
        message_id: :class:`int`
            The message ID to edit.
        content: Optional[:class:`str`]
            The content to edit the message with or ``None`` to clear it.
        embeds: List[:class:`Embed`]
            A list of embeds to edit the message with.
        embed: Optional[:class:`Embed`]
            The embed to edit the message with. ``None`` suppresses the embeds.
            This should not be mixed with the ``embeds`` parameter.
        file: :class:`File`
            The file to upload. This cannot be mixed with ``files`` parameter.
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        thread: Optional[:class:`~discord.abc.Snowflake`]
            The thread that contains the message.
        suppress: :class:`bool`
            Whether to suppress embeds for the message.

            .. deprecated:: 2.8
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.

            .. versionadded:: 2.8

        Raises
        ------
        HTTPException
            Editing the message failed.
        Forbidden
            Edited a message that is not yours.
        TypeError
            You specified both ``embed`` and ``embeds`` or ``file`` and ``files``
        ValueError
            The length of ``embeds`` was invalid
        InvalidArgument
            There was no token associated with this webhook.
        """
        request = self._edit_message_request(
            message_id,
            content=content,
            embeds=embeds,
            embed=embed,
            file=file,
            files=files,
            allowed_mentions=allowed_mentions,
            thread=thread,
            suppress=suppress,
            suppress_embeds=suppress_embeds,
        )
        data = _adapter.execute(request, session=self.session)
        return self._create_message(data)

    def delete_message(self, message_id: int, *, thread_id: int | None = None) -> None:
        """Deletes a message owned by this webhook.

        This is a lower level interface to :meth:`WebhookMessage.delete` in case
        you only have an ID.

        .. versionadded:: 1.6

        Parameters
        ----------
        message_id: :class:`int`
            The message ID to delete.
        thread_id: Optional[:class:`int`]
            The ID of the thread that contains the message.

        Raises
        ------
        HTTPException
            Deleting the message failed.
        Forbidden
            Deleted a message that is not yours.
        """
        _adapter.execute(
            self._delete_message_request(message_id, thread_id), session=self.session
        )
