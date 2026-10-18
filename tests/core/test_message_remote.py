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

import io
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import types as t
from discord.errors import InvalidArgument
from discord.message import (
    Message,
    PartialMessage,
)
from tests.core.rig import Case, Rig, check_type, execute

if TYPE_CHECKING:
    from tests.models.context import World

MEMBER = discord.Object(id=77)


def message(r: Rig) -> Message:
    if not hasattr(r, "message"):
        r.message = r.make_message()  # type: ignore[attr-defined]
    return r.message  # type: ignore[attr-defined,no-any-return]


def partial(r: Rig) -> PartialMessage:
    return PartialMessage(channel=r.channel, id=321)


def edit_case(case_id: str, kwargs: Any, **expected: Any) -> Case:
    return Case(
        case_id,
        message,
        "edit",
        "edit_message",
        lambda r: r.message_payload(5000),
        kwargs=kwargs if callable(kwargs) else (lambda r: kwargs),
        called_with=lambda r: ((r.channel.id, 5000), expected),
        check=check_type(Message),
        setup=lambda r: setattr(r.state, "allowed_mentions", None),
    )


def edit_error(case_id: str, kwargs: Any, text: str) -> Case:
    return Case(
        case_id,
        message,
        "edit",
        "edit_message",
        kwargs=kwargs if callable(kwargs) else (lambda r: kwargs),
        raises=(InvalidArgument, text),
    )


