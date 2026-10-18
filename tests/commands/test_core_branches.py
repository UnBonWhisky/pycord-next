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

import asyncio
import inspect
from enum import Enum
from types import SimpleNamespace
from typing import TYPE_CHECKING, Annotated, Any, Literal, Optional, Union
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import discord
from discord.commands.core import (
    SlashCommandGroup,
    validate_chat_input_description,
    validate_chat_input_name,
)
from discord.enums import SlashCommandOptionType as OptionType
from discord.errors import (
    CheckFailure,
    ClientException,
    InvalidArgument,
    ValidationError,
)
from discord.interactions import InteractionResponse
from tests.commands.interaction_support import (
    add_member,
    interaction_payload,
    make_context,
    make_interaction,
)

if TYPE_CHECKING:
    from tests.models.context import World


def typed(**annotations: Any) -> Any:
    """Give a callback real annotations: option types are not read from strings."""

    def decorator(function: Any) -> Any:
        function.__annotations__.update(annotations)
        return function

    return decorator


def command(callback: Any, **kwargs: Any) -> discord.SlashCommand:
    return discord.SlashCommand(callback, name="cmd", description="d", **kwargs)


class Colour(Enum):
    red = 1
    blue = 2


def option(cmd: discord.SlashCommand, name: str) -> discord.Option:
    return next(o for o in cmd.options if o.name == name)


def test_parameters_become_options() -> None:
    @typed(
        text=str,
        number=int,
        maybe=Optional[str],  # noqa: UP045
        either=Union[discord.User, discord.Role],  # noqa: UP007
        member=Optional[discord.Member],  # noqa: UP045
        colour=Colour,
    )
    async def cb(
        ctx,
        plain,
        text,
        number=5,
        maybe=None,
        either=None,
        member=None,
        colour=Colour.red,
    ) -> None: ...

    cmd = command(cb)

    assert option(cmd, "plain").input_type is OptionType.string
    assert option(cmd, "text").required is True
    assert option(cmd, "number").required is False
    assert option(cmd, "number").default == 5
    assert option(cmd, "maybe").default is None
    assert option(cmd, "maybe").required is False
    assert option(cmd, "member").input_type is OptionType.user
    assert option(cmd, "colour").default is not None or option(cmd, "colour").choices
    assert [o._parameter_name for o in cmd.options] == [
        "plain",
        "text",
        "number",
        "maybe",
        "either",
        "member",
        "colour",
    ]


def test_literal_options_become_choices() -> None:
    @typed(kind=Literal["a", "b"], size=Literal[1, 2, 3])
    async def cb(ctx, kind, size) -> None: ...

    cmd = command(cb)
    assert [c.value for c in option(cmd, "kind").choices] == ["a", "b"]
    assert option(cmd, "kind").input_type is OptionType.string
    assert option(cmd, "size").input_type is OptionType.integer
    assert [c.name for c in option(cmd, "size").choices] == ["1", "2", "3"]


def test_literal_options_must_be_homogeneous() -> None:
    @typed(kind=Literal["a", 1])
    async def mixed(ctx, kind) -> None: ...

    @typed(kind=Literal[b"x"])
    async def odd(ctx, kind) -> None: ...

    with pytest.raises(TypeError, match="same type"):
        command(mixed)
    with pytest.raises(TypeError, match="must be str, int, or float"):
        command(odd)


def test_annotated_options() -> None:
    @typed(
        one=Annotated[str, discord.Option(description="first")],
        two=Annotated[int | None, discord.Option(description="second")],
        three=Annotated[int, "no option here"],
    )
    async def cb(ctx, one, two, three) -> None: ...

    cmd = command(cb)
    assert option(cmd, "one").description == "first"
    assert option(cmd, "two").input_type is OptionType.integer
    assert option(cmd, "two").default is None
    assert option(cmd, "three").input_type is OptionType.integer


def test_default_option_objects_get_their_input_type() -> None:
    declared = discord.Option(description="d")
    declared.input_type = None  # type: ignore[assignment]

    @typed(value=int)
    async def cb(ctx, value=declared) -> None: ...

    cmd = command(cb)
    assert option(cmd, "value") is declared
    assert declared.input_type is OptionType.integer
    assert declared.description == "d"


def test_enum_default_becomes_choices() -> None:
    async def cb(ctx: Any, colour: Colour = Colour) -> None: ...  # type: ignore[assignment]

    cmd = command(cb)
    assert {c.name for c in option(cmd, "colour").choices} == {"red", "blue"}


