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

"""Invite target user endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from discord import Object
from discord.invite import InviteTargetUsers

if TYPE_CHECKING:
    from discord.http import HTTPClient


@pytest.fixture
def requests() -> list[tuple[str, str, dict[str, Any]]]:
    return []


@pytest.fixture(autouse=True)
def _record(http: HTTPClient, requests: list[tuple[str, str, dict[str, Any]]]) -> None:
    async def request(route: Any, **kwargs: Any) -> None:
        requests.append((route.method, route.path, kwargs))

    http.request = request  # pyright: ignore[reportAttributeAccessIssue]


@pytest.fixture
def targets(http: HTTPClient) -> InviteTargetUsers:
    return InviteTargetUsers(state=SimpleNamespace(http=http), invite_code="abc")  # pyright: ignore[reportArgumentType]


async def test_add(
    targets: InviteTargetUsers, requests: list[tuple[str, str, dict[str, Any]]]
) -> None:
    await targets.add(Object(id=7))
    assert requests == [("PUT", "/invites/{invite_id}/target-users/{user_id}", {})]


async def test_remove(
    targets: InviteTargetUsers, requests: list[tuple[str, str, dict[str, Any]]]
) -> None:
    await targets.remove(Object(id=7))
    assert requests == [("DELETE", "/invites/{invite_id}/target-users/{user_id}", {})]


async def test_bulk_add(
    targets: InviteTargetUsers, requests: list[tuple[str, str, dict[str, Any]]]
) -> None:
    await targets.bulk_add([Object(id=1), Object(id=2)])
    assert requests == [
        (
            "POST",
            "/invites/{invite_id}/target-users/bulk-add",
            {"json": {"user_ids": ["1", "2"]}},
        )
    ]


async def test_bulk_remove(
    targets: InviteTargetUsers, requests: list[tuple[str, str, dict[str, Any]]]
) -> None:
    await targets.bulk_remove([Object(id=1)])
    assert requests == [
        (
            "POST",
            "/invites/{invite_id}/target-users/bulk-delete",
            {"json": {"user_ids": ["1"]}},
        )
    ]


async def test_bulk_limit(targets: InviteTargetUsers) -> None:
    users = [Object(id=i) for i in range(1001)]
    with pytest.raises(ValueError, match="1000"):
        await targets.bulk_add(users)
    with pytest.raises(ValueError, match="1000"):
        await targets.bulk_remove(users)
    await targets.bulk_add(users[:1000])


async def test_urls_use_the_invite_code(
    targets: InviteTargetUsers, http: HTTPClient
) -> None:
    urls: list[str] = []

    async def request(route: Any, **_: Any) -> None:
        urls.append(route.url)

    http.request = request  # pyright: ignore[reportAttributeAccessIssue]
    await targets.add(Object(id=7))
    await targets.bulk_add([Object(id=7)])
    assert urls == [
        "https://discord.com/api/v10/invites/abc/target-users/7",
        "https://discord.com/api/v10/invites/abc/target-users/bulk-add",
    ]
