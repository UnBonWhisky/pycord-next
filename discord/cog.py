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
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
import inspect
import pathlib
import sys
import types
from collections.abc import Callable, Generator, Mapping
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    TypeGuard,
    TypeVar,
    cast,
    overload,
)

from typing_extensions import TypeIs

import discord.utils

from . import errors
from .commands import (
    ApplicationCommand,
    SlashCommand,
    SlashCommandGroup,
    _BaseCommand,
)
from .commands.core import _is_str, _mark_callback
from .commands.registry import declared_parent

if TYPE_CHECKING:
    from typing_extensions import Self

    from .commands.context import BaseContext
    from .ext.bridge import BridgeCommand
    from .ext.commands.core import Command

    CogCommand = ApplicationCommand | Command[Any, ..., Any] | BridgeCommand


__all__ = (
    "Cog",
    "CogMeta",
    "CogMixin",
)

CogT = TypeVar("CogT", bound="Cog")
FuncT = TypeVar("FuncT", bound=Callable[..., Any])

MISSING: Any = discord.utils.MISSING


def _is_submodule(parent: str, child: str) -> bool:
    return parent == child or child.startswith(f"{parent}.")


def _is_bridge_command(command: object) -> TypeIs[BridgeCommand]:
    return getattr(command, "__bridge__", False)


def _is_group_member(
    value: object,
) -> TypeGuard[SlashCommand[Any, ..., Any] | SlashCommandGroup]:
    return bool(getattr(value, "parent", None)) and isinstance(
        value, ApplicationCommand
    )


def _name_filter(c: object) -> str:
    return (
        "app"
        if isinstance(c, ApplicationCommand)
        else ("bridge" if not _is_bridge_command(c) else "ext")
    )


def _validate_name_prefix(base_class: type, name: str) -> None:
    if name.startswith(("cog_", "bot_")):
        raise TypeError(
            f"Commands or listeners must not start with cog_ or bot_ (in method {base_class}.{name})"
        )


def _process_attributes(
    base: type,
) -> tuple[
    dict[str, _BaseCommand | BridgeCommand],
    dict[str, Callable[..., Any]],
    dict[str, SlashCommand[Any, ..., Any] | SlashCommandGroup],
    dict[str, BridgeCommand],
]:
    commands: dict[str, _BaseCommand | BridgeCommand] = {}
    listeners: dict[str, Callable[..., Any]] = {}
    members: dict[str, SlashCommand[Any, ..., Any] | SlashCommandGroup] = {}
    bridge_members: dict[str, BridgeCommand] = {}

    for attr_name, raw_value in base.__dict__.items():
        attr_value: object = raw_value
        commands.pop(attr_name, None)
        listeners.pop(attr_name, None)
        members.pop(attr_name, None)
        if attr_name in bridge_members:
            del bridge_members[attr_name]
            members.pop(f"app_{attr_name}", None)

        if _is_group_member(attr_value):
            members[attr_name] = attr_value
            continue

        if _is_bridge_command(attr_value) and attr_value.parent:
            bridge_members[attr_name] = attr_value
            members[f"app_{attr_name}"] = attr_value.slash_variant
            continue

        is_static_method = isinstance(attr_value, staticmethod)
        if is_static_method:
            attr_value = _unwrap_static(attr_value)

        if inspect.iscoroutinefunction(attr_value) and getattr(
            attr_value, "__cog_listener__", False
        ):
            _validate_name_prefix(base, attr_name)
            listeners[attr_name] = cast("Callable[..., Any]", attr_value)
            continue

        if isinstance(attr_value, _BaseCommand) or _is_bridge_command(attr_value):
            if is_static_method:
                raise TypeError(
                    f"Command in method {base}.{attr_name!r} must not be staticmethod."
                )
            _validate_name_prefix(base, attr_name)

        if isinstance(attr_value, _BaseCommand):
            commands[attr_name] = attr_value

        if _is_bridge_command(attr_value) and not attr_value.parent:
            commands[f"ext_{attr_name}"] = attr_value.ext_variant
            commands[f"app_{attr_name}"] = attr_value.slash_variant
            commands[attr_name] = attr_value
            for cmd in getattr(attr_value, "walk_commands", tuple)():
                commands[f"ext_{cmd.ext_variant.qualified_name}"] = cmd.ext_variant

    return commands, listeners, members, bridge_members


def _update_command(
    command: CogCommand,
    guild_ids: list[int],
    lookup_table: dict[str, CogCommand],
    new_cls: type[Cog],
) -> None:
    if isinstance(command, ApplicationCommand) and not command.guild_ids and guild_ids:
        command.guild_ids = guild_ids

    if not isinstance(command, SlashCommandGroup) and not _is_bridge_command(command):
        # ignore bridge commands
        callback_name: str = command.callback.__name__
        cmd: object = getattr(new_cls, callback_name, None)
        if _is_bridge_command(cmd):
            setattr(
                cmd,
                f"{_name_filter(command).replace('app', 'slash')}_variant",
                command,
            )
        else:
            setattr(new_cls, callback_name, command)

        parent: Any = command.parent
        if parent is not None:
            # Get the latest parent reference
            parent = lookup_table[f"{_name_filter(command)}_{parent.qualified_name}"]

            # Update the parent's reference to our self
            parent.remove_command(command.name)
            parent.add_command(command)


