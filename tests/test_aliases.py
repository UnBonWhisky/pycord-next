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

import ast
import asyncio
import importlib
import inspect
import sys
import types
import warnings
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, TypeVar
from unittest.mock import AsyncMock, MagicMock

import pytest
from typing_extensions import deprecated

import discord
from discord import (
    AuditLogDiff,
    Color,
    Colour,
    Embed,
    ExpireBehavior,
    ExpireBehaviour,
    Role,
    RoleColours,
    ui,
)
from discord._internal.aliases import (
    SPELLING_ALIASES,
    AliasMixin,
    accepts_aliases,
    alias_of,
    canonical_of,
    export_module_aliases,
    install_aliases,
)
from discord.ext import bridge, commands, pages
from discord.ext.commands import BadColorArgument, ColorConverter
from discord.guild import Guild
from discord.integrations import StreamIntegration
from discord.raw_models import RawReactionActionEvent, RawReactionClearEmojiEvent
from discord.reaction import Reaction
from discord.utils import MISSING

if TYPE_CHECKING:
    from collections.abc import Coroutine

T = TypeVar("T")


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


NAMESPACES = (discord, ui, commands, bridge, pages)
ALIAS_MODULES = (
    "discord.colour",
    "discord.enums",
    "discord.ext.commands.converter",
    "discord.ext.commands.errors",
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("colour", "color"),
        ("Colour", "Color"),
        ("COLOUR", "COLOR"),
        ("colours", "colors"),
        ("accent_colour", "accent_color"),
        ("burst_colours", "burst_colors"),
        ("lighter_grey", "lighter_gray"),
        ("greyple", "grayple"),
        ("ExpireBehaviour", "ExpireBehavior"),
        ("expire_behaviour", "expire_behaviour".replace("behaviour", "behavior")),
        ("BadColourArgument", "BadColorArgument"),
        ("colour_and_behaviour", "color_and_behavior"),
        ("name", None),
        ("color", None),
        ("", None),
    ],
)
def test_alias_of(name: str, expected: str | None) -> None:
    assert alias_of(name) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("color", "colour"),
        ("Color", "Colour"),
        ("accent_color", "accent_colour"),
        ("ExpireBehavior", "ExpireBehaviour"),
        ("light_gray", "light_grey"),
        ("colour", None),
        ("name", None),
    ],
)
def test_canonical_of(name: str, expected: str | None) -> None:
    assert canonical_of(name) == expected


def test_alias_table_is_consistent() -> None:
    for canonical, alias in SPELLING_ALIASES.items():
        assert alias_of(canonical) == alias
        assert canonical_of(alias) == canonical


class Sample(AliasMixin):
    __slots__ = ("__weakref__", "_accent_colour", "grey_value")

    shade_colour = 5

    def __init__(self) -> None:
        self._accent_colour = 7
        self.grey_value = 1

    @property
    def colour(self) -> int:
        return self._accent_colour

    @colour.setter
    def colour(self, value: int) -> None:
        self._accent_colour = value

    @classmethod
    def make(cls, *, colour: int = 0, color: int = 0) -> tuple[type, int]:
        del color
        return cls, colour

    @staticmethod
    def static(*, colour: int | None = None, color: int | None = None) -> int | None:
        del color
        return colour

    @classmethod
    def dark_grey(cls) -> str:
        return "dark"

    def function(self, *, colour: Any = MISSING, color: Any = MISSING) -> Any:
        del color
        return colour

    async def coroutine(
        self, *, colour: Any = MISSING, color: Any = MISSING, plain: int = 0
    ) -> Any:
        del color
        return colour, plain


def test_install_property_is_shared_and_writable() -> None:
    sample = Sample()
    assert Sample.color is Sample.colour
    assert sample.color == 7
    sample.color = 9
    assert sample.colour == 9


def test_install_slot_delegates_get_set_del() -> None:
    sample = Sample()
    assert sample.grey_value == 1
    assert sample.gray_value == 1
    sample.gray_value = 3
    assert sample.grey_value == 3
    del sample.gray_value
    assert not hasattr(sample, "grey_value")
    assert not hasattr(sample, "gray_value")


