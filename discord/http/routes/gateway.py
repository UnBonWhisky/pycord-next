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

"""Discord API routes for the gateway resource."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...errors import GatewayNotFound, HTTPException
from ...gateway.models import GatewayInfo, SessionStartLimit
from ..base import HTTPBase
from ..route import API_VERSION, Route

if TYPE_CHECKING:
    from ...gateway.compression import GatewayCompression

__all__ = ("GatewayRoutes",)


def _gateway_url(url: str, encoding: str, compress: GatewayCompression | None) -> str:
    value = f"{url}?encoding={encoding}&v={API_VERSION}"
    if compress is not None:
        value += f"&compress={compress}"
    return value


class GatewayRoutes(HTTPBase):
    """Endpoints of the gateway resource."""

    async def get_gateway(
        self,
        *,
        encoding: str = "json",
        zlib: bool = True,
        compress: GatewayCompression | None = "zlib-stream",
    ) -> str:
        """Fetch the gateway URL."""
        try:
            data = await self.request(Route("GET", "/gateway"))
        except HTTPException as exc:
            raise GatewayNotFound from exc
        return _gateway_url(data["url"], encoding, compress if zlib else None)

    async def get_bot_gateway(
        self,
        *,
        encoding: str = "json",
        zlib: bool = True,
        compress: GatewayCompression | None = "zlib-stream",
    ) -> tuple[int, str]:
        """Fetch the gateway URL and the recommended shard count."""
        info = await self.get_bot_gateway_info(
            encoding=encoding, compress=compress if zlib else None
        )
        return info.shards, info.url

    async def get_bot_gateway_info(
        self,
        *,
        encoding: str = "json",
        compress: GatewayCompression | None = "zlib-stream",
    ) -> GatewayInfo:
        """Fetch the gateway URL, the recommended shard count and the session start limit."""
        try:
            data = await self.request(Route("GET", "/gateway/bot"))
        except HTTPException as exc:
            raise GatewayNotFound from exc

        return GatewayInfo(
            url=_gateway_url(data["url"], encoding, compress),
            shards=data["shards"],
            session_start_limit=(
                SessionStartLimit.from_payload(data["session_start_limit"])
                if "session_start_limit" in data
                else SessionStartLimit()
            ),
        )
