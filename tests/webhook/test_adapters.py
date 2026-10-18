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

from __future__ import annotations

from errno import ECONNRESET
from io import BytesIO
from typing import TYPE_CHECKING

import pytest
from requests import ConnectionError as RequestsConnectionError

import discord
from discord import (
    DiscordServerError,
    Forbidden,
    HTTPException,
    InvalidArgument,
    NotFound,
)
from discord.file import File
from discord.object import Object
from discord.webhook import SyncWebhook, SyncWebhookMessage, Webhook, WebhookMessage
from tests.webhook.conftest import (
    APP_HOOK,
    BOT_TOKEN,
    HOOK,
    MESSAGE,
    TOKEN,
    VIA,
    WEBHOOK,
    WEBHOOK_ID,
)

if TYPE_CHECKING:
    from tests.webhook.conftest import Transport

MESSAGE_PATH = f"{HOOK}/messages/111"
LIMITED = {"message": "You are being rate limited.", "retry_after": 1.5}
RESET_HEADERS = {"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset-After": "2.5"}


def message_class(transport: Transport) -> type:
    return WebhookMessage if transport.name == "async" else SyncWebhookMessage


def webhook_class(transport: Transport) -> type:
    return Webhook if transport.name == "async" else SyncWebhook


def test_send_content(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=204)
    wh = transport.partial()

    assert transport.call(wh.send("hi")) is None

    (call,) = transport.calls
    assert (call.method, call.path) == ("POST", HOOK)
    assert call.query == {"wait": "0", "with_components": "0"}
    assert call.payload == {"content": "hi", "tts": False, "flags": 0}
    assert call.headers["content-type"] == "application/json"
    assert "authorization" not in call.headers
    assert transport.sleeps == []


def test_send_wait_returns_the_message(transport: Transport) -> None:
    transport.reply("POST", HOOK, json=MESSAGE)
    wh = transport.partial()

    message = transport.call(wh.send("hi", wait=True))

    assert isinstance(message, message_class(transport))
    assert message.id == 111
    assert message.content == "hi"
    assert message.channel.id == 222
    assert transport.calls[0].query["wait"] == "1"


def test_send_options(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=204)
    wh = transport.partial()

    transport.call(
        wh.send(
            "hi",
            username="bot",
            avatar_url="https://example.com/a.png",
            tts=True,
            allowed_mentions=discord.AllowedMentions.none(),
            suppress_embeds=True,
        )
    )

    assert transport.calls[0].payload == {
        "content": "hi",
        "tts": True,
        "username": "bot",
        "avatar_url": "https://example.com/a.png",
        "allowed_mentions": {"parse": []},
        "flags": 4,
    }


def test_send_embeds(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=204, times=2)
    wh = transport.partial()

    transport.call(wh.send(embed=discord.Embed(title="one")))
    transport.call(wh.send(embeds=[discord.Embed(title="a"), discord.Embed(title="b")]))

    first, second = transport.calls
    assert [e["title"] for e in first.payload["embeds"]] == ["one"]
    assert [e["title"] for e in second.payload["embeds"]] == ["a", "b"]
    assert "content" not in first.payload


def test_send_embed_validation(transport: Transport) -> None:
    wh = transport.partial()

    with pytest.raises(InvalidArgument):
        transport.call(wh.send(embeds=[discord.Embed()] * 11))
    with pytest.raises(TypeError):
        transport.call(wh.send(embed=discord.Embed(), embeds=[discord.Embed()]))
    with pytest.raises(TypeError):
        transport.call(wh.send(file=File(BytesIO(b"x"), "x"), files=[]))
    assert transport.calls == []


def test_send_files(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=204)
    wh = transport.partial()
    files = [
        File(BytesIO(b"first"), "a.txt", description="d"),
        File(BytesIO(b"second"), "b.txt"),
    ]

    transport.call(wh.send("hi", files=files))

    (call,) = transport.calls
    assert call.json is None
    assert call.headers["content-type"].startswith("multipart/form-data")
    assert call.payload["attachments"] == [
        {"id": 0, "filename": "a.txt", "description": "d"},
        {"id": 1, "filename": "b.txt", "description": None},
    ]
    assert call.payload["content"] == "hi"
    assert call.form is not None
    assert call.form["files[0]"] == ("a.txt", b"first")
    assert call.form["files[1]"] == ("b.txt", b"second")


