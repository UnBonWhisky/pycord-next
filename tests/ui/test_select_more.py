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

from types import SimpleNamespace
from typing import Any

import pytest

import discord
from discord import ui
from discord.components import _component_factory
from discord.enums import ChannelType, ComponentType, SelectDefaultValueType
from discord.errors import InvalidArgument

OPT = discord.SelectOption(label="a", value="a")


class TestSelectConstruction:
    async def test_invalid_combinations(self) -> None:
        with pytest.raises(InvalidArgument, match="options"):
            ui.Select(ComponentType.user_select, options=[OPT])
        with pytest.raises(InvalidArgument, match="channel_types"):
            ui.Select(channel_types=[ChannelType.text])
        with pytest.raises(ValueError, match="min_values"):
            ui.Select(options=[OPT], required=True, min_values=0)

    async def test_default_values_validation(self) -> None:
        user = discord.SelectDefaultValue(id=1, type=SelectDefaultValueType.user)
        role = discord.SelectDefaultValue(id=2, type=SelectDefaultValueType.role)
        ok = ui.Select(ComponentType.user_select, default_values=[user])
        assert ok.default_values == [user]
        with pytest.raises(TypeError, match="not a valid select default value"):
            ui.Select(ComponentType.user_select, default_values=[role])
        with pytest.raises(TypeError, match="not allowed for this select type"):
            ui.Select(default_values=[user])
        mention = ui.Select(
            ComponentType.mentionable_select, default_values=[user, role]
        )
        assert len(mention.default_values) == 2
        skipped = ui.Select(ComponentType.user_select, default_values=["str"])  # type: ignore[list-item]
        assert skipped.default_values == []
        obj = ui.Select(
            ComponentType.user_select,
            default_values=[discord.Object(5, type=discord.User)],
        )
        assert obj.default_values[0].id == 5


class TestSelectProperties:
    async def test_options_setter(self) -> None:
        select = ui.Select(options=[OPT])
        select.options = [OPT, discord.SelectOption(label="b", value="b")]
        assert len(select.options) == 2
        with pytest.raises(InvalidArgument, match="string selects"):
            ui.Select(ComponentType.user_select).options = [OPT]
        with pytest.raises(ValueError, match="options"):
            select.options = [OPT] * 26

    async def test_channel_types_setter(self) -> None:
        select = ui.Select(ComponentType.channel_select)
        select.channel_types = [ChannelType.voice]
        assert select.channel_types == [ChannelType.voice]
        with pytest.raises(InvalidArgument, match="channel selects"):
            ui.Select(options=[OPT]).channel_types = [ChannelType.text]

    async def test_option_builders(self) -> None:
        select = ui.Select(options=[OPT])
        select.add_option(label="b", value="b", description="d", default=True)
        assert [o.value for o in select.options] == ["a", "b"]
        for i in range(23):
            select.add_option(label=f"o{i}", value=f"o{i}")
        with pytest.raises(ValueError, match="maximum number of options"):
            select.append_option(discord.SelectOption(label="x", value="x"))
        with pytest.raises(InvalidArgument):
            ui.Select(ComponentType.user_select).add_option(label="b")
        with pytest.raises(InvalidArgument):
            ui.Select(ComponentType.user_select).append_option(OPT)

    async def test_default_value_builders(self) -> None:
        select = ui.Select(ComponentType.user_select)
        select.default_values = [discord.Object(1, type=discord.User)]
        select.default_values = None
        select.add_default_value(id=9)
        assert select.default_values[0].type is SelectDefaultValueType.user
        select.append_default_value(discord.Object(3, type=discord.User))
        assert [d.id for d in select.default_values] == [9, 3]
        mentionable = ui.Select(ComponentType.mentionable_select)
        with pytest.raises(TypeError, match="type is required"):
            mentionable.add_default_value(id=1)
        mentionable.add_default_value(id=1, type=SelectDefaultValueType.role)
        with pytest.raises(TypeError, match="do not allow default_values"):
            ui.Select(options=[OPT]).append_default_value(
                discord.Object(1, type=discord.User)
            )
        full = ui.Select(ComponentType.role_select)
        for i in range(25):
            full.add_default_value(id=i)
        with pytest.raises(ValueError, match="maximum number of default values"):
            full.add_default_value(id=99)

    async def test_refresh_state_and_dispatchability(self) -> None:
        select = ui.Select(options=[OPT], custom_id="s")
        select.refresh_state({"values": ["a"]})
        assert select._selected_values == ["a"]
        assert select.values is None
        interaction = object.__new__(discord.Interaction)
        interaction.data = {"values": ["a"]}
        select.refresh_state(interaction)
        assert select.values == ["a"]
        assert select.is_dispatchable()
        assert select.is_storable()
        view = ui.View(select, store=False)
        assert select.is_dispatchable() is False
        assert view.children == [select]

    async def test_from_component(self) -> None:
        component = _component_factory(
            {
                "type": 5,
                "custom_id": "u",
                "default_values": [{"id": "1", "type": "user"}],
                "min_values": 1,
                "max_values": 2,
            }
        )
        select = ui.Select.from_component(component)
        assert select.type is ComponentType.user_select
        assert select.default_values[0].id == 1


class TestSelectDecorators:
    def test_validation(self) -> None:
        with pytest.raises(ValueError, match="select_type"):
            ui.select(ComponentType.button)
        with pytest.raises(TypeError, match="options"):
            ui.select(ComponentType.user_select, options=[OPT])
        with pytest.raises(TypeError, match="channel_types"):
            ui.select(ComponentType.user_select, channel_types=[ChannelType.text])
        with pytest.raises(TypeError, match="default_values"):
            ui.select(ComponentType.string_select, default_values=[1])  # type: ignore[list-item]
        with pytest.raises(TypeError, match="coroutine"):
            ui.select()(lambda self, s, i: None)  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        ("factory", "kind"),
        [
            (ui.string_select, ComponentType.string_select),
            (ui.user_select, ComponentType.user_select),
            (ui.role_select, ComponentType.role_select),
            (ui.mentionable_select, ComponentType.mentionable_select),
            (ui.channel_select, ComponentType.channel_select),
        ],
    )
    async def test_shortcuts_build_items(self, factory: Any, kind: Any) -> None:
        kwargs: dict[str, Any] = {"custom_id": "x"}
        if kind is ComponentType.string_select:
            kwargs["options"] = [OPT]
        if kind is ComponentType.channel_select:
            kwargs["channel_types"] = [ChannelType.text]

        class V(ui.View):
            @factory(**kwargs)
            async def pick(self, select: Any, interaction: Any) -> None:
                pass

        view = V()
        assert view.pick.type is kind
        assert view.pick.custom_id == "x"


class TestResolution:
    async def test_string_select_has_no_resolution(self) -> None:
        select = ui.Select(options=[OPT], custom_id="s")
        select.refresh_state({"values": ["a"]})
        await select._resolve_state()
        assert select._resolved_values is None
        assert select._selected_values == ["a"]

    async def test_without_interaction_resolves_empty(self) -> None:
        select = ui.Select(ComponentType.user_select, custom_id="u")
        await select._resolve_state()
        assert select._resolved_values == []
        select.refresh_state({"values": ["1"]})
        await select._resolve_state()
        assert select._resolved_values == []
        select._interaction = SimpleNamespace(data={"resolved": {}}, guild=None)
        await select._resolve_state()
        assert select._resolved_values == []
