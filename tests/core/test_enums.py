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

from typing import Union

import pytest

import discord
from discord import enums
from discord.enums import AuditLogAction, SlashCommandOptionType as OptionType


class Plain(enums.Enum):
    first = 1
    second = 2
    alias = 1

    def describe(self) -> str:
        return f"{self.name}!"


class Ordered(enums.Enum, comparable=True):
    low = 1
    high = 5


def test_enum_members_and_aliases() -> None:
    assert list(Plain) == [Plain.first, Plain.second]
    assert list(reversed(Plain)) == [Plain.second, Plain.first]
    assert Plain.alias is Plain.first
    assert repr(Plain) == "<enum Plain>"
    assert Plain(2) is Plain.second
    assert repr(Plain.first) == "<Plain.first: 1>"
    assert str(Plain.first) == "Plain.first"
    assert Plain.second.describe() == "second!"
    assert len(Plain) == 2
    assert "first" in Plain.__members__


def test_enum_lookup_failures() -> None:
    with pytest.raises(ValueError, match="99 is not a valid Plain"):
        Plain(99)
    with pytest.raises(ValueError, match="is not a valid Plain"):
        Plain([])
    assert enums.try_enum(Plain, 99).value == 99


def test_enums_are_immutable() -> None:
    with pytest.raises(TypeError, match="immutable"):
        Plain.first = 3  # type: ignore[misc]
    with pytest.raises(TypeError, match="immutable"):
        del Plain.first


def test_comparable_enums() -> None:
    assert Ordered.low < Ordered.high
    assert Ordered.low <= Ordered.low
    assert Ordered.high > Ordered.low
    assert Ordered.high >= Ordered.high
    assert not Ordered.low > Ordered.high
    assert (Ordered.low < 3) is False


def test_string_and_int_conversions() -> None:
    assert str(discord.ChannelType.text) == "text"
    assert str(discord.VerificationLevel.high) == "high"
    assert str(enums.SortOrder.latest_activity) == "latest_activity"
    assert str(discord.ContentFilter.disabled) == "disabled"
    assert str(discord.SpeakingState.voice) == "voice"
    assert int(discord.SpeakingState.voice) == discord.SpeakingState.voice.value
    assert int(discord.VideoQualityMode.full) == 2
    assert int(discord.ScheduledEventRecurrenceFrequency.daily) == 3
    assert int(discord.ScheduledEventWeekday.monday) == 0


@pytest.mark.parametrize(
    ("value", "target"),
    [
        (-1, "all"),
        (1, "guild"),
        (10, "channel"),
        (20, "user"),
        (30, "role"),
        (40, "invite"),
        (50, "webhook"),
        (60, "emoji"),
        (73, "channel"),
        (72, "message"),
        (80, "integration"),
        (83, "stage_instance"),
        (90, "sticker"),
        (100, "scheduled_event"),
        (110, "thread"),
        (121, "application_command_permission"),
        (140, "auto_moderation_rule"),
        (150, "monetization"),
        (160, "onboarding"),
        (190, "server_guide"),
        (192, "voice_channel_status"),
        (500, None),
    ],
)
def test_audit_log_action_targets(value: int, target: str | None) -> None:
    assert enums.try_enum(AuditLogAction, value).target_type == target


@pytest.mark.parametrize(
    ("datatype", "expected"),
    [
        (discord.Member, OptionType.user),
        (discord.User, OptionType.user),
        (discord.TextChannel, OptionType.channel),
        (discord.abc.GuildChannel, OptionType.channel),
        ("Thread", OptionType.channel),
        (discord.Role, OptionType.role),
        (discord.Attachment, OptionType.attachment),
        ("Mentionable", OptionType.mentionable),
        (str, OptionType.string),
        ("anything", OptionType.string),
        (bool, OptionType.boolean),
        (int, OptionType.integer),
        (float, OptionType.number),
        ((discord.TextChannel, discord.VoiceChannel), OptionType.channel),
        ((discord.User, discord.Role), OptionType.mentionable),
        (Union[discord.User, discord.Role], OptionType.mentionable),  # noqa: UP007
        (discord.User | discord.Role, OptionType.mentionable),
    ],
)
def test_option_type_from_datatype(datatype: object, expected: OptionType) -> None:
    assert OptionType.from_datatype(datatype) is expected


def test_option_type_from_datatype_errors() -> None:
    with pytest.raises(TypeError, match=r"Invalid usage of typing\.Union"):
        OptionType.from_datatype((discord.User, discord.TextChannel))
    with pytest.raises(TypeError, match="Invalid class"):
        OptionType.from_datatype(dict)
    assert OptionType.from_datatype(discord.ApplicationContext) is None
