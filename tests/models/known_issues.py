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

from dataclasses import dataclass


@dataclass(frozen=True)
class KnownIssue:
    case: str
    reason: str
    check: str = "*"
    variant: str = ""


@dataclass(frozen=True)
class PropertyIssue:
    cls: str
    name: str
    reason: str


KNOWN_ISSUES: list[KnownIssue] = []

PROPERTY_ISSUES: list[PropertyIssue] = []

UNTESTED: dict[str, str] = {
    "discord.activity.Spotify": "__init__(self, **data) takes untyped keyword arguments",
    "discord.appinfo.IntegrationTypesConfig.from_payload": (
        "payload annotated as a plain dict, no TypedDict to generate from"
    ),
    "discord.interactions.AuthorizingIntegrationOwners": (
        "payload annotated as dict[str, Any], no TypedDict to generate from"
    ),
    "discord.opus.Decoder.packet_get_samples_per_frame": "operates on raw opus bytes",
    "discord.sinks.core.RawData": "operates on raw voice packets, payload unannotated",
    "discord.webhook.async_.Webhook._as_follower": (
        "payload unannotated and needs a live HTTP session"
    ),
}
