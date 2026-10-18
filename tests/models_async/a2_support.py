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

import datetime as dt
from typing import TYPE_CHECKING, Any

from discord import Member, Role, types as t
from discord.guild import Guild
from discord.permissions import Permissions

if TYPE_CHECKING:
    from tests.models.context import World

GUILD_ID = 7000
OWNER_ID = 7100


class Scene:
    def __init__(self, world: World, owner_id: int = OWNER_ID) -> None:
        self.world = world
        self.state = world.state
        payload = world.payload(t.guild.Guild, id=str(GUILD_ID), owner_id=str(owner_id))
        self.guild = Guild(data=payload, state=self.state)
        self.run(self.state._add_guild(self.guild))
        self.everyone = self.add_role(GUILD_ID, position=0)

    def run(self, coro: Any) -> Any:
        return self.world.run(coro)

    def add_role(
        self,
        role_id: int,
        *,
        position: int,
        permissions: Permissions | None = None,
        colour: int = 0,
    ) -> Role:
        payload = self.world.payload(
            t.role.Role,
            id=str(role_id),
            position=position,
            permissions=str((permissions or Permissions.none()).value),
            color=colour,
            managed=False,
            colors={
                "primary_color": colour,
                "secondary_color": None,
                "tertiary_color": None,
            },
        )
        payload.pop("tags", None)
        role = Role(guild=self.guild, state=self.state, data=payload)
        self.run(self.state._guild_bucket("roles", GUILD_ID).set(role.id, role))
        return role

    def add_member(
        self,
        user_id: int,
        roles: list[int] | None = None,
        *,
        timed_out_for: dt.timedelta | None = None,
    ) -> Member:
        payload = self.world.payload(
            t.member.MemberWithUser,
            roles=[str(r) for r in roles or []],
            user={**self.world.payload(t.user.User), "id": str(user_id)},
        )
        payload.pop("communication_disabled_until", None)
        if timed_out_for is not None:
            until = dt.datetime.now(dt.timezone.utc) + timed_out_for
            payload["communication_disabled_until"] = until.isoformat()
        member = Member(data=payload, guild=self.guild, state=self.state)
        self.run(self.guild._add_member(member))
        return member
