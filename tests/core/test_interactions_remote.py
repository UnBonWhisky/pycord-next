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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import discord
from discord import types as t
from discord.errors import ClientException, InteractionResponded, InvalidArgument
from discord.file import VoiceMessage
from discord.interactions import (
    AuthorizingIntegrationOwners,
    InteractionCallback,
    InteractionMessage,
)
from discord.webhook.async_ import async_context
from tests.commands.interaction_support import (
    MEMBER_ID,
    interaction_payload,
    make_interaction,
)
from tests.commands.test_interaction_responses import message_payload

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.models.context import World

CALLBACK = {"interaction": {"id": "1", "type": 2}, "resource": {"type": 4}}


class Adapter:
    def __init__(self, world: World) -> None:
        self.world = world
        self.create_interaction_response = AsyncMock(return_value=CALLBACK)
        self.get_original_interaction_response = AsyncMock(
            return_value=message_payload(world)
        )
        self.edit_original_interaction_response = AsyncMock(
            return_value=message_payload(world)
        )
        self.delete_original_interaction_response = AsyncMock(return_value=None)


@pytest.fixture
def adapter(world: World) -> Iterator[Adapter]:
    fake = Adapter(world)
    token = async_context.set(fake)  # type: ignore[arg-type]
    yield fake
    async_context.reset(token)


def command(world: World, **fields: Any) -> discord.Interaction:
    return make_interaction(world, **fields)


def component(world: World, **fields: Any) -> discord.Interaction:
    return make_interaction(
        world,
        type=3,
        data={"custom_id": "x", "component_type": 2},
        message=message_payload(world),
        **fields,
    )


def sent(adapter: Adapter) -> dict[str, Any]:
    return adapter.create_interaction_response.call_args.kwargs


