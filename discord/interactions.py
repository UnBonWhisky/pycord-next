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
import contextlib
from typing import TYPE_CHECKING, Any, cast, overload

from typing_extensions import deprecated

from . import utils
from ._internal.cache_peek import cached_guild, cached_guild_channel
from .channel import ChannelType, PartialMessageable, _threaded_channel_factory
from .enums import (
    InteractionContextType,
    InteractionResponseType,
    InteractionType,
    try_enum,
)
from .errors import ClientException, InteractionResponded, InvalidArgument
from .file import File, VoiceMessage
from .flags import MessageFlags
from .guild import Guild, PartialGuild
from .member import Member
from .message import Attachment, Message
from .monetization import Entitlement
from .permissions import Permissions
from .user import User
from .utils import warn_deprecated
from .webhook.async_ import (
    Webhook,
    WebhookMessage,
    async_context,
    handle_message_parameters,
)

__all__ = (
    "AuthorizingIntegrationOwners",
    "Interaction",
    "InteractionCallback",
    "InteractionCallbackActivityInstanceResource",
    "InteractionMessage",
    "InteractionMetadata",
    "InteractionResponse",
    "MessageInteraction",
)

if TYPE_CHECKING:
    import datetime as dt
    from collections.abc import Coroutine, Mapping

    from aiohttp import ClientSession

    from .abc import MessageableChannel
    from .channel import (
        CategoryChannel,
        DMChannel,
        ForumChannel,
        GroupChannel,
        StageChannel,
        TextChannel,
        VoiceChannel,
    )
    from .client import Client
    from .commands import ApplicationCommand, OptionChoice
    from .embeds import Embed
    from .http import HTTPClient
    from .mentions import AllowedMentions
    from .poll import Poll
    from .state import ConnectionState
    from .threads import Thread
    from .types.interaction_metadata import (
        InteractionMetadata as InteractionMetadataPayload,
        MessageInteraction as MessageInteractionPayload,
    )
    from .types.interactions import (
        Interaction as InteractionPayload,
        InteractionCallback as InteractionCallbackPayload,
        InteractionCallbackActivityInstance as InteractionCallbackActivityInstancePayload,
        InteractionCallbackResponse,
        InteractionData,
    )
    from .types.message import Message as MessagePayload
    from .types.user import User as UserPayload
    from .ui.modal import BaseModal
    from .ui.view import BaseView

    InteractionChannel = (
        VoiceChannel
        | StageChannel
        | TextChannel
        | ForumChannel
        | CategoryChannel
        | Thread
        | DMChannel
        | GroupChannel
        | PartialMessageable
    )

MISSING: Any = utils.MISSING


def _is_file(value: object) -> bool:
    return isinstance(value, File)


def _require_message(message: Message | None) -> Message:
    if message is None:
        raise ClientException("The interaction has no message to edit.")
    return message


