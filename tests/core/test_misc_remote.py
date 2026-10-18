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
import io
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import types as t
from discord.errors import InvalidArgument, InvalidData, ValidationError
from discord.utils import MISSING
from tests.core.rig import (
    PNG,
    Case,
    Rig,
    check_type,
    execute,
    one,
)

if TYPE_CHECKING:
    from tests.models.context import World

IMG = "data:image/png;base64,iVBORw0KGgo="
ROLE = discord.Object(id=5252)


def cached(rig: Rig, name: str, build: Any) -> Any:
    if name not in rig.__dict__:
        rig.__dict__[name] = build(rig)
    return rig.__dict__[name]


def event(r: Rig) -> Any:
    return cached(
        r,
        "_event",
        lambda rig: discord.ScheduledEvent(
            state=rig.state,
            guild=rig.guild,
            creator=None,
            data=rig.payload(
                t.scheduled_events.ScheduledEvent,
                id="7100",
                guild_id=str(rig.guild.id),
                creator_id=None,
                entity_type=2,
                scheduled_end_time=None,
            ),
        ),
    )


def external_event(r: Rig) -> Any:
    return cached(
        r,
        "_external",
        lambda rig: discord.ScheduledEvent(
            state=rig.state,
            guild=rig.guild,
            creator=None,
            data=rig.payload(
                t.scheduled_events.ScheduledEvent,
                id="7101",
                guild_id=str(rig.guild.id),
                creator_id=None,
                entity_type=3,
                scheduled_end_time=None,
                entity_metadata={"location": "park"},
                channel_id=None,
            ),
        ),
    )


def event_payload(r: Rig) -> Any:
    return r.payload(
        t.scheduled_events.ScheduledEvent,
        id="7100",
        guild_id=str(r.guild.id),
        creator_id=None,
    )


def rule(r: Rig) -> Any:
    return cached(
        r,
        "_rule",
        lambda rig: discord.AutoModRule(
            state=rig.state,
            data=rig.payload(
                t.automod.AutoModRule, id="7200", guild_id=str(rig.guild.id)
            ),
        ),
    )


def guild_emoji(r: Rig) -> Any:
    return cached(
        r,
        "_emoji",
        lambda rig: discord.GuildEmoji(
            guild=rig.guild, state=rig.state, data=rig.payload(t.emoji.Emoji, id="7300")
        ),
    )


def stage(r: Rig) -> Any:
    return cached(
        r,
        "_stage",
        lambda rig: discord.StageInstance(
            guild=rig.guild,
            state=rig.state,
            data=rig.payload(
                t.channel.StageInstance,
                id="7400",
                guild_id=str(rig.guild.id),
                channel_id="7401",
            ),
        ),
    )


def sound(r: Rig) -> Any:
    return cached(
        r,
        "_sound",
        lambda rig: discord.SoundboardSound(
            state=rig.state,
            http=rig.http,
            data=rig.payload(
                t.soundboard.SoundboardSound,
                sound_id="7500",
                guild_id=str(rig.guild.id),
            ),
        ),
    )


def template(r: Rig) -> Any:
    return cached(
        r,
        "_template",
        lambda rig: discord.Template(
            state=rig.state,
            data=rig.payload(t.template.Template, code="abc", source_guild_id="9"),
        ),
    )


def guild_sticker(r: Rig) -> Any:
    return cached(
        r,
        "_sticker",
        lambda rig: discord.GuildSticker(
            state=rig.state,
            data=rig.payload(
                t.sticker.GuildSticker, id="7600", guild_id=str(rig.guild.id)
            ),
        ),
    )


def integration(r: Rig, kind: str) -> Any:
    return cached(
        r,
        f"_integration_{kind}",
        lambda rig: (
            discord.StreamIntegration if kind == "stream" else discord.BotIntegration
        )(
            guild=rig.guild,
            data=rig.payload(
                t.integration.StreamIntegration
                if kind == "stream"
                else t.integration.BotIntegration,
                id="7700",
                type="twitch" if kind == "stream" else "discord",
            ),
        ),
    )


def invite(r: Rig) -> Any:
    return cached(
        r,
        "_invite",
        lambda rig: discord.Invite.from_incomplete(
            state=rig.state,
            data=rig.payload(
                t.invite.Invite,
                code="pycord",
                channel={"id": str(rig.channel.id), "type": 0, "name": "x"},
            ),
        ),
    )