def test_send_voice_message_sets_the_flag(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=204)
    wh = transport.partial()
    voice = discord.file.VoiceMessage(BytesIO(b"ogg"), "voice.ogg", waveform="AAAA")

    transport.call(wh.send(file=voice))

    payload = transport.calls[0].payload
    assert payload["flags"] & (1 << 13)
    assert payload["attachments"][0]["waveform"] == "AAAA"


def test_send_thread(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=204, times=2)
    wh = transport.partial()

    transport.call(wh.send("hi", thread=Object(999)))
    transport.call(wh.send("hi", thread_name="topic"))

    in_thread, new_thread = transport.calls
    assert in_thread.query["thread_id"] == "999"
    assert "thread_name" not in in_thread.payload
    assert "thread_id" not in new_thread.query
    assert new_thread.payload["thread_name"] == "topic"


def test_send_thread_and_thread_name_are_exclusive(transport: Transport) -> None:
    wh = transport.partial()

    with pytest.raises(InvalidArgument):
        transport.call(wh.send("hi", thread=Object(1), thread_name="topic"))
    assert transport.calls == []


def test_send_needs_a_token(transport: Transport) -> None:
    wh = transport.make({"id": str(WEBHOOK_ID), "type": 1}, BOT_TOKEN)

    with pytest.raises(InvalidArgument):
        transport.call(wh.send("hi"))
    with pytest.raises(InvalidArgument):
        transport.call(wh.fetch_message(1))
    with pytest.raises(InvalidArgument):
        transport.call(wh.edit_message(1, content="x"))
    with pytest.raises(InvalidArgument):
        transport.call(wh.delete_message(1))
    assert transport.calls == []


def test_fetch(transport: Transport) -> None:
    transport.reply("GET", HOOK, json=WEBHOOK)
    wh = transport.partial()

    fetched = transport.call(wh.fetch())

    assert isinstance(fetched, webhook_class(transport))
    assert fetched.name == "hook"
    assert fetched.channel_id == 222
    (call,) = transport.calls
    assert (call.method, call.path) == ("GET", HOOK)
    assert "authorization" not in call.headers


def test_fetch_prefers_the_bot_token(transport: Transport) -> None:
    transport.reply("GET", APP_HOOK, json=WEBHOOK)
    transport.reply("GET", HOOK, json=WEBHOOK)
    wh = transport.partial(BOT_TOKEN)

    transport.call(wh.fetch())
    transport.call(wh.fetch(prefer_auth=False))

    authenticated, plain = transport.calls
    assert authenticated.path == APP_HOOK
    assert authenticated.headers["authorization"] == f"Bot {BOT_TOKEN}"
    assert plain.path == HOOK
    assert "authorization" not in plain.headers


def test_fetch_falls_back_to_the_bot_token(transport: Transport) -> None:
    transport.reply("GET", APP_HOOK, json=WEBHOOK)
    wh = transport.make({"id": str(WEBHOOK_ID), "type": 1}, BOT_TOKEN)

    transport.call(wh.fetch(prefer_auth=False))

    assert transport.calls[0].path == APP_HOOK


def test_fetch_without_credentials(transport: Transport) -> None:
    wh = transport.make({"id": str(WEBHOOK_ID), "type": 1})

    with pytest.raises(InvalidArgument):
        transport.call(wh.fetch())
    assert transport.calls == []


def test_edit(transport: Transport) -> None:
    transport.reply("PATCH", HOOK, json={**WEBHOOK, "name": "new"})
    wh = transport.partial()

    edited = transport.call(wh.edit(name="new", reason="why"))

    assert edited.name == "new"
    (call,) = transport.calls
    assert call.path == HOOK
    assert call.payload == {"name": "new"}
    assert call.headers["x-audit-log-reason"] == "why"