def test_defer_an_application_command(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    world.run(interaction.response.defer(ephemeral=True))
    assert sent(adapter)["type"] == 5
    assert sent(adapter)["data"] == {"flags": 64}
    assert interaction.response.is_done()
    assert interaction.callback is not None
    with pytest.raises(InteractionResponded):
        world.run(interaction.response.defer())


def test_defer_a_component_interaction(world: World, adapter: Adapter) -> None:
    interaction = component(world)
    world.run(interaction.response.defer())
    assert sent(adapter)["type"] == 6
    assert sent(adapter)["data"] is None

    other = component(world)
    world.run(other.response.defer(invisible=False, ephemeral=True))
    assert sent(adapter)["type"] == 5
    assert sent(adapter)["data"] == {"flags": 64}


def test_defer_does_nothing_for_other_interaction_types(
    world: World, adapter: Adapter
) -> None:
    interaction = make_interaction(world, type=4, data={"name": "x", "type": 1})
    world.run(interaction.response.defer())
    adapter.create_interaction_response.assert_not_called()
    assert not interaction.response.is_done()


def test_pong(world: World, adapter: Adapter) -> None:
    interaction = make_interaction(world, type=1, data=None)
    world.run(interaction.response.pong())
    assert sent(adapter)["type"] == 1
    with pytest.raises(InteractionResponded):
        world.run(interaction.response.pong())

    other = command(world)
    world.run(other.response.pong())
    assert adapter.create_interaction_response.await_count == 1


def test_send_message_payload(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    world.state.allowed_mentions = None
    poll = discord.Poll("q?", answers=[discord.PollAnswer("a")])

    returned = world.run(
        interaction.response.send_message(
            5,
            embed=discord.Embed(title="e"),
            tts=True,
            ephemeral=True,
            silent=True,
            suppress_embeds=True,
            poll=poll,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    )

    assert returned is interaction
    payload = sent(adapter)["data"]
    assert payload["content"] == "5"
    assert payload["tts"] is True
    assert payload["embeds"] == [discord.Embed(title="e").to_dict()]
    assert payload["poll"] == poll.to_dict()
    assert payload["allowed_mentions"] == discord.AllowedMentions.none().to_dict()
    flags = discord.MessageFlags._from_value(payload["flags"])
    assert flags.ephemeral
    assert flags.suppress_notifications
    assert flags.suppress_embeds
    assert sent(adapter)["type"] == 4


def test_send_message_merges_default_mentions(world: World, adapter: Adapter) -> None:
    world.state.allowed_mentions = discord.AllowedMentions(everyone=False)
    interaction = command(world)
    world.run(
        interaction.response.send_message(
            "a", allowed_mentions=discord.AllowedMentions(users=False)
        )
    )
    assert sent(adapter)["data"]["allowed_mentions"] == (
        discord.AllowedMentions(everyone=False, users=False).to_dict()
    )
    other = command(world)
    world.run(other.response.send_message("a"))
    assert sent(adapter)["data"]["allowed_mentions"] == (
        discord.AllowedMentions(everyone=False).to_dict()
    )


def test_send_message_files(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    voice = VoiceMessage(io.BytesIO(b"ogg"), waveform="AA==", duration_secs=1.0)
    world.run(interaction.response.send_message(files=[voice]))
    flags = discord.MessageFlags._from_value(sent(adapter)["data"]["flags"])
    assert flags.is_voice_message
    assert sent(adapter)["files"] == [voice]

    other = command(world)
    single = discord.File(io.BytesIO(b"x"), "a.txt")
    world.run(other.response.send_message("a", file=single))
    assert sent(adapter)["files"] == [single]


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"embed": discord.Embed(), "embeds": []}, TypeError, "mix embed and embeds"),
        ({"embeds": [discord.Embed()] * 11}, ValueError, "maximum of 10"),
        ({"file": 1, "files": []}, InvalidArgument, "both file and files"),
        ({"file": 1}, InvalidArgument, "must be File"),
        ({"files": [1] * 11}, InvalidArgument, "up to 10"),
        ({"files": [1]}, InvalidArgument, "list of File"),
    ],
)
def test_send_message_validation(
    world: World,
    adapter: Adapter,
    kwargs: dict[str, Any],
    error: type[Exception],
    message: str,
) -> None:
    interaction = command(world)
    with pytest.raises(error, match=message):
        world.run(interaction.response.send_message("a", **kwargs))
    adapter.create_interaction_response.assert_not_called()
    assert not interaction.response.is_done()


