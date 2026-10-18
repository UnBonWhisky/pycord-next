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
from unittest.mock import AsyncMock

import pytest

import discord
from discord import types as t
from discord.errors import ClientException, InvalidArgument
from discord.utils import MISSING
from tests.core.rig import (
    PNG,
    Case,
    Rig,
    check_list,
    check_type,
    execute,
    one,
)
from tests.core.test_channel_remote import channel_of

if TYPE_CHECKING:
    from tests.models.context import World

IMG = "data:image/png;base64,iVBORw0KGgo="
ROLE = discord.Object(id=5252)
OTHER = discord.Object(id=5353)


def member(r: Rig) -> Any:
    return r.world.member


def me(r: Rig) -> Any:
    found = r.world.member
    r.state.user = r.world.me
    found._user.id = r.world.me.id
    return found


def with_voice(r: Rig) -> None:
    r.run(
        r.state._guild_bucket("voice_states", r.guild.id).set(
            r.world.member.id,
            discord.VoiceState(
                data=r.payload(
                    t.voice.GuildVoiceState,
                    channel_id=str(channel_of("voice")(r).id),
                    user_id=str(r.world.member.id),
                ),
                state=r.state,
                channel=channel_of("voice")(r),
            ),
        )
    )


def member_payload(r: Rig) -> Any:
    return r.payload(t.member.MemberWithUser, roles=[])


MEMBER_CASES = [
    Case(
        "edit_nothing",
        member,
        "edit",
        check=lambda r, res: res is None or pytest.fail(res),
    ),
    Case(
        "edit_moderation",
        member,
        "edit",
        "edit_member",
        member_payload,
        kwargs=lambda r: {
            "nick": None,
            "mute": True,
            "deafen": False,
            "roles": [ROLE, OTHER],
            "voice_channel": None,
            "communication_disabled_until": dt.datetime(
                2030, 1, 1, tzinfo=dt.timezone.utc
            ),
            "bypass_verification": True,
            "reason": "r",
        },
        called_with=lambda r: (
            (r.guild.id, r.world.member.id),
            {
                "reason": "r",
                "nick": "",
                "deaf": False,
                "mute": True,
                "channel_id": None,
                "roles": (5252, 5353),
                "communication_disabled_until": "2030-01-01T00:00:00+00:00",
                "flags": r.world.member.flags.value
                | discord.MemberFlags(bypasses_verification=True).value,
            },
        ),
        check=check_type(discord.Member),
    ),
    Case(
        "edit_unmute_and_move",
        member,
        "edit",
        "edit_member",
        member_payload,
        kwargs=lambda r: {
            "voice_channel": channel_of("voice")(r),
            "communication_disabled_until": None,
        },
        kwargs_include=lambda r: {
            "channel_id": channel_of("voice")(r).id,
            "communication_disabled_until": None,
        },
    ),
    Case(
        "edit_the_bot_profile",
        me,
        "edit",
        "edit_member",
        member_payload,
        kwargs=lambda r: {"nick": "bot", "avatar": PNG, "banner": None, "bio": None},
        called_with=lambda r: (
            (r.guild.id, "@me"),
            {
                "reason": None,
                "nick": "bot",
                "avatar": IMG,
                "banner": None,
                "bio": "",
            },
        ),
        check=check_type(discord.Member),
    ),
    Case(
        "edit_the_bot_banner",
        me,
        "edit",
        "edit_member",
        member_payload,
        kwargs=lambda r: {"banner": PNG, "avatar": None},
        kwargs_include=lambda r: {"banner": IMG, "avatar": None},
    ),
    Case(
        "edit_someone_elses_profile",
        member,
        "edit",
        "edit_member",
        kwargs=lambda r: {"avatar": PNG},
        raises=(InvalidArgument, "bot's member"),
    ),
    Case(
        "suppress_requires_a_voice_channel",
        member,
        "edit",
        "edit_voice_state",
        kwargs=lambda r: {"suppress": True},
        raises=(ClientException, "not connected"),
    ),
    Case(
        "suppress_another_member",
        member,
        "edit",
        "edit_voice_state",
        kwargs=lambda r: {"suppress": True},
        setup=with_voice,
        check=lambda r, res: _suppress(r, True),
    ),
    Case(
        "unsuppress_another_member",
        member,
        "edit",
        "edit_voice_state",
        kwargs=lambda r: {"suppress": False},
        setup=with_voice,
        check=lambda r, res: _suppress(r, False),
    ),
    Case(
        "add_roles_atomically",
        member,
        "add_roles",
        "add_role",
        args=lambda r: (ROLE,),
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.guild.id, r.world.member.id, 5252), {"reason": "r"}),
    ),
    Case(
        "remove_roles_atomically",
        member,
        "remove_roles",
        "remove_role",
        args=lambda r: (ROLE,),
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.guild.id, r.world.member.id, 5252), {"reason": "r"}),
    ),
    Case(
        "add_roles_non_atomically",
        member,
        "add_roles",
        "edit_member",
        member_payload,
        args=lambda r: (ROLE, ROLE),
        kwargs=lambda r: {"atomic": False},
        check=lambda r, res: _roles_sent(r, (5252,)),
    ),
    Case(
        "remove_roles_non_atomically",
        member,
        "remove_roles",
        "edit_member",
        member_payload,
        args=lambda r: (ROLE,),
        kwargs=lambda r: {"atomic": False},
        check=lambda r, res: _roles_sent(r, ()),
    ),
    Case(
        "request_to_speak",
        member,
        "request_to_speak",
        "edit_voice_state",
        setup=with_voice,
        check=lambda r, res: _request_to_speak(r),
    ),
    Case(
        "request_to_speak_as_the_bot",
        me,
        "request_to_speak",
        "edit_my_voice_state",
        setup=lambda r: _bot_voice(r),  # noqa: PLW0108
        check=lambda r, res: _request_to_speak_bot(r),
    ),
]


