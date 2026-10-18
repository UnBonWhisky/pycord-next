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

import datetime as dt
from typing import TYPE_CHECKING, Any, cast

from typing_extensions import deprecated

from . import utils
from ._internal.aliases import AliasMixin
from ._internal.cache_peek import cached_guild, cached_guild_channel
from .automod import AutoModAction, AutoModTriggerType
from .enums import (
    AuditLogAction,
    ChannelType,
    ReactionType,
    try_enum,
)

if TYPE_CHECKING:
    from collections.abc import ItemsView, KeysView, Mapping, ValuesView

    from .abc import GuildChannel
    from .channel import PartialGuildChannel
    from .guild import Guild, PartialGuild
    from .member import Member
    from .message import Message
    from .partial_emoji import PartialEmoji
    from .state import ConnectionState
    from .threads import Thread
    from .types.gateway import GatewayRateLimit as GatewayRateLimitPayload
    from .types.member import MemberUpdateEvent
    from .types.raw_models import (
        AuditLogEntryEvent,
        AutoModActionExecutionEvent as AutoModActionExecution,
        BulkMessageDeleteEvent,
        ChannelInfoChannel,
        IntegrationDeleteEvent,
        MemberRemoveEvent,
        MessageDeleteEvent,
        MessagePollVoteEvent,
        MessageUpdateEvent,
        ReactionActionEvent,
        ReactionClearEmojiEvent,
        ReactionClearEvent,
        ScheduledEventSubscription,
        SoundboardSoundDeleteEvent,
        ThreadDeleteEvent,
        ThreadMembersUpdateEvent,
        ThreadUpdateEvent,
        TypingEvent,
        VoiceChannelStartTimeUpdateEvent,
        VoiceChannelStatusUpdateEvent,
    )
    from .types.voice import (
        VoiceServerUpdate as VoiceServerUpdateEvent,
        VoiceState as VoiceStateEvent,
    )
    from .user import User


__all__ = (
    "AutoModActionExecutionEvent",
    "ChannelInfo",
    "GatewayRateLimit",
    "RawAuditLogEntryEvent",
    "RawBulkMessageDeleteEvent",
    "RawIntegrationDeleteEvent",
    "RawMemberRemoveEvent",
    "RawMemberUpdateEvent",
    "RawMessageDeleteEvent",
    "RawMessagePollVoteEvent",
    "RawMessageUpdateEvent",
    "RawReactionActionEvent",
    "RawReactionClearEmojiEvent",
    "RawReactionClearEvent",
    "RawScheduledEventSubscription",
    "RawSoundboardSoundDeleteEvent",
    "RawThreadDeleteEvent",
    "RawThreadMembersUpdateEvent",
    "RawThreadUpdateEvent",
    "RawTypingEvent",
    "RawVoiceChannelStartTimeUpdateEvent",
    "RawVoiceChannelStatusUpdateEvent",
    "RawVoiceServerUpdateEvent",
    "RawVoiceStateUpdateEvent",
)


class _RawReprMixin:
    __slots__: tuple[str, ...]

    def __repr__(self) -> str:
        value = " ".join(
            f"{attr}={getattr(self, attr)!r}"
            for attr in self.__slots__
            if not attr.startswith("_")
        )
        return f"<{self.__class__.__name__} {value}>"


class RawMessageDeleteEvent(_RawReprMixin):
    """Represents the event payload for a :func:`on_raw_message_delete` event.

    Attributes
    ----------
    channel_id: :class:`int`
        The channel ID where the deletion took place.
    guild_id: Optional[:class:`int`]
        The guild ID where the deletion took place, if applicable.
    message_id: :class:`int`
        The message ID that got deleted.
    cached_message: Optional[:class:`Message`]
        The cached message, if found in the internal message cache.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#message-delete>`__.

        .. versionadded:: 2.5
    """

    __slots__ = ("cached_message", "channel_id", "data", "guild_id", "message_id")

    def __init__(self, data: MessageDeleteEvent) -> None:
        self.message_id: int = int(data["id"])
        self.channel_id: int = int(data["channel_id"])
        self.cached_message: Message | None = None
        self.guild_id: int | None = utils._get_as_snowflake(data, "guild_id")
        self.data: MessageDeleteEvent = data