class CogMeta(type):
    """A metaclass for defining a cog.

    Note that you should probably not use this directly. It is exposed
    purely for documentation purposes along with making custom metaclasses to intermix
    with other metaclasses such as the :class:`abc.ABCMeta` metaclass.

    For example, to create an abstract cog mixin class, the following would be done.

    .. code-block:: python3

        import abc


        class CogABCMeta(discord.CogMeta, abc.ABCMeta):
            pass


        class SomeMixin(metaclass=abc.ABCMeta):
            pass


        class SomeCogMixin(SomeMixin, discord.Cog, metaclass=CogABCMeta):
            pass

    .. note::

        When passing an attribute of a metaclass that is documented below, note
        that you must pass it as a keyword-only argument to the class creation
        like the following example:

        .. code-block:: python3

            class MyCog(discord.Cog, name="My Cog"):
                pass

    Attributes
    ----------
    name: :class:`str`
        The cog name. By default, it is the name of the class with no modification.
    description: :class:`str`
        The cog description. By default, it is the cleaned docstring of the class.

        .. versionadded:: 1.6

    command_attrs: :class:`dict`
        A list of attributes to apply to every command inside this cog. The dictionary
        is passed into the :class:`Command` options at ``__init__``.
        If you specify attributes inside the command attribute in the class, it will
        override the one specified inside this attribute. For example:

        .. code-block:: python3

            class MyCog(discord.Cog, command_attrs=dict(hidden=True)):
                @discord.slash_command()
                async def foo(self, ctx):
                    pass  # hidden -> True

                @discord.slash_command(hidden=False)
                async def bar(self, ctx):
                    pass  # hidden -> False

    guild_ids: Optional[List[:class:`int`]]
        A shortcut to :attr:`.command_attrs`, what ``guild_ids`` should all application commands have
        in the cog. You can override this by setting ``guild_ids`` per command.

        .. versionadded:: 2.0
    """

    __cog_name__: str
    __cog_settings__: dict[str, Any]
    __cog_commands__: list[CogCommand]
    __cog_listeners__: list[tuple[str, str]]
    __cog_guild_ids__: list[int]
    __cog_group_members__: list[SlashCommand[Any, ..., Any] | SlashCommandGroup]
    __cog_ext_members__: list[Command[Any, ..., Any]]
    __cog_group_copies__: list[tuple[SlashCommandGroup, SlashCommandGroup]]

    def __new__(cls: type[CogMeta], *args: Any, **kwargs: Any) -> CogMeta:
        """Creates the cog class and collects its commands, listeners and groups."""
        name, bases, attrs = args
        attrs["__cog_name__"] = kwargs.pop("name", name)
        attrs["__cog_settings__"] = kwargs.pop("command_attrs", {})
        attrs["__cog_guild_ids__"] = kwargs.pop("guild_ids", [])

        description = kwargs.pop("description", None)
        if description is None:
            description = inspect.cleandoc(attrs.get("__doc__", ""))
        attrs["__cog_description__"] = description

        commands: dict[str, _BaseCommand | BridgeCommand] = {}
        listeners: dict[str, Callable[..., Any]] = {}
        members: dict[str, SlashCommand | SlashCommandGroup] = {}
        bridge_members: dict[str, BridgeCommand] = {}

        new_cls = super().__new__(cls, name, bases, attrs, **kwargs)
        cog_cls = cast("type[Cog]", new_cls)

        for base in reversed(new_cls.__mro__):
            new_commands, new_listeners, new_members, new_bridge_members = (
                _process_attributes(base)
            )
            commands.update(new_commands)
            listeners.update(new_listeners)
            members.update(new_members)
            bridge_members.update(new_bridge_members)

        new_cls.__cog_commands__ = cast("list[CogCommand]", list(commands.values()))

        collected = {id(c) for c in new_cls.__cog_commands__}
        new_cls.__cog_ext_members__ = [
            b.ext_variant
            for b in bridge_members.values()
            if id(b.ext_variant) not in collected
        ]
        for ext_member in new_cls.__cog_ext_members__:
            if ext_member.parent is not None:
                ext_member.parent.remove_command(ext_member.name)

        new_cls.__cog_group_members__ = list(members.values())
        for member in new_cls.__cog_group_members__:
            declared_parent(member)
            if member._cog_class is None:
                member._cog_class = cog_cls

        new_cls.__cog_listeners__ = [
            (listener_name, listener.__name__)
            for listener in listeners.values()
            for listener_name in _listener_names(listener)
        ]

        cmd_attrs = new_cls.__cog_settings__

        # Either update the command with the cog provided defaults or copy it.
        originals = new_cls.__cog_commands__
        new_cls.__cog_commands__ = [
            c if _is_bridge_command(c) else c._update_copy(cmd_attrs)
            for c in new_cls.__cog_commands__
        ]

        new_cls.__cog_group_copies__ = []
        for original, copy in zip(originals, new_cls.__cog_commands__, strict=True):
            if isinstance(copy, SlashCommandGroup):
                copy.subcommands = [c for c in copy.subcommands if c._cog_class is None]
                new_cls.__cog_group_copies__.append(
                    (cast("SlashCommandGroup", original), copy)
                )

        lookup = {
            f"{_name_filter(cmd)}_{cmd.qualified_name}": cmd
            for cmd in new_cls.__cog_commands__
        }

        # Update the Command instances dynamically as well
        for command in new_cls.__cog_commands__:
            _update_command(command, new_cls.__cog_guild_ids__, lookup, cog_cls)

        return new_cls

    def __init__(cls, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args)

    @classmethod
    def qualified_name(cls) -> str:
        """The name of the cog class."""
        return cls.__cog_name__


