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
import email
import email.policy
import inspect
import json
import re
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlsplit

import aiohttp
import aioresponses.core
import pytest
import requests
import responses
from aiohttp import ClientResponse
from aioresponses import aioresponses as aioresponses_mock
from urllib3.exceptions import ProtocolError

from discord.webhook import async_, sync

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

WEBHOOK_ID = 123456789012345678
TOKEN = "t" * 64
BOT_TOKEN = "bot-token"  # noqa: S105
BASE = "https://discord.com/api/v10"
HOOK = f"/webhooks/{WEBHOOK_ID}/{TOKEN}"
APP_HOOK = f"/webhooks/{WEBHOOK_ID}"
VIA = {"Via": "1.1 google"}

MESSAGE = {
    "id": "111",
    "channel_id": "222",
    "content": "hi",
    "author": {
        "id": "5",
        "username": "hook",
        "discriminator": "0",
        "avatar": None,
        "bot": True,
    },
    "attachments": [],
    "embeds": [],
    "pinned": False,
    "mention_everyone": False,
    "tts": False,
    "type": 0,
    "timestamp": "2024-01-01T00:00:00+00:00",
    "edited_timestamp": None,
    "flags": 0,
    "mentions": [],
    "mention_roles": [],
    "webhook_id": "5",
}
WEBHOOK = {
    "id": str(WEBHOOK_ID),
    "type": 1,
    "name": "hook",
    "channel_id": "222",
    "guild_id": "333",
    "token": TOKEN,
}


class _MockedResponse(ClientResponse):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
        super().__init__(*args, **kwargs)


@pytest.fixture(autouse=True)
def _aioresponses_supports_new_aiohttp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aioresponses.core, "ClientResponse", _MockedResponse)


@dataclass
class Call:
    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    json: Any = None
    form: dict[str, tuple[str | None, bytes]] | None = None

    @property
    def payload(self) -> Any:
        if self.form is not None:
            return json.loads(self.form["payload_json"][1])
        return self.json


def _split(url: str) -> tuple[str, dict[str, str]]:
    parts = urlsplit(url)
    return parts.path.removeprefix("/api/v10"), dict(parse_qsl(parts.query))


def _pattern(path: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(BASE + path)}(\?.*)?$")


def _error(errno: int) -> OSError:
    return ConnectionResetError(errno, "Connection reset by peer")


class Transport:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.sleeps: list[float] = []

    @property
    def calls(self) -> list[Call]:
        raise NotImplementedError

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def reply(
        self,
        method: str,
        path: str,
        *,
        status: int = 200,
        json: Any = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        times: int = 1,
    ) -> None:
        raise NotImplementedError

    def reset(self, method: str, path: str, errno: int = 104) -> None:
        raise NotImplementedError

    def partial(self, bot_token: str | None = None) -> Any:
        raise NotImplementedError

    def make(self, data: dict[str, Any], bot_token: str | None = None) -> Any:
        raise NotImplementedError

    def call(self, result: Any) -> Any:
        return result