class RawBulkMessageDeleteEvent(_RawReprMixin):
    """Represents the event payload for a :func:`on_raw_bulk_message_delete` event.

    Attributes
    ----------
    message_ids: Set[:class:`int`]
        A :class:`set` of the message IDs that were deleted.
    channel_id: :class:`int`
        The channel ID where the message got deleted.
    guild_id: Optional[:class:`int`]
        The guild ID where the message got deleted, if applicable.
    cached_messages: List[:class:`Message`]
        The cached messages, if found in the internal message cache.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#message-delete-bulk>`__.

        .. versionadded:: 2.5
    """

    __slots__ = ("cached_messages", "channel_id", "data", "guild_id", "message_ids")

    def __init__(self, data: BulkMessageDeleteEvent) -> None:
        self.message_ids: set[int] = {int(x) for x in data.get("ids", [])}
        self.channel_id: int = int(data["channel_id"])
        self.cached_messages: list[Message] = []
        self.guild_id: int | None = utils._get_as_snowflake(data, "guild_id")
        self.data: BulkMessageDeleteEvent = data


class RawMessageUpdateEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_message_edit` event.

    Attributes
    ----------
    message_id: :class:`int`
        The message ID that got updated.
    channel_id: :class:`int`
        The channel ID where the update took place.

        .. versionadded:: 1.3
    guild_id: Optional[:class:`int`]
        The guild ID where the message got updated, if applicable.

        .. versionadded:: 1.7

    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events#message-update>`__
    cached_message: Optional[:class:`Message`]
        The cached message, if found in the internal message cache. Represents the message before
        it is modified by the data in :attr:`RawMessageUpdateEvent.data`.
    new_message: :class:`Message`
        The new message object. Represents the message after it is modified by the data in
        :attr:`RawMessageUpdateEvent.data`.

        .. versionadded:: 2.7
    """

    __slots__ = ("cached_message", "channel_id", "data", "guild_id", "message_id")

    def __init__(self, data: MessageUpdateEvent, new_message: Message) -> None:
        self.message_id: int = int(data["id"])
        self.channel_id: int = int(data["channel_id"])
        self.data: MessageUpdateEvent = data
        self.cached_message: Message | None = None
        self.new_message: Message = new_message
        self.guild_id: int | None = utils._get_as_snowflake(data, "guild_id")


class RawReactionActionEvent(_RawReprMixin, AliasMixin):
    """Represents the payload for a :func:`on_raw_reaction_add` event or a :func:`on_raw_reaction_remove` event.

    Attributes
    ----------
    message_id: :class:`int`
        The message ID that got or lost a reaction.
    user_id: :class:`int`
        The user ID who added the reaction or whose reaction was removed.
    channel_id: :class:`int`
        The channel ID where the reaction got added or removed.
    guild_id: Optional[:class:`int`]
        The guild ID where the reaction got added or removed, if applicable.
    emoji: :class:`PartialEmoji`
        The custom or unicode emoji being used.
    member: Optional[:class:`Member`]
        The member who added the reaction. Only available if the reaction occurs within a guild.

        .. versionadded:: 1.3

    event_type: :class:`str`
        The event type that triggered this action. Can be
        ``REACTION_ADD`` for reaction addition or
        ``REACTION_REMOVE`` for reaction removal.

        .. versionadded:: 1.3
    message_author_id: Optional[:class:`int`]
        The ID of the user who authored the message that was reacted to. Only
        available if `event_type` is `REACTION_ADD`.

        .. versionadded:: 3.0
    burst: :class:`bool`
        Whether this reaction is a burst (super) reaction.
    burst_colours: Optional[:class:`list`]
        A list of hex codes this reaction can be. Only available if `event_type` is `REACTION_ADD`
        and this emoji has super reactions available.
    type: :class:`ReactionType`
        The type of reaction added.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#message-reaction-add>`__.

        .. versionadded:: 2.5
    """

    __slots__ = (
        "burst",
        "burst_colours",
        "channel_id",
        "data",
        "emoji",
        "event_type",
        "guild_id",
        "member",
        "message_author_id",
        "message_id",
        "type",
        "user_id",
    )

    def __init__(
        self, data: ReactionActionEvent, emoji: PartialEmoji, event_type: str
    ) -> None:
        self.message_id: int = int(data["message_id"])
        self.channel_id: int = int(data["channel_id"])
        self.user_id: int = int(data["user_id"])
        self.emoji: PartialEmoji = emoji
        self.event_type: str = event_type
        self.member: Member | None = None
        self.message_author_id: int | None = utils._get_as_snowflake(
            data, "message_author_id"
        )
        self.burst: bool = data.get("burst")
        self.burst_colours: list[str] = data.get("burst_colors", [])
        self.type: ReactionType = try_enum(ReactionType, data.get("type", 0))
        self.guild_id: int | None = utils._get_as_snowflake(data, "guild_id")
        self.data: ReactionActionEvent = data

    if TYPE_CHECKING:
        burst_colors: list[str]


class RawReactionClearEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_reaction_clear` event.

    Attributes
    ----------
    message_id: :class:`int`
        The message ID that got its reactions cleared.
    channel_id: :class:`int`
        The channel ID where the reactions got cleared.
    guild_id: Optional[:class:`int`]
        The guild ID where the reactions got cleared.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#message-reaction-remove-all>`__.

        .. versionadded:: 2.5
    """

    __slots__ = ("channel_id", "data", "guild_id", "message_id")

    def __init__(self, data: ReactionClearEvent) -> None:
        self.message_id: int = int(data["message_id"])
        self.channel_id: int = int(data["channel_id"])
        self.guild_id: int | None = utils._get_as_snowflake(data, "guild_id")
        self.data: ReactionClearEvent = data