def welcome(r: Rig) -> Any:
    return cached(
        r,
        "_welcome",
        lambda rig: discord.WelcomeScreen(
            data=rig.payload(t.welcome_screen.WelcomeScreen), guild=rig.guild
        ),
    )


def onboarding(r: Rig) -> Any:
    return cached(
        r,
        "_onboarding",
        lambda rig: discord.Onboarding(
            data=rig.payload(t.onboarding.Onboarding), guild=rig.guild
        ),
    )


def sent(r: Rig, route: str) -> dict[str, Any]:
    return getattr(r.http, route).call_args.kwargs


CASES = [
    Case(
        "event_edit_everything",
        event,
        "edit",
        "edit_scheduled_event",
        event_payload,
        kwargs=lambda r: {
            "reason": "r",
            "name": "party",
            "description": None,
            "status": discord.ScheduledEventStatus.active,
            "image": PNG,
            "start_time": dt.datetime(2030, 1, 1, tzinfo=dt.timezone.utc),
            "end_time": dt.datetime(2030, 1, 2, tzinfo=dt.timezone.utc),
            "location": "somewhere",
            "recurrence_rule": None,
        },
        kwargs_include=lambda r: {
            "name": "party",
            "description": None,
            "status": 2,
            "image": IMG,
            "scheduled_start_time": "2030-01-01T00:00:00+00:00",
            "scheduled_end_time": "2030-01-02T00:00:00+00:00",
            "entity_type": 3,
            "entity_metadata": {"location": "somewhere"},
            "recurrence_rule": None,
            "privacy_level": 2,
            "reason": "r",
        },
        check=check_type(discord.ScheduledEvent),
    ),
    Case(
        "event_edit_cover_is_deprecated",
        event,
        "edit",
        "edit_scheduled_event",
        event_payload,
        kwargs=lambda r: {"cover": PNG},
        warns=(DeprecationWarning, "cover"),
        kwargs_include=lambda r: {"image": IMG},
    ),
    Case(
        "event_edit_cover_and_image",
        event,
        "edit",
        "edit_scheduled_event",
        kwargs=lambda r: {"cover": PNG, "image": PNG},
        warns=(DeprecationWarning, "cover"),
        raises=(InvalidArgument, "both `image` and `cover`"),
    ),
    Case(
        "event_edit_nothing_still_sends_the_privacy_level",
        event,
        "edit",
        "edit_scheduled_event",
        event_payload,
        kwargs_include=lambda r: {"privacy_level": 2},
    ),
    Case(
        "external_event_edit_needs_an_end_time",
        external_event,
        "edit",
        "edit_scheduled_event",
        kwargs=lambda r: {"name": "x"},
        raises=(ValidationError, "end_time"),
    ),
    Case(
        "external_event_edit_with_an_end_time",
        external_event,
        "edit",
        "edit_scheduled_event",
        event_payload,
        kwargs=lambda r: {"end_time": dt.datetime(2030, 1, 2, tzinfo=dt.timezone.utc)},
        kwargs_include=lambda r: {"scheduled_end_time": "2030-01-02T00:00:00+00:00"},
    ),
    Case(
        "event_delete",
        event,
        "delete",
        "delete_scheduled_event",
        called_with=lambda r: ((r.guild.id, 7100), {}),
    ),
    Case(
        "rule_delete",
        rule,
        "delete",
        "delete_auto_moderation_rule",
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.guild.id, 7200), {"reason": "r"}),
    ),
    Case(
        "rule_edit_everything",
        rule,
        "edit",
        "edit_auto_moderation_rule",
        one(t.automod.AutoModRule),
        kwargs=lambda r: {
            "name": "n",
            "event_type": discord.AutoModEventType.message_send,
            "trigger_metadata": discord.AutoModTriggerMetadata(keyword_filter=["x"]),
            "actions": [
                discord.AutoModAction(
                    discord.AutoModActionType.block_message,
                    discord.AutoModActionMetadata(),
                )
            ],
            "enabled": True,
            "exempt_roles": [ROLE],
            "exempt_channels": [discord.Object(id=3)],
            "reason": "r",
        },
        check=lambda r, res: _rule_edit(r, res),  # noqa: PLW0108
    ),
    Case(
        "rule_edit_nothing",
        rule,
        "edit",
        check=lambda r, res: (
            res is None and r.http.edit_auto_moderation_rule.assert_not_called()
        ),
    ),
    Case(
        "invite_delete",
        invite,
        "delete",
        "delete_invite",
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: (("pycord",), {"reason": "r"}),
    ),
    Case(
        "invite_edit_target_users",
        invite,
        "edit_target_users",
        "update_invite_target_users",
        args=lambda r: (discord.File(io.BytesIO(b"x"), "u.csv"),),
        check=lambda r, res: _target_file(r),
    ),
    Case(
        "invite_target_users_job_status",
        invite,
        "fetch_target_users_job_status",
        "get_invite_target_users_job_status",
        lambda r: {
            "status": 1,
            "total_users": 3,
            "processed_users": 2,
            "created_at": "2024-01-01T00:00:00+00:00",
            "completed_at": None,
            "error_message": None,
        },
        called_with=lambda r: (("pycord",), {}),
        check=check_type(discord.InviteTargetUsersJobStatus),
    ),
    Case(
        "emoji_delete",
        guild_emoji,
        "delete",
        "delete_custom_emoji",
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.guild.id, 7300), {"reason": "r"}),
    ),
    Case(
        "emoji_edit",
        guild_emoji,
        "edit",
        "edit_custom_emoji",
        lambda r: r.payload(t.emoji.Emoji, id="7300"),
        kwargs=lambda r: {"name": "new", "roles": [ROLE], "reason": "r"},
        called_with=lambda r: (
            (r.guild.id, 7300),
            {"payload": {"name": "new", "roles": [5252]}, "reason": "r"},
        ),
        check=check_type(discord.GuildEmoji),
    ),
    Case(
        "welcome_screen_edit",
        welcome,
        "edit",
        "edit_welcome_screen",
        one(t.welcome_screen.WelcomeScreen),
        kwargs=lambda r: {
            "description": "hello",
            "welcome_channels": [
                discord.WelcomeScreenChannel(r.channel, "start", "\N{WAVING HAND SIGN}")
            ],
            "reason": "r",
        },
        check=lambda r, res: _welcome_edit(r, res),  # noqa: PLW0108
    ),
    Case(
        "welcome_screen_edit_bad_channel",
        welcome,
        "edit",
        "edit_welcome_screen",
        kwargs=lambda r: {"welcome_channels": [r.channel]},
        raises=(TypeError, "WelcomeScreenChannel"),
    ),
    Case(
        "stage_instance_edit",
        stage,
        "edit",
        "edit_stage_instance",
        kwargs=lambda r: {
            "topic": "new topic",
            "privacy_level": discord.StagePrivacyLevel.guild_only,
            "reason": "r",
        },
        called_with=lambda r: (
            (7401,),
            {"topic": "new topic", "privacy_level": 2, "reason": "r"},
        ),
    ),
    Case(
        "stage_instance_edit_nothing",
        stage,
        "edit",
        check=lambda r, res: r.http.edit_stage_instance.assert_not_called(),
    ),
    Case(
        "stage_instance_edit_bad_privacy",
        stage,
        "edit",
        "edit_stage_instance",
        kwargs=lambda r: {"privacy_level": 2},
        raises=(InvalidArgument, "PrivacyLevel"),
    ),
    Case(
        "stage_instance_delete",
        stage,
        "delete",
        "delete_stage_instance",
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((7401,), {"reason": "r"}),
    ),
    Case(
        "integration_delete",
        lambda r: integration(r, "bot"),
        "delete",
        "delete_integration",
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.guild.id, 7700), {"reason": "r"}),
    ),
    Case(
        "stream_integration_edit",
        lambda r: integration(r, "stream"),
        "edit",
        "edit_integration",
        kwargs=lambda r: {
            "expire_behaviour": discord.ExpireBehaviour.kick,
            "expire_grace_period": 7,
            "enable_emoticons": True,
        },
        called_with=lambda r: (
            (r.guild.id, 7700),
            {"expire_behavior": 1, "expire_grace_period": 7, "enable_emoticons": True},
        ),
    ),
    Case(
        "stream_integration_edit_bad_behaviour",
        lambda r: integration(r, "stream"),
        "edit",
        "edit_integration",
        kwargs=lambda r: {"expire_behaviour": 1},
        raises=(InvalidArgument, "ExpireBehaviour"),
    ),
    Case(
        "sound_edit",
        sound,
        "edit",
        "edit_guild_sound",
        one(t.soundboard.SoundboardSound),
        kwargs=lambda r: {
            "name": "n",
            "volume": 0.5,
            "emoji": "\N{FIRE}",
            "reason": "r",
        },
        called_with=lambda r: (
            (r.guild.id, 7500),
            {
                "reason": "r",
                "name": "n",
                "volume": 0.5,
                "emoji_id": None,
                "emoji_name": "\N{FIRE}",
            },
        ),
        check=check_type(discord.SoundboardSound),
    ),
    Case(
        "sound_edit_custom_emoji",
        sound,
        "edit",
        "edit_guild_sound",
        one(t.soundboard.SoundboardSound),
        kwargs=lambda r: {"emoji": discord.PartialEmoji(name="x", id=5)},
        kwargs_include=lambda r: {"emoji_id": 5, "emoji_name": None},
    ),
    Case(
        "template_sync",
        template,
        "sync",
        "sync_template",
        one(t.template.Template),
        called_with=lambda r: ((9, "abc"), {}),
        check=check_type(discord.Template),
    ),
    Case(
        "template_edit",
        template,
        "edit",
        "edit_template",
        one(t.template.Template),
        kwargs=lambda r: {"name": "n", "description": None},
        called_with=lambda r: ((9, "abc", {"name": "n", "description": None}), {}),
        check=check_type(discord.Template),
    ),
    Case(
        "template_delete",
        template,
        "delete",
        "delete_template",
        called_with=lambda r: ((9, "abc"), {}),
    ),
    Case(
        "guild_sticker_edit",
        guild_sticker,
        "edit",
        "modify_guild_sticker",
        one(t.sticker.GuildSticker, id="7600"),
        kwargs=lambda r: {
            "name": "n",
            "description": None,
            "emoji": "\N{WAVING HAND SIGN}",
            "reason": "r",
        },
        called_with=lambda r: (
            (
                r.guild.id,
                7600,
                {"name": "n", "description": None, "tags": "WAVING_HAND_SIGN"},
                "r",
            ),
            {},
        ),
        check=check_type(discord.GuildSticker),
    ),
    Case(
        "guild_sticker_edit_plain_tag",
        guild_sticker,
        "edit",
        "modify_guild_sticker",
        one(t.sticker.GuildSticker, id="7600"),
        kwargs=lambda r: {"emoji": "smile"},
        check=lambda r, res: (
            r.http.modify_guild_sticker.call_args.args[2] == {"tags": "smile"}
            or pytest.fail(r.http.modify_guild_sticker.call_args)
        ),
    ),
    Case(
        "guild_sticker_delete",
        guild_sticker,
        "delete",
        "delete_guild_sticker",
        kwargs=lambda r: {"reason": "r"},
        called_with=lambda r: ((r.guild.id, 7600, "r"), {}),
    ),
    Case(
        "onboarding_edit",
        onboarding,
        "edit",
        "edit_onboarding",
        one(t.onboarding.Onboarding),
        kwargs=lambda r: {
            "prompts": [],
            "default_channels": [r.channel],
            "enabled": False,
            "mode": discord.OnboardingMode.advanced,
            "reason": "r",
        },
        called_with=lambda r: (
            (
                r.guild.id,
                {
                    "prompts": [],
                    "default_channel_ids": [r.channel.id],
                    "enabled": False,
                    "mode": 1,
                },
            ),
            {"reason": "r"},
        ),
        check=check_type(discord.Onboarding),
    ),
]


