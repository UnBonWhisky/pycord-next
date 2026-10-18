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


"""Tests for the comparison between local and registered application commands."""

from __future__ import annotations

import copy
import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

import pytest

import discord
from discord import ChannelType, IntegrationType, InteractionContextType, Permissions
from discord.commands.comparison import (
    COMMAND_DEFAULTS,
    DefaultComparison,
    DefaultSetComparison,
    commands_match,
)
from discord.utils import MISSING

from .helpers import APP_ID, Payload, actions, echo, fill_node, make_bot

if TYPE_CHECKING:
    from collections.abc import Callable


def callback_for(count: int) -> Callable[..., Any]:
    if count == 0:

        async def zero(ctx: discord.ApplicationContext) -> None: ...

        return zero
    if count == 1:

        async def one(ctx: discord.ApplicationContext, a: Any) -> None: ...

        return one

    async def two(ctx: discord.ApplicationContext, a: Any, b: Any) -> None: ...

    return two


def defaulted(command: Any) -> Any:
    discord.Bot().add_application_command(command)
    return command


def make_slash(
    name: str = "tool",
    *,
    options: list[discord.Option] | None = None,
    description: str = "Does things",
    **kwargs: Any,
) -> discord.SlashCommand:
    options = options if options is not None else [text_option()]
    for index, option in enumerate(options):
        option._parameter_name = ("a", "b")[index]
    return defaulted(
        discord.SlashCommand(
            callback_for(len(options)),
            name=name,
            description=description,
            options=options,
            **kwargs,
        )
    )


def text_option(**kwargs: Any) -> discord.Option:
    kwargs.setdefault("name", "text")
    return discord.Option(str, kwargs.pop("description", "Some text"), **kwargs)


def context_menu(
    cls: type[discord.UserCommand | discord.MessageCommand],
    name: str = "Inspect",
    **kwargs: Any,
) -> discord.UserCommand | discord.MessageCommand:
    async def callback(ctx: discord.ApplicationContext, target: Any) -> None: ...

    return defaulted(cls(callback, name=name, **kwargs))


def make_group() -> discord.SlashCommandGroup:
    group = discord.SlashCommandGroup("admin", "Admin commands")
    config = group.create_subgroup("config", "Configuration")

    @group.command(description="Ban somebody")
    async def ban(ctx: discord.ApplicationContext, reason: str) -> None: ...

    @config.command(description="Set a value")
    async def set(
        ctx: discord.ApplicationContext,
        key: discord.Option(str, "Key", choices=["a", "b"]),
    ) -> None: ...

    return defaulted(group)


async def action_of(
    command: Any, remote: Payload | None, guild_id: int | None = None
) -> str | None:
    bot = make_bot(command)
    result = await bot.get_desynced_commands(
        guild_id=guild_id, prefetched=[] if remote is None else [remote]
    )
    return next(c["action"] for c in result if c["command"] is command)


def rich_slash() -> discord.SlashCommand:
    return make_slash(
        options=[
            text_option(
                choices=[
                    discord.OptionChoice("One", "1"),
                    discord.OptionChoice("Two", "2", name_localizations={"fr": "Deux"}),
                ],
                name_localizations={"fr": "texte"},
                description_localizations={"fr": "Du texte"},
            ),
            discord.Option(
                int, "A number", name="number", min_value=1, max_value=9, required=False
            ),
        ],
        name_localizations={"fr": "outil"},
        description_localizations={"fr": "Fait des choses"},
        nsfw=True,
        default_member_permissions=Permissions(8),
        contexts={InteractionContextType.guild, InteractionContextType.bot_dm},
        integration_types={IntegrationType.guild_install, IntegrationType.user_install},
    )


COMMAND_FACTORIES: dict[str, Callable[[], Any]] = {
    "plain slash": make_slash,
    "slash without options": lambda: make_slash(options=[]),
    "rich slash": rich_slash,
    "group": make_group,
    "user command": lambda: context_menu(discord.UserCommand),
    "message command": lambda: context_menu(
        discord.MessageCommand,
        nsfw=True,
        default_member_permissions=Permissions(32),
        name_localizations={"fr": "Inspecter"},
    ),
}


@pytest.mark.parametrize(
    "explicit", [True, False], ids=["defaults-explicit", "defaults-omitted"]
)
@pytest.mark.parametrize(
    "factory", COMMAND_FACTORIES.values(), ids=COMMAND_FACTORIES.keys()
)
async def test_unchanged_commands_are_in_sync(
    factory: Callable[[], Any], explicit: bool
) -> None:
    command = factory()
    assert (
        await action_of(command, echo(make_bot(command) and command, explicit=explicit))
        is None
    )