def test_install_class_attribute_and_methods() -> None:
    assert Sample.shade_color == 5
    assert Sample.dark_gray() == "dark"
    assert Sample.dark_gray.__func__ is Sample.dark_grey.__func__
    assert Sample.make(color=4) == (Sample, 4)
    assert Sample.static(color=6) == 6


def test_install_annotation_only_attribute() -> None:
    class Annotated(AliasMixin):
        accent_colour: int

        def __init__(self) -> None:
            self.accent_colour = 3

    assert Annotated().accent_color == 3


def test_install_does_not_touch_private_names() -> None:
    assert not hasattr(Sample, "_accent_color")


def test_install_never_overwrites_explicit_definition() -> None:
    class Explicit(AliasMixin):
        @property
        def colour(self) -> str:
            return "british"

        @property
        def color(self) -> str:
            return "american"

    assert Explicit().colour == "british"
    assert Explicit().color == "american"


def test_subclass_override_rebinds_alias() -> None:
    class Child(Sample):
        @property
        def colour(self) -> int:
            return -1

    assert Child().color == -1
    assert Sample().color == 7


def test_install_aliases_can_be_called_directly() -> None:
    class Plain:
        @property
        def colour(self) -> int:
            return 1

    install_aliases(Plain)
    assert Plain().color == 1


def test_deprecated_property_alias_gets_its_own_message() -> None:
    class Deprecated(AliasMixin):
        @property
        @deprecated("Deprecated.colour is deprecated, use colours.primary instead.")
        def colour(self) -> int:
            return 1

    assert Deprecated.color.fget.__deprecated__ == (
        "Deprecated.color is deprecated, use colors.primary instead."
    )
    with pytest.warns(DeprecationWarning, match=r"Deprecated\.colour is deprecated"):
        assert Deprecated().colour == 1
    with pytest.warns(DeprecationWarning, match=r"Deprecated\.color is deprecated"):
        assert Deprecated().color == 1


def test_deprecated_function_alias_gets_its_own_message() -> None:
    class Deprecated(AliasMixin):
        @deprecated("Deprecated.grey() is deprecated.")
        def grey(self) -> int:
            return 1

    with pytest.warns(DeprecationWarning, match=r"Deprecated\.gray\(\) is deprecated"):
        assert Deprecated().gray() == 1


def test_accepts_aliases_renames_keyword() -> None:
    sample = Sample()
    assert sample.function(color=3) == 3
    assert sample.function(colour=4) == 4
    assert sample.function() is MISSING
    assert Sample.make() == (Sample, 0)
    assert Sample.static(colour=2) == 2


def test_accepts_aliases_keeps_coroutine_function() -> None:
    assert inspect.iscoroutinefunction(Sample.coroutine)
    assert run(Sample().coroutine(color=2, plain=1)) == (2, 1)


@pytest.mark.parametrize(
    "kwargs", [{"colour": 1, "color": 2}, {"color": 1, "colour": 2}]
)
def test_accepts_aliases_conflict_raises(kwargs: dict[str, int]) -> None:
    with pytest.raises(
        TypeError,
        match=r"Sample\.function\(\) got values for both 'colour' and its alias 'color'",
    ):
        Sample().function(**kwargs)


def test_accepts_aliases_unset_alias_is_ignored() -> None:
    sample = Sample()
    assert sample.function(colour=1, color=None) == 1
    assert sample.function(colour=1, color=MISSING) == 1
    assert sample.function(colour=None, color=2) == 2
    assert sample.function(colour=MISSING, color=2) == 2
    assert sample.function(colour=0, color=None) == 0


def test_accepts_aliases_zero_is_a_value() -> None:
    with pytest.raises(TypeError, match="got values for both"):
        Sample().function(colour=0, color=1)
    assert Sample().function(color=0) == 0


