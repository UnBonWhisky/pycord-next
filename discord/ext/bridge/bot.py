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

from abc import ABC
from typing import TYPE_CHECKING, Any, cast

from discord.errors import CheckFailure, DiscordException

from ..commands import (
    AutoShardedBot as ExtAutoShardedBot,
    Bot as ExtBot,
    errors,
)
from .context import BridgeApplicationContext, BridgeExtContext
from .core import (
    BridgeCommand,
    BridgeCommandGroup,
    BridgeExtCommand,
    BridgeSlashCommand,
    bridge_command,
    bridge_group,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterator

    from discord.commands import ApplicationContext
    from discord.interactions import Interaction
    from discord.message import Message

    from ..commands import Context as ExtContext

__all__ = ("AutoShardedBot", "Bot")


class BotBase(ABC):
    _bridge_commands: list[BridgeCommand | BridgeCommandGroup]

    if TYPE_CHECKING:

        def dispatch(self, event: str, *args: Any, **kwargs: Any) -> None: ...

        async def can_run(self, ctx: Any, *, call_once: bool = False) -> bool: ...

    @property
    def bridge_commands(self) -> list[BridgeCommand | BridgeCommandGroup]:
        """Returns all of the bot's bridge commands."""
        if not (cmds := getattr(self, "_bridge_commands", None)):
            cmds = list[BridgeCommand | BridgeCommandGroup]()
            self._bridge_commands = cmds

        return cmds

    def walk_bridge_commands(
        self,
    ) -> Iterator[BridgeCommand | BridgeCommandGroup]:
        """An iterator that recursively walks through all the bot's bridge commands.

        Yields
        ------
        Union[:class:`.BridgeCommand`, :class:`.BridgeCommandGroup`]
            A bridge command or bridge group of the bot.
        """
        for cmd in self._bridge_commands:
            yield cmd
            if isinstance(cmd, BridgeCommandGroup):
                yield from cmd.walk_commands()

    async def get_application_context(
        self,
        interaction: Interaction,
        cls: type[BridgeApplicationContext] | None = None,
    ) -> BridgeApplicationContext:
        cls = cls if cls is not None else BridgeApplicationContext
        # BridgeApplicationContext is a subclass of ApplicationContext, and since
        # we gave it cls, it will be used instead.
        return await cast("Any", super()).get_application_context(interaction, cls=cls)

    async def get_context(
        self, message: Message, cls: type[BridgeExtContext] | None = None
    ) -> BridgeExtContext:
        cls = cls if cls is not None else BridgeExtContext
        # BridgeExtContext is a subclass of Context, and since we gave it cls, it
        # will be used instead.
        return await cast("Any", super()).get_context(message, cls=cls)

    def add_bridge_command(self, command: BridgeCommand) -> None:
        """Takes a :class:`.BridgeCommand` and adds both a slash and traditional (prefix-based) version of the command to the bot."""
        # All subclasses of BotBase pass the type checks.
        command.add_to(cast("Any", self))

        self.bridge_commands.append(command)

    def bridge_command(
        self, **kwargs: Any
    ) -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], BridgeCommand]:
        """A shortcut decorator that invokes :func:`bridge_command` and adds it to the internal command list via :meth:`~.Bot.add_bridge_command`.

        Returns
        -------
        Callable[..., :class:`BridgeCommand`]
            A decorator that converts the provided method into an :class:`.BridgeCommand`, adds both a slash and
            traditional (prefix-based) version of the command to the bot, and returns the :class:`.BridgeCommand`.
        """

        def decorator(func: Callable[..., Coroutine[Any, Any, Any]]) -> BridgeCommand:
            result = bridge_command(**kwargs)(func)
            self.add_bridge_command(result)
            return result

        return decorator

    def bridge_group(
        self, **kwargs: Any
    ) -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], BridgeCommandGroup]:
        """A decorator that is used to wrap a function as a bridge command group.

        Parameters
        ----------
        kwargs: Optional[Dict[:class:`str`, Any]]
            Keyword arguments that are directly passed to the respective command constructors. (:class:`.SlashCommandGroup` and :class:`.ext.commands.Group`)
        """

        def decorator(
            func: Callable[..., Coroutine[Any, Any, Any]],
        ) -> BridgeCommandGroup:
            result = bridge_group(**kwargs)(func)
            self.add_bridge_command(result)
            return result

        return decorator

    async def invoke(self, ctx: ExtContext[Any] | BridgeExtContext) -> None:
        if ctx.command is not None:
            command = cast("Any", ctx.command)
            self.dispatch("command", ctx)
            if isinstance(command, BridgeExtCommand):
                self.dispatch("bridge_command", ctx)
            try:
                if await self.can_run(ctx, call_once=True):
                    await command.invoke(ctx)
                else:
                    raise errors.CheckFailure("The global check once functions failed.")
            except errors.CommandError as exc:
                await command.dispatch_error(ctx, exc)
            else:
                self.dispatch("command_completion", ctx)
                if isinstance(command, BridgeExtCommand):
                    self.dispatch("bridge_command_completion", ctx)
        elif ctx.invoked_with:
            exc = errors.CommandNotFound(f'Command "{ctx.invoked_with}" is not found')
            self.dispatch("command_error", ctx, exc)

    async def invoke_application_command(
        self, ctx: ApplicationContext | BridgeApplicationContext
    ) -> None:
        """|coro|

        Invokes the application command given under the invocation
        context and handles all the internal event dispatch mechanisms.

        Parameters
        ----------
        ctx: :class:`.ApplicationCommand`
            The invocation context to invoke.
        """
        bot = cast("Any", self)._bot
        command = cast("Any", ctx.command)
        bot.dispatch("application_command", ctx)
        if br_cmd := isinstance(command, BridgeSlashCommand):
            bot.dispatch("bridge_command", ctx)
        try:
            if await bot.can_run(ctx, call_once=True):
                await command.invoke(ctx)
            else:
                raise CheckFailure("The global check once functions failed.")
        except DiscordException as exc:
            await command.dispatch_error(ctx, exc)
        else:
            bot.dispatch("application_command_completion", ctx)
            if br_cmd:
                bot.dispatch("bridge_command_completion", ctx)


class Bot(BotBase, ExtBot):  # pyright: ignore[reportIncompatibleMethodOverride]
    """Represents a discord bot, with support for cross-compatibility between command types.

    This class is a subclass of :class:`.ext.commands.Bot` and as a result
    anything that you can do with a :class:`.ext.commands.Bot` you can do with
    this bot.

    .. versionadded:: 2.0
    """


class AutoShardedBot(BotBase, ExtAutoShardedBot):  # pyright: ignore[reportIncompatibleMethodOverride]
    """Similar to :class:`.Bot` except that it is inherited from :class:`.ext.commands.AutoShardedBot` instead.

    .. versionadded:: 2.0
    """
