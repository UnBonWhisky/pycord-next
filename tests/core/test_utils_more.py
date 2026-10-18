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
import datetime as dt
import io
import json
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Literal, Optional, Union
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import discord
from discord import utils
from discord.errors import HTTPException, InvalidArgument

if TYPE_CHECKING:
    from tests.models.context import World


def test_oauth_url() -> None:
    assert (
        utils.oauth_url(1)
        == "https://discord.com/oauth2/authorize?client_id=1&scope=bot"
    )
    url = utils.oauth_url(
        "5",
        permissions=discord.Permissions(administrator=True),
        guild=discord.Object(id=9),
        redirect_uri="https://example.com/cb?x=1",
        scopes=["bot", "applications.commands"],
        disable_guild_select=True,
    )
    assert url == (
        "https://discord.com/oauth2/authorize?client_id=5"
        "&scope=bot+applications.commands&permissions=8&guild_id=9"
        "&response_type=code&redirect_uri=https%3A%2F%2Fexample.com%2Fcb%3Fx%3D1"
        "&disable_guild_select=true"
    )


def test_resolve_invite_and_template() -> None:
    assert utils.resolve_invite("https://discord.gg/pycord") == "pycord"
    assert utils.resolve_invite("discord.com/invite/abc") == "abc"
    assert utils.resolve_invite("plain") == "plain"
    assert utils.resolve_template("https://discord.new/abc") == "abc"
    assert utils.resolve_template("discord.com/template/xyz") == "xyz"
    assert utils.resolve_template("plain") == "plain"


def test_resolve_invite_and_template_objects(world: World) -> None:
    from discord import types as t
    from tests.core.rig import Rig

    rig = Rig(world)
    invite = discord.Invite.from_incomplete(
        state=rig.state,
        data=rig.payload(
            t.invite.Invite,
            code="objcode",
            channel={"id": str(rig.channel.id), "type": 0, "name": "x"},
        ),
    )
    assert utils.resolve_invite(invite) == "objcode"
    template = discord.Template(
        state=rig.state, data=rig.payload(t.template.Template, code="tplcode")
    )
    assert utils.resolve_template(template) == "tplcode"


def test_format_dt() -> None:
    moment = dt.datetime(2024, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)
    stamp = int(moment.timestamp())
    assert utils.format_dt(moment) == f"<t:{stamp}>"
    assert utils.format_dt(moment, "R") == f"<t:{stamp}:R>"
    clock = utils.format_dt(dt.time(12, 0, tzinfo=dt.timezone.utc), "t")
    assert clock.startswith("<t:")
    assert clock.endswith(":t>")


def test_escape_markdown() -> None:
    assert utils.escape_markdown("*bold* _it_ ~~s~~ `c`") == (
        "\\*bold\\* \\_it\\_ \\~\\~s\\~\\~ \\`c\\`"
    )
    link = "see https://example.com/a_b_c *x*"
    assert utils.escape_markdown(link) == "see https://example.com/a_b_c \\*x\\*"
    assert "\\_b\\_" in utils.escape_markdown(link, ignore_links=False)
    assert utils.escape_markdown("a*b\\c", as_needed=True) == "a*b\\\\c"
    assert utils.escape_markdown("plain", as_needed=True) == "plain"


def test_raw_mentions() -> None:
    text = "<@123456789012345678> <@!223456789012345678> <#323456789012345678> <@&423456789012345678>"
    assert utils.raw_mentions(text) == [123456789012345678, 223456789012345678]
    assert utils.raw_channel_mentions(text) == [323456789012345678]
    assert utils.raw_role_mentions(text) == [423456789012345678]


def test_chunking() -> None:
    assert list(utils.as_chunks(iter(range(5)), 2)) == [[0, 1], [2, 3], [4]]
    assert list(utils.as_chunks([], 2)) == []
    with pytest.raises(ValueError, match="greater than 0"):
        utils.as_chunks(iter([]), 0)


async def test_async_chunking() -> None:
    async def numbers(count: int) -> Any:
        for i in range(count):
            yield i

    chunks = [chunk async for chunk in utils.as_chunks(numbers(5), 2)]
    assert chunks == [[0, 1], [2, 3], [4]]
    assert [x async for x in utils._atake(numbers(5), 0)] == []
    assert [x async for x in utils._atake(numbers(5), 3)] == [0, 1, 2]
    assert [c async for c in utils.as_chunks(numbers(0), 3)] == []