def test_accepts_aliases_preserves_signature() -> None:
    def original(self: Any, *, colour: int = 0, color: int = 0, other: str = "") -> int:
        del self, color, other
        return colour

    wrapped = accepts_aliases(original)
    assert wrapped is not original
    assert inspect.signature(wrapped) == inspect.signature(original)
    assert wrapped.__wrapped__ is original
    assert wrapped.__name__ == "original"


def test_accepts_aliases_leaves_unrelated_functions_untouched() -> None:
    def unrelated(a: int, *, b: int = 0) -> int:
        return a + b

    assert accepts_aliases(unrelated) is unrelated


def test_accepts_aliases_is_idempotent() -> None:
    wrapped = accepts_aliases(Sample.function)
    assert accepts_aliases(wrapped) is wrapped


def test_accepts_aliases_works_on_wrapped_functions() -> None:
    @deprecated("old")
    def old(*, colour: int = 0) -> int:
        return colour

    wrapped = accepts_aliases(old)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        assert wrapped(color=3) == 3


def test_export_module_aliases() -> None:
    class Thing:
        pass

    namespace: dict[str, Any] = {"__all__": ("Thing", "Colour"), "Thing": Thing}
    namespace["Colour"] = Colour
    export_module_aliases(namespace)
    assert namespace["Color"] is Colour
    assert namespace["__all__"] == ("Thing", "Colour", "Color")


def test_export_module_aliases_is_idempotent() -> None:
    namespace: dict[str, Any] = {
        "__all__": ("Colour", "Color"),
        "Colour": Colour,
    }
    export_module_aliases(namespace)
    export_module_aliases(namespace)
    assert namespace["__all__"] == ("Colour", "Color")
    assert namespace["Color"] is Colour


def _alias_mixin_subclasses() -> list[type]:
    found: dict[type, None] = {}
    stack = [AliasMixin]
    while stack:
        for sub in stack.pop().__subclasses__():
            if sub not in found:
                found[sub] = None
                stack.append(sub)
    return [
        cls
        for cls in found
        if cls.__module__.startswith("discord") and cls.__module__ != "tests"
    ]


def _library_classes() -> list[type]:
    classes: dict[type, None] = {}
    for namespace in NAMESPACES:
        for value in vars(namespace).values():
            if inspect.isclass(value) and value.__module__.startswith("discord"):
                classes[value] = None
    for cls in _alias_mixin_subclasses():
        classes[cls] = None
    return list(classes)


LIBRARY_CLASSES = _library_classes()
MIXIN_CLASSES = _alias_mixin_subclasses()


def _public_names(cls: type) -> list[str]:
    names = [name for name in vars(cls) if not name.startswith("_")]
    names += [name for name in inspect.get_annotations(cls) if not name.startswith("_")]
    return names


def test_discovery_found_the_migrated_sites() -> None:
    names = {cls.__qualname__ for cls in MIXIN_CLASSES}
    assert {
        "Colour",
        "Embed",
        "Container",
        "Role",
        "Guild",
        "Reaction",
        "RawReactionActionEvent",
        "RawReactionClearEmojiEvent",
        "Integration",
        "StreamIntegration",
        "BaseUser",
        "User",
        "ClientUser",
        "Member",
        "Spotify",
        "AuditLogDiff",
    } <= names


@pytest.mark.parametrize("cls", LIBRARY_CLASSES, ids=lambda cls: cls.__qualname__)
def test_every_spelling_has_an_alias(cls: type) -> None:
    for name in _public_names(cls):
        alias = alias_of(name)
        if alias is not None:
            assert hasattr(cls, alias), f"{cls.__qualname__}.{alias} is missing"


@pytest.mark.parametrize("cls", MIXIN_CLASSES, ids=lambda cls: cls.__qualname__)
def test_functions_with_a_spelling_parameter_accept_aliases(cls: type) -> None:
    for name, value in vars(cls).items():
        function = getattr(value, "__func__", value)
        if not inspect.isfunction(function):
            continue
        target: Any = function
        while hasattr(target, "__wrapped__"):
            target = target.__wrapped__
        code = target.__code__
        parameters = code.co_varnames[: code.co_argcount + code.co_kwonlyargcount]
        if any(alias_of(parameter) for parameter in parameters):
            assert getattr(function, "__accepts_aliases__", False), (
                f"{cls.__qualname__}.{name} does not accept aliases"
            )


