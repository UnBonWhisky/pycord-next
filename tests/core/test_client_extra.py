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

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import discord
from discord import types as t
from discord.errors import HTTPException
from tests.core.rig import (
    PNG,
    Case,
    Rig,
    check_list,
    check_type,
    execute,
    lst,
    one,
)

if TYPE_CHECKING:
    from tests.models.context import World


def client(r: Rig) -> Any:
    return r.client


def app_id(r: Rig) -> None:
    r.state.application_id = 4242


CASES = [
    Case(
        "fetch_application",
        client,
        "fetch_application",
        "get_application",
        one(t.appinfo.PartialAppInfo),
        args=lambda r: (12,),
        called_with=lambda r: ((12,), {}),
        check=check_type(discord.PartialAppInfo),
    ),
    Case(
        "application_info",
        client,
        "application_info",
        "application_info",
        one(t.appinfo.AppInfo),
        check=check_type(discord.AppInfo),
    ),
    Case(
        "fetch_template",
        client,
        "fetch_template",
        "get_template",
        one(t.template.Template),
        args=lambda r: ("https://discord.new/abc",),
        called_with=lambda r: (("abc",), {}),
        check=check_type(discord.Template),
    ),
    Case(
        "fetch_stage_instance",
        client,
        "fetch_stage_instance",
        "get_stage_instance",
        lambda r: r.payload(
            t.channel.StageInstance,
            guild_id=str(r.guild.id),
            channel_id=str(r.channel.id),
        ),
        args=lambda r: (r.channel.id,),
        called_with=lambda r: ((r.channel.id,), {}),
        check=check_type(discord.StageInstance),
    ),
    Case(
        "fetch_invite",
        client,
        "fetch_invite",
        "get_invite",
        lambda r: r.payload(
            t.invite.Invite,
            channel={"id": str(r.channel.id), "type": 0, "name": "x"},
        ),
        args=lambda r: ("https://discord.gg/pycord",),
        kwargs=lambda r: {"with_counts": False, "event_id": 5},
        called_with=lambda r: (
            ("pycord",),
            {
                "with_counts": False,
                "with_expiration": True,
                "guild_scheduled_event_id": 5,
            },
        ),
        check=check_type(discord.Invite),
    ),
    Case(
        "delete_invite",
        client,
        "delete_invite",
        "delete_invite",
        args=lambda r: ("discord.gg/pycord",),
        called_with=lambda r: (("pycord",), {}),
    ),
    Case(
        "fetch_widget",
        client,
        "fetch_widget",
        "get_widget",
        one(t.widget.Widget),
        args=lambda r: (7,),
        called_with=lambda r: ((7,), {}),
        check=check_type(discord.Widget),
    ),
    Case(
        "fetch_webhook",
        client,
        "fetch_webhook",
        "get_webhook",
        one(t.webhook.Webhook),
        args=lambda r: (7,),
        called_with=lambda r: ((7,), {}),
        check=check_type(discord.Webhook),
    ),
    Case(
        "fetch_sticker",
        client,
        "fetch_sticker",
        "get_sticker",
        one(t.sticker.GuildSticker, type=2),
        args=lambda r: (7,),
        called_with=lambda r: ((7,), {}),
        check=check_type(discord.GuildSticker),
    ),
    Case(
        "fetch_premium_sticker_packs",
        client,
        "fetch_premium_sticker_packs",
        "list_premium_sticker_packs",
        lambda r: {"sticker_packs": [r.payload(t.sticker.StickerPack)]},
        check=check_list(discord.StickerPack),
    ),
    Case(
        "fetch_role_connection_metadata_records",
        client,
        "fetch_role_connection_metadata_records",
        "get_application_role_connection_metadata_records",
        lst(t.application_role_connection.ApplicationRoleConnectionMetadata),
        setup=app_id,
        called_with=lambda r: ((4242,), {}),
        check=check_list(discord.ApplicationRoleConnectionMetadata),
    ),
    Case(
        "update_role_connection_metadata_records",
        client,
        "update_role_connection_metadata_records",
        "update_application_role_connection_metadata_records",
        lst(t.application_role_connection.ApplicationRoleConnectionMetadata),
        setup=app_id,
        args=lambda r: (
            discord.ApplicationRoleConnectionMetadata.from_dict(
                r.payload(
                    t.application_role_connection.ApplicationRoleConnectionMetadata
                )
            ),
        ),
        check=check_list(discord.ApplicationRoleConnectionMetadata),
    ),
    Case(
        "fetch_skus",
        client,
        "fetch_skus",
        "list_skus",
        lst(t.monetization.SKU),
        setup=app_id,
        called_with=lambda r: ((4242,), {}),
        check=check_list(discord.SKU),
    ),
    Case(
        "fetch_emojis",
        client,
        "fetch_emojis",
        "get_all_application_emojis",
        lambda r: {"items": [r.payload(t.emoji.Emoji)]},
        setup=app_id,
        called_with=lambda r: ((4242,), {}),
        check=check_list(discord.AppEmoji),
    ),
    Case(
        "fetch_emoji",
        client,
        "fetch_emoji",
        "get_application_emoji",
        one(t.emoji.Emoji),
        setup=app_id,
        args=lambda r: (9,),
        called_with=lambda r: ((4242, 9), {}),
        check=check_type(discord.AppEmoji),
    ),
    Case(
        "create_emoji",
        client,
        "create_emoji",
        "create_application_emoji",
        one(t.emoji.Emoji),
        setup=app_id,
        kwargs=lambda r: {"name": "pyc", "image": PNG},
        called_with=lambda r: (
            (4242, "pyc", "data:image/png;base64,iVBORw0KGgo="),
            {},
        ),
        check=check_type(discord.AppEmoji),
    ),
    Case(
        "delete_emoji",
        client,
        "delete_emoji",
        "delete_application_emoji",
        setup=app_id,
        args=lambda r: (discord.Object(id=9),),
        called_with=lambda r: ((4242, 9), {}),
    ),
    Case(
        "fetch_default_sounds",
        client,
        "fetch_default_sounds",
        "get_default_sounds",
        lst(t.soundboard.SoundboardSound),
        check=check_list(discord.SoundboardSound),
    ),
    Case(
        "create_dm",
        client,
        "create_dm",
        "start_private_message",
        lambda r: r.payload(
            t.channel.DMChannel, recipients=[r.payload(t.user.User, id="55")]
        ),
        args=lambda r: (discord.Object(id=55),),
        called_with=lambda r: ((55,), {}),
        check=check_type(discord.DMChannel),
    ),
]


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_client_remote_calls(world: World, case: Case) -> None:
    execute(Rig(world), case)