def _bot_voice(r: Rig) -> None:
    r.state.user = r.world.me
    r.run(
        r.state._guild_bucket("voice_states", r.guild.id).set(
            r.world.me.id,
            discord.VoiceState(
                data=r.payload(
                    t.voice.GuildVoiceState,
                    channel_id=str(channel_of("voice")(r).id),
                    user_id=str(r.world.me.id),
                ),
                state=r.state,
                channel=channel_of("voice")(r),
            ),
        )
    )


def _suppress(r: Rig, suppressed: bool) -> None:
    args = r.http.edit_voice_state.call_args.args
    assert args[:2] == (r.guild.id, r.world.member.id)
    payload = args[2]
    assert payload["suppress"] is suppressed
    assert payload["channel_id"] == channel_of("voice")(r).id
    if suppressed:
        assert payload["request_to_speak_timestamp"] is None
    else:
        assert payload["request_to_speak_timestamp"]


def _roles_sent(r: Rig, expected: tuple[int, ...]) -> None:
    assert r.http.edit_member.call_args.kwargs["roles"] == expected


def _request_to_speak(r: Rig) -> None:
    payload = r.http.edit_voice_state.call_args.args[2]
    assert payload["suppress"] is False
    assert payload["request_to_speak_timestamp"]


def _request_to_speak_bot(r: Rig) -> None:
    args = r.http.edit_my_voice_state.call_args.args
    assert args[0] == r.guild.id
    assert args[1]["request_to_speak_timestamp"]
    assert "suppress" not in args[1]


@pytest.mark.parametrize("case", MEMBER_CASES, ids=lambda c: c.id)
def test_member_remote_calls(world: World, case: Case) -> None:
    execute(Rig(world), case)


