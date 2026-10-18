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

import datetime as dt
from typing import Any

import pytest

import discord
from discord.activity import (
    Activity,
    CustomActivity,
    Game,
    Spotify,
    Streaming,
    create_activity,
)
from discord.enums import ActivityType, StatusDisplayType

START = 1_700_000_000_000
END = START + 215_000


def moment(milliseconds: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(milliseconds / 1000, tz=dt.timezone.utc)


def test_activity_fields_and_urls() -> None:
    activity = Activity(
        type=0,
        name="Pycord",
        state="coding",
        details="a bot",
        application_id="42",
        session_id="s",
        timestamps={"start": START, "end": END},
        assets={
            "large_image": "big",
            "small_image": "small",
            "large_text": "Big",
            "small_text": "Small",
        },
        status_display_type=1,
        emoji={"name": "\N{FIRE}"},
        created_at=START,
    )

    assert activity.type is ActivityType.playing
    assert activity.status_display_type is StatusDisplayType.state
    assert activity.start == moment(START)
    assert activity.end == moment(END)
    assert (
        activity.large_image_url == "https://cdn.discordapp.com/app-assets/42/big.png"
    )
    assert (
        activity.small_image_url == "https://cdn.discordapp.com/app-assets/42/small.png"
    )
    assert activity.large_image_text == "Big"
    assert activity.small_image_text == "Small"
    assert activity.created_at == moment(START)
    assert "name='Pycord'" in repr(activity)
    assert repr(activity).startswith("<Activity type=")


def test_activity_without_assets_or_timestamps() -> None:
    activity = Activity(name="Plain")
    assert activity.start is None
    assert activity.end is None
    assert activity.large_image_url is None
    assert activity.small_image_url is None
    assert activity.large_image_text is None
    assert activity.small_image_text is None
    assert activity.created_at is None

    without_images = Activity(application_id="1", assets={"large_text": "x"})
    assert without_images.large_image_url is None
    assert without_images.small_image_url is None
    assert Activity(assets={"large_image": "x"}).large_image_url is None
    assert Activity(assets={"small_image": "x"}).small_image_url is None


def test_activity_to_dict_skips_empty_values() -> None:
    activity = Activity(
        type=ActivityType.watching,
        name="Videos",
        state="s",
        status_display_type=StatusDisplayType.details,
        emoji={"name": "\N{FIRE}"},
    )
    data = activity.to_dict()
    assert data["type"] == ActivityType.watching.value
    assert data["name"] == "Videos"
    assert data["state"] == "s"
    assert data["status_display_type"] == 2
    assert (
        data["emoji"] == {"name": "\N{FIRE}", "id": None, "animated": False}
        or data["emoji"]["name"] == "\N{FIRE}"
    )
    assert "timestamps" not in data
    assert "assets" not in data
    assert "details" not in data


def test_game() -> None:
    game = Game("Chess", timestamps={"start": START, "end": END})
    assert game.type is ActivityType.playing
    assert game.name == "Chess"
    assert str(game) == "Chess"
    assert repr(game) == "<Game name='Chess'>"
    assert game.start == moment(START)
    assert game.end == moment(END)
    assert game.to_dict() == {
        "type": 0,
        "name": "Chess",
        "timestamps": {"start": START, "end": END},
    }
    assert game == Game("Chess")
    assert game != Game("Go")
    assert game != "Chess"
    assert hash(game) == hash("Chess")

    plain = Game("Go")
    assert plain.start is None
    assert plain.end is None
    assert plain.to_dict()["timestamps"] == {}


def test_streaming() -> None:
    stream = Streaming(
        name="Twitch",
        url="https://twitch.tv/me",
        details="Playing chess",
        assets={"large_image": "twitch:me"},
    )
    assert stream.type is ActivityType.streaming
    assert stream.platform == "Twitch"
    assert stream.name == "Playing chess"
    assert str(stream) == "Playing chess"
    assert repr(stream) == "<Streaming name='Playing chess'>"
    assert stream.twitch_name == "me"
    assert stream.to_dict() == {
        "type": 1,
        "name": "Playing chess",
        "url": "https://twitch.tv/me",
        "assets": {"large_image": "twitch:me"},
        "details": "Playing chess",
    }
    same = Streaming(name="Twitch", url="https://twitch.tv/me", details="Playing chess")
    assert stream == same
    assert stream != Streaming(
        name="Twitch", url="https://twitch.tv/other", details="Playing chess"
    )
    assert stream != Game("Playing chess")
    assert hash(stream) == hash("Playing chess")

    assert Streaming(name="x", url="u").twitch_name is None
    assert (
        Streaming(name="x", url="u", assets={"large_image": "yt:me"}).twitch_name
        is None
    )


def spotify(**changes: Any) -> Spotify:
    data = {
        "state": "Artist A; Artist B",
        "details": "Song",
        "timestamps": {"start": START, "end": END},
        "assets": {"large_image": "spotify:cover", "large_text": "Album"},
        "party": {"id": "party"},
        "sync_id": "track",
        "session_id": "session",
        "created_at": START,
    }
    return Spotify(**{**data, **changes})


def test_spotify() -> None:
    track = spotify()
    assert track.type is ActivityType.listening
    assert track.name == "Spotify"
    assert str(track) == "Spotify"
    assert (
        repr(track)
        == "<Spotify title='Song' artist='Artist A; Artist B' track_id='track'>"
    )
    assert track.title == "Song"
    assert track.artists == ["Artist A", "Artist B"]
    assert track.artist == "Artist A; Artist B"
    assert track.album == "Album"
    assert track.album_cover_url == "https://i.scdn.co/image/cover"
    assert track.track_id == "track"
    assert track.track_url == "https://open.spotify.com/track/track"
    assert track.start == moment(START)
    assert track.end == moment(END)
    assert track.duration == dt.timedelta(milliseconds=215_000)
    assert track.party_id == "party"
    assert track.created_at == moment(START)
    assert track.to_dict()["flags"] == 48
    assert track.to_dict()["sync_id"] == "track"
    assert track == spotify()
    assert track != spotify(session_id="other")
    assert track != "Spotify"
    assert hash(track) == hash("session")

    bare = Spotify(sync_id="t", session_id="s")
    assert bare.album == ""
    assert bare.album_cover_url == ""
    assert bare.party_id == ""
    assert bare.created_at is None
    assert (
        Spotify(
            sync_id="t", session_id="s", assets={"large_image": "mp:foo"}
        ).album_cover_url
        == ""
    )


def test_custom_activity() -> None:
    status = CustomActivity("Busy", emoji="\N{FIRE}")
    assert status.type is ActivityType.custom
    assert status.emoji is not None
    assert status.emoji.name == "\N{FIRE}"
    assert str(status) == "\N{FIRE} Busy"
    assert repr(status).startswith("<CustomActivity name='Busy'")
    assert status.to_dict()["state"] == "Busy"
    assert status.to_dict()["name"] == "Custom Status"
    assert status.to_dict()["emoji"]["name"] == "\N{FIRE}"
    assert status == CustomActivity("Busy", emoji="\N{FIRE}")
    assert status != CustomActivity("Busy")
    assert status != "Busy"
    assert hash(status) == hash(("Busy", str(status.emoji)))

    assert str(CustomActivity("Busy")) == "Busy"
    assert str(CustomActivity(None, emoji="\N{FIRE}")) == "\N{FIRE}"
    assert CustomActivity("Custom Status", state="real").name == "real"
    different = CustomActivity("Name", state="State")
    assert different.to_dict() == {"type": 4, "name": "Name"}


def test_custom_activity_emoji_forms() -> None:
    partial = discord.PartialEmoji(name="x", id=5)
    assert CustomActivity("a", emoji=partial).emoji is partial
    from_dict = CustomActivity("a", emoji={"name": "x", "id": "5"})
    assert from_dict.emoji is not None
    assert from_dict.emoji.id == 5
    assert CustomActivity("a").emoji is None
    with pytest.raises(TypeError, match="Expected str, PartialEmoji, or None"):
        CustomActivity("a", emoji=5)  # type: ignore[arg-type]


def test_create_activity_picks_the_right_class() -> None:
    assert create_activity(None) is None
    assert create_activity({}) is None  # type: ignore[arg-type]
    assert isinstance(create_activity({"type": 0, "name": "g"}), Game)  # type: ignore[arg-type]
    assert isinstance(
        create_activity({"type": 0, "name": "g", "application_id": "1"}),  # type: ignore[arg-type]
        Activity,
    )
    assert isinstance(
        create_activity({"type": 0, "name": "g", "session_id": "s"}),  # type: ignore[arg-type]
        Activity,
    )
    custom = create_activity({"type": 4, "name": "Custom Status", "state": "hi"})  # type: ignore[arg-type]
    assert isinstance(custom, CustomActivity)
    assert custom.name == "hi"
    nameless = create_activity({"type": 4, "state": "hi"})  # type: ignore[arg-type]
    assert type(nameless) is Activity
    assert isinstance(
        create_activity({"type": 1, "name": "s", "url": "https://twitch.tv/x"}),  # type: ignore[arg-type]
        Streaming,
    )
    assert type(create_activity({"type": 1, "name": "s"})) is Activity  # type: ignore[arg-type]
    assert isinstance(
        create_activity(  # type: ignore[arg-type]
            {"type": 2, "name": "Spotify", "sync_id": "t", "session_id": "s"}
        ),
        Spotify,
    )
    assert type(create_activity({"type": 2, "name": "Other"})) is Activity  # type: ignore[arg-type]
    assert type(create_activity({"type": 3, "name": "Video"})) is Activity  # type: ignore[arg-type]