class RawReactionClearEmojiEvent(_RawReprMixin, AliasMixin):
    """Represents the payload for a :func:`on_raw_reaction_clear_emoji` event.

    .. versionadded:: 1.3

    Attributes
    ----------
    message_id: :class:`int`
        The message ID that got its reactions cleared.
    channel_id: :class:`int`
        The channel ID where the reactions got cleared.
    guild_id: Optional[:class:`int`]
        The guild ID where the reactions got cleared.
    emoji: :class:`PartialEmoji`
        The custom or unicode emoji being removed.
    burst: :class:`bool`
        Whether this reaction was a burst (super) reaction. Discord does not send
        this field for this event, it is ``False`` unless the payload has it.
    burst_colours: :class:`list`
        The available HEX codes of the removed super reaction. Discord does not send
        this field for this event, it is empty unless the payload has it.
    type: :class:`ReactionType`
        The type of reaction removed. Discord does not send this field for this
        event, it is :attr:`ReactionType.normal` unless the payload has it.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#message-reaction-remove-emoji>`__.

        .. versionadded:: 2.5
    """

    __slots__ = (
        "burst",
        "burst_colours",
        "channel_id",
        "data",
        "emoji",
        "guild_id",
        "message_id",
        "type",
    )

    def __init__(self, data: ReactionClearEmojiEvent, emoji: PartialEmoji) -> None:
        extra: Mapping[str, Any] = data
        self.emoji: PartialEmoji = emoji
        self.message_id: int = int(data["message_id"])
        self.channel_id: int = int(data["channel_id"])
        self.burst: bool = bool(extra.get("burst", False))
        self.burst_colours: list[str] = list(extra.get("burst_colors") or [])
        self.type: ReactionType = try_enum(ReactionType, extra.get("type", 0))
        self.guild_id: int | None = utils._get_as_snowflake(data, "guild_id")
        self.data: ReactionClearEmojiEvent = data

    if TYPE_CHECKING:
        burst_colors: list[str]


class RawIntegrationDeleteEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_integration_delete` event.

    .. versionadded:: 2.0

    Attributes
    ----------
    integration_id: :class:`int`
        The ID of the integration that got deleted.
    application_id: Optional[:class:`int`]
        The ID of the bot/OAuth2 application for this deleted integration.
    guild_id: :class:`int`
        The guild ID where the integration got deleted.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#integration-delete>`__.

        .. versionadded:: 2.5
    """

    __slots__ = ("application_id", "data", "guild_id", "integration_id")

    def __init__(self, data: IntegrationDeleteEvent) -> None:
        self.integration_id: int = int(data["id"])
        self.guild_id: int = int(data["guild_id"])
        self.application_id: int | None = utils._get_as_snowflake(
            data, "application_id"
        )
        self.data: IntegrationDeleteEvent = data


class RawThreadUpdateEvent(_RawReprMixin):
    """Represents the payload for an :func:`on_raw_thread_update` event.

    .. versionadded:: 2.4

    Attributes
    ----------
    thread_id: :class:`int`
        The ID of the updated thread.
    thread_type: :class:`discord.ChannelType`
        The channel type of the updated thread.
    guild_id: :class:`int`
        The ID of the guild the thread belongs to.
    parent_id: :class:`int`
        The ID of the channel the thread belongs to.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#thread-update>`__.
    thread: :class:`discord.Thread` | None
        The thread, if it could be found in the internal cache.
    """

    __slots__ = ("data", "guild_id", "parent_id", "thread", "thread_id", "thread_type")

    def __init__(self, data: ThreadUpdateEvent) -> None:
        self.thread_id: int = int(data["id"])
        self.thread_type: ChannelType = try_enum(ChannelType, data["type"])
        self.guild_id: int = int(data["guild_id"])
        self.parent_id: int = int(data["parent_id"])
        self.data: ThreadUpdateEvent = data
        self.thread: Thread | None = None


class RawThreadDeleteEvent(_RawReprMixin):
    """Represents the payload for :func:`on_raw_thread_delete` event.

    .. versionadded:: 2.0

    Attributes
    ----------
    thread_id: :class:`int`
        The ID of the thread that was deleted.
    thread_type: :class:`discord.ChannelType`
        The channel type of the deleted thread.
    guild_id: :class:`int`
        The ID of the guild the deleted thread belonged to.
    parent_id: :class:`int`
        The ID of the channel the thread belonged to.
    thread: Optional[:class:`discord.Thread`]
        The thread that was deleted. This may be ``None`` if deleted thread is not found in internal cache.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#thread-delete>`__.

        .. versionadded:: 2.5
    """

    __slots__ = ("data", "guild_id", "parent_id", "thread", "thread_id", "thread_type")

    def __init__(self, data: ThreadDeleteEvent) -> None:
        self.thread_id: int = int(data["id"])
        self.thread_type: ChannelType = try_enum(ChannelType, int(data["type"]))
        self.guild_id: int = int(data["guild_id"])
        self.parent_id: int = int(data["parent_id"])
        self.thread: Thread | None = None
        self.data: ThreadDeleteEvent = data


class RawVoiceChannelStatusUpdateEvent(_RawReprMixin):
    """Represents the payload for an :func:`on_raw_voice_channel_status_update` event.

    .. versionadded:: 2.5

    Attributes
    ----------
    id: :class:`int`
        The channel ID where the voice channel status update originated from.
    guild_id: :class:`int`
        The guild ID where the voice channel status update originated from.
    status: Optional[:class:`str`]
        The new voice channel status.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#voice-channel-status-update>`__.
    """

    __slots__ = ("data", "guild_id", "id", "status")

    def __init__(self, data: VoiceChannelStatusUpdateEvent) -> None:
        self.id: int = int(data["id"])
        self.guild_id: int = int(data["guild_id"])
        self.status: str | None = data.get("status")
        self.data: VoiceChannelStatusUpdateEvent = data


class RawVoiceChannelStartTimeUpdateEvent(_RawReprMixin):
    """Represents the payload for an :func:`on_raw_voice_channel_start_time_update` event.

    .. versionadded:: 3.0

    Attributes
    ----------
    id: :class:`int`
        The channel ID where the voice channel start time update originated from.
    guild_id: :class:`int`
        The guild ID where the voice channel start time update originated from.
    voice_start_time: Optional[:class:`datetime.datetime`]
        The new voice channel start time, ``None`` if the voice session ended.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events#voice-channel-start-time-update>`__.
    """

    __slots__ = ("data", "guild_id", "id", "voice_start_time")

    def __init__(self, data: VoiceChannelStartTimeUpdateEvent) -> None:
        self.id: int = int(data["id"])
        self.guild_id: int = int(data["guild_id"])
        start_time = data.get("voice_start_time")
        self.voice_start_time: dt.datetime | None = (
            dt.datetime.fromtimestamp(start_time, tz=dt.timezone.utc)
            if start_time
            else None
        )
        self.data: VoiceChannelStartTimeUpdateEvent = data


class RawTypingEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_typing` event.

    .. versionadded:: 2.0

    Attributes
    ----------
    channel_id: :class:`int`
        The channel ID where the typing originated from.
    user_id: :class:`int`
        The ID of the user that started typing.
    when: :class:`datetime.datetime`
        When the typing started as an aware datetime in UTC.
    guild_id: Optional[:class:`int`]
        The guild ID where the typing originated from, if applicable.
    member: Optional[:class:`Member`]
        The member who started typing. Only available if the member started typing in a guild.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#typing-start>`__.

        .. versionadded:: 2.5
    """

    __slots__ = ("channel_id", "data", "guild_id", "member", "user_id", "when")

    def __init__(self, data: TypingEvent) -> None:
        self.channel_id: int = int(data["channel_id"])
        self.user_id: int = int(data["user_id"])
        self.when: dt.datetime = dt.datetime.fromtimestamp(
            data.get("timestamp"), tz=dt.timezone.utc
        )
        self.member: Member | None = None
        self.guild_id: int | None = utils._get_as_snowflake(data, "guild_id")
        self.data: TypingEvent = data


class RawMemberRemoveEvent(_RawReprMixin):
    """Represents the payload for an :func:`on_raw_member_remove` event.

    .. versionadded:: 2.4

    Attributes
    ----------
    user: Union[:class:`discord.User`, :class:`discord.Member`]
        The user that left the guild. This is the cached :class:`discord.Member`
        when the member was cached.
    guild_id: :class:`int`
        The ID of the guild the user left.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#guild-member-remove>`__.

        .. versionadded:: 2.5
    """

    __slots__ = ("data", "guild_id", "user")

    def __init__(self, data: MemberRemoveEvent, user: User) -> None:
        self.user: User | Member = user
        self.guild_id: int = int(data["guild_id"])
        self.data: MemberRemoveEvent = data