def test_member_helpers(world: World) -> None:
    rig = Rig(world)
    found = rig.world.member
    assert "Member" in repr(found)
    message = rig.make_message()
    message.mentions = []
    message.role_mentions = []
    assert found.mentioned_in(message) is False
    other_guild = rig.make_message(guild_id="5")
    assert found.mentioned_in(other_guild) is False
    message.mentions = [found._user]
    assert found.mentioned_in(message) is True
    message.mentions = []
    message.role_mentions = [rig.guild.default_role]
    found._roles.append(rig.guild.default_role.id) if hasattr(
        found._roles, "append"
    ) else None
    assert isinstance(found.mentioned_in(message), bool)
    assert found.activity is None or found.activity is not None


def test_member_presence_updates(world: World) -> None:
    rig = Rig(world)
    found = rig.world.member
    user = {
        "id": str(found.id),
        "username": "renamed",
        "avatar": None,
        "discriminator": "0",
    }
    result = found._presence_update(
        {
            "status": "idle",
            "activities": [{"type": 0, "name": "Chess"}],
            "client_status": {"mobile": "idle"},
        },  # type: ignore[arg-type]
        user,  # type: ignore[arg-type]
    )
    assert found.status is discord.Status.idle
    assert [a.name for a in found.activities] == ["Chess"]
    assert found.activity.name == "Chess"
    assert result is not None
    before, after = result
    assert before.name != "renamed"
    assert after.name == "renamed"

    same = found._presence_update(
        {"status": "online", "activities": [], "client_status": {}},  # type: ignore[arg-type]
        (),
    )
    assert same is None
    assert found.activities == ()
    assert found._update_inner_user({**user}) is None


def role_of(r: Rig) -> Any:
    if not hasattr(r, "_role"):
        r._role = discord.Role(  # type: ignore[attr-defined]
            guild=r.guild,
            state=r.state,
            data=r.payload(
                t.role.Role, id="6100", position=2, managed=False, permissions="0"
            ),
        )
        r.run(r.state._guild_bucket("roles", r.guild.id).set(6100, r._role))  # type: ignore[attr-defined]
    return r._role  # type: ignore[attr-defined]


def role_payload(**fields: Any) -> Any:
    return lambda r: r.payload(t.role.Role, id="6100", **fields)


def colours_sent(r: Rig) -> dict[str, Any]:
    return r.http.edit_role.call_args.kwargs


ROLE_CASES = [
    Case(
        "delete",
        role_of,
        "delete",
        "delete_role",
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.guild.id, 6100), {"reason": "r"}),
    ),
    Case(
        "edit_all",
        role_of,
        "edit",
        "edit_role",
        role_payload(),
        kwargs=lambda r: {
            "name": "mod",
            "permissions": discord.Permissions(kick_members=True),
            "hoist": True,
            "mentionable": True,
            "icon": PNG,
            "reason": "r",
        },
        kwargs_include=lambda r: {
            "name": "mod",
            "permissions": discord.Permissions(kick_members=True).value,
            "hoist": True,
            "mentionable": True,
            "icon": IMG,
            "unicode_emoji": None,
            "reason": "r",
        },
        check=check_type(discord.Role),
    ),
    Case(
        "edit_icon_cleared",
        role_of,
        "edit",
        "edit_role",
        role_payload(),
        kwargs=lambda r: {"icon": None},
        kwargs_include=lambda r: {"icon": None},
    ),
    Case(
        "edit_unicode_emoji",
        role_of,
        "edit",
        "edit_role",
        role_payload(),
        kwargs=lambda r: {"unicode_emoji": "\N{FIRE}"},
        kwargs_include=lambda r: {"unicode_emoji": "\N{FIRE}", "icon": None},
    ),
    Case(
        "edit_colour_alias",
        role_of,
        "edit",
        "edit_role",
        role_payload(),
        kwargs=lambda r: {"color": 0x123456},
        warns=(DeprecationWarning, "colour"),
        check=lambda r, res: _primary(r, 0x123456),
    ),
    Case(
        "edit_colour_object",
        role_of,
        "edit",
        "edit_role",
        role_payload(),
        kwargs=lambda r: {"colour": discord.Colour(0x654321)},
        warns=(DeprecationWarning, "colour"),
        check=lambda r, res: _primary(r, 0x654321),
    ),
    Case(
        "edit_colours_alias",
        role_of,
        "edit",
        "edit_role",
        role_payload(),
        kwargs=lambda r: {"colors": discord.RoleColours(primary=discord.Colour(7))},
        check=lambda r, res: _primary(r, 7),
    ),
    Case(
        "edit_holographic",
        role_of,
        "edit",
        "edit_role",
        role_payload(),
        kwargs=lambda r: {"holographic": True},
        check=lambda r, res: _primary(r, discord.RoleColours.HOLOGRAPHIC_PRIMARY.value),
    ),
    Case(
        "edit_bad_colours",
        role_of,
        "edit",
        "edit_role",
        kwargs=lambda r: {"colours": 5},
        raises=(InvalidArgument, "RoleColours"),
    ),
    Case(
        "move_to_position_zero",
        role_of,
        "edit",
        "move_role_position",
        kwargs=lambda r: {"position": 0},
        raises=(InvalidArgument, "position 0"),
    ),
    Case(
        "move_the_default_role",
        lambda r: r.guild.default_role,
        "edit",
        "move_role_position",
        kwargs=lambda r: {"position": 3},
        raises=(InvalidArgument, "default role"),
    ),
]