def test_snowflake_list_get() -> None:
    values = utils.SnowflakeList([1, 3, 5])
    assert values.get(3) == 3
    assert values.get(4) is None
    assert values.get(9) is None


def test_missing_sentinel_and_sequence_proxy() -> None:
    assert hash(utils.MISSING) == hash(utils.MISSING)
    assert not utils.MISSING
    assert repr(utils.MISSING) == "..."
    backing = [3, 1, 2, 1]
    proxy = utils.SequenceProxy(backing)
    assert len(proxy) == 4
    assert proxy[0] == 3
    assert proxy[1:3] == [1, 2]
    assert 2 in proxy
    assert list(proxy) == [3, 1, 2, 1]
    assert list(reversed(proxy)) == [1, 2, 1, 3]
    assert proxy.index(2) == 2
    assert proxy.count(1) == 2
    backing.append(9)
    assert len(proxy) == 5


def test_string_width() -> None:
    assert utils._string_width("abc") == 3
    assert utils._string_width("日本") == 4
    assert utils._string_width("a日") == 3


def test_compute_timedelta_and_sleep_until() -> None:
    soon = discord.utils.utcnow() + dt.timedelta(seconds=30)
    assert 0 < utils.compute_timedelta(soon) <= 30
    assert utils.compute_timedelta(discord.utils.utcnow() - dt.timedelta(hours=1)) == 0
    naive = dt.datetime.now() - dt.timedelta(hours=1)  # noqa: DTZ005
    assert utils.compute_timedelta(naive) == 0


async def test_sleep_until_returns_the_result() -> None:
    past = discord.utils.utcnow() - dt.timedelta(seconds=1)
    assert await utils.sleep_until(past, "done") == "done"


async def test_sane_wait_for() -> None:
    async def quick() -> int:
        return 1

    done = await utils.sane_wait_for([quick(), quick()], timeout=1)
    assert sorted(task.result() for task in done) == [1, 1]
    with pytest.raises(asyncio.TimeoutError):
        await utils.sane_wait_for([asyncio.sleep(1)], timeout=0.01)


def test_parse_ratelimit_header() -> None:
    request = SimpleNamespace(headers={"X-Ratelimit-Reset-After": "1.5"})
    assert utils._parse_ratelimit_header(request) == 1.5
    reset = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=10)).timestamp()
    clock = SimpleNamespace(headers={"X-Ratelimit-Reset": str(reset)})
    assert 8 < utils._parse_ratelimit_header(clock) <= 10
    both = SimpleNamespace(
        headers={"X-Ratelimit-Reset-After": "1.5", "X-Ratelimit-Reset": str(reset)}
    )
    assert 8 < utils._parse_ratelimit_header(both, use_clock=True) <= 10


def test_filter_params() -> None:
    params = {"old": 1, "gone": 2, "keep": 3}
    assert utils.filter_params(params, old="new", gone=None, missing="x") == {
        "new": 1,
        "keep": 3,
    }


def test_users_to_csv() -> None:
    buffer = utils.users_to_csv([discord.Object(id=1), discord.Object(id=2)])
    assert isinstance(buffer, io.BytesIO)
    assert buffer.read() == b"1\n2"


def test_mime_types() -> None:
    assert utils._get_mime_type_for_file(b"\x89PNG\r\n\x1a\n") == "image/png"
    assert utils._get_mime_type_for_file(b"\xff\xd8\xffrest") == "image/jpeg"
    assert utils._get_mime_type_for_file(b"abcdefJFIFx") == "image/jpeg"
    assert utils._get_mime_type_for_file(b"GIF89a") == "image/gif"
    assert utils._get_mime_type_for_file(b"GIF87a") == "image/gif"
    assert utils._get_mime_type_for_file(b"RIFFxxxxWEBPx") == "image/webp"
    assert utils._get_mime_type_for_file(b"ID3\x03") == "audio/mpeg"
    assert utils._get_mime_type_for_file(b"\xff\xfb\x90") == "audio/mpeg"
    with pytest.raises(InvalidArgument, match="Unsupported"):
        utils._get_mime_type_for_file(b"nothing")
    assert utils._bytes_to_base64_data(b"ID3\x03") == "data:audio/mpeg;base64,SUQzAw=="