class Interaction:
    """Represents a Discord interaction.

    An interaction happens when a user does an action that needs to
    be notified. Current examples are application commands, components, and modals.

    .. versionadded:: 2.0

    Attributes
    ----------
    id: :class:`int`
        The interaction's ID.
    type: :class:`InteractionType`
        The interaction type.
    guild_id: Optional[:class:`int`]
        The guild ID the interaction was sent from.
    channel: Optional[Union[:class:`abc.GuildChannel`, :class:`abc.PrivateChannel`, :class:`Thread`, :class:`PartialMessageable`]]
        The channel the interaction was sent from.
    channel_id: Optional[:class:`int`]
        The ID of the channel the interaction was sent from.
    application_id: :class:`int`
        The application ID that the interaction was for.
    user: Optional[Union[:class:`User`, :class:`Member`]]
        The user or member that sent the interaction. Will be `None` in PING interactions.
    message: Optional[:class:`Message`]
        The message that sent this interaction.
    token: :class:`str`
        The token to continue the interaction. These are valid
        for 15 minutes.
    data: :class:`dict`
        The raw interaction data.
    locale: :class:`str`
        The user's locale.
    guild_locale: :class:`str`
        The guilds preferred locale, if invoked in a guild.
    custom_id: Optional[:class:`str`]
        The custom ID for the interaction.
    entitlements: list[:class:`Entitlement`]
        Entitlements that apply to the invoking user, showing access to premium SKUs.

        .. versionadded:: 2.5
    authorizing_integration_owners: :class:`AuthorizingIntegrationOwners`
        Contains the entities (users or guilds) that authorized this interaction.

        .. versionadded:: 2.6
    context: Optional[:class:`InteractionContextType`]
        The context in which this command was executed.

        .. versionadded:: 2.6
    callback: Optional[:class:`InteractionCallback`]
        The callback of the interaction. Contains information about the status of the interaction response.
        Will be `None` until the interaction is responded to.

        .. versionadded:: 2.7
    activity_instance: Optional[:class:`InteractionCallbackActivityInstanceResource`]
        The activity launched or joined as the response to the interaction.
        Will be ``None`` unless :meth:`InteractionResponse.launch_activity` was used.

        .. versionadded:: 3.0
    command: Optional[:class:`ApplicationCommand`]
        The command that this interaction belongs to.

        .. versionadded:: 2.7
    view: Optional[:class:`BaseView`]
        The view that this interaction belongs to.

        .. versionadded:: 2.7
    modal: Optional[:class:`BaseModal`]
        The modal that this interaction belongs to.

        .. versionadded:: 2.7
    attachment_size_limit: :class:`int`
        The attachment size limit.

        .. versionadded:: 2.7
    """

    __slots__: tuple[str, ...] = (
        "_app_permissions",
        "_channel_data",
        "_cs_app_permissions",
        "_cs_channel",
        "_cs_followup",
        "_cs_response",
        "_guild",
        "_guild_data",
        "_message_data",
        "_original_response",
        "_permissions",
        "_raw_data",
        "_session",
        "_state",
        "activity_instance",
        "application_id",
        "attachment_size_limit",
        "authorizing_integration_owners",
        "callback",
        "channel",
        "channel_id",
        "command",
        "context",
        "custom_id",
        "data",
        "entitlements",
        "guild_id",
        "guild_locale",
        "id",
        "locale",
        "message",
        "modal",
        "token",
        "type",
        "user",
        "user_id",
        "version",
        "view",
    )

    def __init__(self, *, data: InteractionPayload, state: ConnectionState) -> None:
        self._state: ConnectionState = state
        self._session: ClientSession = state.http._session
        self._original_response: InteractionMessage | None = None
        self.callback: InteractionCallback | None = None
        self.activity_instance: InteractionCallbackActivityInstanceResource | None = (
            None
        )
        self._cs_channel: InteractionChannel | None = MISSING
        self._from_data(data)

    def _from_data(self, data: InteractionPayload) -> None:
        self._raw_data: InteractionPayload = data
        self.id: int = int(data["id"])
        self.type: InteractionType = try_enum(InteractionType, data["type"])
        self.data: InteractionData | None = data.get("data")
        self.token: str = data["token"]
        self.version: int = data["version"]
        self.channel_id: int | None = utils._get_as_snowflake(data, "channel_id")
        self.guild_id: int | None = utils._get_as_snowflake(data, "guild_id")
        self.application_id: int = int(data["application_id"])
        self.locale: str | None = data.get("locale")
        self.guild_locale: str | None = data.get("guild_locale")
        self.custom_id: str | None = (
            self.data.get("custom_id") if self.data is not None else None
        )
        self._app_permissions: int = int(data.get("app_permissions", 0))
        self.entitlements: list[Entitlement] = [
            Entitlement(data=e, state=self._state) for e in data.get("entitlements", [])
        ]
        self.authorizing_integration_owners: AuthorizingIntegrationOwners = (
            AuthorizingIntegrationOwners(
                data=data["authorizing_integration_owners"], state=self._state
            )
            if "authorizing_integration_owners" in data
            else AuthorizingIntegrationOwners(data={}, state=self._state)
        )
        self.context: InteractionContextType | None = (
            try_enum(InteractionContextType, data["context"])
            if "context" in data
            else None
        )

        self.command: ApplicationCommand | None = None
        self.view: BaseView | None = None
        self.modal: BaseModal | None = None
        self.attachment_size_limit: int = cast("int", data.get("attachment_size_limit"))

        self.message: Message | None = None
        self.channel: InteractionChannel | None = None

        self.user: User | Member | None = None
        self._permissions: int = 0

        self._guild: Guild | None = None
        self._guild_data = data.get("guild")
        if self._guild_data:
            self._guild = Guild(data=self._guild_data, state=self._state)

        if self.guild_id:
            member = data.get("member")
            if member is not None:
                self._permissions = int(member.get("permissions", 0))
                self.user = Member(
                    state=self._state,
                    data=member,
                    guild=PartialGuild(state=self._state, id=self.guild_id),
                )
        elif (user_data := data.get("user")) is not None:
            with contextlib.suppress(KeyError):
                self.user = User(state=self._state, data=user_data)
        self.user_id: int | None = self.user.id if self.user is not None else None

        channel = data.get("channel")
        data_ch_type: int | None = channel.get("type") if channel else None
        factory: Any | None = None

        if data_ch_type is not None:
            factory, ch_type = _threaded_channel_factory(data_ch_type)
            if factory is not None and ch_type in (
                ChannelType.group,
                ChannelType.private,
            ):
                self.channel = factory(me=self.user, data=channel, state=self._state)

        if self.channel is None and self.guild_id is not None and factory is not None:
            try:
                self.channel = factory(
                    state=self._state,
                    data=channel,
                    guild=PartialGuild(state=self._state, id=self.guild_id),
                )
            except KeyError:
                self.channel = None

        if self.channel is None and self.channel_id is not None:
            ch_type = (
                ChannelType.text if self.guild_id is not None else ChannelType.private
            )
            self.channel = PartialMessageable(
                state=self._state, id=self.channel_id, type=ch_type
            )

        self._channel_data = channel

        if message_data := data.get("message"):
            self.message = Message(
                state=self._state,
                channel=cast("MessageableChannel", self.channel),
                data=message_data,
            )

        self._message_data = message_data

    @property
    def client(self) -> Client:
        """Returns the client that sent the interaction."""
        return self._state._get_client()

    @property
    def guild(self) -> Guild | PartialGuild | None:
        """The guild the interaction was sent from.

        This is the guild partial object of the payload when it has one,
        otherwise the cached guild with the in-process cache, and a
        :class:`PartialGuild` handle when it is not cached or the cache backend
        is not the in-process one.
        """
        if self._guild:
            return self._guild
        if self.guild_id is None:
            return None
        return cached_guild(self._state, self.guild_id) or PartialGuild(
            state=self._state, id=self.guild_id
        )

    async def get_guild(self) -> Guild | None:
        """|coro|

        Returns the guild the interaction was sent from.

        Unlike :attr:`guild` this reads the cache asynchronously, so it returns the
        cached :class:`Guild` with any cache backend.

        Returns
        -------
        Optional[:class:`Guild`]
            The guild, or ``None`` if it is not cached or the interaction was not sent from a guild.
        """
        if self._guild:
            return self._guild
        return await self._state._get_guild(self.guild_id)

    @property
    def created_at(self) -> dt.datetime:
        """Returns the interaction's creation time in UTC."""
        return utils.snowflake_time(self.id)

    def is_command(self) -> bool:
        """Indicates whether the interaction is an application command."""
        return self.type == InteractionType.application_command

    def is_component(self) -> bool:
        """Indicates whether the interaction is a message component."""
        return self.type == InteractionType.component

    @property
    @deprecated(
        "Interaction.cached_channel is deprecated since version 2.7, consider using Interaction.channel instead."
    )
    def cached_channel(self) -> InteractionChannel | None:
        """The cached channel from which the interaction was sent.

        DM channels are not resolved. These are :class:`PartialMessageable` instead.

        .. deprecated:: 2.7
        """
        if self._cs_channel is not MISSING:
            return self._cs_channel
        r: InteractionChannel | None = None
        channel = cached_guild_channel(self._state, self.guild_id, self.channel_id)
        if channel is not None and getattr(channel, "obfuscated", False):
            r = self.channel
        elif channel is not None:
            r = cast("InteractionChannel", channel)
        elif self.channel_id is not None:
            type = (
                ChannelType.text if self.guild_id is not None else ChannelType.private
            )
            r = PartialMessageable(state=self._state, id=self.channel_id, type=type)
        self._cs_channel = r
        return r

    @property
    def permissions(self) -> Permissions:
        """The resolved permissions of the member in the channel, including overwrites.

        In a non-guild context where this doesn't apply, an empty permissions object is returned.
        """
        return Permissions(self._permissions)

    @utils.cached_slot_property("_cs_app_permissions")
    def app_permissions(self) -> Permissions:
        """The resolved permissions of the application in the channel, including overwrites."""
        return Permissions(self._app_permissions)

    @utils.cached_slot_property("_cs_response")
    def response(self) -> InteractionResponse:
        """Returns an object responsible for handling responding to the interaction.

        A response can only be done once. If secondary messages need to be sent, consider using :attr:`followup`
        instead.
        """
        return InteractionResponse(self)

    @utils.cached_slot_property("_cs_followup")
    def followup(self) -> Webhook:
        """Returns the followup webhook for followup interactions."""
        return Webhook.from_interaction(interaction=self)

    def is_guild_authorised(self) -> bool:
        """:class:`bool`: Checks if the interaction is guild authorised.

        There is an alias for this called :meth:`.is_guild_authorized`.

        .. versionadded:: 2.7
        """
        if self.guild_id:
            return self.authorizing_integration_owners.guild_id == self.guild_id
        return False

    def is_user_authorised(self) -> bool:
        """:class:`bool`: Checks if the interaction is user authorised.

        There is an alias for this called :meth:`.is_user_authorized`.

        .. versionadded:: 2.7
        """
        if self.user:
            return self.authorizing_integration_owners.user_id == self.user.id

        # This return should not be called but to make sure it returns the expected value
        return False

    def is_guild_authorized(self) -> bool:
        """:class:`bool`: Checks if the interaction is guild authorized.

        There is an alias for this called :meth:`.is_guild_authorised`.

        .. versionadded:: 2.7
        """
        return self.is_guild_authorised()

    def is_user_authorized(self) -> bool:
        """:class:`bool`: Checks if the interaction is user authorized.

        There is an alias for this called :meth:`.is_user_authorised`.

        .. versionadded:: 2.7
        """
        return self.is_user_authorised()

    async def _create_response_message(
        self, channel: InteractionChannel, data: MessagePayload
    ) -> InteractionMessage:
        state = _InteractionMessageState(self, self._state)
        message = InteractionMessage(
            state=cast("ConnectionState", state),
            channel=cast("MessageableChannel", channel),
            data=data,
        )
        await self._state._populate_message(message, data)
        return message

    async def original_response(self) -> InteractionMessage:
        """|coro|

        Fetches the original interaction response message associated with the interaction.

        If the interaction response was :meth:`InteractionResponse.send_message` then this would
        return the message that was sent using that response. Otherwise, this would return
        the message that triggered the interaction.

        Repeated calls to this will return a cached value.

        Returns
        -------
        InteractionMessage
            The original interaction response message.

        Raises
        ------
        HTTPException
            Fetching the original response message failed.
        ClientException
            The channel for the message could not be resolved.
        """
        if self._original_response is not None:
            return self._original_response

        channel = self.channel
        if channel is None:
            raise ClientException(
                "Channel for message could not be resolved. Please open a issue on GitHub if you encounter this error."
            )

        adapter = async_context.get()
        http = self._state.http
        data = await adapter.get_original_interaction_response(
            application_id=self.application_id,
            token=self.token,
            session=self._session,
            proxy=http.proxy,
            proxy_auth=http.proxy_auth,
        )
        message = await self._create_response_message(channel, data)
        self._original_response = message
        return message

    @deprecated(
        "Interaction.original_message is deprecated since version 2.2, consider using Interaction.original_response instead."
    )
    async def original_message(self) -> InteractionMessage:
        """An alias for :meth:`original_response`.

        Returns
        -------
        InteractionMessage
            The original interaction response message.

        Raises
        ------
        HTTPException
            Fetching the original response message failed.
        ClientException
            The channel for the message could not be resolved.
        """
        return await self.original_response()

    async def edit_original_response(
        self,
        *,
        content: str | None = MISSING,
        embeds: list[Embed] = MISSING,
        embed: Embed | None = MISSING,
        file: File = MISSING,
        files: list[File] = MISSING,
        attachments: list[Attachment] = MISSING,
        view: BaseView | None = MISSING,
        allowed_mentions: AllowedMentions | None = None,
        delete_after: float | None = None,
        suppress: bool | None = None,
        suppress_embeds: bool | None = None,
    ) -> InteractionMessage:
        """|coro|

        Edits the original interaction response message.

        This is a lower level interface to :meth:`InteractionMessage.edit` in case
        you do not want to fetch the message and save an HTTP request.

        This method is also the only way to edit the original message if
        the message sent was ephemeral.

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
        attachments: List[:class:`Attachment`]
            A list of attachments to keep in the message. If ``[]`` is passed
            then all attachments are removed.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        view: Optional[:class:`~discord.ui.BaseView`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.
        delete_after: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message we just edited. If the deletion fails,
            then it is silently ignored.
        suppress: :class:`bool`
            Whether to suppress embeds for the message.

            .. deprecated:: 2.8
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message.

            .. versionadded:: 2.8

        Returns
        -------
        :class:`InteractionMessage`
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
            The length of ``embeds`` was invalid.
        """
        previous_mentions: AllowedMentions | None = self._state.allowed_mentions
        if suppress is not None:
            warn_deprecated("suppress", "suppress_embeds", "2.8")
            if suppress_embeds is None:
                suppress_embeds = suppress
        elif suppress_embeds is None:
            suppress_embeds = False
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
            suppress_embeds=suppress_embeds,
        )
        _target = self.message or self._original_response
        if view and _target:
            self._state.prevent_view_updates_for(_target.id)
        adapter = async_context.get()
        http = self._state.http
        data = await adapter.edit_original_interaction_response(
            self.application_id,
            self.token,
            session=self._session,
            proxy=http.proxy,
            proxy_auth=http.proxy_auth,
            payload=params.payload,
            multipart=params.multipart,
            files=params.files,
        )

        # The message channel types should always match
        message = await self._create_response_message(
            cast("InteractionChannel", self.channel), data
        )
        if view:
            if not view.is_finished():
                view._refresh(message.components)
                if view.is_dispatchable():
                    self._state.store_view(view, message.id)

            view.message = message

        if delete_after is not None:
            await self.delete_original_response(delay=delete_after)

        return message

    @deprecated(
        "Interaction.edit_original_message is deprecated since version 2.2, consider using Interaction.edit_original_response instead."
    )
    async def edit_original_message(self, **kwargs: Any) -> InteractionMessage:
        """An alias for :meth:`edit_original_response`.

        Returns
        -------
        :class:`InteractionMessage`
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
            The length of ``embeds`` was invalid.
        """
        return await self.edit_original_response(**kwargs)

    async def delete_original_response(self, *, delay: float | None = None) -> None:
        """|coro|

        Deletes the original interaction response message.

        This is a lower level interface to :meth:`InteractionMessage.delete` in case
        you do not want to fetch the message and save an HTTP request.

        Parameters
        ----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait before deleting the message.
            The waiting is done in the background and deletion failures are ignored.

        Raises
        ------
        HTTPException
            Deleting the message failed.
        Forbidden
            Deleted a message that is not yours.
        """
        adapter = async_context.get()
        http = self._state.http
        func = adapter.delete_original_interaction_response(
            self.application_id,
            self.token,
            session=self._session,
            proxy=http.proxy,
            proxy_auth=http.proxy_auth,
        )

        if delay is not None:
            utils.delay_task(delay, func)
        else:
            await func

    @deprecated(
        "Interaction.delete_original_message is deprecated since version 2.2, consider using Interaction.delete_original_response instead."
    )
    async def delete_original_message(self, **kwargs: Any) -> None:
        """An alias for :meth:`delete_original_response`.

        Raises
        ------
        HTTPException
            Deleting the message failed.
        Forbidden
            Deleted a message that is not yours.
        """
        return await self.delete_original_response(**kwargs)

    @overload
    async def respond(
        self,
        content: Any | None = None,
        embed: Embed | None = None,
        view: BaseView | None = None,
        tts: bool = False,
        ephemeral: bool = False,
        allowed_mentions: AllowedMentions | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        poll: Poll | None = None,
        delete_after: float | None = None,
        silent: bool = False,
        suppress_embeds: bool = False,
    ) -> Interaction | WebhookMessage: ...

    @overload
    async def respond(
        self,
        content: Any | None = None,
        embeds: list[Embed] | None = None,
        view: BaseView | None = None,
        tts: bool = False,
        ephemeral: bool = False,
        allowed_mentions: AllowedMentions | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        poll: Poll | None = None,
        delete_after: float | None = None,
        silent: bool = False,
        suppress_embeds: bool = False,
    ) -> Interaction | WebhookMessage: ...

    async def respond(self, *args: Any, **kwargs: Any) -> Interaction | WebhookMessage:
        """|coro|

        Sends either a response or a message using the followup webhook determined by whether the interaction
        has been responded to or not.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The content of the message to send.
        embeds: List[:class:`Embed`]
            A list of embeds to send with the content. Maximum of 10. This cannot
            be mixed with the ``embed`` parameter.
        embed: :class:`Embed`
            The rich embed for the content to send. This cannot be mixed with
            ``embeds`` parameter.
        tts: :class:`bool`
            Indicates if the message should be sent using text-to-speech.
        view: :class:`discord.ui.BaseView`
            The view to send with the message.
        ephemeral: :class:`bool`
            Indicates if the message should only be visible to the user who started the interaction.
            If a view is sent with an ephemeral message, and it has no timeout set then the timeout
            is set to 15 minutes.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        delete_after: :class:`float`
            If provided, the number of seconds to wait in the background
            before deleting the message we just sent.
        file: :class:`File`
            The file to upload.
        files: List[:class:`File`]
            A list of files to upload. Must be a maximum of 10.
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
        Union[:class:`discord.Interaction`, :class:`discord.WebhookMessage`]:
            The response, its type depending on whether it's an interaction response or a followup.
        """
        try:
            if not self.response.is_done():
                return await self.response.send_message(*args, **kwargs)
            return await self.followup.send(*args, **kwargs)
        except InteractionResponded:
            return await self.followup.send(*args, **kwargs)

    async def edit(self, *args: Any, **kwargs: Any) -> InteractionMessage | None:
        """|coro|

        Either respond to the interaction with an edit_message or edits the existing response, determined by
        whether the interaction has been responded to or not.

        Returns
        -------
        Union[:class:`discord.InteractionMessage`, :class:`discord.WebhookMessage`]:
            The response, its type depending on whether it's an interaction response or a followup.
        """
        try:
            if not self.response.is_done():
                return await self.response.edit_message(*args, **kwargs)
            return await self.edit_original_response(*args, **kwargs)
        except InteractionResponded:
            return await self.edit_original_response(*args, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        """
        Converts this interaction object into a dict.

        Returns
        -------
        Dict[:class:`str`, Any]
            A dictionary of :class:`str` interaction keys bound to the respective value.
        """
        data: dict[str, Any] = {
            "id": self.id,
            "application_id": self.application_id,
            "type": self.type.value,
            "token": self.token,
            "version": self.version,
        }

        if self.data is not None:
            data["data"] = self.data
            if (resolved := self.data.get("resolved")) and self.user is not None:
                if (users := resolved.get("users")) and (
                    user := users.get(self.user.id)
                ):
                    data["user"] = user
                if (members := resolved.get("members")) and (
                    member := members.get(self.user.id)
                ):
                    data["member"] = member

        if self.guild_id is not None:
            data["guild_id"] = self.guild_id

        if self.channel_id is not None:
            data["channel_id"] = self.channel_id

        if self.locale:
            data["locale"] = self.locale

        if self.guild_locale:
            data["guild_locale"] = self.guild_locale

        if self._message_data:
            data["message"] = self._message_data

        return data


class InteractionResponse:
    """Represents a Discord interaction response.

    This type can be accessed through :attr:`Interaction.response`.

    .. versionadded:: 2.0
    """

    __slots__: tuple[str, ...] = (
        "_parent",
        "_responded",
        "_response_lock",
    )

    def __init__(self, parent: Interaction) -> None:
        self._parent: Interaction = parent
        self._responded: bool = False
        self._response_lock = asyncio.Lock()

    def is_done(self) -> bool:
        """Indicates whether an interaction response has been done before.

        An interaction can only be responded to once.
        """
        return self._responded

    async def defer(self, *, ephemeral: bool = False, invisible: bool = True) -> None:
        """|coro|

        Defers the interaction response.

        This is typically used when the interaction is acknowledged
        and a secondary action will be done later.

        This can only be used with the following interaction types:

        - :attr:`InteractionType.application_command`
        - :attr:`InteractionType.component`
        - :attr:`InteractionType.modal_submit`

        .. note::
            The follow-up response will also be non-ephemeral if the `ephemeral`
            argument is ``False``, and ephemeral if ``True``.

        Parameters
        ----------
        ephemeral: :class:`bool`
            Indicates whether the deferred message will eventually be ephemeral.
            This only applies to :attr:`InteractionType.application_command` interactions,
            or if ``invisible`` is ``False``.
        invisible: :class:`bool`
            Indicates whether the deferred type should be 'invisible'
            (:attr:`InteractionResponseType.deferred_message_update`)
            instead of 'thinking' (:attr:`InteractionResponseType.deferred_channel_message`).
            In the Discord UI, this is represented as the bot thinking of a response. You must
            eventually send a followup message via :attr:`Interaction.followup` to make this thinking state go away.
            This parameter does not apply to interactions of type :attr:`InteractionType.application_command`.

        Raises
        ------
        HTTPException
            Deferring the interaction failed.
        InteractionResponded
            This interaction has already been responded to before.
        """
        if self._responded:
            raise InteractionResponded(self._parent)

        defer_type: int = 0
        data: dict[str, Any] | None = None
        parent = self._parent
        if (
            parent.type is InteractionType.component
            or parent.type is InteractionType.modal_submit
        ):
            defer_type = (
                InteractionResponseType.deferred_message_update.value
                if invisible
                else InteractionResponseType.deferred_channel_message.value
            )
            if not invisible and ephemeral:
                data = {"flags": 64}
        elif parent.type is InteractionType.application_command:
            defer_type = InteractionResponseType.deferred_channel_message.value
            if ephemeral:
                data = {"flags": 64}

        if defer_type:
            adapter = async_context.get()
            http = parent._state.http
            callback_response: InteractionCallbackResponse = (
                await self._locked_response(
                    adapter.create_interaction_response(
                        parent.id,
                        parent.token,
                        session=parent._session,
                        type=defer_type,
                        data=data,
                        proxy=http.proxy,
                        proxy_auth=http.proxy_auth,
                    )
                )
            )
            self._responded = True
            await self._process_callback_response(callback_response)

    async def pong(self) -> None:
        """|coro|

        Pongs the ping interaction.

        This should rarely be used.

        Raises
        ------
        HTTPException
            Ponging the interaction failed.
        InteractionResponded
            This interaction has already been responded to before.
        """
        if self._responded:
            raise InteractionResponded(self._parent)

        parent = self._parent
        if parent.type is InteractionType.ping:
            adapter = async_context.get()
            http = parent._state.http
            callback_response: InteractionCallbackResponse = (
                await self._locked_response(
                    adapter.create_interaction_response(
                        parent.id,
                        parent.token,
                        session=parent._session,
                        proxy=http.proxy,
                        proxy_auth=http.proxy_auth,
                        type=InteractionResponseType.pong.value,
                    )
                )
            )
            self._responded = True
            await self._process_callback_response(callback_response)

    async def _process_callback_response(
        self, callback_response: InteractionCallbackResponse
    ) -> None:
        resource = callback_response.get("resource", {})

        if message_data := resource.get("message"):
            # TODO: fix later to not raise?
            channel = self._parent.channel
            if channel is None:
                raise ClientException(
                    "Channel for message could not be resolved. Please open a issue on GitHub if you encounter this error."
                )
            self._parent._original_response = (
                await self._parent._create_response_message(channel, message_data)
            )

        if activity_instance := resource.get("activity_instance"):
            self._parent.activity_instance = (
                InteractionCallbackActivityInstanceResource(activity_instance)
            )

        self._parent.callback = InteractionCallback(callback_response["interaction"])

    async def send_message(
        self,
        content: Any | None = None,
        *,
        embed: Embed | None = None,
        embeds: list[Embed] | None = None,
        view: BaseView | None = None,
        tts: bool = False,
        ephemeral: bool = False,
        allowed_mentions: AllowedMentions | None = None,
        file: File | None = None,
        files: list[File] | None = None,
        poll: Poll | None = None,
        delete_after: float | None = None,
        silent: bool = False,
        suppress_embeds: bool = False,
    ) -> Interaction:
        """|coro|

        Responds to this interaction by sending a message.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The content of the message to send.
        embeds: List[:class:`Embed`]
            A list of embeds to send with the content. Maximum of 10. This cannot
            be mixed with the ``embed`` parameter.
        embed: :class:`Embed`
            The rich embed for the content to send. This cannot be mixed with
            ``embeds`` parameter.
        tts: :class:`bool`
            Indicates if the message should be sent using text-to-speech.
        view: :class:`discord.ui.BaseView`
            The view to send with the message.
        ephemeral: :class:`bool`
            Indicates if the message should only be visible to the user who started the interaction.
            If a view is sent with an ephemeral message, and it has no timeout set then the timeout
            is set to 15 minutes.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        delete_after: :class:`float`
            If provided, the number of seconds to wait in the background
            before deleting the message we just sent.
        file: :class:`File`
            The file to upload.
        files: List[:class:`File`]
            A list of files to upload. Must be a maximum of 10.
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
        :class:`.Interaction`
            The interaction object associated with the sent message.

        Raises
        ------
        HTTPException
            Sending the message failed.
        TypeError
            You specified both ``embed`` and ``embeds``, or sent content or embeds with V2 components.
        ValueError
            The length of ``embeds`` was invalid.
        InteractionResponded
            This interaction has already been responded to before.
        """
        if self._responded:
            raise InteractionResponded(self._parent)

        payload: dict[str, Any] = {
            "tts": tts,
        }

        if embed is not None and embeds is not None:
            raise TypeError("cannot mix embed and embeds keyword arguments")

        if embed is not None:
            embeds = [embed]

        if embeds:
            if len(embeds) > 10:
                raise ValueError("embeds cannot exceed maximum of 10 elements")
            payload["embeds"] = [e.to_dict() for e in embeds]

        if content is not None:
            payload["content"] = str(content)

        flags = MessageFlags(
            ephemeral=ephemeral,
            suppress_notifications=silent,
            suppress_embeds=suppress_embeds,
        )

        if view:
            payload["components"] = view.to_components()
            if view.is_components_v2():
                if embeds or content:
                    raise TypeError(
                        "cannot send embeds or content with a view using v2 component logic"
                    )
                flags.is_components_v2 = True

        if poll is not None:
            payload["poll"] = poll.to_dict()

        state = self._parent._state

        if allowed_mentions is None:
            payload["allowed_mentions"] = (
                state.allowed_mentions and state.allowed_mentions.to_dict()
            )

        elif state.allowed_mentions is not None:
            payload["allowed_mentions"] = state.allowed_mentions.merge(
                allowed_mentions
            ).to_dict()
        else:
            payload["allowed_mentions"] = allowed_mentions.to_dict()
        if file is not None and files is not None:
            raise InvalidArgument("cannot pass both file and files parameter to send()")

        if file is not None:
            if not _is_file(file):
                raise InvalidArgument("file parameter must be File")
            files = [file]

        if files is not None:
            if len(files) > 10:
                raise InvalidArgument(
                    "files parameter must be a list of up to 10 elements"
                )
            if not all(_is_file(f) for f in files):
                raise InvalidArgument("files parameter must be a list of File")

            if any(isinstance(f, VoiceMessage) for f in files):
                flags = flags + MessageFlags(is_voice_message=True)

        payload["flags"] = flags.value

        parent = self._parent
        adapter = async_context.get()
        http = parent._state.http
        try:
            callback_response: InteractionCallbackResponse = (
                await self._locked_response(
                    adapter.create_interaction_response(
                        parent.id,
                        parent.token,
                        session=parent._session,
                        type=InteractionResponseType.channel_message.value,
                        proxy=http.proxy,
                        proxy_auth=http.proxy_auth,
                        data=payload,
                        files=files,
                    )
                )
            )
        finally:
            if files:
                for f in files:
                    f.close()

        self._responded = True
        await self._process_callback_response(callback_response)
        if view:
            view.parent = self._parent
            if not view.is_finished():
                if ephemeral and view.timeout is None:
                    view.timeout = 15 * 60.0

                if view.is_dispatchable():
                    self._parent._state.store_view(view)

            view.message = await self._parent.original_response()

        if delete_after is not None:
            await self._parent.delete_original_response(delay=delete_after)
        return self._parent

    async def edit_message(
        self,
        *,
        content: Any | None = MISSING,
        embed: Embed | None = MISSING,
        embeds: list[Embed] = MISSING,
        file: File = MISSING,
        files: list[File] = MISSING,
        attachments: list[Attachment] = MISSING,
        view: BaseView | None = MISSING,
        delete_after: float | None = None,
        suppress: bool | None = MISSING,
        allowed_mentions: AllowedMentions | None = None,
    ) -> None:
        """|coro|

        Responds to this interaction by editing the original message of
        a component or modal interaction.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The new content to replace the message with. ``None`` removes the content.
        embeds: List[:class:`Embed`]
            A list of embeds to edit the message with.
        embed: Optional[:class:`Embed`]
            The embed to edit the message with. ``None`` suppresses the embeds.
            This should not be mixed with the ``embeds`` parameter.
        file: :class:`File`
            A new file to add to the message. This cannot be mixed with ``files`` parameter.
        files: List[:class:`File`]
            A list of new files to add to the message. Must be a maximum of 10. This
            cannot be mixed with the ``file`` parameter.
        attachments: List[:class:`Attachment`]
            A list of attachments to keep in the message. If ``[]`` is passed
            then all attachments are removed.
        view: Optional[:class:`~discord.ui.BaseView`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.
        delete_after: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message we just edited. If the deletion fails,
            then it is silently ignored.
        suppress: Optional[:class:`bool`]
            Whether to suppress embeds for the message.
        allowed_mentions: Optional[:class:`~discord.AllowedMentions`]
            Controls the mentions being processed in this message. If this is
            passed, then the object is merged with :attr:`~discord.Client.allowed_mentions`.
            The merging behaviour only overrides attributes that have been explicitly passed
            to the object, otherwise it uses the attributes set in :attr:`~discord.Client.allowed_mentions`.
            If no object is passed at all then the defaults given by :attr:`~discord.Client.allowed_mentions`
            are used instead.

        Raises
        ------
        HTTPException
            Editing the message failed.
        TypeError
            You specified both ``embed`` and ``embeds``.
        InteractionResponded
            This interaction has already been responded to before.
        """
        if self._responded:
            raise InteractionResponded(self._parent)

        parent = self._parent
        msg = parent.message or parent._original_response
        state = parent._state
        message_id = msg.id if msg else None
        if parent.type not in (InteractionType.component, InteractionType.modal_submit):
            return

        is_cv2 = None

        payload: dict[str, Any] = {}
        if content is not MISSING:
            payload["content"] = None if content is None else str(content)
        if embed is not MISSING and embeds is not MISSING:
            raise TypeError("cannot mix both embed and embeds keyword arguments")

        if embed is not MISSING:
            embeds = [] if embed is None else [embed]
        if embeds is not MISSING:
            payload["embeds"] = [e.to_dict() for e in embeds]

        if attachments is not MISSING:
            payload["attachments"] = [a.to_dict() for a in attachments]

        if view is not MISSING:
            if message_id is not None:
                state.prevent_view_updates_for(message_id)
            payload["components"] = [] if view is None else view.to_components()
            if view and view.is_components_v2():
                is_cv2 = True

        if file is not MISSING and files is not MISSING:
            raise InvalidArgument(
                "cannot pass both file and files parameter to edit_message()"
            )

        if file is not MISSING:
            if not _is_file(file):
                raise InvalidArgument("file parameter must be a File")
            files = [file]
            if "attachments" not in payload:
                # we keep previous attachments when adding a new file
                payload["attachments"] = [
                    a.to_dict() for a in _require_message(msg).attachments
                ]

        if files is not MISSING:
            if len(files) > 10:
                raise InvalidArgument(
                    "files parameter must be a list of up to 10 elements"
                )
            if not all(_is_file(f) for f in files):
                raise InvalidArgument("files parameter must be a list of File")
            if "attachments" not in payload:
                # we keep previous attachments when adding new files
                payload["attachments"] = [
                    a.to_dict() for a in _require_message(msg).attachments
                ]

        if suppress is not MISSING or is_cv2:
            flags = MessageFlags._from_value(_require_message(msg).flags.value)
            if is_cv2:
                flags.is_components_v2 = True
            if suppress is not MISSING:
                flags.suppress_embeds = cast("bool", suppress)
            payload["flags"] = flags.value

        if allowed_mentions is None:
            payload["allowed_mentions"] = (
                state.allowed_mentions and state.allowed_mentions.to_dict()
            )

        elif state.allowed_mentions is not None:
            payload["allowed_mentions"] = state.allowed_mentions.merge(
                allowed_mentions
            ).to_dict()
        else:
            payload["allowed_mentions"] = allowed_mentions.to_dict()

        adapter = async_context.get()
        http = parent._state.http
        try:
            callback_response: InteractionCallbackResponse = (
                await self._locked_response(
                    adapter.create_interaction_response(
                        parent.id,
                        parent.token,
                        session=parent._session,
                        type=InteractionResponseType.message_update.value,
                        proxy=http.proxy,
                        proxy_auth=http.proxy_auth,
                        data=payload,
                        files=files,
                    )
                )
            )
        finally:
            if files:
                for f in files:
                    f.close()

        self._responded = True
        await self._process_callback_response(callback_response)
        if view:
            if not view.is_finished():
                state.store_view(view, message_id)
            view.message = msg or await parent.original_response()

        if delete_after is not None:
            await self._parent.delete_original_response(delay=delete_after)

    async def send_autocomplete_result(
        self,
        *,
        choices: list[OptionChoice],
    ) -> None:
        """|coro|

        Responds to this interaction by sending the autocomplete choices.

        Parameters
        ----------
        choices: List[:class:`OptionChoice`]
            A list of choices.

        Raises
        ------
        HTTPException
            Sending the result failed.
        InteractionResponded
            This interaction has already been responded to before.
        """
        if self._responded:
            raise InteractionResponded(self._parent)

        parent = self._parent

        if parent.type is not InteractionType.auto_complete:
            return

        payload = {"choices": [c.to_dict() for c in choices]}

        adapter = async_context.get()
        http = parent._state.http
        callback_response: InteractionCallbackResponse = await self._locked_response(
            adapter.create_interaction_response(
                parent.id,
                parent.token,
                session=parent._session,
                proxy=http.proxy,
                proxy_auth=http.proxy_auth,
                type=InteractionResponseType.auto_complete_result.value,
                data=payload,
            )
        )

        self._responded = True
        await self._process_callback_response(callback_response)

    async def send_modal(self, modal: BaseModal) -> Interaction:
        """|coro|

        Responds to this interaction by sending a modal dialog.
        This cannot be used to respond to another modal dialog submission.

        Parameters
        ----------
        modal: :class:`discord.ui.BaseModal`
            The modal dialog to display to the user.

        Raises
        ------
        HTTPException
            Sending the modal failed.
        InteractionResponded
            This interaction has already been responded to before.
        """
        if self._responded:
            raise InteractionResponded(self._parent)

        parent = self._parent

        payload = cast("dict[str, Any]", modal.to_dict())
        adapter = async_context.get()
        http = parent._state.http
        callback_response: InteractionCallbackResponse = await self._locked_response(
            adapter.create_interaction_response(
                parent.id,
                parent.token,
                session=parent._session,
                proxy=http.proxy,
                proxy_auth=http.proxy_auth,
                type=InteractionResponseType.modal.value,
                data=payload,
            )
        )
        self._responded = True
        await self._process_callback_response(callback_response)
        user = self._parent.user
        if user is None:
            raise ClientException("The interaction has no user to store the modal for.")
        self._parent._state.store_modal(modal, user.id)
        return self._parent

    @deprecated(
        "InteractionResponse.premium_required is deprecated since version 2.6, consider using a button with type ButtonType.premium instead."
    )
    async def premium_required(self) -> Interaction:
        """|coro|

        Responds to this interaction by sending a premium required message.

        .. deprecated:: 2.6

            A button with type :attr:`ButtonType.premium` should be used instead.

        Raises
        ------
        HTTPException
            Sending the message failed.
        InteractionResponded
            This interaction has already been responded to before.
        """
        if self._responded:
            raise InteractionResponded(self._parent)

        parent = self._parent

        adapter = async_context.get()
        http = parent._state.http
        callback_response: InteractionCallbackResponse = await self._locked_response(
            adapter.create_interaction_response(
                parent.id,
                parent.token,
                session=parent._session,
                proxy=http.proxy,
                proxy_auth=http.proxy_auth,
                type=InteractionResponseType.premium_required.value,
            )
        )
        self._responded = True
        await self._process_callback_response(callback_response)
        return self._parent

    async def launch_activity(self) -> Interaction:
        """|coro|

        Responds to this interaction by launching the activity associated with the bot.

        This is only available for applications that have activities enabled.

        .. versionadded:: 3.0

        Raises
        ------
        HTTPException
            Launching the activity failed.
        InteractionResponded
            This interaction has already been responded to before.
        """
        if self._responded:
            raise InteractionResponded(self._parent)

        parent = self._parent

        adapter = async_context.get()
        http = parent._state.http
        callback_response: InteractionCallbackResponse = await self._locked_response(
            adapter.create_interaction_response(
                parent.id,
                parent.token,
                session=parent._session,
                proxy=http.proxy,
                proxy_auth=http.proxy_auth,
                type=InteractionResponseType.launch_activity.value,
            )
        )
        self._responded = True
        await self._process_callback_response(callback_response)
        return self._parent

    async def _locked_response(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """|coro|

        Wraps a response and makes sure that it's locked while executing.

        Parameters
        ----------
        coro: Coroutine[Any]
            The coroutine to wrap.

        Returns
        -------
        Any
            The result of the coroutine.

        Raises
        ------
        InteractionResponded
            This interaction has already been responded to before.

        .. versionchanged:: 2.7
            Return the result of the coroutine
        """
        async with self._response_lock:
            if self.is_done():
                coro.close()  # cleanup un-awaited coroutine
                raise InteractionResponded(self._parent)
            return await coro


class _InteractionMessageState:
    __slots__ = ("_interaction", "_parent")

    def __init__(self, interaction: Interaction, parent: ConnectionState) -> None:
        self._interaction: Interaction = interaction
        self._parent: ConnectionState = parent

    def _get_guild(self, guild_id: int | None) -> Coroutine[Any, Any, Guild | None]:
        return self._parent._get_guild(guild_id)

    def store_user(self, data: UserPayload) -> Coroutine[Any, Any, User]:
        return self._parent.store_user(data)

    def create_user(self, data: UserPayload) -> User:
        return self._parent.create_user(data)

    @property
    def http(self) -> HTTPClient:
        return self._parent.http

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._parent, attr)


class InteractionMessage(Message):
    """Represents the original interaction response message.

    This allows you to edit or delete the message associated with
    the interaction response. To retrieve this object see :meth:`Interaction.original_response`.

    This inherits from :class:`discord.Message` with changes to
    :meth:`edit` and :meth:`delete` to work.

    .. versionadded:: 2.0
    """

    __slots__ = ()
    _state: _InteractionMessageState  # pyright: ignore[reportIncompatibleVariableOverride]

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
        delete_after: float | None = None,
        suppress: bool | None = MISSING,
        suppress_embeds: bool | None = MISSING,
    ) -> InteractionMessage:
        """|coro|

        Edits the message.

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
        attachments: List[:class:`Attachment`]
            A list of attachments to keep in the message. If ``[]`` is passed
            then all attachments are removed.
        allowed_mentions: :class:`AllowedMentions`
            Controls the mentions being processed in this message.
            See :meth:`.abc.Messageable.send` for more information.
        view: Optional[:class:`~discord.ui.BaseView`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.
        delete_after: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message we just edited. If the deletion fails,
            then it is silently ignored.
        suppress: Optional[:class:`bool`]
            Whether to suppress embeds for the message.

            .. deprecated:: 2.8
        suppress_embeds: Optional[:class:`bool`]
            Whether to suppress embeds for the message.

            .. versionadded:: 2.8

        Returns
        -------
        :class:`InteractionMessage`
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
            The length of ``embeds`` was invalid.
        """
        if attachments is MISSING:
            attachments = self.attachments or MISSING

        if suppress is not MISSING:
            warn_deprecated("suppress", "suppress_embeds", "2.8")
            if suppress_embeds is MISSING:
                suppress_embeds = suppress

        if suppress_embeds is MISSING:
            suppress_embeds = self.flags.suppress_embeds

        return await self._state._interaction.edit_original_response(
            content=content,
            embeds=embeds,
            embed=embed,
            file=file,
            files=files,
            attachments=attachments,
            view=view,
            allowed_mentions=allowed_mentions,
            delete_after=delete_after,
            suppress_embeds=suppress_embeds,
        )

    async def delete(
        self, *, delay: float | None = None, reason: str | None = None
    ) -> None:
        """|coro|

        Deletes the message.

        Parameters
        ----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait before deleting the message.
            The waiting is done in the background and deletion failures are ignored.
        reason: Optional[:class:`str`]
            Ignored, deleting the response of an interaction does not take an
            audit log reason. It only exists so that this method matches
            :meth:`Message.delete`.

        Raises
        ------
        Forbidden
            You do not have proper permissions to delete the message.
        NotFound
            The message was deleted already.
        HTTPException
            Deleting the message failed.
        """
        await self._state._interaction.delete_original_response(delay=delay)


