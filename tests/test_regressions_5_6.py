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

import sys
import typing
from unittest.mock import AsyncMock

import pytest

import discord
from discord import types as t
from discord.channel import (
    MediaChannel,
    PartialMessageable,
    StageChannel,
    TextChannel,
    VoiceChannel,
)
from discord.message import Message
from discord.threads import Thread
from discord.ui.view import ViewStore

if typing.TYPE_CHECKING:
    from tests.models.context import World


class TestThumbnailSpoilerInSection:
    async def test_spoiler_survives_being_an_accessory(self) -> None:
        thumbnail = discord.ui.Thumbnail("https://example.com/a.png", spoiler=True)
        section = discord.ui.Section(discord.ui.TextDisplay("x"), accessory=thumbnail)
        assert section.to_component_dict()["accessory"]["spoiler"] is True

    async def test_default_is_not_a_spoiler(self) -> None:
        section = discord.ui.Section(
            discord.ui.TextDisplay("x"),
            accessory=discord.ui.Thumbnail("https://example.com/a.png"),
        )
        assert section.to_component_dict()["accessory"]["spoiler"] is False


class TestViewStoreRemoveView:
    async def test_every_key_of_the_view_is_removed(self) -> None:
        store = ViewStore(None)
        view = discord.ui.DesignerView(
            discord.ui.ActionRow(
                discord.ui.Button(label="a", custom_id="a"),
                discord.ui.Button(label="b", custom_id="b"),
            ),
            timeout=None,
        )
        other = discord.ui.DesignerView(
            discord.ui.ActionRow(discord.ui.Button(label="c", custom_id="c")),
            timeout=None,
        )
        store.add_view(view, 10)
        store.add_view(other, 11)
        assert len(store._views) == 3

        store.remove_view(view)

        assert [key[2] for key in store._views] == ["c"]
        assert store.get_message_view(10) is None
        assert store.get_message_view(11) is other

    async def test_views_without_message_are_removed_too(self) -> None:
        store = ViewStore(None)
        view = discord.ui.View(
            discord.ui.Button(label="a", custom_id="a"), timeout=None
        )
        store.add_view(view)
        store.remove_view(view)
        assert store._views == {}


class TestLegacyModalRemoveItem:
    async def test_remove_item_does_not_raise(self) -> None:
        first = discord.ui.InputText(label="a", custom_id="a")
        second = discord.ui.InputText(label="b", custom_id="b")
        modal = discord.ui.Modal(first, second, title="t")
        modal.remove_item(first)
        assert modal.children == [second]


class TestLabelSetters:
    async def test_radio_group_options_keyword(self) -> None:
        label = discord.ui.Label("Pick")
        options = [
            discord.RadioGroupOption(label="a"),
            discord.RadioGroupOption(label="b"),
        ]
        label.set_radio_group(custom_id="r", options=options)
        assert label.item.options == options

    async def test_checkbox_group_options_keyword(self) -> None:
        label = discord.ui.Label("Pick")
        options = [discord.CheckboxGroupOption(label="a")]
        label.set_checkbox_group(custom_id="c", options=options)
        assert label.item.options == options

    @pytest.mark.parametrize(
        "method", ["set_file_upload", "set_radio_group", "set_checkbox_group"]
    )
    def test_required_is_not_nullable(self, method: str) -> None:
        hints = typing.get_type_hints(
            getattr(discord.ui.Label, method),
            localns={"Self": typing.Any},
        )
        assert hints["required"] is bool


class TestSelectOptions:
    async def test_options_are_validated_on_init(self) -> None:
        with pytest.raises(TypeError):
            discord.ui.Select(options=["not an option"])  # type: ignore[list-item]
        select = discord.ui.Select(options=[discord.SelectOption(label="a")])
        assert [o.label for o in select.options] == ["a"]

    async def test_options_are_not_shared_between_selects(self) -> None:
        first = discord.ui.Select()
        second = discord.ui.Select()
        first.append_option(discord.SelectOption(label="a"))
        assert second.options == []


class TestMemberEditWithBothPayloads:
    async def test_bot_fields_are_sent_to_me(self, world: World) -> None:
        member = discord.Member(
            data=world.payload(
                t.member.MemberWithUser,
                user=world.payload(t.user.User, id=str(world.me.id)),
            ),
            guild=world.guild,
            state=world.state,
        )
        assert world.state.self_id == member.id
        returned = world.payload(t.member.MemberWithUser)
        edit_member = AsyncMock(return_value=returned)
        world.http.edit_member = edit_member

        await member.edit(nick="new nick", mute=True)

        assert edit_member.await_count == 2
        first, second = edit_member.await_args_list
        assert first.args == (world.guild.id, member.id)
        assert first.kwargs["mute"] is True
        assert "nick" not in first.kwargs
        assert second.args == (world.guild.id, "@me")
        assert second.kwargs["nick"] == "new nick"

    async def test_only_bot_fields(self, world: World) -> None:
        member = discord.Member(
            data=world.payload(
                t.member.MemberWithUser,
                user=world.payload(t.user.User, id=str(world.me.id)),
            ),
            guild=world.guild,
            state=world.state,
        )
        edit_member = AsyncMock(return_value=world.payload(t.member.MemberWithUser))
        world.http.edit_member = edit_member
        result = await member.edit(nick="only")
        assert edit_member.await_count == 1
        assert edit_member.await_args.args == (world.guild.id, "@me")
        assert isinstance(result, discord.Member)

    async def test_nothing_to_edit(self, world: World) -> None:
        world.http.edit_member = AsyncMock()
        assert await world.member.edit() is None
        world.http.edit_member.assert_not_awaited()