def test_deprecated_decorator_warns_and_calls() -> None:
    with pytest.warns(DeprecationWarning, match="warnings.deprecated"):

        @utils.deprecated("new_thing", since="2.0", removed="3.0", stacklevel=2)
        def old(value: int) -> int:
            return value * 2

    with pytest.warns(DeprecationWarning, match="old is deprecated since version 2.0"):
        assert old(2) == 4
    assert old.__name__ == "old"

    with pytest.warns(DeprecationWarning, match="warnings.deprecated"):

        @utils.deprecated(use_qualname=False)
        def plain() -> str:
            return "ok"

    with pytest.warns(DeprecationWarning, match="plain"):
        assert plain() == "ok"


async def test_delay_task_runs_after_the_delay() -> None:
    called = asyncio.Event()

    async def action() -> None:
        called.set()

    utils.delay_task(0.01, action())
    assert not called.is_set()
    await asyncio.wait_for(called.wait(), 1)


async def test_delay_task_swallows_http_errors() -> None:
    async def failing() -> None:
        raise HTTPException(MagicMock(status=404, reason="gone"), "gone")

    utils.delay_task(0, failing())
    await asyncio.sleep(0.01)
    assert not utils._background_tasks


def test_emoji_map_loading_without_the_package_data() -> None:
    assert isinstance(utils._load_emojis_map(), dict)
    with patch("importlib.resources.files", side_effect=FileNotFoundError):
        assert utils._load_emojis_map() == {}


def test_voice_dependency_warnings(caplog: pytest.LogCaptureFixture) -> None:
    assert isinstance(utils.get_missing_voice_dependencies(), tuple)
    with (
        patch.object(utils, "get_missing_voice_dependencies", return_value=("PyNaCl",)),
        patch.object(utils, "voice_dependency_warning_emitted", False),
        caplog.at_level(logging.WARNING, logger="discord.utils"),
    ):
        utils.warn_if_voice_dependencies_missing()
        utils.warn_if_voice_dependencies_missing()
    messages = [r.getMessage() for r in caplog.records]
    assert messages == ["PyNaCl is not installed, voice will NOT be supported"]

    with (
        patch.object(
            utils, "get_missing_voice_dependencies", return_value=("PyNaCl", "davey")
        ),
        patch.object(utils, "voice_dependency_warning_emitted", False),
        caplog.at_level(logging.WARNING, logger="discord.utils"),
    ):
        caplog.clear()
        utils.warn_if_voice_dependencies_missing()
    assert "PyNaCl, davey are not installed" in caplog.text

    with (
        patch.object(utils, "get_missing_voice_dependencies", return_value=()),
        patch.object(utils, "voice_dependency_warning_emitted", False),
    ):
        caplog.clear()
        utils.warn_if_voice_dependencies_missing()
    assert not caplog.records


def test_missing_voice_dependencies_reports_import_errors() -> None:
    def fail(name: str) -> None:
        raise ImportError(name)

    with patch("importlib.import_module", side_effect=fail):
        assert utils.get_missing_voice_dependencies() == ("PyNaCl", "davey")


def test_get_event_loop_returns_a_loop() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        assert utils._get_event_loop() is loop
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def test_annotation_resolution() -> None:
    scope = {"Optional": Optional, "Union": Union, "int": int, "str": str}
    assert utils.resolve_annotation(None, scope, None, None) is type(None)
    assert utils.resolve_annotation("int", scope, None, {}) is int
    cache: dict[str, Any] = {}
    assert (
        utils.resolve_annotation("Optional[int]", scope, None, cache) == Optional[int]  # noqa: UP045
    )
    assert "Optional[int]" in cache
    assert (
        utils.resolve_annotation("Optional[int]", scope, None, cache) == Optional[int]  # noqa: UP045
    )
    assert utils.resolve_annotation(int, scope, scope, None) is int
    assert utils.resolve_annotation(int | None, scope, None, None) == Optional[int]  # noqa: UP045
    assert (
        utils.resolve_annotation(Union[None, int, str], scope, None, None)  # noqa: UP007
        == Union[int, str, None]  # noqa: UP007
    )
    assert utils.resolve_annotation(list["int"], scope, None, None) == list[int]
    assert (
        utils.resolve_annotation(Literal["a", 1, None], scope, None, None)  # noqa: PYI061
        == Literal["a", 1, None]  # noqa: PYI061
    )
    assert utils.normalise_optional_params([type(None), int]) == (int, type(None))


def test_annotation_resolution_rejects_bad_literals() -> None:
    with pytest.raises(TypeError, match="Literal arguments"):
        utils.evaluate_annotation(Literal[1.5], {}, {}, {})  # type: ignore[arg-type]