def _listener_names(listener: Callable[..., Any]) -> list[str]:
    return cast("list[str]", getattr(listener, "__cog_listener_names__", []))


def _is_cog(value: object) -> bool:
    return isinstance(value, Cog)


def _unwrap_static(func: object) -> Callable[..., Any]:
    if isinstance(func, staticmethod):
        return cast("Callable[..., Any]", func.__func__)
    return cast("Callable[..., Any]", func)


def _cog_special_method(func: FuncT) -> FuncT:
    _mark_callback(func, "__cog_special_method__", None)
    return func


class Cog(metaclass=CogMeta):
    """The base class that all cogs must inherit from.

    A cog is a collection of commands, listeners, and optional state to
    help group commands together. More information on them can be found on
    the :ref:`ext_commands_cogs` page.

    When inheriting from this class, the options shown in :class:`CogMeta`
    are equally valid here.
    """

    __cog_name__: ClassVar[str]
    __cog_settings__: ClassVar[dict[str, Any]]
    __cog_commands__: ClassVar[list[CogCommand]]
    __cog_listeners__: ClassVar[list[tuple[str, str]]]
    __cog_guild_ids__: ClassVar[list[int]]
    __cog_group_members__: ClassVar[list[SlashCommand | SlashCommandGroup]]
    __cog_ext_members__: ClassVar[list[Command[Any, ..., Any]]]
    __cog_attachment__: Any = None
    __cog_group_copies__: ClassVar[list[tuple[SlashCommandGroup, SlashCommandGroup]]]

    def get_commands(self) -> list[ApplicationCommand | Command[Any, ..., Any]]:
        r"""Returns the commands that are defined inside this cog.

        Returns
        -------
        List[Union[:class:`~discord.ApplicationCommand`, :class:`.Command`]]
            A :class:`list` of commands that are defined inside this cog.

            .. note::

                This does not include subcommands.
        """
        return cast(
            "list[ApplicationCommand | Command[Any, ..., Any]]",
            [c for c in self.__cog_commands__ if c.parent is None],
        )

    @property
    def qualified_name(self) -> str:
        """Returns the cog's specified name, not the class name."""
        return self.__cog_name__

    @property
    def description(self) -> str:
        """Returns the cog's description, typically the cleaned docstring."""
        return self.__cog_description__

    @description.setter
    def description(self, description: str) -> None:
        self.__cog_description__ = description

    def walk_commands(self) -> Generator[ApplicationCommand | Command[Any, ..., Any]]:
        """An iterator that recursively walks through this cog's commands and subcommands.

        Yields
        ------
        Union[:class:`.Command`, :class:`.Group`]
            A command or group from the cog.
        """
        from .ext.commands.core import GroupMixin

        seen: set[int] = set()
        for command in self.__cog_commands__:
            if isinstance(command, SlashCommandGroup):
                for child in command.walk_commands():
                    seen.add(id(child))
                    yield child
            elif isinstance(command, ApplicationCommand):
                yield command
            elif command.parent is None:
                yield cast("Command[Any, ..., Any]", command)
                if isinstance(command, GroupMixin):
                    yield from command.walk_commands()

        for member in self.__cog_group_members__:
            if id(member) not in seen:
                yield member

    def get_listeners(self) -> list[tuple[str, Callable[..., Any]]]:
        """Returns a :class:`list` of (name, function) listener pairs that are defined in this cog.

        Returns
        -------
        List[Tuple[:class:`str`, :ref:`coroutine <coroutine>`]]
            The listeners defined in this cog.
        """
        return [
            (name, getattr(self, method_name))
            for name, method_name in self.__cog_listeners__
        ]

    @classmethod
    def _get_overridden_method(cls, method: FuncT) -> FuncT | None:
        """Return None if the method is not overridden. Otherwise, returns the overridden method."""
        return getattr(
            getattr(method, "__func__", method), "__cog_special_method__", method
        )

    @classmethod
    def listener(
        cls, name: str = MISSING, once: bool = False
    ) -> Callable[[FuncT], FuncT]:
        """A decorator that marks a function as a listener.

        This is the cog equivalent of :meth:`.Bot.listen`.

        Parameters
        ----------
        name: :class:`str`
            The name of the event being listened to. If not provided, it
            defaults to the function's name.
        once: :class:`bool`
            If this listener should only be called once after each cog load.
            Defaults to false.

        Raises
        ------
        TypeError
            The function is not a coroutine function or a string was not passed as
            the name.
        """
        if name is not MISSING and not _is_str(name):
            raise TypeError(
                "Cog.listener expected str but received"
                f" {name.__class__.__name__!r} instead."
            )

        def decorator(func: FuncT) -> FuncT:
            actual = _unwrap_static(func)
            if not inspect.iscoroutinefunction(actual):
                raise TypeError("Listener function must be a coroutine function.")
            _mark_callback(actual, "__cog_listener__", True)
            to_assign = name or actual.__name__
            _mark_callback(actual, "_once", once)
            names: list[str] | None = getattr(actual, "__cog_listener_names__", None)
            if names is None:
                _mark_callback(actual, "__cog_listener_names__", [to_assign])
            else:
                names.append(to_assign)
            # we have to return `func` instead of `actual` because
            # we need the type to be `staticmethod` for the metaclass
            # to pick it up but the metaclass unfurls the function and
            # thus the assignments need to be on the actual function
            return func

        return decorator

    def has_error_handler(self) -> bool:
        """Checks whether the cog has an error handler.

        .. versionadded:: 1.7
        """
        return not hasattr(self.cog_command_error.__func__, "__cog_special_method__")

    @_cog_special_method
    def cog_unload(self) -> None:
        """A special method that is called when the cog gets removed.

        This function **cannot** be a coroutine. It must be a regular
        function.

        Subclasses must replace this if they want special unloading behaviour.
        """

    @_cog_special_method
    def bot_check_once(self, ctx: BaseContext) -> bool:
        """A special method that registers as a :meth:`.Bot.check_once` check.

        This function **can** be a coroutine and must take a sole parameter,
        ``ctx``, to represent the :class:`.Context` or :class:`.ApplicationContext`.

        Parameters
        ----------
        ctx: Union[:class:`.Context`, :class:`.ApplicationContext`]
            The invocation context.
        """
        return True

    @_cog_special_method
    def bot_check(self, ctx: BaseContext) -> bool:
        """A special method that registers as a :meth:`.Bot.check` check.

        This function **can** be a coroutine and must take a sole parameter,
        ``ctx``, to represent the :class:`.Context` or :class:`.ApplicationContext`.

        Parameters
        ----------
        ctx: Union[:class:`.Context`, :class:`.ApplicationContext`]
            The invocation context.
        """
        return True

    @_cog_special_method
    def cog_check(self, ctx: BaseContext) -> bool:
        """A special method that registers as a :func:`~discord.ext.commands.check` for every command and subcommand in this cog.

        This function **can** be a coroutine and must take a sole parameter,
        ``ctx``, to represent the :class:`.Context` or :class:`.ApplicationContext`.

        Parameters
        ----------
        ctx: Union[:class:`.Context`, :class:`.ApplicationContext`]
            The invocation context.
        """
        return True

    @_cog_special_method
    async def cog_command_error(self, ctx: BaseContext, error: Exception) -> None:
        """A special method that is called whenever an error is dispatched inside this cog.

        This is similar to :func:`.on_command_error` except only applying
        to the commands inside this cog.

        This **must** be a coroutine.

        Parameters
        ----------
        ctx: Union[:class:`.Context`, :class:`.ApplicationContext`]
            The invocation context where the error happened.
        error: :class:`ApplicationCommandError`
            The error that happened.
        """

    @_cog_special_method
    async def cog_before_invoke(self, ctx: BaseContext) -> None:
        """A special method that acts as a cog local pre-invoke hook.

        This is similar to :meth:`.ApplicationCommand.before_invoke`.

        This **must** be a coroutine.

        .. versionchanged:: 3.0

            When this cog owns a :class:`.SlashCommandGroup` shared with other cogs, this hook also runs
            before the commands of the other cogs, before their own ``cog_before_invoke``.

        Parameters
        ----------
        ctx: Union[:class:`.Context`, :class:`.ApplicationContext`]
            The invocation context.
        """

    @_cog_special_method
    async def cog_after_invoke(self, ctx: BaseContext) -> None:
        """A special method that acts as a cog local post-invoke hook.

        This is similar to :meth:`.ApplicationCommand.after_invoke`.

        This **must** be a coroutine.

        .. versionchanged:: 3.0

            When this cog owns a :class:`.SlashCommandGroup` shared with other cogs, this hook also runs
            after the commands of the other cogs, after their own ``cog_after_invoke``.

        Parameters
        ----------
        ctx: Union[:class:`.Context`, :class:`.ApplicationContext`]
            The invocation context.
        """

    def _inject(self, bot: Any) -> Self:
        cls = self.__class__

        # realistically, the only thing that can cause loading errors
        # is essentially just the command loading, which raises if there are
        # duplicates. When this condition is met, we want to undo all what
        # we've added so far for some form of atomic loading.

        for index, command in enumerate(self.__cog_commands__):
            if _is_bridge_command(command):
                bot.bridge_commands.append(command)
                continue

            command._set_cog(self)

            if isinstance(command, ApplicationCommand):
                if not isinstance(command, discord.SlashCommandGroup):
                    bot.add_application_command(command)

            elif command.parent is None:
                try:
                    bot.add_command(command)
                except Exception:
                    # undo our additions
                    for to_undo in self.__cog_commands__[:index]:
                        if to_undo.parent is None:
                            bot.remove_command(to_undo.name)
                    raise

        for member in cls.__cog_group_members__:
            member._set_cog(self)

        try:
            changed = bot._group_registry.attach(self)
            self._attach_ext_members(bot)
        except BaseException:
            self._detach_ext_members()
            bot._group_registry.detach(self)
            for member in cls.__cog_group_members__:
                if member.cog is self:
                    member._unset_cog()
            self._remove_commands(bot)
            raise

        if changed:
            bot._schedule_group_sync()

        # check if we're overriding the default
        if cls.bot_check is not Cog.bot_check:
            bot.add_check(self.bot_check)

        if cls.bot_check_once is not Cog.bot_check_once:
            bot.add_check(self.bot_check_once, call_once=True)

        # while Bot.add_listener can raise if it's not a coroutine,
        # this precondition is already met by the listener decorator
        # already, thus this should never raise.
        # Outside of, memory errors and the like...
        for name, method_name in self.__cog_listeners__:
            bot.add_listener(getattr(self, method_name), name)

        return self

    def _attach_ext_members(self, bot: Any) -> None:
        attached: list[tuple[Any, Any]] = []
        self.__cog_ext_attached__ = attached

        def ensure(group: Any) -> Any:
            if group.parent is None:
                return bot.get_command(group.name)
            parent = ensure(group.parent)
            if parent is None:
                return None
            existing = parent.get_command(group.name)
            if existing is not None:
                return existing
            parent.add_command(group)
            attached.append((parent, group))
            return group

        for member in type(self).__cog_ext_members__:
            member._set_cog(self)
            parent = ensure(member.parent)
            if parent is not None:
                parent.add_command(member)
                attached.append((parent, member))

    def _detach_ext_members(self) -> None:
        attached: list[tuple[Any, Any]] = getattr(self, "__cog_ext_attached__", [])
        self.__cog_ext_attached__ = []
        for parent, command in reversed(attached):
            if not getattr(command, "commands", None):
                parent.remove_command(command.name)
            if command.cog is self:
                command.cog = None
        for member in type(self).__cog_ext_members__:
            if member.cog is self:
                member.cog = None

    def _remove_commands(self, bot: Any) -> None:
        for command in self.__cog_commands__:
            if _is_bridge_command(command):
                if command in bot.bridge_commands:
                    bot.bridge_commands.remove(command)
            elif isinstance(command, ApplicationCommand):
                if not isinstance(command, discord.SlashCommandGroup):
                    bot.remove_application_command(command)
            elif command.parent is None:
                bot.remove_command(command.name)

    def _eject(self, bot: Any) -> None:
        cls = self.__class__

        try:
            self._remove_commands(bot)

            self._detach_ext_members()
            if bot._group_registry.detach(self):
                bot._schedule_group_sync()

            for _, method_name in self.__cog_listeners__:
                bot.remove_listener(getattr(self, method_name))

            if cls.bot_check is not Cog.bot_check:
                bot.remove_check(self.bot_check)

            if cls.bot_check_once is not Cog.bot_check_once:
                bot.remove_check(self.bot_check_once, call_once=True)
        finally:
            with contextlib.suppress(Exception):
                self.cog_unload()


