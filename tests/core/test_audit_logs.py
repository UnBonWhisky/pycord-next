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

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import types as t
from discord.enums import AuditLogAction
from tests.core.rig import Rig

if TYPE_CHECKING:
    from tests.models.context import World


def entry(rig: Rig, action: AuditLogAction, changes: list[Any], **fields: Any) -> Any:
    payload = rig.payload(
        t.audit_log.AuditLogEntry,
        **{
            "action_type": action.value,
            "changes": changes,
            "id": "9000000000000000001",
            "target_id": "123456789012345678",
            "user_id": None,
            "options": None,
            **fields,
        },
    )
    return discord.AuditLogEntry(users={}, data=payload, guild=rig.guild)


def change(key: str, old: Any = None, new: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {"key": key}
    if old is not None:
        result["old_value"] = old
    if new is not None:
        result["new_value"] = new
    return result


@pytest.mark.filterwarnings("ignore:VoiceRegion:DeprecationWarning")
def test_simple_value_transformers(world: World) -> None:
    rig = Rig(world)
    log = entry(
        rig,
        AuditLogAction.guild_update,
        [
            change("permissions", "8", "16"),
            change("color", 1, 2),
            change("id", "5", "6"),
            change("owner_id", "7", "8"),
            change("afk_channel_id", "9", None),
            change("exempt_roles", ["1", "2"], None),
            change("exempt_channels", None, ["3"]),
            change("verification_level", 1, 2),
            change("rate_limit_per_user", 0, 5),
            change("default_message_notifications", 0, 1),
            change("communication_disabled_until", None, "2030-01-01T00:00:00+00:00"),
            change("guild_id", "11", None),
            change("rtc_region", "brazil", "us-east"),
        ],
    )
    before, after = log.before, log.after

    assert before.permissions == discord.Permissions(8)
    assert after.permissions == discord.Permissions(16)
    assert after.colour == discord.Colour(2)
    assert (before.id, after.id) == (5, 6)
    assert before.owner.id == 7
    assert before.afk_channel.id == 9
    assert after.afk_channel is None
    assert [r.id for r in before.exempt_roles] == [1, 2]
    assert [c.id for c in after.exempt_channels] == [3]
    assert after.verification_level is discord.VerificationLevel.medium
    assert after.slowmode_delay == 5
    assert after.default_notifications is discord.NotificationLevel.only_mentions
    assert after.communication_disabled_until == dt.datetime(
        2030, 1, 1, tzinfo=dt.timezone.utc
    )
    assert before.communication_disabled_until is None
    assert before.guild.id == 11
    assert after.guild is None
    assert before.rtc_region is discord.VoiceRegion.brazil
    assert len(after) == len(dict(iter(after)))
    assert "AuditLogDiff" in repr(after)
    assert before.color == before.colour
    with pytest.raises(AttributeError):
        before.nothing_here  # noqa: B018
    with pytest.raises(AttributeError):
        before._private  # noqa: B018


def test_asset_transformers(world: World) -> None:
    rig = Rig(world)
    log = entry(
        rig,
        AuditLogAction.guild_update,
        [
            change("icon_hash", "abc", None),
            change("splash_hash", "def", "ghi"),
            change("banner_hash", "jkl", None),
            change("discovery_splash_hash", None, "mno"),
            change("avatar_hash", "pqr", None),
            change("image_hash", "stu", None),
        ],
    )
    assert isinstance(log.before.icon, discord.Asset)
    assert log.after.icon is None
    assert "splashes" in log.after.splash.url
    assert "banners" in log.before.banner.url
    assert "discovery-splashes" in log.after.discovery_splash.url
    assert isinstance(log.before.avatar, discord.Asset)
    assert isinstance(log.before.image, discord.Asset)


def test_type_transformer_depends_on_the_action(world: World) -> None:
    rig = Rig(world)
    channel = entry(rig, AuditLogAction.channel_update, [change("type", 0, 2)])
    assert channel.after.type is discord.ChannelType.voice
    sticker = entry(rig, AuditLogAction.sticker_update, [change("type", 1, 2)])
    assert sticker.after.type is discord.StickerType.guild


def test_overwrite_and_automod_transformers(world: World) -> None:
    rig = Rig(world)
    log = entry(
        rig,
        AuditLogAction.overwrite_update,
        [
            change(
                "permission_overwrites",
                [{"id": "1", "type": 0, "allow": "1", "deny": "2"}],
                [
                    {"id": "2", "type": 1, "allow": "0", "deny": "4"},
                    {"id": "3", "type": 9, "allow": "0", "deny": "0"},
                ],
            ),
        ],
    )
    (role_target, role_overwrite) = log.before.overwrites[0]
    assert role_target.id == 1
    assert role_target.type is discord.Role
    assert role_overwrite.is_empty() is False
    assert [target.id for target, _ in log.after.overwrites] == [2, 3]
    assert log.after.overwrites[0][0].type is discord.Member

    rule = entry(
        rig,
        AuditLogAction.auto_moderation_rule_update,
        [
            change("trigger_type", 1, 3),
            change("event_type", 1, 1),
            change(
                "actions",
                [{"type": 1, "metadata": {}}],
                None,
            ),
            change("trigger_metadata", {"keyword_filter": ["a"]}, None),
        ],
    )
    assert rule.before.actions[0].type is discord.AutoModActionType.block_message
    assert rule.after.actions is None
    assert rule.before.trigger_metadata.keyword_filter == ["a"]
    assert rule.after.trigger_metadata is None
    assert rule.after.trigger_type is discord.AutoModTriggerType.spam


def test_role_changes_are_split_in_before_and_after(world: World) -> None:
    rig = Rig(world)
    role = {"id": "42", "name": "mod"}
    log = entry(
        rig,
        AuditLogAction.member_role_update,
        [
            change("$add", None, [role]),
            change("$remove", None, [{"id": "43", "name": "old"}]),
        ],
    )
    assert [r.id for r in log.after.roles] == [42]
    assert [r.id for r in log.before.roles] == [43]


def test_trigger_metadata_list_changes(world: World) -> None:
    rig = Rig(world)
    log = entry(
        rig,
        AuditLogAction.auto_moderation_rule_update,
        [
            change("$add_keyword_filter", None, ["bad"]),
            change("$remove_regex_patterns", None, ["x+"]),
            change("$add_allow_list", None, ["ok"]),
        ],
    )
    assert log.after.trigger_metadata is not None
    assert log.before.trigger_metadata is not None


def test_scheduled_event_location_changes(world: World) -> None:
    rig = Rig(world)
    external = entry(
        rig,
        AuditLogAction.scheduled_event_update,
        [
            change("entity_type", 3, 3),
            change("location", "park", "mall"),
        ],
    )
    assert external.before.location.value == "park"
    assert external.after.location.value == "mall"
    assert external.after.location_type is discord.ScheduledEventLocationType.external

    voice = entry(
        rig,
        AuditLogAction.scheduled_event_update,
        [
            change("entity_type", 2, 2),
            change("channel_id", "55", "56"),
            change("location", "55", "56"),
        ],
    )
    assert voice.before.location.value.id == 55
    assert voice.after.location.value.id == 56


def test_changes_can_be_resolved_with_cached_objects(world: World) -> None:
    rig = Rig(world)
    log = entry(
        rig,
        AuditLogAction.channel_update,
        [
            change("afk_channel_id", str(rig.channel.id), None),
            change("owner_id", str(rig.world.member.id), None),
            change("exempt_roles", [str(rig.guild.default_role.id)], None),
        ],
    )
    rig.run(rig.guild._add_member(rig.world.member))
    resolved = rig.run(log.get_changes())
    assert resolved.before.afk_channel is rig.channel
    assert resolved.before.owner is rig.world.member
    assert resolved.before.exempt_roles == [rig.guild.default_role]
    assert rig.run(log.get_changes()) is resolved

    sync = entry(
        rig,
        AuditLogAction.channel_update,
        [change("afk_channel_id", str(rig.channel.id), None)],
    )
    assert sync.changes.before.afk_channel is rig.channel
    assert sync.changes._resolve_sync() is sync.changes


def test_entry_extras_for_each_action(world: World) -> None:
    rig = Rig(world)

    prune = entry(
        rig,
        AuditLogAction.member_prune,
        [],
        options={"delete_member_days": "7", "members_removed": "3"},
    )
    assert (prune.extra.delete_member_days, prune.extra.members_removed) == (7, 3)

    moved = entry(
        rig, AuditLogAction.member_move, [], options={"count": "2", "channel_id": "9"}
    )
    assert moved.extra.count == 2
    assert moved.extra.channel.id == 9

    deleted = entry(
        rig,
        AuditLogAction.message_delete,
        [],
        options={"count": "1", "channel_id": "9"},
    )
    assert deleted.extra.channel.id == 9

    disconnect = entry(
        rig, AuditLogAction.member_disconnect, [], options={"count": "4"}
    )
    assert disconnect.extra.count == 4

    pin = entry(
        rig,
        AuditLogAction.message_pin,
        [],
        options={"channel_id": "9", "message_id": "10"},
    )
    assert (pin.extra.channel.id, pin.extra.message_id) == (9, 10)

    stage = entry(
        rig, AuditLogAction.stage_instance_create, [], options={"channel_id": "9"}
    )
    assert stage.extra.channel.id == 9

    member_overwrite = entry(
        rig, AuditLogAction.overwrite_create, [], options={"id": "77", "type": "1"}
    )
    assert member_overwrite.extra.id == 77
    assert member_overwrite.extra.type is discord.Member

    role_overwrite = entry(
        rig,
        AuditLogAction.overwrite_create,
        [],
        options={"id": "78", "type": "0", "role_name": "mods"},
    )
    assert role_overwrite.extra.name == "mods"
    assert role_overwrite.extra.type is discord.Role

    plain = entry(rig, AuditLogAction.guild_update, [])
    assert plain.extra is None
    assert plain.user is None
    assert plain.created_at.year >= 2015
    assert plain.category is AuditLogAction.guild_update.category


def test_entry_lookups(world: World) -> None:
    rig = Rig(world)
    log = entry(rig, AuditLogAction.guild_update, [])
    member = rig.world.member
    rig.run(rig.guild._add_member(member))

    for kind in ("", "guilds", "stickers", "emojis", "roles", "channels", "members"):
        identifier = member.id if kind == "members" else 1
        assert log._peek(kind, identifier) is (member if kind == "members" else None)
        assert rig.run(log._get(kind, identifier)) is (
            member if kind == "members" else None
        )
    assert log._peek("guilds", rig.guild.id) is rig.guild
    assert rig.run(log._get("guilds", rig.guild.id)) is rig.guild
