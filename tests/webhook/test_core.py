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

import inspect
import threading
from errno import ECONNRESET
from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pytest

import discord
from discord import HTTPException, InvalidArgument
from discord.file import File, VoiceMessage
from discord.http import Route
from discord.http.multipart import multipart_form
from discord.http.ratelimit import (
    backoff,
    exhausted_delay,
    is_connection_reset,
)
from discord.object import Object
from discord.webhook import _core, async_, sync
from discord.webhook._core import (
    Done,
    Execution,
    Retry,
    WebhookLimits,
    WebhookRequest,
    execute_request,
    handle_message_parameters,
    interaction_response_request,
    message_request,
    original_response_request,
    webhook_request,
)
from tests.webhook.conftest import (
    BOT_TOKEN,
    MESSAGE,
    TOKEN,
    WEBHOOK_ID,
)

DATA = {"id": str(WEBHOOK_ID), "type": 1, "token": TOKEN}
APPLICATION = {"id": str(WEBHOOK_ID), "type": 3, "token": TOKEN}


class StubView:
    timeout: float | None = None

    def __init__(self, *, v2: bool = False, dispatchable: bool = False) -> None:
        self.v2 = v2
        self.dispatchable = dispatchable

    def to_components(self) -> list[dict[str, Any]]:
        return [{"type": 1}]

    def is_components_v2(self) -> bool:
        return self.v2

    def is_dispatchable(self) -> bool:
        return self.dispatchable


def both(data: dict[str, Any], bot_token: str | None = None) -> list[Any]:
    return [
        async_.Webhook(data, None, token=bot_token),  # type: ignore[arg-type]
        sync.SyncWebhook(data, None, token=bot_token),  # type: ignore[arg-type]
    ]


def response(status: int, headers: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        status=status, headers=headers or {}, reason="reason", status_code=status
    )


def execution(**kwargs: Any) -> Execution:
    route = Route(
        "POST",
        "/webhooks/{webhook_id}/{webhook_token}",
        webhook_id=WEBHOOK_ID,
        webhook_token=TOKEN,
    )
    return Execution(WebhookRequest(route, **kwargs), WebhookLimits(threading.Lock))


def test_connection_reset_matches_every_platform_errno() -> None:
    assert all(
        is_connection_reset(OSError(code, "reset")) for code in (ECONNRESET, 54, 10054)
    )
    assert not is_connection_reset(OSError(111, "refused"))
    assert not is_connection_reset(ValueError("nope"))


def test_connection_reset_is_found_in_wrapped_errors() -> None:
    inner = ConnectionResetError(ECONNRESET, "reset")
    by_args = OSError(Exception("outer", inner))
    by_args.errno = None
    by_cause = RuntimeError("wrapper")
    by_cause.__cause__ = inner
    by_context = RuntimeError("wrapper")
    by_context.__context__ = inner

    assert is_connection_reset(by_args)
    assert is_connection_reset(by_cause)
    assert is_connection_reset(by_context)


def test_connection_reset_handles_cycles() -> None:
    first = RuntimeError("first")
    second = RuntimeError("second")
    first.__cause__ = second
    second.__cause__ = first

    assert not is_connection_reset(first)


def test_backoff() -> None:
    assert [backoff(attempt) for attempt in range(4)] == [1, 3, 5, 7]


def test_exhausted_delay() -> None:
    empty = SimpleNamespace(
        headers={"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset-After": "1.5"}
    )
    room = SimpleNamespace(headers={"X-Ratelimit-Remaining": "3"})

    assert exhausted_delay(empty, 200) == 1.5
    assert exhausted_delay(empty, 429) is None
    assert exhausted_delay(room, 200) is None
    assert exhausted_delay(SimpleNamespace(headers={}), 200) is None


def test_locks_are_shared_by_webhook_and_across_threads() -> None:
    limits = WebhookLimits(threading.Lock)
    route = webhook_request("GET", 1, "a", authenticated=False).route
    other = webhook_request("GET", 2, "a", authenticated=False).route
    found: list[Any] = []
    thread = threading.Thread(target=lambda: found.append(limits.lock_for(route)))
    thread.start()
    thread.join()

    assert found[0] is limits.lock_for(route)
    assert limits.lock_for(route) is not limits.lock_for(other)


def test_global_limit_expires() -> None:
    limits = WebhookLimits(threading.Lock)
    assert limits.global_delay() == 0

    limits.block(30)
    assert 29 < limits.global_delay() <= 30
    limits.block(1)
    assert limits.global_delay() > 29