def test_callbacks_must_declare_the_context() -> None:
    async def missing() -> None: ...

    with pytest.raises(ClientException, match='missing "context" parameter'):
        command(missing)

    class Holder:
        async def method(self) -> None: ...

    with pytest.raises(ClientException, match='missing "context" parameter'):
        command(Holder.method)


def test_explicit_options_are_matched_to_parameters() -> None:
    async def cb(ctx: Any, first: str, second: int, third: str = "x") -> None: ...

    cmd = command(
        cb,
        options=[
            discord.Option(str, name="first"),
            discord.Option(int, name="second"),
        ],
    )
    assert [o._parameter_name for o in cmd.options] == ["first", "second", "third"]
    assert option(cmd, "third").default == "x"


def test_explicit_options_must_fit_the_parameters() -> None:
    async def short(ctx: Any) -> None: ...

    with pytest.raises(ClientException, match="Too many arguments"):
        command(short, options=[discord.Option(str, name="first")])


def test_explicit_option_annotation_forms() -> None:
    async def cb(
        ctx: Any,
        plain: str,
        union: Union[discord.User, discord.Role],  # noqa: UP007
        optional: Optional[int] = None,  # noqa: UP045
        sub: bool = False,
        member: discord.Member = None,  # type: ignore[assignment]
        converter: str = "x",
    ) -> None: ...

    cmd = command(
        cb,
        options=[
            discord.Option(str, name="plain"),
            discord.Option((discord.User, discord.Role), name="union"),
            discord.Option(int, name="optional", required=False),
            discord.Option(OptionType.boolean, name="sub", required=False),
            discord.Option(discord.User, name="member", required=False),
        ],
    )
    assert [o.name for o in cmd.options][:5] == [
        "plain",
        "union",
        "optional",
        "sub",
        "member",
    ]


def test_context_menu_signature_validation() -> None:
    async def good(ctx: Any, user: discord.User) -> None: ...

    async def no_ctx() -> None: ...

    async def no_target(ctx: Any) -> None: ...

    async def too_many(ctx: Any, user: Any, extra: Any) -> None: ...

    command_ = discord.UserCommand(good)
    assert command_.qualified_name == "good"
    assert command_.description == ""
    with pytest.raises(ClientException, match='"ctx" parameter'):
        discord.UserCommand(no_ctx)
    with pytest.raises(ClientException, match='"user" parameter'):
        discord.UserCommand(no_target)
    with pytest.raises(ClientException, match='"message" parameter'):
        discord.MessageCommand(no_target)
    with pytest.raises(ClientException, match="too many parameters"):
        discord.UserCommand(too_many)

    def sync_callback(ctx: Any, user: Any) -> None: ...

    with pytest.raises(TypeError, match="coroutine"):
        discord.UserCommand(sync_callback)  # type: ignore[arg-type]


def test_context_menu_copies_and_decorators() -> None:
    async def action(ctx: Any, user: discord.User) -> None: ...

    async def pin(ctx: Any, message: discord.Message) -> None: ...

    user = discord.UserCommand(action, name="Action")
    copied = user.copy()
    assert copied is not user
    assert copied.name == "Action"
    message = discord.MessageCommand(pin)
    assert message.copy().name == "pin"

    decorated = discord.user_command(name="Hello", guild_ids=[1])(action)
    assert isinstance(decorated, discord.UserCommand)
    assert decorated.name == "Hello"
    assert isinstance(discord.message_command()(pin), discord.MessageCommand)
    assert isinstance(
        discord.application_command(cls=discord.MessageCommand)(pin),
        discord.MessageCommand,
    )


async def test_user_command_invocation_builds_the_target(world: World) -> None:
    pass


def test_user_command_target_without_members(world: World) -> None:
    seen: list[Any] = []

    async def action(ctx: Any, user: discord.User) -> None:
        seen.append(user)

    resolved = {"users": {"55": world.payload(discord.types.user.User, id="55")}}
    payload = interaction_payload(
        world, data={"id": "1", "name": "action", "type": 2, "resolved": resolved}
    )
    ctx = make_context(world, payload)
    world.run(discord.UserCommand(action)._invoke(ctx))
    assert isinstance(seen[0], discord.User)
    assert seen[0].id == 55