def test_edit_avatar(transport: Transport) -> None:
    transport.reply("PATCH", HOOK, json=WEBHOOK)
    wh = transport.partial()

    transport.call(wh.edit(avatar=None))

    assert transport.calls[0].payload == {"avatar": None}


def test_edit_channel_sends_a_single_authenticated_request(
    transport: Transport,
) -> None:
    transport.reply("PATCH", APP_HOOK, json=WEBHOOK)
    wh = transport.partial(BOT_TOKEN)

    transport.call(wh.edit(channel=Object(5)))

    (call,) = transport.calls
    assert call.path == APP_HOOK
    assert call.payload == {"channel_id": 5}
    assert call.headers["authorization"] == f"Bot {BOT_TOKEN}"


def test_edit_channel_needs_the_bot_token(transport: Transport) -> None:
    wh = transport.partial()

    with pytest.raises(InvalidArgument):
        transport.call(wh.edit(channel=Object(5)))
    assert transport.calls == []


def test_delete(transport: Transport) -> None:
    transport.reply("DELETE", HOOK, status=204)
    transport.reply("DELETE", APP_HOOK, status=204)
    wh = transport.partial(BOT_TOKEN)

    transport.call(wh.delete(reason="café ok", prefer_auth=False))
    transport.call(wh.delete())

    plain, authenticated = transport.calls
    assert plain.path == HOOK
    assert plain.headers["x-audit-log-reason"] == "caf%C3%A9 ok"
    assert authenticated.path == APP_HOOK
    assert authenticated.headers["authorization"] == f"Bot {BOT_TOKEN}"


def test_delete_falls_back_to_the_bot_token(transport: Transport) -> None:
    transport.reply("DELETE", APP_HOOK, status=204)
    wh = transport.make({"id": str(WEBHOOK_ID), "type": 1}, BOT_TOKEN)

    transport.call(wh.delete(prefer_auth=False))

    assert [c.path for c in transport.calls] == [APP_HOOK]


def test_fetch_message(transport: Transport) -> None:
    transport.reply("GET", MESSAGE_PATH, json=MESSAGE)
    wh = transport.partial()

    message = transport.call(wh.fetch_message(111, thread_id=9))

    assert isinstance(message, message_class(transport))
    assert message.id == 111
    assert message._thread_id == 9
    (call,) = transport.calls
    assert (call.method, call.query) == ("GET", {"thread_id": "9"})