def test_the_sync_adapter_is_shared_by_every_thread() -> None:
    seen: list[Any] = []
    thread = threading.Thread(target=lambda: seen.append(sync._adapter))
    thread.start()
    thread.join()

    assert seen[0] is sync._adapter


def test_execution_headers_and_body() -> None:
    run = execution(payload={"content": "hi"}, reason="café", auth_token="t")  # noqa: S106  # nosec B106

    assert run.headers == {
        "Content-Type": "application/json",
        "Authorization": "Bot t",
        "X-Audit-Log-Reason": "caf%C3%A9",
    }
    assert run.body == '{"content":"hi"}'
    assert execution().body is None
    assert execution().headers == {}


def test_execution_success_decodes_json() -> None:
    run = execution()

    done = run.handle(
        response(200, {"Content-Type": "application/json"}), '{"a": 1}', 0
    )
    text = run.handle(response(200, {"Content-Type": "text/plain"}), "plain", 0)
    empty = run.handle(response(204), "", 0)

    assert done == Done({"a": 1})
    assert text == Done("plain")
    assert empty == Done(None)


def test_execution_429_policy() -> None:
    run = execution()
    json_type = {"Content-Type": "application/json", "Via": "1.1 google"}

    retry = run.handle(response(429, json_type), '{"retry_after": 2}', 0)
    assert retry == Retry(2.0)
    assert run.limits.global_delay() == 0

    run.handle(response(429, json_type), '{"retry_after": 4, "global": true}', 0)
    assert 3 < run.limits.global_delay() <= 4

    with pytest.raises(HTTPException):
        run.handle(response(429, {"Content-Type": "application/json"}), "{}", 0)


def test_execution_5xx_policy() -> None:
    run = execution()

    assert run.handle(response(502), "", 0) == Retry(1)
    assert run.handle(response(502), "", 3) == Retry(7)
    with pytest.raises(discord.DiscordServerError):
        run.handle(response(502), "", 4)


def test_execution_connection_errors() -> None:
    run = execution()
    reset = ConnectionResetError(ECONNRESET, "reset")

    assert run.connection_error(reset, 0) == Retry(1)
    assert run.connection_error(reset, 4) is None
    assert run.connection_error(OSError(111, "refused"), 0) is None


def test_execution_give_up_without_a_response() -> None:
    with pytest.raises(RuntimeError):
        execution().give_up()


def test_execution_remembers_an_exhausted_bucket() -> None:
    run = execution()

    run.handle(
        response(200, {"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset-After": "3"}),
        "",
        0,
    )

    assert run.hold == 3


def test_webhook_request_routes() -> None:
    plain = webhook_request("PATCH", 1, "tok", authenticated=False, payload={"a": 1})
    bot = webhook_request("DELETE", 1, "bot", authenticated=True, reason="why")

    assert plain.route.url.endswith("/webhooks/1/tok")
    assert plain.auth_token is None
    assert plain.payload == {"a": 1}
    assert bot.route.url.endswith("/webhooks/1")
    assert (bot.auth_token, bot.reason) == ("bot", "why")


def test_execute_request_params() -> None:
    assert execute_request(1, "t").params == {"wait": 0}
    assert execute_request(
        1, "t", thread_id=5, with_components=False, wait=True
    ).params == {"wait": 1, "thread_id": 5, "with_components": 0}


def test_message_request() -> None:
    request = message_request("PATCH", 1, "t", 7, thread_id=5, with_components=True)

    assert request.route.url.endswith("/webhooks/1/t/messages/7")
    assert request.params == {"thread_id": 5, "with_components": 1}
    assert message_request("GET", 1, "t", 7).params == {}


def test_original_response_request() -> None:
    request = original_response_request("GET", 1, "t")

    assert request.route.url.endswith("/webhooks/1/t/messages/@original")


def test_interaction_response_request() -> None:
    file = File(BytesIO(b"x"), "a.txt")

    plain = interaction_response_request(1, "t", type=5)
    with_file = interaction_response_request(
        1, "t", type=4, data={"content": "hi"}, files=[file]
    )

    assert plain.route.url.endswith("/interactions/1/t/callback")
    assert plain.params == {"with_response": "true"}
    assert plain.multipart is not None
    assert [f["name"] for f in plain.multipart] == ["payload_json"]
    assert plain.multipart[0]["value"] == '{"type":5,"data":{}}'
    assert with_file.multipart is not None
    assert [f["name"] for f in with_file.multipart] == ["payload_json", "files[0]"]
    assert with_file.files == [file]
    assert (
        '"attachments":[{"id":0,"filename":"a.txt","description":null}]'
        in (with_file.multipart[0]["value"])
    )


