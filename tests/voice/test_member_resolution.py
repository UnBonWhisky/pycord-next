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

import asyncio
import threading
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

import discord

if discord.utils.get_missing_voice_dependencies():
    pytest.skip("requires the voice extra", allow_module_level=True)

from discord import Member, types as t
from discord.enums import SpeakingState
from discord.member import VoiceState
from discord.utils import MISSING
from discord.voice.client import VoiceClient
from discord.voice.enums import ConnectionFlowState, OpCodes
from discord.voice.receive.reader import SpeakingTimer
from discord.voice.state import VoiceConnectionState
from tests.models.context import World
from tests.models_async.a2_support import GUILD_ID, Scene
from tests.state.conftest import build_state

if TYPE_CHECKING:
    from discord.http import HTTPClient


@pytest.fixture(params=["memory", "redis"])
def scene(
    request: pytest.FixtureRequest, loop: asyncio.AbstractEventLoop, http: HTTPClient
) -> Scene:
    return Scene(World(build_state(loop, http, request.param)))


def make_voice_client(scene: Scene) -> VoiceClient:
    channel = scene.world.channel
    vc = VoiceClient.__new__(VoiceClient)
    vc.loop = scene.state.loop
    vc._state = scene.state
    vc.channel = SimpleNamespace(id=channel.id, guild_id=GUILD_ID, guild=scene.guild)  # type: ignore[assignment]
    vc._ssrc_to_id = {}
    vc._id_to_ssrc = {}
    vc._reader = MISSING
    vc._event_listeners = {}
    vc._member_cache = {}
    vc._members_resolving = set()
    vc._resolve_tasks = set()
    vc.dispatched = []  # type: ignore[attr-defined]
    vc.dispatch = lambda event, *args: vc.dispatched.append((event, *args))  # type: ignore[attr-defined,method-assign]
    return vc


def test_speaking_op_resolves_the_member(scene: Scene) -> None:
    member = scene.add_member(61)
    vc = make_voice_client(scene)

    scene.run(
        vc._recv_hook(
            None,  # type: ignore[arg-type]
            {"op": OpCodes.speaking, "d": {"user_id": "61", "ssrc": 9, "speaking": 1}},
        )
    )

    event, resolved, ssrc, speaking = vc.dispatched[0]  # type: ignore[attr-defined]
    assert event == "member_speaking_state_update"
    assert resolved.id == member.id
    assert isinstance(resolved, Member)
    assert ssrc == 9
    assert speaking is SpeakingState.voice
    assert vc._ssrc_to_id == {9: 61}
    assert vc._peek_member(61).id == 61  # type: ignore[union-attr]


def test_speaking_op_for_an_unknown_member_dispatches_none(scene: Scene) -> None:
    vc = make_voice_client(scene)

    scene.run(
        vc._recv_hook(
            None,  # type: ignore[arg-type]
            {"op": OpCodes.speaking, "d": {"user_id": "62", "ssrc": 3, "speaking": 0}},
        )
    )

    assert vc.dispatched[0][1] is None  # type: ignore[attr-defined]
    assert vc._peek_member(62) is None


def test_clients_connect_skips_unknown_members(scene: Scene) -> None:
    scene.add_member(63)
    vc = make_voice_client(scene)

    scene.run(
        vc._recv_hook(
            None,  # type: ignore[arg-type]
            {"op": OpCodes.clients_connect, "d": {"user_ids": ["63", "64"]}},
        )
    )

    assert [(e, m.id) for e, m in vc.dispatched] == [("member_connect", 63)]  # type: ignore[attr-defined]


def test_client_disconnect_dispatches_member_and_forgets_it(scene: Scene) -> None:
    scene.add_member(65)
    vc = make_voice_client(scene)
    vc._add_ssrc(65, 5)
    scene.run(vc._resolve_member(65))

    scene.run(
        vc._recv_hook(
            None,  # type: ignore[arg-type]
            {"op": OpCodes.client_disconnect, "d": {"user_id": "65"}},
        )
    )

    event, member, ssrc = vc.dispatched[0]  # type: ignore[attr-defined]
    assert (event, member.id, ssrc) == ("member_disconnect", 65, 5)
    assert 65 not in vc._member_cache


def test_ready_op_registers_our_own_ssrc(scene: Scene) -> None:
    vc = make_voice_client(scene)

    scene.run(vc._recv_hook(None, {"op": OpCodes.ready, "d": {"ssrc": 77}}))  # type: ignore[arg-type]

    assert vc._ssrc_to_id == {77: scene.state.user.id}


def test_member_resolution_from_a_router_thread_runs_on_the_loop(
    scene: Scene,
) -> None:
    scene.add_member(66)
    vc = make_voice_client(scene)
    loop_thread = threading.get_ident()
    resolved_on: list[int] = []
    original = vc._resolve_member

    async def spy(user_id: int) -> Member | None:
        resolved_on.append(threading.get_ident())
        return await original(user_id)

    vc._resolve_member = spy  # type: ignore[method-assign]
    results: list[Any] = []

    def router_thread() -> None:
        results.append(vc._peek_member(66))
        results.append(vc._peek_member(66))

    thread = threading.Thread(target=router_thread)
    thread.start()
    thread.join()
    assert results == [None, None]

    async def settle() -> None:
        await asyncio.sleep(0.05)
        while vc._resolve_tasks:
            await asyncio.gather(*list(vc._resolve_tasks))

    scene.run(settle())

    assert resolved_on == [loop_thread]
    later: list[Any] = []
    thread = threading.Thread(target=lambda: later.append(vc._peek_member(66)))
    thread.start()
    thread.join()
    assert later[0] is not None
    assert later[0].id == 66