def _rule_edit(r: Rig, result: Any) -> None:
    assert isinstance(result, discord.AutoModRule)
    (_, _, payload) = r.http.edit_auto_moderation_rule.call_args.args
    assert payload["name"] == "n"
    assert payload["event_type"] == 1
    assert payload["enabled"] is True
    assert payload["exempt_roles"] == [5252]
    assert payload["exempt_channels"] == [3]
    assert payload["trigger_metadata"]["keyword_filter"] == ["x"]
    assert payload["actions"][0]["type"] == 1


def _target_file(r: Rig) -> None:
    args, kwargs = r.http.update_invite_target_users.call_args
    assert args == ("pycord",)
    assert kwargs["target_users_file"].filename == "u.csv"


def _welcome_edit(r: Rig, result: Any) -> None:
    assert result is welcome(r)
    args, kwargs = r.http.edit_welcome_screen.call_args
    assert args[0] == r.guild.id
    assert args[1]["description"] == "hello"
    assert args[1]["welcome_channels"][0]["description"] == "start"
    assert kwargs == {"reason": "r"}


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
@pytest.mark.filterwarnings("ignore:cover:DeprecationWarning")
def test_misc_remote_calls(world: World, case: Case) -> None:
    execute(Rig(world), case)


def prompt(
    title: str = "Pick", prompt_id: int | None = None
) -> discord.OnboardingPrompt:
    return discord.OnboardingPrompt(
        discord.PromptType.multiple_choice,
        title,
        [discord.PromptOption("opt", description="d")],
        single_select=True,
        required=False,
        in_onboarding=True,
        id=prompt_id,
    )


