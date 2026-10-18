"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz
Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import contextlib
import copy
import datetime as dt
import io
import os
import re
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    TypeAlias,
    TypeVar,
    cast,
)
from urllib.parse import parse_qs, urlparse

from . import utils
from ._internal.cache_peek import cached_channel, cached_guild
from .channel import PartialMessageable
from .components import _component_factory
from .embeds import Embed
from .emoji import AppEmoji, GuildEmoji
from .enums import ChannelType, MessageReferenceType, MessageType, try_enum
from .errors import InvalidArgument
from .file import File
from .flags import AttachmentFlags, MessageFlags
from .guild import Guild, PartialGuild
from .member import Member
from .mixins import Hashable
from .object import Object
from .partial_emoji import PartialEmoji
from .poll import Poll
from .reaction import Reaction
from .shared_client_theme import SharedClientTheme
from .sticker import StickerItem
from .threads import Thread
from .utils import MISSING, escape_mentions, warn_deprecated

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Mapping
    from os import PathLike

    from typing_extensions import Self

    from .abc import (
        GuildChannel,
        MessageableChannel,
        PartialMessageableChannel,
        Snowflake,
    )
    from .components import Component
    from .interactions import MessageInteraction
    from .iterators import MessageSearchIterator
    from .mentions import AllowedMentions
    from .role import Role
    from .state import ConnectionState
    from .types.components import Component as ComponentPayload
    from .types.embed import Embed as EmbedPayload
    from .types.member import (
        Member as MemberPayload,
        UserWithMember as UserWithMemberPayload,
    )
    from .types.message import (
        Attachment as AttachmentPayload,
        ForwardedMessage as ForwardedMessagePayload,
        Message as MessagePayload,
        MessageActivity as MessageActivityPayload,
        MessageApplication as MessageApplicationPayload,
        MessageCall as MessageCallPayload,
        MessagePin as MessagePinPayload,
        MessageReference as MessageReferencePayload,
        MessageSnapshot as MessageSnapshotPayload,
        Reaction as ReactionPayload,
        SharedClientTheme as SharedClientThemePayload,
    )
    from .types.poll import Poll as PollPayload
    from .types.raw_models import ReactionActionEvent
    from .types.snowflake import SnowflakeList
    from .types.threads import ThreadArchiveDuration
    from .types.user import User as UserPayload
    from .ui.view import BaseView
    from .user import User

    MR = TypeVar("MR", bound="MessageReference")
    EmojiInputType: TypeAlias = GuildEmoji | AppEmoji | PartialEmoji | str

_T = TypeVar("_T")

__all__ = (
    "Attachment",
    "DeletedReferencedMessage",
    "ForwardedMessage",
    "Message",
    "MessageCall",
    "MessagePin",
    "MessageReference",
    "MessageSnapshot",
    "PartialMessage",
)


def convert_emoji_reaction(emoji: object) -> str:
    """Convert an emoji, or a reaction, to the string Discord expects."""
    if isinstance(emoji, Reaction):
        emoji = emoji.emoji

    if isinstance(emoji, (GuildEmoji, AppEmoji)):
        return f"{emoji.name}:{emoji.id}"
    if isinstance(emoji, PartialEmoji):
        return emoji._as_reaction()
    if isinstance(emoji, str):
        # Reactions can be in :name:id format, but not <:name:id>.
        # No existing emojis have <> in them, so this should be okay.
        return emoji.strip("<>")

    raise InvalidArgument(
        "emoji argument must be str, GuildEmoji, AppEmoji, or Reaction not"
        f" {emoji.__class__.__name__}."
    )


class Attachment(Hashable):
    """Represents an attachment from Discord.

    .. container:: operations

        .. describe:: str(x)

            Returns the URL of the attachment.

        .. describe:: x == y

            Checks if the attachment is equal to another attachment.

        .. describe:: x != y

            Checks if the attachment is not equal to another attachment.

        .. describe:: hash(x)

            Returns the attachment's unique identifier.

            This is equivalent to :attr:`id`.

    .. versionchanged:: 1.7
        Attachment can now be cast to :class:`str` and is hashable.

    Attributes
    ----------
    id: :class:`int`
        The attachment ID.
    size: :class:`int`
        The attachment size in bytes.
    height: Optional[:class:`int`]
        The attachment's height, in pixels. Only applicable to images and videos.
    width: Optional[:class:`int`]
        The attachment's width, in pixels. Only applicable to images and videos.
    filename: :class:`str`
        The attachment's filename.
    title: Optional[:class:`str`]
        The attachment's title. This is equal to the original :attr:`filename` (without an extension)
        if special characters were filtered from it.

        .. versionadded:: 2.6
    url: :class:`str`
        The attachment URL. If the message this attachment was attached
        to is deleted, then this will 404.
    proxy_url: :class:`str`
        The proxy URL. This is a cached version of the :attr:`~Attachment.url` in the
        case of images. When the message is deleted, this URL might be valid for a few
        minutes or not valid at all.
    content_type: Optional[:class:`str`]
        The attachment's `media type <https://en.wikipedia.org/wiki/Media_type>`_.
    ephemeral: :class:`bool`
        Whether the attachment is ephemeral or not.

        .. versionadded:: 1.7

    description: Optional[:class:`str`]
        The attachment's description.

        .. versionadded:: 2.0

    duration_secs: Optional[:class:`float`]
        The duration of the audio file (currently for voice messages).

        .. versionadded:: 2.5

    waveform: Optional[:class:`str`]
        The base64 encoded bytearray representing a sampled waveform (currently for voice messages).

        .. versionadded:: 2.5

    flags: :class:`AttachmentFlags`
        Extra attributes of the attachment.

        .. versionadded:: 2.5

    hm: :class:`str`
        The unique signature of this attachment's instance.

        .. versionadded:: 2.5
    """

    __slots__ = (
        "_ex",
        "_http",
        "_is",
        "_spoiler",
        "content_type",
        "description",
        "duration_secs",
        "ephemeral",
        "filename",
        "flags",
        "height",
        "hm",
        "id",
        "proxy_url",
        "size",
        "title",
        "url",
        "waveform",
        "width",
    )

    def __init__(self, *, data: AttachmentPayload, state: ConnectionState) -> None:
        self.id: int = int(data["id"])
        self.size: int = data["size"]
        self.height: int | None = data.get("height")
        self.width: int | None = data.get("width")
        self.filename: str = data["filename"]
        self.title: str | None = data.get("title")
        self.url: str = data.get("url")
        self.proxy_url: str = data.get("proxy_url")
        self._http = state.http
        self.content_type: str | None = data.get("content_type")
        self.ephemeral: bool = data.get("ephemeral", False)
        self.description: str | None = data.get("description")
        self.duration_secs: float | None = data.get("duration_secs")
        self.waveform: str | None = data.get("waveform")
        self.flags: AttachmentFlags = AttachmentFlags._from_value(data.get("flags", 0))
        self._ex: str | None = None
        self._is: str | None = None
        self.hm: str | None = None
        self._spoiler: bool | None = None

        query = urlparse(self.url).query
        extras = ["_ex", "_is", "hm"]
        if query_params := parse_qs(query):
            for attr in extras:
                value = "".join(query_params.get(attr.replace("_", ""), []))
                if value:
                    setattr(self, attr, value)

    @property
    def expires_at(self) -> dt.datetime | None:
        """The expiry time of this attachment URL in UTC."""
        if not self._ex:
            return None
        return dt.datetime.fromtimestamp(int(self._ex, 16), tz=dt.timezone.utc).replace(
            tzinfo=None
        )

    @property
    def issued_at(self) -> dt.datetime | None:
        """The attachment URL's issue time in UTC."""
        if not self._is:
            return None
        return dt.datetime.fromtimestamp(int(self._is, 16), tz=dt.timezone.utc).replace(
            tzinfo=None
        )

    def is_spoiler(self) -> bool:
        """Whether this attachment contains a spoiler.

        This is ``True`` when the attachment has the :attr:`AttachmentFlags.is_spoiler`
        flag or when its filename starts with ``SPOILER_``.
        """
        if self._spoiler is not None:
            return self._spoiler
        return self.flags.is_spoiler or self.filename.startswith("SPOILER_")

    def with_changes(
        self,
        *,
        description: str | None = MISSING,
        is_spoiler: bool = MISSING,
    ) -> Attachment:
        """Returns a copy of this attachment with an updated description and/or spoiler state.

        The copy is meant to be passed in the ``attachments`` list of :meth:`Message.edit`
        to change the alt text or the spoiler flag of an attachment that is kept.
        This attachment is left untouched.

        .. versionadded:: 3.0

        Parameters
        ----------
        description: Optional[:class:`str`]
            The new description (alt text, up to 1024 characters).
            Pass ``None`` to remove it.
        is_spoiler: :class:`bool`
            Whether the attachment should be marked as a spoiler.

        Returns
        -------
        :class:`Attachment`
            The updated copy.
        """
        new = copy.copy(self)
        new.flags = AttachmentFlags._from_value(self.flags.value)
        if description is not MISSING:
            new.description = description
        if is_spoiler is not MISSING:
            new.flags.is_spoiler = is_spoiler
            new._spoiler = is_spoiler
        return new

    def __repr__(self) -> str:
        return f"<Attachment id={self.id} filename={self.filename!r} url={self.url!r}>"

    def __str__(self) -> str:
        return self.url or ""

    async def save(
        self,
        fp: io.BufferedIOBase | PathLike[str] | PathLike[bytes],
        *,
        seek_begin: bool = True,
        use_cached: bool = False,
        chunksize: int | None = None,
    ) -> int:
        """|coro|

        Saves this attachment into a file-like object.

        Parameters
        ----------
        fp: Union[:class:`io.BufferedIOBase`, :class:`os.PathLike`]
            The file-like object to save this attachment to or the filename
            to use. If a filename is passed then a file is created with that
            filename and used instead.
        seek_begin: :class:`bool`
            Whether to seek to the beginning of the file after saving is
            successfully done.
        use_cached: :class:`bool`
            Whether to use :attr:`proxy_url` rather than :attr:`url` when downloading
            the attachment. This will allow attachments to be saved after deletion
            more often, compared to the regular URL which is generally deleted right
            after the message is deleted. Note that this can still fail to download
            deleted attachments if too much time has passed, and it does not work
            on some types of attachments.
        chunksize: Optional[:class:`int`]
            The maximum size of each chunk to process. Must be a positive integer.

        Returns
        -------
        :class:`int`
            The number of bytes written.

        Raises
        ------
        HTTPException
            Saving the attachment failed.
        NotFound
            The attachment was deleted.
        InvalidArgument
            Argument `chunksize` is less than 1.
        """
        data: AsyncGenerator[bytes, None] | bytes
        if chunksize is not None:
            data = self.read_chunked(use_cached=use_cached, chunksize=chunksize)
        else:
            data = await self.read(use_cached=use_cached)

        if isinstance(fp, io.BufferedIOBase):
            if isinstance(data, bytes):
                written = fp.write(data)
            else:
                written = 0
                async for chunk in data:
                    written += fp.write(chunk)
            if seek_begin:
                fp.seek(0)
            return written
        with Path(os.fsdecode(fp)).open("wb") as f:
            if isinstance(data, bytes):
                return f.write(data)
            written = 0
            async for chunk in data:
                written += f.write(chunk)
            return written

    async def read(self, *, use_cached: bool = False) -> bytes:
        """|coro|

        Retrieves the content of this attachment as a :class:`bytes` object.

        .. versionadded:: 1.1

        Parameters
        ----------
        use_cached: :class:`bool`
            Whether to use :attr:`proxy_url` rather than :attr:`url` when downloading
            the attachment. This will allow attachments to be saved after deletion
            more often, compared to the regular URL which is generally deleted right
            after the message is deleted. Note that this can still fail to download
            deleted attachments if too much time has passed, and it does not work
            on some types of attachments.

        Returns
        -------
        :class:`bytes`
            The contents of the attachment.

        Raises
        ------
        HTTPException
            Downloading the attachment failed.
        Forbidden
            You do not have permissions to access this attachment
        NotFound
            The attachment was deleted.
        """
        url = self.proxy_url if use_cached else self.url
        return await self._http.get_from_cdn(url)

    async def read_chunked(
        self, chunksize: int, *, use_cached: bool = False
    ) -> AsyncGenerator[bytes]:
        """|coro|

        Retrieves the content of this attachment in chunks as a :class:`AsyncGenerator` object of bytes.

        Parameters
        ----------
        chunksize: :class:`int`
            The maximum size of each chunk to process. Must be a positive integer.
        use_cached: :class:`bool`
            Whether to use :attr:`proxy_url` rather than :attr:`url` when downloading
            the attachment. This will allow attachments to be saved after deletion
            more often, compared to the regular URL which is generally deleted right
            after the message is deleted. Note that this can still fail to download
            deleted attachments if too much time has passed, and it does not work
            on some types of attachments.

        Yields
        ------
        :class:`bytes`
            A chunk of the file.

        Raises
        ------
        HTTPException
            Downloading the attachment failed.
        Forbidden
            You do not have permissions to access this attachment
        NotFound
            The attachment was deleted.
        InvalidArgument
            Argument `chunksize` is less than 1.
        """
        url = self.proxy_url if use_cached else self.url
        async for chunk in self._http.stream_from_cdn(url, chunksize):
            yield chunk

    async def to_file(self, *, use_cached: bool = False, spoiler: bool = False) -> File:
        """|coro|

        Converts the attachment into a :class:`File` suitable for sending via
        :meth:`abc.Messageable.send`.

        .. versionadded:: 1.3

        Parameters
        ----------
        use_cached: :class:`bool`
            Whether to use :attr:`proxy_url` rather than :attr:`url` when downloading
            the attachment. This will allow attachments to be saved after deletion
            more often, compared to the regular URL which is generally deleted right
            after the message is deleted. Note that this can still fail to download
            deleted attachments if too much time has passed, and it does not work
            on some types of attachments.

            .. versionadded:: 1.4
        spoiler: :class:`bool`
            Whether the file is a spoiler.

            .. versionadded:: 1.4

        Returns
        -------
        :class:`File`
            The attachment as a file suitable for sending.

        Raises
        ------
        HTTPException
            Downloading the attachment failed.
        Forbidden
            You do not have permissions to access this attachment
        NotFound
            The attachment was deleted.
        """
        data = await self.read(use_cached=use_cached)
        return File(
            io.BytesIO(data),
            filename=self.filename,
            spoiler=spoiler,
            description=self.description,
        )

    def to_dict(self) -> AttachmentPayload:
        """Convert this attachment to its payload."""
        result: AttachmentPayload = {
            "filename": self.filename,
            "id": self.id,
            "proxy_url": self.proxy_url,
            "size": self.size,
            "url": self.url,
            "is_spoiler": self.is_spoiler(),
        }
        if self.height:
            result["height"] = self.height
        if self.width:
            result["width"] = self.width
        if self.content_type:
            result["content_type"] = self.content_type
        if self.description is not None:
            result["description"] = self.description
        if self.flags.value:
            result["flags"] = self.flags.value
        return result


