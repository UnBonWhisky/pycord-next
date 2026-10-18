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

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from discord.commands import ApplicationContext

from ..commands import Context

if TYPE_CHECKING:
    import asyncio
    from types import TracebackType

    from typing_extensions import Self

    from discord.context_managers import Typing
    from discord.interactions import Interaction, InteractionMessage
    from discord.message import Message
    from discord.webhook import WebhookMessage

    from .core import BridgeExtCommand, BridgeSlashCommand


__all__ = (
    "BridgeApplicationContext",
    "BridgeContext",
    "BridgeExtContext",
    "Context",
    "DeferTyping",
)


class DeferTyping:
    """A context manager that defers the interaction of a :class:`BridgeApplicationContext` for as long as it is active.

    This is both a regular context manager and an async context manager.

    .. versionadded:: 3.0
    """

    def __init__(
        self, ctx: BridgeApplicationContext, *, ephemeral: bool = False
    ) -> None:
        self.loop: asyncio.AbstractEventLoop = ctx._state.loop
        self.ctx: BridgeApplicationContext = ctx
        self.ephemeral: bool = ephemeral

    async def do_defer(self) -> None:
        """|coro|

        Defers the interaction.
        """
        await self.ctx.defer(ephemeral=self.ephemeral)

    def __enter__(self) -> Self:
        self.task: asyncio.Task[None] = self.loop.create_task(self.do_defer())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.task.cancel()

    async def __aenter__(self) -> Self:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return self.__exit__(exc_type, exc_value, traceback)


class BridgeContext(ABC):
    """The base context class for compatibility commands.

    This class is an :term:`abstract base class` (also known as an ``abc``), which is
    subclassed by :class:`BridgeExtContext` and :class:`BridgeApplicationContext`. The
    methods in this class are meant to give parity between the two contexts, while still
    allowing for all of their functionality.

    When this is passed to a command, it will either be passed as :class:`BridgeExtContext`, or
    :class:`BridgeApplicationContext`. Since they are two separate classes, it's easy to use the :attr:`BridgeContext.is_app` attribute.
    to make different functionality for each context. For example, if you want to respond to a command with the command
    type that it was invoked with, you can do the following:

    .. code-block:: python3

        @bot.bridge_command()
        async def example(ctx: BridgeContext):
            if ctx.is_app:
                command_type = "Application command"
            else:
                command_type = "Traditional (prefix-based) command"
            await ctx.send(f"This command was invoked with a(n) {command_type}.")

    .. versionadded:: 2.0
    """

    @abstractmethod
    async def _respond(
        self, *args: Any, **kwargs: Any
    ) -> Interaction | WebhookMessage | Message: ...

    @abstractmethod
    async def _defer(self, *args: Any, **kwargs: Any) -> None: ...

    @abstractmethod
    def _typing(self, *args: Any, **kwargs: Any) -> Typing | DeferTyping: ...

    @abstractmethod
    async def _edit(
        self, *args: Any, **kwargs: Any
    ) -> InteractionMessage | Message | None: ...

    if TYPE_CHECKING:

        async def invoke(
            self,
            command: BridgeSlashCommand | BridgeExtCommand,
            *args: Any,
            **kwargs: Any,
        ) -> None:
            """|coro|

            Calls the callback of a bridge command with the arguments given.
            """

    async def respond(
        self, *args: Any, **kwargs: Any
    ) -> Interaction | WebhookMessage | Message:
        """|coro|

        Responds to the command with the respective response type to the current context. In :class:`BridgeExtContext`,
        this will be :meth:`~.Context.reply` while in :class:`BridgeApplicationContext`, this will be
        :meth:`~.ApplicationContext.respond`.
        """
        return await self._respond(*args, **kwargs)

    async def reply(
        self, *args: Any, **kwargs: Any
    ) -> Interaction | WebhookMessage | Message:
        """|coro|

        Alias for :meth:`~.BridgeContext.respond`.
        """
        return await self.respond(*args, **kwargs)

    async def defer(self, *args: Any, **kwargs: Any) -> None:
        """|coro|

        Defers the command with the respective approach to the current context. In :class:`BridgeExtContext`, this will
        be :meth:`~discord.abc.Messageable.trigger_typing` while in :class:`BridgeApplicationContext`, this will be
        :attr:`~.ApplicationContext.defer`.

        .. note::
            There is no ``trigger_typing`` alias for this method. ``trigger_typing`` will always provide the same
            functionality across contexts.
        """
        return await self._defer(*args, **kwargs)

    def typing(self, *args: Any, **kwargs: Any) -> Typing | DeferTyping:
        """Returns a context manager that allows you to type for an indefinite period of time.

        In :class:`BridgeExtContext`, this will be :meth:`~.Context.typing` while in
        :class:`BridgeApplicationContext`, this is equivalent to a :meth:`defer` call and
        does not do any typing calls.

        .. versionadded:: 3.0
        """
        return self._typing(*args, **kwargs)

    async def edit(
        self, *args: Any, **kwargs: Any
    ) -> InteractionMessage | Message | None:
        """|coro|

        Edits the original response message with the respective approach to the current context. In
        :class:`BridgeExtContext`, this will have a custom approach where :meth:`.respond` caches the message to be
        edited here. In :class:`BridgeApplicationContext`, this will be :attr:`~.ApplicationContext.edit`.
        """
        return await self._edit(*args, **kwargs)

    def _get_super(self, attr: str) -> Any:
        return getattr(super(), attr)

    @property
    def is_app(self) -> bool:
        """Whether the context is an :class:`BridgeApplicationContext` or not."""
        return isinstance(self, BridgeApplicationContext)