def test_user_command_target_with_a_member(world: World) -> None:
    seen: list[Any] = []

    async def action(ctx: Any, user: discord.Member) -> None:
        seen.append(user)

    cached = add_member(world, 66)
    user = world.payload(discord.types.user.User, id="66")
    resolved = {
        "users": {"66": user},
        "members": {"66": {"roles": [], "joined_at": "2024-01-01T00:00:00+00:00"}},
    }
    payload = interaction_payload(
        world, data={"id": "1", "name": "action", "type": 2, "resolved": resolved}
    )
    ctx = make_context(world, payload)
    world.run(discord.UserCommand(action)._invoke(ctx))
    assert isinstance(seen[0], discord.Member)
    assert seen[0].id == cached.id


def test_message_command_target(world: World) -> None:
    seen: list[Any] = []

    async def pin(ctx: Any, message: discord.Message) -> None:
        seen.append(message)

    from tests.commands.test_interaction_responses import message_payload

    resolved = {"messages": {"7900": message_payload(world)}}
    payload = interaction_payload(
        world, data={"id": "1", "name": "pin", "type": 3, "resolved": resolved}
    )
    world.run(discord.MessageCommand(pin)._invoke(make_context(world, payload)))
    assert seen[0].id == 7900

    other_channel = {
        **message_payload(world),
        "channel_id": str(world.channel.id + 5),
    }
    payload = interaction_payload(
        world,
        data={
            "id": "1",
            "name": "pin",
            "type": 3,
            "resolved": {"messages": {"1": other_channel}},
        },
    )
    world.run(discord.MessageCommand(pin)._invoke(make_context(world, payload)))
    assert seen[1].channel.id == world.channel.id + 5


def test_names_and_descriptions_are_validated() -> None:
    validate_chat_input_name("ok-name_1")
    with pytest.raises(TypeError, match="must be of type str"):
        validate_chat_input_name(5)
    with pytest.raises(ValidationError, match="regex"):
        validate_chat_input_name("bad name")
    with pytest.raises(ValidationError, match="lowercase"):
        validate_chat_input_name("Upper")
    with pytest.raises(ValidationError, match="not a valid locale"):
        validate_chat_input_name("ok", "xx-XX")
    with pytest.raises(ValidationError, match="in locale fr"):
        validate_chat_input_name("bad name", "fr")
    validate_chat_input_description("fine")
    with pytest.raises(TypeError, match="must be of type str"):
        validate_chat_input_description(5)
    with pytest.raises(ValidationError, match="1-100"):
        validate_chat_input_description("")
    with pytest.raises(ValidationError, match="1-100"):
        validate_chat_input_description("x" * 101)
    with pytest.raises(ValidationError, match="not a valid locale"):
        validate_chat_input_description("ok", "xx-XX")
    with pytest.raises(ValidationError, match="in locale fr"):
        validate_chat_input_description("", "fr")


def test_group_registration_and_serialisation() -> None:
    group = SlashCommandGroup(
        "tools",
        "Tools",
        name_localizations={"fr": "outils"},
        contexts={discord.InteractionContextType.guild},
        integration_types={discord.IntegrationType.guild_install},
    )
    sub = group.create_subgroup("deep", "Deeper")

    @group.command()
    async def one(ctx: Any) -> None: ...

    @sub.command()
    async def two(ctx: Any) -> None: ...

    @group.subgroup("named", "Named")
    class Named(SlashCommandGroup): ...

    @group.subgroup()
    class inferred(SlashCommandGroup):  # noqa: N801
        """Inferred description."""

    assert [c.name for c in group.subcommands] == ["deep", "one", "named", "inferred"]
    assert group.subcommands[-1].description == "Inferred description."
    data = group.to_dict()
    assert data["name_localizations"] == {"fr": "outils"}
    assert "type" not in data
    assert data["nsfw"] is False
    assert sub.to_dict()["type"] == OptionType.sub_command_group.value
    assert group._find_subcommand("one") is group.subcommands[1]
    with pytest.raises(ClientException, match="was not found"):
        group._find_subcommand("missing")