class DeletedReferencedMessage:
    """A special sentinel type that denotes whether the resolved referenced message was deleted.

    The purpose of this class is to separate referenced messages that could not be
    fetched and those that were previously fetched but have since been deleted.

    .. versionadded:: 1.6
    """

    __slots__ = ("_parent",)

    def __init__(self, parent: MessageReference) -> None:
        self._parent: MessageReference = parent

    def __repr__(self) -> str:
        return (
            "<DeletedReferencedMessage"
            f" id={self.id} channel_id={self.channel_id} guild_id={self.guild_id!r}>"
        )

    @property
    def id(self) -> int:
        """The message ID of the deleted referenced message."""
        # the parent's message id won't be None here
        return cast("int", self._parent.message_id)

    @property
    def channel_id(self) -> int:
        """The channel ID of the deleted referenced message."""
        return self._parent.channel_id

    @property
    def guild_id(self) -> int | None:
        """The guild ID of the deleted referenced message."""
        return self._parent.guild_id


class MessageReference:
    """Represents a reference to a :class:`~discord.Message`.

    .. versionadded:: 1.5

    .. versionchanged:: 1.6
        This class can now be constructed by users.

    Attributes
    ----------
    type: Optional[:class:`~discord.MessageReferenceType`]
        The type of message reference. If this is not provided, assume the default behavior (i.e., reply).

        .. versionadded:: 2.7

    message_id: Optional[:class:`int`]
        The id of the message referenced.
    channel_id: :class:`int`
        The channel id of the message referenced.
    guild_id: Optional[:class:`int`]
        The guild id of the message referenced.
    fail_if_not_exists: :class:`bool`
        Whether replying to the referenced message should raise :class:`HTTPException`
        if the message no longer exists or Discord could not fetch the message.

        .. versionadded:: 1.7

    resolved: Optional[Union[:class:`Message`, :class:`DeletedReferencedMessage`]]
        The message that this reference resolved to. If this is ``None``
        then the original message was not fetched either due to the Discord API
        not attempting to resolve it or it not being available at the time of creation.
        If the message was resolved at a prior point but has since been deleted then
        this will be of type :class:`DeletedReferencedMessage`.

        Currently, this is mainly the replied to message when a user replies to a message.

        .. versionadded:: 1.6
    """

    __slots__ = (
        "_state",
        "channel_id",
        "fail_if_not_exists",
        "guild_id",
        "message_id",
        "resolved",
        "type",
    )

    def __init__(
        self,
        *,
        message_id: int,
        channel_id: int,
        guild_id: int | None = None,
        fail_if_not_exists: bool = True,
        type: MessageReferenceType = MessageReferenceType.default,
    ) -> None:
        self._state: ConnectionState | None = None
        self.resolved: Message | DeletedReferencedMessage | None = None
        self.type: MessageReferenceType = type
        self.message_id: int | None = message_id
        self.channel_id: int = channel_id
        self.guild_id: int | None = guild_id
        self.fail_if_not_exists: bool = fail_if_not_exists

    @classmethod
    def with_state(cls, state: ConnectionState, data: MessageReferencePayload) -> Self:
        """Build a reference bound to a connection state from its payload."""
        self = cls.__new__(cls)
        self.type = (
            try_enum(MessageReferenceType, data.get("type"))
            or MessageReferenceType.default
        )
        self.message_id = utils._get_as_snowflake(data, "message_id")
        self.channel_id = cast("int", utils._get_as_snowflake(data, "channel_id"))
        self.guild_id = utils._get_as_snowflake(data, "guild_id")
        self.fail_if_not_exists = data.get("fail_if_not_exists", True)
        self._state = state
        self.resolved = None
        return self

    @classmethod
    def from_message(
        cls,
        message: Message,
        *,
        fail_if_not_exists: bool = True,
        type: MessageReferenceType = MessageReferenceType.default,
    ) -> Self:
        """Creates a :class:`MessageReference` from an existing :class:`~discord.Message`.

        .. versionadded:: 1.6

        Parameters
        ----------
        message: :class:`~discord.Message`
            The message to be converted into a reference.
        fail_if_not_exists: :class:`bool`
            Whether replying to the referenced message should raise :class:`HTTPException`
            if the message no longer exists or Discord could not fetch the message.

            .. versionadded:: 1.7

        type: Optional[:class:`~discord.MessageReferenceType`]
            The type of reference to create. Defaults to :attr:`MessageReferenceType.default` (reply).

            .. versionadded:: 2.7

        Returns
        -------
        :class:`MessageReference`
            A reference to the message.
        """
        self = cls(
            message_id=message.id,
            channel_id=message.channel.id,
            guild_id=getattr(message.guild, "id", None),
            fail_if_not_exists=fail_if_not_exists,
            type=type,
        )
        self._state = message._state
        return self

    @property
    def cached_message(self) -> Message | None:
        """The cached message, if found in the internal message cache.

        This reads the in-memory cache, use :meth:`get_cached_message` with a remote cache backend.
        """
        if self._state is None or self.message_id is None:
            return None
        if self._state._messages is None:
            return None
        return self._state._messages.get_nowait(self.message_id)

    async def get_cached_message(self) -> Message | None:
        """|coro|

        Returns the referenced message, if found in the internal message cache.

        Returns
        -------
        Optional[:class:`Message`]
            The cached message, or ``None`` if it is not cached.
        """
        if self._state is None or self.message_id is None:
            return None
        return await self._state._get_message(self.message_id)

    @property
    def jump_url(self) -> str:
        """Returns a URL that allows the client to jump to the referenced message.

        .. versionadded:: 1.7
        """
        guild_id = self.guild_id if self.guild_id is not None else "@me"
        return f"https://discord.com/channels/{guild_id}/{self.channel_id}/{self.message_id}"

    def __repr__(self) -> str:
        return (
            f"<MessageReference message_id={self.message_id!r}"
            f" channel_id={self.channel_id!r} guild_id={self.guild_id!r}"
            f" type={self.type!r}>"
        )

    def to_dict(self) -> MessageReferencePayload:
        """Convert this reference to its payload."""
        result: MessageReferencePayload = (
            {"message_id": self.message_id} if self.message_id is not None else {}
        )
        result["channel_id"] = self.channel_id
        result["type"] = self.type and self.type.value
        if self.guild_id is not None:
            result["guild_id"] = self.guild_id
        if self.fail_if_not_exists is not None:  # pyright: ignore[reportUnnecessaryComparison]
            result["fail_if_not_exists"] = self.fail_if_not_exists
        return result

    to_message_reference_dict = to_dict