class BridgeApplicationContext(BridgeContext, ApplicationContext):  # pyright: ignore[reportIncompatibleMethodOverride, reportIncompatibleVariableOverride]
    """The application context class for compatibility commands.

    This class is a subclass of :class:`BridgeContext` and
    :class:`~.ApplicationContext`. This class is meant to be used with
    :class:`BridgeCommand`.

    .. versionadded:: 2.0
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # This is needed in order to represent the correct class init signature on the docs
        super().__init__(*args, **kwargs)

    async def _respond(self, *args: Any, **kwargs: Any) -> Interaction | WebhookMessage:
        return await self._get_super("respond")(*args, **kwargs)

    async def _defer(self, *args: Any, **kwargs: Any) -> None:
        return await self._get_super("defer")(*args, **kwargs)

    def _typing(self, *args: Any, **kwargs: Any) -> DeferTyping:
        return DeferTyping(self, *args, **kwargs)

    async def _edit(self, *args: Any, **kwargs: Any) -> InteractionMessage:
        return await self._get_super("edit")(*args, **kwargs)


class BridgeExtContext(BridgeContext, Context[Any]):  # pyright: ignore[reportIncompatibleMethodOverride]
    """The ext.commands context class for compatibility commands.

    This class is a subclass of :class:`BridgeContext` and :class:`~.Context`. This
    class is meant to be used with :class:`BridgeCommand`.

    .. versionadded:: 2.0
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._original_response_message: Message | None = None

    async def _respond(self, *args: Any, **kwargs: Any) -> Message:
        kwargs.pop("ephemeral", None)
        message = await self._get_super("reply")(*args, **kwargs)
        if self._original_response_message is None:
            self._original_response_message = message
        return message

    async def _defer(self, *args: Any, **kwargs: Any) -> None:
        kwargs.pop("ephemeral", None)
        return await self._get_super("trigger_typing")(*args, **kwargs)

    def _typing(self, *args: Any, **kwargs: Any) -> Typing:
        kwargs.pop("ephemeral", None)
        return self._get_super("typing")(*args, **kwargs)

    async def _edit(self, *args: Any, **kwargs: Any) -> Message | None:
        if self._original_response_message:
            return await self._original_response_message.edit(*args, **kwargs)
        return None

    async def delete(
        self, *, delay: float | None = None, reason: str | None = None
    ) -> None:
        """|coro|

        Deletes the original response message, if it exists.

        Parameters
        ----------
        delay: Optional[:class:`float`]
            If provided, the number of seconds to wait before deleting the message.
        reason: Optional[:class:`str`]
            The reason for deleting the message. Shows up on the audit log.
        """
        if self._original_response_message:
            await self._original_response_message.delete(delay=delay, reason=reason)


Context = BridgeExtContext | BridgeApplicationContext
"""
A Union class for either :class:`BridgeExtContext` or :class:`BridgeApplicationContext`.
Can be used as a type hint for Context for bridge commands.
"""