class MessageInteraction:
    """Represents a Discord message interaction.

    This is sent on the message object when the message is a response
    to an interaction without an existing message e.g. application command.

    .. versionadded:: 2.0

    .. deprecated:: 2.6

        See :class:`InteractionMetadata`.

    .. note::
        Responses to message components do not include this property.

    Attributes
    ----------
    id: :class:`int`
        The interaction's ID.
    type: :class:`InteractionType`
        The interaction type.
    name: :class:`str`
        The name of the invoked application command.
    user: :class:`User`
        The user that sent the interaction.
    data: :class:`dict`
        The raw interaction data.
    """

    __slots__: tuple[str, ...] = ("_state", "data", "id", "name", "type", "user")

    def __init__(
        self, *, data: MessageInteractionPayload, state: ConnectionState
    ) -> None:
        self._state = state
        self.data = data
        self.id: int = int(data["id"])
        self.type: InteractionType = try_enum(InteractionType, data["type"])
        self.name: str = data["name"]
        self.user: User = self._state.create_user(data["user"])


class InteractionMetadata:
    """Represents metadata about an interaction.

    This is sent on the message object when the message is related to an interaction

    .. versionadded:: 2.6

    Attributes
    ----------
    id: :class:`int`
        The interaction's ID.
    type: :class:`InteractionType`
        The interaction type.
    user: :class:`User`
        The user that sent the interaction.
    authorizing_integration_owners: :class:`AuthorizingIntegrationOwners`
        The authorizing user or server for the installation(s) relevant to the interaction.
    original_response_message_id: Optional[:class:`int`]
        The ID of the original response message. Only present on interaction follow-up messages.
    interacted_message_id: Optional[:class:`int`]
        The ID of the message that triggered the interaction. Only present on interactions of type
        :attr:`InteractionType.component`.
    triggering_interaction_metadata: Optional[:class:`InteractionMetadata`]
        The metadata of the interaction that opened the model. Only present on interactions of type
        :attr:`InteractionType.modal_submit`.
    """

    __slots__: tuple[str, ...] = (
        "_cs_interacted_message",
        "_cs_original_response_message",
        "_state",
        "authorizing_integration_owners",
        "id",
        "interacted_message_id",
        "original_response_message_id",
        "triggering_interaction_metadata",
        "type",
        "user",
    )

    def __init__(
        self, *, data: InteractionMetadataPayload, state: ConnectionState
    ) -> None:
        self._state = state
        self.id: int = int(data["id"])
        self.type: InteractionType = try_enum(InteractionType, data["type"])
        self.user: User = User(state=state, data=data["user"])
        self.authorizing_integration_owners: AuthorizingIntegrationOwners = (
            AuthorizingIntegrationOwners(data["authorizing_integration_owners"], state)
        )
        self.original_response_message_id: int | None = utils._get_as_snowflake(
            data, "original_response_message_id"
        )
        self.interacted_message_id: int | None = utils._get_as_snowflake(
            data, "interacted_message_id"
        )
        self.triggering_interaction_metadata: InteractionMetadata | None = None
        if tim := data.get("triggering_interaction_metadata"):
            self.triggering_interaction_metadata = InteractionMetadata(
                data=tim, state=state
            )

    def __repr__(self) -> str:
        return (
            f"<InteractionMetadata id={self.id} type={self.type!r} user={self.user!r}>"
        )

    @utils.cached_slot_property("_cs_original_response_message")
    def original_response_message(self) -> Message | None:
        """Optional[:class:`Message`]: The original response message.

        Returns ``None`` if the message is not in cache, or if :attr:`original_response_message_id` is ``None``.
        """
        if not self.original_response_message_id or self._state._messages is None:
            return None
        return self._state._messages.get_nowait(self.original_response_message_id)

    @utils.cached_slot_property("_cs_interacted_message")
    def interacted_message(self) -> Message | None:
        """Optional[:class:`Message`]: The message that triggered the interaction.

        Returns ``None`` if the message is not in cache, or if :attr:`interacted_message_id` is ``None``.
        """
        if not self.interacted_message_id or self._state._messages is None:
            return None
        return self._state._messages.get_nowait(self.interacted_message_id)

    async def get_original_response_message(self) -> Message | None:
        """|coro|

        Returns the original response message from the cache, with any cache backend.

        Returns
        -------
        Optional[:class:`Message`]
            The message, or ``None`` if it is not in cache or :attr:`original_response_message_id` is ``None``.
        """
        if not self.original_response_message_id or self._state._messages is None:
            return None
        return await self._state._messages.get(self.original_response_message_id)

    async def get_interacted_message(self) -> Message | None:
        """|coro|

        Returns the message that triggered the interaction from the cache, with any cache backend.

        Returns
        -------
        Optional[:class:`Message`]
            The message, or ``None`` if it is not in cache or :attr:`interacted_message_id` is ``None``.
        """
        if not self.interacted_message_id or self._state._messages is None:
            return None
        return await self._state._messages.get(self.interacted_message_id)