def test_onboarding_prompt_management(world: World) -> None:
    rig = Rig(world)
    screen = onboarding(rig)
    updated = rig.payload(t.onboarding.Onboarding)
    rig.respond("edit_onboarding", updated)

    existing = screen.prompts[0] if screen.prompts else None
    new = prompt("New", 9001)
    assert rig.run(screen.append_prompt(new, reason="r")) is screen
    sent_prompts = rig.http.edit_onboarding.call_args.args[1]["prompts"]
    assert sent_prompts[-1]["title"] == "New"
    assert rig.http.edit_onboarding.call_args.kwargs == {"reason": "r"}

    rig.run(
        screen.add_prompt(
            discord.PromptType.dropdown,
            "Added",
            [discord.PromptOption("x")],
            single_select=False,
            required=True,
            in_onboarding=False,
        )
    )
    assert rig.http.edit_onboarding.call_args.args[1]["prompts"][-1]["title"] == "Added"

    screen.prompts = [prompt("Keep", 1), prompt("Drop", 2)]
    assert screen.get_prompt(2).title == "Drop"  # type: ignore[union-attr]
    assert screen.get_prompt(3) is None
    rig.run(screen.delete_prompt(2, reason="r"))
    sent_prompts = rig.http.edit_onboarding.call_args.args[1]["prompts"]
    assert [p["title"] for p in sent_prompts] == ["Keep"]
    screen.prompts = [prompt("Keep", 1)]
    with pytest.raises(ValueError, match="was not found"):
        rig.run(screen.delete_prompt(77))
    _ = existing


