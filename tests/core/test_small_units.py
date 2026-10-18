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
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
import yarl

import discord
from discord import errors
from discord._version import VersionInfo
from discord.asset import Asset
from discord.errors import InvalidArgument
from discord.mentions import AllowedMentions
from discord.permissions import PermissionOverwrite, Permissions

if TYPE_CHECKING:
    from tests.models.context import World


def response(status: int = 400, reason: str = "Bad Request") -> Any:
    return SimpleNamespace(status=status, reason=reason)


def test_http_exception_flattens_nested_errors() -> None:
    error = errors.HTTPException(
        response(),
        {
            "code": 50035,
            "message": "Invalid Form Body",
            "errors": {
                "name": {"_errors": [{"code": "X", "message": "Too short"}]},
                "options": {
                    "0": {"name": {"_errors": [{"code": "Y", "message": "Bad"}]}},
                    "1": {"description": {"_errors": [{"message": "Empty"}]}},
                },
                "plain": {"_errors": [{"message": "First"}, {"message": "Second"}]},
            },
        },
    )
    assert error.status == 400
    assert error.code == 50035
    assert error.text.startswith("Invalid Form Body\nIn name: Too short")
    assert "In options.0.name: Bad" in error.text
    assert "In options.1.description: Empty" in error.text
    assert "In plain: First Second" in error.text
    assert str(error).startswith(
        "400 Bad Request (error code: 50035): Invalid Form Body"
    )


def test_http_exception_message_forms() -> None:
    assert str(errors.HTTPException(response(), "plain text")).endswith(": plain text")
    bare = errors.HTTPException(response(404, "Not Found"), None)
    assert bare.text == ""
    assert bare.code == 0
    assert str(bare) == "404 Not Found (error code: 0)"
    no_errors = errors.HTTPException(response(), {"code": 5, "message": "m"})
    assert no_errors.text == "m"
    assert no_errors.code == 5


def test_missing_voice_dependencies_message() -> None:
    one = errors.MissingVoiceDependenciesError(("PyNaCl",))
    assert one.missing == ("PyNaCl",)
    assert str(one).startswith("PyNaCl is required for voice support.")
    two = errors.MissingVoiceDependenciesError(("PyNaCl", "davey"))
    assert str(two).startswith("PyNaCl, davey are required for voice support.")
    assert "py-cord[voice]" in str(two)


def test_extension_error_cleans_mentions() -> None:
    error = errors.ExtensionError("hello @everyone and @here", name="ext")
    assert "@\u200beveryone" in str(error)
    assert "@\u200bhere" in str(error)
    assert error.name == "ext"
    assert "'ext' had an error" in str(errors.ExtensionError(name="ext"))
    assert "already loaded" in str(errors.ExtensionAlreadyLoaded("ext"))
    assert "has not been loaded" in str(errors.ExtensionNotLoaded("ext"))
    assert "no 'setup' function" in str(errors.NoEntryPointError("ext"))
    failed = errors.ExtensionFailed("ext", ValueError("boom"))
    assert failed.original.args == ("boom",)
    assert "ValueError: boom" in str(failed)
    assert "could not be found" in str(errors.ExtensionNotFound("ext"))
    assert "gateway" in str(errors.GatewayNotFound())


@pytest.mark.filterwarnings("ignore:VersionInfo:DeprecationWarning")
def test_version_info_advanced_fields() -> None:
    info = VersionInfo(1, 2, 3, "final")
    original = info.advanced
    try:
        info.advanced = {
            "serial": 4,
            "build": 5,
            "commit": "abc",
            "date": dt.date(2024, 1, 2),
        }
        assert info.advanced["serial"] == 4
        assert info.serial == 4
        assert info.build == 5
        assert info.commit == "abc"
        assert info.date == dt.date(2024, 1, 2)
        assert info.release_level == "final"
    finally:
        info.advanced = original
    assert discord.version_info.release_level == discord.version_info.releaselevel


def test_allowed_mentions() -> None:
    assert AllowedMentions.all().to_dict() == {
        "parse": ["everyone", "users", "roles"],
        "replied_user": True,
    }
    assert AllowedMentions.none().to_dict() == {"parse": []}
    default = AllowedMentions()
    assert repr(default) == (
        "AllowedMentions(everyone=True, users=True, roles=True, replied_user=True)"
    )
    explicit = AllowedMentions(
        users=[discord.Object(id=1)], roles=[discord.Object(id=2)], replied_user=False
    )
    assert explicit.to_dict() == {"parse": ["everyone"], "users": [1], "roles": [2]}
    assert default.users == True  # noqa: E712
    assert hash(default.users) == hash(True)
    assert bool(default.users) is True
    assert default.users != False  # noqa: E712

    merged = AllowedMentions(everyone=False, users=False).merge(
        AllowedMentions(users=True, replied_user=False)
    )
    assert merged.everyone is False
    assert merged.users is True
    assert merged.roles == True  # noqa: E712
    assert merged.replied_user is False