def test_create_dm_reuses_a_known_channel(world: World) -> None:
    rig = Rig(world)
    rig.respond(
        "start_private_message",
        rig.payload(
            t.channel.DMChannel, recipients=[rig.payload(t.user.User, id="55")]
        ),
    )
    first = rig.run(rig.client.create_dm(discord.Object(id=55)))
    second = rig.run(rig.client.create_dm(discord.Object(id=55)))
    assert first is second
    assert rig.http.start_private_message.call_count == 1


def test_delete_emoji_evicts_the_cached_emoji(world: World) -> None:
    rig = Rig(world)
    rig.state.application_id = 4242
    rig.state.cache_app_emojis = True
    rig.respond("create_application_emoji", rig.payload(t.emoji.Emoji, id="9"))
    emoji = rig.run(rig.client.create_emoji(name="pyc", image=PNG))
    assert rig.run(rig.state.get_emoji(9)) is emoji

    rig.run(rig.client.delete_emoji(emoji))

    assert rig.run(rig.state.get_emoji(9)) is None


def test_application_properties_and_store_url(world: World) -> None:
    rig = Rig(world)
    client = rig.client
    rig.state.application_id = 4242
    assert client.application_id == 4242
    assert client._application_id == 4242
    rig.state.application_flags = discord.ApplicationFlags._from_value(8)
    assert client.application_flags is rig.state.application_flags
    assert client.store_url == "https://discord.com/application-directory/4242/store"
    assert client.intents == rig.state.intents
    assert client.persistent_views == rig.state.persistent_views


def test_activity_status_and_mentions_setters(world: World) -> None:
    client = Rig(world).client
    assert client.activity is None
    client.activity = discord.Game("chess")
    assert client.activity.name == "chess"
    client.activity = None
    assert client.activity is None
    with pytest.raises(TypeError, match="BaseActivity"):
        client.activity = "chess"

    assert client.status is discord.Status.online
    client.status = discord.Status.offline
    assert client._connection._status == "invisible"
    assert client.status is discord.Status.invisible
    client.status = discord.Status.idle
    assert client.status is discord.Status.idle
    with pytest.raises(TypeError, match="Status"):
        client.status = "idle"

    assert client.allowed_mentions is None
    client.allowed_mentions = discord.AllowedMentions.none()
    assert client.allowed_mentions.to_dict() == discord.AllowedMentions.none().to_dict()
    client.allowed_mentions = None
    with pytest.raises(TypeError, match="AllowedMentions"):
        client.allowed_mentions = object()


