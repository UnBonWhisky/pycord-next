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

import datetime as dt
from typing import TYPE_CHECKING, Any, cast, overload

from ._internal.aliases import AliasMixin
from .asset import Asset
from .colour import Colour
from .enums import ActivityType, StatusDisplayType, try_enum
from .partial_emoji import PartialEmoji
from .utils import _get_as_snowflake

__all__ = (
    "Activity",
    "BaseActivity",
    "CustomActivity",
    "Game",
    "Spotify",
    "Streaming",
)

"""If you're curious, this is the current schema for an activity.

It's fairly long so I will document it here:

All keys are optional.

state: str (max: 128),
details: str (max: 128)
timestamps: dict
    start: int (min: 1)
    end: int (min: 1)
assets: dict
    large_image: str (max: 32)
    large_text: str (max: 128)
    small_image: str (max: 32)
    small_text: str (max: 128)
party: dict
    id: str (max: 128),
    size: List[int] (max-length: 2)
        elem: int (min: 1)
secrets: dict
    match: str (max: 128)
    join: str (max: 128)
    spectate: str (max: 128)
instance: bool
application_id: str
name: str (max: 128)
url: str
type: int
sync_id: str
session_id: str
flags: int
buttons: list[dict]
    label: str (max: 32)
    url: str (max: 512)
NOTE: Bots cannot access a user's activity button URLs. When received through the
gateway, the type of the buttons field will be list[str].

There are also activity flags which are mostly uninteresting for the library atm.

t.ActivityFlags = {
    INSTANCE: 1,
    JOIN: 2,
    SPECTATE: 4,
    JOIN_REQUEST: 8,
    SYNC: 16,
    PLAY: 32
}
"""

if TYPE_CHECKING:
    from .types.activity import (
        Activity as ActivityPayload,
        ActivityAssets,
        ActivityParty,
        ActivityTimestamps,
    )


class BaseActivity:
    """The base activity that all user-settable activities inherit from.

    A user-settable activity is one that can be used in :meth:`Client.change_presence`.

    The following types currently count as user-settable:

    - :class:`Activity`
    - :class:`Game`
    - :class:`Streaming`
    - :class:`CustomActivity`

    Note that although these types are considered user-settable by the library,
    Discord typically ignores certain combinations of activity depending on
    what is currently set. This behaviour may change in the future so there are
    no guarantees on whether Discord will actually let you set these types.

    .. versionadded:: 1.3
    """

    __slots__ = ("_created_at",)

    def __init__(self, **kwargs: Any) -> None:
        self._created_at: float | None = kwargs.pop("created_at", None)

    @property
    def created_at(self) -> dt.datetime | None:
        """When the user started doing this activity in UTC.

        .. versionadded:: 1.3
        """
        if self._created_at is not None:
            return dt.datetime.fromtimestamp(
                self._created_at / 1000, tz=dt.timezone.utc
            )
        return None

    def to_dict(self) -> ActivityPayload:
        """Convert the activity to the payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The activity payload.
        """
        raise NotImplementedError