class AsyncTransport(Transport):
    def __init__(self) -> None:
        super().__init__("async")
        self._calls: list[Call] = []
        self.loop = asyncio.new_event_loop()
        self.mock = aioresponses_mock()
        self.session: aiohttp.ClientSession = self.loop.run_until_complete(
            self._session()
        )

    @staticmethod
    async def _session() -> aiohttp.ClientSession:
        return aiohttp.ClientSession()

    def start(self) -> None:
        self.mock.start()

    def stop(self) -> None:
        self.mock.stop()
        self.loop.run_until_complete(self.session.close())
        self.loop.close()

    @property
    def calls(self) -> list[Call]:
        return self._calls

    def _record(self, url: Any, method: str, **kwargs: Any) -> None:
        path, query = _split(str(url))
        data = kwargs.get("data")
        call = Call(
            method,
            path,
            query,
            {k.lower(): v for k, v in (kwargs.get("headers") or {}).items()},
        )
        if isinstance(data, aiohttp.FormData):
            call.headers.setdefault("content-type", "multipart/form-data")
            call.form = {}
            for options, _, value in data._fields:
                content = value.getvalue() if hasattr(value, "getvalue") else value
                if isinstance(content, str):
                    content = content.encode()
                call.form[options["name"]] = (options.get("filename"), content)
        elif data is not None:
            call.json = json.loads(data)
        self._calls.append(call)

    def _recorder(self, method: str) -> Callable[..., None]:
        def record(url: Any, **kwargs: Any) -> None:
            self._record(url, method, **kwargs)

        return record

    def reply(
        self,
        method: str,
        path: str,
        *,
        status: int = 200,
        json: Any = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        times: int = 1,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if text is not None:
            kwargs.update(body=text, content_type="text/plain")
        elif json is not None:
            kwargs.update(payload=json)
        for _ in range(times):
            self.mock.add(
                _pattern(path),
                method,
                status=status,
                headers=headers,
                callback=self._recorder(method),
                **kwargs,
            )

    def reset(self, method: str, path: str, errno: int = 104) -> None:
        self.mock.add(
            _pattern(path),
            method,
            exception=aiohttp.ClientOSError(errno, "Connection reset by peer"),
            callback=self._recorder(method),
        )

    def partial(self, bot_token: str | None = None) -> async_.Webhook:
        return async_.Webhook.partial(
            WEBHOOK_ID, TOKEN, session=self.session, bot_token=bot_token
        )

    def make(
        self, data: dict[str, Any], bot_token: str | None = None
    ) -> async_.Webhook:
        return async_.Webhook(data, self.session, token=bot_token)  # type: ignore[arg-type]

    def call(self, result: Any) -> Any:
        if inspect.isawaitable(result):
            return self.loop.run_until_complete(result)
        return result


def _parse_multipart(content_type: str, body: bytes) -> dict[str, Any]:
    raw = b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body
    message = email.message_from_bytes(raw, policy=email.policy.HTTP)
    form: dict[str, Any] = {}
    for part in message.iter_parts():  # type: ignore[attr-defined]
        name = part.get_param("name", header="content-disposition")
        form[name] = (part.get_filename(), part.get_payload(decode=True))
    return form


class SyncTransport(Transport):
    def __init__(self) -> None:
        super().__init__("sync")
        self.mock = responses.RequestsMock(assert_all_requests_are_fired=False)
        self.session = requests.Session()

    def start(self) -> None:
        self.mock.start()

    @property
    def calls(self) -> list[Call]:
        return [self._record(call.request) for call in self.mock.calls]

    def stop(self) -> None:
        self.mock.stop()
        self.mock.reset()
        self.session.close()

    @staticmethod
    def _record(request: requests.PreparedRequest) -> Call:
        path, query = _split(request.url or "")
        headers = {k.lower(): v for k, v in request.headers.items()}
        call = Call(request.method or "", path, query, headers)
        body = request.body
        content_type = headers.get("content-type", "")
        if content_type.startswith("multipart/form-data"):
            assert isinstance(body, bytes)
            call.form = _parse_multipart(content_type, body)
        elif body:
            call.json = json.loads(body)
        return call

    def reply(
        self,
        method: str,
        path: str,
        *,
        status: int = 200,
        json: Any = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        times: int = 1,
    ) -> None:
        kwargs: dict[str, Any] = {}
        if text is not None:
            kwargs.update(body=text, content_type="text/plain")
        elif json is not None:
            kwargs.update(json=json)
        else:
            kwargs.update(body="", content_type="application/json")
        for _ in range(times):
            self.mock.add(
                method, _pattern(path), status=status, headers=headers, **kwargs
            )

    def reset(self, method: str, path: str, errno: int = 104) -> None:
        self.mock.add(
            method,
            _pattern(path),
            body=requests.ConnectionError(
                ProtocolError("Connection aborted.", _error(errno))
            ),
        )

    def partial(self, bot_token: str | None = None) -> sync.SyncWebhook:
        return sync.SyncWebhook.partial(
            WEBHOOK_ID, TOKEN, session=self.session, bot_token=bot_token
        )

    def make(
        self, data: dict[str, Any], bot_token: str | None = None
    ) -> sync.SyncWebhook:
        return sync.SyncWebhook(data, self.session, token=bot_token)  # type: ignore[arg-type]


@pytest.fixture(params=["async", "sync"])
def transport(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Transport]:
    sleeps: list[float] = []

    async def async_sleep(delay: float, result: Any = None) -> Any:
        sleeps.append(delay)
        return result

    def sync_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", async_sleep)
    monkeypatch.setattr(time, "sleep", sync_sleep)
    monkeypatch.setattr(sync, "_adapter", sync.WebhookAdapter())
    token = async_.async_context.set(async_.AsyncWebhookAdapter())

    active: Transport = (
        AsyncTransport() if request.param == "async" else SyncTransport()
    )
    active.sleeps = sleeps
    active.start()
    try:
        yield active
    finally:
        active.stop()
        async_.async_context.reset(token)


@pytest.fixture
def transport_sync(monkeypatch: pytest.MonkeyPatch) -> Iterator[SyncTransport]:
    monkeypatch.setattr(sync, "_adapter", sync.WebhookAdapter())
    active = SyncTransport()
    active.start()
    try:
        yield active
    finally:
        active.stop()