def test_add_view_validation(world: World) -> None:
    client = Rig(world).client
    with pytest.raises(TypeError, match="BaseView"):
        client.add_view(object())

    view = MagicMock(spec=discord.ui.View)
    view.is_persistent.return_value = False
    with pytest.raises(ValueError, match="not persistent"):
        client.add_view(view)


async def test_add_view_stores_persistent_views() -> None:
    client = discord.Client()
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(custom_id="persist"))
    client.add_view(view, message_id=5)
    assert view in client.persistent_views


def test_entitlements_iterator_arguments(world: World) -> None:
    rig = Rig(world)
    iterator = rig.client.entitlements(
        user=discord.Object(id=1),
        skus=[discord.Object(id=2)],
        guild=discord.Object(id=3),
        limit=5,
        exclude_ended=True,
    )
    assert iterator.user_id == 1
    assert iterator.sku_ids == [2]
    assert iterator.guild_id == 3
    assert iterator.exclude_ended is True
    plain = rig.client.entitlements()
    assert plain.user_id is None
    assert plain.sku_ids is None
    assert plain.guild_id is None


def test_fetch_guilds_builds_a_guild_iterator(world: World) -> None:
    rig = Rig(world)
    iterator = rig.client.fetch_guilds(limit=7, with_counts=False)
    assert isinstance(iterator, discord.iterators.GuildIterator)
    assert iterator.limit == 7
    assert iterator.with_counts is False


def test_get_poll_stage_instance_and_user_helpers(world: World) -> None:
    rig = Rig(world)
    client = rig.client
    poll = discord.Poll("q?")
    rig.run(rig.state.store_poll(poll, 9))
    assert rig.run(client.get_poll(9)) is poll
    assert rig.run(client.get_poll(10)) is None
    assert rig.run(client.get_stage_instance(rig.channel.id)) is None

    stage = discord.StageChannel(
        state=rig.state,
        guild=rig.guild,
        data=rig.payload(
            t.channel.StageChannel,
            id="9500",
            guild_id=str(rig.guild.id),
            type=13,
            parent_id=None,
            permission_overwrites=[],
        ),
    )
    rig.run(rig.guild._add_channel(stage))
    instance = discord.StageInstance(
        guild=rig.guild,
        state=rig.state,
        data=rig.payload(
            t.channel.StageInstance,
            guild_id=str(rig.guild.id),
            channel_id="9500",
        ),
    )
    rig.run(
        rig.state._guild_bucket("stage_instances", rig.guild.id).set(
            instance.id, instance
        )
    )
    assert rig.run(client.get_stage_instance(9500)) is instance


def test_get_or_fetch_swallows_http_errors(world: World) -> None:
    rig = Rig(world)
    rig.state._cache_users = True
    user_payload = rig.payload(t.user.User, id="31")
    rig.respond("get_user", user_payload)
    with pytest.warns(DeprecationWarning, match="get_or_fetch_user"):
        user = rig.run(rig.client.get_or_fetch_user(31))
    assert isinstance(user, discord.User)
    assert user.id == 31

    rig.http.get_user.side_effect = HTTPException(
        MagicMock(status=404, reason="missing"), "missing"
    )
    assert rig.run(rig.client.get_or_fetch(discord.User, 32, default="d")) == "d"
    assert rig.run(rig.client.get_or_fetch(discord.User, None, default="d")) == "d"


def test_iter_cached_messages(world: World) -> None:
    rig = Rig(world)
    client = rig.client
    for i in range(3):
        rig.run(rig.state._store_message(rig.make_message(7000 + i)))

    async def collect() -> list[Any]:
        return [m async for m in client.iter_cached_messages()]

    assert sorted(m.id for m in rig.run(collect())) == [7000, 7001, 7002]
    rig.state._messages = None
    assert rig.run(collect()) == []


async def test_dispatch_resolves_wait_for_and_runs_listeners() -> None:
    client = discord.Client()
    seen: list[Any] = []

    async def on_ping(value: int) -> None:
        seen.append(("listener", value))

    async def on_once(value: int) -> None:
        seen.append(("once", value))

    async def on_pong(value: int) -> None:
        seen.append(("pong", value))

    client.add_listener(on_ping, "on_ping")
    client.listen("on_ping", once=True)(on_once)
    client.event(on_pong)

    waiter = asyncio.ensure_future(
        client.wait_for("ping", check=lambda value: value == 2, timeout=1)
    )
    cancelled = asyncio.ensure_future(client.wait_for("ping", timeout=1))
    broken = asyncio.ensure_future(client.wait_for("ping", check=lambda v: 1 / 0))
    await asyncio.sleep(0)
    cancelled.cancel()
    await asyncio.sleep(0)

    client.dispatch("ping", 1)
    client.dispatch("ping", 2)
    client.dispatch("pong", 3)
    await asyncio.sleep(0.01)

    assert await waiter == 2
    with pytest.raises(ZeroDivisionError):
        await broken
    assert ("listener", 1) in seen
    assert ("listener", 2) in seen
    assert [item for item in seen if item[0] == "once"] == [("once", 1)]
    assert ("pong", 3) in seen