def test_send_message_twice_raises(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    world.run(interaction.response.send_message("a"))
    with pytest.raises(InteractionResponded):
        world.run(interaction.response.send_message("b"))
    assert adapter.create_interaction_response.await_count == 1


@pytest.mark.usefixtures("adapter")
def test_send_message_delete_after(world: World) -> None:
    interaction = command(world)
    with patch.object(
        discord.Interaction, "delete_original_response", new=AsyncMock()
    ) as delete:
        world.run(interaction.response.send_message("a", delete_after=3))
    delete.assert_awaited_once_with(delay=3)


def test_response_message_in_callback_becomes_the_original_response(
    world: World, adapter: Adapter
) -> None:
    adapter.create_interaction_response.return_value = {
        "interaction": {
            "id": "1",
            "type": 2,
            "response_message_loading": True,
            "response_message_ephemeral": True,
        },
        "resource": {
            "type": 4,
            "message": message_payload(world),
            "activity_instance": {"id": "inst"},
        },
    }
    interaction = command(world)
    world.run(interaction.response.send_message("a"))
    assert isinstance(interaction._original_response, InteractionMessage)
    assert interaction.callback is not None
    assert interaction.callback.is_loading()
    assert interaction.callback.is_ephemeral()
    assert interaction.activity_instance is not None
    assert "InteractionCallback" in repr(interaction.callback)
    assert isinstance(interaction.callback, InteractionCallback)


def test_edit_message_on_a_component(world: World, adapter: Adapter) -> None:
    interaction = component(world)
    world.state.allowed_mentions = None

    world.run(
        interaction.response.edit_message(
            content=None,
            embed=discord.Embed(title="e"),
            attachments=[],
            suppress=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    )

    payload = sent(adapter)["data"]
    assert sent(adapter)["type"] == 7
    assert payload["content"] is None
    assert payload["embeds"] == [discord.Embed(title="e").to_dict()]
    assert payload["attachments"] == []
    assert discord.MessageFlags._from_value(payload["flags"]).suppress_embeds
    assert payload["allowed_mentions"] == discord.AllowedMentions.none().to_dict()
    with pytest.raises(InteractionResponded):
        world.run(interaction.response.edit_message(content="x"))


def test_edit_message_files_keep_attachments(world: World, adapter: Adapter) -> None:
    interaction = component(world)
    world.state.allowed_mentions = discord.AllowedMentions(everyone=False)
    file = discord.File(io.BytesIO(b"x"), "a.txt")

    world.run(
        interaction.response.edit_message(
            embeds=[], file=file, allowed_mentions=discord.AllowedMentions(users=False)
        )
    )

    payload = sent(adapter)["data"]
    assert payload["embeds"] == []
    assert payload["attachments"] == [
        a.to_dict()
        for a in interaction.message.attachments  # type: ignore[union-attr]
    ]
    assert sent(adapter)["files"] == [file]
    assert payload["allowed_mentions"] == (
        discord.AllowedMentions(everyone=False, users=False).to_dict()
    )

    other = component(world)
    world.run(other.response.edit_message(files=[file], view=None))
    assert sent(adapter)["data"]["components"] == []
    assert sent(adapter)["data"]["allowed_mentions"] == (
        discord.AllowedMentions(everyone=False).to_dict()
    )


@pytest.mark.usefixtures("adapter")
def test_edit_message_delete_after(world: World) -> None:
    interaction = component(world)
    with patch.object(
        discord.Interaction, "delete_original_response", new=AsyncMock()
    ) as delete:
        world.run(interaction.response.edit_message(content="x", delete_after=2))
    delete.assert_awaited_once_with(delay=2)


@pytest.mark.parametrize(
    ("kwargs", "error", "message"),
    [
        ({"embed": discord.Embed(), "embeds": []}, TypeError, "mix both"),
        ({"file": 1, "files": []}, InvalidArgument, "both file and files"),
        ({"file": 1}, InvalidArgument, "must be a File"),
        ({"files": [1] * 11}, InvalidArgument, "up to 10"),
        ({"files": [1]}, InvalidArgument, "list of File"),
    ],
)
def test_edit_message_validation(
    world: World,
    adapter: Adapter,
    kwargs: dict[str, Any],
    error: type[Exception],
    message: str,
) -> None:
    interaction = component(world)
    with pytest.raises(error, match=message):
        world.run(interaction.response.edit_message(**kwargs))
    adapter.create_interaction_response.assert_not_called()


def test_edit_message_ignores_other_interaction_types(
    world: World, adapter: Adapter
) -> None:
    interaction = command(world)
    assert world.run(interaction.response.edit_message(content="x")) is None
    adapter.create_interaction_response.assert_not_called()


def test_autocomplete_result(world: World, adapter: Adapter) -> None:
    interaction = make_interaction(
        world,
        type=4,
        data={"id": "1", "name": "cmd", "type": 1, "options": []},
    )
    world.run(
        interaction.response.send_autocomplete_result(
            choices=[discord.OptionChoice("a", 1)]
        )
    )
    assert sent(adapter)["type"] == 8
    assert sent(adapter)["data"] == {"choices": [{"name": "a", "value": 1}]}
    with pytest.raises(InteractionResponded):
        world.run(interaction.response.send_autocomplete_result(choices=[]))

    other = command(world)
    world.run(other.response.send_autocomplete_result(choices=[]))
    assert adapter.create_interaction_response.await_count == 1


def test_send_modal(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    modal = MagicMock()
    modal.to_dict.return_value = {"title": "t", "custom_id": "m", "components": []}
    with patch.object(world.state, "store_modal") as store:
        returned = world.run(interaction.response.send_modal(modal))
    assert returned is interaction
    assert sent(adapter)["type"] == 9
    assert sent(adapter)["data"]["title"] == "t"
    store.assert_called_once_with(modal, interaction.user.id)  # type: ignore[union-attr]
    with pytest.raises(InteractionResponded):
        world.run(interaction.response.send_modal(modal))


@pytest.mark.usefixtures("adapter")
def test_send_modal_needs_a_user(world: World) -> None:
    interaction = command(world)
    interaction.user = None
    modal = MagicMock()
    modal.to_dict.return_value = {}
    with pytest.raises(ClientException, match="no user"):
        world.run(interaction.response.send_modal(modal))


def test_premium_required(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    with pytest.warns(DeprecationWarning, match="premium_required"):
        assert world.run(interaction.response.premium_required()) is interaction
    assert sent(adapter)["type"] == 10
    with (
        pytest.warns(DeprecationWarning, match="premium_required"),
        pytest.raises(InteractionResponded),
    ):
        world.run(interaction.response.premium_required())


def test_locked_response_closes_the_coroutine_when_already_done(
    world: World,
) -> None:
    interaction = command(world)
    interaction.response._responded = True

    async def never() -> None:
        raise AssertionError

    coro = never()
    with pytest.raises(InteractionResponded):
        world.run(interaction.response._locked_response(coro))
    assert coro.cr_frame is None


def test_original_response_and_aliases(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    message = world.run(interaction.original_response())
    assert isinstance(message, InteractionMessage)
    with pytest.warns(DeprecationWarning, match="original_message"):
        assert world.run(interaction.original_message()) is message
    adapter.get_original_interaction_response.assert_awaited_once()

    other = command(world)
    other._original_response = None
    with (
        patch.object(type(other), "channel", None),
        pytest.raises(ClientException, match="Channel for message"),
    ):
        world.run(other.original_response())


def test_edit_original_response(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    world.state.allowed_mentions = None

    message = world.run(
        interaction.edit_original_response(
            content="x", embeds=[discord.Embed(title="e")], suppress_embeds=True
        )
    )

    assert isinstance(message, InteractionMessage)
    kwargs = adapter.edit_original_interaction_response.call_args.kwargs
    assert kwargs["payload"]["content"] == "x"
    assert kwargs["payload"]["embeds"] == [discord.Embed(title="e").to_dict()]
    assert discord.MessageFlags._from_value(kwargs["payload"]["flags"]).suppress_embeds
    with pytest.warns(DeprecationWarning, match="edit_original_message"):
        world.run(interaction.edit_original_message(content="y"))
    assert adapter.edit_original_interaction_response.await_count == 2

    with pytest.warns(DeprecationWarning, match="suppress"):
        world.run(interaction.edit_original_response(suppress=True))
    with patch.object(
        discord.Interaction, "delete_original_response", new=AsyncMock()
    ) as delete:
        world.run(interaction.edit_original_response(content="z", delete_after=1))
    delete.assert_awaited_once_with(delay=1)


def test_delete_original_response(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    world.run(interaction.delete_original_response())
    with pytest.warns(DeprecationWarning, match="delete_original_message"):
        world.run(interaction.delete_original_message())
    assert adapter.delete_original_interaction_response.await_count == 2

    with patch("discord.utils.delay_task") as delayed:
        world.run(interaction.delete_original_response(delay=4))
    assert delayed.call_args.args[0] == 4
    delayed.call_args.args[1].close()


def test_interaction_message_edit_and_delete_delegate(
    world: World, adapter: Adapter
) -> None:
    interaction = command(world)
    message = world.run(interaction.original_response())
    with pytest.warns(DeprecationWarning, match="suppress"):
        edited = world.run(message.edit(content="x", suppress=True))
    assert isinstance(edited, InteractionMessage)
    world.run(message.delete(delay=None))
    adapter.delete_original_interaction_response.assert_awaited()


def test_respond_and_edit_fall_back_to_the_original_response(
    world: World, adapter: Adapter
) -> None:
    interaction = command(world)
    world.run(interaction.respond("first"))
    assert adapter.create_interaction_response.await_count == 1
    with patch.object(
        type(interaction.followup), "send", new=AsyncMock(return_value="f")
    ):
        assert world.run(interaction.respond("second")) == "f"
    world.run(interaction.edit(content="x"))
    adapter.edit_original_interaction_response.assert_awaited_once()

    fresh = component(world)
    world.run(fresh.edit(content="x"))
    assert sent(adapter)["type"] == 7


def test_respond_survives_a_concurrent_response(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    with (
        patch.object(
            type(interaction.response),
            "send_message",
            new=AsyncMock(side_effect=InteractionResponded(interaction)),
        ),
        patch.object(
            type(interaction.followup), "send", new=AsyncMock(return_value="f")
        ),
    ):
        assert world.run(interaction.respond("a")) == "f"
    with patch.object(
        type(interaction.response),
        "edit_message",
        new=AsyncMock(side_effect=InteractionResponded(interaction)),
    ):
        world.run(interaction.edit(content="x"))
    adapter.edit_original_interaction_response.assert_awaited_once()


def test_interaction_predicates_and_conversion(world: World) -> None:
    interaction = command(world)
    assert interaction.is_command()
    assert not interaction.is_component()
    assert component(world).is_component()
    assert world.run(interaction.get_guild()).id == world.guild.id
    interaction._guild = None
    assert world.run(interaction.get_guild()).id == world.guild.id

    data = interaction.to_dict()
    assert data["id"] == interaction.id
    assert data["guild_id"] == world.guild.id
    assert data["channel_id"] == world.channel.id
    assert data["data"] == interaction.data
    with_message = component(world, locale="fr", guild_locale="de")
    converted = with_message.to_dict()
    assert converted["locale"] == "fr"
    assert converted["guild_locale"] == "de"
    assert converted["message"]


def test_to_dict_includes_the_resolved_user_and_member(world: World) -> None:
    payload = interaction_payload(
        world,
        data={
            "id": "1",
            "name": "cmd",
            "type": 1,
            "resolved": {
                "users": {str(MEMBER_ID): {"id": str(MEMBER_ID)}},
                "members": {str(MEMBER_ID): {"roles": []}},
            },
        },
    )
    interaction = make_interaction(world, payload)
    interaction.data["resolved"] = {  # type: ignore[index]
        "users": {MEMBER_ID: {"id": str(MEMBER_ID)}},
        "members": {MEMBER_ID: {"roles": []}},
    }
    converted = interaction.to_dict()
    assert converted["user"] == {"id": str(MEMBER_ID)}
    assert converted["member"] == {"roles": []}


@pytest.mark.filterwarnings("ignore:Interaction.cached_channel:DeprecationWarning")
def test_cached_channel(world: World) -> None:
    interaction = command(world)
    assert interaction.cached_channel is not None
    assert interaction.cached_channel.id == world.channel.id
    assert interaction.cached_channel is interaction.cached_channel

    unknown = make_interaction(world, channel_id="777")
    assert unknown.cached_channel.id == 777  # type: ignore[union-attr]
    assert unknown.cached_channel.type is discord.ChannelType.text  # type: ignore[union-attr]

    dm = make_interaction(world, guild=False, channel_id="778")
    assert dm.cached_channel.type is discord.ChannelType.private  # type: ignore[union-attr]


def test_authorisation_helpers(world: World) -> None:
    interaction = command(
        world,
        authorizing_integration_owners={
            "0": str(world.guild.id),
            "1": str(MEMBER_ID),
        },
    )
    assert interaction.is_guild_authorised()
    assert interaction.is_guild_authorized()
    assert interaction.is_user_authorised()
    assert interaction.is_user_authorized()

    owners = interaction.authorizing_integration_owners
    assert owners.guild is not None
    assert owners.guild.id == world.guild.id
    assert owners == AuthorizingIntegrationOwners(
        {"0": str(world.guild.id), "1": str(MEMBER_ID)}, world.state
    )
    assert owners != AuthorizingIntegrationOwners({}, world.state)
    assert hash(owners) == hash((owners.user_id, owners.guild_id))
    assert "AuthorizingIntegrationOwners" in repr(owners)

    nobody = AuthorizingIntegrationOwners({}, world.state)
    assert nobody.user is None
    assert nobody.guild is None

    dm = make_interaction(world, guild=False)
    assert dm.is_guild_authorised() is False
    interaction.user = None
    assert interaction.is_user_authorised() is False


def make_view(world: World, *, timeout: float | None = None) -> Any:
    async def build() -> Any:
        view = discord.ui.View(timeout=timeout)
        view.add_item(discord.ui.Button(label="go", custom_id="go"))
        return view

    return world.run(build())


def test_send_message_with_a_view_stores_it(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    view = make_view(world)

    world.run(interaction.response.send_message("a", view=view))

    assert sent(adapter)["data"]["components"] == view.to_components()
    assert isinstance(view.message, InteractionMessage)
    assert view.parent is interaction
    assert view in world.state.persistent_views


def test_ephemeral_views_get_a_timeout(world: World, adapter: Adapter) -> None:
    interaction = command(world)
    view = make_view(world)
    view.timeout = None
    world.run(interaction.response.send_message("a", view=view, ephemeral=True))
    assert view.timeout == 15 * 60.0


def test_edit_message_with_a_view_replaces_the_stored_one(
    world: World, adapter: Adapter
) -> None:
    interaction = component(world)
    view = make_view(world)

    world.run(interaction.response.edit_message(content="x", view=view))

    assert sent(adapter)["data"]["components"] == view.to_components()
    assert view.message is interaction.message
    assert view in world.state.persistent_views


def test_edit_original_response_with_a_view(world: World, adapter: Adapter) -> None:
    interaction = component(world)
    view = make_view(world)
    adapter.edit_original_interaction_response.return_value = {
        **message_payload(world),
        "components": [],
    }

    message = world.run(interaction.edit_original_response(view=view))

    assert view.message is message
    payload = adapter.edit_original_interaction_response.call_args.kwargs["payload"]
    assert payload["components"][0]["components"][0]["label"] == "go"


def test_editing_without_a_message_fails(world: World, adapter: Adapter) -> None:
    interaction = component(world)
    interaction.message = None
    with pytest.raises(ClientException, match="no message to edit"):
        world.run(
            interaction.response.edit_message(
                file=discord.File(io.BytesIO(b"x"), "a.txt")
            )
        )
    adapter.create_interaction_response.assert_not_called()


def test_interaction_message_state_delegates_to_the_interaction(world: World) -> None:
    interaction = command(world)
    state = interaction._state
    inner = discord.interactions._InteractionMessageState(interaction, state)
    assert world.run(inner._get_guild(world.guild.id)) is world.guild
    payload = world.payload(t.user.User, id="9999", discriminator="0")
    assert world.run(inner.store_user(payload)).id == 9999
    assert inner.create_user(payload).id == 9999


def test_get_guild_prefers_the_cached_attribute(world: World) -> None:
    interaction = command(world)
    interaction._guild = world.guild
    assert world.run(interaction.get_guild()) is world.guild


def test_interaction_message_edit_keeps_the_suppression(
    world: World, adapter: Adapter
) -> None:
    interaction = command(world)
    message = world.run(interaction.original_response())
    message.flags.suppress_embeds = True
    world.run(message.edit(content="x"))
    payload = adapter.edit_original_interaction_response.call_args.kwargs["payload"]
    assert discord.MessageFlags._from_value(payload["flags"]).suppress_embeds