class AuthorizingIntegrationOwners:
    """Contains details on the authorizing user or server for the installation(s) relevant to the interaction.

    .. versionadded:: 2.6

    Attributes
    ----------
    user_id: :class:`int` | None
        The ID of the user that authorized the integration.
    guild_id: :class:`int` | None
        The ID of the guild that authorized the integration.
        This will be ``0`` if the integration was triggered
        from the user in the bot's DMs.
    """

    __slots__ = ("_cs_guild", "_cs_user", "_state", "guild_id", "user_id")

    def __init__(self, data: Mapping[Any, Any], state: ConnectionState) -> None:
        self._state = state
        # keys are Application Integration Types as strings
        self.user_id = int(uid) if (uid := data.get("1")) is not None else None
        self.guild_id = (
            int(guild_id) if (guild_id := data.get("0")) is not None else None
        )

    def __repr__(self) -> str:
        return f"<AuthorizingIntegrationOwners user_id={self.user_id} guild_id={self.guild_id}>"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, AuthorizingIntegrationOwners)
            and self.user_id == other.user_id
            and self.guild_id == other.guild_id
        )

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash((self.user_id, self.guild_id))

    @utils.cached_slot_property("_cs_user")
    def user(self) -> User | None:
        """Optional[:class:`User`]: The user that authorized the integration.

        Returns ``None`` if the user is not in cache, or if :attr:`user_id` is ``None``.
        """
        if not self.user_id:
            return None
        return self._state._users.get_nowait(self.user_id)

    @utils.cached_slot_property("_cs_guild")
    def guild(self) -> Guild | None:
        """Optional[:class:`Guild`]: The guild that authorized the integration.

        Returns ``None`` if the guild is not in cache, or if :attr:`guild_id` is ``0`` or ``None``.
        """
        if not self.guild_id:
            return None
        return self._state._guilds.get_nowait(self.guild_id)

    async def get_user(self) -> User | None:
        """|coro|

        Returns the user that authorized the integration from the cache, with any cache backend.

        Returns
        -------
        Optional[:class:`User`]
            The user, or ``None`` if the user is not in cache or :attr:`user_id` is ``None``.
        """
        if not self.user_id:
            return None
        return await self._state._users.get(self.user_id)

    async def get_guild(self) -> Guild | None:
        """|coro|

        Returns the guild that authorized the integration from the cache, with any cache backend.

        Returns
        -------
        Optional[:class:`Guild`]
            The guild, or ``None`` if the guild is not in cache or :attr:`guild_id` is ``0`` or ``None``.
        """
        if not self.guild_id:
            return None
        return await self._state._guilds.get(self.guild_id)


