"""
The MIT License (MIT)

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

from functools import cached_property
from typing import TYPE_CHECKING, Any, cast

from ._internal.cache_peek import cached_emoji
from .enums import OnboardingMode, PromptType, try_enum
from .object import Object
from .partial_emoji import PartialEmoji
from .utils import MISSING, generate_snowflake, get

if TYPE_CHECKING:
    from .abc import GuildChannel, Snowflake
    from .channel import ForumChannel, TextChannel, VoiceChannel
    from .emoji import AppEmoji, GuildEmoji
    from .guild import Guild, PartialGuild
    from .role import Role
    from .state import ConnectionState
    from .types.emoji import PartialEmoji as EmojiPayload
    from .types.onboarding import (
        Onboarding as OnboardingPayload,
        OnboardingPrompt as OnboardingPromptPayload,
        PromptOption as PromptOptionPayload,
    )
    from .types.snowflake import Snowflake as SnowflakePayload

__all__ = (
    "Onboarding",
    "OnboardingPrompt",
    "PromptOption",
)


class PromptOption:
    """Represents an onboarding prompt option displayed in :class:`OnboardingPrompt`.

    .. versionadded:: 2.5

    Attributes
    ----------
    id: :class:`int`
        The id of the prompt option.
    channels: List[:class:`Snowflake`]
        The channels assigned to the user when they select this option.
    roles: List[:class:`Snowflake`]
        The roles assigned to the user when they select this option.
    emoji: Union[:class:`GuildEmoji`, :class:`PartialEmoji`]
        The emoji displayed with the option.
    title: :class:`str`
        The option's title.
    description: Optional[:class:`str`]
        The option's description.
    """

    def __init__(
        self,
        title: str,
        channels: list[Snowflake] | None = None,
        roles: list[Snowflake] | None = None,
        description: str | None = None,
        emoji: GuildEmoji | AppEmoji | PartialEmoji | None = None,
        id: int | str | None = None,
    ) -> None:
        # ID is required when making edits, but it can be any snowflake that isn't already used by another prompt during edits
        self.id: int = int(id) if id else generate_snowflake()
        self.title: str = title
        self._channels: list[Snowflake] = channels or []
        self._roles: list[Snowflake] = roles or []
        self.description: str | None = description or None
        self._emoji: GuildEmoji | AppEmoji | PartialEmoji | None = emoji
        self._state: ConnectionState | None = None
        self._guild_id: int | None = None

    @property
    def channels(self) -> list[Snowflake]:
        """The channels assigned to the user when they select this option.

        A channel that is in the in-process cache is the cached
        :class:`~discord.abc.GuildChannel`, otherwise it is the :class:`Object`
        (or the snowflake) it was built with. Use :meth:`get_channels` with any
        cache backend.
        """
        state, guild_id = self._state, self._guild_id
        if state is None or guild_id is None or not state.cache.supports_sync:
            return list(self._channels)
        bucket = state._guild_bucket("channels", guild_id)
        return [bucket.get_nowait(channel.id) or channel for channel in self._channels]

    @channels.setter
    def channels(self, value: list[Snowflake]) -> None:
        self._channels = value

    @property
    def roles(self) -> list[Snowflake]:
        """The roles assigned to the user when they select this option.

        A role that is in the in-process cache is the cached :class:`Role`,
        otherwise it is the :class:`Object` (or the snowflake) it was built with.
        Use :meth:`get_roles` with any cache backend.
        """
        state, guild_id = self._state, self._guild_id
        if state is None or guild_id is None or not state.cache.supports_sync:
            return list(self._roles)
        bucket = state._guild_bucket("roles", guild_id)
        return [bucket.get_nowait(role.id) or role for role in self._roles]

    @roles.setter
    def roles(self, value: list[Snowflake]) -> None:
        self._roles = value

    @property
    def emoji(self) -> GuildEmoji | AppEmoji | PartialEmoji | None:
        """The emoji displayed with the option.

        A custom emoji that is in the in-process cache is the cached
        :class:`GuildEmoji`, otherwise it is the :class:`PartialEmoji`.
        Use :meth:`get_emoji` with any cache backend.
        """
        emoji = self._emoji
        if self._state is None or emoji is None or not emoji.id:
            return emoji
        return cached_emoji(self._state, emoji.id) or emoji

    @emoji.setter
    def emoji(self, value: GuildEmoji | AppEmoji | PartialEmoji | None) -> None:
        self._emoji = value

    def __repr__(self) -> str:
        return f"<PromptOption id={self.id} title={self.title!r} description={self.description!r} emoji={self.emoji!r}>"

    def to_dict(self) -> PromptOptionPayload:
        """Convert this object to the payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The payload.
        """
        dict_: PromptOptionPayload = {
            "title": self.title,
            "description": self.description,
            "channel_ids": [channel.id for channel in self._channels],
            "role_ids": [role.id for role in self._roles],
            "id": str(self.id),
        }
        if emoji := self._emoji:
            dict_["emoji"] = cast(
                "EmojiPayload",
                {
                    "id": str(emoji.id) if emoji.id else None,
                    "name": emoji.name,
                    "animated": emoji.animated,
                },
            )
            dict_["emoji_name"] = cast("str", emoji.name)
            if emoji.id:
                dict_["emoji_id"] = str(emoji.id)
                dict_["emoji_animated"] = emoji.animated

        return dict_

    async def get_channels(self) -> list[GuildChannel | Snowflake]:
        """|coro|

        Returns the channels assigned to the user when they select this option.

        .. versionadded:: 3.0

        Returns
        -------
        List[Union[:class:`~discord.abc.GuildChannel`, :class:`Snowflake`]]
            The cached channels, a channel that is not cached is left as it is.
        """
        if self._state is None or self._guild_id is None:
            return list(self._channels)
        bucket = self._state._guild_bucket("channels", self._guild_id)
        return [await bucket.get(channel.id) or channel for channel in self._channels]

    async def get_roles(self) -> list[Role | Snowflake]:
        """|coro|

        Returns the roles assigned to the user when they select this option.

        .. versionadded:: 3.0

        Returns
        -------
        List[Union[:class:`Role`, :class:`Snowflake`]]
            The cached roles, a role that is not cached is left as it is.
        """
        if self._state is None or self._guild_id is None:
            return list(self._roles)
        bucket = self._state._guild_bucket("roles", self._guild_id)
        return [await bucket.get(role.id) or role for role in self._roles]

    async def get_emoji(self) -> GuildEmoji | AppEmoji | PartialEmoji | None:
        """|coro|

        Returns the emoji displayed with the option.

        .. versionadded:: 3.0

        Returns
        -------
        Optional[Union[:class:`GuildEmoji`, :class:`PartialEmoji`]]
            The cached emoji if there is one, else the partial emoji.
        """
        emoji = self._emoji
        if self._state is None or emoji is None or not emoji.id:
            return emoji
        return await self._state.get_emoji(emoji.id) or emoji

    @classmethod
    def _from_dict(
        cls, data: PromptOptionPayload, guild: Guild | PartialGuild
    ) -> PromptOption:
        id = data.get("id", 0)
        channels: list[Snowflake] = [
            Object(int(channel_id)) for channel_id in data.get("channel_ids", [])
        ]
        roles: list[Snowflake] = [
            Object(int(role_id)) for role_id in data.get("role_ids", [])
        ]
        title = data.get("title")
        description = data.get("description")

        _emoji = cast("dict[str, Any]", data.get("emoji") or {})
        # Emoji object is {'id': None, 'name': None, 'animated': False} ...
        emoji = PartialEmoji.from_dict(_emoji) if "name" in _emoji else None

        option = cls(
            channels=channels,
            roles=roles,
            title=title,
            description=description,
            emoji=emoji,
            id=id,
        )
        option._state = guild._state
        option._guild_id = guild.id
        return option


class OnboardingPrompt:
    """Represents an onboarding prompt displayed in :class:`Onboarding`.

    .. versionadded:: 2.5

    Attributes
    ----------
    id: :class:`int`
        The id of the prompt.
    type: :class:`PromptType`
        The type of onboarding prompt.
    title: :class:`str`
        The prompt's title.
    options: List[:class:`PromptOption`]
        The list of options available in the prompt.
    single_select: :class:`bool`
        Whether the user is limited to selecting one option on this prompt.
    required: :class:`bool`
        Whether the user is required to answer this prompt.
    in_onboarding: :class:`bool`
        Whether this prompt is displayed in the initial onboarding flow.
    """

    def __init__(
        self,
        type: PromptType,
        title: str,
        options: list[PromptOption],
        single_select: bool,
        required: bool,
        in_onboarding: bool,
        id: int
        | str
        | None = None,  # Currently optional as users can manually create these
    ) -> None:
        # ID is required when making edits, but it can be any snowflake that isn't already used by another prompt during edits
        self.id: int = int(id) if id else generate_snowflake()

        self.type: PromptType = type
        if isinstance(self.type, int):
            self.type = try_enum(PromptType, self.type)
        self.options: list[PromptOption] = options
        self.title: str = title
        self.single_select: bool = single_select
        self.required: bool = required
        self.in_onboarding: bool = in_onboarding

    def __repr__(self) -> str:
        return f"<OnboardingPrompt id={self.id} title={self.title!r} required={self.required}>"

    def to_dict(self) -> OnboardingPromptPayload:
        """Convert this object to the payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The payload.
        """
        dict_: OnboardingPromptPayload = {
            "type": self.type.value,
            "title": self.title,
            "single_select": self.single_select,
            "required": self.required,
            "in_onboarding": self.in_onboarding,
            "options": [option.to_dict() for option in self.options],
            "id": self.id,
        }

        return dict_

    @classmethod
    def _from_dict(
        cls, data: OnboardingPromptPayload, guild: Guild | PartialGuild
    ) -> OnboardingPrompt:
        id = data.get("id", 0)
        type = try_enum(PromptType, data.get("type"))
        title = data.get("title")
        single_select = data.get("single_select")
        required = data.get("required")
        in_onboarding = data.get("in_onboarding")
        options = [
            PromptOption._from_dict(option, guild) for option in data.get("options", [])
        ]

        return cls(
            type=type,
            title=title,
            single_select=single_select,
            required=required,
            in_onboarding=in_onboarding,
            options=options,
            id=id,
        )


class Onboarding:
    """Represents the onboarding flow for a guild.

    .. versionadded:: 2.5

    Attributes
    ----------
    prompts: List[:class:`OnboardingPrompt`]
        A list of prompts displayed in the onboarding flow.
    enabled: :class:`bool`
        Whether onboarding is enabled in the guild.
    mode: :class:`OnboardingMode`
        The current onboarding mode.
    """

    def __init__(self, data: OnboardingPayload, guild: Guild | PartialGuild) -> None:
        self.guild = guild
        self._update(data)

    def __repr__(self) -> str:
        return f"<Onboarding guild={self.guild!r} enabled={self.enabled} mode={self.mode} prompts={self.prompts}>"

    def _update(self, data: OnboardingPayload) -> None:
        self.guild_id: SnowflakePayload = data["guild_id"]
        self.prompts: list[OnboardingPrompt] = [
            OnboardingPrompt._from_dict(prompt, self.guild)
            for prompt in data.get("prompts", [])
        ]
        self.default_channel_ids: list[int] = [
            int(c) for c in data["default_channel_ids"]
        ]
        self.enabled: bool = data["enabled"]
        self.mode: OnboardingMode = try_enum(OnboardingMode, data.get("mode"))

    @cached_property
    def default_channels(
        self,
    ) -> list[TextChannel | ForumChannel | VoiceChannel | Object]:
        """The channels that members are opted into by default.

        If a channel is not found in the guild's cache,
        then it will be returned as an :class:`Object`.

        This reads the in-memory cache, use :meth:`get_default_channels` with any
        cache backend.
        """
        bucket = self.guild._state._guild_bucket("channels", self.guild.id)
        return [
            bucket.get_nowait(channel_id) or Object(channel_id)
            for channel_id in self.default_channel_ids
        ]

    async def get_default_channels(
        self,
    ) -> list[TextChannel | ForumChannel | VoiceChannel | Object]:
        """|coro|

        Returns the channels that members are opted into by default.

        If a channel is not found in the guild's cache,
        then it will be returned as an :class:`Object`.

        .. versionadded:: 3.0

        Returns
        -------
        List[Union[:class:`TextChannel`, :class:`ForumChannel`, :class:`VoiceChannel`, :class:`Object`]]
            The default channels.
        """
        bucket = self.guild._state._guild_bucket("channels", self.guild.id)
        return [
            await bucket.get(channel_id) or Object(channel_id)
            for channel_id in self.default_channel_ids
        ]

    async def edit(
        self,
        *,
        prompts: list[OnboardingPrompt] | None = MISSING,
        default_channels: list[Snowflake] | None = MISSING,
        enabled: bool | None = MISSING,
        mode: OnboardingMode | None = MISSING,
        reason: str | None = MISSING,
    ) -> Onboarding:
        """|coro|

        Edits this onboarding flow.

        You must have the :attr:`~Permissions.manage_guild` and :attr:`~Permissions.manage_roles` permissions in the
        guild to do this.

        Parameters
        ----------
        prompts: Optional[List[:class:`OnboardingPrompt`]]
            The new list of prompts for this flow.
        default_channels: Optional[List[:class:`Snowflake`]]
            The new default channels that users are opted into.
        enabled: Optional[:class:`bool`]
            Whether onboarding should be enabled. Setting this to ``True`` requires
            the guild to have ``COMMUNITY`` in :attr:`~Guild.features` and at
            least 7 ``default_channels``.
        mode: Optional[:class:`OnboardingMode`]
            The new onboarding mode.
        reason: Optional[:class:`str`]
            The reason for editing this onboarding flow. Shows up on the audit log.

        Returns
        -------
        :class:`Onboarding`
            The updated onboarding flow.

        Raises
        ------
        HTTPException
            Editing the onboarding flow failed somehow.
        Forbidden
            You don't have permissions to edit the onboarding flow.
        """
        fields: dict[str, Any] = {}
        if prompts is not MISSING:
            fields["prompts"] = [
                prompt.to_dict() for prompt in cast("list[OnboardingPrompt]", prompts)
            ]

        if default_channels is not MISSING:
            fields["default_channel_ids"] = [
                channel.id for channel in cast("list[Snowflake]", default_channels)
            ]

        if enabled is not MISSING:
            fields["enabled"] = enabled

        if mode is not MISSING:
            fields["mode"] = cast("OnboardingMode", mode).value

        new = await self.guild._state.http.edit_onboarding(
            self.guild.id, fields, reason=reason
        )
        self._update(new)
        return self

    async def add_prompt(
        self,
        type: PromptType,
        title: str,
        options: list[PromptOption],
        single_select: bool,
        required: bool,
        in_onboarding: bool,
        *,
        reason: str | None = None,
    ) -> Onboarding:
        """|coro|

        Adds a new onboarding prompt.

        You must have the :attr:`~Permissions.manage_guild` and :attr:`~Permissions.manage_roles` permissions in the
        guild to do this.

        Parameters
        ----------
        type: :class:`PromptType`
            The type of onboarding prompt.
        title: :class:`str`
            The prompt's title.
        options: List[:class:`PromptOption`]
            The list of options available in the prompt.
        single_select: :class:`bool`
            Whether the user is limited to selecting one option on this prompt.
        required: :class:`bool`
            Whether the user is required to answer this prompt.
        in_onboarding: :class:`bool`
            Whether this prompt is displayed in the initial onboarding flow.
        reason: Optional[:class:`str`]
            The reason for adding this prompt. Shows up on the audit log.

        Returns
        -------
        :class:`Onboarding`
            The updated onboarding flow.

        Raises
        ------
        HTTPException
            Editing the onboarding flow failed somehow.
        Forbidden
            You don't have permissions to edit the onboarding flow.
        """
        prompt = OnboardingPrompt(
            type, title, options, single_select, required, in_onboarding
        )
        prompts = [*self.prompts, prompt]
        return await self.edit(prompts=prompts, reason=reason)

    async def append_prompt(
        self,
        prompt: OnboardingPrompt,
        *,
        reason: str | None = None,
    ) -> Onboarding:
        """|coro|

        Append an onboarding prompt onto this flow.

        You must have the :attr:`~Permissions.manage_guild` and :attr:`~Permissions.manage_roles` permissions in the
        guild to do this.

        Parameters
        ----------
        prompt: :class:`OnboardingPrompt`
            The onboarding prompt to append.
        reason: Optional[:class:`str`]
            The reason for appending this prompt. Shows up on the audit log.

        Returns
        -------
        :class:`Onboarding`
            The updated onboarding flow.

        Raises
        ------
        HTTPException
            Editing the onboarding flow failed somehow.
        Forbidden
            You don't have permissions to edit the onboarding flow.
        """
        prompts = [*self.prompts, prompt]
        return await self.edit(prompts=prompts, reason=reason)

    def get_prompt(
        self,
        id: int,
    ) -> OnboardingPrompt | None:
        """Get an onboarding prompt with the given ID.

        Parameters
        ----------
        id: :class:`int`
            The ID of the prompt to get.

        Returns
        -------
        :class:`OnboardingPrompt`
            The matching prompt, or None if it didn't exist.
        """
        return get(self.prompts, id=id)

    async def delete_prompt(
        self,
        id: int,
        *,
        reason: str | None = MISSING,
    ) -> Onboarding:
        """|coro|

        Delete an onboarding prompt with the given ID.

        You must have the :attr:`~Permissions.manage_guild` and :attr:`~Permissions.manage_roles` permissions in the
        guild to do this.

        Parameters
        ----------
        id: :class:`int`
            The ID of the prompt to delete.
        reason: Optional[:class:`str`]
            The reason for deleting this prompt. Shows up on the audit log.

        Returns
        -------
        :class:`Onboarding`
            The updated onboarding flow.

        Raises
        ------
        ValueError
            No prompt with this ID exists.
        HTTPException
            Editing the onboarding flow failed somehow.
        Forbidden
            You don't have permissions to edit the onboarding flow.
        """
        to_delete = self.get_prompt(id)
        if not to_delete:
            raise ValueError("Prompt with the given ID was not found.")

        prompts = self.prompts[:]
        prompts.remove(to_delete)
        return await self.edit(prompts=prompts, reason=reason)