async def test_unregistered_command_is_upserted() -> None:
    assert await action_of(make_slash(), None) == "upsert"


MUTATIONS: dict[str, Callable[[Payload], None]] = {
    "description": lambda p: p.update(description="Other"),
    "name_localizations added": lambda p: p.update(name_localizations={"fr": "outil"}),
    "name_localizations changed": lambda p: p.update(
        name_localizations={"fr": "autre"}
    ),
    "description_localizations added": lambda p: p.update(
        description_localizations={"fr": "Fait"}
    ),
    "nsfw": lambda p: p.update(nsfw=True),
    "default_member_permissions": lambda p: p.update(default_member_permissions="8"),
    "contexts changed": lambda p: p.update(contexts=[0]),
    "contexts removed": lambda p: p.pop("contexts"),
    "integration_types changed": lambda p: p.update(integration_types=[0, 1]),
    "integration_types removed": lambda p: p.pop("integration_types"),
    "option description": lambda p: p["options"][0].update(description="Other"),
    "option name": lambda p: p["options"][0].update(name="other"),
    "option type": lambda p: p["options"][0].update(type=4),
    "option required": lambda p: p["options"][0].update(required=False),
    "option autocomplete": lambda p: p["options"][0].update(autocomplete=True),
    "option min_length": lambda p: p["options"][0].update(min_length=2),
    "option max_length": lambda p: p["options"][0].update(max_length=20),
    "option name_localizations": lambda p: p["options"][0].update(
        name_localizations={"fr": "x"}
    ),
    "option description_localizations": lambda p: p["options"][0].update(
        description_localizations={"fr": "x"}
    ),
    "option added": lambda p: p["options"].append(
        {"type": 5, "name": "flag", "description": "A flag", "required": False}
    ),
    "option removed": lambda p: p["options"].pop(),
    "choice added": lambda p: p["options"][0].update(
        choices=[{"name": "x", "value": "x"}]
    ),
}


@pytest.mark.parametrize(
    "explicit", [True, False], ids=["defaults-explicit", "defaults-omitted"]
)
@pytest.mark.parametrize("mutation", MUTATIONS.values(), ids=MUTATIONS.keys())
async def test_remote_difference_is_desynced(
    mutation: Callable[[Payload], None], explicit: bool
) -> None:
    command = make_slash()
    remote = echo(command, explicit=explicit)
    mutation(remote)
    assert await action_of(command, remote) == "edit"


RICH_MUTATIONS: dict[str, Callable[[Payload], None]] = {
    "name_localizations value": lambda p: p.update(name_localizations={"fr": "autre"}),
    "name_localizations removed": lambda p: p.pop("name_localizations"),
    "description_localizations removed": lambda p: p.update(
        description_localizations=None
    ),
    "nsfw cleared": lambda p: p.update(nsfw=False),
    "default_member_permissions cleared": lambda p: p.update(
        default_member_permissions=None
    ),
    "default_member_permissions changed": lambda p: p.update(
        default_member_permissions="32"
    ),
    "contexts widened": lambda p: p.update(contexts=[0, 1, 2]),
    "integration_types narrowed": lambda p: p.update(integration_types=[0]),
    "choice value": lambda p: p["options"][0]["choices"][0].update(value="9"),
    "choice name": lambda p: p["options"][0]["choices"][0].update(name="Uno"),
    "choice name_localizations": lambda p: p["options"][0]["choices"][1].update(
        name_localizations={"fr": "Duo"}
    ),
    "choice removed": lambda p: p["options"][0]["choices"].pop(),
    "choice order": lambda p: p["options"][0]["choices"].reverse(),
    "choices cleared": lambda p: p["options"][0].update(choices=[]),
    "option order": lambda p: p["options"].reverse(),
    "min_value changed": lambda p: p["options"][1].update(min_value=2),
    "min_value removed": lambda p: p["options"][1].pop("min_value"),
    "max_value changed": lambda p: p["options"][1].update(max_value=10),
    "required flipped": lambda p: p["options"][1].update(required=True),
}


@pytest.mark.parametrize("mutation", RICH_MUTATIONS.values(), ids=RICH_MUTATIONS.keys())
async def test_remote_difference_on_a_full_command_is_desynced(
    mutation: Callable[[Payload], None],
) -> None:
    command = rich_slash()
    remote = echo(command)
    mutation(remote)
    assert await action_of(command, remote) == "edit"