class Activity(BaseActivity):
    """Represents an activity in Discord.

    This could be an activity such as streaming, playing, listening
    or watching.

    For memory optimisation purposes, some activities are offered in slimmed
    down versions:

    - :class:`Game`
    - :class:`Streaming`

    Attributes
    ----------
    application_id: Optional[:class:`int`]
        The application ID of the game.
    name: Optional[:class:`str`]
        The name of the activity.
    url: Optional[:class:`str`]
        A stream URL that the activity could be doing.
    type: :class:`ActivityType`
        The type of activity currently being done.
    state: Optional[:class:`str`]
        The user's current party status or text used for a custom status.
    details: Optional[:class:`str`]
        The detail of the user's current activity.
    state_url: Optional[:class:`str`]
        The URL that is linked when clicking on the state text.

        .. versionadded:: 3.0
    details_url: Optional[:class:`str`]
        The URL that is linked when clicking on the details text.

        .. versionadded:: 3.0
    status_display_type: Optional[:class:`StatusDisplayType`]
        Which field is displayed in the status text of the user, ``None`` when
        Discord did not send it.

        .. versionadded:: 3.0
    timestamps: Dict[:class:`str`, :class:`int`]
        A dictionary of timestamps. It contains the following optional keys:

        - ``start``: Corresponds to when the user started doing the
          activity in milliseconds since Unix epoch.
        - ``end``: Corresponds to when the user will finish doing the
          activity in milliseconds since Unix epoch.

    assets: Dict[:class:`str`, :class:`str`]
        A dictionary representing the images and their hover text of an activity.
        It contains the following optional keys:

        - ``large_image``: A string representing the ID for the large image asset.
        - ``large_text``: A string representing the text when hovering over the large image asset.
        - ``large_url``: A string representing the URL opened when clicking on the large image asset.
        - ``small_image``: A string representing the ID for the small image asset.
        - ``small_text``: A string representing the text when hovering over the small image asset.
        - ``small_url``: A string representing the URL opened when clicking on the small image asset.
        - ``invite_cover_image``: A string representing the ID for the banner shown on a game invite.

    party: Dict[:class:`str`, Union[:class:`str`, List[:class:`int`]]]
        A dictionary representing the activity party. It contains the following optional keys:

        - ``id``: A string representing the party ID.
        - ``size``: A list of up to two integer elements denoting (current_size, maximum_size).
    buttons: Union[List[Dict[:class:`str`, :class:`str`]], List[:class:`str`]]
        A list of dictionaries representing custom buttons shown in a rich presence.
        Each dictionary contains the following keys:

        - ``label``: A string representing the text shown on the button.
        - ``url``: A string representing the URL opened upon clicking the button.

        .. note::

            Bots cannot access a user's activity button URLs. Therefore, the type of this attribute
            will be List[:class:`str`] when received through the gateway.

        .. versionadded:: 2.0

    emoji: Optional[:class:`PartialEmoji`]
        The emoji that belongs to this activity.
    """

    __slots__ = (
        "_created_at",
        "application_id",
        "assets",
        "buttons",
        "details",
        "details_url",
        "emoji",
        "flags",
        "name",
        "party",
        "session_id",
        "state",
        "state_url",
        "status_display_type",
        "sync_id",
        "timestamps",
        "type",
        "url",
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.state: str | None = kwargs.pop("state", None)
        self.state_url: str | None = kwargs.pop("state_url", None)
        self.details: str | None = kwargs.pop("details", None)
        self.details_url: str | None = kwargs.pop("details_url", None)
        status_display_type = kwargs.pop("status_display_type", None)
        self.status_display_type: StatusDisplayType | None = (
            None
            if status_display_type is None
            else status_display_type
            if isinstance(status_display_type, StatusDisplayType)
            else try_enum(StatusDisplayType, status_display_type)
        )
        self.timestamps: ActivityTimestamps = kwargs.pop("timestamps", {})
        self.assets: ActivityAssets = kwargs.pop("assets", {})
        self.party: ActivityParty = kwargs.pop("party", {})
        self.application_id: int | None = _get_as_snowflake(kwargs, "application_id")
        self.url: str | None = kwargs.pop("url", None)
        self.flags: int = kwargs.pop("flags", 0)
        self.sync_id: str | None = kwargs.pop("sync_id", None)
        self.session_id: str | None = kwargs.pop("session_id", None)
        self.buttons: list[str] = kwargs.pop("buttons", [])

        activity_type = kwargs.pop("type", -1)
        self.type: ActivityType = (
            activity_type
            if isinstance(activity_type, ActivityType)
            else try_enum(ActivityType, activity_type)
        )
        self.name: str | None = kwargs.pop(
            "name", "Custom Status" if self.type == ActivityType.custom else None
        )

        emoji = kwargs.pop("emoji", None)
        self.emoji: PartialEmoji | None = (
            PartialEmoji.from_dict(emoji) if emoji is not None else None
        )

    def __repr__(self) -> str:
        attrs = (
            ("type", self.type),
            ("name", self.name),
            ("state", self.state),
            ("url", self.url),
            ("details", self.details),
            ("application_id", self.application_id),
            ("session_id", self.session_id),
            ("emoji", self.emoji),
        )
        inner = " ".join(f"{k}={v!r}" for k, v in attrs)
        return f"<Activity {inner}>"

    def to_dict(self) -> ActivityPayload:
        """Convert the activity to the payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The activity payload.
        """
        ret: dict[str, Any] = {}
        for attr in self.__slots__:
            value = getattr(self, attr, None)
            if value is None:
                continue

            if isinstance(value, dict) and not value:
                continue

            ret[attr] = value
        ret["type"] = int(self.type)
        if self.status_display_type is not None:
            ret["status_display_type"] = int(self.status_display_type)
        if self.emoji:
            ret["emoji"] = self.emoji.to_dict()
        return cast("ActivityPayload", ret)

    @property
    def start(self) -> dt.datetime | None:
        """When the user started doing this activity in UTC, if applicable."""
        start = self.timestamps.get("start")
        if start is None:
            return None
        return dt.datetime.fromtimestamp(start / 1000, tz=dt.timezone.utc)

    @property
    def end(self) -> dt.datetime | None:
        """When the user will stop doing this activity in UTC, if applicable."""
        end = self.timestamps.get("end")
        if end is None:
            return None
        return dt.datetime.fromtimestamp(end / 1000, tz=dt.timezone.utc)

    @property
    def large_image_url(self) -> str | None:
        """Returns a URL pointing to the large image asset of this activity if applicable."""
        if self.application_id is None:
            return None

        large_image = self.assets.get("large_image")
        if large_image is None:
            return None
        return f"{Asset.BASE}/app-assets/{self.application_id}/{large_image}.png"

    @property
    def small_image_url(self) -> str | None:
        """Returns a URL pointing to the small image asset of this activity if applicable."""
        if self.application_id is None:
            return None

        small_image = self.assets.get("small_image")
        if small_image is None:
            return None
        return f"{Asset.BASE}/app-assets/{self.application_id}/{small_image}.png"

    @property
    def large_image_text(self) -> str | None:
        """Returns the large image asset hover text of this activity if applicable."""
        return self.assets.get("large_text", None)

    @property
    def small_image_text(self) -> str | None:
        """Returns the small image asset hover text of this activity if applicable."""
        return self.assets.get("small_text", None)

    @property
    def large_url(self) -> str | None:
        """Returns the URL opened when clicking the large image of this activity, if any.

        .. versionadded:: 3.0
        """
        return self.assets.get("large_url", None)

    @property
    def small_url(self) -> str | None:
        """Returns the URL opened when clicking the small image of this activity, if any.

        .. versionadded:: 3.0
        """
        return self.assets.get("small_url", None)


class Game(BaseActivity):
    """A slimmed down version of :class:`Activity` that represents a Discord game.

    This is typically displayed via **Playing** on the official Discord client.

    .. container:: operations

        .. describe:: x == y

            Checks if two games are equal.

        .. describe:: x != y

            Checks if two games are not equal.

        .. describe:: hash(x)

            Returns the game's hash.

        .. describe:: str(x)

            Returns the game's name.

    Parameters
    ----------
    name: :class:`str`
        The game's name.

    Attributes
    ----------
    name: :class:`str`
        The game's name.
    """

    __slots__ = ("_end", "_start", "name")

    def __init__(self, name: str, **extra: Any) -> None:
        super().__init__(**extra)
        self.name: str = name

        try:
            timestamps: ActivityTimestamps = extra["timestamps"]
        except KeyError:
            self._start = 0
            self._end = 0
        else:
            self._start = timestamps.get("start", 0)
            self._end = timestamps.get("end", 0)

    @property
    def type(self) -> ActivityType:
        """Returns the game's type. This is for compatibility with :class:`Activity`.

        It always returns :attr:`ActivityType.playing`.
        """
        return ActivityType.playing

    @property
    def start(self) -> dt.datetime | None:
        """When the user started playing this game in UTC, if applicable."""
        if self._start:
            return dt.datetime.fromtimestamp(self._start / 1000, tz=dt.timezone.utc)
        return None

    @property
    def end(self) -> dt.datetime | None:
        """When the user will stop playing this game in UTC, if applicable."""
        if self._end:
            return dt.datetime.fromtimestamp(self._end / 1000, tz=dt.timezone.utc)
        return None

    def __str__(self) -> str:
        return str(self.name)

    def __repr__(self) -> str:
        return f"<Game name={self.name!r}>"

    def to_dict(self) -> ActivityPayload:
        """Convert the activity to the payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The activity payload.
        """
        timestamps: dict[str, Any] = {}
        if self._start:
            timestamps["start"] = self._start

        if self._end:
            timestamps["end"] = self._end

        return cast(
            "ActivityPayload",
            {
                "type": ActivityType.playing.value,
                "name": str(self.name),
                "timestamps": timestamps,
            },
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Game) and other.name == self.name

    def __hash__(self) -> int:
        return hash(self.name)


class Streaming(BaseActivity):
    """A slimmed down version of :class:`Activity` that represents a Discord streaming status.

    This is typically displayed via **Streaming** on the official Discord client.

    .. container:: operations

        .. describe:: x == y

            Checks if two streams are equal.

        .. describe:: x != y

            Checks if two streams are not equal.

        .. describe:: hash(x)

            Returns the stream's hash.

        .. describe:: str(x)

            Returns the stream's name.

    Attributes
    ----------
    platform: Optional[:class:`str`]
        Where the user is streaming from (ie. YouTube, Twitch).

        .. versionadded:: 1.3

    name: Optional[:class:`str`]
        The stream's name.
    details: Optional[:class:`str`]
        An alias for :attr:`name`
    game: Optional[:class:`str`]
        The game being streamed.

        .. versionadded:: 1.3

    url: :class:`str`
        The stream's URL.
    assets: Dict[:class:`str`, :class:`str`]
        A dictionary comprised of similar keys than those in :attr:`Activity.assets`.
    """

    __slots__ = ("assets", "details", "game", "name", "platform", "url")

    def __init__(self, *, name: str | None, url: str, **extra: Any) -> None:
        super().__init__(**extra)
        self.platform: str | None = name
        self.name: str | None = extra.pop("details", name)
        self.game: str | None = extra.pop("state", None)
        self.url: str = url
        self.details: str | None = extra.pop("details", self.name)  # compatibility
        self.assets: ActivityAssets = extra.pop("assets", {})

    @property
    def type(self) -> ActivityType:
        """Returns the game's type. This is for compatibility with :class:`Activity`.

        It always returns :attr:`ActivityType.streaming`.
        """
        return ActivityType.streaming

    def __str__(self) -> str:
        return str(self.name)

    def __repr__(self) -> str:
        return f"<Streaming name={self.name!r}>"

    @property
    def twitch_name(self) -> str | None:
        """If provided, the twitch name of the user streaming.

        This corresponds to the ``large_image`` key of the :attr:`Streaming.assets`
        dictionary if it starts with ``twitch:``. Typically this is set by the Discord client.
        """
        name = self.assets.get("large_image")
        if name is None:
            return None
        return name[7:] if name[:7] == "twitch:" else None

    def to_dict(self) -> ActivityPayload:
        """Convert the activity to the payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The activity payload.
        """
        ret: dict[str, Any] = {
            "type": ActivityType.streaming.value,
            "name": str(self.name),
            "url": str(self.url),
            "assets": self.assets,
        }
        if self.details:
            ret["details"] = self.details
        return cast("ActivityPayload", ret)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Streaming)
            and other.name == self.name
            and other.url == self.url
        )

    def __hash__(self) -> int:
        return hash(self.name)