class MessageCall:
    """Represents information about a call in a private channel.

    .. versionadded:: 2.6
    """

    __slots__ = (
        "_ended_timestamp",
        "_participants",
        "_state",
    )

    def __init__(self, state: ConnectionState, data: MessageCallPayload) -> None:
        self._state: ConnectionState = state
        self._participants: SnowflakeList = data.get("participants", [])
        self._ended_timestamp: dt.datetime | None = utils.parse_time(
            data.get("ended_timestamp")
        )

    @property
    def participant_ids(self) -> list[int]:
        """A list of the IDs of the users that participated in this call."""
        return [int(i) for i in self._participants]

    @property
    def participants(self) -> list[User | Object]:
        """A list of :class:`User` that participated in this call.

        If a user is not found in the client's cache,
        then it will be returned as an :class:`Object`.

        This reads the in-memory cache, use :meth:`get_participants` with a remote cache backend.
        """
        return [
            self._state._users.get_nowait(user_id) or Object(user_id)
            for user_id in self.participant_ids
        ]

    async def get_participants(self) -> list[User | Object]:
        """|coro|

        Returns the users that participated in this call.

        If a user is not found in the client's cache,
        then it will be returned as an :class:`Object`.

        Returns
        -------
        List[Union[:class:`User`, :class:`Object`]]
            The participants of this call.
        """
        return [
            await self._state.get_user(user_id) or Object(user_id)
            for user_id in self.participant_ids
        ]

    @property
    def ended_at(self) -> dt.datetime | None:
        """An aware timestamp of when the call ended."""
        return self._ended_timestamp


