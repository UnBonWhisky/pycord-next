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
from tests.core.rig import (
    MP3,
    PNG,
    Case,
    Rig,
    check_list,
    check_type,
    execute,
    guild,
    lst,
    one,
)

if TYPE_CHECKING:
    from tests.models.context import World

USER = discord.Object(id=4242)
ROLE = discord.Object(id=5252)


CASES = [
    Case(
        "fetch_sounds",
        guild,
        "fetch_sounds",
        "get_all_guild_sounds",
        lambda r: {"items": [r.payload(t.soundboard.SoundboardSound)]},
        called_with=lambda r: ((r.guild.id,), {}),
        check=check_list(discord.SoundboardSound),
    ),
    Case(
        "fetch_sound",
        guild,
        "fetch_sound",
        "get_guild_sound",
        one(t.soundboard.SoundboardSound),
        args=lambda r: (77,),
        called_with=lambda r: ((r.guild.id, 77), {}),
        check=check_type(discord.SoundboardSound),
    ),
    Case(
        "create_sound_unicode_emoji",
        guild,
        "create_sound",
        "create_guild_sound",
        one(t.soundboard.SoundboardSound),
        args=lambda r: ("boom", MP3),
        kwargs=lambda r: {"emoji": "\N{FIRE}", "reason": "why", "volume": 0.5},
        check=lambda r, res: (
            check_type(discord.SoundboardSound)(r, res),
            _sound_payload(r, emoji_name="\N{FIRE}", emoji_id=None),
        ),
    ),
    Case(
        "fetch_roles_member_counts",
        guild,
        "fetch_roles_member_counts",
        "get_roles_member_counts",
        lambda r: {"1": 3},
        called_with=lambda r: ((r.guild.id,), {}),
        check=lambda r, res: _counts(res),
    ),
    Case(
        "leave",
        guild,
        "leave",
        "leave_guild",
        None,
        called_with=lambda r: ((r.guild.id,), {}),
    ),
    Case(
        "kick",
        guild,
        "kick",
        "kick",
        None,
        args=lambda r: (USER,),
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((USER.id, r.guild.id), {"reason": "r"}),
    ),
    Case(
        "ban",
        guild,
        "ban",
        "ban",
        None,
        args=lambda r: (USER,),
        kwargs=lambda r: {"delete_message_seconds": 60, "reason": "r"},
        called_with=lambda r: ((USER.id, r.guild.id, 60), {"reason": "r"}),
    ),
    Case(
        "unban",
        guild,
        "unban",
        "unban",
        None,
        args=lambda r: (USER,),
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((USER.id, r.guild.id), {"reason": "r"}),
    ),
    Case(
        "bulk_ban",
        guild,
        "bulk_ban",
        "bulk_ban",
        lambda r: {"banned_users": [str(USER.id)], "failed_users": [str(ROLE.id)]},
        args=lambda r: (USER, ROLE),
        kwargs=lambda r: {"delete_message_seconds": 5, "reason": "r"},
        called_with=lambda r: (([USER.id, ROLE.id], r.guild.id, 5), {"reason": "r"}),
        check=lambda r, res: res == ([USER], [ROLE]) or pytest.fail(res),
    ),
    Case(
        "fetch_ban",
        guild,
        "fetch_ban",
        "get_ban",
        lambda r: {"reason": "spam", "user": r.payload(t.user.User)},
        args=lambda r: (USER,),
        called_with=lambda r: ((USER.id, r.guild.id), {}),
        check=lambda r, res: res.reason == "spam" or pytest.fail(res),
    ),
    Case(
        "prune_members",
        guild,
        "prune_members",
        "prune_members",
        {"pruned": 3},
        kwargs=lambda r: {"days": 7, "roles": [ROLE], "reason": "r"},
        called_with=lambda r: (
            (r.guild.id, 7),
            {"compute_prune_count": True, "roles": [str(ROLE.id)], "reason": "r"},
        ),
        check=lambda r, res: res == 3 or pytest.fail(res),
    ),
    Case(
        "estimate_pruned_members",
        guild,
        "estimate_pruned_members",
        "estimate_pruned_members",
        {"pruned": 4},
        kwargs=lambda r: {"days": 3, "roles": [ROLE]},
        called_with=lambda r: ((r.guild.id, 3, [str(ROLE.id)]), {}),
        check=lambda r, res: res == 4 or pytest.fail(res),
    ),
    Case(
        "search_members",
        guild,
        "search_members",
        "search_members",
        lst(t.member.MemberWithUser),
        args=lambda r: ("bob",),
        kwargs=lambda r: {"limit": 5},
        called_with=lambda r: ((r.guild.id, "bob", 5), {}),
        check=check_list(discord.Member),
    ),
    Case(
        "templates",
        guild,
        "templates",
        "guild_templates",
        lst(t.template.Template),
        called_with=lambda r: ((r.guild.id,), {}),
        check=check_list(discord.Template),
    ),
    Case(
        "webhooks",
        guild,
        "webhooks",
        "guild_webhooks",
        lst(t.webhook.Webhook),
        called_with=lambda r: ((r.guild.id,), {}),
        check=check_list(discord.Webhook),
    ),
    Case(
        "create_template",
        guild,
        "create_template",
        "create_template",
        one(t.template.Template),
        kwargs=lambda r: {"name": "tpl", "description": "d"},
        called_with=lambda r: ((r.guild.id, {"name": "tpl", "description": "d"}), {}),
        check=check_type(discord.Template),
    ),
    Case(
        "create_integration",
        guild,
        "create_integration",
        "create_integration",
        None,
        kwargs=lambda r: {"type": "twitch", "id": 9},
        called_with=lambda r: ((r.guild.id, "twitch", 9), {}),
    ),
    Case(
        "integrations",
        guild,
        "integrations",
        "get_all_integrations",
        lst(t.integration.BotIntegration, type="discord"),
        called_with=lambda r: ((r.guild.id,), {}),
        check=lambda r, res: len(res) == 1 or pytest.fail(res),
    ),
    Case(
        "fetch_stickers",
        guild,
        "fetch_stickers",
        "get_all_guild_stickers",
        lst(t.sticker.GuildSticker),
        called_with=lambda r: ((r.guild.id,), {}),
        check=check_list(discord.GuildSticker),
    ),
    Case(
        "delete_sticker",
        guild,
        "delete_sticker",
        "delete_guild_sticker",
        None,
        args=lambda r: (USER,),
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.guild.id, USER.id, "r"), {}),
    ),
    Case(
        "fetch_emojis",
        guild,
        "fetch_emojis",
        "get_all_custom_emojis",
        lst(t.emoji.Emoji),
        called_with=lambda r: ((r.guild.id,), {}),
        check=check_list(discord.GuildEmoji),
    ),
    Case(
        "delete_emoji",
        guild,
        "delete_emoji",
        "delete_custom_emoji",
        None,
        args=lambda r: (USER,),
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.guild.id, USER.id), {"reason": "r"}),
    ),
    Case(
        "create_custom_emoji",
        guild,
        "create_custom_emoji",
        "create_custom_emoji",
        one(t.emoji.Emoji),
        kwargs=lambda r: {"name": "em", "image": PNG, "roles": [ROLE], "reason": "r"},
        check=lambda r, res: (
            check_type(discord.GuildEmoji)(r, res),
            r.http.create_custom_emoji.assert_called_once_with(
                r.guild.id,
                "em",
                "data:image/png;base64,iVBORw0KGgo=",
                roles=[ROLE.id],
                reason="r",
            ),
        ),
    ),
    Case(
        "fetch_role",
        guild,
        "fetch_role",
        "get_role",
        one(t.role.Role),
        args=lambda r: (123,),
        called_with=lambda r: ((r.guild.id, 123), {}),
        check=check_type(discord.Role),
    ),
    Case(
        "welcome_screen",
        guild,
        "welcome_screen",
        "get_welcome_screen",
        one(t.welcome_screen.WelcomeScreen),
        called_with=lambda r: ((r.guild.id,), {}),
        check=check_type(discord.WelcomeScreen),
    ),
    Case(
        "widget",
        guild,
        "widget",
        "get_widget",
        one(t.widget.Widget),
        called_with=lambda r: ((r.guild.id,), {}),
        check=check_type(discord.Widget),
    ),
    Case(
        "edit_widget",
        guild,
        "edit_widget",
        "edit_widget",
        None,
        kwargs=lambda r: {"enabled": True, "channel": r.channel},
        called_with=lambda r: (
            (r.guild.id,),
            {"payload": {"channel_id": r.channel.id, "enabled": True}},
        ),
    ),
    Case(
        "edit_widget_clear_channel",
        guild,
        "edit_widget",
        "edit_widget",
        None,
        kwargs=lambda r: {"channel": None},
        called_with=lambda r: ((r.guild.id,), {"payload": {"channel_id": None}}),
    ),
    Case(
        "fetch_auto_moderation_rules",
        guild,
        "fetch_auto_moderation_rules",
        "get_auto_moderation_rules",
        lst(t.automod.AutoModRule),
        called_with=lambda r: ((r.guild.id,), {}),
        check=check_list(discord.AutoModRule),
    ),
    Case(
        "fetch_auto_moderation_rule",
        guild,
        "fetch_auto_moderation_rule",
        "get_auto_moderation_rule",
        one(t.automod.AutoModRule),
        args=lambda r: (8,),
        called_with=lambda r: ((r.guild.id, 8), {}),
        check=check_type(discord.AutoModRule),
    ),
    Case(
        "delete_auto_moderation_rule",
        guild,
        "delete_auto_moderation_rule",
        "delete_auto_moderation_rule",
        None,
        args=lambda r: (8,),
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.guild.id, 8), {"reason": "r"}),
    ),
    Case(
        "onboarding",
        guild,
        "onboarding",
        "get_onboarding",
        one(t.onboarding.Onboarding),
        called_with=lambda r: ((r.guild.id,), {}),
        check=check_type(discord.Onboarding),
    ),
    Case(
        "edit_onboarding",
        guild,
        "edit_onboarding",
        "edit_onboarding",
        one(t.onboarding.Onboarding),
        kwargs=lambda r: {
            "prompts": None,
            "default_channels": [r.channel],
            "enabled": True,
            "mode": discord.OnboardingMode.default,
            "reason": "r",
        },
        called_with=lambda r: (
            (
                r.guild.id,
                {
                    "prompts": None,
                    "default_channel_ids": [r.channel.id],
                    "enabled": True,
                    "mode": 0,
                },
            ),
            {"reason": "r"},
        ),
        check=check_type(discord.Onboarding),
    ),
    Case(
        "modify_incident_actions",
        guild,
        "modify_incident_actions",
        "modify_guild_incident_actions",
        lambda r: {"invites_disabled_until": None, "dms_disabled_until": None},
        kwargs=lambda r: {
            "invites_disabled_until": dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc),
            "dms_disabled_until": None,
            "reason": "r",
        },
        called_with=lambda r: (
            (
                r.guild.id,
                {
                    "invites_disabled_until": "2030-01-01T00:00:00+00:00",
                    "dms_disabled_until": None,
                },
            ),
            {"reason": "r"},
        ),
        check=check_type(discord.IncidentsData),
    ),
    Case(
        "vanity_invite_none",
        guild,
        "vanity_invite",
        "get_vanity_code",
        lambda r: {"code": None, "uses": 0},
        called_with=lambda r: ((r.guild.id,), {}),
        check=lambda r, res: res is None or pytest.fail(res),
    ),
]


def _sound_payload(r: Rig, **expected: Any) -> None:
    kwargs = r.http.create_guild_sound.call_args.kwargs
    for key, value in expected.items():
        assert kwargs[key] == value
    assert kwargs["reason"] == "why"
    assert kwargs["volume"] == 0.5


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_guild_remote_calls(world: World, case: Case) -> None:
    execute(Rig(world), case)


def _counts(result: Any) -> None:
    assert result[1] == 3
    assert result[discord.Object(id=1)] == 3
    assert discord.Object(id=1) in result
    assert result.get(discord.Object(id=1)) == 3
    assert result.get(ROLE.id) is None
    assert repr(result).startswith("<GuildRoleCounts")