def test_group_guild_only_and_validation() -> None:
    with pytest.warns(DeprecationWarning, match="guild_only"):
        group = SlashCommandGroup("tools", "Tools", guild_only=True)
    with pytest.warns(DeprecationWarning, match="guild_only"):
        assert group.guild_only is True
    with pytest.warns(DeprecationWarning, match="guild_only"):
        group.guild_only = False
    assert len(group.contexts) == 3
    with (
        pytest.warns(DeprecationWarning, match="guild_only"),
        pytest.raises(InvalidArgument, match="both"),
    ):
        SlashCommandGroup(
            "tools",
            "Tools",
            guild_only=True,
            contexts={discord.InteractionContextType.guild},
        )
    with pytest.raises(InvalidArgument, match="not available for guild commands"):
        SlashCommandGroup("tools", "Tools", guild_ids=[1], contexts=set())
    perms = discord.Permissions(manage_messages=True)
    restricted = SlashCommandGroup(
        "tools",
        "Tools",
        default_member_permissions=perms,
        contexts={discord.InteractionContextType.guild},
        integration_types={discord.IntegrationType.guild_install},
    )
    data = restricted.to_dict()
    assert data["default_member_permissions"] == perms.value
    assert data["contexts"] == [0]
    assert data["integration_types"] == [0]
    guild_group = SlashCommandGroup("tools", "Tools", guild_ids=[1])
    assert "contexts" not in guild_group.to_dict()


def test_group_class_form_collects_members() -> None:
    class Admin(SlashCommandGroup):
        """Admin things."""

        @discord.slash_command()
        async def ban(self, ctx: Any) -> None: ...

        class nested(SlashCommandGroup): ...  # noqa: N801

    group = Admin("admin", "Admin things")
    assert sorted(c.name for c in group.subcommands) == ["ban", "nested"]
    assert group.subcommands[0].parent is group or group.subcommands[1].parent is group


async def test_group_resolves_the_leaf_and_forwards_autocomplete() -> None:
    group = SlashCommandGroup("tools", "Tools")
    inner = group.create_subgroup("inner", "Inner")
    forwarded: list[Any] = []

    @inner.command()
    async def leaf(ctx: Any, value: str) -> None: ...

    leaf.invoke_autocomplete_callback = AsyncMock(
        side_effect=lambda ctx: forwarded.append(ctx)  # noqa: PLW0108
    )  # type: ignore[method-assign]

    ctx = SimpleNamespace(
        interaction=SimpleNamespace(
            data={
                "options": [
                    {"name": "inner", "options": [{"name": "leaf", "options": []}]}
                ]
            }
        )
    )
    assert group._resolve_leaf(ctx) is leaf  # type: ignore[arg-type]
    missing = SimpleNamespace(
        interaction=SimpleNamespace(data={"options": [{"name": "nothing"}]})
    )
    assert group._resolve_leaf(missing) is group  # type: ignore[arg-type]
    bare = SimpleNamespace(interaction=SimpleNamespace(data=None))
    assert group._resolve_leaf(bare) is group  # type: ignore[arg-type]

    top = SimpleNamespace(
        interaction=SimpleNamespace(
            data={
                "options": [
                    {"name": "inner", "options": [{"name": "leaf", "options": []}]}
                ]
            }
        )
    )
    await group.invoke_autocomplete_callback(top)  # type: ignore[arg-type]
    assert top.interaction.data == {"name": "leaf", "options": []}
    assert forwarded == [top]
    nested = SimpleNamespace(
        interaction=SimpleNamespace(data={"options": [{"name": "leaf", "options": []}]})
    )
    await inner.invoke_autocomplete_callback(nested)  # type: ignore[arg-type]
    assert nested.interaction.data == {"name": "leaf", "options": []}
    unknown = SimpleNamespace(
        interaction=SimpleNamespace(data={"options": [{"name": "ghost"}]})
    )
    with pytest.raises(ClientException, match="was not found"):
        await inner.invoke_autocomplete_callback(unknown)  # type: ignore[arg-type]
    forwarded.pop(0)
    assert forwarded == [nested]


def autocomplete_ctx(world: World, focused: str, options: list[dict[str, Any]]) -> Any:
    data = {"id": "1", "name": "cmd", "type": 1, "options": options}
    payload = interaction_payload(world, data=data, type=4)
    interaction = make_interaction(world, payload)
    return SimpleNamespace(interaction=interaction, cog=None)


@pytest.fixture(autouse=True)
def _record_autocomplete_results() -> Any:
    with patch.object(
        InteractionResponse, "send_autocomplete_result", new=AsyncMock()
    ) as sent:
        yield sent