def test_colour_factories_have_equal_gray_aliases() -> None:
    for name in dir(Colour):
        alias = alias_of(name)
        if alias is None or name.startswith("_"):
            continue
        assert getattr(Colour, alias)() == getattr(Colour, name)()


def _type_checking_declarations(class_node: ast.ClassDef) -> dict[str, ast.stmt]:
    declared: dict[str, ast.stmt] = {}
    for node in class_node.body:
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            for child in node.body:
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name):
                            declared[target.id] = child
                elif isinstance(child, ast.AnnAssign) and isinstance(
                    child.target, ast.Name
                ):
                    declared[child.target.id] = child
    return declared


def _is_type_checking(node: ast.expr) -> bool:
    return (isinstance(node, ast.Name) and node.id == "TYPE_CHECKING") or (
        isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING"
    )


def _class_node(module: types.ModuleType, cls: type) -> ast.ClassDef:
    source = inspect.getsource(module)
    tree = ast.parse(source)
    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == cls.__name__
    ]
    assert len(matches) == 1, f"{cls.__qualname__} is not unique in {module.__name__}"
    return matches[0]


def _explicit_names(class_node: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for node in class_node.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


@pytest.mark.parametrize("cls", MIXIN_CLASSES, ids=lambda cls: cls.__qualname__)
def test_generated_aliases_are_declared_for_type_checkers(cls: type) -> None:
    module = sys.modules[cls.__module__]
    class_node = _class_node(module, cls)
    declared = _type_checking_declarations(class_node)
    explicit = _explicit_names(class_node)
    own = [name for name in _public_names(cls) if name not in declared]

    for name in own:
        alias = alias_of(name)
        if alias is None or alias in explicit:
            continue
        assert alias in declared, (
            f"{cls.__qualname__}.{alias} is generated at runtime but not declared "
            "in an `if TYPE_CHECKING:` block"
        )

    for alias, statement in declared.items():
        canonical = canonical_of(alias)
        if canonical is None:
            continue
        if isinstance(statement, ast.Assign):
            assert isinstance(statement.value, ast.Name)
            assert statement.value.id == canonical
            assert alias in vars(cls), f"{cls.__qualname__}.{alias} is not generated"
        else:
            assert (
                canonical in _public_names(cls)
                or canonical in declared
                or canonical in explicit
            )


@pytest.mark.parametrize("module_name", ALIAS_MODULES)
def test_module_aliases_are_declared_and_exported(module_name: str) -> None:
    module = importlib.import_module(module_name)
    tree = ast.parse(inspect.getsource(module))

    source_all: tuple[str, ...] = ()
    declared: dict[str, str] = {}
    calls_export = False
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            source_all = tuple(ast.literal_eval(node.value))
        elif isinstance(node, ast.If) and _is_type_checking(node.test):
            for child in node.body:
                if (
                    isinstance(child, ast.Assign)
                    and isinstance(child.targets[0], ast.Name)
                    and isinstance(child.value, ast.Name)
                ):
                    declared[child.targets[0].id] = child.value.id
        elif (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "export_module_aliases"
        ):
            calls_export = True

    assert calls_export
    canonicals = [name for name in source_all if alias_of(name)]
    assert canonicals
    for name in canonicals:
        alias = alias_of(name)
        assert alias in source_all
        assert declared.get(alias) == name
        assert getattr(module, alias) is getattr(module, name)
    for alias, canonical in declared.items():
        assert alias_of(canonical) == alias
        assert canonical in canonicals


def test_module_aliases_are_importable() -> None:
    assert Color is Colour
    assert ExpireBehavior is ExpireBehaviour
    assert ColorConverter is commands.ColourConverter
    assert BadColorArgument is commands.BadColourArgument
    assert "Color" in discord.colour.__all__
    assert "ExpireBehavior" in discord.enums.__all__
    assert "ColorConverter" in commands.converter.__all__
    assert "BadColorArgument" in commands.errors.__all__


def test_button_style_enum_alias_is_unchanged() -> None:
    assert discord.ButtonStyle.grey is discord.ButtonStyle.gray


def test_colour_classmethods() -> None:
    assert Colour.lighter_gray() == Colour.lighter_grey() == Colour(0x95A5A6)
    assert Colour.dark_gray() == Colour.dark_grey() == Colour(0x607D8B)
    assert Colour.light_gray() == Colour.light_grey() == Colour(0x979C9F)
    assert Colour.darker_gray() == Colour.darker_grey() == Colour(0x546E7A)
    assert Colour.grayple() == Colour.greyple()
    assert discord.Color.dark_gray() == Colour(0x607D8B)
    assert isinstance(discord.Color.light_gray(), discord.Color)


def test_embed_colour_aliases() -> None:
    assert Embed(color=1).colour == Colour(1)
    assert Embed(colour=2).color == Colour(2)
    assert Embed(color=0).colour == Colour(0)
    assert Embed().colour is None
    embed = Embed()
    embed.color = 5
    assert embed.colour == Colour(5)
    assert embed.to_dict()["color"] == 5
    assert Embed.from_dict(embed.to_dict()).color == Colour(5)


def test_embed_conflict_raises() -> None:
    with pytest.raises(TypeError, match=r"Embed\.__init__\(\) got values for both"):
        Embed(colour=1, color=2)


def test_embed_signature_still_declares_both_spellings() -> None:
    parameters = inspect.signature(Embed.__init__).parameters
    assert "colour" in parameters
    assert "color" in parameters


def test_container_colour_aliases() -> None:
    assert ui.Container(color=3).colour == Colour(3)
    assert ui.Container(colour=4).color == Colour(4)
    container = ui.Container()
    container.color = 6
    assert container.colour == Colour(6)


def test_container_zero_colour_does_not_fall_back_to_alias() -> None:
    assert ui.Container(colour=0).colour == Colour(0)
    assert ui.Container(colour=0, color=None).colour == Colour(0)
    assert ui.Container(color=0).colour == Colour(0)
    assert ui.Container(colour=0).to_component_dict()["accent_color"] == 0


def test_container_conflict_raises() -> None:
    with pytest.raises(TypeError, match="got values for both 'colour'"):
        ui.Container(colour=1, color=2)


def test_container_subclass_keeps_aliases() -> None:
    class Custom(ui.Container):
        def __init__(self, *, colour: int | None = None, color: int | None = None):
            del color
            super().__init__(colour=colour)

    assert Custom(color=5).colour == Colour(5)


def _role_payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "10",
        "name": "role",
        "permissions": "0",
        "position": 1,
        "color": 0,
        "colors": {
            "primary_color": 0x112233,
            "secondary_color": None,
            "tertiary_color": None,
        },
        "hoist": False,
        "managed": False,
        "mentionable": False,
    }
    data.update(overrides)
    return data