def test_multipart_form_section() -> None:
    payload = {"type": 4, "data": {"attachments": [{"id": 9}]}}

    form = multipart_form(payload, [File(BytesIO(b"x"), "a.txt")], section="data")

    assert payload == {"type": 4, "data": {"attachments": [{"id": 9}]}}
    assert '"data":{"attachments":[{"id":9},{"id":0' in form[0]["value"]
    assert '"type":4' in form[0]["value"]


def test_message_parameters_json() -> None:
    params = handle_message_parameters(
        "hi", embed=discord.Embed(title="e"), username="u", tts=True
    )

    assert params.multipart == []
    assert params.payload == {
        "content": "hi",
        "embeds": [{"type": "rich", "title": "e", "fields": []}],
        "tts": True,
        "username": "u",
        "flags": 0,
    }


def test_message_parameters_attachments_are_kept_next_to_new_files() -> None:
    kept = SimpleNamespace(to_dict=lambda: {"id": 77})

    params = handle_message_parameters(
        attachments=[kept],
        file=File(BytesIO(b"x"), "a.txt"),  # type: ignore[list-item]
    )

    assert params.payload is None
    assert params.multipart is not None
    assert [f["name"] for f in params.multipart] == ["payload_json", "files[0]"]
    assert '"attachments":[{"id":77},{"id":0' in params.multipart[0]["value"]

    only_kept = handle_message_parameters(attachments=[kept])  # type: ignore[list-item]
    assert only_kept.payload is not None
    assert only_kept.payload["attachments"] == [{"id": 77}]


def test_message_parameters_voice_message() -> None:
    params = handle_message_parameters(file=VoiceMessage(BytesIO(b"x"), "v.ogg"))

    assert params.multipart is not None
    assert '"flags":8192' in params.multipart[0]["value"]


def test_message_parameters_poll_and_view() -> None:
    poll = SimpleNamespace(to_dict=lambda: {"question": {"text": "?"}})

    params = handle_message_parameters(poll=poll, view=StubView())  # type: ignore[arg-type]

    assert params.payload is not None
    assert params.payload["poll"] == {"question": {"text": "?"}}
    assert params.payload["components"] == [{"type": 1}]
    assert handle_message_parameters(view=None).payload["components"] == []  # type: ignore[index]
    with pytest.raises(TypeError):
        handle_message_parameters("hi", view=StubView(v2=True))  # type: ignore[arg-type]
    v2 = handle_message_parameters(view=StubView(v2=True))  # type: ignore[arg-type]
    assert v2.payload is not None
    assert v2.payload["flags"] == 1 << 15


@pytest.mark.parametrize("webhook", both(DATA))
def test_send_plan_is_the_same_for_both_webhooks(webhook: Any) -> None:
    poll = SimpleNamespace(to_dict=lambda: {"question": {"text": "?"}})

    plan = webhook._send_plan(
        "hi",
        poll=poll,
        view=StubView(),
        thread=Object(5),
        wait=True,
    )

    assert plan.wait is True
    request = plan.request
    assert (request.route.method, request.route.url.rsplit("/", 2)[-2:]) == (
        "POST",
        [str(WEBHOOK_ID), TOKEN],
    )
    assert request.params == {"wait": 1, "thread_id": 5, "with_components": 1}
    assert request.payload == {
        "content": "hi",
        "components": [{"type": 1}],
        "poll": {"question": {"text": "?"}},
        "tts": False,
        "flags": 0,
    }


@pytest.mark.parametrize("webhook", both(APPLICATION))
def test_send_plan_for_application_webhooks(webhook: Any) -> None:
    plan = webhook._send_plan("hi", ephemeral=True, view=StubView())

    assert plan.wait is True
    assert plan.request.params == {"wait": 1, "with_components": 0}
    assert plan.request.payload["flags"] == 64
    assert plan.request.payload["components"] == [{"type": 1}]


@pytest.mark.parametrize("webhook", both(DATA))
def test_send_plan_validation(webhook: Any) -> None:
    with pytest.raises(InvalidArgument):
        webhook._send_plan("hi", ephemeral=True)
    with pytest.raises(InvalidArgument):
        webhook._send_plan("hi", applied_tags=[Object(1)])
    with pytest.raises(InvalidArgument):
        webhook._send_plan("hi", thread=Object(1), thread_name="x")
    with pytest.raises(InvalidArgument):
        webhook._send_plan("hi", view=StubView(dispatchable=True))


