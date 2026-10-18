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

from typing import TYPE_CHECKING, Any, TypeVar

import discord
from discord import types as t
from discord.channel import (
    CategoryChannel,
    ForumChannel,
    PartialMessageable,
    StageChannel,
    TextChannel,
    VoiceChannel,
)
from discord.enums import ChannelType
from discord.ext import commands
from discord.ext.commands.view import StringView
from discord.message import Message
from discord.permissions import Permissions
from discord.threads import Thread

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from discord.guild import Guild
    from tests.models.context import World

T = TypeVar("T")

MESSAGE_ID = 1500000000000000001
DM_CHANNEL_ID = 1700000000000000001
FIRST_USER = 1300000000000000001


PLAIN_MESSAGE_KEYS = (
    "member",
    "mention_channels",
    "reactions",
    "activity",
    "application",
    "message_reference",
    "interaction",
    "interaction_metadata",
    "components",
    "thread",
    "poll",
    "call",
    "message_snapshots",
    "referenced_message",
    "sticker_items",
)


class Server:
    def __init__(self, bot: commands.Bot, world: World) -> None:
        self.bot = bot
        self.world = world
        self.state = world.state
        self.guild: Guild = world.guild
        self.next_id = 1400000000000000000
        self.everyone = self.add_role(self.guild.id, "@everyone", position=0)
        self.me = self.add_member(
            world.me.id, name="botuser", roles=[], global_name="Bot"
        )

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        return self.world.run(coro)

    def new_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def add_role(
        self,
        role_id: int | None,
        name: str,
        *,
        position: int = 1,
        permissions: Permissions | None = None,
    ) -> discord.Role:
        role_id = role_id or self.new_id()
        payload = self.world.payload(
            t.role.Role,
            id=str(role_id),
            name=name,
            position=position,
            permissions=str((permissions or Permissions.none()).value),
            managed=False,
        )
        payload.pop("tags", None)
        role = discord.Role(guild=self.guild, state=self.state, data=payload)
        self.run(self.state._guild_bucket("roles", self.guild.id).set(role.id, role))
        return role

    def user_payload(
        self,
        user_id: int,
        name: str,
        *,
        global_name: str | None = None,
        discriminator: str = "0",
    ) -> dict[str, Any]:
        return {
            **self.world.payload(t.user.User),
            "id": str(user_id),
            "username": name,
            "global_name": global_name,
            "discriminator": discriminator,
            "bot": False,
        }

    def add_user(
        self,
        user_id: int,
        name: str,
        *,
        global_name: str | None = None,
        discriminator: str = "0",
    ) -> discord.User:
        payload = self.user_payload(
            user_id, name, global_name=global_name, discriminator=discriminator
        )
        user = self.run(self.state.store_user(payload))
        self.run(self.state._users.set(user.id, user))
        return user

    def build_member(
        self,
        user_id: int,
        *,
        name: str,
        nick: str | None = None,
        global_name: str | None = None,
        discriminator: str = "0",
        roles: list[int] | None = None,
    ) -> discord.Member:
        payload = self.world.payload(
            t.member.MemberWithUser,
            roles=[str(r) for r in roles or []],
            nick=nick,
            user=self.user_payload(
                user_id, name, global_name=global_name, discriminator=discriminator
            ),
        )
        payload.pop("communication_disabled_until", None)
        payload["premium_since"] = None
        return discord.Member(data=payload, guild=self.guild, state=self.state)

    def add_member(
        self,
        user_id: int,
        *,
        name: str,
        nick: str | None = None,
        global_name: str | None = None,
        discriminator: str = "0",
        roles: list[int] | None = None,
    ) -> discord.Member:
        member = self.build_member(
            user_id,
            name=name,
            nick=nick,
            global_name=global_name,
            discriminator=discriminator,
            roles=roles,
        )
        self.run(self.guild._add_member(member))
        return member

    def add_channel(self, cls: Any, tp: Any, name: str, **fields: Any) -> Any:
        channel_id = fields.pop("id", None) or self.new_id()
        fields = {"parent_id": None, "permission_overwrites": [], **fields}
        payload = self.world.payload(
            tp,
            id=str(channel_id),
            guild_id=str(self.guild.id),
            name=name,
            **fields,
        )
        channel = cls(state=self.state, guild=self.guild, data=payload)
        self.run(self.guild._add_channel(channel))
        return channel

    def add_text(self, name: str, **fields: Any) -> TextChannel:
        return self.add_channel(TextChannel, t.channel.TextChannel, name, **fields)

    def add_voice(self, name: str, **fields: Any) -> VoiceChannel:
        return self.add_channel(VoiceChannel, t.channel.VoiceChannel, name, **fields)

    def add_stage(self, name: str, **fields: Any) -> StageChannel:
        return self.add_channel(StageChannel, t.channel.StageChannel, name, **fields)

    def add_category(self, name: str, **fields: Any) -> CategoryChannel:
        return self.add_channel(
            CategoryChannel, t.channel.CategoryChannel, name, **fields
        )

    def add_forum(self, name: str, **fields: Any) -> ForumChannel:
        return self.add_channel(ForumChannel, t.channel.ForumChannel, name, **fields)

    def add_thread(self, name: str, parent: TextChannel) -> Thread:
        payload = self.world.payload(
            t.threads.Thread,
            id=str(self.new_id()),
            guild_id=str(self.guild.id),
            parent_id=str(parent.id),
            name=name,
        )
        payload.pop("member", None)
        thread = Thread(guild=self.guild, state=self.state, data=payload)
        self.run(self.guild._add_thread(thread))
        return thread

    def add_emoji(self, name: str, guild: Guild | None = None) -> discord.GuildEmoji:
        payload = self.world.payload(
            t.emoji.Emoji,
            id=str(self.new_id()),
            name=name,
            roles=[],
            available=True,
        )
        return self.run(self.state.store_emoji(guild or self.guild, payload))

    def add_sticker(
        self, name: str, guild: Guild | None = None
    ) -> discord.GuildSticker:
        payload = self.world.payload(
            t.sticker.GuildSticker,
            id=str(self.new_id()),
            name=name,
            guild_id=str((guild or self.guild).id),
        )
        return self.run(self.state.store_sticker(guild or self.guild, payload))

    def add_message(self, channel: Any, content: str = "") -> Message:
        payload = self.world.payload(
            t.message.Message,
            id=str(self.new_id()),
            channel_id=str(channel.id),
            guild_id=str(self.guild.id),
            content=content,
        )
        for key in PLAIN_MESSAGE_KEYS:
            payload.pop(key, None)
        message = Message(state=self.state, channel=channel, data=payload)
        self.run(self.state._store_message(message))
        return message

    def message(
        self,
        content: str = "",
        *,
        author: discord.Member | discord.User | None = None,
        channel: Any = None,
        in_guild: bool = True,
        mentions: list[discord.User] | None = None,
    ) -> Message:
        author = author or self.me
        if channel is None:
            channel = (
                self.world.channel
                if in_guild
                else PartialMessageable(
                    state=self.state, id=DM_CHANNEL_ID, type=ChannelType.private
                )
            )
        payload = self.world.payload(
            t.message.Message,
            id=str(MESSAGE_ID),
            channel_id=str(channel.id),
            content=content,
            author=self.user_payload(author.id, author.name),
            mentions=[
                self.user_payload(user.id, user.name, global_name=user.global_name)
                for user in mentions or []
            ],
            mention_roles=[],
        )
        payload["member"] = dict(self.world.payload(t.member.Member))
        payload["member"]["roles"] = [
            str(role_id) for role_id in getattr(author, "_roles", [])
        ]
        payload["member"]["premium_since"] = None
        payload["member"].pop("communication_disabled_until", None)
        if in_guild:
            payload["guild_id"] = str(self.guild.id)
        else:
            payload.pop("guild_id", None)
            payload.pop("member", None)
        return Message(state=self.state, channel=channel, data=payload)

    def context(self, content: str = "", **kwargs: Any) -> commands.Context:
        message = self.message(content, **kwargs)
        return commands.Context(
            message=message, bot=self.bot, view=StringView(content), prefix="!"
        )
