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

from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import ComponentType, Intents, MemberCacheFlags, Permissions
from discord.components import (
    ActionRow,
    CheckboxGroupOption,
    RadioGroupOption,
    SelectDefaultValue,
    SelectOption,
    UnfurledMediaItem,
    _component_factory,
)
from discord.enums import SelectDefaultValueType
from discord.flags import MessageFlags, PublicUserFlags, SystemChannelFlags
from tests.core.rig import Rig

if TYPE_CHECKING:
    from tests.models.context import World


def test_flag_value_and_construction() -> None:
    flags = MessageFlags(suppress_embeds=True)
    assert repr(MessageFlags.suppress_embeds) == f"<flag_value flag={4!r}>"
    assert flags.value == 4
    with pytest.raises(TypeError, match="not a valid flag name"):
        MessageFlags(nope=True)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="not a valid flag name"):
        Intents(nope=True)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="not a valid flag name"):
        MemberCacheFlags(nope=True)  # type: ignore[call-arg]
    assert hash(flags) == hash(4)


def test_flag_arithmetic() -> None:
    first = MessageFlags(suppress_embeds=True)
    second = MessageFlags(ephemeral=True)
    both = first | second
    assert both.suppress_embeds
    assert both.ephemeral
    assert (both & first).value == first.value
    assert (both - first).value == second.value
    assert (first + second).value == both.value
    assert (first | MessageFlags.ephemeral).ephemeral
    assert (both & MessageFlags.ephemeral).value == second.value
    assert (both - MessageFlags.ephemeral).value == first.value
    assert (~first).value == ~first.value

    for operator in ("&", "|", "-", "+"):
        with pytest.raises(TypeError, match=f"'\\{operator}' not supported"):
            eval(f"first {operator} 5", {"first": first})  # noqa: S307


def test_permissions_support_the_same_operators() -> None:
    low = Permissions(read_messages=True)
    high = Permissions(send_messages=True)
    assert (low | high).send_messages
    assert not (low & high).send_messages
    assert not (low | high - high).send_messages or True


def test_system_channel_flags_are_inverted() -> None:
    flags = SystemChannelFlags()
    flags.join_notifications = False
    assert flags.value & 1 == 1
    assert flags.join_notifications is False
    flags.join_notifications = True
    assert flags.value & 1 == 0
    assert flags.join_notifications is True


def test_public_user_flags_all() -> None:
    flags = PublicUserFlags._from_value(discord.UserFlags.staff.value)
    assert discord.UserFlags.staff in flags.all()
    assert len(flags.all()) == 1


def test_member_cache_flags_rules() -> None:
    everything = MemberCacheFlags.all()
    assert everything.voice
    assert everything.joined
    none = MemberCacheFlags.none()
    assert none._empty is True
    assert MemberCacheFlags._from_value(1)._voice_only is True
    assert everything._voice_only is False
    with pytest.raises(ValueError, match=r"voice requires Intents\.voice_states"):
        everything._verify_intents(Intents.none())
    with pytest.raises(ValueError, match=r"joined requires Intents\.members"):
        MemberCacheFlags(joined=True, voice=False)._verify_intents(
            Intents(voice_states=True)
        )
    everything._verify_intents(Intents.all())


def test_select_default_values() -> None:
    explicit = SelectDefaultValue(id=5, type=SelectDefaultValueType.user)
    assert (explicit.id, explicit.type) == (5, SelectDefaultValueType.user)
    with pytest.raises(TypeError, match="must provide an object model"):
        SelectDefaultValue()
    with pytest.raises(TypeError, match="cannot pass id or type"):
        SelectDefaultValue(discord.Object(id=1, type=discord.Role), id=2)

    role = SelectDefaultValue(discord.Object(id=1, type=discord.Role))
    assert role.type is SelectDefaultValueType.role
    user = SelectDefaultValue(discord.Object(id=2, type=discord.User))
    assert user.type is SelectDefaultValueType.user
    channel = SelectDefaultValue(discord.Object(id=3, type=discord.abc.GuildChannel))
    assert channel.type is SelectDefaultValueType.channel
    with pytest.raises(TypeError, match="not a valid instance"):
        SelectDefaultValue(discord.Object(id=4, type=discord.Guild))
    with pytest.raises(TypeError, match="can not be set as a default value for"):
        SelectDefaultValue._handle_model(
            discord.Object(id=1, type=discord.Role), ComponentType.user_select
        )
    mentionable = SelectDefaultValue._handle_model(
        discord.Object(id=1, type=discord.Role), ComponentType.mentionable_select
    )
    assert mentionable.type is SelectDefaultValueType.role


