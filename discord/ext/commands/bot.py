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

import collections.abc
import contextlib
import sys
import traceback
from typing import TYPE_CHECKING, Any, TypeVar, cast

import discord

from . import errors
from .context import Context
from .core import GroupMixin
from .help import DefaultHelpCommand, HelpCommand
from .view import StringView

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Iterable

    from discord.message import Message
    from discord.user import ClientUser

    from ._types import Check, CoroFunc

__all__ = (
    "AutoShardedBot",
    "Bot",
    "when_mentioned",
    "when_mentioned_or",
)

MISSING: Any = discord.utils.MISSING

T = TypeVar("T")
CFT = TypeVar("CFT", bound="CoroFunc")
CXT = TypeVar("CXT", bound="Context[Any]")


def when_mentioned(bot: Bot | AutoShardedBot, msg: Message) -> list[str]:
    """A callable that implements a command prefix equivalent to being mentioned.

    These are meant to be passed into the :attr:`.Bot.command_prefix` attribute.
    """
    # bot.user will never be None when this is called
    user = cast("ClientUser", bot.user)
    return [f"<@{user.id}> ", f"<@!{user.id}> "]


def when_mentioned_or(
    *prefixes: str,
) -> Callable[[Bot | AutoShardedBot, Message], list[str]]:
    """A callable that implements when mentioned or other prefixes provided.

    These are meant to be passed into the :attr:`.Bot.command_prefix` attribute.

    See Also
    --------
    :func:`.when_mentioned`

    Example
    -------

    .. code-block:: python3

        bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"))

    .. note::

        This callable returns another callable, so if this is done inside a custom
        callable, you must call the returned callable, for example:

        .. code-block:: python3

            async def get_prefix(bot, message):
                extras = await prefixes_for(message.guild)  # returns a list
                return commands.when_mentioned_or(*extras)(bot, message)
    """

    def inner(bot: Bot | AutoShardedBot, msg: Message) -> list[str]:
        r = list(prefixes)
        return when_mentioned(bot, msg) + r

    return inner


