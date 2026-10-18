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


"""Resolution of the options of application commands from the interaction ``resolved`` data on both cache backends."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

import discord
from discord import types as t
from discord.channel import TextChannel
from discord.enums import SlashCommandOptionType as OptionType
from discord.message import Message
from discord.object import Object
from discord.role import Role
from discord.threads import Thread
from tests.commands.interaction_support import (
    MEMBER_ID,
    OTHER_ID,
    ROLE_ID,
    THREAD_ID,
    add_member,
    add_role,
    add_thread,
    backend_world,
    interaction_payload,
    is_memory,
    make_context,
    member_payload,
    thread_payload,
)

if TYPE_CHECKING:
    from tests.models.context import World

__all__ = ("backend_world",)

OTHER_CHANNEL_ID = 8500


def option_value(name: str, value: Any, kind: OptionType) -> dict[str, Any]:
    return {"name": name, "type": kind.value, "value": str(value)}


def slash(
    world: World, options: list[dict[str, Any]], resolved: dict[str, Any]
) -> tuple[discord.SlashCommand, Any, dict[str, Any]]:
    captured: dict[str, Any] = {}

    async def callback(_ctx: Any, **kwargs: Any) -> None:
        captured.update(kwargs)

    callback.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        [inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD)]
        + [
            inspect.Parameter(o["name"], inspect.Parameter.POSITIONAL_OR_KEYWORD)
            for o in options
        ]
    )

    command = discord.SlashCommand(
        callback,
        name="cmd",
        description="d",
        options=[
            discord.Option(
                o["input_type"],
                name=o["name"],
                required=False,
            )
            for o in options
        ],
    )
    names = {o["name"] for o in options}
    data = {
        "id": "1",
        "name": "cmd",
        "type": 1,
        "options": [
            {k: v for k, v in o.items() if k != "input_type"}
            for o in options
            if o["name"] in names
        ],
        "resolved": resolved,
    }
    payload = interaction_payload(world, data=data)
    return command, make_context(world, payload), captured


def run(world: World, options: list[dict[str, Any]], resolved: dict[str, Any]) -> Any:
    command, ctx, captured = slash(world, options, resolved)
    world.run(command._invoke(ctx))
    return ctx, captured


def user_resolved(world: World, user_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = member_payload(world, user_id)
    user = payload.pop("user")
    return {str(user_id): payload}, {str(user_id): user}


def channel_payload(world: World, channel_id: int, **fields: Any) -> dict[str, Any]:
    return world.payload(
        t.channel.TextChannel,
        id=str(channel_id),
        guild_id=str(world.guild.id),
        **fields,
    )


class TestMember:
    def test_cached_member_is_updated(self, backend_world: World) -> None:
        cached = add_member(backend_world, OTHER_ID)
        members, users = user_resolved(backend_world, OTHER_ID)
        members[str(OTHER_ID)]["nick"] = "Trinity"
        _, kwargs = run(
            backend_world,
            [
                {
                    **option_value("who", OTHER_ID, OptionType.user),
                    "input_type": discord.Member,
                }
            ],
            {"members": members, "users": users},
        )
        who = kwargs["who"]
        assert isinstance(who, discord.Member)
        assert who.id == OTHER_ID
        assert who.nick == "Trinity"
        if is_memory(backend_world):
            assert who is cached
        stored = backend_world.run(backend_world.guild.get_member(OTHER_ID))
        assert stored is not None
        assert stored.nick == "Trinity"

    def test_uncached_member_is_built(self, backend_world: World) -> None:
        members, users = user_resolved(backend_world, OTHER_ID)
        ctx, kwargs = run(
            backend_world,
            [
                {
                    **option_value("who", OTHER_ID, OptionType.user),
                    "input_type": discord.Member,
                }
            ],
            {"members": members, "users": users},
        )
        who = kwargs["who"]
        assert isinstance(who, discord.Member)
        assert who.id == OTHER_ID
        assert who.guild_id == backend_world.guild.id
        assert ctx.guild is not None

    def test_member_with_uncached_guild(self, backend_world: World) -> None:
        backend_world.run(backend_world.state._remove_guild(backend_world.guild))
        members, users = user_resolved(backend_world, OTHER_ID)
        _, kwargs = run(
            backend_world,
            [
                {
                    **option_value("who", OTHER_ID, OptionType.user),
                    "input_type": discord.Member,
                }
            ],
            {"members": members, "users": users},
        )
        who = kwargs["who"]
        assert isinstance(who, discord.Member)
        assert who.guild_id == backend_world.guild.id

    def test_user_without_member(self, backend_world: World) -> None:
        user = {**backend_world.payload(t.user.User), "id": str(OTHER_ID)}
        _, kwargs = run(
            backend_world,
            [
                {
                    **option_value("who", OTHER_ID, OptionType.user),
                    "input_type": discord.User,
                }
            ],
            {"users": {str(OTHER_ID): user}},
        )
        assert type(kwargs["who"]) is discord.User
        assert kwargs["who"].id == OTHER_ID

    def test_unresolved_is_an_object(self, backend_world: World) -> None:
        _, kwargs = run(
            backend_world,
            [
                {
                    **option_value("who", OTHER_ID, OptionType.user),
                    "input_type": discord.User,
                }
            ],
            {},
        )
        assert isinstance(kwargs["who"], Object)
        assert kwargs["who"].id == OTHER_ID


class TestMentionable:
    def option(self) -> dict[str, Any]:
        return {"input_type": discord.abc.Mentionable}

    def test_member(self, backend_world: World) -> None:
        cached = add_member(backend_world, OTHER_ID)
        members, users = user_resolved(backend_world, OTHER_ID)
        _, kwargs = run(
            backend_world,
            [
                {
                    **option_value("who", OTHER_ID, OptionType.mentionable),
                    **self.option(),
                }
            ],
            {"members": members, "users": users},
        )
        assert isinstance(kwargs["who"], discord.Member)
        if is_memory(backend_world):
            assert kwargs["who"] is cached

    def test_role(self, backend_world: World) -> None:
        payload = backend_world.payload(t.role.Role, id=str(ROLE_ID), name="Mods")
        payload.pop("tags", None)
        _, kwargs = run(
            backend_world,
            [
                {
                    **option_value("who", ROLE_ID, OptionType.mentionable),
                    **self.option(),
                }
            ],
            {"roles": {str(ROLE_ID): payload}},
        )
        assert isinstance(kwargs["who"], Role)
        assert kwargs["who"].name == "Mods"
        assert kwargs["who"].guild_id == backend_world.guild.id

    def test_unresolved(self, backend_world: World) -> None:
        _, kwargs = run(
            backend_world,
            [
                {
                    **option_value("who", OTHER_ID, OptionType.mentionable),
                    **self.option(),
                }
            ],
            {},
        )
        assert isinstance(kwargs["who"], Object)


class TestRole:
    def test_role_is_built_from_the_payload(self, backend_world: World) -> None:
        add_role(backend_world)
        payload = backend_world.payload(t.role.Role, id=str(ROLE_ID), name="Fresh")
        payload.pop("tags", None)
        _, kwargs = run(
            backend_world,
            [
                {
                    **option_value("r", ROLE_ID, OptionType.role),
                    "input_type": discord.Role,
                }
            ],
            {"roles": {str(ROLE_ID): payload}},
        )
        assert isinstance(kwargs["r"], Role)
        assert kwargs["r"].name == "Fresh"


class TestChannel:
    def channel_option(self) -> dict[str, Any]:
        return {
            **option_value("c", 0, OptionType.channel),
            "input_type": discord.abc.GuildChannel,
        }

    def run_channel(
        self, world: World, channel_id: int, payload: dict[str, Any]
    ) -> Any:
        option = self.channel_option()
        option["value"] = str(channel_id)
        _, kwargs = run(world, [option], {"channels": {str(channel_id): payload}})
        return kwargs["c"]

    def test_cached_channel_is_updated_in_place(self, backend_world: World) -> None:
        payload = channel_payload(
            backend_world, int(backend_world.channel.id), name="renamed"
        )
        channel = self.run_channel(
            backend_world, int(backend_world.channel.id), payload
        )
        assert isinstance(channel, TextChannel)
        assert channel.id == backend_world.channel.id
        assert channel.name == "renamed"
        assert channel.guild_id == backend_world.guild.id
        if is_memory(backend_world):
            assert channel is backend_world.channel
            assert backend_world.channel.name == "renamed"

    def test_cached_channel_keeps_what_the_payload_lacks(
        self, backend_world: World
    ) -> None:
        backend_world.channel.topic = "kept"
        payload = {
            "id": str(backend_world.channel.id),
            "type": 0,
            "name": "renamed",
            "guild_id": str(backend_world.guild.id),
        }
        channel = self.run_channel(
            backend_world, int(backend_world.channel.id), payload
        )
        assert channel.name == "renamed"
        if is_memory(backend_world):
            assert channel.topic == "kept"

    def test_uncached_channel_is_built(self, backend_world: World) -> None:
        payload = channel_payload(backend_world, OTHER_CHANNEL_ID, name="fresh")
        channel = self.run_channel(backend_world, OTHER_CHANNEL_ID, payload)
        assert isinstance(channel, TextChannel)
        assert channel.id == OTHER_CHANNEL_ID
        assert channel.name == "fresh"
        assert channel.guild_id == backend_world.guild.id

    def test_cached_thread_fills_the_missing_fields(self, backend_world: World) -> None:
        cached = add_thread(backend_world)
        cached.message_count = 12
        backend_world.run(
            backend_world.state._guild_bucket("threads", backend_world.guild.id).set(
                cached.id, cached
            )
        )
        payload = thread_payload(backend_world, name="renamed")
        for key in ("owner_id", "message_count", "member_count"):
            payload.pop(key, None)
        thread = self.run_channel(backend_world, THREAD_ID, payload)
        assert isinstance(thread, Thread)
        assert thread.id == THREAD_ID
        assert thread.name == "renamed"
        assert thread.owner_id == MEMBER_ID
        assert thread.message_count == 12

    def test_uncached_thread_is_built(self, backend_world: World) -> None:
        payload = thread_payload(backend_world, name="fresh")
        thread = self.run_channel(backend_world, THREAD_ID, payload)
        assert isinstance(thread, Thread)
        assert thread.name == "fresh"
        assert thread.guild_id == backend_world.guild.id


class TestAttachment:
    def test_attachment(self, backend_world: World) -> None:
        payload = backend_world.payload(
            t.message.Attachment, id=str(OTHER_ID), filename="a.png"
        )
        _, kwargs = run(
            backend_world,
            [
                {
                    **option_value("a", OTHER_ID, OptionType.attachment),
                    "input_type": discord.Attachment,
                }
            ],
            {"attachments": {str(OTHER_ID): payload}},
        )
        assert isinstance(kwargs["a"], discord.Attachment)
        assert kwargs["a"].filename == "a.png"


def context_command(
    kind: type[discord.UserCommand | discord.MessageCommand],
) -> tuple[Any, list[Any]]:
    seen: list[Any] = []

    async def callback(_ctx: Any, target: Any) -> None:
        seen.append(target)

    return kind(callback, name="cmd"), seen


class TestUserCommand:
    def data(self, world: World, user_id: int, *, member: bool) -> dict[str, Any]:
        members, users = user_resolved(world, user_id)
        resolved: dict[str, Any] = {"users": users}
        if member:
            resolved["members"] = members
        return {
            "id": "1",
            "name": "cmd",
            "type": 2,
            "target_id": str(user_id),
            "resolved": resolved,
        }

    def test_member_target(self, backend_world: World) -> None:
        cached = add_member(backend_world, OTHER_ID)
        command, seen = context_command(discord.UserCommand)
        ctx = make_context(
            backend_world,
            interaction_payload(
                backend_world, data=self.data(backend_world, OTHER_ID, member=True)
            ),
        )
        backend_world.run(command._invoke(ctx))
        (target,) = seen
        assert isinstance(target, discord.Member)
        assert target.id == OTHER_ID
        if is_memory(backend_world):
            assert target is cached

    def test_user_target(self, backend_world: World) -> None:
        command, seen = context_command(discord.UserCommand)
        ctx = make_context(
            backend_world,
            interaction_payload(
                backend_world, data=self.data(backend_world, OTHER_ID, member=False)
            ),
        )
        backend_world.run(command._invoke(ctx))
        (target,) = seen
        assert type(target) is discord.User
        assert target.id == OTHER_ID


class TestMessageCommand:
    def test_message_target_is_populated(self, backend_world: World) -> None:
        cached = add_member(backend_world, OTHER_ID)
        message = backend_world.payload(
            t.message.Message,
            id="7790",
            type=0,
            mentions=[],
            mention_roles=[],
            reactions=[],
            guild_id=str(backend_world.guild.id),
            channel_id=str(backend_world.channel.id),
            author={**backend_world.payload(t.user.User), "id": str(OTHER_ID)},
        )
        for key in (
            "message_reference",
            "referenced_message",
            "message_snapshots",
            "poll",
            "thread",
            "call",
            "interaction",
            "interaction_metadata",
            "member",
        ):
            message.pop(key, None)
        command, seen = context_command(discord.MessageCommand)
        data = {
            "id": "1",
            "name": "cmd",
            "type": 3,
            "target_id": "7790",
            "resolved": {"messages": {"7790": message}},
        }
        ctx = make_context(backend_world, interaction_payload(backend_world, data=data))
        backend_world.run(command._invoke(ctx))
        (target,) = seen
        assert isinstance(target, Message)
        assert target.id == 7790
        assert target.channel.id == backend_world.channel.id
        assert target.author.id == OTHER_ID
        if is_memory(backend_world):
            assert target.author is cached

    def test_message_in_another_channel(self, backend_world: World) -> None:
        message = backend_world.payload(
            t.message.Message,
            id="7791",
            type=0,
            mentions=[],
            mention_roles=[],
            reactions=[],
            guild_id=str(backend_world.guild.id),
            channel_id=str(OTHER_CHANNEL_ID),
        )
        for key in (
            "message_reference",
            "referenced_message",
            "message_snapshots",
            "poll",
            "thread",
            "call",
            "interaction",
            "interaction_metadata",
            "member",
        ):
            message.pop(key, None)
        command, seen = context_command(discord.MessageCommand)
        data = {
            "id": "1",
            "name": "cmd",
            "type": 3,
            "target_id": "7791",
            "resolved": {"messages": {"7791": message}},
        }
        ctx = make_context(backend_world, interaction_payload(backend_world, data=data))
        backend_world.run(command._invoke(ctx))
        (target,) = seen
        assert target.channel.id == OTHER_CHANNEL_ID