LOCAL_VARIANTS: dict[str, dict[str, Any]] = {
    "nsfw": {"nsfw": True},
    "permissions": {"default_member_permissions": Permissions(8)},
    "name_localizations": {"name_localizations": {"fr": "outil"}},
    "description_localizations": {"description_localizations": {"fr": "Fait"}},
    "contexts": {"contexts": {InteractionContextType.guild}},
    "integration_types": {"integration_types": {IntegrationType.user_install}},
    "description": {"description": "Another description"},
    "name": {"name": "other"},
    "options": {"options": [text_option(description="Other text")]},
    "option type": {"options": [discord.Option(int, "Some text", name="text")]},
    "option choices": {"options": [text_option(choices=["a"])]},
    "option constraints": {"options": [text_option(min_length=1, max_length=5)]},
    "extra option": {
        "options": [text_option(), text_option(name="more", required=False)]
    },
}


@pytest.mark.parametrize("variant", LOCAL_VARIANTS.values(), ids=LOCAL_VARIANTS.keys())
async def test_local_difference_is_desynced(variant: dict[str, Any]) -> None:
    reference = make_slash()
    remote = echo(reference)
    changed = make_slash(**variant)
    result = await action_of(changed, remote)
    assert result == ("upsert" if variant.get("name") else "edit")


async def test_default_member_permissions_compare_by_value() -> None:
    command = make_slash(default_member_permissions=Permissions(8))
    assert await action_of(command, echo(command)) is None
    remote = echo(command)
    remote["default_member_permissions"] = "0"
    assert await action_of(command, remote) == "edit"
    zero = make_slash(default_member_permissions=Permissions(0))
    assert await action_of(zero, echo(zero)) is None
    remote = echo(zero)
    remote["default_member_permissions"] = None
    assert await action_of(zero, remote) == "edit"


async def test_extra_remote_fields_are_ignored() -> None:
    command = make_slash()
    remote = echo(command)
    remote.update(
        guild_id="1",
        name_localized="outil",
        description_localized="Fait des choses",
        unknown_future_field=[1, 2, 3],
    )
    remote["options"][0].update(name_localized="texte", file_types=None)
    assert await action_of(command, remote) is None


async def test_nested_groups_and_subcommands() -> None:
    group = make_group()
    reference = echo(group)
    assert await action_of(group, reference) is None
    assert await action_of(group, echo(group, explicit=False)) is None

    def sub(p: Payload, name: str) -> Payload:
        return next(o for o in p["options"] if o["name"] == name)

    mutations: dict[str, Callable[[Payload], None]] = {
        "group description": lambda p: p.update(description="Other"),
        "group nsfw": lambda p: p.update(nsfw=True),
        "group permissions": lambda p: p.update(default_member_permissions="8"),
        "group localizations": lambda p: p.update(name_localizations={"fr": "x"}),
        "subcommand description": lambda p: sub(p, "ban").update(description="Other"),
        "subcommand option": lambda p: sub(p, "ban")["options"][0].update(
            description="Other"
        ),
        "subcommand removed": lambda p: p["options"].remove(sub(p, "ban")),
        "subcommand added": lambda p: p["options"].append(
            {"type": 1, "name": "extra", "description": "Extra", "options": []}
        ),
        "subcommand renamed": lambda p: sub(p, "ban").update(name="kick"),
        "subcommand localizations": lambda p: sub(p, "ban").update(
            description_localizations={"fr": "x"}
        ),
        "subgroup description": lambda p: sub(p, "config").update(description="Other"),
        "subgroup type": lambda p: sub(p, "config").update(type=1),
        "nested subcommand": lambda p: sub(sub(p, "config"), "set").update(
            description="Other"
        ),
        "nested subcommand option": lambda p: sub(sub(p, "config"), "set")["options"][
            0
        ].update(choices=[{"name": "a", "value": "z"}]),
        "nested choice added": lambda p: sub(sub(p, "config"), "set")["options"][0][
            "choices"
        ].append({"name": "c", "value": "c"}),
        "nested subcommand removed": lambda p: sub(p, "config").update(options=[]),
    }
    for label, mutation in mutations.items():
        remote = copy.deepcopy(reference)
        mutation(remote)
        assert await action_of(group, remote) == "edit", label


async def test_subcommand_order_does_not_matter() -> None:
    group = make_group()
    remote = echo(group)
    remote["options"].reverse()
    assert await action_of(group, remote) is None