async def test_wait_for_returns_tuples_and_none() -> None:
    client = discord.Client()
    first = asyncio.ensure_future(client.wait_for("pair", timeout=1))
    second = asyncio.ensure_future(client.wait_for("nothing", timeout=1))
    await asyncio.sleep(0)
    client.dispatch("pair", 1, 2)
    client.dispatch("nothing")
    assert await first == (1, 2)
    assert await second is None
    assert client._listeners == {}


async def test_failing_event_handlers_go_to_on_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = discord.Client()

    async def on_boom() -> None:
        raise RuntimeError("boom")

    handled = asyncio.Event()
    errors: list[Any] = []

    async def on_error(event: str, *_args: Any, **_kwargs: Any) -> None:
        errors.append(event)
        handled.set()

    client.event(on_boom)
    client.event(on_error)
    client.dispatch("boom")
    await asyncio.wait_for(handled.wait(), 1)
    assert errors == ["on_boom"]

    plain = discord.Client()

    async def on_fail() -> None:
        raise RuntimeError("visible")

    plain.event(on_fail)
    plain.dispatch("fail")
    await asyncio.sleep(0.01)
    captured = capsys.readouterr()
    assert "Ignoring exception in on_fail" in captured.err


async def test_default_view_and_modal_error_handlers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = discord.Client()
    interaction = MagicMock(view="V", modal="M")
    await client.on_view_error(ValueError("v"), "ITEM", interaction)
    await client.on_modal_error(ValueError("m"), interaction)
    err = capsys.readouterr().err
    assert "Ignoring exception in view V for item ITEM" in err
    assert "Ignoring exception in modal M" in err


def test_listener_registration_rules() -> None:
    client = discord.Client()

    async def on_thing() -> None: ...

    def sync_listener() -> None: ...

    with pytest.raises(ValueError, match="must start with 'on_'"):
        client.add_listener(on_thing, "thing")
    with pytest.raises(TypeError, match="coroutines"):
        client.add_listener(sync_listener, "on_sync")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="coroutine function"):
        client.event(sync_listener)  # type: ignore[arg-type]

    client.add_listener(on_thing)
    assert client._event_handlers["on_thing"] == [on_thing]
    client.remove_listener(on_thing)
    client.remove_listener(on_thing)
    client.remove_listener(on_thing, "on_missing")
    assert client._event_handlers["on_thing"] == []

    @client.listen
    async def on_decorated() -> None: ...

    assert client._event_handlers["on_decorated"] == [on_decorated]

    @client.listen("on_application_command_error")
    async def on_application_command_error(ctx: Any, error: Any) -> None: ...

    assert client.on_application_command_error is on_application_command_error  # type: ignore[attr-defined]


async def test_wait_until_ready_and_close() -> None:
    client = discord.Client()
    client._ready.set()
    await client.wait_until_ready()
    with patch.object(type(client.http), "close", new=AsyncMock()) as close:
        await client.close()
        await client.close()
    close.assert_awaited_once()
    assert client.is_closed()
    assert not client.is_ready()


async def test_login_validates_the_token_and_stores_the_user() -> None:
    client = discord.Client()
    with pytest.raises(TypeError, match="token must be of type str"):
        await client.login(123)  # type: ignore[arg-type]
    payload = {
        "id": "1",
        "username": "bot",
        "discriminator": "0",
        "avatar": None,
        "bot": True,
        "verified": True,
        "mfa_enabled": False,
    }
    with patch.object(
        type(client.http), "static_login", new=AsyncMock(return_value=payload)
    ) as login:
        await client.login(" token ")
    login.assert_awaited_once_with("token")
    assert client._connection.user is not None
    assert client._connection.user.id == 1


async def test_start_logs_in_then_connects() -> None:
    client = discord.Client()
    client.login = AsyncMock()  # type: ignore[method-assign]
    client.connect = AsyncMock()  # type: ignore[method-assign]
    await client.start("token", reconnect=False)
    client.login.assert_awaited_once_with("token")
    client.connect.assert_awaited_once_with(reconnect=False)


