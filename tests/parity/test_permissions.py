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

"""Permission and attachment flag bits against the Discord documentation."""

from __future__ import annotations

import pytest

import discord
from discord import AttachmentFlags, LobbyMemberFlags, Permissions

DOCUMENTED_PERMISSIONS = {
    "create_instant_invite": 0,
    "kick_members": 1,
    "ban_members": 2,
    "administrator": 3,
    "manage_channels": 4,
    "manage_guild": 5,
    "add_reactions": 6,
    "view_audit_log": 7,
    "priority_speaker": 8,
    "stream": 9,
    "view_channel": 10,
    "send_messages": 11,
    "send_tts_messages": 12,
    "manage_messages": 13,
    "embed_links": 14,
    "attach_files": 15,
    "read_message_history": 16,
    "mention_everyone": 17,
    "use_external_emojis": 18,
    "view_guild_insights": 19,
    "connect": 20,
    "speak": 21,
    "mute_members": 22,
    "deafen_members": 23,
    "move_members": 24,
    "use_voice_activation": 25,
    "change_nickname": 26,
    "manage_nicknames": 27,
    "manage_roles": 28,
    "manage_webhooks": 29,
    "manage_emojis_and_stickers": 30,
    "use_application_commands": 31,
    "request_to_speak": 32,
    "manage_events": 33,
    "manage_threads": 34,
    "create_public_threads": 35,
    "create_private_threads": 36,
    "use_external_stickers": 37,
    "send_messages_in_threads": 38,
    "start_embedded_activities": 39,
    "moderate_members": 40,
    "view_creator_monetization_analytics": 41,
    "use_soundboard": 42,
    "create_guild_expressions": 43,
    "create_events": 44,
    "use_external_sounds": 45,
    "send_voice_messages": 46,
    "set_voice_channel_status": 48,
    "send_polls": 49,
    "use_external_apps": 50,
    "pin_messages": 51,
    "bypass_slowmode": 52,
}


@pytest.mark.parametrize(("name", "bit"), DOCUMENTED_PERMISSIONS.items())
def test_permission_bit(name: str, bit: int) -> None:
    assert getattr(Permissions, name).flag == 1 << bit
    assert getattr(Permissions(**{name: True}), name) is True
    assert Permissions(**{name: True}).value == 1 << bit


@pytest.mark.parametrize("name", ["create_guild_expressions", "create_events"])
def test_new_permissions_are_valid_overwrite_names(name: str) -> None:
    overwrite = discord.PermissionOverwrite(**{name: True})
    allow, deny = overwrite.pair()
    assert allow.value == getattr(Permissions, name).flag
    assert deny.value == 0


def test_all_includes_new_permissions() -> None:
    assert Permissions.all().create_guild_expressions
    assert Permissions.all().create_events


def test_categories() -> None:
    assert Permissions.general().create_guild_expressions
    assert Permissions.all_channel().create_events
    assert not Permissions.all_channel().create_guild_expressions


@pytest.mark.parametrize(
    ("name", "bit"),
    [
        ("is_clip", 0),
        ("is_thumbnail", 1),
        ("is_remix", 2),
        ("is_spoiler", 3),
        ("is_animated", 5),
    ],
)
def test_attachment_flag_bit(name: str, bit: int) -> None:
    assert getattr(AttachmentFlags, name).flag == 1 << bit
    flags = AttachmentFlags._from_value(1 << bit)
    assert getattr(flags, name) is True
    assert sum(value for _, value in flags) == 1


def test_lobby_member_flags() -> None:
    assert LobbyMemberFlags.can_link_lobby.flag == 1
    assert LobbyMemberFlags(can_link_lobby=True).value == 1