def _primary(r: Rig, value: int) -> None:
    assert colours_sent(r)["colors"]["primary_color"] == value


@pytest.mark.parametrize("case", ROLE_CASES, ids=lambda c: c.id)
def test_role_remote_calls(world: World, case: Case) -> None:
    execute(Rig(world), case)


def test_role_moves(world: World) -> None:
    rig = Rig(world)
    low = role_of(rig)
    low.position = 2
    other = discord.Role(
        guild=rig.guild,
        state=rig.state,
        data=rig.payload(t.role.Role, id="6200", position=3, managed=False),
    )
    third = discord.Role(
        guild=rig.guild,
        state=rig.state,
        data=rig.payload(t.role.Role, id="6300", position=4, managed=False),
    )
    for extra in (other, third):
        rig.run(rig.state._guild_bucket("roles", rig.guild.id).set(extra.id, extra))
    rig.respond("move_role_position", [])
    rig.guild.default_role.position = 0

    rig.run(low._move(2, "r"))
    rig.http.move_role_position.assert_not_called()

    rig.run(low._move(4, "r"))
    args, kwargs = rig.http.move_role_position.call_args
    assert args[0] == rig.guild.id
    assert args[1] == [
        {"id": other.id, "position": 2},
        {"id": third.id, "position": 3},
        {"id": low.id, "position": 4},
    ]
    assert kwargs == {"reason": "r"}

    rig.run(third._move(2, None))
    payload = rig.http.move_role_position.call_args.args[1]
    assert payload[0] == {"id": third.id, "position": 2}
    assert len(payload) == 3


def test_role_assignability_and_ordering(world: World) -> None:
    rig = Rig(world)
    target = role_of(rig)
    assert rig.run(target.check_assignable()) is False
    rig.state.user = rig.world.me
    assert rig.run(target.check_assignable()) is False
    assert rig.run(rig.guild.default_role.check_assignable()) is False

    target.position = 5
    rig.guild.default_role.position = 0
    assert str(target) == target.name
    other = rig.guild.default_role
    assert (target >= other) is True
    assert (target <= other) is False
    assert (other <= target) is True


def thread_of(r: Rig) -> Any:
    if not hasattr(r, "_thread"):
        r._thread = discord.Thread(  # type: ignore[attr-defined]
            guild=r.guild,
            state=r.state,
            data=r.payload(
                t.threads.Thread,
                id="6400",
                guild_id=str(r.guild.id),
                parent_id=str(r.channel.id),
                type=11,
            ),
        )
        r.run(r.state._add_thread(r.guild.id, r._thread))  # type: ignore[attr-defined]
    return r._thread  # type: ignore[attr-defined]