class RawScheduledEventSubscription(_RawReprMixin):
    """Represents the payload for a :func:`raw_scheduled_event_user_add` or :func:`raw_scheduled_event_user_remove` event.

    .. versionadded:: 2.0

    Attributes
    ----------
    event_id: :class:`int`
        The event ID where the typing originated from.
    user_id: :class:`int`
        The ID of the user that subscribed/unsubscribed.
    guild: Optional[:class:`Guild`]
        The guild where the subscription/unsubscription happened.
    event_type: :class:`str`
        Can be either ``USER_ADD`` or ``USER_REMOVE`` depending on
        the event called.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#guild-scheduled-event-user-add>`__.

        .. versionadded:: 2.5
    """

    __slots__ = ("data", "event_id", "event_type", "guild", "user_id")

    def __init__(self, data: ScheduledEventSubscription, event_type: str) -> None:
        self.event_id: int = int(data["guild_scheduled_event_id"])
        self.user_id: int = int(data["user_id"])
        self.guild: Guild | None = None
        self.event_type: str = event_type
        self.data: ScheduledEventSubscription = data


class AutoModActionExecutionEvent:
    """Represents the payload for an :func:`on_auto_moderation_action_execution`

    .. versionadded:: 2.0

    Attributes
    ----------
    action: :class:`AutoModAction`
        The action that was executed.
    rule_id: :class:`int`
        The ID of the rule that the action belongs to.
    rule_trigger_type: :class:`AutoModTriggerType`
        The category of trigger the rule belongs to.

        .. versionadded:: 2.4
    guild_id: :class:`int`
        The ID of the guild that the action was executed in.
    guild: Optional[:class:`Guild`]
        The guild that the action was executed in, if cached.
    user_id: :class:`int`
        The ID of the user that triggered the action.
    member: Optional[:class:`Member`]
        The member that triggered the action, if cached.
    channel_id: Optional[:class:`int`]
        The ID of the channel in which the member's content was posted.
    channel: Optional[Union[:class:`abc.GuildChannel`, :class:`Thread`]]
        The channel in which the member's content was posted, if cached.
    message_id: Optional[:class:`int`]
        The ID of the message that triggered the action. This is only available if the
        message was not blocked.
    message: Optional[:class:`Message`]
        The message that triggered the action, if cached.
    alert_system_message_id: Optional[:class:`int`]
        The ID of the system auto moderation message that was posted as a result
        of the action.
    alert_system_message: Optional[:class:`Message`]
        The system auto moderation message that was posted as a result of the action,
        if cached.
    content: :class:`str`
        The content of the message that triggered the action.
    matched_keyword: Optional[:class:`str`]
        The word or phrase configured that was matched in the content.
    matched_content: :class:`str`
        The substring in the content that was matched.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#auto-moderation-action-execution>`__.

        .. versionadded:: 2.5
    """

    __slots__ = (
        "action",
        "alert_system_message",
        "alert_system_message_id",
        "channel",
        "channel_id",
        "content",
        "data",
        "guild",
        "guild_id",
        "matched_content",
        "matched_keyword",
        "member",
        "message",
        "message_id",
        "rule_id",
        "rule_trigger_type",
        "user_id",
    )

    def __init__(self, state: ConnectionState, data: AutoModActionExecution) -> None:
        self.action: AutoModAction = AutoModAction.from_dict(data["action"])
        self.rule_id: int = int(data["rule_id"])
        self.rule_trigger_type: AutoModTriggerType = try_enum(
            AutoModTriggerType, int(data["rule_trigger_type"])
        )
        self.guild_id: int = int(data["guild_id"])
        self.guild: Guild | None = None
        self.user_id: int = int(data["user_id"])
        self.content: str | None = data.get("content", None)
        self.matched_keyword: str | None = data.get("matched_keyword")
        self.matched_content: str | None = data.get("matched_content", None)
        self.channel_id: int | None = utils._get_as_snowflake(data, "channel_id")
        self.channel: GuildChannel | Thread | None = None
        self.member: Member | None = None
        self.message_id: int | None = utils._get_as_snowflake(data, "message_id")
        self.message: Message | None = None
        self.alert_system_message_id: int | None = utils._get_as_snowflake(
            data, "alert_system_message_id"
        )
        self.alert_system_message: Message | None = None
        self.data: AutoModActionExecution = data

    def __repr__(self) -> str:
        return (
            f"<AutoModActionExecutionEvent action={self.action!r} "
            f"rule_id={self.rule_id!r} guild_id={self.guild_id!r} "
            f"user_id={self.user_id!r}>"
        )


class RawThreadMembersUpdateEvent(_RawReprMixin):
    """Represents the payload for an :func:`on_raw_thread_member_remove` event.

    .. versionadded:: 2.4

    Attributes
    ----------
    thread_id: :class:`int`
        The ID of the thread that was updated.
    guild_id: :class:`int`
        The ID of the guild the thread is in.
    member_count: :class:`int`
        The approximate number of members in the thread. Maximum of 50.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#thread-members-update>`__.

        .. versionadded:: 2.5
    """

    __slots__ = ("data", "guild_id", "member_count", "thread_id")

    def __init__(self, data: ThreadMembersUpdateEvent) -> None:
        self.thread_id = int(data["id"])
        self.guild_id = int(data["guild_id"])
        self.member_count = int(data["member_count"])
        self.data: ThreadMembersUpdateEvent = data