class TestMessageThreadFromPartialMessageable:
    async def test_thread_is_resolved_through_the_payload_guild(
        self, world: World
    ) -> None:
        channel = PartialMessageable(state=world.state, id=world.channel.id)
        thread_payload = world.payload(t.threads.Thread, guild_id=str(world.guild.id))
        data = world.payload(t.message.Message, thread=thread_payload, guild_id=None)
        message = Message(state=world.state, channel=channel, data=data)
        await world.state._populate_message(message, data)
        assert isinstance(message.thread, Thread)
        assert message.thread.guild_id == world.guild.id
        assert message.thread.id == int(thread_payload["id"])

    async def test_cached_thread_is_reused(self, world: World) -> None:
        channel = PartialMessageable(state=world.state, id=world.channel.id)
        thread_payload = world.payload(t.threads.Thread, guild_id=str(world.guild.id))
        cached = Thread(guild=world.guild, state=world.state, data=thread_payload)
        await world.guild._add_thread(cached)
        data = world.payload(t.message.Message, thread=thread_payload, guild_id=None)
        message = Message(state=world.state, channel=channel, data=data)
        await world.state._populate_message(message, data)
        assert message.thread is cached

    async def test_unknown_guild_gives_no_thread(self, world: World) -> None:
        channel = PartialMessageable(state=world.state, id=world.channel.id)
        thread_payload = world.payload(t.threads.Thread, guild_id="999999999999")
        data = world.payload(t.message.Message, thread=thread_payload, guild_id=None)
        message = Message(state=world.state, channel=channel, data=data)
        await world.state._populate_message(message, data)
        assert message.thread is None

    async def test_message_without_thread(self, world: World) -> None:
        payload = world.payload(t.message.Message)
        payload.pop("thread", None)
        message = Message(state=world.state, channel=world.channel, data=payload)
        assert message.thread is None


class TestThreadFillsMissingData:
    async def test_missing_data_comes_from_the_cached_thread(
        self, world: World
    ) -> None:
        payload = world.payload(t.threads.Thread, guild_id=str(world.guild.id))
        cached = Thread(guild=world.guild, state=world.state, data=dict(payload))
        await world.guild._add_thread(cached)

        partial = dict(payload)
        partial.pop("owner_id", None)
        partial["_invoke_flag"] = True
        thread = await world.state._build_thread(world.guild, partial)

        assert thread.owner_id == cached.owner_id

    async def test_without_invoke_flag_nothing_is_filled(self, world: World) -> None:
        payload = world.payload(t.threads.Thread, guild_id=str(world.guild.id))
        cached = Thread(guild=world.guild, state=world.state, data=dict(payload))
        await world.guild._add_thread(cached)
        partial = dict(payload)
        partial.pop("owner_id", None)
        thread = await world.state._build_thread(world.guild, partial)
        assert thread.owner_id is None


@pytest.mark.skipif(sys.version_info < (3, 11), reason="typing.get_overloads")
class TestChannelOverloads:
    def test_media_channel_edit_returns_media_channel(self) -> None:
        overloads = typing.get_overloads(MediaChannel.edit)
        assert overloads
        assert {o.__annotations__["return"] for o in overloads} == {
            "MediaChannel | None"
        }

    @pytest.mark.parametrize("cls", [VoiceChannel, StageChannel])
    def test_sync_permissions_is_a_bool(self, cls: type) -> None:
        full = [
            o
            for o in typing.get_overloads(cls.edit)
            if "sync_permissions" in o.__annotations__
        ]
        assert full
        assert all(o.__annotations__["sync_permissions"] == "bool" for o in full)

    def test_stage_edit_accepts_voice_style_options(self) -> None:
        full = [
            o
            for o in typing.get_overloads(StageChannel.edit)
            if "sync_permissions" in o.__annotations__
        ]
        for name in ("bitrate", "user_limit", "slowmode_delay"):
            assert all(name in o.__annotations__ for o in full)

    def test_send_notification_is_a_bool(self) -> None:
        assert (
            StageChannel.create_instance.__annotations__["send_notification"] == "bool"
        )

    def test_archived_threads_limit_doc(self) -> None:
        assert "limit: Optional[:class:`int`]" in TextChannel.archived_threads.__doc__
        assert (
            "limit: Optional[:class:`bool`]" not in TextChannel.archived_threads.__doc__
        )