def _make_role() -> Role:
    state = MagicMock()
    state.http.edit_role = AsyncMock(return_value=_role_payload())
    guild = SimpleNamespace(id=1, features=["ENHANCED_ROLE_COLORS"])
    state._get_guild = AsyncMock(return_value=guild)
    return Role(guild=guild, state=state, data=_role_payload())  # type: ignore[arg-type]


def test_role_colour_properties_and_deprecation_messages() -> None:
    role = _make_role()
    assert role.colors is role.colours
    assert role.colours.primary == Colour(0x112233)

    with pytest.warns(
        DeprecationWarning,
        match=(
            r"Role\.colour is deprecated since version 2\.7, "
            r"consider using colours\.primary instead\."
        ),
    ):
        assert role.colour == Colour(0x112233)
    with pytest.warns(
        DeprecationWarning,
        match=(
            r"Role\.color is deprecated since version 2\.7, "
            r"consider using colors\.primary instead\."
        ),
    ):
        assert role.color == Colour(0x112233)


@pytest.mark.parametrize(
    "kwargs",
    [{"colour": 5}, {"color": 5}, {"colour": Colour(5)}, {"color": Colour(5)}],
)
def test_role_edit_colour_spellings(kwargs: dict[str, Any]) -> None:
    role = _make_role()
    with pytest.warns(DeprecationWarning, match="colour is deprecated"):
        run(role.edit(**kwargs))
    role._state.http.edit_role.assert_awaited_once()
    payload = role._state.http.edit_role.await_args.kwargs
    assert payload["colors"] == RoleColours(primary=Colour(5))._to_dict()