class RawAuditLogEntryEvent(_RawReprMixin):
    """Represents the payload for an :func:`on_raw_audit_log_entry` event.

    .. versionadded:: 2.5

    Attributes
    ----------
    action_type: :class:`AuditLogAction`
        The action that was done.
    id: :class:`int`
        The entry ID.
    guild_id: :class:`int`
        The ID of the guild this action came from.
    user_id: Optional[:class:`int`]
        The ID of the user who initiated this action.
    target_id: Optional[:class:`int`]
        The ID of the target that got changed.
    reason: Optional[:class:`str`]
        The reason this action was done.
    changes: Optional[:class:`list`]
        The changes that were made to the target.
    extra: Any
        Extra information that this entry has that might be useful.
        For most actions, this is ``None``. However, in some cases it
        contains extra information. See :class:`AuditLogAction` for
        which actions have this field filled out.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#guild-audit-log-entry-create>`__.
    guild: :class:`Guild`
        The guild this action came from. Set once the event is dispatched.
    """

    guild: Guild

    __slots__ = (
        "action_type",
        "changes",
        "data",
        "extra",
        "guild_id",
        "id",
        "reason",
        "target_id",
        "user_id",
    )

    def __init__(self, data: AuditLogEntryEvent) -> None:
        self.id = int(data["id"])
        user_id = data.get("user_id")
        self.user_id: int | None = int(user_id) if user_id else None
        self.guild_id = int(data["guild_id"])
        self.target_id = data.get("target_id")
        if self.target_id:
            self.target_id = int(self.target_id)
        self.action_type = try_enum(AuditLogAction, int(data["action_type"]))
        self.reason = data.get("reason")
        self.extra = data.get("options")
        self.changes = data.get("changes")
        self.data: AuditLogEntryEvent = data


class RawMessagePollVoteEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_message_poll_vote` event.

    .. versionadded:: 2.6

    Attributes
    ----------
    user_id: :class:`int`:
        The user that added or removed their vote
    message_id: :class:`int`
        The message ID of the poll that received the vote.
    channel_id: :class:`int`
        The channel ID where the vote was updated.
    guild_id: Optional[:class:`int`]
        The guild ID where the vote was updated, if applicable.
    answer_id: :class:`int`
        The answer ID of the vote that was updated.
    added: :class:`bool`
        Whether this vote was added or removed.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events#message-poll-vote-add>`__
    """

    __slots__ = (
        "added",
        "answer_id",
        "channel_id",
        "data",
        "guild_id",
        "message_id",
        "user_id",
    )

    def __init__(self, data: MessagePollVoteEvent, added: bool) -> None:
        self.user_id: int = int(data["user_id"])
        self.channel_id: int = int(data["channel_id"])
        self.message_id: int = int(data["message_id"])
        self.answer_id: int = int(data["answer_id"])
        self.data: MessagePollVoteEvent = data
        self.added: bool = added
        self.guild_id: int | None = utils._get_as_snowflake(data, "guild_id")


# this is for backwards compatibility because VoiceProtocol.on_voice_..._update
# passed the raw payload instead of a raw object. Emit deprecation warning.
class _PayloadLike(_RawReprMixin):
    _raw_data: Mapping[str, Any]

    @deprecated(
        "__getitem__ is deprecated since version 2.7 and will be removed in version 3.0. Consider using the attributes instead.",
    )
    def __getitem__(self, key: str) -> Any:
        return self._raw_data[key]

    @deprecated(
        "get is deprecated since version 2.7 and will be removed in version 3.0. Consider using the attributes instead.",
    )
    def get(self, key: str, default: Any = None) -> Any:
        """Gets an item from this raw event, and returns its value or ``default``.

        .. deprecated:: 2.7
            Use the attributes instead.
        """
        return self._raw_data.get(key, default)

    @deprecated(
        "items is deprecated since version 2.7 and will be removed in version 3.0. Consider using the attributes instead.",
    )
    def items(self) -> ItemsView[str, Any]:
        """Returns the (key, value) pairs of this raw event.

        .. deprecated:: 2.7
            Use the attributes instead.
        """
        return self._raw_data.items()

    @deprecated(
        "values is deprecated since version 2.7 and will be removed in version 3.0. Consider using the attributes instead.",
    )
    def values(self) -> ValuesView[Any]:
        """Returns the values of this raw event.

        .. deprecated:: 2.7
            Use the attributes instead.
        """
        return self._raw_data.values()

    @deprecated(
        "keys is deprecated since version 2.7 and will be removed in version 3.0. Consider using the attributes instead.",
    )
    def keys(self) -> KeysView[str]:
        """Returns the keys of this raw event.

        .. deprecated:: 2.7
            Use the attributes instead.
        """
        return self._raw_data.keys()


class RawVoiceStateUpdateEvent(_PayloadLike):
    """Represents the payload for a :meth:`VoiceProtocol.on_voice_state_update` event.

    .. versionadded:: 2.7

    Attributes
    ----------
    deaf: :class:`bool`
        Whether the user is guild deafened.
    mute: :class:`bool`
        Whether the user is guild muted.
    self_mute: :class:`bool`
        Whether the user has muted themselves by their own accord.
    self_deaf: :class:`bool`
        Whether the user has deafened themselves by their own accord.
    self_stream: :class:`bool`
        Whether the user is currently streaming via the 'Go Live' feature.
    self_video: :class:`bool`
        Whether the user is currently broadcasting video.
    suppress: :class:`bool`
        Whether the user is suppressed from speaking in a stage channel.
    requested_to_speak_at: Optional[:class:`datetime.datetime`]
        An aware datetime object that specifies when a member has requested to speak
        in a stage channel. It will be ``None`` if they are not requesting to speak
        anymore or have been accepted to.
    afk: :class:`bool`
        Whether the user is connected on the guild's AFK channel.
    channel: Optional[Union[:class:`VoiceChannel`, :class:`StageChannel`]]
        The voice channel that the user is currently connected to. ``None`` if the user
        is not currently in a voice channel.

        There are certain scenarios in which this is impossible to be ``None``.
    session_id: :class:`str`
        The voice connection session ID.
    guild_id: Optional[:class:`int`]
        The guild ID the user channel is from.
    channel_id: Optional[:class:`int`]
        The channel ID the user is connected to. Or ``None`` if not connected to any.
    """

    __slots__ = (
        "_raw_data",
        "_state",
        "afk",
        "channel_id",
        "deaf",
        "guild_id",
        "mute",
        "requested_to_speak_at",
        "self_deaf",
        "self_mute",
        "self_stream",
        "self_video",
        "session_id",
        "suppress",
    )

    def __init__(self, *, data: VoiceStateEvent, state: ConnectionState) -> None:
        self.session_id: str = data["session_id"]
        self._state: ConnectionState = state

        self.self_mute: bool = data.get("self_mute", False)
        self.self_deaf: bool = data.get("self_deaf", False)
        self.self_stream: bool = data.get("self_stream", False)
        self.self_video: bool = data.get("self_video", False)
        self.mute: bool = data.get("mute", False)
        self.deaf: bool = data.get("deaf", False)
        self.suppress: bool = data.get("suppress", False)
        self.requested_to_speak_at: dt.datetime | None = utils.parse_time(
            data.get("request_to_speak_timestamp")
        )
        self.guild_id: int | None = utils._get_as_snowflake(data, "guild_id")
        self.channel_id: int | None = utils._get_as_snowflake(data, "channel_id")
        self.afk: bool = False
        self._raw_data = data

    @property
    def guild(self) -> Guild | PartialGuild | None:
        """Returns the guild the user is connected to, or ``None``.

        This is the cached guild when it is available in an in-process cache,
        otherwise a :class:`PartialGuild` handle.
        Use :meth:`get_guild` to look the cached guild up with any cache backend.
        """
        from .guild import PartialGuild

        if self.guild_id is None:
            return None
        return cached_guild(self._state, self.guild_id) or PartialGuild(
            state=self._state, id=self.guild_id
        )

    @property
    def channel(self) -> GuildChannel | Thread | PartialGuildChannel | None:
        """Returns the channel the user is connected to, or ``None``.

        This is the cached channel when it is available in an in-process cache,
        otherwise a :class:`PartialGuildChannel` handle.
        Use :meth:`get_channel` to look the cached channel up with any cache backend.
        """
        from .channel import PartialGuildChannel

        if self.guild_id is None or self.channel_id is None:
            return None
        return cached_guild_channel(
            self._state, self.guild_id, self.channel_id
        ) or PartialGuildChannel(
            state=self._state, id=self.channel_id, guild_id=self.guild_id
        )

    async def get_guild(self) -> Guild | None:
        """|coro|

        Returns the cached guild the user is connected to, or ``None``.
        """
        return await self._state._get_guild(self.guild_id)

    async def get_channel(self) -> GuildChannel | None:
        """|coro|

        Returns the cached channel the user is connected to, or ``None``.
        """
        return cast(
            "GuildChannel | None", await self._state.get_channel(self.channel_id)
        )


class RawVoiceServerUpdateEvent(_PayloadLike):
    """Represents the payload for a :meth:`VoiceProtocol.on_voice_server_update` event.

    .. versionadded:: 2.7

    Attributes
    ----------
    token: :class:`str`
        The voice connection token. This should not be shared.
    guild_id: :class:`int`
        The guild ID this token is part from.
    endpoint: Optional[:class:`str`]
        The voice server host to connect to.
    """

    __slots__ = (
        "_raw_data",
        "_state",
        "endpoint",
        "guild_id",
        "token",
    )

    def __init__(self, *, data: VoiceServerUpdateEvent, state: ConnectionState) -> None:
        self._state: ConnectionState = state
        self.guild_id: int = int(data["guild_id"])
        self.token: str = data["token"]
        self.endpoint: str | None = data["endpoint"]
        self._raw_data = data

    @property
    def guild(self) -> Guild | PartialGuild:
        """Returns the guild this server update is from.

        This is the cached guild when it is available in an in-process cache,
        otherwise a :class:`PartialGuild` handle.
        Use :meth:`get_guild` to look the cached guild up with any cache backend.
        """
        from .guild import PartialGuild

        return cached_guild(self._state, self.guild_id) or PartialGuild(
            state=self._state, id=self.guild_id
        )

    async def get_guild(self) -> Guild | None:
        """|coro|

        Returns the cached guild this server update is from.
        """
        return await self._state._get_guild(self.guild_id)


class RawSoundboardSoundDeleteEvent(_RawReprMixin):
    """Represents the payload for an :func:`on_raw_soundboard_sound_delete`.

    .. versionadded 2.7
    """

    __slots__ = ("data", "guild_id", "sound_id")

    def __init__(self, data: SoundboardSoundDeleteEvent) -> None:
        self.sound_id: int = int(data["sound_id"])
        self.guild_id: int = int(data["guild_id"])
        self.data: SoundboardSoundDeleteEvent = data


class RawMemberUpdateEvent(_RawReprMixin):
    """Represents the payload for a :func:`on_raw_member_update` event.

    .. versionadded:: 2.8

    Attributes
    ----------
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events-events#guild-member-update>`_
    cached_member: Optional[:class:`Member`]
        The cached member, if found in the internal member cache.
    member: :class:`Member`
        The new member object after the update.
    """

    __slots__ = ("cached_member", "data", "guild_id", "member", "user_id")

    def __init__(self, data: MemberUpdateEvent, member: Member) -> None:
        self.guild_id: int = int(data["guild_id"])
        self.user_id: int = int(data["user"]["id"])
        self.data: MemberUpdateEvent = data
        self.cached_member: Member | None = None
        self.member: Member = member


class GatewayRateLimit(_RawReprMixin):
    """Represents the payload for a :func:`on_gateway_rate_limited` event.

    .. versionadded:: 3.0

    Attributes
    ----------
    opcode: :class:`int`
        The gateway opcode that was rate limited.
    retry_after: :class:`float`
        The number of seconds to wait before sending the request again.
    meta: :class:`dict`
        The metadata of the rate limited request. For opcode ``8`` (Request Guild
        Members) it holds ``guild_id`` and optionally ``nonce``.
    guild_id: Optional[:class:`int`]
        The guild the rate limited request was about, if the metadata has one.
    nonce: Optional[:class:`str`]
        The nonce of the rate limited request, if the metadata has one.
    data: :class:`dict`
        The raw data sent by the `gateway <https://docs.discord.com/developers/events/gateway-events#rate-limited>`_
    """

    __slots__ = ("data", "guild_id", "meta", "nonce", "opcode", "retry_after")

    def __init__(self, data: GatewayRateLimitPayload) -> None:
        self.opcode: int = int(data["opcode"])
        self.retry_after: float = float(data["retry_after"])
        self.meta: dict[str, Any] = data.get("meta") or {}
        self.guild_id: int | None = utils._get_as_snowflake(self.meta, "guild_id")
        self.nonce: str | None = self.meta.get("nonce")
        self.data: GatewayRateLimitPayload = data


class ChannelInfo(_RawReprMixin):
    """Represents the ephemeral data of a channel sent by the gateway in response to a request for channel info.

    .. versionadded:: 3.0

    Attributes
    ----------
    id: :class:`int`
        The ID of the channel this info belongs to.
    status: Optional[:class:`str`]
        The voice channel status.
    voice_start_time: Optional[:class:`int`]
        The Unix timestamp (in seconds) of when the voice session started.
    """

    __slots__ = ("id", "status", "voice_start_time")

    def __init__(self, data: ChannelInfoChannel) -> None:
        self.id: int = int(data["id"])
        self.status: str | None = data.get("status")
        self.voice_start_time: int | None = data.get("voice_start_time")