class ForwardedMessage:
    """Represents the snapshotted contents from a forwarded message. Forwarded messages are immutable; any updates to the original message will not be reflected.

    .. versionadded:: 2.7

    Attributes
    ----------
    type: :class:`MessageType`
        The type of the original message. In most cases this should not be checked, but it is helpful
        in cases where it might be a system message for :meth:`get_system_content`.
    original_message: Optional[Union[:class:`Message`, :class:`PartialMessage`]]
        The original message that was forwarded, if available.
    channel: Union[:class:`TextChannel`, :class:`Thread`, :class:`DMChannel`, :class:`GroupChannel`, :class:`PartialMessageable`]
        The channel that the original message was sent from, or a :class:`PartialMessageable`
        handle if it is not in an in-process cache.
    guild: Optional[Union[:class:`Guild`, :class:`PartialGuild`]]
        The guild that the original message belonged to, if applicable, or a
        :class:`PartialGuild` handle if it is not in an in-process cache.
    content: :class:`str`
        The contents of the original message.
    embeds: List[:class:`Embed`]
        A list of embeds the original message had.
    attachments: List[:class:`Attachment`]
        A list of attachments given to the original message.
    flags: :class:`MessageFlags`
        Extra features of the original message.
    mentions: List[:class:`User`]
        A list of :class:`User` that were originally mentioned.

        .. note::
            This list will be empty if the message was forwarded to a different place, e.g., from a DM to a guild, or
            from one guild to another.
    role_mentions: List[:class:`Role`]
        A list of :class:`Role` that were originally mentioned.
        This reads the in-memory cache, use :meth:`get_role_mentions` with a remote cache backend.
    role_mention_ids: List[:class:`int`]
        A list of the IDs of the roles that were originally mentioned.
    stickers: List[:class:`StickerItem`]
        A list of sticker items given to the original message.
    components: List[:class:`Component`]
        A list of components in the original message.
    """

    __slots__ = (
        "_edited_timestamp",
        "_reference",
        "_state",
        "attachments",
        "channel",
        "components",
        "content",
        "embeds",
        "flags",
        "guild",
        "id",
        "mentions",
        "original_message",
        "role_mention_ids",
        "stickers",
        "type",
    )

    def __init__(
        self,
        *,
        state: ConnectionState,
        reference: MessageReference,
        data: ForwardedMessagePayload,
    ) -> None:
        self._state: ConnectionState = state
        self._reference = reference
        self.id: int = cast("int", reference.message_id)
        self.channel = reference.channel_id and (
            cached_channel(state, reference.channel_id)
            or PartialMessageable(state=state, id=reference.channel_id)
        )
        self.guild = reference.guild_id and (
            cached_guild(state, reference.guild_id)
            or PartialGuild(state=state, id=reference.guild_id)
        )
        cached_message = (
            state._messages.get_nowait(self.id)
            if self.id and state._messages is not None and state.cache.supports_sync
            else None
        )
        self.original_message = cached_message or (
            self.id
            and PartialMessageable(
                state=state, id=reference.channel_id
            ).get_partial_message(self.id)
        )
        self.content: str = data["content"]
        self.embeds: list[Embed] = [Embed.from_dict(a) for a in data["embeds"]]
        self.attachments: list[Attachment] = [
            Attachment(data=a, state=state) for a in data["attachments"]
        ]
        self.flags: MessageFlags = MessageFlags._from_value(data.get("flags", 0))
        self.stickers: list[StickerItem] = [
            StickerItem(data=d, state=state) for d in data.get("sticker_items", [])
        ]
        self.components: list[Component] = [
            _component_factory(d) for d in data.get("components", [])
        ]
        self.mentions: list[User] = [
            state.create_user(data=user) for user in data["mentions"]
        ]
        self.role_mention_ids: list[int] = [
            int(role_id) for role_id in data.get("mention_roles", [])
        ]

        self.type: MessageType = try_enum(MessageType, data["type"])
        self._edited_timestamp: dt.datetime | None = utils.parse_time(
            data["edited_timestamp"]
        )

    @property
    def role_mentions(self) -> list[Role]:
        """The cached roles that were originally mentioned."""
        guild_id = self._reference.guild_id
        if guild_id is None:
            return []
        roles = self._state._guild_bucket("roles", guild_id)
        return [
            role
            for role_id in self.role_mention_ids
            if (role := roles.get_nowait(role_id)) is not None
        ]

    async def get_role_mentions(self) -> list[Role]:
        """|coro|

        Returns the cached roles that were originally mentioned.

        Roles are looked up in the guild the original message belonged to,
        so this is empty if the message was forwarded from another guild
        or from a private channel.

        Returns
        -------
        List[:class:`Role`]
            The cached roles that were mentioned.
        """
        guild_id = self._reference.guild_id
        if guild_id is None:
            return []
        roles = self._state._guild_bucket("roles", guild_id)
        return [
            role
            for role_id in self.role_mention_ids
            if (role := await roles.get(role_id)) is not None
        ]

    @property
    def created_at(self) -> dt.datetime:
        """The original message's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def edited_at(self) -> dt.datetime | None:
        """An aware UTC datetime object containing the edited time of the original message."""
        return self._edited_timestamp

    def __repr__(self) -> str:
        return f"<ForwardedMessage reference={self._reference!r}>"


class MessageSnapshot:
    """Represents a message snapshot.

    .. versionadded:: 2.7

    Attributes
    ----------
    message: :class:`ForwardedMessage`
        The forwarded message, which includes a minimal subset of fields from the original message.
    """

    __slots__ = (
        "_state",
        "message",
    )

    def __init__(
        self,
        *,
        state: ConnectionState,
        reference: MessageReference,
        data: MessageSnapshotPayload,
    ) -> None:
        self._state: ConnectionState = state
        self.message: ForwardedMessage | None = None
        if fm := data.get("message"):
            self.message = ForwardedMessage(state=state, reference=reference, data=fm)

    def __repr__(self) -> str:
        return f"<MessageSnapshot message={self.message!r}>"


def flatten_handlers(cls: type[_T]) -> type[_T]:
    """Collect the ``_handle_*`` methods of a message class for fast updates."""
    target = cast("Any", cls)
    prefix = len("_handle_")
    handlers = [
        (key[prefix:], value)
        for key, value in target.__dict__.items()
        if key.startswith("_handle_") and key != "_handle_member"
    ]

    # store _handle_member last
    handlers.append(("member", target._handle_member))
    target._HANDLERS = handlers
    target._CACHED_SLOTS = [
        attr for attr in target.__slots__ if attr.startswith("_cs_")
    ]
    return cls


class MessagePin:
    """Represents information about a pinned message.

    .. versionadded:: 2.7
    """

    def __init__(
        self,
        state: ConnectionState,
        channel: MessageableChannel,
        data: MessagePinPayload,
    ) -> None:
        self._state: ConnectionState = state
        self._pinned_at: dt.datetime = utils.parse_time(data["pinned_at"])
        self._message: Message = state.create_message(
            channel=channel, data=data["message"]
        )

    @property
    def message(self) -> Message:
        """The pinned message."""
        return self._message

    @property
    def pinned_at(self) -> dt.datetime:
        """An aware timestamp of when the message was pinned."""
        return self._pinned_at

    def __repr__(self) -> str:
        return f"<MessagePin pinned_at={self.pinned_at!r} message={self.message!r}>"


@flatten_handlers
class Message(Hashable):
    r"""Represents a message from Discord.

    .. container:: operations

        .. describe:: x == y

            Checks if two messages are equal.

        .. describe:: x != y

            Checks if two messages are not equal.

        .. describe:: hash(x)

            Returns the message's hash.

    Attributes
    ----------
    tts: :class:`bool`
        Specifies if the message was done with text-to-speech.
        This can only be accurately received in :func:`on_message` due to
        a discord limitation.
    type: :class:`MessageType`
        The type of message. In most cases this should not be checked, but it is helpful
        in cases where it might be a system message for :meth:`get_system_content`.
    author: Union[:class:`Member`, :class:`abc.User`]
        A :class:`Member` that sent the message. If :attr:`channel` is a
        private channel or the user has the left the guild, then it is a :class:`User` instead.
    content: :class:`str`
        The actual contents of the message.
    nonce: Optional[Union[:class:`str`, :class:`int`]]
        The value used by the discord guild and the client to verify that the message is successfully sent.
        This is not stored long term within Discord's servers and is only used ephemerally.
    embeds: List[:class:`Embed`]
        A list of embeds the message has.
    channel: :class:`PartialMessageable`
        A handle to the channel the message was sent from.
        Use :meth:`PartialMessageable.get` to get the cached channel.
    reference: Optional[:class:`~discord.MessageReference`]
        The message that this message references. This is only applicable to messages of
        type :attr:`MessageType.pins_add`, crossposted messages created by a
        followed channel integration, or message replies.

        .. versionadded:: 1.5

    mention_everyone: :class:`bool`
        Specifies if the message mentions everyone.

        .. note::

            This does not check if the ``@everyone`` or the ``@here`` text is in the message itself.
            Rather this boolean indicates if either the ``@everyone`` or the ``@here`` text is in the message
            **and** it did end up mentioning.
    mentions: List[:class:`abc.User`]
        A list of :class:`Member` that were mentioned. If the message is in a private message
        then the list will be of :class:`User` instead. For messages that are not of type
        :attr:`MessageType.default`\, this array can be used to aid in system messages.
        For more information, see :meth:`get_system_content`.

        .. warning::

            The order of the mentions list is not in any particular order, so you should
            not rely on it. This is a Discord limitation, not one with the library.
    role_mentions: List[:class:`Role`]
        A list of :class:`Role` that were mentioned, as cached when the message was received.
        If the message is in a private message then the list is always empty.
        Use :meth:`get_role_mentions` to look the roles up again.
    role_mention_ids: List[:class:`int`]
        A list of the IDs of the roles that were mentioned.
    id: :class:`int`
        The message ID.
    webhook_id: Optional[:class:`int`]
        If this message was sent by a webhook, then this is the webhook ID's that sent this
        message.
    attachments: List[:class:`Attachment`]
        A list of attachments given to a message.
    pinned: :class:`bool`
        Specifies if the message is currently pinned.
    flags: :class:`MessageFlags`
        Extra features of the message.

        .. versionadded:: 1.3

    reactions : List[:class:`Reaction`]
        Reactions to a message. Reactions can be either custom emoji or standard unicode emoji.
    activity: Optional[:class:`dict`]
        The activity associated with this message. Sent with Rich-Presence related messages that for
        example, request joining, spectating, or listening to or with another member.

        It is a dictionary with the following optional keys:

        - ``type``: An integer denoting the type of message activity being requested.
        - ``party_id``: The party ID associated with the party.
    application: Optional[:class:`dict`]
        The rich presence enabled application associated with this message.

        It is a dictionary with the following keys:

        - ``id``: A string representing the application's ID.
        - ``name``: A string representing the application's name.
        - ``description``: A string representing the application's description.
        - ``icon``: A string representing the icon ID of the application.
        - ``cover_image``: A string representing the embed's image asset ID.
    stickers: List[:class:`StickerItem`]
        A list of sticker items given to the message.

        .. versionadded:: 1.6
    components: List[:class:`Component`]
        A list of components in the message.

        .. versionadded:: 2.0
    guild_id: Optional[:class:`int`]
        The ID of the guild that the message belongs to, if applicable.
    channel_id: :class:`int`
        The ID of the channel the message was sent in.
    interaction: Optional[:class:`MessageInteraction`]
        The interaction associated with the message, if applicable.

        .. deprecated:: 2.6

            Use :attr:`interaction_metadata` instead.
    interaction_metadata: Optional[:class:`InteractionMetadata`]
        The interaction metadata associated with the message, if applicable.

        .. versionadded:: 2.6
    thread: Optional[:class:`Thread`]
        The thread created from this message, if applicable.

        .. versionadded:: 2.0
    poll: Optional[:class:`Poll`]
        The poll associated with this message, if applicable.

        .. versionadded:: 2.6
    call: Optional[:class:`MessageCall`]
        The call information associated with this message, if applicable.

        .. versionadded:: 2.6
    shared_client_theme: Optional[:class:`SharedClientTheme`]
        The client theme shared via this message, if applicable.

        .. versionadded:: 3.0
    snapshots: Optional[List[:class:`MessageSnapshot`]]
        The snapshots attached to this message, if applicable.

        .. versionadded:: 2.7
    """

    __slots__ = (
        "_channel_type",
        "_cs_channel_mentions",
        "_cs_clean_content",
        "_cs_raw_channel_mentions",
        "_cs_raw_mentions",
        "_cs_raw_role_mentions",
        "_cs_system_content",
        "_edited_timestamp",
        "_interaction",
        "_poll",
        "_raw_data",
        "_state",
        "activity",
        "application",
        "attachments",
        "author",
        "call",
        "channel_id",
        "components",
        "content",
        "embeds",
        "flags",
        "guild_id",
        "id",
        "interaction_metadata",
        "mention_everyone",
        "mentions",
        "nonce",
        "pinned",
        "reactions",
        "reference",
        "role_mention_ids",
        "role_mentions",
        "shared_client_theme",
        "snapshots",
        "stickers",
        "thread",
        "tts",
        "type",
        "webhook_id",
    )

    if TYPE_CHECKING:
        _HANDLERS: ClassVar[list[tuple[str, Callable[..., None]]]]
        _CACHED_SLOTS: ClassVar[list[str]]
        reference: MessageReference | None
        mentions: list[User | Member]
        author: User | Member
        role_mentions: list[Role]

    def __init__(
        self,
        *,
        state: ConnectionState,
        channel: MessageableChannel,
        data: MessagePayload,
    ) -> None:
        self._state: ConnectionState = state
        self._raw_data: MessagePayload = data
        self.id: int = int(data["id"])
        self.channel_id: int = channel.id
        self._channel_type: ChannelType | None = getattr(channel, "type", None)
        guild_id = getattr(channel, "guild_id", None)
        if guild_id is None:
            guild_id = utils._get_as_snowflake(data, "guild_id")
        self.guild_id: int | None = guild_id
        self.webhook_id: int | None = utils._get_as_snowflake(data, "webhook_id")
        self.role_mention_ids: list[int] = []
        self.role_mentions = []
        self.reactions: list[Reaction] = [
            Reaction(message=self, data=d) for d in data.get("reactions", [])
        ]
        self.attachments: list[Attachment] = [
            Attachment(data=a, state=self._state) for a in data["attachments"]
        ]
        self.embeds: list[Embed] = [Embed.from_dict(a) for a in data["embeds"]]
        self.application: MessageApplicationPayload | None = data.get("application")
        self.activity: MessageActivityPayload | None = data.get("activity")
        self._edited_timestamp: dt.datetime | None = utils.parse_time(
            data["edited_timestamp"]
        )
        self.type: MessageType = try_enum(MessageType, data["type"])
        self.pinned: bool = data["pinned"]
        self.flags: MessageFlags = MessageFlags._from_value(data.get("flags", 0))
        self.mention_everyone: bool = data["mention_everyone"]
        self.tts: bool = data["tts"]
        self.content: str = data["content"]
        self.nonce: int | str | None = data.get("nonce")
        self.stickers: list[StickerItem] = [
            StickerItem(data=d, state=state) for d in data.get("sticker_items", [])
        ]
        self.components: list[Component] = [
            _component_factory(d, state=state) for d in data.get("components", [])
        ]

        raw = cast("dict[str, Any]", data)

        self.reference: MessageReference | None
        if "message_reference" in data:
            self.reference = ref = MessageReference.with_state(
                state, data["message_reference"]
            )
            if "referenced_message" in data:
                resolved = data["referenced_message"]
                if resolved is None:
                    ref.resolved = DeletedReferencedMessage(ref)
                else:
                    # Right now the channel IDs match but maybe in the future they won't.
                    if ref.channel_id == channel.id:
                        chan = channel
                    else:
                        chan = PartialMessageable(
                            state=state, id=int(resolved["channel_id"])
                        )

                    # the channel will be the correct type here
                    ref.resolved = self.__class__(
                        channel=chan, data=resolved, state=state
                    )
        else:
            self.reference = None

        self.snapshots: list[MessageSnapshot]
        try:
            self.snapshots = [
                MessageSnapshot(
                    state=state,
                    reference=cast("MessageReference", self.reference),
                    data=ms,
                )
                for ms in raw["message_snapshots"]
            ]
        except KeyError:
            self.snapshots = []

        from .interactions import InteractionMetadata, MessageInteraction

        self._interaction: MessageInteraction | None
        try:
            self._interaction = MessageInteraction(data=raw["interaction"], state=state)
        except KeyError:
            self._interaction = None
        self.interaction_metadata: InteractionMetadata | None
        try:
            self.interaction_metadata = InteractionMetadata(
                data=raw["interaction_metadata"], state=state
            )
        except KeyError:
            self.interaction_metadata = None

        self._poll: Poll | None
        try:
            self._poll = Poll.from_dict(
                raw["poll"],
                PartialMessage(
                    channel=self._partial_channel(), id=self.id, guild_id=self.guild_id
                ),
            )
        except KeyError:
            self._poll = None

        self.thread: Thread | None = None
        if thread_data := data.get("thread"):
            thread_guild_id = self.guild_id or utils._get_as_snowflake(
                thread_data, "guild_id"
            )
            if thread_guild_id is not None:
                self.thread = Thread(
                    guild=PartialGuild(state=state, id=thread_guild_id),
                    state=self._state,
                    data=thread_data,
                )

        self.call: MessageCall | None
        try:
            self.call = MessageCall(state=self._state, data=data["call"])
        except KeyError:
            self.call = None

        self.shared_client_theme: SharedClientTheme | None = None
        if theme := data.get("shared_client_theme"):
            self.shared_client_theme = SharedClientTheme.from_dict(theme)

        for handler in ("author", "member", "mentions", "mention_roles"):
            with contextlib.suppress(KeyError):
                getattr(self, f"_handle_{handler}")(raw[handler])

    def __repr__(self) -> str:
        name = self.__class__.__name__
        return (
            f"<{name} id={self.id} channel={self.channel!r} type={self.type!r}"
            f" author={self.author!r} flags={self.flags!r}>"
        )

    def _try_patch(
        self,
        data: Mapping[str, Any],
        key: str,
        transform: Callable[[Any], Any] | None = None,
    ) -> None:
        try:
            value = data[key]
        except KeyError:
            pass
        else:
            if transform is None:
                setattr(self, key, value)
            else:
                setattr(self, key, transform(value))

    def _add_reaction(
        self,
        data: ReactionPayload | ReactionActionEvent,
        emoji: EmojiInputType,
        user_id: int | None,
    ) -> Reaction:
        reaction = utils.find(lambda r: r.emoji == emoji, self.reactions)
        is_me = data["me"] = user_id == self._state.self_id

        if reaction is None:
            reaction = Reaction(message=self, data=data, emoji=emoji)
            self.reactions.append(reaction)
        else:
            reaction.count += 1
            if is_me:
                reaction.me = is_me

        return reaction

    def _remove_reaction(
        self,
        data: ReactionPayload | ReactionActionEvent,
        emoji: EmojiInputType,
        user_id: int,
    ) -> Reaction:
        reaction = utils.find(lambda r: r.emoji == emoji, self.reactions)

        if reaction is None:
            # already removed?
            raise ValueError("Emoji already removed?")

        # if reaction isn't in the list, we crash. This means discord
        # sent bad data, or we stored improperly
        reaction.count -= 1

        if user_id == self._state.self_id:
            reaction.me = False
        if reaction.count == 0:
            # this raises ValueError if something went wrong as well.
            self.reactions.remove(reaction)

        return reaction

    def _clear_emoji(self, emoji: EmojiInputType | Reaction) -> Reaction | None:
        to_check = str(emoji)
        for index, reaction in enumerate(self.reactions):
            if str(reaction.emoji) == to_check:
                del self.reactions[index]
                return reaction

        # didn't find anything so just return
        return None

    def _handle_edited_timestamp(self, value: str) -> None:
        self._edited_timestamp = utils.parse_time(value)

    def _handle_pinned(self, value: bool) -> None:
        self.pinned = value

    def _handle_flags(self, value: int) -> None:
        self.flags = MessageFlags._from_value(value)

    def _handle_application(self, value: MessageApplicationPayload) -> None:
        self.application = value

    def _handle_activity(self, value: MessageActivityPayload) -> None:
        self.activity = value

    def _handle_mention_everyone(self, value: bool) -> None:
        self.mention_everyone = value

    def _handle_tts(self, value: bool) -> None:
        self.tts = value

    def _handle_type(self, value: int) -> None:
        self.type = try_enum(MessageType, value)

    def _handle_content(self, value: str) -> None:
        self.content = value

    def _handle_attachments(self, value: list[AttachmentPayload]) -> None:
        self.attachments = [Attachment(data=a, state=self._state) for a in value]

    def _handle_embeds(self, value: list[EmbedPayload]) -> None:
        self.embeds = [Embed.from_dict(data) for data in value]

    def _handle_nonce(self, value: str | int) -> None:
        self.nonce = value

    def _handle_shared_client_theme(self, value: SharedClientThemePayload) -> None:
        self.shared_client_theme = SharedClientTheme.from_dict(value) if value else None

    def _handle_poll(self, value: PollPayload) -> None:
        self._poll = Poll.from_dict(
            value,
            PartialMessage(
                channel=self._partial_channel(), id=self.id, guild_id=self.guild_id
            ),
        )

    def _handle_author(self, author: UserPayload) -> None:
        self.author = self._state.create_user(author)

    def _handle_member(self, member: MemberPayload) -> None:
        # The gateway now gives us full Member objects sometimes with the following keys
        # deaf, mute, joined_at, roles
        # For the sake of performance I'm going to assume that the only
        # field that needs *updating* would be the joined_at field.
        # If there is no Member object (for some strange reason), then we can upgrade
        # ourselves to a more "partial" member object.
        author = self.author
        try:
            # Update member reference
            cast("Any", author)._update_from_message(member)
        except AttributeError:
            # It's a user here
            # TODO: consider adding to cache here
            if self.guild_id is not None:
                self.author = Member._from_message(message=self, data=member)

    def _handle_mentions(self, mentions: list[UserWithMemberPayload]) -> None:
        r: list[User | Member] = []
        self.mentions = r
        guild = self.guild
        state = self._state
        if guild is None:
            self.mentions = [state.create_user(m) for m in mentions]
            return

        r.extend(
            Member._try_upgrade(data=mention, guild=guild, state=state)
            for mention in filter(None, mentions)
        )

    def _handle_mention_roles(self, role_mentions: list[int]) -> None:
        self.role_mention_ids = [int(role_id) for role_id in role_mentions]
        self.role_mentions = []

    def _handle_components(self, components: list[ComponentPayload]) -> None:
        self.components = [_component_factory(d, state=self._state) for d in components]

    @property
    def interaction(self) -> MessageInteraction | None:
        """The interaction the message is a response to, if any."""
        utils.warn_deprecated(
            "interaction",
            "interaction_metadata",
            "2.6",
            reference="https://docs.discord.com/developers/change-log#user-installable-apps-preview",
        )
        return self._interaction

    @interaction.setter
    def interaction(self, value: MessageInteraction | None) -> None:
        utils.warn_deprecated(
            "interaction",
            "interaction_metadata",
            "2.6",
            reference="https://docs.discord.com/developers/change-log#user-installable-apps-preview",
        )
        self._interaction = value

    @utils.cached_slot_property("_cs_raw_mentions")
    def raw_mentions(self) -> list[int]:
        """A property that returns an array of user IDs matched with the syntax of ``<@user_id>`` in the message content.

        This allows you to receive the user IDs of mentioned users
        even in a private message context.
        """
        return [int(x) for x in re.findall(r"<@!?([0-9]{15,20})>", self.content)]

    @utils.cached_slot_property("_cs_raw_channel_mentions")
    def raw_channel_mentions(self) -> list[int]:
        """A property that returns an array of channel IDs matched with the syntax of ``<#channel_id>`` in the message content."""
        return [int(x) for x in re.findall(r"<#([0-9]{15,20})>", self.content)]

    @utils.cached_slot_property("_cs_raw_role_mentions")
    def raw_role_mentions(self) -> list[int]:
        """A property that returns an array of role IDs matched with the syntax of ``<@&role_id>`` in the message content."""
        return [int(x) for x in re.findall(r"<@&([0-9]{15,20})>", self.content)]

    @utils.cached_slot_property("_cs_channel_mentions")
    def channel_mentions(self) -> list[GuildChannel]:
        """A list of :class:`abc.GuildChannel` that were mentioned.

        If the message is in a private message then the list is always empty.

        This reads the in-memory cache, use :meth:`get_channel_mentions` with a remote cache backend.
        """
        if self.guild_id is None:
            return []
        channels = self._state._guild_bucket("channels", self.guild_id)
        found = [
            channel
            for channel_id in self.raw_channel_mentions
            if (channel := channels.get_nowait(channel_id)) is not None
        ]
        return utils._unique(found)

    async def get_channel_mentions(self) -> list[GuildChannel]:
        """|coro|

        Returns the cached channels mentioned in the message content with the
        syntax of ``<#channel_id>``.

        Returns
        -------
        List[:class:`abc.GuildChannel`]
            The cached channels that were mentioned, without duplicates.
        """
        if self.guild_id is None:
            return []
        channels = self._state._guild_bucket("channels", self.guild_id)
        found = [
            channel
            for channel_id in self.raw_channel_mentions
            if (channel := await channels.get(channel_id)) is not None
        ]
        return utils._unique(found)

    async def get_role_mentions(self) -> list[Role]:
        """|coro|

        Returns the cached roles mentioned in the message.

        Returns
        -------
        List[:class:`Role`]
            The cached roles that were mentioned.
        """
        if self.guild_id is None:
            return []
        roles = self._state._guild_bucket("roles", self.guild_id)
        return [
            role
            for role_id in self.role_mention_ids
            if (role := await roles.get(role_id)) is not None
        ]

    @utils.cached_slot_property("_cs_clean_content")
    def clean_content(self) -> str:
        """A property that returns the content in a "cleaned up" manner.

        This basically means that mentions are transformed
        into the way the client shows it. e.g. ``<#id>`` will transform
        into ``#name``.

        This will also transform @everyone and @here mentions into
        non-mentions.

        This reads the in-memory cache, use :meth:`get_clean_content` with a remote cache backend.

        .. note::

            This *does not* affect markdown. If you want to escape
            or remove markdown then use :func:`utils.escape_markdown` or :func:`utils.remove_markdown`
            respectively, along with this function.
        """
        return self._clean_content(self.channel_mentions, self.role_mentions)

    async def get_clean_content(self) -> str:
        """|coro|

        Returns the content in a "cleaned up"
        manner, like :attr:`clean_content`, looking the mentioned channels and
        roles up through the asynchronous cache API.

        Returns
        -------
        :class:`str`
            The cleaned up content.
        """
        return self._clean_content(
            await self.get_channel_mentions(), await self.get_role_mentions()
        )

    def _clean_content(self, channels: list[GuildChannel], roles: list[Role]) -> str:
        transformations = {
            re.escape(f"<#{channel.id}>"): f"#{channel.name}" for channel in channels
        }

        mention_transforms = {
            re.escape(f"<@{member.id}>"): f"@{member.display_name}"
            for member in self.mentions
        }

        # add the <@!user_id> cases as well..
        second_mention_transforms = {
            re.escape(f"<@!{member.id}>"): f"@{member.display_name}"
            for member in self.mentions
        }

        transformations.update(mention_transforms)
        transformations.update(second_mention_transforms)

        if self.guild_id is not None:
            role_transforms = {
                re.escape(f"<@&{role.id}>"): f"@{role.name}" for role in roles
            }
            transformations.update(role_transforms)

        def repl(obj: re.Match[str]) -> str:
            return transformations.get(re.escape(obj.group(0)), "")

        pattern = re.compile("|".join(transformations.keys()))
        result = pattern.sub(repl, self.content)
        return escape_mentions(result)

    @property
    def created_at(self) -> dt.datetime:
        """The message's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def edited_at(self) -> dt.datetime | None:
        """An aware UTC datetime object containing the edited time of the message."""
        return self._edited_timestamp

    @property
    def jump_url(self) -> str:
        """Returns a URL that allows the client to jump to this message."""
        guild_id = getattr(self.guild, "id", "@me")
        return f"https://discord.com/channels/{guild_id}/{self.channel.id}/{self.id}"

    @property
    def channel(self) -> MessageableChannel | PartialMessageable:
        """The channel the message was sent in.

        This is the cached channel when it is available in an in-process cache,
        otherwise a :class:`PartialMessageable` handle.
        Use :meth:`get_channel` to look the cached channel up with any cache backend.
        """
        return cached_channel(self._state, self.channel_id) or self._partial_channel()

    @property
    def guild(self) -> Guild | PartialGuild | None:
        """The guild that the message belongs to, if applicable.

        This is the cached guild when it is available in an in-process cache,
        otherwise a :class:`PartialGuild` handle.
        Use :meth:`get_guild` to look the cached guild up with any cache backend.
        """
        if self.guild_id is None:
            return None
        return cached_guild(self._state, self.guild_id) or PartialGuild(
            state=self._state, id=self.guild_id
        )

    def _partial_channel(self) -> PartialMessageable:
        return PartialMessageable(
            state=self._state, id=self.channel_id, type=self._channel_type
        )

    async def get_channel(self) -> MessageableChannel | None:
        """|coro|

        Returns the cached channel the message was sent in.

        Returns
        -------
        Optional[Union[:class:`TextChannel`, :class:`VoiceChannel`, :class:`StageChannel`, :class:`DMChannel`, :class:`GroupChannel`, :class:`Thread`]]
            The channel, or ``None`` if it is not cached.
        """
        return await self._partial_channel().get()

    async def get_guild(self) -> Guild | None:
        """|coro|

        Returns the cached guild that the message belongs to.

        Returns
        -------
        Optional[:class:`Guild`]
            The guild, or ``None`` if it is not cached or the message is not in a guild.
        """
        return await self._state._get_guild(self.guild_id)

    @property
    def poll(self) -> Poll | None:
        """The cached poll of this message, if any.

        This reads the in-process cache, use :meth:`get_poll` with a remote
        cache backend.

        Raises
        ------
        SyncCacheAccessError
            The cache backend is not the in-process one.
        """
        return self._state._polls.get_nowait(self.id)

    async def get_poll(self) -> Poll | None:
        """|coro|

        Returns the cached poll of this message.

        Returns
        -------
        Optional[:class:`Poll`]
            The poll, or ``None`` if it is not cached.
        """
        return await self._state.get_poll(self.id)

    def is_system(self) -> bool:
        """Whether the message is a system message.

        A system message is a message that is constructed entirely by the Discord API
        in response to something.

        .. versionadded:: 1.3
        """
        return self.type not in (
            MessageType.default,
            MessageType.reply,
            MessageType.application_command,
            MessageType.thread_starter_message,
        )

    @utils.cached_slot_property("_cs_system_content")
    def system_content(self) -> str | None:
        r"""A property that returns the content that is rendered regardless of the :attr:`Message.type`.

        In the case of :attr:`MessageType.default` and :attr:`MessageType.reply`\,
        this just returns the regular :attr:`Message.content`, and forwarded messages
        will display the original message's content from :attr:`Message.snapshots`. Otherwise, this
        returns an English message denoting the contents of the system message.

        This reads the in-memory cache, use :meth:`get_system_content` with a remote cache backend.
        """
        guild_name = None
        if self.guild_id is not None:
            guild = self._state._guilds.get_nowait(self.guild_id)
            guild_name = guild.name if guild is not None else None
        return self._system_content(guild_name)

    async def get_system_content(self) -> str | None:
        r"""|coro|

        Returns the content that is rendered regardless of the :attr:`Message.type`,
        like :attr:`system_content`, looking the guild up through the asynchronous cache API.

        Returns
        -------
        Optional[:class:`str`]
            The rendered content, or ``None`` for message types without one.
        """
        guild = await self.get_guild()
        guild_name = guild.name if guild is not None else None
        return self._system_content(guild_name)

    def _system_content(self, guild_name: str | None) -> str | None:
        if self.type is MessageType.default:
            if self.snapshots:
                return self.snapshots[0].message and self.snapshots[0].message.content
            return self.content

        if self.type is MessageType.recipient_add:
            if self.channel.type is ChannelType.group:
                return f"{self.author.name} added {self.mentions[0].name} to the group."
            return f"{self.author.name} added {self.mentions[0].name} to the thread."

        if self.type is MessageType.recipient_remove:
            if self.channel.type is ChannelType.group:
                return (
                    f"{self.author.name} removed {self.mentions[0].name} from the"
                    " group."
                )
            return (
                f"{self.author.name} removed {self.mentions[0].name} from the thread."
            )

        if self.type is MessageType.channel_name_change:
            return f"{self.author.name} changed the channel name: **{self.content}**"

        if self.type is MessageType.channel_icon_change:
            return f"{self.author.name} changed the channel icon."

        if self.type is MessageType.pins_add:
            return f"{self.author.name} pinned a message to this channel."

        if self.type is MessageType.new_member:
            formats = [
                "{0} joined the party.",
                "{0} is here.",
                "Welcome, {0}. We hope you brought pizza.",
                "A wild {0} appeared.",
                "{0} just landed.",
                "{0} just slid into the server.",
                "{0} just showed up!",
                "Welcome {0}. Say hi!",
                "{0} hopped into the server.",
                "Everyone welcome {0}!",
                "Glad you're here, {0}.",
                "Good to see you, {0}.",
                "Yay you made it, {0}!",
            ]

            created_at_ms = int(self.created_at.timestamp() * 1000)
            return formats[created_at_ms % len(formats)].format(self.author.name)

        if self.type is MessageType.premium_guild_subscription:
            if not self.content:
                return f"{self.author.name} just boosted the server!"
            return (
                f"{self.author.name} just boosted the server **{self.content}** times!"
            )

        if self.type is MessageType.premium_guild_tier_1:
            if not self.content:
                return (
                    f"{self.author.name} just boosted the server! {guild_name} has"
                    " achieved **Level 1!**"
                )
            return (
                f"{self.author.name} just boosted the server **{self.content}**"
                f" times! {guild_name} has achieved **Level 1!**"
            )

        if self.type is MessageType.premium_guild_tier_2:
            if not self.content:
                return (
                    f"{self.author.name} just boosted the server! {guild_name} has"
                    " achieved **Level 2!**"
                )
            return (
                f"{self.author.name} just boosted the server **{self.content}**"
                f" times! {guild_name} has achieved **Level 2!**"
            )

        if self.type is MessageType.premium_guild_tier_3:
            if not self.content:
                return (
                    f"{self.author.name} just boosted the server! {guild_name} has"
                    " achieved **Level 3!**"
                )
            return (
                f"{self.author.name} just boosted the server **{self.content}**"
                f" times! {guild_name} has achieved **Level 3!**"
            )

        if self.type is MessageType.channel_follow_add:
            return f"{self.author.name} has added {self.content} to this channel"

        if self.type is MessageType.guild_stream:
            # the author will be a Member
            activity_name = cast("Any", self.author).activity.name
            return f"{self.author.name} is live! Now streaming {activity_name}"

        if self.type is MessageType.guild_discovery_disqualified:
            return (
                "This server has been removed from Server Discovery because it no"
                " longer passes all the requirements. Check Server Settings for more"
                " details."
            )

        if self.type is MessageType.guild_discovery_requalified:
            return (
                "This server is eligible for Server Discovery again and has been"
                " automatically relisted!"
            )

        if self.type is MessageType.guild_discovery_grace_period_initial_warning:
            return (
                "This server has failed Discovery activity requirements for 1 week. If"
                " this server fails for 4 weeks in a row, it will be automatically"
                " removed from Discovery."
            )

        if self.type is MessageType.guild_discovery_grace_period_final_warning:
            return (
                "This server has failed Discovery activity requirements for 3 weeks in"
                " a row. If this server fails for 1 more week, it will be removed from"
                " Discovery."
            )

        if self.type is MessageType.thread_created:
            return (
                f"{self.author.name} started a thread: **{self.content}**. See all"
                " **threads**."
            )

        if self.type is MessageType.reply:
            return self.content

        if self.type is MessageType.thread_starter_message:
            if self.reference is None or self.reference.resolved is None:
                return "Sorry, we couldn't load the first message in this thread"

            # the resolved message for the reference will be a Message
            return cast("Message", self.reference.resolved).content

        if self.type is MessageType.guild_invite_reminder:
            return (
                "Wondering who to invite?\nStart by inviting anyone who can help you"
                " build the server!"
            )

        return None

    async def delete(
        self, *, delay: float | None = None, reason: str | None = None
    ) -> None:
        """|coro|

        Deletes the message.

        Your own messages could be deleted without any proper permissions. However, to
        delete other people's messages, you need the :attr:`~Permissions.manage_messages`
        permission.

        .. versionchanged:: 1.1
            Added the new ``delay`` keyword-only parameter.

        Parameters
        ----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message. If the deletion fails then it is silently ignored.
        reason: Optional[:class:`str`]
            The reason for deleting the message. Shows up on the audit log.

        Raises
        ------
        Forbidden
            You do not have proper permissions to delete the message.
        NotFound
            The message was deleted already
        HTTPException
            Deleting the message failed.
        """
        del_func = self._state.http.delete_message(
            self.channel.id, self.id, reason=reason
        )
        if delay is not None:
            utils.delay_task(delay, del_func)
        else:
            await del_func

    async def edit(
        self,
        content: str | None = MISSING,
        embed: Embed | None = MISSING,
        embeds: list[Embed] = MISSING,
        file: File | None = MISSING,
        files: list[File] | None = MISSING,
        attachments: list[Attachment] = MISSING,
        suppress: bool = MISSING,
        suppress_embeds: bool = MISSING,
        delete_after: float | None = None,
        allowed_mentions: AllowedMentions | None = MISSING,
        view: BaseView | None = MISSING,
    ) -> Message:
        """|coro|

        Edits the message.

        The content must be able to be transformed into a string via ``str(content)``.

        .. versionchanged:: 1.3
            The ``suppress`` keyword-only parameter was added.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The new content to replace the message with.
            Could be ``None`` to remove the content.
        embed: Optional[:class:`Embed`]
            The new embed to replace the original with.
            Could be ``None`` to remove the embed.
        embeds: List[:class:`Embed`]
            The new embeds to replace the original with. Must be a maximum of 10.
            To remove all embeds ``[]`` should be passed.

            .. versionadded:: 2.0
        file: Sequence[:class:`File`]
            A new file to add to the message.
        files: List[Sequence[:class:`File`]]
            New files to add to the message.
        attachments: List[:class:`Attachment`]
            A list of attachments to keep in the message. If ``[]`` is passed
            then all attachments are removed.
        suppress: :class:`bool`
            Whether to suppress embeds for the message. This removes
            all the embeds if set to ``True``. If set to ``False``
            this brings the embeds back if they were suppressed.
            Using this parameter requires :attr:`~.Permissions.manage_messages`.

            .. deprecated:: 2.8
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message. This removes
            all the embeds if set to ``True``. If set to ``False``
            this brings the embeds back if they were suppressed.
            Using this parameter requires :attr:`~.Permissions.manage_messages`.

            .. versionadded:: 2.8
        delete_after: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message we just edited. If the deletion fails,
            then it is silently ignored.
        allowed_mentions: Optional[:class:`~discord.AllowedMentions`]
            Controls the mentions being processed in this message. If this is
            passed, then the object is merged with :attr:`~discord.Client.allowed_mentions`.
            The merging behaviour only overrides attributes that have been explicitly passed
            to the object, otherwise it uses the attributes set in :attr:`~discord.Client.allowed_mentions`.
            If no object is passed at all then the defaults given by :attr:`~discord.Client.allowed_mentions`
            are used instead.

            .. versionadded:: 1.4
        view: Optional[:class:`~discord.ui.BaseView`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.

        Raises
        ------
        NotFound
            The message was not found.
        HTTPException
            Editing the message failed.
        Forbidden
            Tried to suppress a message without permissions or
            edited a message's content or embed that isn't yours.
        ~discord.InvalidArgument
            You specified both ``embed`` and ``embeds``,
            specified both ``file`` and ``files``, or either``file``
            or ``files`` were of the wrong type.
        """
        payload: dict[str, Any] = {}
        if content is not MISSING:
            payload["content"] = str(content) if content is not None else None
        if embed is not MISSING and embeds is not MISSING:
            raise InvalidArgument(
                "cannot pass both embed and embeds parameter to edit()"
            )

        if embed is not MISSING:
            payload["embeds"] = [] if embed is None else [embed.to_dict()]
        elif embeds is not MISSING:
            payload["embeds"] = [e.to_dict() for e in embeds]

        flags = MessageFlags._from_value(self.flags.value)

        if suppress is not MISSING:
            warn_deprecated("suppress", "suppress_embeds", "2.8")
            if suppress_embeds is MISSING:
                suppress_embeds = suppress

        if suppress_embeds is not MISSING:
            flags.suppress_embeds = suppress_embeds

        if allowed_mentions is MISSING:
            if (
                self._state.allowed_mentions is not None
                and self.author.id == self._state.self_id
            ):
                payload["allowed_mentions"] = self._state.allowed_mentions.to_dict()
        elif allowed_mentions is not None:
            if self._state.allowed_mentions is not None:
                payload["allowed_mentions"] = self._state.allowed_mentions.merge(
                    allowed_mentions
                ).to_dict()
            else:
                payload["allowed_mentions"] = allowed_mentions.to_dict()

        if attachments is not MISSING:
            payload["attachments"] = [a.to_dict() for a in attachments]

        if view is not MISSING:
            self._state.prevent_view_updates_for(self.id)
            payload["components"] = view.to_components() if view else []
            if view and view.is_components_v2():
                flags.is_components_v2 = True
        if file is not MISSING and files is not MISSING:
            raise InvalidArgument("cannot pass both file and files parameter to edit()")

        if flags.value != self.flags.value:
            payload["flags"] = flags.value

        if file is not MISSING or files is not MISSING:
            if file is not MISSING:
                if not isinstance(file, File):
                    raise InvalidArgument("file parameter must be of type File")
                upload = [file]
            else:
                upload = cast("list[File]", files)
                if len(upload) > 10:
                    raise InvalidArgument(
                        "files parameter must be a list of up to 10 elements"
                    )
                if not all(isinstance(f, File) for f in upload):  # pyright: ignore[reportUnnecessaryIsInstance]
                    raise InvalidArgument("files parameter must be a list of File")

            if "attachments" not in payload:
                # don't want it to remove any attachments when we just add a new file
                payload["attachments"] = [a.to_dict() for a in self.attachments]
            try:
                data = await self._state.http.edit_files(
                    self.channel.id,
                    self.id,
                    files=upload,
                    **payload,
                )
            finally:
                for f in upload:
                    f.close()
        else:
            data = await self._state.http.edit_message(
                self.channel.id, self.id, **payload
            )
        message = await self._state._create_message(channel=self.channel, data=data)

        if view and not view.is_finished():
            view.message = message
            view._refresh(message.components)
            if view.is_dispatchable():
                self._state.store_view(view, self.id)

        if delete_after is not None:
            await self.delete(delay=delete_after)

        return message

    async def publish(self) -> None:
        """|coro|

        Publishes this message to your announcement channel.

        You must have the :attr:`~Permissions.send_messages` permission to do this.

        If the message is not your own then the :attr:`~Permissions.manage_messages`
        permission is also needed.

        Raises
        ------
        Forbidden
            You do not have the proper permissions to publish this message.
        HTTPException
            Publishing the message failed.
        """
        await self._state.http.publish_message(self.channel.id, self.id)

    async def pin(self, *, reason: str | None = None) -> None:
        """|coro|

        Pins the message.

        You must have the :attr:`~Permissions.pin_messages` permission to do
        this in a non-private channel context.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for pinning the message. Shows up on the audit log.

            .. versionadded:: 1.4

        Raises
        ------
        Forbidden
            You do not have permissions to pin the message.
        NotFound
            The message or channel was not found or deleted.
        HTTPException
            Pinning the message failed, probably due to the channel
            having more than 50 pinned messages.
        """
        await self._state.http.pin_message(self.channel.id, self.id, reason=reason)
        self.pinned = True

    async def unpin(self, *, reason: str | None = None) -> None:
        """|coro|

        Unpins the message.

        You must have the :attr:`~Permissions.pin_messages` permission to do
        this in a non-private channel context.

        Parameters
        ----------
        reason: Optional[:class:`str`]
            The reason for unpinning the message. Shows up on the audit log.

            .. versionadded:: 1.4

        Raises
        ------
        Forbidden
            You do not have permissions to unpin the message.
        NotFound
            The message or channel was not found or deleted.
        HTTPException
            Unpinning the message failed.
        """
        await self._state.http.unpin_message(self.channel.id, self.id, reason=reason)
        self.pinned = False

    async def add_reaction(self, emoji: EmojiInputType) -> None:
        """|coro|

        Add a reaction to the message.

        The emoji may be a unicode emoji, a custom :class:`GuildEmoji`, or an :class:`AppEmoji`.

        You must have the :attr:`~Permissions.read_message_history` permission
        to use this. If nobody else has reacted to the message using this
        emoji, the :attr:`~Permissions.add_reactions` permission is required.

        Parameters
        ----------
        emoji: Union[:class:`GuildEmoji`, :class:`AppEmoji`, :class:`Reaction`, :class:`PartialEmoji`, :class:`str`]
            The emoji to react with.

        Raises
        ------
        HTTPException
            Adding the reaction failed.
        Forbidden
            You do not have the proper permissions to react to the message.
        NotFound
            The emoji you specified was not found.
        InvalidArgument
            The emoji parameter is invalid.
        """
        emoji = convert_emoji_reaction(emoji)
        await self._state.http.add_reaction(self.channel.id, self.id, emoji)

    async def remove_reaction(
        self, emoji: EmojiInputType | Reaction, member: Snowflake
    ) -> None:
        """|coro|

        Remove a reaction by the member from the message.

        The emoji may be a unicode emoji, a custom :class:`GuildEmoji`, or an :class:`AppEmoji`.

        If the reaction is not your own (i.e. ``member`` parameter is not you) then
        the :attr:`~Permissions.manage_messages` permission is needed.

        The ``member`` parameter must represent a member and meet
        the :class:`abc.Snowflake` abc.

        Parameters
        ----------
        emoji: Union[:class:`GuildEmoji`, :class:`AppEmoji`, :class:`Reaction`, :class:`PartialEmoji`, :class:`str`]
            The emoji to remove.
        member: :class:`abc.Snowflake`
            The member for which to remove the reaction.

        Raises
        ------
        HTTPException
            Removing the reaction failed.
        Forbidden
            You do not have the proper permissions to remove the reaction.
        NotFound
            The member or emoji you specified was not found.
        InvalidArgument
            The emoji parameter is invalid.
        """
        emoji = convert_emoji_reaction(emoji)

        if member.id == self._state.self_id:
            await self._state.http.remove_own_reaction(self.channel.id, self.id, emoji)
        else:
            await self._state.http.remove_reaction(
                self.channel.id, self.id, emoji, member.id
            )

    async def clear_reaction(self, emoji: EmojiInputType | Reaction) -> None:
        """|coro|

        Clears a specific reaction from the message.

        The emoji may be a unicode emoji, a custom :class:`GuildEmoji`, or an :class:`AppEmoji`.

        You need the :attr:`~Permissions.manage_messages` permission to use this.

        .. versionadded:: 1.3

        Parameters
        ----------
        emoji: Union[:class:`GuildEmoji`, :class:`AppEmoji`, :class:`Reaction`, :class:`PartialEmoji`, :class:`str`]
            The emoji to clear.

        Raises
        ------
        HTTPException
            Clearing the reaction failed.
        Forbidden
            You do not have the proper permissions to clear the reaction.
        NotFound
            The emoji you specified was not found.
        InvalidArgument
            The emoji parameter is invalid.
        """
        emoji = convert_emoji_reaction(emoji)
        await self._state.http.clear_single_reaction(self.channel.id, self.id, emoji)

    async def clear_reactions(self) -> None:
        """|coro|

        Removes all the reactions from the message.

        You need the :attr:`~Permissions.manage_messages` permission to use this.

        Raises
        ------
        HTTPException
            Removing the reactions failed.
        Forbidden
            You do not have the proper permissions to remove all the reactions.
        """
        await self._state.http.clear_reactions(self.channel.id, self.id)

    async def create_thread(
        self,
        *,
        name: str,
        auto_archive_duration: ThreadArchiveDuration = MISSING,
        slowmode_delay: int = MISSING,
    ) -> Thread:
        """|coro|

        Creates a public thread from this message.

        You must have :attr:`~discord.Permissions.create_public_threads` in order to
        create a public thread from a message.

        The channel this message belongs in must be a :class:`TextChannel`.

        .. versionadded:: 2.0

        Parameters
        ----------
        name: :class:`str`
            The name of the thread.
        auto_archive_duration:  Optional[:class:`int`]
            The duration in minutes before a thread is automatically archived for inactivity.
            If not provided, the channel's default auto archive duration is used.
        slowmode_delay: Optional[:class:`int`]
            Specifies the slowmode rate limit for user in this thread, in seconds.
            A value of ``0`` disables slowmode. The maximum value possible is ``21600``.

        Returns
        -------
        :class:`.Thread`
            The created thread.

        Raises
        ------
        Forbidden
            You do not have permissions to create a thread.
        HTTPException
            Creating the thread failed.
        InvalidArgument
            This message does not have guild info attached.
        """
        if self.guild is None:
            raise InvalidArgument("This message does not have guild info attached.")

        default_auto_archive_duration: ThreadArchiveDuration = getattr(
            await self.get_channel(), "default_auto_archive_duration", 1440
        )

        data = await self._state.http.start_thread_with_message(
            self.channel.id,
            self.id,
            name=name,
            auto_archive_duration=auto_archive_duration
            or default_auto_archive_duration,
            rate_limit_per_user=slowmode_delay or 0,
        )

        self.thread = Thread(guild=self.guild, state=self._state, data=data)
        return self.thread

    async def reply(self, content: str | None = None, **kwargs: Any) -> Message:
        """|coro|

        A shortcut method to :meth:`.abc.Messageable.send` to reply to the
        :class:`.Message`.

        .. versionadded:: 1.6

        Returns
        -------
        :class:`.Message`
            The message that was sent.

        Raises
        ------
        ~discord.HTTPException
            Sending the message failed.
        ~discord.Forbidden
            You do not have the proper permissions to send the message.
        ~discord.InvalidArgument
            The ``files`` list is not of the appropriate size, or
            you specified both ``file`` and ``files``.
        """
        return await self.channel.send(content, reference=self.to_reference(), **kwargs)

    async def forward_to(
        self, channel: MessageableChannel | PartialMessageableChannel, **kwargs: Any
    ) -> Message:
        """|coro|

        A shortcut method to :meth:`.abc.Messageable.send` to forward the
        :class:`.Message` to a channel.

        .. versionadded:: 2.7

        Parameters
        ----------
        channel: Union[:class:`TextChannel`, :class:`Thread`, :class:`DMChannel`, :class:`GroupChannel`, :class:`PartialMessageable`]
            The channel to forward this to.

        Returns
        -------
        :class:`.Message`
            The message that was sent.

        Raises
        ------
        ~discord.HTTPException
            Sending the message failed.
        ~discord.Forbidden
            You do not have the proper permissions to send the message.
        ~discord.InvalidArgument
            The ``files`` list is not of the appropriate size, or
            you specified both ``file`` and ``files``.
        """
        return await channel.send(
            reference=self.to_reference(type=MessageReferenceType.forward), **kwargs
        )

    async def end_poll(self) -> Message:
        """|coro|

        Immediately ends the poll associated with this message. Only doable by the poll's owner.

        .. versionadded:: 2.6

        Returns
        -------
        :class:`Message`
            The updated message.

        Raises
        ------
        Forbidden
            You do not have permissions to end this poll.
        HTTPException
            Ending this poll failed.
        """
        data = await self._state.http.expire_poll(
            self.channel.id,
            self.id,
        )
        return await self._state._create_message(channel=self.channel, data=data)

    def search_replies(self, **filters: Any) -> MessageSearchIterator:
        """Retrieves an :class:`.AsyncIterator` of the messages replying to this message.

        This is :meth:`Guild.search_messages` with ``replied_to_messages`` set to this message.

        .. versionadded:: 3.0

        Raises
        ------
        ValueError
            This message is not in a guild.
        """
        guild = self.guild
        if guild is None:
            raise ValueError("only messages of a guild can be searched")
        return guild.search_messages(replied_to_messages=[self], **filters)

    def to_reference(
        self,
        *,
        fail_if_not_exists: bool = True,
        type: MessageReferenceType | None = None,
    ) -> MessageReference:
        """Creates a :class:`~discord.MessageReference` from the current message.

        .. versionadded:: 1.6

        Parameters
        ----------
        fail_if_not_exists: :class:`bool`
            Whether replying using the message reference should raise :class:`HTTPException`
            if the message no longer exists or Discord could not fetch the message.

            .. versionadded:: 1.7

        type: Optional[:class:`~discord.MessageReferenceType`]
            The type of message reference. Defaults to a reply.

            .. versionadded:: 2.7

        Returns
        -------
        :class:`~discord.MessageReference`
            The reference to this message.
        """
        return MessageReference.from_message(
            self,
            fail_if_not_exists=fail_if_not_exists,
            type=cast("MessageReferenceType", type),
        )

    def to_message_reference_dict(
        self, type: MessageReferenceType | None = None
    ) -> MessageReferencePayload:
        """Convert this message to a reference payload."""
        data = cast(
            "MessageReferencePayload",
            {
                "message_id": self.id,
                "channel_id": self.channel.id,
                "type": type and type.value,
            },
        )

        if self.guild is not None:
            data["guild_id"] = self.guild.id

        return data

    def get_view(self) -> BaseView:
        """Gets the view attached to this message.

        If a view is being tracked for this message, it is returned. Otherwise a new
        view is built from the components of the message: a :class:`~discord.ui.DesignerView`
        if the message uses components v2, a :class:`~discord.ui.View` otherwise. That view
        is not registered to listen for interactions.

        .. versionadded:: 3.0

        Returns
        -------
        :class:`~discord.ui.BaseView`
            The view attached to this message.
        """
        view = self._state.get_message_view(self.id)
        if view is not None:
            return view
        from .ui import DesignerView, View

        if self.flags.is_components_v2:
            return DesignerView.from_message(self, store=False)
        return View.from_message(self, store=False)

    def get_component(self, id: str | int) -> Component | None:
        """Gets a component from this message. Roughly equal to `utils.get(message.components, ...)`.

        If an :class:`int` is provided, the component will be retrieved by ``id``, otherwise by  ``custom_id``.
        This method will also search nested components.

        Parameters
        ----------
        id: Union[:class:`str`, :class:`int`]
            The id or custom_id the item to get

        Returns
        -------
        Optional[:class:`Component`]
            The component with the matching ``custom_id`` or ``id`` if it exists.
        """
        if not id:
            return None
        attr = "id" if isinstance(id, int) else "custom_id"
        for i in self.components:
            if getattr(i, attr, None) == id:
                return i
            if hasattr(i, "get_component") and (
                component := cast("Any", i).get_component(id)
            ):
                return component
        return None


class PartialMessage(Hashable):
    """Represents a partial message to aid with working messages when only a message and channel ID are present.

    There are two ways to construct this class. The first one is through
    the constructor itself, and the second is via the following:

    - :meth:`TextChannel.get_partial_message`
    - :meth:`Thread.get_partial_message`
    - :meth:`DMChannel.get_partial_message`
    - :meth:`VoiceChannel.get_partial_message`
    - :meth:`StageChannel.get_partial_message`
    - :meth:`PartialMessageable.get_partial_message`

    Note that this class is trimmed down and has no rich attributes.

    .. versionadded:: 1.6

    .. container:: operations

        .. describe:: x == y

            Checks if two partial messages are equal.

        .. describe:: x != y

            Checks if two partial messages are not equal.

        .. describe:: hash(x)

            Returns the partial message's hash.

    Attributes
    ----------
    channel: Union[:class:`TextChannel`, :class:`Thread`, :class:`DMChannel`, :class:`VoiceChannel`, :class:`StageChannel`, :class:`PartialMessageable`]
        The channel associated with this partial message.
    id: :class:`int`
        The message ID.
    """

    __slots__ = ("_cs_guild", "_guild_id", "_state", "channel", "id")

    jump_url: str = cast("str", Message.jump_url)
    delete = Message.delete
    publish = Message.publish
    pin = Message.pin
    unpin = Message.unpin
    add_reaction = Message.add_reaction
    remove_reaction = Message.remove_reaction
    clear_reaction = Message.clear_reaction
    clear_reactions = Message.clear_reactions
    reply = Message.reply
    forward_to = Message.forward_to
    to_reference = Message.to_reference
    to_message_reference_dict = Message.to_message_reference_dict

    def __init__(
        self,
        *,
        channel: PartialMessageableChannel,
        id: int,
        guild_id: int | None = None,
    ) -> None:
        if channel.type not in (
            ChannelType.text,
            ChannelType.voice,
            ChannelType.stage_voice,
            ChannelType.news,
            ChannelType.private,
            ChannelType.news_thread,
            ChannelType.public_thread,
            ChannelType.private_thread,
        ) and not isinstance(channel, PartialMessageable):
            raise TypeError(
                "Expected TextChannel, VoiceChannel, StageChannel, DMChannel, Thread or PartialMessageable not"
                f" {type(channel)!r}"
            )

        self.channel: PartialMessageableChannel = channel
        self._state: ConnectionState = channel._state
        self.id: int = id
        self._guild_id: int | None = guild_id

    def _update(self, data: object) -> None:
        # This is used for duck typing purposes.
        # Just do nothing with the data.
        pass

    # Also needed for duck typing purposes
    # n.b. not exposed
    pinned = property(None, lambda _x, _y: None)

    def __repr__(self) -> str:
        return f"<PartialMessage id={self.id} channel={self.channel!r}>"

    @property
    def created_at(self) -> dt.datetime:
        """The partial message's creation time in UTC."""
        return utils.snowflake_time(self.id)

    @property
    def poll(self) -> Poll | None:
        """The cached poll of this message, if any.

        This reads the in-process cache, use :meth:`get_poll` with a remote
        cache backend.

        Raises
        ------
        SyncCacheAccessError
            The cache backend is not the in-process one.
        """
        return self._state._polls.get_nowait(self.id)

    async def get_poll(self) -> Poll | None:
        """|coro|

        Returns the cached poll of this message.

        Returns
        -------
        Optional[:class:`Poll`]
            The poll, or ``None`` if it is not cached.
        """
        return await self._state.get_poll(self.id)

    async def get(self) -> Message | None:
        """|coro|

        Returns the cached message.

        Returns
        -------
        Optional[:class:`Message`]
            The message, or ``None`` if it is not cached.
        """
        return await self._state._get_message(self.id)

    @utils.cached_slot_property("_cs_guild")
    def guild(self) -> PartialGuild | None:
        """A handle to the guild that the partial message belongs to, if applicable."""
        guild_id = getattr(self.channel, "guild_id", None) or self._guild_id
        if guild_id is None:
            return None
        return PartialGuild(state=self._state, id=guild_id)

    async def fetch(self) -> Message:
        """|coro|

        Fetches the partial message to a full :class:`Message`.

        Returns
        -------
        :class:`Message`
            The full message.

        Raises
        ------
        NotFound
            The message was not found.
        Forbidden
            You do not have the permissions required to get a message.
        HTTPException
            Retrieving the message failed.
        """
        data = await self._state.http.get_message(self.channel.id, self.id)
        return await self._state._cache_fetched(
            await self._state._create_message(channel=self.channel, data=data)
        )

    async def edit(self, **fields: Any) -> Message | None:
        """|coro|

        Edits the message.

        .. versionchanged:: 1.7
            :class:`discord.Message` is returned instead of ``None`` if an edit took place.

        Parameters
        ----------
        content: Optional[:class:`str`]
            The new content to replace the message with.
            Could be ``None`` to remove the content.
        embed: Optional[:class:`~discord.Embed`]
            The new embed to replace the original with.
            Could be ``None`` to remove the embed.
        embeds: Optional[List[:class:`~discord.Embed`]]
            A list of embeds to upload. Must be a maximum of 10.

            .. versionadded:: 2.0
        suppress: :class:`bool`
            Whether to suppress embeds for the message. This removes
            all the embeds if set to ``True``. If set to ``False``
            this brings the embeds back if they were suppressed.
            Using this parameter requires :attr:`~.Permissions.manage_messages`.
        delete_after: Optional[:class:`float`]
            If provided, the number of seconds to wait in the background
            before deleting the message we just edited. If the deletion fails,
            then it is silently ignored.
        allowed_mentions: Optional[:class:`~discord.AllowedMentions`]
            Controls the mentions being processed in this message. If this is
            passed, then the object is merged with :attr:`~discord.Client.allowed_mentions`.
            The merging behaviour only overrides attributes that have been explicitly passed
            to the object, otherwise it uses the attributes set in :attr:`~discord.Client.allowed_mentions`.
            If no object is passed at all then the defaults given by :attr:`~discord.Client.allowed_mentions`
            are used instead.
        view: Optional[:class:`~discord.ui.BaseView`]
            The updated view to update this message with. If ``None`` is passed then
            the view is removed.

            .. versionadded:: 2.0

        Returns
        -------
        Optional[:class:`Message`]
            The message that was edited.

        Raises
        ------
        NotFound
            The message was not found.
        HTTPException
            Editing the message failed.
        Forbidden
            Tried to suppress a message without permissions or
            edited a message's content or embed that isn't yours.
        """
        content = fields.pop("content", MISSING)
        if content is not MISSING:
            fields["content"] = str(content) if content is not None else None

        embed = fields.pop("embed", MISSING)
        embeds = fields.pop("embeds", MISSING)

        if embed is not MISSING and embeds is not MISSING:
            raise InvalidArgument("Cannot pass both embed and embeds parameters.")

        if embed is not MISSING:
            fields["embeds"] = [] if embed is None else [embed.to_dict()]

        if embeds is not MISSING:
            fields["embeds"] = [embed.to_dict() for embed in embeds]

        suppress = fields.pop("suppress", False)
        flags = MessageFlags._from_value(0)
        flags.suppress_embeds = suppress

        delete_after = fields.pop("delete_after", None)

        allowed_mentions = fields.get("allowed_mentions", MISSING)
        if allowed_mentions is not MISSING:
            if self._state.allowed_mentions is not None:
                allowed_mentions = self._state.allowed_mentions.merge(
                    allowed_mentions
                ).to_dict()
            else:
                allowed_mentions = allowed_mentions.to_dict()
            fields["allowed_mentions"] = allowed_mentions
        else:
            fields["allowed_mentions"] = (
                self._state.allowed_mentions.to_dict()
                if self._state.allowed_mentions
                else None
            )

        view = fields.pop("view", MISSING)
        if view is not MISSING:
            self._state.prevent_view_updates_for(self.id)
            fields["components"] = view.to_components() if view else []
            if view and view.is_components_v2():
                flags.is_components_v2 = True

        fields["flags"] = flags.value
        data = await self._state.http.edit_message(self.channel.id, self.id, **fields)

        if delete_after is not None:
            await self.delete(delay=delete_after)

        msg = await self._state._create_message(channel=self.channel, data=data)
        if view and not view.is_finished():
            view.message = msg
            view._refresh(msg.components)
            if view.is_dispatchable():
                self._state.store_view(view, self.id)
        return msg

    async def end_poll(self) -> Message:
        """|coro|

        Immediately ends the poll associated with this message. Only doable by the poll's owner.

        .. versionadded:: 2.6

        Returns
        -------
        :class:`Message`
            The updated message.

        Raises
        ------
        Forbidden
            You do not have permissions to end this poll.
        HTTPException
            Ending this poll failed.
        """
        data = await self._state.http.expire_poll(
            self.channel.id,
            self.id,
        )
        return await self._state._create_message(channel=self.channel, data=data)