async def test_context_fields_are_ignored_for_guild_commands() -> None:
    command = make_slash(guild_ids=[7])
    remote = echo(command)
    remote.update(guild_id="7", contexts=[0, 1, 2], integration_types=[0, 1])
    assert await action_of(command, remote, guild_id=7) is None
    remote["nsfw"] = True
    assert await action_of(command, remote, guild_id=7) == "edit"


async def test_commands_are_matched_by_name_and_type() -> None:
    slash = make_slash("inspect", options=[])
    user = context_menu(discord.UserCommand, "inspect")
    message = context_menu(discord.MessageCommand, "inspect")
    bot = make_bot(slash, user, message)
    assert await actions(bot, [echo(slash), echo(user)]) == [
        ("inspect", None),
        ("inspect", None),
        ("inspect", "upsert"),
    ]
    other = echo(user)
    other["description"] = ""
    assert await actions(bot, [echo(message), other]) == [
        ("inspect", "upsert"),
        ("inspect", None),
        ("inspect", None),
    ]


async def test_remote_commands_without_a_local_command_are_deleted() -> None:
    kept = make_slash("kept", options=[])
    stale = make_slash("stale", options=[])
    stale_remote = echo(stale)
    stale_remote["id"] = "99"
    bot = make_bot(kept)
    result = await bot.get_desynced_commands(prefetched=[echo(kept), stale_remote])
    assert [(c["action"], c.get("id")) for c in result] == [(None, 1), ("delete", 99)]
    assert result[1]["command"] is stale_remote


async def test_missing_type_in_the_payload_means_a_slash_command() -> None:
    command = make_slash()
    remote = echo(command, explicit=False)
    remote.pop("type", None)
    assert await action_of(command, remote) is None


async def test_defaults_can_be_customised() -> None:
    class CustomBot(discord.Bot):
        async def _get_command_defaults(self) -> Any:
            defaults = COMMAND_DEFAULTS.copy()
            defaults["integration_types"] = DefaultSetComparison(
                (MISSING, {IntegrationType.guild_install.value}),
                lambda x, y: set(x) == set(y),
            )
            return defaults

    command = make_slash()
    command.integration_types = {IntegrationType.guild_install}
    bot = CustomBot()
    bot.add_application_command(command)
    remote = echo(command)
    del remote["integration_types"]
    result = await bot.get_desynced_commands(prefetched=[remote])
    assert result[0]["action"] is None


def test_default_comparison_rules() -> None:
    rule = DefaultComparison((None, MISSING), lambda x, y: x == y)
    assert rule.check(None, MISSING)
    assert rule.check(MISSING, None)
    assert not rule.check(None, "a")
    assert not rule.check("a", MISSING)
    assert rule.check("a", "a")
    assert not rule.check("a", "b")

    sets = DefaultSetComparison(([], MISSING), lambda x, y: x == y)
    assert sets.check([], MISSING)
    assert sets.check([1, 2], [2, 1])
    assert not sets.check([1], [1, 2])
    assert not sets.check([], [1])


def test_channel_types_are_compared_as_sets() -> None:
    option = discord.Option(
        discord.abc.GuildChannel,
        "Channel",
        name="channel",
        channel_types=[ChannelType.text, ChannelType.voice],
    )
    command = make_slash(options=[option])
    remote = echo(command)
    assert remote["options"][0]["channel_types"] == [0, 2]
    remote["options"][0]["channel_types"] = [2, 0]
    assert commands_match(command, remote)
    remote["options"][0]["channel_types"] = [0]
    assert not commands_match(command, remote)
    del remote["options"][0]["channel_types"]
    assert not commands_match(command, remote)