def test_basic_autocomplete_filters_and_limits() -> None:
    ctx = SimpleNamespace(value="b")
    values = ["apple", "banana", "blueberry", SimpleNamespace(name="Berry")]

    async def run(callback: Any) -> list[Any]:
        return list(await callback(ctx))

    default = utils.basic_autocomplete(values)
    assert asyncio.run(run(default)) == ["banana", "blueberry", values[3]]

    def producer(context: Any) -> list[str]:
        return [f"{context.value}{i}" for i in range(40)]

    assert len(asyncio.run(run(utils.basic_autocomplete(producer)))) == 25

    async def async_producer(context: Any) -> list[str]:
        return ["b1", "a2"]

    assert asyncio.run(run(utils.basic_autocomplete(async_producer))) == ["b1"]

    sync_filter = utils.basic_autocomplete(values, filter=lambda c, v: v == "apple")
    assert asyncio.run(run(sync_filter)) == ["apple"]

    async def async_filter(context: Any, value: Any) -> bool:
        return isinstance(value, str)

    many = [str(i) for i in range(60)]
    chosen = asyncio.run(run(utils.basic_autocomplete(many, filter=async_filter)))
    assert len(chosen) == 25

    with pytest.raises(TypeError, match="callable"):
        asyncio.run(run(utils.basic_autocomplete(values, filter="x")))  # type: ignore[arg-type]


async def test_get_or_fetch_validation(world: World) -> None:
    client = discord.Client()
    guild = discord.Guild.__new__(discord.Guild)
    assert await utils.get_or_fetch(client, discord.User, None) is None
    assert await utils.get_or_fetch(client, discord.User, None, default="d") == "d"
    with pytest.raises(TypeError, match="required parameters"):
        await utils.get_or_fetch(client, discord.User)
    for target, kind, message in (
        (guild, discord.User, "Guild cannot get_or_fetch User"),
        (client, discord.Member, "Client cannot get_or_fetch Member"),
        (client, discord.Role, "Client cannot get_or_fetch Role"),
        (guild, discord.Guild, "Guild cannot get_or_fetch Guild"),
        (guild, discord.AppEmoji, "Guild cannot get_or_fetch AppEmoji"),
        (client, int, "cannot be used with discord.Client"),
    ):
        with pytest.raises(InvalidArgument, match=message):
            await utils.get_or_fetch(target, kind, 1)  # type: ignore[arg-type]
    _ = world


async def test_get_or_fetch_deprecated_forms() -> None:
    client = discord.Client()
    client._connection.http.get_user = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "id": "5",
            "username": "u",
            "discriminator": "0",
            "avatar": None,
        }
    )
    with pytest.warns(DeprecationWarning, match="get_or_fetch"):
        user = await utils.get_or_fetch(client, "user", 5)  # type: ignore[arg-type]
    assert user.id == 5
    with pytest.warns(DeprecationWarning, match="get_or_fetch"):
        assert (await utils.get_or_fetch(client, attr="user", id=5)).id == 5  # type: ignore[call-arg]
    with (
        pytest.warns(DeprecationWarning, match="get_or_fetch"),
        pytest.raises(InvalidArgument, match="Unknown type"),
    ):
        await utils.get_or_fetch(client, "nothing", 5)  # type: ignore[arg-type]
    with (
        pytest.warns(DeprecationWarning, match="get_or_fetch"),
        pytest.raises(TypeError, match="Invalid `attr`"),
    ):
        await utils.get_or_fetch(client, attr=5, id=5)  # type: ignore[call-arg]
    with pytest.warns(DeprecationWarning, match="get_or_fetch"):
        assert (await utils.get_or_fetch(client, attr=discord.User, id=5)).id == 5  # type: ignore[call-arg]


async def test_get_or_fetch_raises_without_a_default() -> None:
    client = discord.Client()
    client._connection.http.get_user = AsyncMock(  # type: ignore[method-assign]
        side_effect=HTTPException(MagicMock(status=404, reason="x"), "x")
    )
    with pytest.raises(HTTPException):
        await utils.get_or_fetch(client, discord.User, 5)
    assert await utils.get_or_fetch(client, discord.User, 5, default=None) is None


def test_string_to_type_map() -> None:
    mapping = utils._get_string_to_type_map()
    assert mapping["user"] is discord.User
    assert mapping["channel"] is discord.abc.GuildChannel
    assert set(mapping) == {
        "channel",
        "member",
        "user",
        "guild",
        "emoji",
        "appemoji",
        "role",
    }


_ = json