@pytest.mark.parametrize("webhook", both(DATA))
def test_edit_message_request_is_the_same_for_both_webhooks(webhook: Any) -> None:
    request = webhook._edit_message_request(
        7, content="edited", view=StubView(), thread=Object(5)
    )

    assert request.route.method == "PATCH"
    assert request.route.url.endswith("/messages/7")
    assert request.params == {"thread_id": 5, "with_components": 1}
    assert request.payload["content"] == "edited"
    assert request.payload["components"] == [{"type": 1}]


@pytest.mark.parametrize("webhook", both(DATA, BOT_TOKEN))
def test_credentials(webhook: Any) -> None:
    assert webhook._credentials(True) == (BOT_TOKEN, True)
    assert webhook._credentials(False) == (TOKEN, False)


@pytest.mark.parametrize("webhook", both({"id": str(WEBHOOK_ID), "type": 1}))
def test_no_credentials(webhook: Any) -> None:
    for build in (
        lambda: webhook._credentials(True),
        lambda: webhook._delete_request(None, True),
        lambda: webhook._fetch_message_request(1, None),
    ):
        with pytest.raises(InvalidArgument):
            build()


class Tripwire:
    allowed_mentions = None

    @property
    def cache(self) -> Any:
        raise AssertionError("the sync webhook read the cache")

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the sync webhook used the state: {name}")


def test_the_sync_webhook_never_touches_the_state_cache(
    transport_sync: Any,
) -> None:
    transport_sync.reply("POST", f"/webhooks/{WEBHOOK_ID}/{TOKEN}", json=MESSAGE)
    transport_sync.reply(
        "GET", f"/webhooks/{WEBHOOK_ID}/{TOKEN}/messages/111", json=MESSAGE
    )
    wh = sync.SyncWebhook(DATA, transport_sync.session, state=Tripwire())  # type: ignore[arg-type]

    sent = wh.send("hi", wait=True)
    fetched = wh.fetch_message(111)

    assert (sent.id, fetched.id) == (111, 111)
    assert not isinstance(wh._state, async_._WebhookState)


def test_the_sync_webhook_has_no_coroutines() -> None:
    for name, member in inspect.getmembers(sync.SyncWebhook):
        assert not inspect.iscoroutinefunction(member), name
    assert not hasattr(sync.SyncWebhook, "get_guild")
    assert not hasattr(sync.SyncWebhook, "get_channel")
    assert inspect.iscoroutinefunction(async_.Webhook.get_guild)
    assert inspect.iscoroutinefunction(async_.Webhook.get_channel)
    assert not inspect.iscoroutinefunction(sync.SyncWebhookMessage.edit)
    assert not inspect.iscoroutinefunction(sync.SyncWebhookMessage.delete)


def test_the_sync_webhook_message_has_no_async_cache_getters() -> None:
    pycord_coroutines = {
        "delete",
        "edit",
        "publish",
        "pin",
        "unpin",
        "add_reaction",
        "remove_reaction",
        "clear_reaction",
        "clear_reactions",
        "create_thread",
        "reply",
        "forward_to",
        "end_poll",
    }
    getters = (
        "get_channel",
        "get_guild",
        "get_poll",
        "get_channel_mentions",
        "get_role_mentions",
        "get_clean_content",
        "get_system_content",
    )
    for name in getters:
        assert not hasattr(sync.SyncWebhookMessage, name), name
        assert inspect.iscoroutinefunction(getattr(discord.Message, name)), name
    assert not hasattr(sync.SyncWebhookMessage, "search_replies")
    assert hasattr(discord.Message, "search_replies")
    coroutines = {
        name
        for name in dir(sync.SyncWebhookMessage)
        if inspect.iscoroutinefunction(getattr(sync.SyncWebhookMessage, name, None))
    }
    assert coroutines <= pycord_coroutines
    assert issubclass(sync.SyncWebhookMessage, discord.Message)


def test_public_names_are_unchanged() -> None:
    assert {
        "Webhook",
        "WebhookMessage",
        "PartialWebhookChannel",
        "PartialWebhookGuild",
        "SyncWebhook",
        "SyncWebhookMessage",
    } <= set(dir(discord))
    assert _core.WebhookRequests in async_.BaseWebhook.__mro__
    assert issubclass(sync.SyncWebhook, async_.BaseWebhook)