class FakeHTTP:
    def __init__(self, remote: list[Payload]) -> None:
        self.remote = {c["id"]: copy.deepcopy(c) for c in remote}
        self.next_id = 1000
        self.get_global_commands = AsyncMock(side_effect=self._get)
        self.get_guild_commands = AsyncMock(side_effect=self._get_guild)
        self.bulk_upsert_global_commands = AsyncMock(side_effect=self._bulk)
        self.bulk_upsert_guild_commands = AsyncMock(side_effect=self._bulk_guild)
        self.upsert_global_command = AsyncMock(side_effect=self._upsert)
        self.edit_global_command = AsyncMock(side_effect=self._edit)
        self.delete_global_command = AsyncMock(side_effect=self._delete)

    def _store(self, payload: Payload, command_id: str | None = None) -> Payload:
        if command_id is None:
            self.next_id += 1
            command_id = str(self.next_id)
        stored = fill_node(payload, True, top=True)
        stored["id"] = command_id
        self.remote[command_id] = stored
        return copy.deepcopy(stored)

    async def _get(self, app_id: int, **kwargs: Any) -> list[Payload]:
        return [copy.deepcopy(c) for c in self.remote.values()]

    async def _get_guild(self, app_id: int, guild_id: int) -> list[Payload]:
        return []

    async def _bulk(self, app_id: int, data: list[Payload]) -> list[Payload]:
        sent = {(c["name"], c.get("type", 1)) for c in data}
        for command in self.remote.values():
            if command.get("type") == 4 and (command["name"], 4) not in sent:
                raise AssertionError("the Entry Point command was removed")
        by_key = {(c["name"], c.get("type", 1)): c["id"] for c in self.remote.values()}
        self.remote = {}
        return [self._store(p, by_key.get((p["name"], p.get("type", 1)))) for p in data]

    async def _bulk_guild(
        self, app_id: int, guild_id: int, data: list[Payload]
    ) -> list[Payload]:
        return []

    async def _upsert(self, app_id: int, data: Payload) -> Payload:
        return self._store(data)

    async def _edit(self, app_id: int, command_id: Any, data: Payload) -> Payload:
        return self._store(data, str(command_id))

    async def _delete(self, app_id: int, command_id: Any) -> None:
        self.remote.pop(str(command_id), None)


def bot_with_http(
    remote: list[Payload], *commands: Any
) -> tuple[discord.Bot, FakeHTTP]:
    bot = make_bot(*commands)
    bot._connection.user = SimpleNamespace(id=APP_ID)  # type: ignore[assignment]
    http = FakeHTTP(remote)
    bot.http = http  # type: ignore[assignment]
    return bot, http


async def test_sync_registers_then_leaves_unchanged_commands_alone() -> None:
    slash = rich_slash()
    group = make_group()
    user = context_menu(discord.UserCommand)
    bot, http = bot_with_http([], slash, group, user)

    await bot.sync_commands()
    assert http.bulk_upsert_global_commands.await_count == 1
    sent = http.bulk_upsert_global_commands.await_args.args[1]
    assert [p["name"] for p in sent] == ["tool", "admin", "Inspect"]
    assert slash.id is not None
    assert group.id is not None
    assert user.id is not None

    http.bulk_upsert_global_commands.reset_mock()
    await bot.sync_commands()
    http.bulk_upsert_global_commands.assert_not_awaited()
    http.edit_global_command.assert_not_awaited()

    slash.nsfw = False
    await bot.sync_commands()
    assert http.bulk_upsert_global_commands.await_count == 1
    sent = http.bulk_upsert_global_commands.await_args.args[1]
    assert next(p for p in sent if p["name"] == "tool")["nsfw"] is False

    http.bulk_upsert_global_commands.reset_mock()
    await bot.sync_commands()
    http.bulk_upsert_global_commands.assert_not_awaited()


async def test_sync_detects_a_change_deep_in_a_group() -> None:
    group = make_group()
    bot, http = bot_with_http([], group)
    await bot.sync_commands()
    http.bulk_upsert_global_commands.reset_mock()
    await bot.sync_commands()
    http.bulk_upsert_global_commands.assert_not_awaited()

    nested = next(c for c in group.walk_commands() if c.name == "set")
    nested.options[0].choices = [discord.OptionChoice("c", "c")]
    await bot.sync_commands()
    assert http.bulk_upsert_global_commands.await_count == 1


async def test_sync_individual_edits_only_changed_commands() -> None:
    first = make_slash("first", options=[])
    second = make_slash("second", options=[])
    bot, http = bot_with_http([], first, second)
    await bot.sync_commands(method="bulk")
    second.description = "Changed"
    await bot.sync_commands(method="individual")
    http.edit_global_command.assert_awaited_once()
    assert http.edit_global_command.await_args.args[1] == int(second.id)  # type: ignore[arg-type]
    http.upsert_global_command.assert_not_awaited()
    http.delete_global_command.assert_not_awaited()


async def test_sync_individual_deletes_stale_commands() -> None:
    kept = make_slash("kept", options=[])
    stale = make_slash("stale", options=[])
    stale_remote = echo(stale)
    stale_remote["id"] = "77"
    bot, http = bot_with_http([echo(kept), stale_remote], kept)
    await bot.sync_commands(method="individual")
    http.delete_global_command.assert_awaited_once()
    assert http.delete_global_command.await_args.args[1] == 77
    assert list(http.remote) == ["1"]