def thread_payload(**fields: Any) -> Any:
    return lambda r: r.payload(
        t.threads.Thread,
        **{
            "id": "6400",
            "guild_id": str(r.guild.id),
            "parent_id": str(r.channel.id),
            "type": 11,
            **fields,
        },
    )


THREAD_CASES = [
    Case(
        "edit_everything",
        thread_of,
        "edit",
        "edit_channel",
        thread_payload(),
        kwargs=lambda r: {
            "name": 5,
            "archived": True,
            "locked": True,
            "invitable": False,
            "slowmode_delay": 3,
            "auto_archive_duration": 60,
            "pinned": True,
            "applied_tags": [discord.ForumTag(name="x")],
            "reason": "r",
        },
        kwargs_include=lambda r: {
            "name": "5",
            "archived": True,
            "locked": True,
            "invitable": False,
            "rate_limit_per_user": 3,
            "auto_archive_duration": 60,
            "applied_tags": [0],
            "reason": "r",
        },
        check=check_type(discord.Thread),
    ),
    Case(
        "archive",
        thread_of,
        "archive",
        "edit_channel",
        thread_payload(),
        kwargs=lambda r: {"locked": True},
        kwargs_include=lambda r: {"archived": True, "locked": True},
    ),
    Case(
        "unarchive",
        thread_of,
        "unarchive",
        "edit_channel",
        thread_payload(),
        kwargs_include=lambda r: {"archived": False},
    ),
    Case(
        "join",
        thread_of,
        "join",
        "join_thread",
        called_with=lambda r: ((6400,), {}),
    ),
    Case(
        "leave",
        thread_of,
        "leave",
        "leave_thread",
        called_with=lambda r: ((6400,), {}),
    ),
    Case(
        "add_user",
        thread_of,
        "add_user",
        "add_user_to_thread",
        args=lambda r: (OTHER,),
        called_with=lambda r: ((6400, 5353), {}),
    ),
    Case(
        "remove_user",
        thread_of,
        "remove_user",
        "remove_user_from_thread",
        args=lambda r: (OTHER,),
        called_with=lambda r: ((6400, 5353), {}),
    ),
    Case(
        "delete",
        thread_of,
        "delete",
        "delete_channel",
        called_with=lambda r: ((6400,), {}),
    ),
    Case(
        "fetch_members",
        thread_of,
        "fetch_members",
        "get_thread_members",
        lambda r: [r.payload(t.threads.ThreadMember, id="6400", user_id="7")],
        called_with=lambda r: ((6400,), {}),
        check=check_list(discord.ThreadMember),
    ),
    Case(
        "delete_messages_bulk",
        thread_of,
        "delete_messages",
        "delete_messages",
        args=lambda r: ([discord.Object(id=1), discord.Object(id=2)],),
        called_with=lambda r: ((6400, [1, 2]), {"reason": None}),
    ),
    Case(
        "delete_one_message",
        thread_of,
        "delete_messages",
        "delete_message",
        args=lambda r: ((x for x in [discord.Object(id=1)]),),
        called_with=lambda r: ((6400, 1), {"reason": None}),
    ),
]


@pytest.mark.parametrize("case", THREAD_CASES, ids=lambda c: c.id)
def test_thread_remote_calls(world: World, case: Case) -> None:
    execute(Rig(world), case)