class Spotify(AliasMixin):
    """Represents a Spotify listening activity from Discord. This is a special case of :class:`Activity` that makes it easier to work with the Spotify integration.

    .. container:: operations

        .. describe:: x == y

            Checks if two activities are equal.

        .. describe:: x != y

            Checks if two activities are not equal.

        .. describe:: hash(x)

            Returns the activity's hash.

        .. describe:: str(x)

            Returns the string 'Spotify'.
    """

    __slots__ = (
        "_assets",
        "_created_at",
        "_details",
        "_party",
        "_session_id",
        "_state",
        "_sync_id",
        "_timestamps",
    )

    def __init__(self, **data: Any) -> None:
        self._state: str = data.pop("state", "")
        self._details: str = data.pop("details", "")
        self._timestamps: dict[str, int] = data.pop("timestamps", {})
        self._assets: ActivityAssets = data.pop("assets", {})
        self._party: ActivityParty = data.pop("party", {})
        self._sync_id: str = data.pop("sync_id")
        self._session_id: str = data.pop("session_id")
        self._created_at: float | None = data.pop("created_at", None)

    @property
    def type(self) -> ActivityType:
        """Returns the activity's type. This is for compatibility with :class:`Activity`.

        It always returns :attr:`ActivityType.listening`.
        """
        return ActivityType.listening

    @property
    def created_at(self) -> dt.datetime | None:
        """When the user started listening in UTC.

        .. versionadded:: 1.3
        """
        if self._created_at is not None:
            return dt.datetime.fromtimestamp(
                self._created_at / 1000, tz=dt.timezone.utc
            )
        return None

    @property
    def colour(self) -> Colour:
        """Returns the Spotify integration colour, as a :class:`Colour`."""
        return Colour(0x1DB954)

    def to_dict(self) -> ActivityPayload:
        """Convert the activity to the payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The activity payload.
        """
        return cast(
            "ActivityPayload",
            {
                "flags": 48,  # SYNC | PLAY
                "name": "Spotify",
                "assets": self._assets,
                "party": self._party,
                "sync_id": self._sync_id,
                "session_id": self._session_id,
                "timestamps": self._timestamps,
                "details": self._details,
                "state": self._state,
            },
        )

    @property
    def name(self) -> str:
        """The activity's name. This will always return "Spotify"."""
        return "Spotify"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, Spotify)
            and other._session_id == self._session_id
            and other._sync_id == self._sync_id
            and other.start == self.start
        )

    def __hash__(self) -> int:
        return hash(self._session_id)

    def __str__(self) -> str:
        return "Spotify"

    def __repr__(self) -> str:
        return (
            "<Spotify"
            f" title={self.title!r} artist={self.artist!r} track_id={self.track_id!r}>"
        )

    @property
    def title(self) -> str:
        """The title of the song being played."""
        return self._details

    @property
    def artists(self) -> list[str]:
        """The artists of the song being played."""
        return self._state.split("; ")

    @property
    def artist(self) -> str:
        """The artist of the song being played.

        This does not attempt to split the artist information into
        multiple artists. Useful if there's only a single artist.
        """
        return self._state

    @property
    def album(self) -> str:
        """The album that the song being played belongs to."""
        return self._assets.get("large_text", "")

    @property
    def album_cover_url(self) -> str:
        """The album cover image URL from Spotify's CDN."""
        large_image = self._assets.get("large_image", "")
        if large_image[:8] != "spotify:":
            return ""
        album_image_id = large_image[8:]
        return f"https://i.scdn.co/image/{album_image_id}"

    @property
    def track_id(self) -> str:
        """The track ID used by Spotify to identify this song."""
        return self._sync_id

    @property
    def track_url(self) -> str:
        """The track URL to listen on Spotify.

        .. versionadded:: 2.0
        """
        return f"https://open.spotify.com/track/{self.track_id}"

    @property
    def start(self) -> dt.datetime:
        """When the user started playing this song in UTC."""
        return dt.datetime.fromtimestamp(
            self._timestamps["start"] / 1000, tz=dt.timezone.utc
        )

    @property
    def end(self) -> dt.datetime:
        """When the user will stop playing this song in UTC."""
        return dt.datetime.fromtimestamp(
            self._timestamps["end"] / 1000, tz=dt.timezone.utc
        )

    @property
    def duration(self) -> dt.timedelta:
        """The duration of the song being played."""
        return self.end - self.start

    @property
    def party_id(self) -> str:
        """The party ID of the listening party."""
        return self._party.get("id", "")

    if TYPE_CHECKING:
        color = colour


