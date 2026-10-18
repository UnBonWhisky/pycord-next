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

import asyncio
import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Literal, cast, overload

import aiohttp

from .. import utils
from .._internal.cache_peek import cached_guild
from ..asset import Asset
from ..channel import ForumChannel, PartialMessageable
from ..enums import WebhookType, try_enum
from ..http.ratelimit import MAX_TRIES
from ..message import Attachment, Message
from ..mixins import Hashable
from ..object import Object
from ..threads import Thread
from ..user import BaseUser, User
from . import _core
from ._core import (
    Done,
    Execution,
    WebhookLimits,
    WebhookRequest,
    WebhookRequests,
    _WebhookState,
    interaction_response_request,
    original_response_request,
    parse_webhook_url,
    partial_webhook_data,
)

__all__ = (
    "PartialWebhookChannel",
    "PartialWebhookGuild",
    "Webhook",
    "WebhookMessage",
)

from ..utils import warn_deprecated

_log = logging.getLogger(__name__)

if TYPE_CHECKING:
    import datetime as dt

    from ..abc import Snowflake
    from ..channel import TextChannel
    from ..embeds import Embed
    from ..file import File
    from ..guild import Guild, PartialGuild
    from ..http import Response, Route
    from ..interactions import Interaction
    from ..mentions import AllowedMentions
    from ..poll import Poll
    from ..state import ConnectionState
    from ..types.channel import PartialChannel
    from ..types.message import Message as MessagePayload
    from ..types.webhook import (
        FollowerWebhook as FollowerWebhookPayload,
        SourceGuild as SourceGuildPayload,
        Webhook as WebhookPayload,
    )
    from ..ui.view import BaseView, DesignerView, View
    from ..user import ClientUser, User as UserModel

MISSING = utils.MISSING
handle_message_parameters = _core.handle_message_parameters


def _form(multipart: list[dict[str, Any]]) -> aiohttp.FormData:
    form_data = aiohttp.FormData(quote_fields=False)
    for field in multipart:
        form_data.add_field(**field)
    return form_data