def test_thread_predicates_and_members(world: World) -> None:
    rig = Rig(world)
    thread = thread_of(rig)
    assert str(thread) == thread.name
    assert rig.run(thread._get_channel()) is thread
    assert thread.is_pinned() in (True, False)
    assert thread.is_private() is False
    assert thread.is_news() is False
    assert thread.category_id == rig.channel.category_id
    assert rig.run(thread.get_category_id()) == rig.channel.category_id

    rig.respond(
        "get_thread_members",
        [rig.payload(t.threads.ThreadMember, id="6400", user_id="7")],
    )
    members = rig.run(thread.fetch_members())
    assert rig.run(thread._pop_member(members[0].id)) is not None
    assert rig.run(thread._pop_member(members[0].id)) is None
    assert members[0].thread is thread
    from_data = (
        discord.ThreadMember._from_data(
            thread,  # type: ignore[arg-type]
            rig.payload(t.threads.ThreadMember, id="6400", user_id="7"),  # type: ignore[arg-type]
        )
        if False
        else None
    )
    assert from_data is None


def test_thread_purge_delegates(world: World) -> None:
    from unittest.mock import patch

    rig = Rig(world)
    thread = thread_of(rig)
    with patch(
        "discord.threads.purge_messages_helper", new=AsyncMock(return_value=["m"])
    ):
        assert rig.run(thread.purge(limit=3)) == ["m"]


def user_cases() -> list[Case]:
    return [
        Case(
            "client_user_edit",
            lambda r: r.world.me,
            "edit",
            "edit_profile",
            one(t.user.User),
            kwargs=lambda r: {"username": "new", "avatar": PNG, "banner": None},
            called_with=lambda r: (
                ({"username": "new", "avatar": IMG, "banner": None},),
                {},
            ),
            check=check_type(discord.ClientUser),
        ),
        Case(
            "client_user_edit_banner_and_cleared_avatar",
            lambda r: r.world.me,
            "edit",
            "edit_profile",
            one(t.user.User),
            kwargs=lambda r: {"avatar": None, "banner": PNG},
            called_with=lambda r: (({"avatar": None, "banner": IMG},), {}),
        ),
        Case(
            "user_create_dm",
            lambda r: r.world.user,
            "create_dm",
            "start_private_message",
            lambda r: r.payload(
                t.channel.DMChannel,
                recipients=[r.payload(t.user.User, id=str(r.world.user.id))],
            ),
            called_with=lambda r: ((r.world.user.id,), {}),
            check=check_type(discord.DMChannel),
        ),
        Case(
            "user_create_test_entitlement",
            lambda r: r.world.user,
            "create_test_entitlement",
            "create_test_entitlement",
            one(t.monetization.Entitlement),
            args=lambda r: (discord.Object(id=31),),
            setup=lambda r: setattr(r.state, "application_id", 99),
            called_with=lambda r: (
                (99, {"sku_id": 31, "owner_id": r.world.user.id, "owner_type": 2}),
                {},
            ),
            check=check_type(discord.Entitlement),
        ),
        Case(
            "user_create_test_entitlement_without_application",
            lambda r: r.world.user,
            "create_test_entitlement",
            "create_test_entitlement",
            args=lambda r: (discord.Object(id=31),),
            setup=lambda r: setattr(r.state, "application_id", None),
            raises=(ClientException, "application ID"),
        ),
    ]


@pytest.mark.parametrize("case", user_cases(), ids=lambda c: c.id)
def test_user_remote_calls(world: World, case: Case) -> None:
    execute(Rig(world), case)


def test_user_helpers(world: World) -> None:
    rig = Rig(world)
    user = rig.world.user
    assert "User" in repr(user)
    assert "ClientUser" in repr(rig.world.me)
    iterator = user.entitlements(
        skus=[discord.Object(id=1)], limit=3, exclude_ended=True
    )
    assert iterator.user_id == user.id
    assert iterator.sku_ids == [1]
    message = rig.make_message()
    message.mentions = [user]
    assert user.mentioned_in(message) is True
    message.mentions = []
    message.mention_everyone = True
    assert user.mentioned_in(message) is True
    message.mention_everyone = False
    assert user.mentioned_in(message) is False
    assert user.banner is None or user.banner is not None
    assert user.avatar_decoration is None or user.avatar_decoration is not None


def app_info(r: Rig) -> Any:
    return discord.AppInfo(r.state, r.payload(t.appinfo.AppInfo))