async def test_connect_dispatches_gateway_events_and_closes() -> None:
    client = discord.Client()

    async def events() -> Any:
        yield "event-1"
        yield "event-2"

    manager = MagicMock()
    manager.events = events
    client._start_gateway = AsyncMock(return_value=manager)  # type: ignore[method-assign]
    client._handle_event = AsyncMock()  # type: ignore[method-assign]
    client.close = AsyncMock()  # type: ignore[method-assign]

    await client.connect()

    assert client._handle_event.await_args_list[0].args == ("event-1",)
    assert client._handle_event.await_count == 2
    client.close.assert_awaited_once()


async def test_connect_closes_when_the_event_loop_fails() -> None:
    client = discord.Client()

    async def events() -> Any:
        raise RuntimeError("gateway down")
        yield

    manager = MagicMock()
    manager.events = events
    client._start_gateway = AsyncMock(return_value=manager)  # type: ignore[method-assign]
    client.close = AsyncMock()  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="gateway down"):
        await client.connect()
    client.close.assert_awaited_once()


async def test_fetch_gateway_info_retries_http_errors() -> None:
    client = discord.Client()
    info = object()
    client.http.get_bot_gateway_info = AsyncMock(  # type: ignore[method-assign]
        side_effect=[OSError("down"), info]
    )
    with patch("asyncio.sleep", new=AsyncMock()) as sleep:
        assert await client._fetch_gateway_info(True) is info
    sleep.assert_awaited_once()

    client.http.get_bot_gateway_info = AsyncMock(side_effect=OSError("down"))  # type: ignore[method-assign]
    with pytest.raises(OSError, match="down"):
        await client._fetch_gateway_info(False)


async def test_clear_resets_the_connection() -> None:
    client = discord.Client()
    client._closed = True
    client._ready.set()
    with patch.object(type(client.http), "recreate") as recreate:
        await client.clear()
    recreate.assert_called_once_with()
    assert not client.is_closed()
    assert not client.is_ready()


def test_change_presence_updates_cached_members(world: World) -> None:
    rig = Rig(world)
    websocket = MagicMock()
    websocket.change_presence = AsyncMock()
    manager = MagicMock()
    manager.get_transport.return_value = websocket
    rig.client._shard_manager = manager
    me = rig.run(rig.guild.get_me())
    if me is None:
        me = rig.world.member
        rig.state.user = rig.world.me
        me._user.id = rig.world.me.id
        rig.run(rig.guild._add_member(me))

    rig.run(
        rig.client.change_presence(
            activity=discord.Game("chess"), status=discord.Status.offline
        )
    )
    websocket.change_presence.assert_awaited_once()
    assert websocket.change_presence.await_args.kwargs["status"] == "invisible"
    refreshed = rig.run(rig.guild.get_me())
    assert refreshed is not None
    assert refreshed.status is discord.Status.offline
    assert [a.name for a in refreshed.activities] == ["chess"]

    rig.run(rig.client.change_presence())
    assert websocket.change_presence.await_args.kwargs["status"] == "online"
    refreshed = rig.run(rig.guild.get_me())
    assert refreshed.status is discord.Status.online
    assert refreshed.activities == ()


def test_run_stops_when_the_client_finishes(world: World) -> None:
    rig = Rig(world)
    client = rig.client
    client.start = AsyncMock()
    client.close = AsyncMock()
    with patch("discord.client._cleanup_loop") as cleanup:
        client.run("token")
    client.start.assert_awaited_once_with("token")
    client.close.assert_awaited_once()
    cleanup.assert_called_once_with(rig.state.loop)


def test_run_reraises_errors_from_start(world: World) -> None:
    rig = Rig(world)
    client = rig.client
    client.start = AsyncMock(side_effect=RuntimeError("bad token"))
    client.close = AsyncMock()
    with (
        patch("discord.client._cleanup_loop"),
        pytest.raises(RuntimeError, match="bad token"),
    ):
        client.run("token")


def test_cancel_tasks_and_cleanup_loop() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def sleeper() -> None:
        await asyncio.sleep(10)

    async def failing() -> None:
        try:
            await asyncio.sleep(10)
        finally:
            raise RuntimeError("shutdown")

    tasks = [loop.create_task(sleeper()), loop.create_task(failing())]
    loop.run_until_complete(asyncio.sleep(0))
    handler = MagicMock()
    loop.set_exception_handler(lambda _loop, context: handler(context))

    from discord.client import _cancel_tasks, _cleanup_loop

    _cancel_tasks(loop)
    assert all(task.done() for task in tasks)
    assert handler.call_count == 1
    assert isinstance(handler.call_args.args[0]["exception"], RuntimeError)

    _cleanup_loop(loop)
    assert loop.is_closed()
    asyncio.set_event_loop(None)
