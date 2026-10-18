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

"""Discord API route definition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import quote as _uriquote

if TYPE_CHECKING:
    from ..types.snowflake import Snowflake

__all__ = ("API_VERSION", "Route")

API_VERSION: int = 10


class Route:
    """A Discord API route.

    Parameters
    ----------
    method: :class:`str`
        The HTTP method.
    path: :class:`str`
        The path template, relative to the API base URL.
    **parameters
        The values of the path template placeholders.
    """

    API_BASE_URL: str = "https://discord.com/api/v{API_VERSION}"

    def __init__(self, method: str, path: str, **parameters: Any) -> None:
        self.path: str = path
        self.method: str = method
        url = self.base + self.path
        if parameters:
            url = url.format_map(
                {
                    k: _uriquote(v) if isinstance(v, str) else v
                    for k, v in parameters.items()
                }
            )
        self.url: str = url

        # major parameters:
        self.channel_id: Snowflake | None = parameters.get("channel_id")
        self.guild_id: Snowflake | None = parameters.get("guild_id")
        self.webhook_id: Snowflake | None = parameters.get("webhook_id")
        self.webhook_token: str | None = parameters.get("webhook_token")

    @property
    def base(self) -> str:
        """The base URL of the API."""
        return self.API_BASE_URL.format(API_VERSION=API_VERSION)

    @property
    def major_parameters(self) -> str:
        """The major parameters identifying the rate limit scope."""
        return (
            f"{self.channel_id}:{self.guild_id}:{self.webhook_id}:{self.webhook_token}"
        )

    @property
    def bucket(self) -> str:
        """The key of the rate limit bucket of this route."""
        return f"{self.major_parameters}:{self.path}"