@pytest.mark.parametrize("keyword", ["colours", "colors"])
def test_role_edit_colours_spellings(keyword: str) -> None:
    role = _make_role()
    colours = RoleColours(primary=Colour(1), secondary=Colour(2))
    run(role.edit(**{keyword: colours}))
    payload = role._state.http.edit_role.await_args.kwargs
    assert payload["colors"] == colours._to_dict()


def test_role_edit_conflict_raises() -> None:
    role = _make_role()
    with pytest.raises(TypeError, match="got values for both 'colour'"):
        run(role.edit(colour=1, color=2))
    with pytest.raises(TypeError, match="got values for both 'colours'"):
        run(role.edit(colours=RoleColours.default(), colors=RoleColours.default()))
    role._state.http.edit_role.assert_not_called()


def _fake_guild() -> Any:
    state = MagicMock()
    state.http.create_role = AsyncMock(return_value=_role_payload())
    return SimpleNamespace(id=1, features=["ENHANCED_ROLE_COLORS"], _state=state)


@pytest.mark.parametrize(
    "kwargs", [{"colour": 5}, {"color": 5}, {"colour": Colour(5)}, {"color": Colour(5)}]
)
def test_guild_create_role_colour_spellings(kwargs: dict[str, Any]) -> None:
    guild = _fake_guild()
    with pytest.warns(DeprecationWarning, match="colour is deprecated"):
        run(Guild.create_role(guild, **kwargs))
    payload = guild._state.http.create_role.await_args.kwargs
    assert payload["colors"] == RoleColours(primary=Colour(5))._to_dict()


@pytest.mark.parametrize("keyword", ["colours", "colors"])
def test_guild_create_role_colours_spellings(keyword: str) -> None:
    guild = _fake_guild()
    colours = RoleColours(primary=Colour(1), secondary=Colour(2))
    run(Guild.create_role(guild, **{keyword: colours}))
    payload = guild._state.http.create_role.await_args.kwargs
    assert payload["colors"] == colours._to_dict()


def test_guild_create_role_defaults_and_conflict() -> None:
    guild = _fake_guild()
    run(Guild.create_role(guild, name="x"))
    payload = guild._state.http.create_role.await_args.kwargs
    assert payload["colors"] == RoleColours.default()._to_dict()
    assert payload["name"] == "x"
    with pytest.raises(TypeError, match="got values for both 'colour'"):
        run(Guild.create_role(guild, colour=1, color=2))


def test_reaction_burst_colors() -> None:
    reaction = object.__new__(Reaction)
    reaction._burst_colours = ["#ffffff", "#000001"]
    assert reaction.burst_colours == [Colour(0xFFFFFF), Colour(1)]
    assert reaction.burst_colors == reaction.burst_colours
    assert Reaction.burst_colors is Reaction.burst_colours


