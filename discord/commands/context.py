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

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, cast, overload

from typing_extensions import ParamSpec, TypeVar

import discord.abc
from discord.channel import PartialMessageable
from discord.errors import CheckFailure
from discord.guild import Guild
from discord.interactions import Interaction, InteractionMessage, InteractionResponse
from discord.webhook.async_ import Webhook

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from .. import AllowedMentions, Bot
    from ..abc import MessageableChannel
    from ..client import ClientUser
    from ..cog import Cog
    from ..embeds import Embed
    from ..file import File
    from ..guild import PartialGuild
    from ..interactions import InteractionChannel
    from ..member import Member
    from ..message import Message
    from ..permissions import Permissions
    from ..poll import Poll
    from ..state import ConnectionState
    from ..ui import BaseView
    from ..user import User
    from ..voice import VoiceProtocol
    from ..webhook import WebhookMessage
    from .core import ApplicationCommand, Option

T = TypeVar("T", default=Any)
CogT = TypeVar("CogT", bound="Cog", default=Any)
P = ParamSpec("P", default=...)

# The attributes of the contexts that are set when a command is invoked.
_UNSET: Any = None

__all__ = ("ApplicationContext", "AutocompleteContext", "BaseContext")


class BaseContext(discord.abc.Messageable, ABC):
    """The base class of the contexts commands are invoked with.

    It holds the members that do not depend on whether the command was
    invoked from an interaction or from a message. This is subclassed by
    :class:`.ApplicationContext` and :class:`~discord.ext.commands.Context`.

    .. versionadded:: 3.0

    Attributes
    ----------
    bot: :class:`.Bot`
        The bot that the command belongs to.
    command: Optional[Union[:class:`.ApplicationCommand`, :class:`~discord.ext.commands.Command`]]
        The command that this context belongs to.
    """

    if TYPE_CHECKING:
        bot: Any
        command: Any

    @property
    @abstractmethod
    def guild(self) -> Guild | PartialGuild | None:
        """Returns the guild associated with this context's command.

        This is the cached guild with the in-process cache and a
        :class:`PartialGuild` handle when it is not cached or the cache backend
        is not the in-process one. Use :meth:`get_guild` to get the cached guild
        with any cache backend.
        """

    async def get_guild(self) -> Guild | None:
        """|coro|

        Returns the cached guild associated with this context's command.

        Returns
        -------
        Optional[:class:`Guild`]
            The guild, or ``None`` if it is not cached or the context is not in a guild.
        """
        guild = self.guild
        if guild is None or isinstance(guild, Guild):
            return guild
        return await guild.get()

    @property
    @abstractmethod
    def channel(self) -> InteractionChannel | MessageableChannel | None:
        """Returns the channel associated with this context's command."""

    @abstractmethod
    async def get_channel(self) -> MessageableChannel | None:
        """|coro|

        Returns the cached channel associated with this context's command.

        Returns
        -------
        Optional[:class:`.abc.Messageable`]
            The channel, or ``None`` if it is not cached.
        """

    @property
    @abstractmethod
    def author(self) -> Member | User:
        """Returns the user that invoked this context's command."""

    @property
    def cog(self) -> Cog | None:
        """Returns the cog associated with this context's command.

        ``None`` if it does not exist.
        """
        if self.command is None:
            return None

        return self.command.cog

    def _check_failure(self, message: str) -> CheckFailure:
        return CheckFailure(message)

    @property
    def me(self) -> Member | ClientUser:
        """Union[:class:`.Member`, :class:`.ClientUser`]: Similar to :attr:`.Guild.me` except it may return the :class:`.ClientUser` in private message message contexts, when :meth:`Intents.guilds` is absent, or when the guild or the member is not available in the in-process cache.

        Use :meth:`get_me` to read the cached member with any cache backend.
        """
        guild = self.guild
        if isinstance(guild, Guild) and guild._state.cache.supports_sync:
            me = guild.me
            if me is not None:  # pyright: ignore[reportUnnecessaryComparison]
                return me

        return cast("ClientUser", self.bot.user)

    async def get_me(self) -> Member | ClientUser:
        """|coro|

        Similar to :attr:`me`, using the asynchronous cache accessors so that it works
        with every cache backend.

        Returns
        -------
        Union[:class:`.Member`, :class:`.ClientUser`]
            The cached member of the client user in the guild of this context, or the
            :class:`.ClientUser` when there is none.
        """
        guild = self.guild
        if guild is not None:
            state = self.bot._connection
            if state.self_id is not None:
                me = await state._guild_bucket("members", guild.id).get(state.self_id)
                if me is not None:
                    return cast("Member", me)

        return cast("ClientUser", self.bot.user)

    @property
    def voice_client(self) -> VoiceProtocol[Any] | None:
        r"""A shortcut to :attr:`.Guild.voice_client`\, if applicable."""
        guild = self.guild
        if guild is None:
            return None
        return cast(
            "VoiceProtocol[Any] | None",
            self.bot._connection._get_voice_client(guild.id),
        )