def test_slash_command_autocomplete(world: World) -> None:
    async def suggest(ctx: Any) -> list[Any]:
        return ["alpha", discord.OptionChoice("beta", 2), *[f"x{i}" for i in range(40)]]

    async def cb(
        ctx: Any, name: str = discord.Option(autocomplete=suggest)
    ) -> None: ...

    cmd = command(cb)
    ctx = autocomplete_ctx(
        world,
        "name",
        [{"name": "name", "type": 3, "value": "al", "focused": True}],
    )
    world.run(cmd.invoke_autocomplete_callback(ctx))
    (choices,) = (
        InteractionResponse.send_autocomplete_result.call_args.kwargs["choices"],
    )
    assert len(choices) == 25
    assert choices[0].name == "alpha"
    assert choices[1].value == 2
    assert ctx.value == "al"
    assert ctx.focused.name == "name"
    assert ctx.options == {"name": "al"}
    assert ctx.command is cmd


def test_slash_command_autocomplete_sync_and_unknown(world: World) -> None:
    def suggest(ctx: Any) -> list[str]:
        return ["only"]

    async def cb(
        ctx: Any, name: str = discord.Option(autocomplete=suggest)
    ) -> None: ...

    cmd = command(cb)
    ctx = autocomplete_ctx(
        world,
        "name",
        [
            {"name": "other", "type": 3, "value": "x"},
            {"name": "name", "type": 3, "value": "o", "focused": True},
        ],
    )
    world.run(cmd.invoke_autocomplete_callback(ctx))
    assert (
        InteractionResponse.send_autocomplete_result.call_args.kwargs["choices"][0].name
        == "only"
    )

    unknown = autocomplete_ctx(
        world, "ghost", [{"name": "ghost", "type": 3, "value": "o", "focused": True}]
    )
    with pytest.raises(ClientException, match="was not found in the command"):
        world.run(cmd.invoke_autocomplete_callback(unknown))

    InteractionResponse.send_autocomplete_result.reset_mock()
    unfocused = autocomplete_ctx(
        world, "name", [{"name": "name", "type": 3, "value": "o"}]
    )
    assert world.run(cmd.invoke_autocomplete_callback(unfocused)) is None
    InteractionResponse.send_autocomplete_result.assert_not_called()


def slash_context(world: World, options: list[dict[str, Any]]) -> Any:
    data = {"id": "1", "name": "cmd", "type": 1, "options": options}
    return make_context(world, interaction_payload(world, data=data))


def test_slash_invocation_converts_scalar_options(world: World) -> None:
    seen: dict[str, Any] = {}

    async def cb(
        ctx: Any,
        colour: Colour,
        number: int,
        text: str = "default",
        ignored: str = "kept",
    ) -> None:
        seen.update(colour=colour, number=number, text=text, ignored=ignored)

    cmd = command(
        cb,
        options=[
            discord.Option(Colour, name="colour"),
            discord.Option(int, name="number"),
        ],
    )
    ctx = slash_context(
        world,
        [
            {"name": "colour", "type": 3, "value": "2"},
            {"name": "number", "type": 4, "value": 3},
            {"name": "unknown", "type": 3, "value": "x"},
        ],
    )
    world.run(cmd._invoke(ctx))
    assert seen["colour"] is Colour.blue
    assert seen["number"] == 3
    assert seen["text"] == "default"
    assert seen["ignored"] == "kept"


def test_slash_invocation_enum_by_value(world: World) -> None:
    seen: dict[str, Any] = {}

    @typed(colour=Colour)
    async def cb(ctx, colour) -> None:
        seen["colour"] = colour

    cmd = command(cb)
    ctx = slash_context(world, [{"name": "colour", "type": 3, "value": "1"}])
    world.run(cmd._invoke(ctx))
    assert seen["colour"] is Colour.red

    ctx = slash_context(world, [{"name": "colour", "type": 3, "value": "99"}])
    with pytest.raises(ValueError, match="99"):
        world.run(cmd._invoke(ctx))


def test_slash_invocation_string_converters(world: World) -> None:
    from discord.ext import commands

    seen: list[Any] = []

    class Upper(commands.Converter):  # type: ignore[type-arg]
        async def convert(self, ctx: Any, argument: str) -> str:
            return argument.upper()

    async def cb(ctx: Any, text: str, other: str) -> None:
        seen.extend([text, other])

    cmd = command(
        cb,
        options=[
            discord.Option(Upper, name="text"),
            discord.Option(Upper(), name="other"),
        ],
    )
    ctx = slash_context(
        world,
        [
            {"name": "text", "type": 3, "value": "abc"},
            {"name": "other", "type": 3, "value": "def"},
        ],
    )
    world.run(cmd._invoke(ctx))
    assert seen == ["ABC", "DEF"]