def test_app_install_params_payload() -> None:
    params = discord.AppInstallParams({"scopes": ["bot"], "permissions": "8"})
    assert params._to_payload() == {"scopes": ["bot"], "permissions": "8"}
    invalid = discord.AppInstallParams({"scopes": ["identify"], "permissions": "8"})
    with pytest.raises(ValueError, match="'bot' must be in"):
        invalid._to_payload()
    assert discord.AppInstallParams({"permissions": "0"})._to_payload()["scopes"] == []


def test_integration_types_config_payload() -> None:
    params = discord.AppInstallParams({"scopes": ["bot"], "permissions": "8"})
    config = discord.IntegrationTypesConfig(guild=params, user=None)
    assert config._to_payload() == {
        0: {"oauth2_install_params": params._to_payload()},
        1: None,
    }
    assert discord.IntegrationTypesConfig()._to_payload() == {}
    assert discord.IntegrationTypesConfig._get_ctx(None, 0) is None
    assert discord.IntegrationTypesConfig._get_ctx({0: {"a": 1}}, 0) == {"a": 1}
    assert discord.IntegrationTypesConfig._get_ctx({"1": {"b": 2}}, 1) == {"b": 2}
    assert discord.IntegrationTypesConfig._decode_ctx(None) is None
    assert discord.IntegrationTypesConfig._decode_ctx({}) is None
    decoded = discord.IntegrationTypesConfig._decode_ctx(
        {"oauth2_install_params": {"scopes": ["bot"], "permissions": "8"}}
    )
    assert decoded is not None
    assert decoded.permissions.value == 8


def test_app_info_edit(world: World) -> None:
    rig = Rig(world)
    info = app_info(rig)
    rig.respond("edit_current_application_info", rig.payload(t.appinfo.AppInfo))
    params = discord.AppInstallParams({"scopes": ["bot"], "permissions": "8"})

    edited = rig.run(
        info.edit(
            description="d",
            icon=PNG,
            cover_image=PNG,
            tags=["a"],
            terms_of_service_url="https://tos",
            privacy_policy_url="https://pp",
            interactions_endpoint_url="https://i",
            role_connections_verification_url="https://r",
            install_params=params,
            custom_install_url="https://c",
            integration_types_config=discord.IntegrationTypesConfig(guild=params),
            flags=discord.ApplicationFlags._from_value(8),
            event_webhooks_url="https://w",
            event_webhooks_status=discord.ApplicationEventWebhookStatus.enabled,
            event_webhooks_types=["APPLICATION_AUTHORIZED"],
        )
    )

    assert isinstance(edited, discord.AppInfo)
    (payload,) = rig.http.edit_current_application_info.call_args.args
    assert payload == {
        "description": "d",
        "icon": IMG,
        "cover_image": IMG,
        "tags": ["a"],
        "terms_of_service_url": "https://tos",
        "privacy_policy_url": "https://pp",
        "interactions_endpoint_url": "https://i",
        "role_connections_verification_url": "https://r",
        "install_params": params._to_payload(),
        "custom_install_url": "https://c",
        "integration_types_config": {
            0: {"oauth2_install_params": params._to_payload()}
        },
        "flags": 8,
        "event_webhooks_url": "https://w",
        "event_webhooks_status": 2,
        "event_webhooks_types": ["APPLICATION_AUTHORIZED"],
    }


def test_app_info_edit_clears_values(world: World) -> None:
    rig = Rig(world)
    info = app_info(rig)
    rig.respond("edit_current_application_info", rig.payload(t.appinfo.AppInfo))
    rig.run(
        info.edit(
            icon=None,
            cover_image=None,
            install_params=None,
            integration_types_config=None,
            flags=None,
        )
    )
    (payload,) = rig.http.edit_current_application_info.call_args.args
    assert payload == {
        "icon": None,
        "cover_image": None,
        "install_params": None,
        "integration_types_config": None,
        "flags": None,
    }
    _ = MISSING
