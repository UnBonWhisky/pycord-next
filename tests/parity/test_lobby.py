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

"""Lobby models and endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import Lobby, LobbyMemberFlags, LobbyMemberUpdate, Object

if TYPE_CHECKING:
    from discord.http import HTTPClient

LOBBY: dict[str, Any] = {
    "id": "96008815106887111",
    "application_id": "41771983429993937",
    "metadata": {"topic": "we need more redstone"},
    "members": [
        {
            "id": "41771983429993000",
            "metadata": None,
            "flags": 1,
            "additional_name": "Twindly Shimmerleaf",
        }
    ],
}


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.response: Any = None

    async def __call__(self, route: Any, **kwargs: Any) -> Any:
        self.calls.append((route.method, route.url.removeprefix(route.base), kwargs))
        return self.response


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def state(recorder: Recorder, http: HTTPClient) -> Any:
    http.request = recorder  # pyright: ignore[reportAttributeAccessIssue]
    return SimpleNamespace(
        http=http,
        get_user=lambda _: None,
        get_channel=lambda _: None,
    )


@pytest.fixture
def lobby(state: Any) -> Lobby:
    return Lobby(state=state, data=LOBBY)  # pyright: ignore[reportArgumentType]


def test_parse(lobby: Lobby) -> None:
    assert lobby.id == 96008815106887111
    assert lobby.application_id == 41771983429993937
    assert lobby.metadata == {"topic": "we need more redstone"}
    assert lobby.linked_channel_id is None
    assert lobby.linked_channel is None
    (member,) = lobby.members
    assert member.id == 41771983429993000
    assert member.lobby_id == lobby.id
    assert member.flags.can_link_lobby
    assert member.additional_name == "Twindly Shimmerleaf"
    assert lobby.get_member(member.id) is member
    assert lobby.get_member(1) is None


def test_linked_channel_id(state: Any) -> None:
    data = {**LOBBY, "linked_channel": {"id": "5", "name": "n", "type": 0}}
    assert Lobby(state=state, data=data).linked_channel_id == 5  # pyright: ignore[reportArgumentType]


def test_member_update_payload() -> None:
    update = LobbyMemberUpdate(
        Object(id=1),
        metadata={"a": "b"},
        flags=LobbyMemberFlags(can_link_lobby=True),
        additional_name=None,
    )
    assert update.to_dict() == {
        "id": "1",
        "metadata": {"a": "b"},
        "flags": 1,
        "additional_name": None,
    }
    assert LobbyMemberUpdate(Object(id=1)).to_dict() == {"id": "1"}
    assert LobbyMemberUpdate(Object(id=1), remove=True).to_dict() == {
        "id": "1",
        "remove_member": True,
    }


async def test_create_lobby(state: Any, recorder: Recorder) -> None:
    recorder.response = LOBBY
    client = discord.Client()
    client._connection = state
    client.http = state.http
    lobby = await client.create_lobby(
        metadata={"k": "v"},
        members=[LobbyMemberUpdate(Object(id=2), additional_name="x")],
        idle_timeout_seconds=60,
    )
    assert isinstance(lobby, Lobby)
    assert recorder.calls == [
        (
            "POST",
            "/lobbies",
            {
                "json": {
                    "metadata": {"k": "v"},
                    "members": [{"id": "2", "additional_name": "x"}],
                    "idle_timeout_seconds": 60,
                }
            },
        )
    ]
    await client.create_lobby()
    assert recorder.calls[-1][2] == {"json": {}}


async def test_fetch_lobby(state: Any, recorder: Recorder) -> None:
    recorder.response = LOBBY
    client = discord.Client()
    client._connection = state
    client.http = state.http
    lobby = await client.fetch_lobby(96008815106887111)
    assert lobby.id == 96008815106887111
    assert recorder.calls == [("GET", "/lobbies/96008815106887111", {})]


async def test_edit(lobby: Lobby, recorder: Recorder) -> None:
    recorder.response = {**LOBBY, "metadata": {"new": "meta"}, "members": []}
    result = await lobby.edit(
        metadata={"new": "meta"},
        members=[],
        idle_timeout_seconds=5,
    )
    assert result is lobby
    assert lobby.metadata == {"new": "meta"}
    assert lobby.members == []
    assert recorder.calls == [
        (
            "PATCH",
            f"/lobbies/{lobby.id}",
            {
                "json": {
                    "metadata": {"new": "meta"},
                    "members": [],
                    "idle_timeout_seconds": 5,
                }
            },
        )
    ]


async def test_edit_can_clear_metadata(lobby: Lobby, recorder: Recorder) -> None:
    recorder.response = {**LOBBY, "metadata": None}
    await lobby.edit(metadata=None)
    assert recorder.calls[0][2] == {"json": {"metadata": None}}
    assert lobby.metadata is None


async def test_delete(lobby: Lobby, recorder: Recorder) -> None:
    await lobby.delete()
    assert recorder.calls == [("DELETE", f"/lobbies/{lobby.id}", {})]


async def test_add_member(lobby: Lobby, recorder: Recorder) -> None:
    recorder.response = {"id": "9", "flags": 0, "additional_name": "Z"}
    member = await lobby.add_member(
        Object(id=9), metadata={"a": "b"}, additional_name="Z"
    )
    assert member.id == 9
    assert member.lobby_id == lobby.id
    assert lobby.get_member(9) is member
    assert recorder.calls == [
        (
            "PUT",
            f"/lobbies/{lobby.id}/members/9",
            {"json": {"metadata": {"a": "b"}, "additional_name": "Z"}},
        )
    ]
    await member.edit(flags=LobbyMemberFlags(can_link_lobby=True))
    assert recorder.calls[-1][2] == {"json": {"flags": 1}}


async def test_remove_member(lobby: Lobby, recorder: Recorder) -> None:
    await lobby.remove_member(Object(id=41771983429993000))
    assert lobby.members == []
    assert recorder.calls == [
        ("DELETE", f"/lobbies/{lobby.id}/members/41771983429993000", {})
    ]


async def test_bulk_update_members(lobby: Lobby, recorder: Recorder) -> None:
    recorder.response = [{"id": "9"}]
    updated = await lobby.bulk_update_members(
        [
            LobbyMemberUpdate(Object(id=9)),
            LobbyMemberUpdate(Object(id=41771983429993000), remove=True),
        ]
    )
    assert [m.id for m in updated] == [9]
    assert [m.id for m in lobby.members] == [9]
    assert recorder.calls == [
        (
            "POST",
            f"/lobbies/{lobby.id}/members/bulk",
            {
                "json": [
                    {"id": "9"},
                    {"id": "41771983429993000", "remove_member": True},
                ]
            },
        )
    ]


async def test_bulk_update_limits(lobby: Lobby) -> None:
    with pytest.raises(ValueError, match="25"):
        await lobby.bulk_update_members([])
    with pytest.raises(ValueError, match="25"):
        await lobby.bulk_update_members(
            [LobbyMemberUpdate(Object(id=i)) for i in range(26)]
        )


async def test_invites(lobby: Lobby, recorder: Recorder) -> None:
    recorder.response = {"code": "abc"}
    invite = await lobby.create_invite_for(Object(id=9))
    assert invite.code == "abc"
    assert invite.url == "https://discord.gg/abc"
    assert recorder.calls == [("POST", f"/lobbies/{lobby.id}/members/9/invites", {})]
    member_invite = await lobby.members[0].create_invite()
    assert member_invite.code == "abc"


async def test_moderation_metadata(lobby: Lobby, recorder: Recorder) -> None:
    await lobby.set_message_moderation_metadata(77, {"action": "flag"})
    assert recorder.calls == [
        (
            "PUT",
            f"/lobbies/{lobby.id}/messages/77/moderation-metadata",
            {"json": {"action": "flag"}},
        )
    ]
    with pytest.raises(ValueError, match="5"):
        await lobby.set_message_moderation_metadata(77, {str(i): "v" for i in range(6)})
    with pytest.raises(ValueError, match="2000"):
        await lobby.set_message_moderation_metadata(77, {"k": "v" * 2001})
    with pytest.raises(ValueError, match="1024"):
        await lobby.set_message_moderation_metadata(77, {"k" * 1025: "v"})