class CogMixin:
    """The part of the bots that loads cogs and extensions."""

    if TYPE_CHECKING:
        # Provided by the other bases of the bots, they depend on the bot class.
        _help_command: Any
        _supports_prefixed_commands: Any
        prefixed_commands: Any
        _application_commands: Any
        _event_handlers: Any
        remove_command: Any
        remove_application_command: Any

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.__cogs: dict[str, Cog] = {}
        self.__extensions: dict[str, types.ModuleType] = {}

    def add_cog(self, cog: Cog, *, override: bool = False) -> None:
        """Adds a "cog" to the bot.

        A cog is a class that has its own event listeners and commands.

        .. versionchanged:: 2.0

            :exc:`.ClientException` is raised when a cog with the same name
            is already loaded.

        Parameters
        ----------
        cog: :class:`.Cog`
            The cog to register to the bot.
        override: :class:`bool`
            If a previously loaded cog with the same name should be ejected
            instead of raising an error.

            .. versionadded:: 2.0

        Raises
        ------
        TypeError
            The cog does not inherit from :class:`.Cog`.
        ApplicationCommandError
            An error happened during loading.
        ClientException
            A cog with the same name is already loaded.
        """
        if not _is_cog(cog):
            raise TypeError("cogs must derive from Cog")

        cog_name = cog.__cog_name__
        existing = self.__cogs.get(cog_name)

        if existing is not None:
            if not override:
                raise discord.ClientException(f"Cog named {cog_name!r} already loaded")
            self.remove_cog(cog_name)

        cog = cog._inject(self)
        self.__cogs[cog_name] = cog

    def get_cog(self, name: str) -> Cog | None:
        """Gets the cog instance requested.

        If the cog is not found, ``None`` is returned instead.

        Parameters
        ----------
        name: :class:`str`
            The name of the cog you are requesting.
            This is equivalent to the name passed via keyword
            argument in class creation or the class name if unspecified.

        Returns
        -------
        Optional[:class:`Cog`]
            The cog that was requested. If not found, returns ``None``.
        """
        return self.__cogs.get(name)

    def remove_cog(self, name: str) -> Cog | None:
        """Removes a cog from the bot and returns it.

        All registered commands and event listeners that the
        cog has registered will be removed as well.

        If no cog is found then this method has no effect.

        Parameters
        ----------
        name: :class:`str`
            The name of the cog to remove.

        Returns
        -------
        Optional[:class:`.Cog`]
             The cog that was removed. ``None`` if not found.
        """
        cog = self.__cogs.pop(name, None)
        if cog is None:
            return None

        if hasattr(self, "_help_command"):
            help_command = self._help_command
            if help_command and help_command.cog is cog:
                help_command.cog = None

        cog._eject(self)

        return cog

    @property
    def cogs(self) -> Mapping[str, Cog]:
        """A read-only mapping of cog name to cog."""
        return types.MappingProxyType(self.__cogs)

    # extensions

    def _remove_module_references(self, name: str) -> None:
        # find all references to the module
        # remove the cogs registered from the module
        for cog_name, cog in self.__cogs.copy().items():
            if _is_submodule(name, cog.__module__):
                self.remove_cog(cog_name)

        # remove all the commands from the module
        if self._supports_prefixed_commands:
            for cmd in self.prefixed_commands.copy().values():
                if cmd.module is not None and _is_submodule(name, cmd.module):
                    self.remove_command(cmd.name)
        for cmd in self._application_commands.copy().values():
            if cmd.module is not None and _is_submodule(name, cmd.module):
                self.remove_application_command(cmd)

        # remove all the listeners from the module
        for event_list in self._event_handlers.copy().values():
            remove = [
                index
                for index, event in enumerate(event_list)
                if event.__module__ is not None
                and _is_submodule(name, event.__module__)
            ]

            for index in reversed(remove):
                del event_list[index]

    def _call_module_finalizers(self, lib: types.ModuleType, key: str) -> None:
        try:
            func = getattr(lib, "teardown", None)
            if func is not None:
                with contextlib.suppress(Exception):
                    func(self)
        finally:
            self.__extensions.pop(key, None)
            sys.modules.pop(key, None)
            name = lib.__name__
            for module in list(sys.modules.keys()):
                if _is_submodule(name, module):
                    del sys.modules[module]

    def _load_from_module_spec(
        self, spec: importlib.machinery.ModuleSpec, key: str
    ) -> None:
        # the key must not be loaded yet
        lib = importlib.util.module_from_spec(spec)
        sys.modules[key] = lib
        try:
            cast("importlib.abc.Loader", spec.loader).exec_module(lib)
        except Exception as e:
            del sys.modules[key]
            raise errors.ExtensionFailed(key, e) from e

        try:
            setup = lib.setup
        except AttributeError:
            del sys.modules[key]
            raise errors.NoEntryPointError(key) from None

        try:
            setup(self)
        except Exception as e:
            del sys.modules[key]
            self._remove_module_references(lib.__name__)
            self._call_module_finalizers(lib, key)
            raise errors.ExtensionFailed(key, e) from e
        else:
            self.__extensions[key] = lib

    def _resolve_name(self, name: str, package: str | None) -> str:
        try:
            return importlib.util.resolve_name(name, package)
        except ImportError as exc:
            raise errors.ExtensionNotFound(name) from exc

    @overload
    def load_extension(
        self,
        name: str,
        *,
        package: str | None = None,
        recursive: bool = False,
    ) -> list[str]: ...

    @overload
    def load_extension(
        self,
        name: str,
        *,
        package: str | None = None,
        recursive: bool = False,
        store: bool = False,
    ) -> dict[str, Exception | bool] | list[str] | None: ...

    def load_extension(
        self,
        name: str,
        *,
        package: str | None = None,
        recursive: bool = False,
        store: bool = False,
    ) -> dict[str, Exception | bool] | list[str] | None:
        """Loads an extension.

        An extension is a python module that contains commands, cogs, or
        listeners.

        An extension must have a global function, ``setup`` defined as
        the entry point on what to do when the extension is loaded. This entry
        point must have a single argument, the ``bot``.

        The extension passed can either be the direct name of a file within
        the current working directory or a folder that contains multiple extensions.

        Parameters
        ----------
        name: :class:`str`
            The extension or folder name to load. It must be dot separated
            like regular Python imports if accessing a submodule. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when loading an extension using a relative
            path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7
        recursive: Optional[:class:`bool`]
            If subdirectories under the given head directory should be
            recursively loaded.
            Defaults to ``False``.

            .. versionadded:: 2.0
        store: Optional[:class:`bool`]
            If exceptions should be stored or raised. If set to ``True``,
            all exceptions encountered will be stored in a returned dictionary
            as a load status. If set to ``False``, if any exceptions are
            encountered they will be raised and the bot will be closed.
            If no exceptions are encountered, a list of loaded
            extension names will be returned.
            Defaults to ``False``.

            .. versionadded:: 2.0

        Returns
        -------
        Optional[Union[Dict[:class:`str`, Union[:exc:`errors.ExtensionError`, :class:`bool`]], List[:class:`str`]]]
            If the store parameter is set to ``True``, a dictionary will be returned that
            contains keys to represent the loaded extension names. The values bound to
            each key can either be an exception that occurred when loading that extension
            or a ``True`` boolean representing a successful load. If the store parameter
            is set to ``False``, either a list containing a list of loaded extensions or
            nothing due to an encountered exception.

        Raises
        ------
        ExtensionNotFound
            The extension could not be imported.
            This is also raised if the name of the extension could not
            be resolved using the provided ``package`` parameter.
        ExtensionAlreadyLoaded
            The extension is already loaded.
        NoEntryPointError
            The extension does not have a setup function.
        ExtensionFailed
            The extension or its setup function had an execution error.
        """
        name = self._resolve_name(name, package)

        final_out: dict[str, Exception | bool] | list[str] | Exception
        if name in self.__extensions:
            exc = errors.ExtensionAlreadyLoaded(name)
            final_out = {name: exc} if store else exc
        # This indicates that there is neither an extension nor folder here
        elif (spec := importlib.util.find_spec(name)) is None:
            exc = errors.ExtensionNotFound(name)
            final_out = {name: exc} if store else exc
        # This indicates we've found an extension file to load, and we need to store any exceptions
        elif spec.has_location and store:
            try:
                self._load_from_module_spec(spec, name)
            except Exception as exc:
                final_out = {name: exc}
            else:
                final_out = {name: True}
        # This indicates we've found an extension file to load, and any encountered exceptions can be raised
        elif spec.has_location:
            self._load_from_module_spec(spec, name)
            final_out = [name]
        # This indicates we've been given a folder because the ModuleSpec exists but is not a file
        else:
            # Split the directory path and join it to get an os-native Path object
            path = pathlib.Path(*name.split("."))
            glob = path.rglob if recursive else path.glob
            found: dict[str, Exception | bool] = {}
            found_names: list[str] = []

            # Glob all files with a pattern to gather all .py files that don't start with _
            for ext_file in glob("[!_]*.py"):
                # Gets all parts leading to the directory minus the file name
                parts = list(ext_file.parts[:-1])
                # Gets the file name without the extension
                parts.append(ext_file.stem)
                loaded = self.load_extension(
                    ".".join(parts), package=package, recursive=recursive, store=store
                )
                if store:
                    found.update(cast("dict[str, Exception | bool]", loaded))
                else:
                    found_names.extend(cast("list[str]", loaded))
            final_out = found if store else found_names

        if isinstance(final_out, Exception):
            raise final_out
        return final_out

    @overload
    def load_extensions(
        self,
        *names: str,
        package: str | None = None,
        recursive: bool = False,
    ) -> list[str]: ...

    @overload
    def load_extensions(
        self,
        *names: str,
        package: str | None = None,
        recursive: bool = False,
        store: bool = False,
    ) -> dict[str, Exception | bool] | list[str] | None: ...

    def load_extensions(
        self,
        *names: str,
        package: str | None = None,
        recursive: bool = False,
        store: bool = False,
    ) -> dict[str, Exception | bool] | list[str] | None:
        """Loads multiple extensions at once.

        This method simplifies the process of loading multiple
        extensions by handling the looping of ``load_extension``.

        Parameters
        ----------
        names: :class:`str`
           The extension or folder names to load. It must be dot separated
           like regular Python imports if accessing a submodule. e.g.
           ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when loading an extension using a relative
            path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7
        recursive: Optional[:class:`bool`]
            If subdirectories under the given head directory should be
            recursively loaded.
            Defaults to ``False``.

            .. versionadded:: 2.0
        store: Optional[:class:`bool`]
            If exceptions should be stored or raised. If set to ``True``,
            all exceptions encountered will be stored in a returned dictionary
            as a load status. If set to ``False``, if any exceptions are
            encountered they will be raised and the bot will be closed.
            If no exceptions are encountered, a list of loaded
            extension names will be returned.
            Defaults to ``False``.

            .. versionadded:: 2.0

        Returns
        -------
        Optional[Union[Dict[:class:`str`, Union[:exc:`errors.ExtensionError`, :class:`bool`]], List[:class:`str`]]]
            If the store parameter is set to ``True``, a dictionary will be returned that
            contains keys to represent the loaded extension names. The values bound to
            each key can either be an exception that occurred when loading that extension
            or a ``True`` boolean representing a successful load. If the store parameter
            is set to ``False``, either a list containing names of loaded extensions or
            nothing due to an encountered exception.

        Raises
        ------
        ExtensionNotFound
            A given extension could not be imported.
            This is also raised if the name of the extension could not
            be resolved using the provided ``package`` parameter.
        ExtensionAlreadyLoaded
            A given extension is already loaded.
        NoEntryPointError
            A given extension does not have a setup function.
        ExtensionFailed
            A given extension or its setup function had an execution error.
        """
        loaded_dict: dict[str, Exception | bool] = {}
        loaded_list: list[str] = []

        for ext_path in names:
            loaded = self.load_extension(
                ext_path, package=package, recursive=recursive, store=store
            )
            if store:
                loaded_dict.update(cast("dict[str, Exception | bool]", loaded))
            else:
                loaded_list.extend(cast("list[str]", loaded))

        return loaded_dict if store else loaded_list

    def unload_extension(self, name: str, *, package: str | None = None) -> None:
        """Unloads an extension.

        When the extension is unloaded, all commands, listeners, and cogs are
        removed from the bot and the module is un-imported.

        The extension can provide an optional global function, ``teardown``,
        to do miscellaneous clean-up if necessary. This function takes a single
        parameter, the ``bot``, similar to ``setup`` from
        :meth:`~.Bot.load_extension`.

        Parameters
        ----------
        name: :class:`str`
            The extension name to unload. It must be dot separated like
            regular Python imports if accessing a submodule. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when unloading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7

        Raises
        ------
        ExtensionNotFound
            The name of the extension could not
            be resolved using the provided ``package`` parameter.
        ExtensionNotLoaded
            The extension was not loaded.
        """
        name = self._resolve_name(name, package)
        lib = self.__extensions.get(name)
        if lib is None:
            raise errors.ExtensionNotLoaded(name)

        self._remove_module_references(lib.__name__)
        self._call_module_finalizers(lib, name)

    def reload_extension(self, name: str, *, package: str | None = None) -> None:
        """Atomically reloads an extension.

        This replaces the extension with the same extension, only refreshed. This is
        equivalent to a :meth:`unload_extension` followed by a :meth:`load_extension`
        except done in an atomic way. That is, if an operation fails mid-reload then
        the bot will roll back to the prior working state.

        Parameters
        ----------
        name: :class:`str`
            The extension name to reload. It must be dot separated like
            regular Python imports if accessing a submodule. e.g.
            ``foo.test`` if you want to import ``foo/test.py``.
        package: Optional[:class:`str`]
            The package name to resolve relative imports with.
            This is required when reloading an extension using a relative path, e.g ``.foo.test``.
            Defaults to ``None``.

            .. versionadded:: 1.7

        Raises
        ------
        ExtensionNotLoaded
            The extension was not loaded.
        ExtensionNotFound
            The extension could not be imported.
            This is also raised if the name of the extension could not
            be resolved using the provided ``package`` parameter.
        NoEntryPointError
            The extension does not have a setup function.
        ExtensionFailed
            The extension setup function had an execution error.
        """
        name = self._resolve_name(name, package)
        lib = self.__extensions.get(name)
        if lib is None:
            raise errors.ExtensionNotLoaded(name)

        # get the previous module states from sys modules
        modules = {
            name: module
            for name, module in sys.modules.items()
            if _is_submodule(lib.__name__, name)
        }

        try:
            # Unload and then load the module...
            self._remove_module_references(lib.__name__)
            self._call_module_finalizers(lib, name)
            self.load_extension(name)
        except Exception:
            # if the load failed, the remnants should have been
            # cleaned from the load_extension function call
            # so let's load it from our old compiled library.
            lib.setup(self)
            self.__extensions[name] = lib

            # revert sys.modules back to normal and raise back to caller
            sys.modules.update(modules)
            raise

    @property
    def extensions(self) -> Mapping[str, types.ModuleType]:
        """A read-only mapping of extension name to extension."""
        return types.MappingProxyType(self.__extensions)