class CustomActivity(BaseActivity):
    """Represents a Custom activity from Discord.

    .. container:: operations

        .. describe:: x == y

            Checks if two activities are equal.

        .. describe:: x != y

            Checks if two activities are not equal.

        .. describe:: hash(x)

            Returns the activity's hash.

        .. describe:: str(x)

            Returns the custom status text.

    .. versionadded:: 1.3

    Attributes
    ----------
    name: Optional[:class:`str`]
        The custom activity's name.
    emoji: Optional[:class:`PartialEmoji`]
        The emoji to pass to the activity, if any.
    state: Optional[:class:`str`]
        The text used for the custom activity.
    """

    __slots__ = ("emoji", "name", "state")

    def __init__(
        self,
        name: str | None,
        *,
        emoji: PartialEmoji | str | dict[str, Any] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(**extra)
        self.name: str | None = name
        self.state: str | None = extra.pop("state", name)
        if self.name == "Custom Status":
            self.name = self.state

        value = cast("object", emoji)
        self.emoji: PartialEmoji | None
        if value is None:
            self.emoji = None
        elif isinstance(value, dict):
            self.emoji = PartialEmoji.from_dict(cast("dict[str, Any]", value))
        elif isinstance(value, str):
            self.emoji = PartialEmoji(name=value)
        elif isinstance(value, PartialEmoji):
            self.emoji = value
        else:
            raise TypeError(
                f"Expected str, PartialEmoji, or None, received {type(value)!r} instead."
            )

    @property
    def type(self) -> ActivityType:
        """Returns the activity's type. This is for compatibility with :class:`Activity`.

        It always returns :attr:`ActivityType.custom`.
        """
        return ActivityType.custom

    def to_dict(self) -> ActivityPayload:
        """Convert the activity to the payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The activity payload.
        """
        o: dict[str, Any]
        if self.name == self.state:
            o = {
                "type": ActivityType.custom.value,
                "state": self.name,
                "name": "Custom Status",
            }
        else:
            o = {
                "type": ActivityType.custom.value,
                "name": self.name,
            }

        if self.emoji:
            o["emoji"] = self.emoji.to_dict()
        return cast("ActivityPayload", o)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, CustomActivity)
            and other.name == self.name
            and other.emoji == self.emoji
        )

    def __hash__(self) -> int:
        return hash((self.name, str(self.emoji)))

    def __str__(self) -> str:
        if not self.emoji:
            return str(self.name)
        if self.name:
            return f"{self.emoji} {self.name}"
        return str(self.emoji)

    def __repr__(self) -> str:
        return f"<CustomActivity name={self.name!r} emoji={self.emoji!r}>"


ActivityTypes = Activity | Game | CustomActivity | Streaming | Spotify


@overload
def create_activity(data: ActivityPayload) -> ActivityTypes: ...


@overload
def create_activity(data: None) -> None: ...


def create_activity(data: ActivityPayload | None) -> ActivityTypes | None:
    if not data:
        return None

    game_type = try_enum(ActivityType, data.get("type", -1))
    if game_type is ActivityType.playing:
        if "application_id" in data or "session_id" in data:
            return Activity(**data)
        return Game(**data)
    kwargs = cast("dict[str, Any]", data)
    if game_type is ActivityType.custom:
        try:
            name = kwargs.pop("name")
        except KeyError:
            return Activity(**kwargs)
        else:
            # we removed the name key from data already
            return CustomActivity(name=name, **kwargs)
    elif game_type is ActivityType.streaming:
        if "url" in data:
            # the url won't be None here
            return Streaming(**kwargs)
        return Activity(**kwargs)
    elif (
        game_type is ActivityType.listening
        and "sync_id" in data
        and "session_id" in data
    ):
        return Spotify(**data)
    return Activity(**data)