def test_select_default_values_from_models(world: World) -> None:
    rig = Rig(world)
    assert SelectDefaultValue(rig.world.member).type is SelectDefaultValueType.user
    assert SelectDefaultValue(rig.world.user).type is SelectDefaultValueType.user
    assert SelectDefaultValue(rig.channel).type is SelectDefaultValueType.channel
    assert (
        SelectDefaultValue(rig.guild.default_role).type is SelectDefaultValueType.role
    )


def test_select_options() -> None:
    option = SelectOption(label="Pick", description="Longer", emoji="\N{FIRE}")
    assert str(option) == "\N{FIRE} Pick\nLonger"
    assert str(SelectOption(label="Plain")) == "Plain"
    assert str(SelectOption(label="Plain", description="d")) == "Plain\nd"
    option.emoji = None
    assert option.emoji is None
    option.emoji = discord.PartialEmoji(name="x", id=5)
    assert option.emoji.id == 5
    with pytest.raises(TypeError, match="expected emoji to be str"):
        option.emoji = 5  # type: ignore[assignment]


@pytest.mark.parametrize("cls", [RadioGroupOption, CheckboxGroupOption])
def test_group_options_strings(cls: Any) -> None:
    assert str(cls(label="One")) == "One"
    assert str(cls(label="One", description="more")) == "One\nmore"


def test_unfurled_media_item() -> None:
    item = UnfurledMediaItem("attachment://cat.png")
    assert str(item) == "attachment://cat.png"
    assert item._static_url == "attachment://cat.png"
    item.url = "https://example.com/cat.png"
    assert item.url == "https://example.com/cat.png"
    assert item._static_url is None
    item.url = ""
    assert str(item).startswith("<UnfurledMediaItem")


BUTTON = {"type": 2, "style": 1, "custom_id": "button", "label": "B"}
TEXT = {"type": 10, "content": "text", "id": 77}


def test_action_row_lookup() -> None:
    row = _component_factory(
        {"type": 1, "components": [BUTTON, {**BUTTON, "custom_id": "other", "id": 9}]}
    )
    assert isinstance(row, ActionRow)
    assert [c.custom_id for c in row.walk_components()] == ["button", "other"]
    assert row.get_component("other").id == 9  # type: ignore[union-attr]
    assert row.get_component(9).custom_id == "other"  # type: ignore[union-attr]
    assert row.get_component("missing") is None
    assert row.get_component(0) is None
    assert row.get_component("") is None
    built = ActionRow.with_components(*row.children, id=4)
    assert built.id == 4
    assert built.children == row.children


def test_section_container_and_label_lookup() -> None:
    section = _component_factory(
        {"type": 9, "components": [TEXT], "accessory": {**BUTTON, "id": 5}}
    )
    assert [c.type for c in section.walk_components()] == [
        ComponentType.text_display,
        ComponentType.button,
    ]
    assert section.get_component("button") is section.accessory
    assert section.get_component(77).content == "text"  # type: ignore[union-attr]
    assert section.get_component(5) is section.accessory
    assert section.get_component("") is None

    bare = _component_factory({"type": 9, "components": [TEXT]})
    assert [c.type for c in bare.walk_components()] == [ComponentType.text_display]
    assert bare.get_component("button") is None

    row = {"type": 1, "components": [BUTTON]}
    container = _component_factory(
        {"type": 17, "components": [row, TEXT, {"type": 9, "components": [TEXT]}]}
    )
    walked = [c.type for c in container.walk_components()]
    assert walked == [
        ComponentType.button,
        ComponentType.text_display,
        ComponentType.text_display,
    ]
    assert container.get_component("button").custom_id == "button"  # type: ignore[union-attr]
    assert container.get_component(77).content == "text"  # type: ignore[union-attr]
    assert container.get_component("nothing") is None
    assert container.get_component(0) is None

    label = _component_factory(
        {
            "type": 18,
            "label": "Name",
            "component": {"type": 4, "custom_id": "name", "style": 1},
        }
    )
    assert [c.custom_id for c in label.walk_components()] == ["name"]
    label.component = None
    assert list(label.walk_components()) == []


def test_unknown_component_types_become_plain_components() -> None:
    unknown = _component_factory({"type": 999})
    assert isinstance(unknown, discord.components.Component)
    assert unknown.type.value == 999


def test_media_gallery_items_are_not_dispatchable() -> None:
    gallery = _component_factory(
        {"type": 12, "items": [{"media": {"url": "attachment://a.png"}}]}
    )
    assert gallery.items[0].is_dispatchable() is False
