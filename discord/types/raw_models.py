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

from typing import Any

from typing_extensions import NotRequired, TypedDict

from .activity import PartialPresenceUpdate
from .automod import AutoModAction, AutoModTriggerType
from .emoji import Emoji, PartialEmoji
from .integration import (
    IntegrationAccount,
    IntegrationApplication,
    IntegrationExpireBehavior,
)
from .member import Member, MemberWithUser
from .role import Role
from .snowflake import Snowflake
from .soundboard import SoundboardSound
from .sticker import GuildSticker
from .threads import Thread, ThreadMember
from .user import User


class _MessageEventOptional(TypedDict, total=False):
    guild_id: Snowflake


class MessageDeleteEvent(_MessageEventOptional):
    id: Snowflake
    channel_id: Snowflake


class BulkMessageDeleteEvent(_MessageEventOptional):
    ids: list[Snowflake]
    channel_id: Snowflake


class MessageUpdateEvent(_MessageEventOptional):
    id: Snowflake
    channel_id: Snowflake


class _ReactionEventOptional(TypedDict, total=False):
    guild_id: Snowflake


class ReactionActionEvent(_ReactionEventOptional):
    member: NotRequired[Member]
    me: NotRequired[bool]
    user_id: Snowflake
    channel_id: Snowflake
    message_id: Snowflake
    emoji: PartialEmoji
    message_author_id: NotRequired[Snowflake]
    burst: bool
    burst_colors: NotRequired[list[str]]
    type: int


class ReactionClearEvent(_ReactionEventOptional):
    channel_id: Snowflake
    message_id: Snowflake


class ReactionClearEmojiEvent(_ReactionEventOptional):
    channel_id: Snowflake
    message_id: Snowflake
    emoji: PartialEmoji


class IntegrationDeleteEvent(TypedDict):
    application_id: NotRequired[Snowflake]
    id: Snowflake
    guild_id: Snowflake


ThreadUpdateEvent = Thread


class ThreadDeleteEvent(TypedDict):
    id: Snowflake
    guild_id: Snowflake
    parent_id: Snowflake
    type: int


class TypingEvent(TypedDict):
    guild_id: NotRequired[Snowflake]
    member: NotRequired[Member]
    channel_id: Snowflake
    user_id: Snowflake
    timestamp: int


class ScheduledEventSubscription(TypedDict):
    guild_scheduled_event_id: Snowflake
    user_id: Snowflake
    guild_id: Snowflake


class SoundboardSoundDeleteEvent(TypedDict):
    sound_id: Snowflake
    guild_id: Snowflake


class AutoModActionExecutionEvent(TypedDict):
    channel_id: NotRequired[Snowflake]
    message_id: NotRequired[Snowflake]
    alert_system_message_id: NotRequired[Snowflake]
    matched_keyword: str | None
    matched_content: str | None
    guild_id: Snowflake
    action: AutoModAction
    rule_id: Snowflake
    rule_trigger_type: AutoModTriggerType
    user_id: Snowflake
    content: str


class MemberRemoveEvent(TypedDict):
    guild_id: Snowflake
    user: User


class VoiceChannelStatusUpdateEvent(TypedDict):
    id: Snowflake
    guild_id: Snowflake
    status: str | None


class VoiceChannelStartTimeUpdateEvent(TypedDict):
    id: Snowflake
    guild_id: Snowflake
    voice_start_time: NotRequired[int | None]


class ChannelInfoChannel(TypedDict):
    id: Snowflake
    status: NotRequired[str | None]
    voice_start_time: NotRequired[int | None]


class ChannelInfoEvent(TypedDict):
    guild_id: Snowflake
    channels: list[ChannelInfoChannel]


class ThreadMembersUpdateEvent(TypedDict):
    id: Snowflake
    guild_id: Snowflake
    member_count: int
    added_members: NotRequired[list[ThreadMember]]
    removed_member_ids: NotRequired[list[Snowflake]]


class AuditLogEntryEvent(TypedDict):
    id: Snowflake
    user_id: Snowflake | None
    guild_id: Snowflake
    target_id: str | None
    action_type: int
    changes: NotRequired[list[dict[str, Any]]]
    reason: NotRequired[str]
    options: NotRequired[dict[str, Any]]


class MessagePollVoteEvent(TypedDict):
    user_id: Snowflake
    guild_id: NotRequired[Snowflake]
    channel_id: Snowflake
    message_id: Snowflake
    answer_id: int


class ChannelPinsUpdateEvent(TypedDict):
    guild_id: NotRequired[Snowflake]
    channel_id: Snowflake
    last_pin_timestamp: NotRequired[str | None]


class GuildBanEvent(TypedDict):
    guild_id: Snowflake
    user: User


GuildBanAddEvent = GuildBanEvent
GuildBanRemoveEvent = GuildBanEvent


class GuildEmojisUpdateEvent(TypedDict):
    guild_id: Snowflake
    emojis: list[Emoji]


class GuildStickersUpdateEvent(TypedDict):
    guild_id: Snowflake
    stickers: list[GuildSticker]


class GuildIntegrationsUpdateEvent(TypedDict):
    guild_id: Snowflake


class GuildMemberAddEvent(MemberWithUser):
    guild_id: Snowflake


class GuildMembersChunkEvent(TypedDict):
    guild_id: Snowflake
    members: list[MemberWithUser]
    chunk_index: int
    chunk_count: int
    not_found: NotRequired[list[Snowflake]]
    presences: NotRequired[list[PartialPresenceUpdate]]
    nonce: NotRequired[str]


class GuildRoleEvent(TypedDict):
    guild_id: Snowflake
    role: Role


GuildRoleCreateEvent = GuildRoleEvent
GuildRoleUpdateEvent = GuildRoleEvent


class GuildRoleDeleteEvent(TypedDict):
    guild_id: Snowflake
    role_id: Snowflake


class IntegrationEvent(TypedDict):
    guild_id: Snowflake
    id: Snowflake
    name: str
    type: str
    enabled: bool
    syncing: NotRequired[bool]
    role_id: NotRequired[Snowflake]
    enable_emoticons: NotRequired[bool]
    expire_behavior: NotRequired[IntegrationExpireBehavior]
    expire_grace_period: NotRequired[int]
    account: IntegrationAccount
    synced_at: NotRequired[str]
    subscriber_count: NotRequired[int]
    revoked: NotRequired[bool]
    application: NotRequired[IntegrationApplication]
    scopes: NotRequired[list[str]]


IntegrationCreateEvent = IntegrationEvent
IntegrationUpdateEvent = IntegrationEvent


class SoundboardSoundsEvent(TypedDict):
    soundboard_sounds: list[SoundboardSound]
    guild_id: Snowflake


SoundboardSoundsUpdateEvent = SoundboardSoundsEvent


class ThreadListSyncEvent(TypedDict):
    guild_id: Snowflake
    channel_ids: NotRequired[list[Snowflake]]
    threads: list[Thread]
    members: list[ThreadMember]


class ThreadMemberUpdateEvent(TypedDict):
    id: Snowflake
    user_id: Snowflake
    join_timestamp: str
    flags: int
    member: NotRequired[Member]
    guild_id: Snowflake


class WebhooksUpdateEvent(TypedDict):
    guild_id: Snowflake
    channel_id: Snowflake