def test_edit_message(transport: Transport) -> None:
    transport.reply("PATCH", MESSAGE_PATH, json={**MESSAGE, "content": "edited"})
    wh = transport.partial()

    message = transport.call(
        wh.edit_message(
            111,
            content="edited",
            embed=discord.Embed(title="t"),
            thread=Object(9),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    )

    assert message.content == "edited"
    (call,) = transport.calls
    assert call.query["thread_id"] == "9"
    assert call.payload["content"] == "edited"
    assert call.payload["embeds"][0]["title"] == "t"
    assert call.payload["allowed_mentions"] == {"parse": []}
    assert call.payload["flags"] == 0


def test_edit_message_with_files(transport: Transport) -> None:
    transport.reply("PATCH", MESSAGE_PATH, json=MESSAGE)
    wh = transport.partial()

    transport.call(wh.edit_message(111, file=File(BytesIO(b"data"), "a.txt")))

    (call,) = transport.calls
    assert call.form is not None
    assert call.form["files[0]"] == ("a.txt", b"data")
    assert call.payload["attachments"] == [
        {"id": 0, "filename": "a.txt", "description": None}
    ]


def test_edit_message_validation(transport: Transport) -> None:
    wh = transport.partial()

    with pytest.raises(TypeError):
        transport.call(wh.edit_message(1, embed=discord.Embed(), embeds=[]))
    assert transport.calls == []


def test_delete_message(transport: Transport) -> None:
    transport.reply("DELETE", MESSAGE_PATH, status=204)
    wh = transport.partial()

    assert transport.call(wh.delete_message(111, thread_id=9)) is None

    (call,) = transport.calls
    assert (call.method, call.path, call.query) == (
        "DELETE",
        MESSAGE_PATH,
        {"thread_id": "9"},
    )


def test_message_edit_and_delete(transport: Transport) -> None:
    transport.reply("POST", HOOK, json=MESSAGE)
    transport.reply("PATCH", MESSAGE_PATH, json={**MESSAGE, "content": "edited"})
    transport.reply("DELETE", MESSAGE_PATH, status=204)
    wh = transport.partial()
    message = transport.call(wh.send("hi", wait=True))

    edited = transport.call(message.edit(content="edited"))
    transport.call(message.delete())

    assert isinstance(edited, message_class(transport))
    assert edited.content == "edited"
    assert [c.method for c in transport.calls] == ["POST", "PATCH", "DELETE"]


def test_partial_and_from_url(transport: Transport) -> None:
    cls = webhook_class(transport)
    url = f"https://discord.com/api/webhooks/{WEBHOOK_ID}/{TOKEN}"
    session = transport.session  # type: ignore[attr-defined]

    from_url = cls.from_url(url, session=session, bot_token=BOT_TOKEN)

    assert (from_url.id, from_url.token, from_url.auth_token) == (
        WEBHOOK_ID,
        TOKEN,
        BOT_TOKEN,
    )
    assert from_url.url == url
    with pytest.raises(InvalidArgument):
        cls.from_url("https://example.com/hook", session=session)


@pytest.mark.parametrize(
    ("status", "error"),
    [(403, Forbidden), (404, NotFound), (400, HTTPException), (401, HTTPException)],
)
def test_error_mapping(transport: Transport, status: int, error: type) -> None:
    body = {"code": 50013, "message": "Missing Permissions"}
    transport.reply("POST", HOOK, status=status, json=body)
    wh = transport.partial()

    with pytest.raises(error) as caught:
        transport.call(wh.send("hi"))

    assert type(caught.value) is error
    assert caught.value.status == status
    assert caught.value.code == 50013
    assert caught.value.text == "Missing Permissions"
    assert len(transport.calls) == 1
    assert transport.sleeps == []


def test_error_with_a_plain_text_body(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=400, text="bad request")
    wh = transport.partial()

    with pytest.raises(HTTPException) as caught:
        transport.call(wh.send("hi"))

    assert caught.value.text == "bad request"
    assert caught.value.code == 0


def test_bucket_429_waits_retry_after(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=429, json=LIMITED, headers=VIA)
    transport.reply("POST", HOOK, status=204)
    wh = transport.partial()

    assert transport.call(wh.send("hi")) is None

    assert len(transport.calls) == 2
    assert transport.sleeps == [1.5]


def test_global_429_holds_back_the_next_request(transport: Transport) -> None:
    transport.reply(
        "POST",
        HOOK,
        status=429,
        json={**LIMITED, "retry_after": 2.0, "global": True},
        headers=VIA,
    )
    transport.reply("POST", HOOK, status=204)
    transport.reply("POST", HOOK, status=204)
    wh = transport.partial()

    transport.call(wh.send("one"))
    assert transport.sleeps == [2.0]
    transport.call(wh.send("two"))

    assert len(transport.sleeps) == 2
    assert transport.sleeps[1] == pytest.approx(2.0, abs=0.5)
    assert len(transport.calls) == 3


def test_bucket_429_does_not_block_other_requests(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=429, json=LIMITED, headers=VIA)
    transport.reply("POST", HOOK, status=204)
    transport.reply("POST", HOOK, status=204)
    wh = transport.partial()

    transport.call(wh.send("one"))
    transport.call(wh.send("two"))

    assert transport.sleeps == [1.5]


def test_cloudflare_429_is_not_retried(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=429, text="banned")
    wh = transport.partial()

    with pytest.raises(HTTPException) as caught:
        transport.call(wh.send("hi"))

    assert caught.value.status == 429
    assert len(transport.calls) == 1
    assert transport.sleeps == []


def test_429_without_a_json_body_is_not_retried(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=429, text="slow down", headers=VIA)
    wh = transport.partial()

    with pytest.raises(HTTPException):
        transport.call(wh.send("hi"))

    assert len(transport.calls) == 1


def test_429_gives_up_after_five_attempts(transport: Transport) -> None:
    for _ in range(5):
        transport.reply("POST", HOOK, status=429, json=LIMITED, headers=VIA)
    wh = transport.partial()

    with pytest.raises(HTTPException) as caught:
        transport.call(wh.send("hi"))

    assert caught.value.status == 429
    assert len(transport.calls) == 5
    assert transport.sleeps == [1.5] * 4


@pytest.mark.parametrize("status", [500, 502, 503, 504, 520])
def test_5xx_is_retried_with_a_backoff(transport: Transport, status: int) -> None:
    transport.reply("POST", HOOK, status=status, text="unavailable")
    transport.reply("POST", HOOK, status=status, text="unavailable")
    transport.reply("POST", HOOK, status=204)
    wh = transport.partial()

    assert transport.call(wh.send("hi")) is None

    assert len(transport.calls) == 3
    assert transport.sleeps == [1, 3]


def test_5xx_gives_up_after_five_attempts(transport: Transport) -> None:
    for _ in range(5):
        transport.reply("POST", HOOK, status=503, text="unavailable")
    wh = transport.partial()

    with pytest.raises(DiscordServerError) as caught:
        transport.call(wh.send("hi"))

    assert caught.value.status == 503
    assert len(transport.calls) == 5
    assert transport.sleeps == [1, 3, 5, 7]


@pytest.mark.parametrize("errno", sorted({ECONNRESET, 54, 10054}))
def test_connection_reset_is_retried(transport: Transport, errno: int) -> None:
    transport.reset("POST", HOOK, errno)
    transport.reply("POST", HOOK, status=204)
    wh = transport.partial()

    assert transport.call(wh.send("hi")) is None

    assert len(transport.calls) == 2
    assert transport.sleeps == [1]


def test_connection_reset_gives_up_after_five_attempts(transport: Transport) -> None:
    for _ in range(5):
        transport.reset("POST", HOOK)
    wh = transport.partial()

    with pytest.raises((OSError, RequestsConnectionError)):
        transport.call(wh.send("hi"))

    assert len(transport.calls) == 5
    assert transport.sleeps == [1, 3, 5, 7]


def test_other_connection_errors_are_not_retried(transport: Transport) -> None:
    transport.reset("POST", HOOK, errno=111)
    wh = transport.partial()

    with pytest.raises((OSError, RequestsConnectionError)):
        transport.call(wh.send("hi"))

    assert len(transport.calls) == 1
    assert transport.sleeps == []


def test_files_are_rewound_when_retrying(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=502, text="bad gateway")
    transport.reply("POST", HOOK, status=204)
    wh = transport.partial()

    transport.call(wh.send(file=File(BytesIO(b"data"), "a.txt")))

    first, second = transport.calls
    assert first.form is not None
    assert second.form is not None
    assert first.form["files[0]"] == second.form["files[0]"] == ("a.txt", b"data")


def test_exhausted_bucket_pauses_after_the_response(transport: Transport) -> None:
    transport.reply("POST", HOOK, status=204, headers=RESET_HEADERS)
    wh = transport.partial()

    transport.call(wh.send("hi"))

    assert transport.sleeps == [2.5]


def test_exhausted_bucket_pauses_after_an_error(transport: Transport) -> None:
    transport.reply(
        "POST", HOOK, status=403, json={"message": "no"}, headers=RESET_HEADERS
    )
    wh = transport.partial()

    with pytest.raises(Forbidden):
        transport.call(wh.send("hi"))

    assert transport.sleeps == [2.5]


def test_json_with_a_charset_is_decoded(transport: Transport) -> None:
    transport.reply(
        "GET",
        HOOK,
        json=WEBHOOK,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    wh = transport.partial()

    assert transport.call(wh.fetch()).name == "hook"
