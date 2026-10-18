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


"""Tests for slash command groups shared by several cogs."""

from __future__ import annotations

import asyncio
import itertools
import json
from types import SimpleNamespace
from typing import Any

import pytest

import discord
from discord.commands import ApplicationContext
from discord.ext import commands


def make_bot(**kwargs: Any) -> discord.Bot:
    return discord.Bot(**kwargs)


def payload(bot: discord.Bot) -> list[dict[str, Any]]:
    return [command.to_dict() for command in bot.pending_application_commands]


def shape(node: dict[str, Any]) -> Any:
    options = [shape(o) for o in node.get("options", []) if o.get("type") in (1, 2)]
    return (node["name"], options) if options else node["name"]


def group_shape(bot: discord.Bot) -> list[Any]:
    return [shape(d) for d in payload(bot)]


def make_ctx(bot: discord.Bot, *path: str, **values: Any) -> ApplicationContext:
    options: list[dict[str, Any]] = [
        {"name": k, "type": 3, "value": v} for k, v in values.items()
    ]
    for index, name in enumerate(reversed(path[1:])):
        kind = 1 if index == 0 else 2
        options = [{"name": name, "type": kind, "options": options}]
    data = {"name": path[0], "type": 1, "options": options}
    interaction = SimpleNamespace(
        data=data,
        command=None,
        guild=None,
        user=SimpleNamespace(id=1),
        channel=None,
        _state=SimpleNamespace(),
    )
    return ApplicationContext(bot, interaction)  # type: ignore[arg-type]


async def run(bot: discord.Bot, *path: str, **values: Any) -> ApplicationContext:
    ctx = make_ctx(bot, *path, **values)
    command = bot.get_application_command(path[0]) or next(
        c for c in bot.pending_application_commands if c.name == path[0]
    )
    await command.invoke(ctx)
    return ctx


