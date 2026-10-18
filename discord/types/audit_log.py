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

from typing import Literal

from typing_extensions import NotRequired, TypedDict

from .automod import AutoModRule
from .channel import ChannelType, PermissionOverwrite, VideoQualityMode
from .guild import (
    DefaultMessageNotificationLevel,
    ExplicitContentFilterLevel,
    MFALevel,
    VerificationLevel,
)
from .integration import IntegrationExpireBehavior, PartialIntegration
from .role import Role
from .scheduled_events import ScheduledEvent
from .snowflake import Snowflake
from .threads import Thread
from .user import User
from .webhook import Webhook

AuditLogEvent = Literal[
    1,
    10,
    11,
    12,
    13,
    14,
    15,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
    28,
    30,
    31,
    32,
    40,
    41,
    42,
    50,
    51,
    52,
    60,
    61,
    62,
    72,
    73,
    74,
    75,
    80,
    81,
    82,
    83,
    84,
    85,
    90,
    91,
    92,
    100,
    101,
    102,
    110,
    111,
    112,
    121,
    140,
    141,
    142,
    143,
]


class _AuditLogChangeStr(TypedDict):
    key: Literal[
        "name",
        "description",
        "preferred_locale",
        "vanity_url_code",
        "topic",
        "code",
        "allow",
        "deny",
        "permissions",
        "tags",
        "status",
    ]
    new_value: str
    old_value: str


class _AuditLogChangeAssetHash(TypedDict):
    key: Literal[
        "icon_hash",
        "splash_hash",
        "discovery_splash_hash",
        "banner_hash",
        "avatar_hash",
        "asset",
    ]
    new_value: str
    old_value: str


class _AuditLogChangeSnowflake(TypedDict):
    key: Literal[
        "id",
        "owner_id",
        "afk_channel_id",
        "rules_channel_id",
        "public_updates_channel_id",
        "widget_channel_id",
        "system_channel_id",
        "application_id",
        "channel_id",
        "inviter_id",
        "guild_id",
    ]
    new_value: Snowflake
    old_value: Snowflake


class _AuditLogChangeBool(TypedDict):
    key: Literal[
        "widget_enabled",
        "nsfw",
        "hoist",
        "mentionable",
        "temporary",
        "deaf",
        "mute",
        "nick",
        "enabled_emoticons",
        "rtc_region",
        "available",
        "archived",
        "locked",
    ]
    new_value: bool
    old_value: bool


class _AuditLogChangeInt(TypedDict):
    key: Literal[
        "afk_timeout",
        "prune_delete_days",
        "position",
        "bitrate",
        "rate_limit_per_user",
        "color",
        "max_uses",
        "max_age",
        "user_limit",
        "auto_archive_duration",
        "default_auto_archive_duration",
    ]
    new_value: int
    old_value: int


class _AuditLogChangeListRole(TypedDict):
    key: Literal["$add", "$remove"]
    new_value: list[Role]
    old_value: list[Role]


class _AuditLogChangeMFALevel(TypedDict):
    key: Literal["mfa_level"]
    new_value: MFALevel
    old_value: MFALevel


class _AuditLogChangeVerificationLevel(TypedDict):
    key: Literal["verification_level"]
    new_value: VerificationLevel
    old_value: VerificationLevel


class _AuditLogChangeExplicitContentFilter(TypedDict):
    key: Literal["explicit_content_filter"]
    new_value: ExplicitContentFilterLevel
    old_value: ExplicitContentFilterLevel


class _AuditLogChangeDefaultMessageNotificationLevel(TypedDict):
    key: Literal["default_message_notifications"]
    new_value: DefaultMessageNotificationLevel
    old_value: DefaultMessageNotificationLevel


class _AuditLogChangeChannelType(TypedDict):
    key: Literal["type"]
    new_value: ChannelType
    old_value: ChannelType


class _AuditLogChangeIntegrationExpireBehaviour(TypedDict):
    key: Literal["expire_behavior"]
    new_value: IntegrationExpireBehavior
    old_value: IntegrationExpireBehavior


class _AuditLogChangeVideoQualityMode(TypedDict):
    key: Literal["video_quality_mode"]
    new_value: VideoQualityMode
    old_value: VideoQualityMode


class _AuditLogChangeOverwrites(TypedDict):
    key: Literal["permission_overwrites"]
    new_value: list[PermissionOverwrite]
    old_value: list[PermissionOverwrite]


AuditLogChange = (
    _AuditLogChangeStr
    | _AuditLogChangeAssetHash
    | _AuditLogChangeSnowflake
    | _AuditLogChangeInt
    | _AuditLogChangeBool
    | _AuditLogChangeListRole
    | _AuditLogChangeMFALevel
    | _AuditLogChangeVerificationLevel
    | _AuditLogChangeExplicitContentFilter
    | _AuditLogChangeDefaultMessageNotificationLevel
    | _AuditLogChangeChannelType
    | _AuditLogChangeIntegrationExpireBehaviour
    | _AuditLogChangeVideoQualityMode
    | _AuditLogChangeOverwrites
)


class AuditEntryInfo(TypedDict):
    delete_member_days: str
    members_removed: str
    channel_id: Snowflake
    message_id: Snowflake
    count: str
    id: Snowflake
    type: Literal["0", "1"]
    role_name: str
    application_id: Snowflake
    auto_moderation_rule_name: str
    auto_moderation_rule_trigger_type: str
    # TODO: add integration_type
    status: str


class AuditLogEntry(TypedDict):
    changes: NotRequired[list[AuditLogChange]]
    options: NotRequired[AuditEntryInfo]
    reason: NotRequired[str]
    target_id: str | None
    user_id: Snowflake | None
    id: Snowflake
    action_type: AuditLogEvent


class AuditLog(TypedDict):
    webhooks: list[Webhook]
    users: list[User]
    audit_log_entries: list[AuditLogEntry]
    integrations: list[PartialIntegration]
    threads: list[Thread]
    scheduled_events: list[ScheduledEvent]
    auto_moderation_rules: list[AutoModRule]