def test_raw_reaction_events_burst_colors() -> None:
    emoji = MagicMock()
    data: dict[str, Any] = {
        "message_id": "1",
        "channel_id": "2",
        "user_id": "3",
        "burst_colors": ["#fff"],
    }
    action = RawReactionActionEvent(data, emoji, "REACTION_ADD")  # type: ignore[arg-type]
    assert action.burst_colours == ["#fff"]
    assert action.burst_colors is action.burst_colours
    action.burst_colors = ["#000"]
    assert action.burst_colours == ["#000"]
    assert "burst_colors" not in type(action).__slots__
    assert "burst_colors=" not in repr(action)

    cleared = RawReactionClearEmojiEvent(
        {"message_id": "1", "channel_id": "2", "emoji": {"id": None, "name": "x"}},
        emoji,
    )
    assert cleared.burst is False
    assert cleared.burst_colours == []
    assert cleared.burst_colors is cleared.burst_colours
    assert "burst_colors" not in type(cleared).__slots__
    assert "burst_colors=" not in repr(cleared)


def _stream_integration() -> StreamIntegration:
    integration = object.__new__(StreamIntegration)
    integration.expire_behaviour = ExpireBehaviour.kick
    return integration


def test_integration_expire_behavior_slot_alias() -> None:
    integration = _stream_integration()
    assert integration.expire_behavior is ExpireBehaviour.kick
    integration.expire_behavior = ExpireBehaviour.remove_role
    assert integration.expire_behaviour is ExpireBehaviour.remove_role


@pytest.mark.parametrize("keyword", ["expire_behaviour", "expire_behavior"])
def test_integration_edit_accepts_both_spellings(keyword: str) -> None:
    http = SimpleNamespace(edit_integration=AsyncMock())
    integration = SimpleNamespace(
        guild=SimpleNamespace(id=1), id=2, _state=SimpleNamespace(http=http)
    )
    run(
        StreamIntegration.edit(integration, **{keyword: ExpireBehaviour.kick})  # type: ignore[arg-type]
    )
    http.edit_integration.assert_awaited_once_with(1, 2, expire_behavior=1)


def test_integration_edit_conflict_raises() -> None:
    with pytest.raises(TypeError, match="got values for both 'expire_behaviour'"):
        run(
            StreamIntegration.edit(  # type: ignore[arg-type]
                SimpleNamespace(),
                expire_behaviour=ExpireBehaviour.kick,
                expire_behavior=ExpireBehaviour.remove_role,
            )
        )


def test_user_colour_aliases() -> None:
    user = object.__new__(discord.User)
    user._accent_colour = 0x123456
    assert user.accent_colour == Colour(0x123456)
    assert user.accent_color == user.accent_colour
    assert user.colour == user.color == Colour.default()
    user._accent_colour = None
    assert user.accent_color is None
    assert discord.ClientUser.color is discord.ClientUser.colour


def test_member_colour_aliases_share_properties() -> None:
    assert discord.Member.color is discord.Member.colour
    assert discord.Member.colors is discord.Member.colours
    assert discord.Member.get_color is discord.Member.get_colour
    assert discord.Member.get_colors is discord.Member.get_colours


def test_spotify_colour_alias() -> None:
    spotify = object.__new__(discord.Spotify)
    assert spotify.color == spotify.colour == Colour(0x1DB954)


def test_audit_log_diff_resolves_spellings() -> None:
    diff = AuditLogDiff()
    diff.colour = Colour(1)  # type: ignore[attr-defined]
    diff.expire_behavior = ExpireBehaviour.kick  # type: ignore[attr-defined]
    diff.name = "x"  # type: ignore[attr-defined]
    assert diff.color == Colour(1)  # type: ignore[attr-defined]
    assert diff.colour == Colour(1)  # type: ignore[attr-defined]
    assert diff.expire_behaviour is ExpireBehaviour.kick  # type: ignore[attr-defined]
    assert hasattr(diff, "color")
    assert not hasattr(diff, "unknown")
    assert not hasattr(diff, "grey")
    assert dict(iter(diff)) == {
        "colour": Colour(1),
        "expire_behavior": ExpireBehaviour.kick,
        "name": "x",
    }
    assert len(diff) == 3


def test_audit_log_diff_without_the_attribute_raises() -> None:
    diff = AuditLogDiff()
    with pytest.raises(AttributeError):
        _ = diff.color  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        _ = diff.__deepcopy__  # type: ignore[attr-defined]