class AsyncWebhookAdapter:
    def __init__(self) -> None:
        self._limits: WebhookLimits[asyncio.Lock] = WebhookLimits(asyncio.Lock)

    async def execute(
        self,
        request: WebhookRequest,
        *,
        session: aiohttp.ClientSession,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None,
    ) -> Any:
        return await self.request(
            request.route,
            session,
            payload=request.payload,
            multipart=request.multipart,
            proxy=proxy,
            proxy_auth=proxy_auth,
            files=request.files,
            reason=request.reason,
            auth_token=request.auth_token,
            params=request.params,
        )

    async def request(
        self,
        route: Route,
        session: aiohttp.ClientSession,
        *,
        payload: dict[str, Any] | None = None,
        multipart: list[dict[str, Any]] | None = None,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None,
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
            await asyncio.sleep(delay)

        async with self._limits.lock_for(route):
            try:
                for attempt in range(MAX_TRIES):
                    run.begin(attempt)
                    try:
                        async with session.request(
                            route.method,
                            route.url,
                            data=_form(multipart) if multipart else run.body,
                            headers=run.headers,
                            params=params,
                            proxy=proxy,
                            proxy_auth=proxy_auth,
                        ) as response:
                            step = run.handle(
                                response, await response.text(encoding="utf-8"), attempt
                            )
                    except OSError as e:
                        step = run.connection_error(e, attempt)
                        if step is None:
                            raise
                    if isinstance(step, Done):
                        return step.data
                    await asyncio.sleep(step.delay)
                run.give_up()
            finally:
                if run.hold:
                    await asyncio.sleep(run.hold)

    def create_interaction_response(
        self,
        interaction_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None,
        type: int,
        data: dict[str, Any] | None = None,
        files: list[File] | None = None,
    ) -> Response[None]:
        request = interaction_response_request(
            interaction_id, token, type=type, data=data, files=files
        )
        return self.execute(
            request, session=session, proxy=proxy, proxy_auth=proxy_auth
        )

    def get_original_interaction_response(
        self,
        application_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None,
    ) -> Response[MessagePayload]:
        request = original_response_request("GET", application_id, token)
        return self.execute(
            request, session=session, proxy=proxy, proxy_auth=proxy_auth
        )

    def edit_original_interaction_response(
        self,
        application_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None,
        payload: dict[str, Any] | None = None,
        multipart: list[dict[str, Any]] | None = None,
        files: list[File] | None = None,
    ) -> Response[MessagePayload]:
        request = original_response_request(
            "PATCH",
            application_id,
            token,
            payload=payload,
            multipart=multipart,
            files=files,
        )
        return self.execute(
            request, session=session, proxy=proxy, proxy_auth=proxy_auth
        )

    def delete_original_interaction_response(
        self,
        application_id: int,
        token: str,
        *,
        session: aiohttp.ClientSession,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None,
    ) -> Response[None]:
        request = original_response_request("DELETE", application_id, token)
        return self.execute(
            request, session=session, proxy=proxy, proxy_auth=proxy_auth
        )


_default_adapter = AsyncWebhookAdapter()
async_context: ContextVar[AsyncWebhookAdapter] = ContextVar(
    "async_webhook_context", default=_default_adapter
)


class PartialWebhookChannel(Hashable):
    """Represents a partial channel for webhooks.

    These are typically given for channel follower webhooks.

    .. versionadded:: 2.0

    Attributes
    ----------
    id: :class:`int`
        The partial channel's ID.
    name: :class:`str`
        The partial channel's name.
    """

    __slots__ = ("id", "name")

    def __init__(self, *, data: PartialChannel) -> None:
        self.id: int = int(data["id"])
        self.name: str = data["name"]

    def __repr__(self) -> str:
        return f"<PartialWebhookChannel name={self.name!r} id={self.id}>"


class PartialWebhookGuild(Hashable):
    """Represents a partial guild for webhooks.

    These are typically given for channel follower webhooks.

    .. versionadded:: 2.0

    Attributes
    ----------
    id: :class:`int`
        The partial guild's ID.
    name: :class:`str`
        The partial guild's name.
    """

    __slots__ = ("_icon", "_state", "id", "name")

    def __init__(
        self,
        *,
        data: SourceGuildPayload,
        state: ConnectionState | _WebhookState,
    ) -> None:
        self._state: ConnectionState | _WebhookState = state
        self.id: int = int(data["id"])
        self.name: str = data["name"]
        self._icon: str | None = data["icon"]

    def __repr__(self) -> str:
        return f"<PartialWebhookGuild name={self.name!r} id={self.id}>"

    @property
    def icon(self) -> Asset | None:
        """Returns the guild's icon asset, if available."""
        if self._icon is None:
            return None
        return Asset._from_guild_icon(
            cast("ConnectionState", self._state), self.id, self._icon
        )


class WebhookMessage(Message):
    """Represents a message sent from your webhook.

    This allows you to edit or delete a message sent by your
    webhook.

    This inherits from :class:`discord.Message` with changes to
    :meth:`edit` and :meth:`delete` to work.

    .. versionadded:: 1.6
    """

    if TYPE_CHECKING:
        _thread_id: int

    async def edit(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        content: str | None = MISSING,
        embeds: list[Embed] = MISSING,
        embed: Embed | None = MISSING,
        file: File = MISSING,
        files: list[File] = MISSING,
        attachments: list[Attachment] = MISSING,
        view: BaseView | None = MISSING,
        allowed_mentions: AllowedMentions | None = None,
        suppress: bool | None = MISSING,
        suppress_embeds: bool | None = MISSING,
    ) -> WebhookMessage:
        """|coro|

        Edits the message.

        .. versionadded:: 1.6

        .. versionchanged:: 2.0
            The edit is no longer in-place, instead the newly edited message is returned.

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

            .. versionadded:: 2.0
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.

            .. versionadded:: 2.0
        attachments: List[:class:`Attachment`]
            A list of attachments to keep in the message. If ``[]`` is passed
            then all attachments are removed.

            .. versionadded:: 2.0
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        view: Optional[:class:`~discord.ui.BaseView`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.

            .. versionadded:: 2.0
        suppress: Optional[:class:`bool`]
            Whether to suppress embeds for the message.

            .. deprecated:: 2.8
        suppress_embeds: Optional[:class:`bool`]
            Whether to suppress embeds for the message.

            .. versionadded:: 2.8

        Returns
        -------
        :class:`WebhookMessage`
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
        else:
            channel = await self.get_channel()
            if isinstance(channel, Thread):
                thread = Object(channel.id)
            elif isinstance(channel, ForumChannel):
                thread = Object(self.id)

        if attachments is MISSING:
            attachments = self.attachments or MISSING

        if suppress is not MISSING:
            warn_deprecated("suppress", "suppress_embeds", "2.8")
            if suppress_embeds is MISSING:
                suppress_embeds = suppress

        if suppress_embeds is MISSING:
            suppress_embeds = self.flags.suppress_embeds

        return await cast("_WebhookState", self._state)._webhook.edit_message(
            self.id,
            content=content,
            embeds=embeds,
            embed=embed,
            file=file,
            files=files,
            attachments=attachments,
            view=view,
            allowed_mentions=allowed_mentions,
            thread=thread,
            suppress_embeds=suppress_embeds,
        )

    async def delete(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, *, delay: float | None = None
    ) -> None:
        """|coro|

        Deletes the message.

        Parameters
        ----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait before deleting the message.
            The waiting is done in the background and deletion failures are ignored.

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
        else:
            channel = await self.get_channel()
            if isinstance(channel, Thread):
                thread_id = channel.id

        webhook = cast("_WebhookState", self._state)._webhook
        if delay is not None:
            utils.delay_task(
                delay, webhook.delete_message(self.id, thread_id=thread_id)
            )
        else:
            await webhook.delete_message(self.id, thread_id=thread_id)


class BaseWebhook(WebhookRequests, Hashable):
    __slots__: tuple[str, ...] = (
        "_avatar",
        "_state",
        "auth_token",
        "channel_id",
        "guild_id",
        "id",
        "name",
        "parent",
        "source_channel",
        "source_guild",
        "token",
        "type",
        "user",
    )

    def __init__(
        self,
        data: WebhookPayload | FollowerWebhookPayload,
        token: str | None = None,
        state: ConnectionState | _WebhookState | None = None,
    ) -> None:
        self.auth_token: str | None = token
        self._state: ConnectionState | _WebhookState = state or _WebhookState(
            self, parent=state
        )
        self._update(data)

    def _update(self, data: WebhookPayload | FollowerWebhookPayload) -> None:
        self.id = int(data["id"])
        self.type = try_enum(WebhookType, int(data["type"]))
        self.channel_id = utils._get_as_snowflake(data, "channel_id")
        self.guild_id = utils._get_as_snowflake(data, "guild_id")
        self.name = data.get("name")
        self._avatar = data.get("avatar")
        self.token = data.get("token")

        user = data.get("user")
        self.user: BaseUser | User | None = None
        if user is not None:
            # state parameter may be _WebhookState
            self.user = User(state=cast("ConnectionState", self._state), data=user)

        source_channel = data.get("source_channel")
        self.source_channel: PartialWebhookChannel | None = (
            PartialWebhookChannel(data=source_channel) if source_channel else None
        )

        source_guild = data.get("source_guild")
        self.source_guild: PartialWebhookGuild | None = (
            PartialWebhookGuild(data=source_guild, state=self._state)
            if source_guild
            else None
        )

    def is_partial(self) -> bool:
        """Whether the webhook is a "partial" webhook.

        .. versionadded:: 2.0
        """
        return self.channel_id is None

    def is_authenticated(self) -> bool:
        """Whether the webhook is authenticated with a bot token.

        .. versionadded:: 2.0
        """
        return self.auth_token is not None

    def _cache_state(self) -> ConnectionState | None:
        state = self._state
        if isinstance(state, _WebhookState):
            return state._parent
        return state

    @property
    def guild(self) -> Guild | PartialGuild | None:
        """The guild this webhook belongs to.

        If this is a partial webhook, then this will always return ``None``.

        This is a :class:`PartialGuild` when the guild is not cached or when the
        cache is not held in-process.
        """
        from ..guild import PartialGuild

        if self.guild_id is None:
            return None
        state = self._cache_state()
        guild = None if state is None else cached_guild(state, self.guild_id)
        if guild is not None:
            return guild
        return PartialGuild(
            state=cast("ConnectionState", self._state), id=self.guild_id
        )

    @property
    def channel(self) -> TextChannel | PartialMessageable | None:
        """The text channel this webhook belongs to.

        If this is a partial webhook, then this will always return ``None``.

        This is a :class:`PartialMessageable` when the channel is not cached or when
        the cache is not held in-process.
        """
        if self.channel_id is None:
            return None
        state = self._cache_state()
        if (
            state is not None
            and state.cache.supports_sync
            and self.guild_id is not None
        ):
            channel = state._guild_bucket("channels", self.guild_id).get_nowait(
                self.channel_id
            )
            if channel is not None:
                return channel
        return PartialMessageable(
            state=cast("ConnectionState", self._state), id=self.channel_id
        )

    @property
    def created_at(self) -> dt.datetime:
        """Returns the webhook's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def avatar(self) -> Asset:
        """Returns an :class:`Asset` for the avatar the webhook has.

        If the webhook does not have a traditional avatar, an asset for
        the default avatar is returned instead.
        """
        if self._avatar is None:
            # Default is always blurple apparently
            return Asset._from_default_avatar(cast("ConnectionState", self._state), 0)
        return Asset._from_avatar(
            cast("ConnectionState", self._state), self.id, self._avatar
        )


class Webhook(BaseWebhook):
    """Represents an asynchronous Discord webhook.

    Webhooks are a form to send messages to channels in Discord without a
    bot user or authentication.

    There are two main ways to use Webhooks. The first is through the ones
    received by the library such as :meth:`.Guild.webhooks` and
    :meth:`.TextChannel.webhooks`. The ones received by the library will
    automatically be bound using the library's internal HTTP session.

    The second form involves creating a webhook object manually using the
    :meth:`~.Webhook.from_url` or :meth:`~.Webhook.partial` classmethods.

    For example, creating a webhook from a URL and using :doc:`aiohttp <aio:index>`:

    .. code-block:: python3

        from discord import Webhook
        import aiohttp


        async def foo():
            async with aiohttp.ClientSession() as session:
                webhook = Webhook.from_url("url-here", session=session)
                await webhook.send("Hello World", username="Foo")

    For a synchronous counterpart, see :class:`SyncWebhook`.

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

    parent: Optional[:class:`Interaction`]
        The interaction this webhook belongs to.
        Only set if :attr:`type` is :attr:`WebhookType.application`.

        .. versionadded:: 2.7
    """

    __slots__: tuple[str, ...] = ("proxy", "proxy_auth", "session")

    async def get_guild(self) -> Guild | None:
        """|coro|

        Returns the cached guild this webhook belongs to.

        If this is a partial webhook, then this will always return ``None``.

        .. versionadded:: 3.0
        """
        state = self._cache_state()
        if state is None or self.guild_id is None:
            return None
        return await state._get_guild(self.guild_id)

    async def get_channel(self) -> TextChannel | None:
        """|coro|

        Returns the cached text channel this webhook belongs to.

        If this is a partial webhook, then this will always return ``None``.

        .. versionadded:: 3.0
        """
        state = self._cache_state()
        if state is None or self.guild_id is None or self.channel_id is None:
            return None
        return await state._guild_bucket("channels", self.guild_id).get(self.channel_id)

    def __init__(
        self,
        data: WebhookPayload | FollowerWebhookPayload,
        session: aiohttp.ClientSession,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None,
        token: str | None = None,
        state: ConnectionState | _WebhookState | None = None,
        parent: Interaction | None = None,
    ) -> None:
        super().__init__(data, token, state)
        self.session = session
        self.proxy: str | None = proxy
        self.proxy_auth: aiohttp.BasicAuth | None = proxy_auth
        self.parent: Interaction | None = parent

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
        session: aiohttp.ClientSession,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None,
        bot_token: str | None = None,
    ) -> Webhook:
        """Creates a partial :class:`Webhook`.

        Parameters
        ----------
        id: :class:`int`
            The ID of the webhook.
        token: :class:`str`
            The authentication token of the webhook.
        session: :class:`aiohttp.ClientSession`
            The session to use to send requests with. Note
            that the library does not manage the session and
            will not close it.

            .. versionadded:: 2.0
        bot_token: Optional[:class:`str`]
            The bot authentication token for authenticated requests
            involving the webhook.

            .. versionadded:: 2.0

        Returns
        -------
        :class:`Webhook`
            A partial :class:`Webhook`.
            A partial webhook is just a webhook object with an ID and a token.
        """
        data: WebhookPayload = partial_webhook_data(id, token)
        return cls(data, session, proxy=proxy, proxy_auth=proxy_auth, token=bot_token)

    @classmethod
    def from_url(
        cls,
        url: str,
        *,
        session: aiohttp.ClientSession,
        proxy: str | None = None,
        proxy_auth: aiohttp.BasicAuth | None = None,
        bot_token: str | None = None,
    ) -> Webhook:
        """Creates a partial :class:`Webhook` from a webhook URL.

        Parameters
        ----------
        url: :class:`str`
            The URL of the webhook.
        session: :class:`aiohttp.ClientSession`
            The session to use to send requests with. Note
            that the library does not manage the session and
            will not close it.

            .. versionadded:: 2.0
        bot_token: Optional[:class:`str`]
            The bot authentication token for authenticated requests
            involving the webhook.

            .. versionadded:: 2.0

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
        return cls(data, session, proxy=proxy, proxy_auth=proxy_auth, token=bot_token)

    @classmethod
    def _as_follower(
        cls, data: Any, *, channel: TextChannel, user: ClientUser | UserModel
    ) -> Webhook:
        name = f"{channel.guild} #{channel}"
        feed: WebhookPayload = {
            "id": data["webhook_id"],
            "type": 2,
            "name": name,
            "channel_id": channel.id,
            "guild_id": channel.guild.id,
            "user": {
                "username": user.name,
                "discriminator": user.discriminator,
                "global_name": user.global_name,
                "id": user.id,
                "avatar": user._avatar,
            },
        }

        state = channel._state
        http = state.http
        session = http._session
        proxy_auth = http.proxy_auth
        proxy = http.proxy
        return cls(
            feed,
            session=session,
            state=state,
            proxy_auth=proxy_auth,
            proxy=proxy,
            token=state.http.token,
        )

    @classmethod
    def from_state(
        cls, data: WebhookPayload | FollowerWebhookPayload, state: ConnectionState
    ) -> Webhook:
        """Creates a :class:`Webhook` bound to the HTTP session of a connection state.

        Parameters
        ----------
        data: dict[:class:`str`, Any]
            The webhook payload.
        state: :class:`ConnectionState`
            The connection state whose HTTP session is used.

        Returns
        -------
        :class:`Webhook`
            The webhook.
        """
        http = state.http
        session = http._session
        proxy_auth = http.proxy_auth
        proxy = http.proxy
        return cls(
            data,
            session=session,
            state=state,
            proxy_auth=proxy_auth,
            proxy=proxy,
            token=state.http.token,
        )

    @classmethod
    def from_interaction(cls, interaction: Interaction) -> Webhook:
        """Creates a :class:`Webhook` for the application of an interaction.

        Parameters
        ----------
        interaction: :class:`Interaction`
            The interaction to create the webhook from.

        Returns
        -------
        :class:`Webhook`
            The webhook, authenticated with the interaction token.
        """
        state = interaction._state
        data: WebhookPayload = {
            "id": interaction.application_id,
            "type": 3,
            "token": interaction.token,
        }
        http = state.http
        session = http._session
        proxy_auth = http.proxy_auth
        proxy = http.proxy
        return cls(
            data,
            session=session,
            state=state,
            proxy_auth=proxy_auth,
            proxy=proxy,
            token=state.http.token,
            parent=interaction,
        )

    async def fetch(self, *, prefer_auth: bool = True) -> Webhook:
        """|coro|

        Fetches the current webhook.

        This could be used to get a full webhook from a partial webhook.

        .. versionadded:: 2.0

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
        :class:`Webhook`
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
        data = await async_context.get().execute(
            self._fetch_request(prefer_auth),
            session=self.session,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
        )

        return Webhook(
            data,
            session=self.session,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
            token=self.auth_token,
            state=self._state,
        )

    async def delete(
        self, *, reason: str | None = None, prefer_auth: bool = True
    ) -> None:
        """|coro|

        Deletes this Webhook.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for deleting this webhook. Shows up on the audit log.

            .. versionadded:: 1.4
        prefer_auth: :class:`bool`
            Whether to use the bot token over the webhook token
            if available. Defaults to ``True``.

            .. versionadded:: 2.0

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
        await async_context.get().execute(
            self._delete_request(reason, prefer_auth),
            session=self.session,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
        )

    async def edit(
        self,
        *,
        reason: str | None = None,
        name: str | None = MISSING,
        avatar: bytes | None = MISSING,
        channel: Snowflake | None = None,
        prefer_auth: bool = True,
    ) -> Webhook:
        """|coro|

        Edits this Webhook.

        Parameters
        ----------
        name: Optional[:class:`str`]
            The webhook's new default name.
        avatar: Optional[:class:`bytes`]
            A :term:`py:bytes-like object` representing the webhook's new default avatar.
        channel: Optional[:class:`abc.Snowflake`]
            The webhook's new channel. This requires an authenticated webhook.

            .. versionadded:: 2.0
        reason: Optional[:class:`str`]
            The reason for editing this webhook. Shows up on the audit log.

            .. versionadded:: 1.4
        prefer_auth: :class:`bool`
            Whether to use the bot token over the webhook token
            if available. Defaults to ``True``.

            .. versionadded:: 2.0

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
        data = await async_context.get().execute(
            self._edit_request(
                reason=reason,
                name=name,
                avatar=avatar,
                channel=channel,
                prefer_auth=prefer_auth,
            ),
            session=self.session,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
        )

        return Webhook(
            data,
            session=self.session,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
            token=self.auth_token,
            state=self._state,
        )

    async def _create_message(self, data: MessagePayload) -> WebhookMessage:
        state = _WebhookState(self, parent=self._state)
        # state may be artificial (unlikely at this point...)
        channel = PartialMessageable(
            state=cast("ConnectionState", self._state), id=int(data["channel_id"])
        )
        # state is artificial
        message = WebhookMessage(
            data=data, state=cast("ConnectionState", state), channel=channel
        )
        if message.guild_id is None:
            message.guild_id = self.guild_id
        await state._populate_message(message, data)
        return message

    @overload
    async def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Any = MISSING,
        tts: bool = MISSING,
        ephemeral: bool = MISSING,
        file: File = MISSING,
        files: list[File] = MISSING,
        embed: Embed = MISSING,
        embeds: list[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        view: BaseView = MISSING,
        poll: Poll = MISSING,
        thread: Snowflake = MISSING,
        thread_name: str | None = None,
        applied_tags: list[Snowflake] = MISSING,
        wait: Literal[True],
        delete_after: float | None = None,
        silent: bool = False,
        suppress_embeds: bool = False,
    ) -> WebhookMessage: ...

    @overload
    async def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Any = MISSING,
        tts: bool = MISSING,
        ephemeral: bool = MISSING,
        file: File = MISSING,
        files: list[File] = MISSING,
        embed: Embed = MISSING,
        embeds: list[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        view: BaseView = MISSING,
        poll: Poll = MISSING,
        thread: Snowflake = MISSING,
        thread_name: str | None = None,
        applied_tags: list[Snowflake] = MISSING,
        wait: Literal[False] = ...,
        delete_after: float | None = None,
        silent: bool = False,
        suppress_embeds: bool = False,
    ) -> None: ...

    async def send(
        self,
        content: str = MISSING,
        *,
        username: str = MISSING,
        avatar_url: Any = MISSING,
        tts: bool = False,
        ephemeral: bool = False,
        file: File = MISSING,
        files: list[File] = MISSING,
        embed: Embed = MISSING,
        embeds: list[Embed] = MISSING,
        allowed_mentions: AllowedMentions = MISSING,
        view: BaseView = MISSING,
        poll: Poll = MISSING,
        thread: Snowflake = MISSING,
        thread_name: str | None = None,
        applied_tags: list[Snowflake] = MISSING,
        wait: bool = False,
        delete_after: float | None = None,
        silent: bool = False,
        suppress_embeds: bool = False,
    ) -> WebhookMessage | None:
        """|coro|

        Sends a message using the webhook.

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
            a :class:`WebhookMessage` if set to ``True``. If the type of webhook
            is :attr:`WebhookType.application` then this is always set to ``True``.
        username: :class:`str`
            The username to send with this message. If no username is provided
            then the default username for the webhook is used.
        avatar_url: :class:`str`
            The avatar URL to send with this message. If no avatar URL is provided
            then the default avatar for the webhook is used. If this is not a
            string then it is explicitly cast using ``str``.
        tts: :class:`bool`
            Indicates if the message should be sent using text-to-speech.
        ephemeral: :class:`bool`
            Indicates if the message should only be visible to the user.
            This is only available to :attr:`WebhookType.application` webhooks.
            If a view is sent with an ephemeral message, and it has no timeout set
            then the timeout is set to 15 minutes.

            .. versionadded:: 2.0
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
        view: :class:`discord.ui.BaseView`
            The view to send with the message. You can only send a view
            if this webhook is not partial and has state attached. A
            webhook has state attached if the webhook is managed by the
            library.

            .. versionadded:: 2.0
        thread: :class:`~discord.abc.Snowflake`
            The thread to send this webhook to.

            .. versionadded:: 2.0
        thread_name: :class:`str`
            The name of the thread to create. Only works for forum channels.

            .. versionadded:: 2.0
        applied_tags: List[:class:`Snowflake`]
            A list of tags to apply to the message. Only works for threads.

            .. versionadded:: 2.5
        delete_after: :class:`float`
            If provided, the number of seconds to wait in the background
            before deleting the message we just sent.
        poll: :class:`Poll`
            The poll to send.

            .. versionadded:: 2.6
        silent: :class:`bool`
            Whether to suppress push and desktop notifications for the message.

            .. versionadded:: 2.8
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.

            .. versionadded:: 2.8

        Returns
        -------
        Optional[:class:`WebhookMessage`]
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
            You specified both ``embed`` and ``embeds`` or ``file`` and ``files``.
        ValueError
            The length of ``embeds`` was invalid.
        InvalidArgument
            Either there was no token associated with this webhook, ``ephemeral`` was passed
            with the improper webhook type, there was no state attached with this webhook when
            giving it a dispatchable view, you specified both ``thread_name`` and ``thread``,
            or ``applied_tags`` was passed with neither ``thread_name`` nor ``thread`` specified.
        """
        plan = self._send_plan(
            content,
            username=username,
            avatar_url=avatar_url,
            tts=tts,
            ephemeral=ephemeral,
            file=file,
            files=files,
            embed=embed,
            embeds=embeds,
            allowed_mentions=allowed_mentions,
            view=view,
            poll=poll,
            thread=thread,
            thread_name=thread_name,
            applied_tags=applied_tags,
            wait=wait,
            silent=silent,
            suppress_embeds=suppress_embeds,
        )
        data = await async_context.get().execute(
            plan.request,
            session=self.session,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
        )

        msg = None
        if plan.wait:
            msg = await self._create_message(data)

        if view and not view.is_finished():
            message_id = None if msg is None else msg.id
            view.message = None if msg is None else msg
            if self.parent and not view.parent:
                view.parent = self.parent
            if msg:
                cast("View | DesignerView", view)._refresh(msg.components)
            if view.is_dispatchable():
                self._state.store_view(view, message_id)

        if delete_after is not None and msg is not None:
            utils.delay_task(delete_after, msg.delete())

        return msg

    async def fetch_message(
        self, id: int, *, thread_id: int | None = None
    ) -> WebhookMessage:
        """|coro|

        Retrieves a single :class:`~discord.WebhookMessage` owned by this webhook.

        .. versionadded:: 2.0

        Parameters
        ----------
        id: :class:`int`
            The message ID to look for.
        thread_id: Optional[:class:`int`]
            The ID of the thread that contains the message.

        Returns
        -------
        :class:`~discord.WebhookMessage`
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
        data = await async_context.get().execute(
            self._fetch_message_request(id, thread_id),
            session=self.session,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
        )
        msg = await self._create_message(data)
        if thread_id and isinstance(msg.channel, PartialMessageable):
            msg._thread_id = thread_id

        return msg

    async def edit_message(
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
    ) -> WebhookMessage:
        """|coro|

        Edits a message owned by this webhook.

        This is a lower level interface to :meth:`WebhookMessage.edit` in case
        you only have an ID.

        .. versionadded:: 1.6

        .. versionchanged:: 2.0
            The edit is no longer in-place, instead the newly edited message is returned.

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
        attachments: List[:class:`Attachment`]
            A list of attachments to keep in the message. If ``[]`` is passed
            then all attachments are removed.
        file: :class:`File`
            The file to upload. This cannot be mixed with ``files`` parameter.

            .. versionadded:: 2.0
        files: List[:class:`File`]
            A list of files to send with the content. This cannot be mixed with the
            ``file`` parameter.

            .. versionadded:: 2.0
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        view: Optional[:class:`~discord.ui.BaseView`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed. The webhook must have state attached, similar to
            :meth:`send`.

            .. versionadded:: 2.0
        thread: Optional[:class:`~discord.abc.Snowflake`]
            The thread that contains the message.
        suppress: :class:`bool`
            Whether to suppress embeds for the message.

            .. deprecated:: 2.8
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.

            .. versionadded:: 2.8

        Returns
        -------
        :class:`WebhookMessage`
            The newly edited webhook message.

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
            There was no token associated with this webhook or the webhook had
            no state.
        """
        request = self._edit_message_request(
            message_id,
            content=content,
            embeds=embeds,
            embed=embed,
            file=file,
            files=files,
            attachments=attachments,
            view=view,
            allowed_mentions=allowed_mentions,
            thread=thread,
            suppress=suppress,
            suppress_embeds=suppress_embeds,
        )
        if view is not MISSING and not isinstance(self._state, _WebhookState):
            self._state.prevent_view_updates_for(message_id)

        data = await async_context.get().execute(
            request,
            session=self.session,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
        )

        message = await self._create_message(data)
        if view and not view.is_finished():
            view.message = message
            cast("View | DesignerView", view)._refresh(message.components)
            if view.is_dispatchable():
                self._state.store_view(view, message_id)
        return message

    async def delete_message(
        self, message_id: int, *, thread_id: int | None = None
    ) -> None:
        """|coro|

        Deletes a message owned by this webhook.

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
        await async_context.get().execute(
            self._delete_message_request(message_id, thread_id),
            session=self.session,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth,
        )
