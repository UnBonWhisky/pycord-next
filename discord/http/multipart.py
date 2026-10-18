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

"""Builders for JSON message payloads and multipart uploads."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .. import utils
from ..file import VoiceMessage

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from ..file import File
    from ..types import (
        components as components_,
        embed,
        message,
        poll as poll_,
    )
    from ..types.snowflake import Snowflake

__all__ = ("message_payload", "multipart_form")


def message_payload(
    *,
    content: str | None = None,
    embed: embed.Embed | None = None,
    embeds: Iterable[embed.Embed | None] | None = None,
    nonce: int | str | None = None,
    enforce_nonce: bool | None = None,
    allowed_mentions: message.AllowedMentions | None = None,
    message_reference: message.MessageReference | None = None,
    stickers: Sequence[Snowflake] | None = None,
    components: list[components_.Component] | None = None,
    flags: int | None = None,
    poll: poll_.Poll | None = None,
    shared_client_theme: message.SharedClientTheme | None = None,
) -> dict[str, Any]:
    """Build the JSON body of a message, leaving out every unset field."""
    payload: dict[str, Any] = {}
    if content:
        payload["content"] = content
    all_embeds = [*([embed] if embed else []), *(embeds or ())]
    if all_embeds:
        payload["embeds"] = all_embeds
    if nonce is not None:
        payload["nonce"] = nonce
    if enforce_nonce:
        payload["enforce_nonce"] = enforce_nonce
    if allowed_mentions:
        payload["allowed_mentions"] = allowed_mentions
    if message_reference:
        payload["message_reference"] = message_reference
    if components:
        payload["components"] = components
    if stickers:
        payload["sticker_ids"] = stickers
    if flags:
        payload["flags"] = flags
    if poll:
        payload["poll"] = poll
    if shared_client_theme:
        payload["shared_client_theme"] = shared_client_theme
    return payload


def multipart_form(
    payload: Mapping[str, Any],
    files: Sequence[File],
    *,
    field: str = "files[{index}]",
    attach: bool = True,
    section: str | None = None,
) -> list[dict[str, Any]]:
    """Build the form fields of a ``payload_json`` plus files upload.

    The payload is never modified. With ``attach``, the metadata of every file is
    appended to the ``attachments`` of the payload, or of its ``section`` key when
    given.
    """
    body = dict(payload)
    form: list[dict[str, Any]] = [{"name": "payload_json"}]
    attachments: list[dict[str, Any]] = []
    for index, file in enumerate(files):
        attachment: dict[str, Any] = {
            "id": index,
            "filename": file.filename,
            "description": file.description,
        }
        if isinstance(file, VoiceMessage):
            attachment.update(
                waveform=file.waveform,
                duration_secs=file.duration_secs,
            )
        attachments.append(attachment)
        form.append(
            {
                "name": field.format(index=index),
                "value": file.fp,
                "filename": file.filename,
                "content_type": "application/octet-stream",
            }
        )
    if attach and section is None:
        body["attachments"] = [*body.get("attachments", ()), *attachments]
    elif attach and section is not None:
        inner = dict(body[section])
        inner["attachments"] = [*inner.get("attachments", ()), *attachments]
        body[section] = inner
    form[0]["value"] = utils._to_json(body)
    return form