def test_unresolvable_members_are_not_resolved_again_for_every_packet(
    scene: Scene,
) -> None:
    vc = make_voice_client(scene)
    calls: list[int] = []
    original = vc._resolve_member

    async def spy(user_id: int) -> Member | None:
        calls.append(user_id)
        return await original(user_id)

    vc._resolve_member = spy  # type: ignore[method-assign]

    def router_thread() -> None:
        for _ in range(20):
            vc._peek_member(67)

    thread = threading.Thread(target=router_thread)
    thread.start()
    thread.join()
    scene.run(asyncio.sleep(0.05))
    thread = threading.Thread(target=router_thread)
    thread.start()
    thread.join()
    scene.run(asyncio.sleep(0.05))

    assert calls == [67]


def test_speaking_timer_dispatches_the_resolved_member(scene: Scene) -> None:
    member = scene.add_member(68)
    vc = make_voice_client(scene)
    vc._connection = SimpleNamespace(ssrc_user_map={4: 68})  # type: ignore[assignment]
    scene.run(vc._resolve_member(68))
    sinked: list[Any] = []
    vc._dispatch_sink = lambda event, m: sinked.append((event, m))  # type: ignore[method-assign]
    timer = SpeakingTimer(SimpleNamespace(client=vc))

    thread = threading.Thread(target=lambda: timer.dispatch("member_speaking_start", 4))
    thread.start()
    thread.join()

    assert sinked[0][0] == "member_speaking_start"
    assert sinked[0][1].id == member.id


def test_packet_decoder_resolves_the_user_without_touching_the_cache(
    scene: Scene,
) -> None:
    from discord.opus import PacketDecoder

    scene.add_member(69)
    vc = make_voice_client(scene)
    scene.run(vc._resolve_member(69))
    decoder = PacketDecoder.__new__(PacketDecoder)
    decoder.router = SimpleNamespace(sink=SimpleNamespace(client=vc))  # type: ignore[assignment]
    found: list[Any] = []

    thread = threading.Thread(target=lambda: found.append(decoder._get_user(69)))
    thread.start()
    thread.join()

    assert found[0].id == 69


def make_connection(scene: Scene) -> VoiceConnectionState:
    vc = make_voice_client(scene)
    connection = VoiceConnectionState.__new__(VoiceConnectionState)
    connection.client = vc
    connection.self_deaf = False
    connection.self_mute = True
    return connection


def test_self_voice_state_is_read_from_the_cache(scene: Scene) -> None:
    connection = make_connection(scene)
    assert scene.run(connection.get_self_voice_state()) is None
    assert scene.run(connection._self_voice_flags()) == {
        "self_deaf": False,
        "self_mute": True,
    }

    payload = scene.world.payload(
        t.voice.GuildVoiceState,
        user_id=str(scene.state.self_id),
        guild_id=str(GUILD_ID),
        self_deaf=True,
        self_mute=False,
    )
    payload.pop("member", None)
    voice = VoiceState(data=payload, state=scene.state, channel=scene.world.channel)  # type: ignore[arg-type]
    scene.run(
        scene.state._guild_bucket("voice_states", GUILD_ID).set(
            scene.state.self_id, voice
        )
    )

    found = scene.run(connection.get_self_voice_state())
    assert found is not None
    assert found.self_deaf is True
    assert scene.run(connection._self_voice_flags()) == {
        "self_deaf": True,
        "self_mute": False,
    }


def test_move_updates_the_voice_channel_from_the_cache(scene: Scene) -> None:
    connection = make_connection(scene)
    other = scene.world.channel
    scene.run(scene.state._guild_bucket("channels", GUILD_ID).set(other.id, other))

    scene.run(connection._update_voice_channel(other.id))

    assert connection.client.channel.id == other.id
    scene.run(connection._update_voice_channel(None))
    assert not connection.client.channel


def test_voice_state_update_moves_while_connected(scene: Scene) -> None:
    connection = make_connection(scene)
    connection._state = ConnectionFlowState.connected
    connection._disconnected = asyncio.Event()
    connection._expecting_disconnect = False
    other = scene.world.channel
    scene.run(scene.state._guild_bucket("channels", GUILD_ID).set(other.id, other))
    event = SimpleNamespace(channel_id=other.id, session_id="s")

    scene.run(connection.voice_state_update(event))  # type: ignore[arg-type]

    assert connection.client.channel.id == other.id
    assert connection.session_id == "s"


async def test_voice_client_dispatch_runs_listeners_and_forwards_to_the_client() -> (
    None
):
    client = discord.Client()
    client._connection.user = SimpleNamespace(id=5)  # type: ignore[assignment]
    channel = SimpleNamespace(id=2, guild=SimpleNamespace(id=1))
    vc = VoiceClient(client, channel)  # type: ignore[arg-type]
    vc._connection._socket_reader.stop()
    vc._connection = SimpleNamespace()  # type: ignore[assignment]
    forwarded: list[tuple[str, tuple[Any, ...]]] = []
    client.dispatch = lambda event, *args: forwarded.append((event, args))  # type: ignore[method-assign]
    called = asyncio.Event()
    seen: list[tuple[Any, ...]] = []

    async def listener(*args: Any) -> None:
        seen.append(args)
        called.set()

    vc._event_listeners["on_thing"] = [listener]

    vc.dispatch("thing", 1, 2)
    assert vc._dispatch_task_set
    await asyncio.wait_for(called.wait(), 2)
    await asyncio.sleep(0)

    assert seen == [(1, 2)]
    assert forwarded == [("thing", (1, 2))]
    assert not vc._dispatch_task_set
    await client.http.close()