@pytest.mark.parametrize("method", ["bulk", "individual", "auto"])
async def test_sync_without_deleting_existing_commands(method: str) -> None:
    kept = make_slash("kept", options=[])
    changed = make_slash("changed", options=[])
    stale = make_slash("stale", options=[])
    kept_remote = echo(kept)
    stale_remote = echo(stale)
    stale_remote["id"] = "77"
    changed_remote = echo(changed)
    changed_remote["id"] = "78"
    changed_remote["description"] = "Old"
    bot, http = bot_with_http(
        [kept_remote, stale_remote, changed_remote], kept, changed
    )

    await bot.sync_commands(method=method, delete_existing=False)  # type: ignore[arg-type]

    http.delete_global_command.assert_not_awaited()
    assert "77" in http.remote
    assert http.remote["78"]["description"] == changed.description


async def test_sync_ignores_registered_commands_it_does_not_know(
    caplog: pytest.LogCaptureFixture,
) -> None:
    command = make_slash("known", options=[])
    bot, http = bot_with_http([], command)

    async def bulk(app_id: int, data: list[Payload]) -> list[Payload]:
        stored = [http._store(p) for p in data]
        unknown = http._store(echo(make_slash("ghost", options=[])))
        return [*stored, unknown]

    http.bulk_upsert_global_commands = AsyncMock(side_effect=bulk)
    with caplog.at_level(logging.WARNING, logger="discord.bot"):
        await bot.sync_commands()
    assert any("ghost" in record.getMessage() for record in caplog.records)
    assert command.id is not None


def entry_point_remote(command_id: str = "55") -> Payload:
    return {
        "id": command_id,
        "application_id": str(APP_ID),
        "version": "1",
        "name": "launch",
        "description": "Launch the activity",
        "type": 4,
        "handler": 2,
        "contexts": [0, 1, 2],
        "integration_types": [0],
        "default_member_permissions": None,
        "nsfw": False,
    }


async def test_remote_entry_point_is_never_desynced_for_deletion() -> None:
    kept = make_slash("kept", options=[])
    remote = entry_point_remote()
    bot = make_bot(kept)
    result = await bot.get_desynced_commands(prefetched=[echo(kept), remote])
    assert [(c["action"], c.get("id")) for c in result] == [(None, 1), (None, 55)]
    assert result[1]["command"] is remote


@pytest.mark.parametrize("method", ["bulk", "individual", "auto"])
@pytest.mark.parametrize("force", [False, True])
async def test_sync_keeps_a_remote_entry_point(method: str, force: bool) -> None:
    kept = make_slash("kept", options=[])
    stale = make_slash("stale", options=[])
    stale_remote = echo(stale)
    stale_remote["id"] = "77"
    remote = entry_point_remote()
    bot, http = bot_with_http([echo(kept), stale_remote, remote], kept)

    await bot.sync_commands(method=method, force=force)  # type: ignore[arg-type]

    assert "55" in http.remote
    assert http.remote["55"]["handler"] == 2
    assert http.remote["55"]["name"] == "launch"
    assert "77" not in http.remote
    if method != "individual" or force:
        sent = http.bulk_upsert_global_commands.await_args.args[1]
        assert remote in sent
    else:
        http.delete_global_command.assert_awaited_once()
        assert http.delete_global_command.await_args.args[1] == 77


async def test_sync_leaves_a_remote_entry_point_without_changes_alone(
    caplog: pytest.LogCaptureFixture,
) -> None:
    kept = make_slash("kept", options=[])
    bot, http = bot_with_http([echo(kept), entry_point_remote()], kept)

    with caplog.at_level(logging.WARNING, logger="discord.bot"):
        await bot.sync_commands()

    http.bulk_upsert_global_commands.assert_not_awaited()
    http.delete_global_command.assert_not_awaited()
    assert not caplog.records


async def test_a_local_entry_point_replaces_the_remote_one_by_name() -> None:

    async def launch(ctx: discord.ApplicationContext) -> None: ...

    local = discord.EntryPointCommand(
        launch,
        name="launch",
        description="Launch the activity",
        handler=discord.EntryPointHandler.app_handler,
    )
    bot, http = bot_with_http([entry_point_remote()], local)

    await bot.sync_commands()

    assert http.remote["55"]["handler"] == 1
    assert local.id == "55"
