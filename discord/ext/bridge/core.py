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

from typing import TYPE_CHECKING, Any, ClassVar, TypeVar, cast

from typing_extensions import override

import discord
from discord import (
    ApplicationCommand,
    Attachment,
    Option,
    Permissions,
    SlashCommand,
    SlashCommandGroup,
    SlashCommandOptionType,
)

from ...utils import MISSING, find, get
from ..commands import (
    BadArgument,
    Bot as ExtBot,
    Command,
    Context,
    Converter,
    Group,
    GuildChannelConverter,
    MemberConverter,
    NoPrivateMessage,
    RoleConverter,
    UserConverter,
)
from ..commands.converter import _convert_to_bool, run_converters

T = TypeVar("T")

if TYPE_CHECKING:
    import inspect
    from collections.abc import Callable, Coroutine, Iterator

    from discord import ApplicationContext

    from .context import BridgeApplicationContext, BridgeExtContext

    CommandCallback = Callable[..., Coroutine[Any, Any, Any]]


__all__ = (
    "BridgeCommand",
    "BridgeCommandGroup",
    "BridgeExtCommand",
    "BridgeExtGroup",
    "BridgeOption",
    "BridgeSlashCommand",
    "BridgeSlashGroup",
    "bridge_command",
    "bridge_group",
    "bridge_option",
    "guild_only",
    "has_permissions",
    "is_nsfw",
    "map_to",
)


class BridgeSlashCommand(SlashCommand):
    """A subclass of :class:`.SlashCommand` that is used for bridge commands."""

    def __init__(self, func: CommandCallback, **kwargs: Any) -> None:
        self.brief: str | None = kwargs.pop("brief", None)
        super().__init__(func, **kwargs)

    @override
    async def dispatch_error(self, ctx: ApplicationContext, error: Exception) -> None:
        await super().dispatch_error(ctx, error)
        ctx.bot.dispatch("bridge_command_error", ctx, error)


class BridgeExtCommand(Command[Any, Any, Any]):
    """A subclass of :class:`.ext.commands.Command` that is used for bridge commands."""

    def __init__(self, func: CommandCallback, **kwargs: Any) -> None:
        super().__init__(func, **kwargs)

        for option in self.params.values():
            if isinstance(option.annotation, Option) and not isinstance(
                option.annotation, BridgeOption
            ):
                raise TypeError(
                    f"{option.annotation.__class__.__name__} is not supported in bridge commands. Use BridgeOption instead."
                )

    @override
    async def dispatch_error(self, ctx: Context[Any], error: Exception) -> None:
        await super().dispatch_error(ctx, error)
        ctx.bot.dispatch("bridge_command_error", ctx, error)

    @override
    async def transform(self, ctx: Context[Any], param: inspect.Parameter) -> Any:
        if param.annotation is Attachment:
            # skip the parameter checks for bridge attachments
            return await run_converters(ctx, AttachmentConverter, None, param)
        return await super().transform(ctx, param)


class BridgeSlashGroup(SlashCommandGroup):
    """A subclass of :class:`.SlashCommandGroup` that is used for bridge commands."""

    __slots__ = ("module",)  # pyright: ignore[reportIncompatibleMethodOverride]

    def __init__(self, callback: CommandCallback, *args: Any, **kwargs: Any) -> None:
        if perms := getattr(callback, "__default_member_permissions__", None):
            kwargs["default_member_permissions"] = perms
        super().__init__(*args, **kwargs)
        self.callback = callback
        self.__original_kwargs__["callback"] = callback
        self.__command = None

    @override
    async def _invoke(self, ctx: ApplicationContext) -> None:
        interaction = cast("Any", ctx.interaction)
        data = interaction.data
        if not (options := data and data.get("options")):
            if not self.__command:
                self.__command = BridgeSlashCommand(self.callback)
            ctx.command = self.__command
            await self.__command.invoke(cast("BridgeApplicationContext", ctx))
            return
        option = options[0]
        resolved = data and data.get("resolved", None)
        command = cast(
            "BridgeSlashCommand",
            find(lambda x: x.name == option["name"], self.subcommands),
        )
        option["resolved"] = resolved
        interaction.data = option
        await command.invoke(cast("BridgeApplicationContext", ctx))


