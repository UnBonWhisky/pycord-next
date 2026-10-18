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

import copy
import json
from io import BytesIO
from typing import TYPE_CHECKING, Any

import pytest

from discord.file import File, VoiceMessage
from discord.http.multipart import message_payload, multipart_form

if TYPE_CHECKING:
    from discord.http import Route


def payload_of(form: list[dict[str, Any]]) -> dict[str, Any]:
    assert form[0]["name"] == "payload_json"
    return json.loads(form[0]["value"])


def test_files_are_attached_in_order() -> None:
    first = File(BytesIO(b"a"), "a.txt", description="first")
    second = File(BytesIO(b"b"), "b.txt")

    form = multipart_form({"content": "hi"}, [first, second])

    assert payload_of(form) == {
        "content": "hi",
        "attachments": [
            {"id": 0, "filename": "a.txt", "description": "first"},
            {"id": 1, "filename": "b.txt", "description": None},
        ],
    }
    assert [f["name"] for f in form[1:]] == ["files[0]", "files[1]"]
    assert form[1]["value"] is first.fp
    assert form[2]["filename"] == "b.txt"
    assert form[1]["content_type"] == "application/octet-stream"


def test_payload_is_not_mutated() -> None:
    existing = [{"id": 123}]
    payload = {"content": "hi", "attachments": existing}
    before = copy.deepcopy(payload)

    form = multipart_form(payload, [File(BytesIO(b"a"), "a.txt")])

    assert payload == before
    assert payload["attachments"] is existing
    assert payload_of(form)["attachments"] == [
        {"id": 123},
        {"id": 0, "filename": "a.txt", "description": None},
    ]


def test_voice_message_carries_its_waveform() -> None:
    voice = VoiceMessage(
        BytesIO(b"ogg"), "voice.ogg", waveform="AAA=", duration_secs=1.5
    )

    form = multipart_form({}, [voice])

    assert payload_of(form)["attachments"] == [
        {
            "id": 0,
            "filename": "voice.ogg",
            "description": None,
            "waveform": "AAA=",
            "duration_secs": 1.5,
        }
    ]


def test_single_file_field_without_attachments() -> None:
    file = File(BytesIO(b"a"), "a.txt")

    form = multipart_form({"content": "hi"}, [file], field="file", attach=False)

    assert payload_of(form) == {"content": "hi"}
    assert [f["name"] for f in form] == ["payload_json", "file"]


def test_no_files() -> None:
    form = multipart_form({"content": "hi"}, [])

    assert len(form) == 1
    assert payload_of(form) == {"content": "hi", "attachments": []}


def test_message_payload_leaves_out_unset_fields() -> None:
    assert message_payload() == {}
    assert message_payload(content="", embeds=[], flags=0) == {}


def test_message_payload_keeps_a_zero_nonce() -> None:
    assert message_payload(nonce=0) == {"nonce": 0}
    assert message_payload(nonce="abc") == {"nonce": "abc"}


def test_message_payload_merges_embed_and_embeds() -> None:
    single: Any = {"title": "one"}
    others: list[Any] = [{"title": "two"}, {"title": "three"}]

    assert message_payload(embed=single)["embeds"] == [single]
    assert message_payload(embeds=others)["embeds"] == others
    assert message_payload(embed=single, embeds=others)["embeds"] == [single, *others]
    assert others == [{"title": "two"}, {"title": "three"}]


def test_message_payload_renames_stickers() -> None:
    payload = message_payload(stickers=[{"id": "1"}], enforce_nonce=True)  # type: ignore[list-item]

    assert payload == {"sticker_ids": [{"id": "1"}], "enforce_nonce": True}


class Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[Route, dict[str, Any]]] = []

    async def __call__(self, route: Route, **kwargs: Any) -> None:
        self.calls.append((route, kwargs))


@pytest.fixture
def recorder(client: Any) -> Recorder:
    recorder = Recorder()
    client.request = recorder
    return recorder


async def test_send_files_builds_a_multipart_request(
    client: Any, recorder: Recorder
) -> None:
    file = File(BytesIO(b"a"), "a.txt")

    await client.send_files(
        5, files=[file], content="hi", tts=True, nonce=0, embed={"title": "t"}
    )

    ((route, kwargs),) = recorder.calls
    assert route.url.endswith("/channels/5/messages")
    assert kwargs["files"] == [file]
    assert payload_of(kwargs["form"]) == {
        "tts": True,
        "content": "hi",
        "nonce": 0,
        "embeds": [{"title": "t"}],
        "attachments": [{"id": 0, "filename": "a.txt", "description": None}],
    }


async def test_edit_files_keeps_and_extends_attachments(
    client: Any, recorder: Recorder
) -> None:
    existing = [{"id": 9}]

    await client.edit_files(
        5,
        6,
        [File(BytesIO(b"a"), "a.txt")],
        attachments=existing,
        content="edited",
        ignored=1,
    )

    ((route, kwargs),) = recorder.calls
    assert route.method == "PATCH"
    assert route.path == "/channels/{channel_id}/messages/{message_id}"
    assert existing == [{"id": 9}]
    assert payload_of(kwargs["form"]) == {
        "content": "edited",
        "attachments": [
            {"id": 9},
            {"id": 0, "filename": "a.txt", "description": None},
        ],
    }


async def test_forum_thread_uploads_files_with_retry_support(
    client: Any, recorder: Recorder
) -> None:
    file = File(BytesIO(b"a"), "a.txt")

    await client.start_forum_thread(
        5,
        "hello",
        name="thread",
        auto_archive_duration=60,
        rate_limit_per_user=0,
        files=[file],
        reason="r",
    )

    ((_, kwargs),) = recorder.calls
    assert kwargs["files"] == [file]
    assert kwargs["reason"] == "r"
    body = payload_of(kwargs["form"])
    assert body["message"] == {"content": "hello"}
    assert body["attachments"][0]["filename"] == "a.txt"


async def test_followup_message_without_files(client: Any, recorder: Recorder) -> None:
    await client.create_followup_message(1, "token", content="hi")

    ((route, kwargs),) = recorder.calls
    assert route.method == "POST"
    assert payload_of(kwargs["form"]) == {
        "tts": False,
        "content": "hi",
        "attachments": [],
    }


async def test_edit_webhook_message_uses_a_single_file_field(
    client: Any, recorder: Recorder
) -> None:
    file = File(BytesIO(b"a"), "a.txt")

    await client.edit_original_interaction_response(1, "token", file=file, content="hi")

    ((_, kwargs),) = recorder.calls
    assert kwargs["files"] == [file]
    assert [f["name"] for f in kwargs["form"]] == ["payload_json", "file"]
    assert payload_of(kwargs["form"]) == {"content": "hi"}