class InteractionCallback:
    """Information about the status of the interaction response.

    .. versionadded:: 2.7
    """

    def __init__(self, data: InteractionCallbackPayload) -> None:
        self._activity_instance_id: str | None = data.get("activity_instance_id")
        self._response_message_loading: bool = data.get(
            "response_message_loading", False
        )
        self._response_message_ephemeral: bool = data.get(
            "response_message_ephemeral", False
        )

    def __repr__(self) -> str:
        return (
            f"<InteractionCallback "
            f"_activity_instance_id={self._activity_instance_id} "
            f"_response_message_loading={self._response_message_loading} "
            f"_response_message_ephemeral={self._response_message_ephemeral}>"
        )

    def is_loading(self) -> bool:
        """Indicates whether the response message is in a loading state."""
        return self._response_message_loading

    def is_ephemeral(self) -> bool:
        """Indicates whether the response message is ephemeral.

        This might be useful for determining if the message was forced to be ephemeral.
        """
        return self._response_message_ephemeral

    @property
    def activity_instance_id(self) -> str | None:
        """Instance ID of the Activity if one was launched or joined.

        If no activity was launched or joined this will be ``None``.

        .. versionadded:: 3.0
        """
        return self._activity_instance_id


class InteractionCallbackActivityInstanceResource:
    """Information about the Activity that was launched or joined as a response to an interaction.

    .. versionadded:: 3.0

    Attributes
    ----------
    id: :class:`str`
        Instance ID of the Activity that was launched or joined.
    """

    __slots__ = ("id",)

    def __init__(self, data: InteractionCallbackActivityInstancePayload) -> None:
        self.id: str = data["id"]

    def __repr__(self) -> str:
        return f"<InteractionCallbackActivityInstanceResource id={self.id!r}>"