class BotBase(GroupMixin[Any], discord.cog.CogMixin):
    _help_command = None
    _supports_prefixed_commands = True

    if TYPE_CHECKING:
        _event_handlers: dict[str, list[CoroFunc]]
        _checks: list[Check]
        _check_once: list[Check]

        @property
        def user(self) -> ClientUser | None: ...

        def dispatch(self, event: str, *args: Any, **kwargs: Any) -> None: ...

    def __init__(
        self,
        command_prefix: CommandPrefix = when_mentioned,
        help_command: HelpCommand | None = MISSING,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self.command_prefix: CommandPrefix = command_prefix
        self.help_command = (
            DefaultHelpCommand() if help_command is MISSING else help_command
        )
        self.strip_after_prefix = options.get("strip_after_prefix", False)

    @discord.utils.copy_doc(discord.Client.close)
    async def close(self) -> None:
        for extension in tuple(self.extensions):
            with contextlib.suppress(Exception):
                self.unload_extension(extension)

        for cog in tuple(self.cogs):
            with contextlib.suppress(Exception):
                self.remove_cog(cog)

        await cast("Any", super()).close()

    async def on_command_error(
        self, context: Context[Any], exception: errors.CommandError
    ) -> None:
        """|coro|

        The default command error handler provided by the bot.

        By default, this prints to :data:`sys.stderr` however it could be
        overridden to have a different implementation.

        This only fires if you do not specify any listeners for command error.
        """
        if self._event_handlers.get("on_command_error", None):
            return

        command = context.command
        if command and command.has_error_handler():
            return

        cog = context.cog
        if cog and cog.has_error_handler():
            return

        sys.stderr.write(f"Ignoring exception in command {context.command}:\n")
        traceback.print_exception(
            type(exception), exception, exception.__traceback__, file=sys.stderr
        )

    async def can_run(self, ctx: Context[Any], *, call_once: bool = False) -> bool:
        data = self._check_once if call_once else self._checks

        if len(data) == 0:
            return True

        # type-checker doesn't distinguish between functions and methods
        return await discord.utils.async_all(
            cast("Callable[[Context[Any]], Any]", f)(ctx) for f in data
        )

    # help command stuff

    @property
    def help_command(self) -> HelpCommand | None:
        return self._help_command

    @help_command.setter
    def help_command(self, value: HelpCommand | None) -> None:
        bot = cast("Bot | AutoShardedBot", self)
        if value is not None:
            if not isinstance(cast("object", value), HelpCommand):
                raise TypeError("help_command must be a subclass of HelpCommand")
            if self._help_command is not None:
                self._help_command._remove_from_bot(bot)
            self._help_command = value
            value._add_to_bot(bot)
        elif self._help_command is not None:
            self._help_command._remove_from_bot(bot)
            self._help_command = None
        else:
            self._help_command = None

    # command processing

    async def get_prefix(self, message: Message) -> list[str] | str:
        """|coro|

        Retrieves the prefix the bot is listening to
        with the message as a context.

        Parameters
        ----------
        message: :class:`discord.Message`
            The message context to get the prefix of.

        Returns
        -------
        Union[List[:class:`str`], :class:`str`]
            A list of prefixes or a single prefix that the bot is
            listening for.
        """
        raw = cast("Any", self.command_prefix)
        if callable(raw):
            raw = await discord.utils.maybe_coroutine(raw, self, message)

        if isinstance(raw, str):
            return raw

        try:
            ret = list(cast("Iterable[str]", raw))
        except TypeError as exc:
            # It's possible that a generator raised this exception.  Don't
            # replace it with our own error if that's the case.
            if isinstance(raw, collections.abc.Iterable):
                raise

            raise TypeError(
                "command_prefix must be plain string, iterable of strings, or"
                f" callable returning either of these, not {raw.__class__.__name__}"
            ) from exc

        if not ret:
            raise ValueError("Iterable command_prefix must contain at least one prefix")

        return ret

    async def get_context(self, message: Message, *, cls: type[CXT] = Context) -> CXT:
        r"""|coro|

        Returns the invocation context from the message.

        This is a more low-level counter-part for :meth:`.process_commands`
        to allow users more fine-grained control over the processing.

        The returned context is not guaranteed to be a valid invocation
        context, :attr:`.Context.valid` must be checked to make sure it is.
        If the context is not valid then it is not a valid candidate to be
        invoked under :meth:`~.Bot.invoke`.

        Parameters
        ----------
        message: :class:`discord.Message`
            The message to get the invocation context from.
        cls
            The factory class that will be used to create the context.
            By default, this is :class:`.Context`. Should a custom
            class be provided, it must be similar enough to :class:`.Context`\'s
            interface.

        Returns
        -------
        :class:`.Context`
            The invocation context. The type of this can change via the
            ``cls`` parameter.
        """
        view = StringView(message.content)
        ctx = cls(
            prefix=None,
            view=view,
            bot=cast("Bot | AutoShardedBot", self),
            message=message,
        )

        if message.author.id == cast("ClientUser", self.user).id:
            return ctx

        prefix = await self.get_prefix(message)
        invoked_prefix: str | None = None

        if isinstance(prefix, str):
            if not view.skip_string(prefix):
                return ctx
            invoked_prefix = prefix
        else:
            try:
                # if the context class' __init__ consumes something from the view this
                # will be wrong.  That seems unreasonable though.
                if message.content.startswith(tuple(prefix)):
                    invoked_prefix = discord.utils.find(view.skip_string, prefix)
                else:
                    return ctx

            except TypeError as exc:
                prefix_value = cast("object", prefix)
                if not isinstance(prefix_value, list):
                    raise TypeError(
                        "get_prefix must return either a string or a list of string, "
                        f"not {prefix_value.__class__.__name__}"
                    ) from exc

                # It's possible a bad command_prefix got us here.
                for value in cast("list[object]", prefix_value):
                    if not isinstance(value, str):
                        raise TypeError(
                            "Iterable command_prefix or list returned from get_prefix"
                            " must contain only strings, not"
                            f" {value.__class__.__name__}"
                        ) from exc

                # Getting here shouldn't happen
                raise

        if self.strip_after_prefix:
            view.skip_ws()

        invoker = view.get_word()
        ctx.invoked_with = invoker
        ctx.prefix = invoked_prefix
        ctx.command = self.prefixed_commands.get(invoker)
        return ctx

    async def invoke(self, ctx: Context[Any]) -> None:
        """|coro|

        Invokes the command given under the invocation context and
        handles all the internal event dispatch mechanisms.

        Parameters
        ----------
        ctx: :class:`.Context`
            The invocation context to invoke.
        """
        if ctx.command is not None:
            self.dispatch("command", ctx)
            try:
                if await self.can_run(ctx, call_once=True):
                    await ctx.command.invoke(ctx)
                else:
                    raise errors.CheckFailure("The global check once functions failed.")
            except errors.CommandError as exc:
                await ctx.command.dispatch_error(ctx, exc)
            else:
                self.dispatch("command_completion", ctx)
        elif ctx.invoked_with:
            exc = errors.CommandNotFound(f'Command "{ctx.invoked_with}" is not found')
            self.dispatch("command_error", ctx, exc)

    async def process_commands(self, message: Message) -> None:
        """|coro|

        This function processes the commands that have been registered
        to the bot and other groups. Without this coroutine, none of the
        commands will be triggered.

        By default, this coroutine is called inside the :func:`.on_message`
        event. If you choose to override the :func:`.on_message` event, then
        you should invoke this coroutine as well.

        This is built using other low level tools, and is equivalent to a
        call to :meth:`~.Bot.get_context` followed by a call to :meth:`~.Bot.invoke`.

        This also checks if the message's author is a bot and doesn't
        call :meth:`~.Bot.get_context` or :meth:`~.Bot.invoke` if so.

        Parameters
        ----------
        message: :class:`discord.Message`
            The message to process commands for.
        """
        if message.author.bot:
            return

        ctx = cast("Context[Any]", await self.get_context(message))
        await self.invoke(ctx)

    async def on_message(self, message: Message) -> None:
        await self.process_commands(message)


class Bot(BotBase, discord.Bot):  # pyright: ignore[reportIncompatibleMethodOverride, reportIncompatibleVariableOverride]
    """Represents a discord bot.

    This class is a subclass of :class:`discord.Bot` and as a result
    anything that you can do with a :class:`discord.Bot` you can do with
    this bot.

    This class also subclasses :class:`.GroupMixin` to provide the functionality
    to manage commands.

    .. note::

        Using prefixed commands requires :attr:`discord.Intents.message_content` to be enabled.

    Attributes
    ----------
    command_prefix
        The command prefix is what the message content must contain initially
        to have a command invoked. This prefix could either be a string to
        indicate what the prefix should be, or a callable that takes in the bot
        as its first parameter and :class:`discord.Message` as its second
        parameter and returns the prefix. This is to facilitate "dynamic"
        command prefixes. This callable can be either a regular function or
        a coroutine.

        An empty string as the prefix always matches, enabling prefix-less
        command invocation. While this may be useful in DMs it should be avoided
        in servers, as it's likely to cause performance issues and unintended
        command invocations.

        The command prefix could also be an iterable of strings indicating that
        multiple checks for the prefix should be used and the first one to
        match will be the invocation prefix. You can get this prefix via
        :attr:`.Context.prefix`. To avoid confusion empty iterables are not
        allowed.

        .. note::

            When passing multiple prefixes be careful to not pass a prefix
            that matches a longer prefix occurring later in the sequence.  For
            example, if the command prefix is ``('!', '!?')``  the ``'!?'``
            prefix will never be matched to any message as the previous one
            matches messages starting with ``!?``. This is especially important
            when passing an empty string, it should always be last as no prefix
            after it will be matched.
    case_insensitive: :class:`bool`
        Whether the commands should be case-insensitive. Defaults to ``False``. This
        attribute does not carry over to groups. You must set it to every group if
        you require group commands to be case-insensitive as well.
    help_command: Optional[:class:`.HelpCommand`]
        The help command implementation to use. This can be dynamically
        set at runtime. To remove the help command pass ``None``. For more
        information on implementing a help command, see :ref:`ext_commands_help_command`.
    strip_after_prefix: :class:`bool`
        Whether to strip whitespace characters after encountering the command
        prefix. This allows for ``!   hello`` and ``!hello`` to both work if
        the ``command_prefix`` is set to ``!``. Defaults to ``False``.

        .. versionadded:: 1.7
    """


class AutoShardedBot(BotBase, discord.AutoShardedBot):  # pyright: ignore[reportIncompatibleMethodOverride, reportIncompatibleVariableOverride]
    """Similar to :class:`.Bot` except that it is inherited from :class:`discord.AutoShardedBot` instead."""


if TYPE_CHECKING:
    CommandPrefix = (
        str
        | Iterable[str]
        | Callable[
            [Bot | AutoShardedBot, Message],
            str | Iterable[str] | Coroutine[Any, Any, str | Iterable[str]],
        ]
    )