class BridgeExtGroup(BridgeExtCommand, Group[Any, Any, Any]):
    """A subclass of :class:`.ext.commands.Group` that is used for bridge commands."""


class BridgeCommand:
    """Compatibility class between prefix-based commands and slash commands.

    Parameters
    ----------
    callback: Callable[[:class:`.BridgeContext`, ...], Awaitable[Any]]
        The callback to invoke when the command is executed. The first argument will be a :class:`BridgeContext`,
        and any additional arguments will be passed to the callback. This callback must be a coroutine.
    parent: Optional[:class:`.BridgeCommandGroup`]:
        Parent of the BridgeCommand.
    kwargs: Optional[Dict[:class:`str`, Any]]
        Keyword arguments that are directly passed to the respective command constructors. (:class:`.SlashCommand` and :class:`.ext.commands.Command`)

    Attributes
    ----------
    slash_variant: :class:`.BridgeSlashCommand`
        The slash command version of this bridge command.
    ext_variant: :class:`.BridgeExtCommand`
        The prefix-based version of this bridge command.
    """

    __bridge__: bool = True

    __special_attrs__: ClassVar[list[str]] = ["slash_variant", "ext_variant", "parent"]

    def __init__(self, callback: CommandCallback, **kwargs: Any) -> None:
        self.parent: BridgeCommandGroup | None = kwargs.pop("parent", None)
        self.slash_variant: BridgeSlashCommand = kwargs.pop(
            "slash_variant", None
        ) or BridgeSlashCommand(callback, **kwargs)
        self.ext_variant: BridgeExtCommand = kwargs.pop(
            "ext_variant", None
        ) or BridgeExtCommand(callback, **kwargs)

    @property
    def name_localizations(self) -> dict[str, str] | None:
        """Returns name_localizations from :attr:`slash_variant` You can edit/set name_localizations directly with

        .. code-block:: python3

            bridge_command.name_localizations["en-UK"] = ...  # or any other locale
            # or
            bridge_command.name_localizations = {"en-UK": ..., "fr-FR": ...}
        """
        return self.slash_variant.name_localizations

    @name_localizations.setter
    def name_localizations(self, value: dict[str, str] | None) -> None:
        self.slash_variant.name_localizations = cast("Any", value)

    @property
    def description_localizations(self) -> dict[str, str] | None:
        """Returns description_localizations from :attr:`slash_variant` You can edit/set description_localizations directly with

        .. code-block:: python3

            bridge_command.description_localizations[
                "en-UK"
            ] = ...  # or any other locale
            # or
            bridge_command.description_localizations = {"en-UK": ..., "fr-FR": ...}
        """
        return self.slash_variant.description_localizations

    @description_localizations.setter
    def description_localizations(self, value: dict[str, str] | None) -> None:
        self.slash_variant.description_localizations = cast("Any", value)

    def __getattribute__(self, name: str) -> Any:
        try:
            # first, look for the attribute on the bridge command
            return super().__getattribute__(name)
        except AttributeError:
            # if it doesn't exist, check this list, if the name of
            # the parameter is here
            if name in self.__special_attrs__:
                raise

            # looks up the result in the variants.
            # slash cmd prioritized
            result = getattr(self.slash_variant, name, MISSING)
            if result is not MISSING:
                return result
            try:
                return getattr(self.ext_variant, name)
            except AttributeError:
                raise AttributeError(
                    f"'{self.__class__.__name__}' object has no attribute '{name}'"
                ) from None

    def __setattr__(self, name: str, value: Any) -> None:
        if name not in self.__special_attrs__:
            setattr(self.slash_variant, name, value)
            setattr(self.ext_variant, name, value)

        return super().__setattr__(name, value)

    def add_to(self, bot: ExtBot) -> None:
        """Adds the command to a bot. This method is inherited by :class:`.BridgeCommandGroup`.

        Parameters
        ----------
        bot: Union[:class:`.Bot`, :class:`.AutoShardedBot`]
            The bot to add the command to.
        """
        bot.add_application_command(self.slash_variant)
        bot.add_command(self.ext_variant)

    async def invoke(
        self,
        ctx: BridgeExtContext | BridgeApplicationContext,
        /,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """|coro|

        Invoke the slash or the prefixed variant of this command depending on ``ctx``.

        Parameters
        ----------
        ctx: Union[:class:`.BridgeExtContext`, :class:`.BridgeApplicationContext`]
            The invocation context.
        """
        if ctx.is_app:
            return await self.slash_variant.invoke(
                cast("BridgeApplicationContext", ctx)
            )
        return await self.ext_variant.invoke(cast("BridgeExtContext", ctx))

    def error(self, coro: Any) -> Any:
        """A decorator that registers a coroutine as a local error handler.

        This error handler is limited to the command it is defined to.
        However, higher scope handlers (per-cog and global) are still
        invoked afterwards as a catch-all. This handler also functions as
        the handler for both the prefixed and slash versions of the command.

        This error handler takes two parameters, a :class:`.BridgeContext` and
        a :class:`~discord.DiscordException`.

        Parameters
        ----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the local error handler.

        Raises
        ------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        self.slash_variant.error(coro)
        self.ext_variant.on_error = coro

        return coro

    def before_invoke(self, coro: Any) -> Any:
        """A decorator that registers a coroutine as a pre-invoke hook.

        This hook is called directly before the command is called, making
        it useful for any sort of set up required. This hook is called
        for both the prefixed and slash versions of the command.

        This pre-invoke hook takes a sole parameter, a :class:`.BridgeContext`.

        Parameters
        ----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the pre-invoke hook.

        Raises
        ------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        self.slash_variant.before_invoke(coro)
        self.ext_variant._before_invoke = coro

        return coro

    def after_invoke(self, coro: Any) -> Any:
        """A decorator that registers a coroutine as a post-invoke hook.

        This hook is called directly after the command is called, making it
        useful for any sort of clean up required. This hook is called for
        both the prefixed and slash versions of the command.

        This post-invoke hook takes a sole parameter, a :class:`.BridgeContext`.

        Parameters
        ----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the post-invoke hook.

        Raises
        ------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        self.slash_variant.after_invoke(coro)
        self.ext_variant._after_invoke = coro

        return coro


class BridgeCommandGroup(BridgeCommand):
    """Compatibility class between prefix-based commands and slash commands.

    Parameters
    ----------
    callback: Callable[[:class:`.BridgeContext`, ...], Awaitable[Any]]
        The callback to invoke when the command is executed. The first argument will be a :class:`BridgeContext`,
        and any additional arguments will be passed to the callback. This callback must be a coroutine.
    kwargs: Optional[Dict[:class:`str`, Any]]
        Keyword arguments that are directly passed to the respective command constructors. (:class:`.SlashCommand` and :class:`.ext.commands.Command`)

    Attributes
    ----------
    slash_variant: :class:`.SlashCommandGroup`
        The slash command version of this command group.
    ext_variant: :class:`.ext.commands.Group`
        The prefix-based version of this command group.
    subcommands: List[Union[:class:`.BridgeCommand`, :class:`.BridgeCommandGroup`]]
        List of bridge commands and subgroups in this group
    mapped: Optional[:class:`.SlashCommand`]
        If :func:`map_to` is used, the mapped slash command.
    """

    __special_attrs__: ClassVar[list[str]] = [
        "slash_variant",
        "ext_variant",
        "parent",
        "subcommands",
        "mapped",
    ]

    ext_variant: BridgeExtGroup  # pyright: ignore[reportIncompatibleVariableOverride]
    slash_variant: BridgeSlashGroup  # pyright: ignore[reportIncompatibleVariableOverride]

    def __init__(self, callback: CommandCallback, *args: Any, **kwargs: Any) -> None:
        ext_var = kwargs.pop("ext_variant", None) or BridgeExtGroup(
            callback, *args, **kwargs
        )
        kwargs.update({"name": ext_var.name})
        slash_var = kwargs.pop("slash_variant", None) or BridgeSlashGroup(
            callback, *args, **kwargs
        )
        super().__init__(
            callback,
            ext_variant=ext_var,
            slash_variant=slash_var,
            parent=kwargs.pop("parent", None),
        )

        self.subcommands: list[BridgeCommand | BridgeCommandGroup] = []

        self.mapped: SlashCommand | None = None
        if map_to := getattr(callback, "__custom_map_to__", None):
            kwargs.update(map_to)
            self.mapped = self.slash_variant.command(**kwargs)(callback)

    def walk_commands(self) -> Iterator[BridgeCommand | BridgeCommandGroup]:
        """An iterator that recursively walks through all the bridge group's subcommands.

        Yields
        ------
        Union[:class:`.BridgeCommand`, :class:`.BridgeCommandGroup`]
            A bridge command or subgroup of this bridge group.
        """
        for command in self.subcommands:
            yield command
            if isinstance(command, BridgeCommandGroup):
                yield from command.walk_commands()

    def command(
        self, *args: Any, **kwargs: Any
    ) -> Callable[[CommandCallback], BridgeCommand]:
        """A decorator to register a function as a subcommand.

        Parameters
        ----------
        kwargs: Optional[Dict[:class:`str`, Any]]
            Keyword arguments that are directly passed to the respective command constructors. (:class:`.SlashCommand` and :class:`.ext.commands.Command`)
        """

        def wrap(callback: CommandCallback) -> BridgeCommand:
            slash = self.slash_variant.command(
                *args,
                **kwargs,
                cls=BridgeSlashCommand,
            )(callback)
            ext = self.ext_variant.command(
                *args,
                **kwargs,
                cls=BridgeExtCommand,
            )(callback)
            command = BridgeCommand(
                callback, parent=self, slash_variant=slash, ext_variant=ext
            )
            self.subcommands.append(command)
            return command

        return wrap

    def subgroup(
        self,
        *,
        name: str = MISSING,
        description: str | None = None,
        **kwargs: Any,
    ) -> Callable[[Callable[..., Any]], BridgeCommandGroup]:
        """A decorator to register a function as a subgroup.

        .. versionadded:: 3.0

        Parameters
        ----------
        name: :class:`str`
            The name of the subgroup. Defaults to the name of the function.
        description: Optional[:class:`str`]
            The description of the subgroup.
        kwargs: Optional[Dict[:class:`str`, Any]]
            Keyword arguments that are directly passed to the respective command constructors. (:class:`.SlashCommandGroup` and :class:`.ext.commands.Group`)
        """

        def wrap(callback: Callable[..., Any]) -> BridgeCommandGroup:
            group_name = callback.__name__ if name is MISSING else name
            slash = self.slash_variant.create_subgroup(
                name=group_name,
                description=description,
                **kwargs,
            )
            ext_kwargs = dict(kwargs)
            if description is not None:
                ext_kwargs["description"] = description
            ext = self.ext_variant.group(
                name=group_name,
                **ext_kwargs,
                cls=BridgeExtGroup,
            )(callback)
            group = BridgeCommandGroup(
                callback,
                parent=self,
                slash_variant=slash,
                ext_variant=ext,
            )
            self.subcommands.append(group)
            return group

        return wrap


def bridge_command(**kwargs: Any) -> Callable[[CommandCallback], BridgeCommand]:
    """A decorator that is used to wrap a function as a bridge command.

    Parameters
    ----------
    kwargs: Optional[Dict[:class:`str`, Any]]
        Keyword arguments that are directly passed to the respective command constructors. (:class:`.SlashCommand` and :class:`.ext.commands.Command`)
    """

    def decorator(callback: CommandCallback) -> BridgeCommand:
        return BridgeCommand(callback, **kwargs)

    return decorator


def bridge_group(**kwargs: Any) -> Callable[[CommandCallback], BridgeCommandGroup]:
    """A decorator that is used to wrap a function as a bridge command group.

    Parameters
    ----------
    kwargs: Optional[Dict[:class:`str`, Any]]
        Keyword arguments that are directly passed to the respective command constructors (:class:`.SlashCommandGroup` and :class:`.ext.commands.Group`).
    """

    def decorator(callback: CommandCallback) -> BridgeCommandGroup:
        return BridgeCommandGroup(callback, **{"name": callback.__name__, **kwargs})

    return decorator


def map_to(name: str, description: str | None = None) -> Callable[[Any], Any]:
    """To be used with bridge command groups, map the main command to a slash subcommand.

    Parameters
    ----------
    name: :class:`str`
        The new name of the mapped command.
    description: Optional[:class:`str`]
        The new description of the mapped command.

    Example
    -------

    .. code-block:: python3

        @bot.bridge_group()
        @bridge.map_to("show")
        async def config(ctx: BridgeContext): ...


        @config.command()
        async def toggle(ctx: BridgeContext): ...

    Prefixed commands will not be affected, but slash commands will appear as:

    .. code-block::

        /config show
        /config toggle
    """

    def decorator(callback: Any) -> Any:
        callback.__custom_map_to__ = {"name": name, "description": description}
        return callback

    return decorator


def guild_only() -> Callable[[T], T]:
    """Intended to work with :class:`.ApplicationCommand` and :class:`BridgeCommand`, adds a :func:`~ext.commands.check` that locks the command to only run in guilds, and also registers the command as guild only client-side (on discord).

    Basically a utility function that wraps both :func:`discord.ext.commands.guild_only` and :func:`discord.commands.guild_only`.
    """

    def predicate(func: T) -> T:
        target = cast("Any", func)
        if isinstance(target, ApplicationCommand):
            target.guild_only = True
        else:
            target.__guild_only__ = True

        from ..commands import guild_only

        return guild_only()(func)

    return predicate


def is_nsfw() -> Callable[[T], T]:
    """Intended to work with :class:`.ApplicationCommand` and :class:`BridgeCommand`, adds a :func:`~ext.commands.check` that locks the command to only run in nsfw contexts, and also registers the command as nsfw client-side (on discord).

    Basically a utility function that wraps both :func:`discord.ext.commands.is_nsfw` and :func:`discord.commands.is_nsfw`.

    .. warning::

        In DMs, the prefix-based command will always run as the user's privacy settings cannot be checked directly.
    """

    def predicate(func: T) -> T:
        target = cast("Any", func)
        if isinstance(target, ApplicationCommand):
            target.nsfw = True
        else:
            target.__nsfw__ = True

        from ..commands import is_nsfw

        return is_nsfw()(func)

    return predicate


def has_permissions(**perms: bool) -> Callable[[T], T]:
    r"""Intended to work with :class:`.SlashCommand` and :class:`BridgeCommand`, adds a :func:`~ext.commands.check` that locks the command to be run by people with certain permissions inside guilds, and also registers the command as locked behind said permissions.

    Basically a utility function that wraps both :func:`discord.ext.commands.has_permissions`
    and :func:`discord.commands.default_permissions`.

    Parameters
    ----------
    \*\*perms: Dict[:class:`str`, :class:`bool`]
        An argument list of permissions to check for.
    """

    def predicate(func: T) -> T:
        from ..commands import has_permissions

        func = has_permissions(**perms)(func)
        target = cast("Any", func)
        _perms = Permissions(**perms)
        if isinstance(target, ApplicationCommand):
            target.default_member_permissions = _perms
        else:
            target.__default_member_permissions__ = _perms

        return func

    return predicate


class MentionableConverter(Converter[Any]):
    """A converter that can convert a mention to a member, a user or a role."""

    @override
    async def convert(self, ctx: Context[Any], argument: str) -> Any:
        try:
            return await RoleConverter().convert(ctx, argument)
        except (BadArgument, NoPrivateMessage):
            pass

        if ctx.guild:
            try:
                return await MemberConverter().convert(ctx, argument)
            except BadArgument:
                pass

        return await UserConverter().convert(ctx, argument)


class AttachmentConverter(Converter[discord.Attachment]):
    @override
    async def convert(self, ctx: Context[Any], argument: str) -> discord.Attachment:
        try:
            attach = ctx.message.attachments[0]
        except IndexError as exc:
            raise BadArgument("At least 1 attachment is needed") from exc
        else:
            return attach


class BooleanConverter(Converter[bool]):
    @override
    async def convert(self, ctx: Context[Any], argument: str) -> bool:
        return _convert_to_bool(str(argument))


BRIDGE_CONVERTER_MAPPING = {
    SlashCommandOptionType.string: str,
    SlashCommandOptionType.integer: int,
    SlashCommandOptionType.boolean: BooleanConverter,
    SlashCommandOptionType.user: UserConverter,
    SlashCommandOptionType.channel: GuildChannelConverter,
    SlashCommandOptionType.role: RoleConverter,
    SlashCommandOptionType.mentionable: MentionableConverter,
    SlashCommandOptionType.number: float,
    SlashCommandOptionType.attachment: AttachmentConverter,
    discord.Member: MemberConverter,
}


class BridgeOption(Option, Converter[Any]):
    """A subclass of :class:`discord.Option` which represents a selectable slash command option and a prefixed command argument for bridge commands."""

    def __init__(self, input_type: Any, *args: Any, **kwargs: Any) -> None:
        self.converter: Any = kwargs.pop("converter", None)
        super().__init__(input_type, *args, **kwargs)

        self.converter = self.converter or BRIDGE_CONVERTER_MAPPING.get(input_type)

    @override
    async def convert(self, ctx: Context[Any], argument: str) -> Any:
        try:
            converted = await self._convert_value(ctx, argument)
            if self.choices:
                converted = self._match_choice(converted, argument)
        except ValueError as exc:
            raise BadArgument from exc
        return converted

    async def _convert_value(self, ctx: Context[Any], argument: str) -> Any:
        converter: Any = (
            self.converter
            if self.converter is not None
            else BRIDGE_CONVERTER_MAPPING.get(self.input_type)
        )
        if isinstance(converter, type) and issubclass(converter, Converter):
            return await cast("Any", converter)().convert(ctx, argument)
        if callable(cast("Any", converter)):
            return converter(argument)
        raise TypeError(f"Invalid converter: {converter}")

    def _match_choice(self, converted: Any, argument: str) -> Any:
        choices_names: list[str | int | float] = [
            choice.name for choice in self.choices
        ]
        if converted in choices_names and (choice := get(self.choices, name=converted)):
            return choice.value
        choices = [choice.value for choice in self.choices]
        if converted not in choices:
            raise ValueError(
                f"{argument} is not a valid choice. Valid choices:"
                f" {list(set(choices_names + choices))}"
            )
        return converted


def bridge_option(
    name: str, input_type: Any = None, **kwargs: Any
) -> Callable[[Any], Any]:
    """A decorator that can be used instead of typehinting :class:`.BridgeOption`.

    .. versionadded:: 2.6

    Attributes
    ----------
    parameter_name: :class:`str`
        The name of the target function parameter this option is mapped to.
        This allows you to have a separate UI ``name`` and parameter name.
    """

    def decorator(func: Any) -> Any:
        resolved_name = kwargs.pop("parameter_name", None) or name
        itype = (
            kwargs.pop("type", None)
            or input_type
            or func.__annotations__.get(resolved_name, str)
        )
        func.__annotations__[resolved_name] = BridgeOption(itype, name=name, **kwargs)
        return func

    return decorator