def test_module_group_with_cog_leaves_registers_one_group() -> None:
    group = discord.SlashCommandGroup("g", "shared group")

    class CogA(discord.Cog):
        @group.command()
        async def a(self, ctx: discord.ApplicationContext) -> None: ...

    class CogB(discord.Cog):
        @group.command()
        async def b(self, ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    cog_a, cog_b = CogA(), CogB()
    bot.add_cog(cog_a)
    bot.add_cog(cog_b)
    assert group_shape(bot) == [("g", ["a", "b"])]
    a, b = (c for c in group.walk_commands())
    assert a.cog is cog_a
    assert b.cog is cog_b
    assert a.options == []
    assert b.options == []


def test_cog_attribute_shared_between_cogs() -> None:
    group = discord.SlashCommandGroup("g", "shared group")

    class CogA(discord.Cog):
        g = group

        @g.command()
        async def a(self, ctx: discord.ApplicationContext) -> None: ...

    class CogB(discord.Cog):
        g = group

        @g.command()
        async def b(self, ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    cog_a, cog_b = CogA(), CogB()
    bot.add_cog(cog_a)
    bot.add_cog(cog_b)
    assert group_shape(bot) == [("g", ["a", "b"])]
    (registered,) = bot.pending_application_commands
    assert registered.cog is cog_a
    a, b = registered.subcommands
    assert (a.cog, b.cog) == (cog_a, cog_b)
    bot.remove_cog("CogB")
    assert group_shape(bot) == [("g", ["a"])]
    assert b.cog is None
    assert a.cog is cog_a
    bot.remove_cog("CogA")
    assert payload(bot) == []
    assert a.cog is None


def test_import_order_does_not_change_the_group() -> None:
    group = discord.SlashCommandGroup("g", "shared group")

    class First(discord.Cog):
        @group.command()
        async def one(self, ctx: discord.ApplicationContext) -> None: ...

    class Second(discord.Cog):
        g = group

        @g.command()
        async def two(self, ctx: discord.ApplicationContext) -> None: ...

    class Third(discord.Cog):
        @group.command()
        async def three(self, ctx: discord.ApplicationContext) -> None: ...

    assert Second.__cog_commands__[0].subcommands == []
    bot = make_bot()
    for cls in (Third, Second, First):
        bot.add_cog(cls())
    (registered,) = bot.pending_application_commands
    assert sorted(c.name for c in registered.subcommands) == ["one", "three", "two"]


def build_three_cogs() -> tuple[
    dict[str, type[discord.Cog]], discord.SlashCommandGroup
]:
    admin = discord.SlashCommandGroup("admin", "Admin commands")

    class Moderation(discord.Cog):
        @admin.command()
        async def ban(self, ctx: discord.ApplicationContext) -> None: ...

        @admin.command()
        async def kick(self, ctx: discord.ApplicationContext) -> None: ...

    class Settings(discord.Cog):
        config = admin.create_subgroup("config", "Configuration")

        @config.command()
        async def prefix(self, ctx: discord.ApplicationContext, value: str) -> None: ...

    class Owner(discord.Cog):
        owned = admin

        @owned.command()
        async def shutdown(self, ctx: discord.ApplicationContext) -> None: ...

    return {"Moderation": Moderation, "Settings": Settings, "Owner": Owner}, admin


EXPECTED = {
    "Moderation": ["ban", "kick"],
    "Settings": [("config", ["prefix"])],
    "Owner": ["shutdown"],
}


def expected_shape(loaded: tuple[str, ...]) -> list[Any]:
    options: list[Any] = []
    for name in ("Moderation", "Settings", "Owner"):
        if name in loaded:
            options.extend(EXPECTED[name])
    return [("admin", options)] if options else []


def ordered(items: list[Any]) -> Any:
    return sorted(
        [(i[0], sorted(i[1])) if isinstance(i, tuple) else i for i in items],
        key=str,
    )


def normalize(shapes: list[Any]) -> Any:
    out = []
    for item in shapes:
        if isinstance(item, tuple):
            out.append((item[0], ordered(item[1])))
        else:
            out.append(item)
    return out


@pytest.mark.parametrize(
    "order", list(itertools.permutations(["Moderation", "Settings", "Owner"]))
)
def test_load_and_unload_permutations(order: tuple[str, ...]) -> None:
    classes, _ = build_three_cogs()
    bot = make_bot()
    loaded: tuple[str, ...] = ()
    for name in order:
        bot.add_cog(classes[name]())
        loaded += (name,)
        assert normalize(group_shape(bot)) == normalize(expected_shape(loaded))
        assert len(bot.pending_application_commands) == 1
    for name in reversed(order):
        bot.remove_cog(name)
        loaded = tuple(n for n in loaded if n != name)
        assert normalize(group_shape(bot)) == normalize(expected_shape(loaded))


@pytest.mark.parametrize(
    "unload", list(itertools.permutations(["Moderation", "Settings", "Owner"]))
)
def test_unload_orders_leave_no_stale_references(unload: tuple[str, ...]) -> None:
    classes, admin = build_three_cogs()
    bot = make_bot()
    for name in ("Moderation", "Settings", "Owner"):
        bot.add_cog(classes[name]())
    members = [m for cls in classes.values() for m in cls.__cog_group_members__]
    for name in unload:
        bot.remove_cog(name)
    assert bot.pending_application_commands == []
    assert all(m.cog is None for m in members)
    assert admin.cog is None
    assert bot._group_registry.groups == {}


def test_reload_after_unload_restores_the_payload() -> None:
    classes, _ = build_three_cogs()
    bot = make_bot()
    for name in classes:
        bot.add_cog(classes[name]())
    before = normalize(group_shape(bot))
    bot.remove_cog("Settings")
    bot.add_cog(classes["Settings"]())
    assert normalize(group_shape(bot)) == before


def test_group_payload_snapshot() -> None:
    classes, _ = build_three_cogs()
    bot = make_bot()
    for name in classes:
        bot.add_cog(classes[name]())
    (data,) = payload(bot)
    assert data["name"] == "admin"
    assert data["description"] == "Admin commands"
    assert "type" not in data
    names = {o["name"]: o for o in data["options"]}
    assert set(names) == {"ban", "kick", "config", "shutdown"}
    assert names["config"]["type"] == 2
    assert names["config"]["description"] == "Configuration"
    (prefix,) = names["config"]["options"]
    assert prefix["type"] == 1
    assert [o["name"] for o in prefix["options"]] == ["value"]
    assert prefix["options"][0]["type"] == 3
    assert names["ban"]["options"] == []
    json.dumps(data)


def test_duplicate_leaf_names_raise_with_both_cogs() -> None:
    group = discord.SlashCommandGroup("g", "d")

    class Alpha(discord.Cog):
        @group.command(name="same")
        async def first(self, ctx: discord.ApplicationContext) -> None: ...

    class Beta(discord.Cog):
        @group.command(name="same")
        async def second(self, ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    alpha = Alpha()
    bot.add_cog(alpha)
    with pytest.raises(discord.ClientException) as info:
        bot.add_cog(Beta())
    assert "Alpha" in str(info.value)
    assert "Beta" in str(info.value)
    assert bot.get_cog("Beta") is None
    assert group_shape(bot) == [("g", ["same"])]
    (registered,) = bot.pending_application_commands
    assert registered.subcommands[0].cog is alpha
    assert Beta.__cog_group_members__[0].cog is None


def test_failed_load_is_atomic() -> None:
    group = discord.SlashCommandGroup("g", "d")

    class Alpha(discord.Cog):
        @group.command(name="same")
        async def first(self, ctx: discord.ApplicationContext) -> None: ...

    class Beta(discord.Cog):
        @discord.slash_command()
        async def plain(self, ctx: discord.ApplicationContext) -> None: ...

        @group.command(name="same")
        async def second(self, ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    bot.add_cog(Alpha())
    with pytest.raises(discord.ClientException):
        bot.add_cog(Beta())
    assert [c.name for c in bot.pending_application_commands] == ["g"]


def test_remove_wrong_cog_keeps_others() -> None:
    classes, _ = build_three_cogs()
    bot = make_bot()
    bot.add_cog(classes["Moderation"]())
    bot.add_cog(classes["Owner"]())
    bot.remove_cog("Moderation")
    assert group_shape(bot) == [("admin", ["shutdown"])]


def test_owner_cog_is_the_group_owner() -> None:
    classes, _ = build_three_cogs()
    bot = make_bot()
    owner = classes["Owner"]()
    bot.add_cog(classes["Moderation"]())
    bot.add_cog(owner)
    (registered,) = bot.pending_application_commands
    assert registered.cog is owner
    bot.remove_cog("Owner")
    assert registered.cog is None
    assert group_shape(bot) == [("admin", ["ban", "kick"])]


def test_two_groups_with_the_same_name_are_merged() -> None:
    class Left(discord.Cog):
        tools = discord.SlashCommandGroup("tools", "Tools")

        @tools.command()
        async def hammer(self, ctx: discord.ApplicationContext) -> None: ...

    class Right(discord.Cog):
        tools = discord.SlashCommandGroup("tools", "Other description")

        @tools.command()
        async def saw(self, ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    bot.add_cog(Left())
    bot.add_cog(Right())
    assert group_shape(bot) == [("tools", ["hammer", "saw"])]
    assert payload(bot)[0]["description"] == "Tools"
    bot.remove_cog("Left")
    assert group_shape(bot) == [("tools", ["saw"])]
    bot.remove_cog("Right")
    assert payload(bot) == []


def test_groups_with_different_guilds_stay_separate() -> None:
    class Global(discord.Cog):
        tools = discord.SlashCommandGroup("tools", "Tools")

        @tools.command()
        async def hammer(self, ctx: discord.ApplicationContext) -> None: ...

    class Guild(discord.Cog):
        tools = discord.SlashCommandGroup("tools", "Tools", guild_ids=[1])

        @tools.command()
        async def saw(self, ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    bot.add_cog(Global())
    bot.add_cog(Guild())
    assert len(bot.pending_application_commands) == 2


def test_cog_guild_ids_apply_to_the_group() -> None:
    class Scoped(discord.Cog, guild_ids=[5]):
        tools = discord.SlashCommandGroup("tools", "Tools")

        @tools.command()
        async def hammer(self, ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    bot.add_cog(Scoped())
    (registered,) = bot.pending_application_commands
    assert registered.guild_ids == [5]
    assert [c.name for c in registered.subcommands] == ["hammer"]


def test_single_cog_pattern_is_unchanged() -> None:
    class Example(discord.Cog):
        greetings = discord.SlashCommandGroup("greetings", "Greetings")
        international = greetings.create_subgroup("international", "International")

        @greetings.command()
        async def hello(self, ctx: discord.ApplicationContext) -> None: ...

        @international.command()
        async def aloha(self, ctx: discord.ApplicationContext) -> None: ...

    assert [c.name for c in Example.greetings.subcommands] == ["international", "hello"]
    bot = make_bot()
    cog = Example()
    bot.add_cog(cog)
    assert normalize(group_shape(bot)) == normalize(
        [("greetings", ["hello", ("international", ["aloha"])])]
    )
    names = {c.qualified_name: c.cog for c in cog.walk_commands()}
    assert names == {
        "greetings hello": cog,
        "greetings international": cog,
        "greetings international aloha": cog,
    }
    bot.remove_cog("Example")
    assert payload(bot) == []
    assert bot.get_application_command("greetings") is None


def test_bot_level_leaf_next_to_cog_leaves() -> None:
    group = discord.SlashCommandGroup("g", "d")

    @group.command()
    async def standalone(ctx: discord.ApplicationContext) -> None: ...

    class Cog(discord.Cog):
        @group.command()
        async def inside(self, ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    bot.add_cog(Cog())
    assert sorted(group_shape(bot)[0][1]) == ["inside", "standalone"]
    bot.remove_cog("Cog")
    assert group.subcommands == [standalone]


def test_manually_added_group_receives_cog_leaves() -> None:
    group = discord.SlashCommandGroup("g", "d")

    class Cog(discord.Cog):
        @group.command()
        async def inside(self, ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    bot.add_application_command(group)
    bot.add_cog(Cog())
    assert bot.pending_application_commands == [group]
    assert [c.name for c in group.subcommands] == ["inside"]
    bot.remove_cog("Cog")
    assert bot.pending_application_commands == [group]


def test_walk_commands_lists_foreign_leaves() -> None:
    group = discord.SlashCommandGroup("g", "d")

    class Cog(discord.Cog):
        @group.command()
        async def inside(self, ctx: discord.ApplicationContext) -> None: ...

    assert [c.qualified_name for c in Cog().walk_commands()] == ["g inside"]


async def test_invocation_binds_the_leaf_cog() -> None:
    seen: list[tuple[str, Any]] = []
    classes: dict[str, type[discord.Cog]] = {}
    group = discord.SlashCommandGroup("g", "d")

    class One(discord.Cog):
        @group.command()
        async def first(self, ctx: discord.ApplicationContext) -> None:
            seen.append(("first", self))

    class Two(discord.Cog):
        sub = group.create_subgroup("sub", "Sub")

        @sub.command(options=[discord.Option(str, name="value")])
        async def second(self, ctx: discord.ApplicationContext, value) -> None:
            seen.append(("second", self, value))

    classes.update(One=One, Two=Two)
    bot = make_bot()
    one, two = One(), Two()
    bot.add_cog(one)
    bot.add_cog(two)
    await run(bot, "g", "first")
    await run(bot, "g", "sub", "second", value="x")
    assert seen == [("first", one), ("second", two, "x")]


async def test_check_and_hook_order() -> None:
    log: list[str] = []
    group = discord.SlashCommandGroup(
        "g", "d", checks=[lambda ctx: log.append("group check") or True]
    )
    sub = group.create_subgroup(
        "sub", "d", checks=[lambda ctx: log.append("subgroup check") or True]
    )

    class Owner(discord.Cog):
        g = group

        async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
            log.append("owner cog_check")
            return True

        async def cog_before_invoke(self, ctx: discord.ApplicationContext) -> None:
            log.append("owner before")

        async def cog_after_invoke(self, ctx: discord.ApplicationContext) -> None:
            log.append("owner after")

    class Leaf(discord.Cog):
        async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
            log.append("leaf cog_check")
            return True

        async def cog_before_invoke(self, ctx: discord.ApplicationContext) -> None:
            log.append("leaf before")

        async def cog_after_invoke(self, ctx: discord.ApplicationContext) -> None:
            log.append("leaf after")

        @sub.command(checks=[lambda ctx: log.append("leaf check") or True])
        async def run(self, ctx: discord.ApplicationContext) -> None:
            log.append("callback")

    bot = make_bot()
    bot.add_cog(Owner())
    bot.add_cog(Leaf())
    await run(bot, "g", "sub", "run")
    positions = {entry: log.index(entry) for entry in set(log)}
    assert (
        positions["owner cog_check"]
        < positions["group check"]
        < positions["subgroup check"]
        < positions["leaf cog_check"]
        < positions["leaf check"]
        < positions["leaf before"]
        < positions["callback"]
        < positions["leaf after"]
        < positions["owner after"]
    )
    assert positions["owner before"] < positions["leaf before"]
    assert positions["callback"] < positions["leaf after"] < positions["owner after"]
    assert positions["leaf check"] < positions["owner before"]
    assert log.count("owner before") == 1


async def test_leaf_cog_error_handler_runs_before_the_group_owner() -> None:
    log: list[str] = []
    group = discord.SlashCommandGroup("g", "d")

    class Owner(discord.Cog):
        g = group

        async def cog_command_error(
            self, ctx: discord.ApplicationContext, error: Exception
        ) -> None:
            log.append("owner error")

    class Leaf(discord.Cog):
        async def cog_command_error(
            self, ctx: discord.ApplicationContext, error: Exception
        ) -> None:
            log.append("leaf error")

        @group.command()
        async def boom(self, ctx: discord.ApplicationContext) -> None:
            raise RuntimeError("boom")

    bot = make_bot()
    bot.add_cog(Owner())
    bot.add_cog(Leaf())
    ctx = make_ctx(bot, "g", "boom")
    (registered,) = bot.pending_application_commands
    with pytest.raises(discord.ApplicationCommandInvokeError) as info:
        await registered.invoke(ctx)
    await ctx.command.dispatch_error(ctx, info.value)
    assert log == ["leaf error", "owner error"]


async def test_group_sync_is_scheduled_once_per_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classes, _ = build_three_cogs()
    bot = make_bot()
    calls: list[int] = []

    async def fake_sync(*args: Any, **kwargs: Any) -> None:
        calls.append(1)

    monkeypatch.setattr(bot, "sync_commands", fake_sync)
    monkeypatch.setattr(type(bot), "is_ready", lambda self: True)
    for name in classes:
        bot.add_cog(classes[name]())
    await asyncio.sleep(0.01)
    assert calls == [1]
    bot.remove_cog("Moderation")
    bot.remove_cog("Owner")
    await asyncio.sleep(0.01)
    assert calls == [1, 1]


async def test_group_sync_respects_auto_sync_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    classes, _ = build_three_cogs()
    bot = make_bot(auto_sync_commands=False)
    calls: list[int] = []

    async def fake_sync(*args: Any, **kwargs: Any) -> None:
        calls.append(1)

    monkeypatch.setattr(bot, "sync_commands", fake_sync)
    monkeypatch.setattr(type(bot), "is_ready", lambda self: True)
    bot.add_cog(classes["Moderation"]())
    await asyncio.sleep(0.01)
    assert calls == []


async def test_no_sync_before_the_bot_is_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    classes, _ = build_three_cogs()
    bot = make_bot()
    calls: list[int] = []

    async def fake_sync(*args: Any, **kwargs: Any) -> None:
        calls.append(1)

    monkeypatch.setattr(bot, "sync_commands", fake_sync)
    bot.add_cog(classes["Moderation"]())
    await asyncio.sleep(0.01)
    assert calls == []


def test_ext_bot_loads_shared_groups() -> None:
    classes, _ = build_three_cogs()
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    for name in classes:
        bot.add_cog(classes[name]())
    assert len(bot.pending_application_commands) == 1


async def test_owner_hooks_wrap_the_hooks_of_every_leaf_cog() -> None:
    log: list[str] = []
    group = discord.SlashCommandGroup("g", "d")
    sub = group.create_subgroup("sub", "d")

    def hooks(label: str) -> dict[str, Any]:
        async def before(self: Any, ctx: discord.ApplicationContext) -> None:
            log.append(f"{label} before")

        async def after(self: Any, ctx: discord.ApplicationContext) -> None:
            log.append(f"{label} after")

        return {"cog_before_invoke": before, "cog_after_invoke": after}

    class Owner(discord.Cog):
        g = group

        locals().update(hooks("owner"))

    class SubOwner(discord.Cog):
        s = sub

        locals().update(hooks("sub owner"))

    class First(discord.Cog):
        locals().update(hooks("first"))

        @sub.command()
        async def one(self, ctx: discord.ApplicationContext) -> None:
            log.append("one")

    class Second(discord.Cog):
        @group.command()
        async def two(self, ctx: discord.ApplicationContext) -> None:
            log.append("two")

    class Plain(discord.Cog):
        @sub.command()
        async def three(self, ctx: discord.ApplicationContext) -> None:
            log.append("three")

    bot = make_bot()
    for cog_class in (Owner, SubOwner, First, Second, Plain):
        bot.add_cog(cog_class())

    await run(bot, "g", "sub", "one")
    assert log == [
        "owner before",
        "sub owner before",
        "first before",
        "one",
        "first after",
        "sub owner after",
        "owner after",
    ]

    log.clear()
    await run(bot, "g", "two")
    assert log == ["owner before", "two", "owner after"]

    log.clear()
    await run(bot, "g", "sub", "three")
    assert log == [
        "owner before",
        "sub owner before",
        "three",
        "sub owner after",
        "owner after",
    ]


async def test_owner_hooks_run_once_for_its_own_leaves() -> None:
    log: list[str] = []
    group = discord.SlashCommandGroup("g", "d")

    class Owner(discord.Cog):
        g = group

        async def cog_before_invoke(self, ctx: discord.ApplicationContext) -> None:
            log.append("before")

        async def cog_after_invoke(self, ctx: discord.ApplicationContext) -> None:
            log.append("after")

        @g.command()
        async def own(self, ctx: discord.ApplicationContext) -> None:
            log.append("own")

    bot = make_bot()
    bot.add_cog(Owner())
    await run(bot, "g", "own")
    assert log == ["before", "own", "after"]


async def test_owner_hooks_stop_with_the_owner_cog() -> None:
    log: list[str] = []
    group = discord.SlashCommandGroup("g", "d")

    class Owner(discord.Cog):
        g = group

        async def cog_before_invoke(self, ctx: discord.ApplicationContext) -> None:
            log.append("owner before")

    class Leaf(discord.Cog):
        @group.command()
        async def leaf(self, ctx: discord.ApplicationContext) -> None:
            log.append("leaf")

    bot = make_bot()
    owner = Owner()
    bot.add_cog(owner)
    bot.add_cog(Leaf())
    await run(bot, "g", "leaf")
    bot.remove_cog("Owner")
    log.clear()
    await run(bot, "g", "leaf")
    assert log == ["leaf"]


async def test_checks_see_the_invoked_leaf_as_ctx_command() -> None:
    seen: list[tuple[str, str]] = []
    group = discord.SlashCommandGroup(
        "g",
        "d",
        checks=[
            lambda ctx: seen.append(("group check", ctx.command.qualified_name)) or True
        ],
    )
    sub = group.create_subgroup("sub", "d")

    class Owner(discord.Cog):
        g = group

        async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
            seen.append(("owner cog_check", ctx.command.qualified_name))
            return True

        async def cog_before_invoke(self, ctx: discord.ApplicationContext) -> None:
            seen.append(("owner before", ctx.command.qualified_name))

    class Leaf(discord.Cog):
        @sub.command()
        async def run(self, ctx: discord.ApplicationContext) -> None:
            seen.append(("callback", ctx.command.qualified_name))

        @group.command()
        async def top(self, ctx: discord.ApplicationContext) -> None:
            seen.append(("callback", ctx.command.qualified_name))

    bot = make_bot()
    bot.add_cog(Owner())
    bot.add_cog(Leaf())

    await run(bot, "g", "sub", "run")
    assert {name for _, name in seen} == {"g sub run"}
    assert [label for label, _ in seen[:2]] == ["owner cog_check", "group check"]

    seen.clear()
    await run(bot, "g", "top")
    assert {name for _, name in seen} == {"g top"}


async def test_failing_group_check_reports_the_leaf_command() -> None:
    group = discord.SlashCommandGroup("g", "d", checks=[lambda ctx: False])
    sub = group.create_subgroup("sub", "d")

    @sub.command()
    async def run(ctx: discord.ApplicationContext) -> None: ...

    bot = make_bot()
    bot.add_application_command(group)
    ctx = make_ctx(bot, "g", "sub", "run")
    with pytest.raises(discord.CheckFailure):
        await group.invoke(ctx)
    assert ctx.command is run
    assert ctx.command.qualified_name == "g sub run"