CASES = [
    edit_case("edit_nothing", {}),
    edit_case(
        "edit_content_and_embed",
        lambda r: {"content": 5, "embed": discord.Embed(title="x")},
        content="5",
        embeds=[discord.Embed(title="x").to_dict()],
    ),
    edit_case("edit_remove_content", {"content": None}, content=None),
    edit_case("edit_remove_embed", {"embed": None}, embeds=[]),
    edit_case(
        "edit_embeds",
        lambda r: {"embeds": [discord.Embed(title="a"), discord.Embed(title="b")]},
        embeds=[discord.Embed(title="a").to_dict(), discord.Embed(title="b").to_dict()],
    ),
    edit_error(
        "edit_embed_and_embeds",
        lambda r: {"embed": discord.Embed(), "embeds": []},
        "both embed and embeds",
    ),
    edit_error(
        "edit_file_and_files",
        lambda r: {"file": 1, "files": []},
        "both file and files",
    ),
    edit_error("edit_bad_file", {"file": 1}, "must be of type File"),
    edit_error(
        "edit_too_many_files",
        lambda r: {"files": [discord.File(io.BytesIO(b"x"), "a.txt")] * 11},
        "up to 10",
    ),
    edit_error("edit_bad_files", {"files": [1]}, "list of File"),
    edit_case(
        "edit_allowed_mentions",
        lambda r: {"allowed_mentions": discord.AllowedMentions.none()},
        allowed_mentions=discord.AllowedMentions.none().to_dict(),
    ),
    edit_case(
        "edit_suppress_embeds",
        {"suppress_embeds": True},
        flags=discord.MessageFlags(suppress_embeds=True).value,
    ),
    Case(
        "edit_allowed_mentions_merged_with_the_default",
        message,
        "edit",
        "edit_message",
        lambda r: r.message_payload(5000),
        kwargs=lambda r: {"allowed_mentions": discord.AllowedMentions(users=False)},
        setup=lambda r: setattr(
            r.state, "allowed_mentions", discord.AllowedMentions(everyone=False)
        ),
        kwargs_include=lambda r: {
            "allowed_mentions": discord.AllowedMentions(
                everyone=False, users=False
            ).to_dict()
        },
    ),
    Case(
        "edit_keeps_default_mentions_for_own_messages",
        message,
        "edit",
        "edit_message",
        lambda r: r.message_payload(5000),
        setup=lambda r: (
            setattr(
                r.state, "allowed_mentions", discord.AllowedMentions(everyone=False)
            ),
            setattr(r.state.user, "id", r.make_message().author.id),
        ),
        kwargs_include=lambda r: {
            "allowed_mentions": discord.AllowedMentions(everyone=False).to_dict()
        },
    ),
    Case(
        "edit_with_a_file_keeps_attachments",
        message,
        "edit",
        "edit_files",
        lambda r: r.message_payload(5000),
        kwargs=lambda r: {"file": discord.File(io.BytesIO(b"x"), "a.txt")},
        check=lambda r, res: _files(r, res),  # noqa: PLW0108
    ),
    Case(
        "edit_view_removed",
        message,
        "edit",
        "edit_message",
        lambda r: r.message_payload(5000),
        kwargs=lambda r: {"view": None},
        kwargs_include=lambda r: {"components": []},
    ),
    Case(
        "edit_deprecated_suppress",
        message,
        "edit",
        "edit_message",
        lambda r: r.message_payload(5000),
        kwargs=lambda r: {"suppress": True},
        warns=(DeprecationWarning, "suppress"),
        kwargs_include=lambda r: {
            "flags": discord.MessageFlags(suppress_embeds=True).value
        },
    ),
    Case(
        "publish",
        message,
        "publish",
        "publish_message",
        called_with=lambda r: ((r.channel.id, 5000), {}),
    ),
    Case(
        "pin",
        message,
        "pin",
        "pin_message",
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.channel.id, 5000), {"reason": "r"}),
        check=lambda r, res: _pinned(r, True),
    ),
    Case(
        "unpin",
        message,
        "unpin",
        "unpin_message",
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.channel.id, 5000), {"reason": "r"}),
        check=lambda r, res: _pinned(r, False),
    ),
    Case(
        "add_reaction",
        message,
        "add_reaction",
        "add_reaction",
        args=lambda r: ("\N{THUMBS UP SIGN}",),
        called_with=lambda r: ((r.channel.id, 5000, "\N{THUMBS UP SIGN}"), {}),
    ),
    Case(
        "remove_own_reaction",
        message,
        "remove_reaction",
        "remove_own_reaction",
        args=lambda r: ("<:a:1>", r.state.user),
        called_with=lambda r: ((r.channel.id, 5000, ":a:1"), {}),
    ),
    Case(
        "remove_reaction_of_a_member",
        message,
        "remove_reaction",
        "remove_reaction",
        args=lambda r: ("x", MEMBER),
        called_with=lambda r: ((r.channel.id, 5000, "x", 77), {}),
    ),
    Case(
        "clear_reaction",
        message,
        "clear_reaction",
        "clear_single_reaction",
        args=lambda r: ("x",),
        called_with=lambda r: ((r.channel.id, 5000, "x"), {}),
    ),
    Case(
        "clear_reactions",
        message,
        "clear_reactions",
        "clear_reactions",
        called_with=lambda r: ((r.channel.id, 5000), {}),
    ),
    Case(
        "end_poll",
        message,
        "end_poll",
        "expire_poll",
        lambda r: r.message_payload(5000),
        called_with=lambda r: ((r.channel.id, 5000), {}),
        check=check_type(Message),
    ),
    Case(
        "delete",
        message,
        "delete",
        "delete_message",
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.channel.id, 5000), {"reason": "r"}),
    ),
    Case(
        "create_thread",
        message,
        "create_thread",
        "start_thread_with_message",
        lambda r: r.payload(
            t.threads.Thread, guild_id=str(r.guild.id), parent_id=str(r.channel.id)
        ),
        kwargs=lambda r: {"name": "talk", "slowmode_delay": 4},
        called_with=lambda r: (
            (r.channel.id, 5000),
            {
                "name": "talk",
                "auto_archive_duration": r.channel.default_auto_archive_duration,
                "rate_limit_per_user": 4,
            },
        ),
        check=check_type(discord.Thread),
    ),
    Case(
        "partial_fetch",
        partial,
        "fetch",
        "get_message",
        lambda r: r.message_payload(321),
        called_with=lambda r: ((r.channel.id, 321), {}),
        check=check_type(Message),
    ),
    Case(
        "partial_end_poll",
        partial,
        "end_poll",
        "expire_poll",
        lambda r: r.message_payload(321),
        called_with=lambda r: ((r.channel.id, 321), {}),
        check=check_type(Message),
    ),
    Case(
        "partial_edit",
        partial,
        "edit",
        "edit_message",
        lambda r: r.message_payload(321),
        kwargs=lambda r: {
            "content": 1,
            "embed": discord.Embed(title="x"),
            "suppress": True,
            "allowed_mentions": discord.AllowedMentions.none(),
            "view": None,
        },
        setup=lambda r: setattr(r.state, "allowed_mentions", None),
        kwargs_include=lambda r: {
            "content": "1",
            "embeds": [discord.Embed(title="x").to_dict()],
            "components": [],
            "allowed_mentions": discord.AllowedMentions.none().to_dict(),
            "flags": discord.MessageFlags(suppress_embeds=True).value,
        },
        check=check_type(Message),
    ),
    Case(
        "partial_edit_embeds_and_default_mentions",
        partial,
        "edit",
        "edit_message",
        lambda r: r.message_payload(321),
        kwargs=lambda r: {"embeds": [discord.Embed(title="x")]},
        setup=lambda r: setattr(
            r.state, "allowed_mentions", discord.AllowedMentions(everyone=False)
        ),
        kwargs_include=lambda r: {
            "allowed_mentions": discord.AllowedMentions(everyone=False).to_dict()
        },
    ),
    Case(
        "partial_edit_both_embeds",
        partial,
        "edit",
        "edit_message",
        kwargs=lambda r: {"embed": discord.Embed(), "embeds": []},
        raises=(InvalidArgument, "Cannot pass both embed and embeds"),
    ),
    Case(
        "partial_edit_merges_mentions",
        partial,
        "edit",
        "edit_message",
        lambda r: r.message_payload(321),
        kwargs=lambda r: {"allowed_mentions": discord.AllowedMentions(users=False)},
        setup=lambda r: setattr(
            r.state, "allowed_mentions", discord.AllowedMentions(everyone=False)
        ),
        kwargs_include=lambda r: {
            "allowed_mentions": discord.AllowedMentions(
                everyone=False, users=False
            ).to_dict()
        },
    ),
]


def _files(r: Rig, result: Any) -> None:
    assert isinstance(result, Message)
    kwargs = r.http.edit_files.call_args.kwargs
    assert [f.filename for f in kwargs["files"]] == ["a.txt"]
    assert kwargs["attachments"] == [a.to_dict() for a in message(r).attachments]


def _pinned(r: Rig, expected: bool) -> None:
    assert message(r).pinned is expected


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_message_remote_calls(world: World, case: Case) -> None:
    execute(Rig(world), case)
