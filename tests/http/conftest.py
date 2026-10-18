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

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import aioresponses.core
import pytest
import pytest_asyncio
from aiohttp import ClientResponse

from discord.http import HTTPClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

BASE_URL = "https://discord.com/api/v10"


class _MockedResponse(ClientResponse):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stream_writer", SimpleNamespace(output_size=0))
        super().__init__(*args, **kwargs)


@pytest.fixture(autouse=True)
def _aioresponses_supports_new_aiohttp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aioresponses.core, "ClientResponse", _MockedResponse)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[HTTPClient]:
    http = HTTPClient()
    http.token = "token"  # noqa: S105
    http.recreate()
    yield http
    await http.close()