def test_prompt_option_setters(world: World) -> None:
    rig = Rig(world)
    option = discord.PromptOption("opt")
    option.roles = [ROLE]
    assert [r.id for r in option.roles] == [5252] or option.roles == [ROLE]
    option.emoji = "\N{FIRE}"
    assert option.emoji is not None
    _ = rig


def test_widget_fetch_invite(world: World) -> None:
    rig = Rig(world)
    widget = discord.Widget(state=rig.state, data=rig.payload(t.widget.Widget))
    rig.respond(
        "get_invite",
        rig.payload(
            t.invite.Invite,
            channel={"id": str(rig.channel.id), "type": 0, "name": "x"},
        ),
    )
    found = rig.run(widget.fetch_invite(with_counts=False))
    assert isinstance(found, discord.Invite)
    assert rig.http.get_invite.call_args.kwargs == {"with_counts": False}


def test_sticker_item_fetch_and_pack(world: World) -> None:
    rig = Rig(world)
    item = discord.StickerItem(
        state=rig.state,
        data=rig.payload(t.sticker.StickerItem, id="7800", format_type=1),
    )
    assert str(item) == item.name
    rig.respond(
        "get_sticker", rig.payload(t.sticker.StandardSticker, id="7800", type=1)
    )
    fetched = rig.run(item.fetch())
    assert isinstance(fetched, discord.StandardSticker)

    rig.respond(
        "list_premium_sticker_packs",
        {
            "sticker_packs": [
                rig.payload(t.sticker.StickerPack, id=str(fetched.pack_id))
            ]
        },
    )
    assert isinstance(rig.run(fetched.pack()), discord.StickerPack)
    rig.respond("list_premium_sticker_packs", {"sticker_packs": []})
    with pytest.raises(InvalidData, match="Could not find corresponding sticker pack"):
        rig.run(fetched.pack())
    assert str(fetched) == fetched.name


def test_invite_target_users_download(world: World, tmp_path: Any) -> None:
    rig = Rig(world)
    users = discord.invite.InviteTargetUsers(state=rig.state, invite_code="pycord")
    rig.respond("get_invite_target_users", b"user_ids\n5,x\n6,y\n")
    assert rig.run(users.read()) == b"user_ids\n5,x\n6,y\n"
    assert rig.run(users.as_user_ids()) == [5, 6]

    buffer = io.BytesIO()
    assert rig.run(users.save(buffer)) == 17
    assert buffer.tell() == 0
    buffer = io.BytesIO()
    rig.run(users.save(buffer, seek_begin=False))
    assert buffer.tell() == 17
    target = tmp_path / "users.csv"
    assert rig.run(users.save(target)) == 17
    assert target.read_bytes() == b"user_ids\n5,x\n6,y\n"
    _ = MISSING