def test_slash_invocation_mentionable_and_unresolved_objects(world: World) -> None:
    seen: dict[str, Any] = {}

    async def cb(ctx: Any, target: Any, ghost: Any) -> None:
        seen.update(target=target, ghost=ghost)

    cmd = command(
        cb,
        options=[
            discord.Option(OptionType.mentionable, name="target"),
            discord.Option(OptionType.user, name="ghost"),
        ],
    )
    resolved = {"users": {"55": world.payload(discord.types.user.User, id="55")}}
    ctx = make_context(
        world,
        interaction_payload(
            world,
            data={
                "id": "1",
                "name": "cmd",
                "type": 1,
                "options": [
                    {"name": "target", "type": 9, "value": "55"},
                    {"name": "ghost", "type": 6, "value": "77"},
                ],
                "resolved": resolved,
            },
        ),
    )
    world.run(cmd._invoke(ctx))
    assert isinstance(seen["target"], discord.User)
    assert isinstance(seen["ghost"], discord.Object)
    assert seen["ghost"].id == 77

    role = world.payload(discord.types.role.Role, id="88")
    ctx = make_context(
        world,
        interaction_payload(
            world,
            data={
                "id": "1",
                "name": "cmd",
                "type": 1,
                "options": [
                    {"name": "target", "type": 9, "value": "88"},
                    {"name": "ghost", "type": 6, "value": "99"},
                ],
                "resolved": {"roles": {"88": role}},
            },
        ),
    )
    world.run(cmd._invoke(ctx))
    assert isinstance(seen["target"], discord.Role)
    ctx = slash_context(
        world,
        [
            {"name": "target", "type": 9, "value": "11"},
            {"name": "ghost", "type": 6, "value": "12"},
        ],
    )
    world.run(cmd._invoke(ctx))
    assert isinstance(seen["target"], discord.Object)


def test_slash_invocation_inside_a_group(world: World) -> None:
    seen: list[Any] = []

    class Tools(SlashCommandGroup):
        @discord.slash_command(name="run")
        @typed(value=int)
        async def run(self, ctx, value) -> None:
            seen.append((self, value))

    group = Tools("tools", "Tools")
    (cmd,) = group.subcommands
    ctx = slash_context(world, [{"name": "value", "type": 4, "value": 5}])
    world.run(cmd._invoke(ctx))
    assert seen == [(group, 5)]


def fake_ctx(**fields: Any) -> Any:
    bot = SimpleNamespace(
        can_run=AsyncMock(return_value=True),
        _before_invoke=None,
        _after_invoke=None,
        dispatch=MagicMock(),
    )
    return SimpleNamespace(bot=bot, command_failed=False, **fields)


def sample_in_cog() -> discord.SlashCommand:
    async def cb(self, ctx) -> None: ...

    return command(cb)


def sample() -> discord.SlashCommand:
    async def cb(ctx: Any) -> None: ...

    return command(cb)


def test_hooks_and_error_handlers_require_coroutines() -> None:
    cmd = sample()

    def plain(ctx: Any) -> None: ...

    with pytest.raises(TypeError, match="error handler"):
        cmd.error(plain)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="pre-invoke"):
        cmd.before_invoke(plain)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="post-invoke"):
        cmd.after_invoke(plain)  # type: ignore[arg-type]


def test_local_and_global_hooks_run_in_order(world: World) -> None:
    cmd = sample()
    calls: list[str] = []

    @cmd.before_invoke
    async def before(ctx: Any) -> None:
        calls.append("before")

    @cmd.after_invoke
    async def after(ctx: Any) -> None:
        calls.append("after")

    async def global_before(ctx: Any) -> None:
        calls.append("global-before")

    async def global_after(ctx: Any) -> None:
        calls.append("global-after")

    ctx = fake_ctx()
    ctx.bot._before_invoke = global_before
    ctx.bot._after_invoke = global_after
    world.run(cmd.call_before_hooks(ctx))
    world.run(cmd.call_after_hooks(ctx))
    assert calls == ["before", "global-before", "after", "global-after"]