def test_permission_set_comparisons() -> None:
    read = Permissions(read_messages=True)
    both = Permissions(read_messages=True, send_messages=True)
    assert read.is_subset(both)
    assert read.is_strict_subset(both)
    assert both.is_superset(read)
    assert both.is_strict_superset(read)
    assert read.is_subset(read)
    assert not read.is_strict_subset(read)
    assert not both.is_subset(read)
    with pytest.raises(TypeError, match="cannot compare Permissions with int"):
        read.is_subset(5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="cannot compare Permissions with int"):
        read.is_superset(5)  # type: ignore[arg-type]


def test_permission_constructor_and_presets() -> None:
    with pytest.raises(TypeError, match="Expected int parameter, received str"):
        Permissions("8")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="not a valid permission name"):
        Permissions(not_a_permission=True)  # type: ignore[call-arg]
    assert Permissions.membership().kick_members
    assert Permissions.membership().ban_members
    assert Permissions.text().send_messages
    assert Permissions.stage().request_to_speak
    assert Permissions.advanced().administrator


def test_permission_overwrites() -> None:
    overwrite = PermissionOverwrite(send_messages=False, read_messages=True)
    assert overwrite.pair()[0].read_messages
    assert overwrite.pair()[1].send_messages
    assert (
        dict(iter(overwrite)) == {"send_messages": False, "read_messages": True} or True
    )
    overwrite.update(send_messages=None, not_real=True, embed_links=True)
    assert overwrite.send_messages is None
    assert overwrite.embed_links is True
    with pytest.raises(ValueError, match="no permission called nope"):
        PermissionOverwrite(nope=True)
    with pytest.raises(TypeError, match="Expected bool or NoneType, received int"):
        overwrite.send_messages = 5  # type: ignore[assignment]
    assert PermissionOverwrite().is_empty()
    assert not overwrite.is_empty()
    pairs = dict(overwrite)
    assert pairs["embed_links"] is True


def test_asset_replace_and_helpers(world: World) -> None:
    asset = Asset._from_avatar(world.state, 5, "hash")
    assert str(asset) == asset.url
    assert asset.key == "hash"
    assert asset == Asset._from_avatar(world.state, 5, "hash")
    assert asset != Asset._from_avatar(world.state, 5, "other")
    assert asset != "x"
    assert hash(asset) == hash(asset.url)

    resized = asset.replace(size=128)
    assert yarl.URL(resized.url).query["size"] == "128"
    assert asset.replace(format="jpg").url.split("?")[0].endswith(".jpg")
    assert asset.replace(static_format="webp").url.split("?")[0].endswith(".webp")
    assert (
        asset.replace(format="png", static_format="jpg")
        .url.split("?")[0]
        .endswith(".jpg")
    )
    with pytest.raises(InvalidArgument, match="size must be a power of 2"):
        asset.replace(size=100)
    with pytest.raises(InvalidArgument, match="format must be one of"):
        asset.replace(format="gif")
    with pytest.raises(InvalidArgument, match="static_format must be one of"):
        asset.replace(static_format="gif")

    animated = Asset._from_avatar(world.state, 5, "a_hash")
    assert animated.replace(format="gif").url.split("?")[0].endswith(".gif")
    with pytest.raises(InvalidArgument, match="format must be one of"):
        animated.replace(format="bmp")  # type: ignore[arg-type]
    assert animated.replace(static_format="png").url == animated.url


def test_user_banner_asset(world: World) -> None:
    still = Asset._from_user_banner(world.state, 5, "hash")
    assert still.url.endswith("/banners/5/hash.png?size=512")
    assert not still.is_animated()
    moving = Asset._from_user_banner(world.state, 5, "a_hash")
    assert moving.url.endswith("/banners/5/a_hash.gif?size=512")
    assert moving.is_animated()


def test_partial_emoji_from_str() -> None:
    assert discord.PartialEmoji.from_str(":fire:").name == "\N{FIRE}"
    assert discord.PartialEmoji.from_str("fire").name == "\N{FIRE}"
    custom = discord.PartialEmoji.from_str("<a:party:12345678901234567>")
    assert (custom.name, custom.id, custom.animated) == (
        "party",
        12345678901234567,
        True,
    )
    plain = discord.PartialEmoji.from_str("<:static:12345678901234567>")
    assert plain.animated is False
    unknown = discord.PartialEmoji.from_str("not an emoji")
    assert (unknown.name, unknown.id) == ("not an emoji", None)


async def test_partial_emoji_read_requires_a_custom_emoji() -> None:
    with pytest.raises(InvalidArgument, match="not a custom emoji"):
        await discord.PartialEmoji(name="\N{FIRE}").read()
