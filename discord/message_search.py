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

"""Types used to search the messages of a guild."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Any

from .enums import SearchEmbedType, SearchSortMode, SearchSortOrder
from .errors import DiscordException

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .abc import Snowflake
    from .types.message import SearchAuthorType, SearchHasType

__all__ = (
    "SearchAuthors",
    "SearchEmbedType",
    "SearchHas",
    "SearchIndexNotReady",
    "SearchSortMode",
    "SearchSortOrder",
)


@dataclass(frozen=True, kw_only=True)
class SearchAuthors:
    """Filters a message search by the kind of account that sent the messages.

    ``True`` keeps messages sent by that kind of author, ``False`` leaves
    them out and ``None`` (the default) does not filter on it.

    .. versionadded:: 3.0

    Attributes
    ----------
    user: Optional[:class:`bool`]
        Messages sent by user accounts.
    bot: Optional[:class:`bool`]
        Messages sent by bot accounts.
    webhook: Optional[:class:`bool`]
        Messages sent by webhooks.
    """

    user: bool | None = None
    bot: bool | None = None
    webhook: bool | None = None

    def to_query(self) -> list[SearchAuthorType | str]:
        """The values of the ``author_type`` query parameter."""
        return _query(self)


@dataclass(frozen=True, kw_only=True)
class SearchHas:
    """Filters a message search by what the messages contain.

    ``True`` keeps messages that have it, ``False`` leaves them out and
    ``None`` (the default) does not filter on it.

    .. versionadded:: 3.0

    Attributes
    ----------
    image: Optional[:class:`bool`]
        Messages that have an image.
    sound: Optional[:class:`bool`]
        Messages that have a sound attachment.
    video: Optional[:class:`bool`]
        Messages that have a video.
    file: Optional[:class:`bool`]
        Messages that have an attachment.
    sticker: Optional[:class:`bool`]
        Messages that have a sent sticker.
    embed: Optional[:class:`bool`]
        Messages that have an embed.
    link: Optional[:class:`bool`]
        Messages that have a link.
    poll: Optional[:class:`bool`]
        Messages that have a poll.
    snapshot: Optional[:class:`bool`]
        Messages that have a forwarded message.
    """

    image: bool | None = None
    sound: bool | None = None
    video: bool | None = None
    file: bool | None = None
    sticker: bool | None = None
    embed: bool | None = None
    link: bool | None = None
    poll: bool | None = None
    snapshot: bool | None = None

    def to_query(self) -> list[SearchHasType | str]:
        """The values of the ``has`` query parameter."""
        return _query(self)


def _query(filters: SearchAuthors | SearchHas) -> list[str]:
    wanted: list[str] = []
    unwanted: list[str] = []
    for field in fields(filters):
        value = getattr(filters, field.name)
        if value is True:
            wanted.append(field.name)
        elif value is False:
            unwanted.append(f"-{field.name}")
    return wanted + unwanted


def _snowflakes(
    name: str, items: Sequence[Snowflake] | None, maximum: int
) -> list[int] | None:
    if not items:
        return None
    if len(items) > maximum:
        raise ValueError(f"{name} can have at most {maximum} items")
    return [item.id for item in items]


def _strings(
    name: str, items: Sequence[str] | None, *, length: int, maximum: int = 100
) -> list[str] | None:
    if not items:
        return None
    if len(items) > maximum:
        raise ValueError(f"{name} can have at most {maximum} items")
    for item in items:
        if len(item) > length:
            raise ValueError(
                f"every item of {name} must be {length} characters or fewer"
            )
    return list(items)


def search_params(
    *,
    before: Snowflake | None,
    after: Snowflake | None,
    offset: int | None,
    slop: int | None,
    content: str | None,
    channels: Sequence[Snowflake] | None,
    author_types: SearchAuthors | None,
    authors: Sequence[Snowflake] | None,
    mentions: Sequence[Snowflake] | None,
    mention_roles: Sequence[Snowflake] | None,
    mention_everyone: bool | None,
    replied_to_users: Sequence[Snowflake] | None,
    replied_to_messages: Sequence[Snowflake] | None,
    pinned: bool | None,
    has: SearchHas | None,
    embed_types: Sequence[SearchEmbedType] | None,
    embed_providers: Sequence[str] | None,
    link_hostnames: Sequence[str] | None,
    attachment_filenames: Sequence[str] | None,
    attachment_extensions: Sequence[str] | None,
    sort_by: SearchSortMode | None,
    sort_order: SearchSortOrder | None,
    include_nsfw: bool | None,
) -> dict[str, Any]:
    """Validate the filters of a message search and name them like the API does."""
    if offset is not None and not 0 <= offset <= 9975:
        raise ValueError("offset must be between 0 and 9975")
    if slop is not None and not 0 <= slop <= 100:
        raise ValueError("slop must be between 0 and 100")
    if content is not None and len(content) > 1024:
        raise ValueError("content must be 1024 characters or fewer")

    params: dict[str, Any] = {
        "offset": offset,
        "max_id": None if before is None else before.id,
        "min_id": None if after is None else after.id,
        "slop": slop,
        "content": content or None,
        "channel_id": _snowflakes("channels", channels, 500),
        "author_type": author_types and author_types.to_query(),
        "author_id": _snowflakes("authors", authors, 100),
        "mentions": _snowflakes("mentions", mentions, 100),
        "mentions_role_id": _snowflakes("mention_roles", mention_roles, 100),
        "mention_everyone": mention_everyone,
        "replied_to_user_id": _snowflakes("replied_to_users", replied_to_users, 100),
        "replied_to_message_id": _snowflakes(
            "replied_to_messages", replied_to_messages, 100
        ),
        "pinned": pinned,
        "has": has and has.to_query(),
        "embed_type": embed_types and [t.value for t in embed_types],
        "embed_provider": _strings("embed_providers", embed_providers, length=256),
        "link_hostname": _strings("link_hostnames", link_hostnames, length=256),
        "attachment_filename": _strings(
            "attachment_filenames", attachment_filenames, length=1024
        ),
        "attachment_extension": _strings(
            "attachment_extensions", attachment_extensions, length=256
        ),
        "sort_by": sort_by and sort_by.value,
        "sort_order": sort_order and sort_order.value,
        "include_nsfw": include_nsfw,
    }
    return {key: value for key, value in params.items() if value is not None}


class SearchIndexNotReady(DiscordException):
    """Raised when a guild is still not indexed after all the retries of a message search.

    Discord answers ``202`` to a search while the guild is being indexed.

    .. versionadded:: 3.0

    Attributes
    ----------
    retry_after: :class:`float`
        The seconds Discord asked to wait before trying again.
    documents_indexed: :class:`int`
        The number of documents indexed so far.
    """

    def __init__(self, *, retry_after: float, documents_indexed: int) -> None:
        self.retry_after: float = retry_after
        self.documents_indexed: int = documents_indexed
        super().__init__(
            "The guild messages are not indexed yet, try again in"
            f" {retry_after} seconds ({documents_indexed} documents indexed)"
        )