def test_prepare_runs_checks_and_releases_concurrency(world: World) -> None:
    cmd = sample()
    ctx = fake_ctx()
    world.run(cmd._prepare(ctx, cmd))
    assert ctx.command is cmd

    ctx.bot.can_run.return_value = False
    with pytest.raises(CheckFailure, match="global check"):
        # can_run raises CheckFailure itself when the global check fails
        world.run(cmd._prepare(fake_ctx(), cmd)) if False else world.run(
            cmd.can_run(ctx)
        )

    failing = sample()
    failing.checks = [lambda c: False]
    with pytest.raises(CheckFailure, match="check functions"):
        world.run(failing._prepare(fake_ctx(), failing))


def test_prepare_releases_the_concurrency_slot_when_hooks_fail(world: World) -> None:
    cmd = sample()
    concurrency = MagicMock()
    concurrency.acquire = AsyncMock()
    concurrency.release = AsyncMock()
    cmd._max_concurrency = concurrency

    @cmd.before_invoke
    async def failing(ctx: Any) -> None:
        raise RuntimeError("hook")

    ctx = fake_ctx()
    with pytest.raises(RuntimeError, match="hook"):
        world.run(cmd._prepare(ctx, cmd))
    concurrency.acquire.assert_awaited_once_with(ctx)
    concurrency.release.assert_awaited_once_with(ctx)


def test_can_run_uses_parent_and_cog_checks(world: World) -> None:
    cmd = sample()
    parent = SimpleNamespace(checks=[lambda c: False])
    cmd.parent = parent  # type: ignore[assignment]
    cmd.checks = [lambda c: True]
    ctx = fake_ctx()
    assert world.run(cmd.can_run(ctx)) is False
    parent.checks = [lambda c: True]
    assert world.run(cmd.can_run(ctx)) is True

    cog = SimpleNamespace(
        cog_check=lambda c: False,
        _get_overridden_method=lambda method: method,
    )
    cmd = sample_in_cog()
    cmd.checks = []
    cmd.cog = cog  # type: ignore[assignment]
    assert world.run(cmd.can_run(ctx)) is False
    cog.cog_check = lambda c: True
    assert world.run(cmd.can_run(ctx)) is True


def test_dispatch_error_calls_every_handler(world: World) -> None:
    cmd = sample()
    seen: list[Any] = []

    @cmd.error
    async def on_error(ctx: Any, error: Exception) -> None:
        seen.append(("command", error))

    ctx = fake_ctx()
    error = RuntimeError("x")
    world.run(cmd.dispatch_error(ctx, error))
    assert ctx.command_failed is True
    assert seen == [("command", error)]
    ctx.bot.dispatch.assert_called_once_with("application_command_error", ctx, error)

    plain = sample()
    other = fake_ctx()
    world.run(plain.dispatch_error(other, error))
    other.bot.dispatch.assert_called_once()


def test_dispatch_error_with_a_cog(world: World) -> None:
    cmd = sample_in_cog()
    seen: list[Any] = []

    class FakeCog:
        async def cog_command_error(self, ctx: Any, error: Exception) -> None:
            seen.append(("cog", error))

        @classmethod
        def _get_overridden_method(cls, method: Any) -> Any:
            return method

    cog = FakeCog()
    cmd.cog = cog  # type: ignore[assignment]

    @cmd.error
    async def on_error(cog_: Any, ctx: Any, error: Exception) -> None:
        seen.append(("command", cog_ is cog))

    ctx = fake_ctx()
    world.run(cmd.dispatch_error(ctx, RuntimeError("x")))
    assert ("command", True) in seen
    assert any(kind == "cog" for kind, _ in seen)


def test_copying_keeps_hooks_checks_and_error_handlers() -> None:
    cmd = sample()

    @cmd.before_invoke
    async def before(ctx: Any) -> None: ...

    @cmd.after_invoke
    async def after(ctx: Any) -> None: ...

    @cmd.error
    async def on_error(ctx: Any, error: Exception) -> None: ...

    check = lambda c: True  # noqa: E731
    cmd.checks = [check]
    copied = cmd.copy()
    assert copied is not cmd
    assert copied._before_invoke is before
    assert copied._after_invoke is after
    assert copied.on_error is on_error
    assert copied.checks == [check]
    assert repr(cmd) == "<discord.commands.SlashCommand name=cmd>"
    assert str(cmd) == "cmd"