class ApplicationContext(BaseContext):
    """Represents a Discord application command interaction context.

    This class is not created manually and is instead passed to application
    commands as the first parameter.

    .. versionadded:: 2.0

    Attributes
    ----------
    bot: :class:`.Bot`
        The bot that the command belongs to.
    interaction: :class:`.Interaction`
        The interaction object that invoked the command.
    """

    def __init__(self, bot: Bot, interaction: Interaction) -> None:
        self.bot = bot
        self.interaction = interaction

        # below attributes will be set after initialization
        self.focused: Option = _UNSET
        self.value: str = _UNSET
        self.options: dict[str, Any] = _UNSET
        self.command_failed: bool = False

        self._state: ConnectionState = self.interaction._state

    async def _get_channel(self) -> MessageableChannel:
        return cast("MessageableChannel", self.interaction.channel)

    async def invoke(
        self,
        command: ApplicationCommand[CogT, P, T],
        /,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        r"""|coro|

        Calls a command with the arguments given.
        This is useful if you want to just call the callback that a
        :class:`.ApplicationCommand` holds internally.

        .. note::

            This does not handle converters, checks, cooldowns, pre-invoke,
            or after-invoke hooks in any matter. It calls the internal callback
            directly as-if it was a regular function.
            You must take care in passing the proper arguments when
            using this function.

        Parameters
        ----------
        command: :class:`.ApplicationCommand`
            The command that is going to be called.
        \*args
            The arguments to use.
        \*\*kwargs
            The keyword arguments to use.

        Raises
        ------
        TypeError
            The command argument to invoke is missing.
        """
        return await command(self, *args, **kwargs)

    @property
    def command(self) -> ApplicationCommand | None:
        """The command that this context belongs to."""
        return self.interaction.command

    @command.setter
    def command(self, value: ApplicationCommand | None) -> None:
        self.interaction.command = value

    @property
    def channel(self) -> InteractionChannel | None:
        """Union[:class:`abc.GuildChannel`, :class:`PartialMessageable`, :class:`Thread`]: Returns the channel associated with this context's command.

        Shorthand for :attr:`.Interaction.channel`.
        """
        return self.interaction.channel

    async def get_channel(self) -> MessageableChannel | None:
        """|coro|

        Returns the channel associated with this context's command.

        Returns
        -------
        Optional[Union[:class:`abc.GuildChannel`, :class:`Thread`, :class:`DMChannel`, :class:`GroupChannel`]]
            The channel of the interaction payload, or the cached channel when the payload
            has none, ``None`` if it is not cached.
        """
        channel = self.interaction.channel
        if isinstance(channel, PartialMessageable):
            return await channel.get()
        return cast("MessageableChannel | None", channel)

    @property
    def channel_id(self) -> int | None:
        """Returns the ID of the channel associated with this context's command.

        Shorthand for :attr:`.Interaction.channel_id`.
        """
        return self.interaction.channel_id

    @property
    def guild(self) -> Guild | PartialGuild | None:
        """Returns the guild associated with this context's command.

        Shorthand for :attr:`.Interaction.guild`.
        """
        return self.interaction.guild

    @property
    def guild_id(self) -> int | None:
        """Returns the ID of the guild associated with this context's command.

        Shorthand for :attr:`.Interaction.guild_id`.
        """
        return self.interaction.guild_id

    @property
    def locale(self) -> str | None:
        """Returns the locale of the guild associated with this context's command.

        Shorthand for :attr:`.Interaction.locale`.
        """
        return self.interaction.locale

    @property
    def guild_locale(self) -> str | None:
        """Returns the locale of the guild associated with this context's command.

        Shorthand for :attr:`.Interaction.guild_locale`.
        """
        return self.interaction.guild_locale

    @property
    def app_permissions(self) -> Permissions:
        """Returns the permissions of the application in the channel of this context's command.

        Shorthand for :attr:`.Interaction.app_permissions`.
        """
        return self.interaction.app_permissions

    @property
    def message(self) -> Message | None:
        """Returns the message sent with this context's command.

        Shorthand for :attr:`.Interaction.message`, if applicable.
        """
        return self.interaction.message

    @property
    def user(self) -> Member | User:
        """Returns the user that sent this context's command.

        Shorthand for :attr:`.Interaction.user`.
        """
        return cast("Member | User", self.interaction.user)

    @property
    def author(self) -> Member | User:
        """Returns the user that sent this context's command.

        An alias of :attr:`user`.
        """
        return self.user

    @property
    def response(self) -> InteractionResponse:
        """Returns the response object associated with this context's command.

        Shorthand for :attr:`.Interaction.response`.
        """
        return self.interaction.response

    @property
    def selected_options(self) -> list[dict[str, Any]] | None:
        """The options and values that were selected by the user when sending the command.

        Returns
        -------
        Optional[List[Dict[:class:`str`, Any]]]
            A dictionary containing the options and values that were selected by the user when the command
            was processed, if applicable. Returns ``None`` if the command has not yet been invoked,
            or if there are no options defined for that command.
        """
        data = cast("dict[str, Any] | None", self.interaction.data)
        if data is None:
            return None
        return data.get("options", None)

    @property
    def unselected_options(self) -> list[Option] | None:
        """The options that were not provided by the user when sending the command.

        Returns
        -------
        Optional[List[:class:`.Option`]]
            A list of Option objects (if any) that were not selected by the user when the command was processed.
            Returns ``None`` if there are no options defined for that command.
        """
        options: list[Option] | None = getattr(self.command, "options", None)
        if options is not None:
            if selected_options := self.selected_options:
                return [
                    option
                    for option in options
                    if option.to_dict()["name"]
                    not in [opt["name"] for opt in selected_options]
                ]
            return options
        return None

    @property
    def attachment_size_limit(self) -> int:
        """Returns the attachment size limit associated with this context's interaction.

        Shorthand for :attr:`.Interaction.attachment_size_limit`.
        """
        return self.interaction.attachment_size_limit

    @property
    @discord.utils.copy_doc(InteractionResponse.send_modal)
    def send_modal(self) -> Callable[..., Awaitable[Interaction]]:
        """Alias of :meth:`.InteractionResponse.send_modal`."""
        return self.interaction.response.send_modal

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

    @discord.utils.copy_doc(Interaction.respond)
    async def respond(self, *args: Any, **kwargs: Any) -> Interaction | WebhookMessage:
        """Alias of :meth:`.Interaction.respond`."""
        return await self.interaction.respond(*args, **kwargs)

    @property
    @discord.utils.copy_doc(InteractionResponse.send_message)
    def send_response(self) -> Callable[..., Awaitable[Interaction]]:
        """Alias of :meth:`.InteractionResponse.send_message`."""
        if not self.interaction.response.is_done():
            return self.interaction.response.send_message
        raise RuntimeError(
            "Interaction was already issued a response. Try using"
            f" {type(self).__name__}.send_followup() instead."
        )

    @property
    @discord.utils.copy_doc(Webhook.send)
    def send_followup(self) -> Callable[..., Awaitable[WebhookMessage]]:
        """Alias of :meth:`.Webhook.send` on the followup webhook."""
        if self.interaction.response.is_done():
            return self.followup.send
        raise RuntimeError(
            "Interaction was not yet issued a response. Try using"
            f" {type(self).__name__}.respond() first."
        )

    @property
    @discord.utils.copy_doc(InteractionResponse.defer)
    def defer(self) -> Callable[..., Awaitable[None]]:
        """Alias of :meth:`.InteractionResponse.defer`."""
        return self.interaction.response.defer

    @property
    def followup(self) -> Webhook:
        """Returns the followup webhook for followup interactions."""
        return self.interaction.followup

    async def delete(self, *, delay: float | None = None) -> None:
        """|coro|

        Deletes the original interaction response message.

        This is a higher level interface to :meth:`Interaction.delete_original_response`.

        Parameters
        ----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait before deleting the message.

        Raises
        ------
        HTTPException
            Deleting the message failed.
        Forbidden
            You do not have proper permissions to delete the message.
        """
        if not self.interaction.response.is_done():
            await self.defer()

        return await self.interaction.delete_original_response(delay=delay)

    @property
    @discord.utils.copy_doc(Interaction.edit_original_response)
    def edit(self) -> Callable[..., Awaitable[InteractionMessage]]:
        """Alias of :meth:`.Interaction.edit_original_response`."""
        return self.interaction.edit_original_response

    def is_guild_authorised(self) -> bool:
        """:class:`bool`: Checks if the invoked command is guild-installed.

        This is a shortcut for :meth:`Interaction.is_guild_authorised`.

        There is an alias for this called :meth:`.is_guild_authorized`.

        .. versionadded:: 2.7
        """
        return self.interaction.is_guild_authorised()

    def is_user_authorised(self) -> bool:
        """:class:`bool`: Checks if the invoked command is user-installed.

        This is a shortcut for :meth:`Interaction.is_user_authorised`.

        There is an alias for this called :meth:`.is_user_authorized`.

        .. versionadded:: 2.7
        """
        return self.interaction.is_user_authorised()

    def is_guild_authorized(self) -> bool:
        """:class:`bool`: An alias for :meth:`.is_guild_authorised`.

        .. versionadded:: 2.7
        """
        return self.is_guild_authorised()

    def is_user_authorized(self) -> bool:
        """:class:`bool`: An alias for :meth:`.is_user_authorised`.

        .. versionadded:: 2.7
        """
        return self.is_user_authorised()


class AutocompleteContext:
    """Represents context for a slash command's option autocomplete.

    This class is not created manually and is instead passed to an :class:`.Option`'s autocomplete callback.

    .. versionadded:: 2.0

    Attributes
    ----------
    bot: :class:`.Bot`
        The bot that the command belongs to.
    interaction: :class:`.Interaction`
        The interaction object that invoked the autocomplete.
    focused: :class:`.Option`
        The option the user is currently typing.
    value: :class:`.str`
        The content of the focused option.
    options: Dict[:class:`str`, Any]
        A name to value mapping of the options that the user has selected before this option.
    """

    __slots__ = ("bot", "focused", "interaction", "options", "value")

    def __init__(self, bot: Bot, interaction: Interaction) -> None:
        self.bot = bot
        self.interaction = interaction

        self.focused: Option = _UNSET
        self.value: str = _UNSET
        self.options: dict[str, Any] = _UNSET

    @property
    def cog(self) -> Cog | None:
        """Returns the cog associated with this context's command.

        ``None`` if it does not exist.
        """
        if self.command is None:
            return None

        return self.command.cog

    @property
    def command(self) -> ApplicationCommand | None:
        """The command that this context belongs to."""
        return self.interaction.command

    @command.setter
    def command(self, value: ApplicationCommand | None) -> None:
        self.interaction.command = value
