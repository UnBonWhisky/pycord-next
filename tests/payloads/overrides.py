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

from collections.abc import Callable
from typing import Any

from discord.types import (
    appinfo,
    channel,
    guild,
    interactions,
    message,
    onboarding,
    threads,
    welcome_screen,
)

Override = Callable[[dict[str, Any]], dict[str, Any]]

GUILD_ID = "1100000000000000001"
CHANNEL_ID = "1100000000000000002"
ROLE_ID = "1100000000000000003"


def _message(payload: dict[str, Any]) -> dict[str, Any]:
    payload["channel_id"] = CHANNEL_ID
    if "guild_id" in payload:
        payload["guild_id"] = GUILD_ID
    if "message_reference" in payload:
        payload["message_reference"]["channel_id"] = CHANNEL_ID
    return payload


def _guild(payload: dict[str, Any]) -> dict[str, Any]:
    payload["id"] = GUILD_ID
    if payload.get("roles"):
        payload["roles"][0]["id"] = ROLE_ID
    return payload


def _voice_effect(payload: dict[str, Any]) -> dict[str, Any]:
    payload["guild_id"] = GUILD_ID
    payload["channel_id"] = CHANNEL_ID
    return payload


def _thread(payload: dict[str, Any]) -> dict[str, Any]:
    payload["parent_id"] = CHANNEL_ID
    return payload


def _prompt_option(payload: dict[str, Any]) -> dict[str, Any]:
    if "channel_ids" in payload:
        payload["channel_ids"] = [CHANNEL_ID]
    if "role_ids" in payload:
        payload["role_ids"] = [ROLE_ID]
    return payload


def _welcome_channel(payload: dict[str, Any]) -> dict[str, Any]:
    payload["channel_id"] = CHANNEL_ID
    return payload


def _interaction(payload: dict[str, Any]) -> dict[str, Any]:
    if "channel_id" in payload:
        payload["channel_id"] = CHANNEL_ID
    if "guild_id" in payload:
        payload["guild_id"] = GUILD_ID
    if "channel" in payload:
        payload["channel"]["id"] = CHANNEL_ID
    return payload


def _shared_client_theme(payload: dict[str, Any]) -> dict[str, Any]:
    payload["colors"] = ["5865f2", "7258f2"]
    return payload


def _app_info(payload: dict[str, Any]) -> dict[str, Any]:
    if "flags_new" in payload:
        payload["flags_new"] = str(1 << 40)
    return payload


OVERRIDES: dict[Any, Override] = {
    appinfo.AppInfo: _app_info,
    channel.VoiceChannelEffectSendEvent: _voice_effect,
    threads.Thread: _thread,
    onboarding.PromptOption: _prompt_option,
    welcome_screen.WelcomeScreenChannel: _welcome_channel,
    interactions.Interaction: _interaction,
    message.Message: _message,
    message.SharedClientTheme: _shared_client_theme,
    guild.Guild: _guild,
}