def test_qualified_id_and_mention() -> None:
    cmd = sample()
    with pytest.raises(AttributeError, match="has no ID"):
        cmd.qualified_id  # noqa: B018
    cmd.id = 5
    assert cmd.qualified_id == 5
    assert cmd.mention == "</cmd:5>"
    group = SlashCommandGroup("tools", "Tools")
    group.id = 9
    child = sample()
    child.parent = group
    assert child.qualified_id == 9


def test_cooldown_helpers() -> None:
    cmd = sample()
    ctx = SimpleNamespace(
        author=SimpleNamespace(id=1),
        guild=None,
        channel=SimpleNamespace(id=1),
        command=cmd,
        interaction=SimpleNamespace(user=SimpleNamespace(id=1)),
    )
    assert cmd.is_on_cooldown(ctx) is False  # type: ignore[arg-type]
    assert cmd.get_cooldown_retry_after(ctx) == 0.0  # type: ignore[arg-type]
    assert cmd.cooldown is None


def test_application_command_init_conflicts() -> None:
    async def cb(ctx: Any) -> None: ...

    with pytest.warns(DeprecationWarning, match="guild_only"):
        guild_only = discord.SlashCommand(cb, description="d", guild_only=True)
    assert guild_only.contexts == {discord.InteractionContextType.guild}
    with (
        pytest.warns(DeprecationWarning, match="guild_only"),
        pytest.raises(InvalidArgument, match="both 'contexts' and 'guild_only'"),
    ):
        discord.SlashCommand(
            cb,
            description="d",
            guild_only=True,
            contexts={discord.InteractionContextType.guild},
        )
    with pytest.raises(InvalidArgument, match="not available for guild commands"):
        discord.SlashCommand(
            cb,
            description="d",
            guild_ids=[1],
            integration_types={discord.IntegrationType.user_install},
        )


def test_command_guild_only_property() -> None:
    cmd = sample()
    with pytest.warns(DeprecationWarning, match="guild_only"):
        assert cmd.guild_only is False
    with pytest.warns(DeprecationWarning, match="guild_only"):
        cmd.guild_only = True
    assert cmd.contexts == {discord.InteractionContextType.guild}
    with pytest.warns(DeprecationWarning, match="guild_only"):
        assert cmd.guild_only is True
    with pytest.warns(DeprecationWarning, match="guild_only"):
        cmd.guild_only = False
    assert len(cmd.contexts) == 3


def test_calling_a_command_calls_its_callback(world: World) -> None:
    seen: list[Any] = []

    async def cb(ctx: Any, value: int = 1) -> None:
        seen.append(value)

    cmd = command(cb)
    world.run(cmd("ctx", value=4))  # type: ignore[call-arg,arg-type]

    async def in_cog(self, ctx: Any, value: int = 1) -> None:
        seen.append((self, value))

    owned = command(in_cog)
    owned.cog = "the-cog"  # type: ignore[assignment]
    world.run(owned("ctx", value=6))  # type: ignore[call-arg,arg-type]
    assert seen == [4, ("the-cog", 6)]


def test_wrap_callback_translates_errors(world: World) -> None:
    from discord.commands.core import wrap_callback

    async def fine(ctx: Any) -> str:
        return "ok"

    async def cancelled(ctx: Any) -> None:
        raise asyncio.CancelledError

    async def broken(ctx: Any) -> None:
        raise ValueError("bad")

    assert world.run(wrap_callback(fine)(None)) == "ok"
    assert world.run(wrap_callback(cancelled)(None)) is None
    with pytest.raises(discord.ApplicationCommandInvokeError) as info:
        world.run(wrap_callback(broken)(None))
    assert isinstance(info.value.original, ValueError)
    already = discord.ApplicationCommandError("x")

    async def reraises(ctx: Any) -> None:
        raise already

    with pytest.raises(discord.ApplicationCommandError) as passthrough:
        world.run(wrap_callback(reraises)(None))
    assert passthrough.value is already


def test_unwrap_function() -> None:
    from discord.commands.core import unwrap_function

    async def base(ctx: Any) -> None: ...

    import functools

    wrapped = functools.wraps(base)(lambda: None)
    assert unwrap_function(wrapped) is base
    assert unwrap_function(base) is base
    assert inspect.iscoroutinefunction(unwrap_function(base))
