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

import inspect
import re
from io import BytesIO
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from discord.file import File
from discord.http import HTTPClient, Route, routes

if TYPE_CHECKING:
    from collections.abc import Callable

METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}

RESOURCE_BY_PATH: list[tuple[str, str]] = [
    (r"^/channels/\{channel_id\}/messages/\{message_id\}/threads", "ChannelRoutes"),
    (r"^/channels/\{channel_id\}/(messages|typing|pins)", "MessageRoutes"),
    (r"^/channels/\{channel_id\}/polls", "PollRoutes"),
    (r"^/channels/\{channel_id\}/(webhooks|followers)", "WebhookRoutes"),
    (r"^/channels/\{channel_id\}/invites", "InviteRoutes"),
    (r"^/channels/\{channel_id\}/voice-status", "VoiceRoutes"),
    (r"^/channels/\{channel_id\}/send-soundboard-sound", "SoundboardRoutes"),
    (r"^/channels", "ChannelRoutes"),
    (r"^/guilds/\{guild_id\}/messages", "MessageRoutes"),
    (r"^/guilds/templates", "GuildTemplateRoutes"),
    (r"^/guilds/\{guild_id\}/templates", "GuildTemplateRoutes"),
    (r"^/guilds/\{guild_id\}/audit-logs", "AuditLogRoutes"),
    (r"^/guilds/\{guild_id\}/auto-moderation", "AutoModerationRoutes"),
    (r"^/guilds/\{guild_id\}/scheduled-events", "GuildScheduledEventRoutes"),
    (r"^/guilds/\{guild_id\}/soundboard-sounds", "SoundboardRoutes"),
    (r"^/guilds/\{guild_id\}/emojis", "EmojiRoutes"),
    (r"^/guilds/\{guild_id\}/stickers", "StickerRoutes"),
    (r"^/guilds/\{guild_id\}/(invites|vanity-url)", "InviteRoutes"),
    (r"^/guilds/\{guild_id\}/webhooks", "WebhookRoutes"),
    (r"^/guilds/\{guild_id\}/voice-states", "VoiceRoutes"),
    (r"^/guilds/\{guild_id\}/channels", "ChannelRoutes"),
    (r"^/guilds/\{guild_id\}/threads", "ChannelRoutes"),
    (r"^/guilds", "GuildRoutes"),
    (r"^/users", "UserRoutes"),
    (r"^/auth", "UserRoutes"),
    (r"^/applications/\{application_id\}/emojis", "EmojiRoutes"),
    (
        r"^/applications/\{application_id\}/(guilds/\{guild_id\}/)?commands",
        "ApplicationCommandRoutes",
    ),
    (r"^/applications/\{application_id\}/(skus|entitlements)", "MonetizationRoutes"),
    (r"^/skus", "MonetizationRoutes"),
    (r"^/applications", "ApplicationRoutes"),
    (r"^/oauth2", "ApplicationRoutes"),
    (r"^/webhooks/\{application_id\}", "InteractionRoutes"),
    (r"^/interactions", "InteractionRoutes"),
    (r"^/webhooks", "WebhookRoutes"),
    (r"^/stage-instances", "StageInstanceRoutes"),
    (r"^/invites", "InviteRoutes"),
    (r"^/lobbies", "LobbyRoutes"),
    (r"^/(stickers|sticker-packs)", "StickerRoutes"),
    (r"^/soundboard-default-sounds", "SoundboardRoutes"),
    (r"^/gateway", "GatewayRoutes"),
    (r"^/voice", "VoiceRoutes"),
]

DELEGATING = {"replace_roles": "GuildRoutes", "move_member": "GuildRoutes"}


def expected_mixin(path: str) -> str:
    for pattern, mixin in RESOURCE_BY_PATH:
        if re.match(pattern, path):
            return mixin
    pytest.fail(f"No resource declared for {path}")


def mixins() -> list[type]:
    return [getattr(routes, name) for name in routes.__all__]


def endpoints() -> list[tuple[type, str]]:
    return [
        (cls, name)
        for cls in mixins()
        for name, member in vars(cls).items()
        if inspect.isfunction(member) and not name.startswith("_")
    ]


def argument_for(name: str, annotation: str) -> Any:
    if name == "sound":
        return SimpleNamespace(id=1, guild_id=2)
    if "File" in annotation:
        return (
            [] if annotation.startswith(("Sequence", "list")) else File(BytesIO(b"x"))
        )
    if annotation.startswith(("list", "SnowflakeList", "Sequence")):
        return []
    if annotation.startswith("dict"):
        return {}
    if "bool" in annotation:
        return False
    if "bytes" in annotation:
        return b"x"
    if re.search(r"\b(Snowflake|int)\b", annotation):
        return 1
    if re.search(r"\bstr\b", annotation):
        return "s"
    return {}


def arguments(function: Callable[..., Any]) -> tuple[list[Any], dict[str, Any]]:
    args: list[Any] = []
    kwargs: dict[str, Any] = {}
    for parameter in list(inspect.signature(function).parameters.values())[1:]:
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.name == "reason":
            kwargs["reason"] = "r"
            continue
        if parameter.default is not parameter.empty:
            continue
        value = argument_for(parameter.name, str(parameter.annotation))
        if parameter.kind is parameter.POSITIONAL_ONLY:
            args.append(value)
        else:
            kwargs[parameter.name] = value
    return args, kwargs


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[Route, dict[str, Any]]] = []

    async def __call__(self, route: Route, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((route, kwargs))
        return {"url": "wss://gateway.discord.gg", "shards": 1}


CASES = endpoints()
IDS = [f"{cls.__name__}.{name}" for cls, name in CASES]


def test_every_endpoint_was_discovered() -> None:
    assert len(CASES) >= 180
    assert len({name for _, name in CASES}) == len(CASES)


def test_http_client_composes_every_mixin() -> None:
    assert all(issubclass(HTTPClient, mixin) for mixin in mixins())
    for cls, name in CASES:
        assert getattr(HTTPClient, name) is vars(cls)[name]


@pytest.mark.parametrize(("cls", "name"), CASES, ids=IDS)
async def test_endpoint(cls: type, name: str) -> None:
    http = HTTPClient()
    recorder = Recorder()
    http.request = recorder  # pyright: ignore[reportAttributeAccessIssue]
    function = vars(cls)[name]
    args, kwargs = arguments(function)

    await getattr(http, name)(*args, **kwargs)

    assert len(recorder.calls) == 1
    route, options = recorder.calls[0]
    assert isinstance(route, Route)
    assert route.method in METHODS
    assert "{" not in route.url
    assert "}" not in route.url
    accepts_reason = "reason" in inspect.signature(function).parameters
    assert (options.get("reason") == "r") is accepts_reason
    if name in {"get_gateway", "get_bot_gateway"}:
        assert cls.__name__ == "GatewayRoutes"
    elif name in DELEGATING:
        assert cls.__name__ == DELEGATING[name]
    else:
        assert cls.__name__ == expected_mixin(route.path)
