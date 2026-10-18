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

import asyncio
import contextlib
import functools
import inspect
import re
import types
from collections.abc import (
    Callable,
    Coroutine,
    Generator,
    Iterable,
    Iterator,
)
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Concatenate,
    Generic,
    Literal,
    Union,
    cast,
    get_args,
    get_origin,
    overload,
)

from typing_extensions import ParamSpec, Self, TypeVar

from ..channel import PartialMessageable, _threaded_guild_channel_factory
from ..enums import (
    EntryPointHandler,
    Enum as DiscordEnum,
    IntegrationType,
    InteractionContextType,
    SlashCommandOptionType,
)
from ..errors import (
    ApplicationCommandError,
    ApplicationCommandInvokeError,
    CheckFailure,
    ClientException,
    InvalidArgument,
    ValidationError,
)
from ..guild import Guild
from ..member import Member
from ..message import Attachment, Message
from ..object import Object
from ..role import Role
from ..threads import Thread
from ..user import User
from ..utils import MISSING, async_all, maybe_coroutine, utcnow, warn_deprecated
from .cooldowns import resolve_cooldown_settings
from .options import Option, OptionChoice, _input_type_of

__all__ = (
    "ApplicationCommand",
    "ContextMenuCommand",
    "EntryPointCommand",
    "MessageCommand",
    "SlashCommand",
    "SlashCommandGroup",
    "UserCommand",
    "_BaseCommand",
    "application_command",
    "command",
    "entry_point_command",
    "message_command",
    "slash_command",
    "user_command",
)

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from typing import TypeGuard

    from typing_extensions import Never

    from .. import Permissions
    from ..abc import MessageableChannel
    from ..cog import Cog
    from ..ext.commands import Context
    from ..guild import PartialGuild
    from ..types.interactions import InteractionData
    from .context import ApplicationContext, AutocompleteContext
    from .cooldowns import BucketType, Cooldown, CooldownMapping, MaxConcurrency


async def _resolve_interaction_member(
    ctx: ApplicationContext, payload: Any, user_id: int
) -> Member:
    state = ctx.interaction._state
    guild = ctx.guild
    if not isinstance(guild, Guild):
        guild = await state._get_guild(ctx.interaction.guild_id)
    if guild is None:
        return Member(
            state=state, data=payload, guild=cast("Guild | PartialGuild", ctx.guild)
        )
    return await guild._get_and_update_member(
        payload, user_id, state.member_cache_flags.interaction
    )


async def _resolve_cached_channel(
    ctx: ApplicationContext, channel_id: int
) -> Any | None:
    guild_id = ctx.interaction.guild_id
    if guild_id is None:
        return None
    return await ctx.interaction._state._resolve_guild_channel(guild_id, channel_id)


T = TypeVar("T", default=Any)
CogT = TypeVar("CogT", bound="Cog", default=Any)
P = ParamSpec("P", default=...)
CommandT = TypeVar("CommandT", bound="ApplicationCommand[Any, ..., Any]")
SlashCommandT = TypeVar("SlashCommandT", bound="SlashCommand[Any, ..., Any]")
CoroFuncT = TypeVar("CoroFuncT", bound="Callable[..., Coro[Any]]")

Coro = Coroutine[Any, Any, T]

if TYPE_CHECKING:
    Callback = (
        Callable[Concatenate[CogT, ApplicationContext, P], Coro[T]]
        | Callable[Concatenate[ApplicationContext, P], Coro[T]]
    )
    Check = Callable[[ApplicationContext], bool | Awaitable[bool]]
    Hook = (
        Callable[[Cog, ApplicationContext], Coro[Any]]
        | Callable[[ApplicationContext], Coro[Any]]
    )
    Error = (
        Callable[[Cog, ApplicationContext, Exception], Coro[Any]]
        | Callable[[ApplicationContext, Exception], Coro[Any]]
    )


def wrap_callback(
    coro: Callable[..., Coro[T]],
) -> Callable[..., Coro[T | None]]:
    from ..ext.commands.errors import CommandError

    @functools.wraps(coro)
    async def wrapped(*args: Any, **kwargs: Any) -> T | None:
        try:
            ret = await coro(*args, **kwargs)
        except ApplicationCommandError:
            raise
        except CommandError:
            raise
        except asyncio.CancelledError:
            return None
        except Exception as exc:
            raise ApplicationCommandInvokeError(exc) from exc
        return ret

    return wrapped


def hooked_wrapped_callback(
    command: ApplicationCommand[Any, ..., Any],
    ctx: ApplicationContext,
    coro: Callable[[ApplicationContext], Coro[T]],
) -> Callable[[ApplicationContext], Coro[T | None]]:
    from ..ext.commands.errors import CommandError

    @functools.wraps(coro)
    async def wrapped(arg: ApplicationContext) -> T | None:
        try:
            ret = await coro(arg)
        except ApplicationCommandError:
            raise
        except CommandError:
            raise
        except asyncio.CancelledError:
            return None
        except Exception as exc:
            raise ApplicationCommandInvokeError(exc) from exc
        finally:
            if (
                hasattr(command, "_max_concurrency")
                and command._max_concurrency is not None
            ):
                await command._max_concurrency.release(ctx)
            await command.call_after_hooks(ctx)
        return ret

    return wrapped


def _describe_cog(
    command: ApplicationCommand[Any, ..., Any], cog: Cog | None = None
) -> str:
    cog = cog or command.cog
    if cog is not None:
        return f"the cog {cog.__cog_name__!r}"
    if command._cog_class is not None:
        return f"the cog {command._cog_class.__cog_name__!r}"
    return "another command"


def unwrap_function(function: Callable[..., Any]) -> Callable[..., Any]:
    partial = functools.partial
    while True:
        wrapped = getattr(function, "__wrapped__", None)
        if wrapped is not None:
            function = cast("Callable[..., Any]", wrapped)
        elif isinstance(function, partial):
            function = cast("Callable[..., Any]", function.func)
        else:
            return function


def _validate_names(obj: Option | ApplicationCommand[Any, ..., Any]) -> None:
    validate_chat_input_name(obj.name)
    if obj.name_localizations:
        for locale, string in obj.name_localizations.items():
            validate_chat_input_name(string, locale=locale)


def _validate_descriptions(obj: Option | ApplicationCommand[Any, ..., Any]) -> None:
    validate_chat_input_description(obj.description)
    if obj.description_localizations:
        for locale, string in obj.description_localizations.items():
            validate_chat_input_description(string, locale=locale)


def _mark_callback(obj: object, name: str, value: object) -> None:  # pyright: ignore[reportUnusedFunction]
    """Sets a marker attribute on a callback.

    The attribute is read when the callback is turned into a command or a listener.

    Parameters
    ----------
    obj: :class:`object`
        The callback to mark.
    name: :class:`str`
        The name of the attribute to set.
    value: :class:`object`
        The value of the attribute.
    """
    setattr(obj, name, value)


def _resolve_checks(func: Callable[..., Any], kwargs: dict[str, Any]) -> list[Check]:
    checks: list[Check] | None = getattr(func, "__commands_checks__", None)
    if checks is None:
        return kwargs.get("checks", [])
    checks.reverse()
    return checks


async def _call_local_hook(
    hook: Hook, cog: Cog | None, ctx: ApplicationContext
) -> None:
    # should be cog if @commands.before_invoke is used
    instance = getattr(hook, "__self__", cog)
    # __self__ only exists for methods, not functions
    # however, if @command.before_invoke is used, it will be a function
    func = cast("Callable[..., Coro[Any]]", hook)
    if instance:
        await func(instance, ctx)
    else:
        await func(ctx)


def _interaction_data(ctx: ApplicationContext | AutocompleteContext) -> dict[str, Any]:
    # The payload of a command interaction is read as a plain mapping, its keys
    # depend on the kind of command and on the option that is being resolved.
    return cast("dict[str, Any]", ctx.interaction.data)


def _enum_values(values: Iterable[Enum] | None) -> list[Any]:
    # Set to their defaults when the command is added to the bot.
    return [value.value for value in cast("Iterable[Enum]", values)]


def _is_slash_member(
    value: object,
) -> TypeGuard[SlashCommand[Any, ..., Any] | SlashCommandGroup]:
    return isinstance(value, (SlashCommand, SlashCommandGroup))


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def _last_resolved(entries: dict[str, dict[str, Any]]) -> Any:
    entry: dict[str, Any] | None = None
    for snowflake, value in entries.items():
        value["id"] = int(snowflake)
        entry = value
    if entry is None:
        raise ClientException("The interaction does not resolve its target.")
    return entry


def _is_none(value: object) -> bool:
    return value is None


def _is_enum_class(value: object) -> bool:
    return isinstance(value, type) and issubclass(value, (DiscordEnum, Enum))


def _is_union_of(annotation: object, raw_type: object) -> bool:
    return isinstance(raw_type, tuple) and annotation == cast("Any", Union)[raw_type]


def _as_cooldown_target(ctx: ApplicationContext) -> Message:
    # Application commands duck-type their context as the message the
    # cooldown buckets and the concurrency limits are keyed on.
    return cast("Message", ctx)


class _BaseCommand:
    __slots__ = ()

    if TYPE_CHECKING:
        # What the application commands and the prefix commands have in common.
        name: str
        parent: Any
        cog: Any
        callback: Any
        qualified_name: Any

        def _set_cog(self, cog: Any) -> None: ...
        def _update_copy(self, kwargs: dict[str, Any]) -> Self: ...


class ApplicationCommand(_BaseCommand, Generic[CogT, P, T]):
    """The base class of the application commands.

    This is not created manually, use :func:`slash_command`,
    :func:`user_command`, :func:`message_command` or
    :func:`entry_point_command` instead.

    Attributes
    ----------
    name: :class:`str`
        The name of the command.
    id: Optional[:class:`int`]
        The ID of the command once it is registered, ``None`` before.
    guild_ids: Optional[List[:class:`int`]]
        The ids of the guilds where this command will be registered.
    parent: Optional[:class:`SlashCommandGroup`]
        The group this command belongs to, ``None`` if there is none.
    cog: Optional[:class:`Cog`]
        The cog that this command belongs to. ``None`` if there isn't one.
    checks: List[Callable[[:class:`.ApplicationContext`], :class:`bool`]]
        The predicates that verify if the command could be executed.
    """

    __original_kwargs__: dict[str, Any]
    _cog: Cog | None = None
    _cog_class: type[Cog] | None = None
    name: str
    description: str
    name_localizations: dict[str, str]
    description_localizations: dict[str, str]
    parent: SlashCommandGroup | None
    on_error: Callable[..., Coro[Any]]
    _before_invoke: Hook | None
    _after_invoke: Hook | None

    if TYPE_CHECKING:
        type: int

        async def _invoke(self, ctx: ApplicationContext) -> None: ...
        async def invoke_autocomplete_callback(self, ctx: AutocompleteContext) -> None:
            """|coro|

            Invokes the autocomplete callback of the focused option, only
            slash commands and slash command groups have one.

            Parameters
            ----------
            ctx: :class:`.AutocompleteContext`
                The autocomplete context to invoke the callback with.
            """

    def __init__(self, func: Callable[..., Any], **kwargs: Any) -> None:
        cooldown = getattr(func, "__commands_cooldown__", kwargs.get("cooldown"))
        max_concurrency = getattr(
            func, "__commands_max_concurrency__", kwargs.get("max_concurrency")
        )
        self._buckets: CooldownMapping
        self._max_concurrency: MaxConcurrency | None
        self._buckets, self._max_concurrency = resolve_cooldown_settings(
            cooldown=cooldown, max_concurrency=max_concurrency
        )

        self._callback: Callable[..., Coro[T]] = func
        self.module: str | None = None

        self.name: str = kwargs.get("name", func.__name__)

        self.checks: list[Check] = _resolve_checks(func, kwargs)
        self.id: int | None = kwargs.get("id")
        self.guild_ids: list[int] | None = kwargs.get("guild_ids")
        self.parent = kwargs.get("parent")

        # Permissions
        self.default_member_permissions: Permissions | None = getattr(
            func,
            "__default_member_permissions__",
            kwargs.get("default_member_permissions"),
        )
        self.nsfw: bool | None = getattr(func, "__nsfw__", kwargs.get("nsfw", False))

        integration_types = getattr(
            func, "__integration_types__", kwargs.get("integration_types")
        )
        contexts = getattr(func, "__contexts__", kwargs.get("contexts"))
        guild_only = getattr(func, "__guild_only__", kwargs.get("guild_only", MISSING))
        if guild_only is not MISSING:
            warn_deprecated(
                "guild_only",
                "contexts",
                "2.6",
                reference="https://docs.discord.com/developers/change-log#user-installable-apps-preview",
            )
        if contexts and guild_only:
            raise InvalidArgument(
                "cannot pass both 'contexts' and 'guild_only' to ApplicationCommand"
            )
        if self.guild_ids and (
            (contexts is not None) or guild_only or integration_types
        ):
            raise InvalidArgument(
                "the 'contexts' and 'integration_types' parameters are not available for guild commands"
            )

        if guild_only:
            contexts = {InteractionContextType.guild}
        self.contexts: set[InteractionContextType] | None = contexts
        self.integration_types: set[IntegrationType] | None = integration_types

    def __repr__(self) -> str:
        return f"<discord.commands.{self.__class__.__name__} name={self.name}>"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, self.__class__)
            and self.qualified_name == other.qualified_name
            and self.guild_ids == other.guild_ids
        )

    __hash__: ClassVar[None]  # type: ignore[assignment]

    async def __call__(
        self, ctx: ApplicationContext, *args: P.args, **kwargs: P.kwargs
    ) -> T:
        """|coro|

        Calls the command's callback.

        This method bypasses all checks that a command has and does not
        convert the arguments beforehand, so take care to pass the correct
        arguments in.
        """
        if self.cog is not None:
            return await self._call_callback(self.cog, ctx, *args, **kwargs)
        return await self._call_callback(ctx, *args, **kwargs)

    def _call_callback(self, *args: Any, **kwargs: Any) -> Coro[T]:
        # The callback takes the cog first when it is a method of one, and the
        # arguments to pass depend on the kind of command, so it is called untyped.
        return self._callback(*args, **kwargs)

    @property
    def callback(
        self,
    ) -> (
        Callable[Concatenate[CogT, ApplicationContext, P], Coro[T]]
        | Callable[Concatenate[ApplicationContext, P], Coro[T]]
    ):
        """The coroutine that is executed when the command is called."""
        return self._callback

    @callback.setter
    def callback(
        self,
        function: (
            Callable[Concatenate[CogT, ApplicationContext, P], Coro[T]]
            | Callable[Concatenate[ApplicationContext, P], Coro[T]]
        ),
    ) -> None:
        self._callback = cast("Callable[..., Coro[T]]", function)
        unwrap = unwrap_function(function)
        self.module = unwrap.__module__

    @property
    def guild_only(self) -> bool:
        """Whether the command is only usable inside a guild.

        .. deprecated:: 2.6
            Use :attr:`contexts` instead.
        """
        warn_deprecated(
            "guild_only",
            "contexts",
            "2.6",
            reference="https://docs.discord.com/developers/change-log#user-installable-apps-preview",
        )
        return (
            self.contexts is not None
            and InteractionContextType.guild in self.contexts
            and len(self.contexts) == 1
        )

    @guild_only.setter
    def guild_only(self, value: bool) -> None:
        warn_deprecated(
            "guild_only",
            "contexts",
            "2.6",
            reference="https://docs.discord.com/developers/change-log#user-installable-apps-preview",
        )
        if value:
            self.contexts = {InteractionContextType.guild}
        else:
            self.contexts = {
                InteractionContextType.guild,
                InteractionContextType.bot_dm,
                InteractionContextType.private_channel,
            }

    async def _prepare_cooldowns(self, ctx: ApplicationContext) -> None:
        if self._buckets.valid:
            current = utcnow().timestamp()
            bucket = await self._buckets.get_bucket_async(
                _as_cooldown_target(ctx), current
            )

            if not _is_none(bucket):
                retry_after = bucket.update_rate_limit(current)

                if retry_after:
                    from ..ext.commands.errors import CommandOnCooldown

                    raise CommandOnCooldown(
                        bucket, retry_after, cast("BucketType", self._buckets.type)
                    )

    async def prepare(self, ctx: ApplicationContext) -> None:
        """|coro|

        Prepares the context to invoke this command, running its checks,
        concurrency limit, cooldown and before invoke hooks.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context to prepare.
        """
        # This should be same across all 3 types
        await self._prepare(ctx, self)

    async def _prepare(
        self, ctx: ApplicationContext, command: ApplicationCommand[Any, ..., Any]
    ) -> None:
        ctx.command = command

        if not await self.can_run(ctx):
            raise CheckFailure(
                f"The check functions for the command {self.name} failed"
            )

        if self._max_concurrency is not None:
            # For this application, context can be duck-typed as a Message
            await self._max_concurrency.acquire(ctx)

        try:
            await self._prepare_cooldowns(ctx)
            await self.call_before_hooks(ctx)
        except:
            if self._max_concurrency is not None:
                await self._max_concurrency.release(ctx)
            raise

    def is_on_cooldown(self, ctx: ApplicationContext) -> bool:
        """Checks whether the command is currently on cooldown.

        .. note::

            This uses the current time instead of the interaction time.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context to use when checking the command's cooldown status.

        Returns
        -------
        :class:`bool`
            A boolean indicating if the command is on cooldown.
        """
        if not self._buckets.valid:
            return False

        bucket = self._buckets.get_bucket(_as_cooldown_target(ctx))
        current = utcnow().timestamp()
        return bucket.get_tokens(current) == 0

    def reset_cooldown(self, ctx: ApplicationContext) -> None:
        """Resets the cooldown on this command.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context to reset the cooldown under.
        """
        if self._buckets.valid:
            bucket = self._buckets.get_bucket(_as_cooldown_target(ctx))
            bucket.reset()

    def get_cooldown_retry_after(self, ctx: ApplicationContext) -> float:
        """Retrieves the amount of seconds before this command can be tried again.

        .. note::

            This uses the current time instead of the interaction time.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context to retrieve the cooldown from.

        Returns
        -------
        :class:`float`
            The amount of time left on this command's cooldown in seconds.
            If this is ``0.0`` then the command isn't on cooldown.
        """
        if self._buckets.valid:
            bucket = self._buckets.get_bucket(_as_cooldown_target(ctx))
            current = utcnow().timestamp()
            return bucket.get_retry_after(current)

        return 0.0

    async def check_on_cooldown(self, ctx: ApplicationContext) -> bool:
        """|coro|

        Like :meth:`is_on_cooldown` but resolving the bucket with
        :meth:`.CooldownMapping.get_bucket_async`, so ``BucketType.role`` and
        ``BucketType.category`` work with every cache backend.

        .. versionadded:: 3.0

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context to use when checking the command's cooldown status.

        Returns
        -------
        :class:`bool`
            A boolean indicating if the command is on cooldown.
        """
        if not self._buckets.valid:
            return False

        current = utcnow().timestamp()
        bucket = await self._buckets.get_bucket_async(_as_cooldown_target(ctx), current)
        return bucket.get_tokens(current) == 0

    async def reset_cooldown_async(self, ctx: ApplicationContext) -> None:
        """|coro|

        Like :meth:`reset_cooldown` but resolving the bucket with
        :meth:`.CooldownMapping.get_bucket_async`.

        .. versionadded:: 3.0

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context to reset the cooldown under.
        """
        if self._buckets.valid:
            bucket = await self._buckets.get_bucket_async(_as_cooldown_target(ctx))
            bucket.reset()

    async def cooldown_retry_after(self, ctx: ApplicationContext) -> float:
        """|coro|

        Like :meth:`get_cooldown_retry_after` but resolving the bucket with
        :meth:`.CooldownMapping.get_bucket_async`.

        .. versionadded:: 3.0

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context to retrieve the cooldown from.

        Returns
        -------
        :class:`float`
            The amount of time left on this command's cooldown in seconds.
            If this is ``0.0`` then the command isn't on cooldown.
        """
        if self._buckets.valid:
            current = utcnow().timestamp()
            bucket = await self._buckets.get_bucket_async(
                _as_cooldown_target(ctx), current
            )
            return bucket.get_retry_after(current)

        return 0.0

    async def invoke(self, ctx: ApplicationContext) -> None:
        """|coro|

        Prepares the context and invokes this command, running the hooks
        around it.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context to invoke the command with.
        """
        await self.prepare(ctx)

        injected = hooked_wrapped_callback(self, ctx, self._invoke)
        await injected(ctx)

    async def can_run(self, ctx: ApplicationContext) -> bool:
        """|coro|

        Checks whether the command can be run, calling the global checks, the
        cog check, the checks of the parent group and the checks of the command.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context to check.

        Returns
        -------
        :class:`bool`
            Whether all the checks passed.

        Raises
        ------
        CheckFailure
            A global check failed.
        """
        if not await ctx.bot.can_run(ctx):
            raise CheckFailure(
                f"The global check functions for command {self.name} failed."
            )

        predicates = self.checks
        if self.parent is not None:
            # parent checks should be run first
            predicates = self.parent.checks + predicates

        cog = self.cog
        if cog is not None:
            local_check = cog._get_overridden_method(cog.cog_check)
            if local_check is not None:
                ret = await maybe_coroutine(local_check, ctx)
                if not ret:
                    return False

        if not predicates:
            # since we have no checks, then we just return True.
            return True

        return await async_all(predicate(ctx) for predicate in predicates)

    async def dispatch_error(self, ctx: ApplicationContext, error: Exception) -> None:
        """|coro|

        Calls the local error handlers of this command, of its cog and of the
        cogs of its groups, then dispatches ``on_application_command_error``.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context the error happened in.
        error: :class:`Exception`
            The error that was raised.
        """
        ctx.command_failed = True
        cog = self.cog
        try:
            coro = self.on_error
        except AttributeError:
            pass
        else:
            injected = wrap_callback(coro)
            if cog is not None:
                await injected(cog, ctx, error)
            else:
                await injected(ctx, error)

        try:
            if cog is not None:
                local = cog.__class__._get_overridden_method(cog.cog_command_error)
                if local is not None:
                    wrapped = wrap_callback(local)
                    await wrapped(ctx, error)
            await self._dispatch_group_owner_errors(ctx, error)
        finally:
            ctx.bot.dispatch("application_command_error", ctx, error)

    def _group_owner_cogs(self) -> list[Cog]:
        owners: list[Cog] = []
        group = getattr(self, "parent", None)
        while group is not None:
            owner = group.cog
            if (
                owner is not None
                and owner is not self.cog
                and all(owner is not seen for seen in owners)
            ):
                owners.append(owner)
            group = group.parent
        return owners

    async def _dispatch_group_owner_errors(
        self, ctx: ApplicationContext, error: Exception
    ) -> None:
        for owner in self._group_owner_cogs():
            local = owner.__class__._get_overridden_method(owner.cog_command_error)
            if local is not None:
                await wrap_callback(local)(ctx, error)

    def _get_signature_parameters(self) -> dict[str, inspect.Parameter]:
        return dict(inspect.signature(self.callback).parameters)

    def error(self, coro: CoroFuncT) -> CoroFuncT:
        """A decorator that registers a coroutine as a local error handler.

        A local error handler is an :func:`.on_command_error` event limited to
        a single command. However, the :func:`.on_command_error` is still
        invoked afterwards as the catch-all.

        Parameters
        ----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the local error handler.

        Raises
        ------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError("The error handler must be a coroutine.")

        self.on_error = coro
        return coro

    def has_error_handler(self) -> bool:
        """Checks whether the command has an error handler registered."""
        return hasattr(self, "on_error")

    def before_invoke(self, coro: CoroFuncT) -> CoroFuncT:
        """A decorator that registers a coroutine as a pre-invoke hook.

        A pre-invoke hook is called directly before the command is
        called. This makes it a useful function to set up database
        connections or any type of set up required.

        This pre-invoke hook takes a sole parameter, an :class:`.ApplicationContext`.
        See :meth:`.Bot.before_invoke` for more info.

        Parameters
        ----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the pre-invoke hook.

        Raises
        ------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError("The pre-invoke hook must be a coroutine.")

        self._before_invoke = coro
        return coro

    def after_invoke(self, coro: CoroFuncT) -> CoroFuncT:
        """A decorator that registers a coroutine as a post-invoke hook.

        A post-invoke hook is called directly after the command is
        called. This makes it a useful function to clean-up database
        connections or any type of clean up required.

        This post-invoke hook takes a sole parameter, an :class:`.ApplicationContext`.
        See :meth:`.Bot.after_invoke` for more info.

        Parameters
        ----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the post-invoke hook.

        Raises
        ------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError("The post-invoke hook must be a coroutine.")

        self._after_invoke = coro
        return coro

    async def call_before_hooks(self, ctx: ApplicationContext) -> None:
        """|coro|

        Calls the pre-invoke hooks of this command, of its cog and of the bot.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context the hooks are called with.
        """
        # now that we're done preparing we can call the pre-command hooks
        # first, call the command local hook:
        cog = self.cog
        if self._before_invoke is not None:
            await _call_local_hook(self._before_invoke, cog, ctx)

        for owner in reversed(self._group_owner_cogs()):
            hook = owner.__class__._get_overridden_method(owner.cog_before_invoke)
            if hook is not None:
                await hook(ctx)

        # call the cog local hook if applicable:
        if cog is not None:
            hook = cog.__class__._get_overridden_method(cog.cog_before_invoke)
            if hook is not None:
                await hook(ctx)

        # call the bot global hook if necessary
        hook = ctx.bot._before_invoke
        if hook is not None:
            await hook(ctx)

    async def call_after_hooks(self, ctx: ApplicationContext) -> None:
        """|coro|

        Calls the post-invoke hooks of this command, of its cog and of the bot.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context the hooks are called with.
        """
        cog = self.cog
        if self._after_invoke is not None:
            await _call_local_hook(self._after_invoke, cog, ctx)

        # call the cog local hook if applicable:
        if cog is not None:
            hook = cog.__class__._get_overridden_method(cog.cog_after_invoke)
            if hook is not None:
                await hook(ctx)

        for owner in self._group_owner_cogs():
            hook = owner.__class__._get_overridden_method(owner.cog_after_invoke)
            if hook is not None:
                await hook(ctx)

        hook = ctx.bot._after_invoke
        if hook is not None:
            await hook(ctx)

    @property
    def cooldown(self) -> Cooldown | None:
        """The cooldown applied when the command is invoked, if any."""
        return self._buckets._cooldown

    @property
    def full_parent_name(self) -> str:
        """Retrieves the fully qualified parent command name.

        This the base command name required to execute it. For example,
        in ``/one two three`` the parent name would be ``one two``.
        """
        entries: list[str] = []
        command: ApplicationCommand[Any, ..., Any] = self
        while command.parent is not None and hasattr(command.parent, "name"):
            command = command.parent
            entries.append(command.name)

        return " ".join(reversed(entries))

    @property
    def qualified_name(self) -> str:
        """Retrieves the fully qualified command name.

        This is the full parent name with the command name as well.
        For example, in ``/one two three`` the qualified name would be
        ``one two three``.
        """
        parent = self.full_parent_name

        if parent:
            return f"{parent} {self.name}"
        return self.name

    @property
    def qualified_id(self) -> int:
        """Retrieves the fully qualified command ID.

        This is the root parent ID. For example, in ``/one two three``
        the qualified ID would return ``one.id``.
        """
        if self.id is None:
            if self.parent is None:
                raise AttributeError(f"The command {self.name!r} has no ID")
            return self.parent.qualified_id
        return self.id

    def to_dict(self) -> dict[str, Any]:
        """Converts this command into the payload sent to Discord."""
        raise NotImplementedError

    def __str__(self) -> str:
        return self.qualified_name

    @property
    def cog(self) -> Cog | None:
        """The cog that this command belongs to, ``None`` if there isn't one."""
        return self._cog

    @cog.setter
    def cog(self, value: Cog | None) -> None:
        self._cog = value

    def _set_cog(self, cog: Cog | None) -> None:
        self.cog = cog

    def _unset_cog(self) -> None:
        self.cog = None

    def _is_owned_by_other(self, cog: Cog | None) -> bool:
        owner = self._cog_class
        return owner is not None and not isinstance(cog, owner)

    def _ensure_assignment_on_copy(self, other: Self) -> Self:
        other._before_invoke = self._before_invoke
        other._after_invoke = self._after_invoke
        if self.checks != other.checks:
            other.checks = self.checks.copy()

        with contextlib.suppress(AttributeError):
            other.on_error = self.on_error
        return other

    def _update_copy(self, kwargs: dict[str, Any]) -> Self:
        if kwargs:
            kw = kwargs.copy()
            kw.update(self.__original_kwargs__)
            copy = self.__class__(self.callback, **kw)
            return self._ensure_assignment_on_copy(copy)
        return self.copy()

    def copy(self) -> Self:
        """Creates a copy of this command.

        Returns
        -------
        :class:`ApplicationCommand`
            A new instance of this command.
        """
        ret = self.__class__(self.callback, **self.__original_kwargs__)
        return self._ensure_assignment_on_copy(ret)


class SlashCommand(ApplicationCommand[CogT, P, T]):
    r"""A class that implements the protocol for a slash command.

    These are not created manually, instead they are created via the
    decorator or functional interface.

    .. versionadded:: 2.0

    Attributes
    ----------
    name: :class:`str`
        The name of the command.
    callback: :ref:`coroutine <coroutine>`
        The coroutine that is executed when the command is called.
    description: Optional[:class:`str`]
        The description for the command.
    guild_ids: Optional[List[:class:`int`]]
        The ids of the guilds where this command will be registered.
    options: List[:class:`Option`]
        The parameters for this command.
    parent: Optional[:class:`SlashCommandGroup`]
        The parent group that this command belongs to. ``None`` if there
        isn't one.
    mention: :class:`str`
        Returns a string that allows you to mention the slash command.
    guild_only: :class:`bool`
        Whether the command should only be usable inside a guild.

        .. deprecated:: 2.6
            Use the :attr:`contexts` parameter instead.
    nsfw: :class:`bool`
        Whether the command should be restricted to 18+ channels and users.
        Apps intending to be listed in the App Directory cannot have NSFW commands.
    default_member_permissions: :class:`~discord.Permissions`
        The default permissions a member needs to be able to run the command.
    cog: Optional[:class:`Cog`]
        The cog that this command belongs to. ``None`` if there isn't one.
    checks: List[Callable[[:class:`.ApplicationContext`], :class:`bool`]]
        A list of predicates that verifies if the command could be executed
        with the given :class:`.ApplicationContext` as the sole parameter. If an exception
        is necessary to be thrown to signal failure, then one inherited from
        :exc:`.ApplicationCommandError` should be used. Note that if the checks fail then
        :exc:`.CheckFailure` exception is raised to the :func:`.on_application_command_error`
        event.
    cooldown: Optional[:class:`~discord.ext.commands.Cooldown`]
        The cooldown applied when the command is invoked. ``None`` if the command
        doesn't have a cooldown.
    name_localizations: Dict[:class:`str`, :class:`str`]
        The name localizations for this command. The values of this should be ``"locale": "name"``. See
        `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    description_localizations: Dict[:class:`str`, :class:`str`]
        The description localizations for this command. The values of this should be ``"locale": "description"``.
        See `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    integration_types: Set[:class:`IntegrationType`]
        The type of installation this command should be available to. For instance, if set to
        :attr:`IntegrationType.user_install`, the command will only be available to users with
        the application installed on their account. Not applicable for guild commands.
    contexts: Set[:class:`InteractionContextType`]
        The location where this command can be used. Cannot be set if this is a guild command.
    """

    type = 1

    parent: SlashCommandGroup | None

    def __new__(cls, *_args: Any, **kwargs: Any) -> Self:
        """Creates the command, keeping the keyword arguments to copy it later."""
        self = super().__new__(cls)

        self.__original_kwargs__ = kwargs.copy()
        return self

    def __init__(self, func: Callback[CogT, P, T], *args: Any, **kwargs: Any) -> None:
        super().__init__(func, **kwargs)
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Callback must be a coroutine.")
        self.callback = func

        self.name_localizations: dict[str, str] = kwargs.get(
            "name_localizations", MISSING
        )
        _validate_names(self)

        description = kwargs.get("description") or (
            inspect.cleandoc(func.__doc__).splitlines()[0]
            if func.__doc__ is not None
            else "No description provided"
        )

        self.description: str = description
        self.description_localizations: dict[str, str] = kwargs.get(
            "description_localizations", MISSING
        )
        _validate_descriptions(self)

        self.attached_to_group: bool = False

        self._options_kwargs = kwargs.get("options", [])
        self.options: list[Option] = []
        self._validate_parameters()

        self.checks = _resolve_checks(func, kwargs)

        self._before_invoke = None
        self._after_invoke = None

    def _validate_parameters(self) -> None:
        params = self._get_signature_parameters()
        if kwop := self._options_kwargs:
            self.options = self._match_option_param_names(params, kwop)
        else:
            self.options = self._parse_options(params)

    def _declares_self(self) -> bool:
        prefix = getattr(self.callback, "__qualname__", "").rpartition(".")[0]
        if not prefix or prefix.endswith("<locals>"):
            return False
        return next(iter(self._get_signature_parameters()), None) == "self"

    def _check_required_params(
        self, params: dict[str, inspect.Parameter]
    ) -> Iterator[tuple[str, inspect.Parameter]]:
        items = iter(params.items())
        required_params = (
            ["self", "context"]
            if self.attached_to_group or self.cog or self._declares_self()
            else ["context"]
        )
        for p in required_params:
            if next(items, None) is None:
                raise ClientException(
                    f'Callback for {self.name} command is missing "{p}" parameter.'
                )

        return items

    def _parse_options(
        self, params: dict[str, inspect.Parameter], *, check_params: bool = True
    ) -> list[Option]:
        items = (
            self._check_required_params(params)
            if check_params
            else iter(params.items())
        )

        final_options: list[Option] = []
        for p_name, p_obj in items:
            option: Any = p_obj.annotation
            if option == inspect.Parameter.empty:
                option = str

            option = Option._strip_none_type(option)
            if self._is_typing_literal(option):
                literal_values = get_args(option)
                if not all(isinstance(v, (str, int, float)) for v in literal_values):
                    raise TypeError(
                        "Literal values for choices must be str, int, or float."
                    )

                value_type = type(cast("object", literal_values[0]))
                if not all(isinstance(v, value_type) for v in literal_values):
                    raise TypeError(
                        "All Literal values for choices must be of the same type."
                    )

                option = Option(
                    cast("Any", value_type),
                    choices=[
                        OptionChoice(name=str(v), value=v) for v in literal_values
                    ],
                )

            if self._is_typing_annotated(option):
                type_hint = get_args(option)[0]
                metadata = option.__metadata__
                # If multiple Options in metadata, the first will be used.
                option_gen = (elem for elem in metadata if isinstance(elem, Option))
                option = next(option_gen, Option())
                # Handle Optional
                if self._is_typing_optional(type_hint):
                    option.input_type = _input_type_of(get_args(type_hint)[0])
                    option.default = None
                else:
                    option.input_type = _input_type_of(type_hint)

            if self._is_typing_union(option):
                if self._is_typing_optional(option):
                    option = Option(option.__args__[0], default=None)
                else:
                    option = Option(option.__args__)

            if not isinstance(option, Option):
                if isinstance(p_obj.default, Option):
                    if _is_none(p_obj.default.input_type):
                        p_obj.default.input_type = _input_type_of(option)
                    option = p_obj.default
                else:
                    option = Option(option)

            if option.default is None and p_obj.default != inspect.Parameter.empty:
                if isinstance(p_obj.default, Option):
                    pass
                elif _is_enum_class(p_obj.default):
                    option = Option(p_obj.default)
                else:
                    option.default = p_obj.default
                    option.required = False
            if option.name is None:
                option.name = p_name
            if option.name != p_name or option._parameter_name is None:
                option._parameter_name = p_name

            _validate_names(option)
            _validate_descriptions(option)

            final_options.append(option)

        return final_options

    def _match_option_param_names(
        self, params: dict[str, inspect.Parameter], options: Iterable[Option]
    ) -> list[Option]:
        option_list = list(options)
        items = self._check_required_params(params)

        check_annotations: list[Callable[[Option, Any], bool]] = [
            lambda o, _: (
                o.input_type == SlashCommandOptionType.string
                and o.converter is not None
            ),  # pass on converters
            lambda o, _: (
                not _is_none(o.input_type)
            ),  # pass on slash cmd option type enums
            lambda o, a: _is_union_of(a, o._raw_type),  # union types
            lambda o, a: (
                self._is_typing_optional(a)
                and not o.required
                and o._raw_type in a.__args__
            ),  # optional
            lambda o, a: (
                isinstance(a, type) and issubclass(a, o._raw_type)
            ),  # 'normal' types
        ]
        for o in option_list:
            _validate_names(o)
            _validate_descriptions(o)
            try:
                p_name, p_obj = next(items)
            except StopIteration:  # not enough params for all the options
                raise ClientException(
                    "Too many arguments passed to the options kwarg."
                ) from None
            annotation: Any = p_obj.annotation

            if not any(check(o, annotation) for check in check_annotations):
                raise TypeError(
                    f"Parameter {p_name} does not match input type of {o.name}."
                )
            o._parameter_name = p_name

        left_out_params = dict(items)
        option_list.extend(self._parse_options(left_out_params, check_params=False))

        return option_list

    def _is_typing_union(self, annotation: Any) -> bool:
        return getattr(annotation, "__origin__", None) is Union or type(
            annotation
        ) is getattr(types, "UnionType", Union)

    def _is_typing_optional(self, annotation: Any) -> bool:
        return self._is_typing_union(annotation) and type(None) in annotation.__args__

    def _is_typing_literal(self, annotation: Any) -> bool:
        return get_origin(annotation) is Literal

    def _is_typing_annotated(self, annotation: Any) -> bool:
        return get_origin(annotation) is Annotated

    @property
    def cog(self) -> Cog | None:
        """The cog that this command belongs to, ``None`` if there isn't one."""
        return self._cog

    @cog.setter
    def cog(self, value: Cog | None) -> None:
        old_cog = self.cog
        self._cog = value

        if (old_cog is None and value is not None) or (
            value is None and old_cog is not None
        ):
            self._validate_parameters()

    def _unset_cog(self) -> None:
        self._cog = None

    @property
    def is_subcommand(self) -> bool:
        """Whether this command is a subcommand of a group."""
        return self.parent is not None

    @property
    def mention(self) -> str:
        """A string that allows you to mention the slash command."""
        return f"</{self.qualified_name}:{self.qualified_id}>"

    def to_dict(self) -> dict[str, Any]:
        """Converts this command into the payload sent to Discord."""
        as_dict: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "options": [o.to_dict() for o in self.options],
        }
        if self.name_localizations is not MISSING:
            as_dict["name_localizations"] = self.name_localizations
        if self.description_localizations is not MISSING:
            as_dict["description_localizations"] = self.description_localizations
        if self.is_subcommand:
            as_dict["type"] = SlashCommandOptionType.sub_command.value

        if self.nsfw is not None:
            as_dict["nsfw"] = self.nsfw

        if self.default_member_permissions is not None:
            as_dict["default_member_permissions"] = (
                self.default_member_permissions.value
            )

        if not self.guild_ids and not self.is_subcommand:
            as_dict["integration_types"] = _enum_values(self.integration_types)
            as_dict["contexts"] = _enum_values(self.contexts)

        return as_dict

    async def _invoke(self, ctx: ApplicationContext) -> None:
        # TODO: Parse the args better
        kwargs: dict[Any, Any] = {}
        data = _interaction_data(ctx)
        for option_data in data.get("options", []):
            op = next((o for o in self.options if o.name == option_data["name"]), None)
            if op is None:
                continue
            arg: Any = option_data["value"]

            # Checks if input_type is user, role or channel
            if op.input_type in (
                SlashCommandOptionType.user,
                SlashCommandOptionType.role,
                SlashCommandOptionType.channel,
                SlashCommandOptionType.attachment,
                SlashCommandOptionType.mentionable,
            ):
                resolved = data.get("resolved", {})
                if (
                    op.input_type
                    in (SlashCommandOptionType.user, SlashCommandOptionType.mentionable)
                    and (_data := resolved.get("members", {}).get(arg)) is not None
                ):
                    # The option type is a user, we resolved a member from the snowflake and assigned it to _data
                    if (_user_data := resolved.get("users", {}).get(arg)) is not None:
                        # We resolved the user from the user id
                        _data["user"] = _user_data
                    arg = await _resolve_interaction_member(ctx, _data, int(arg))
                elif op.input_type is SlashCommandOptionType.mentionable:
                    if (_data := resolved.get("users", {}).get(arg)) is not None:
                        arg = User(state=ctx.interaction._state, data=_data)
                    elif (_data := resolved.get("roles", {}).get(arg)) is not None:
                        arg = Role(
                            state=ctx.interaction._state,
                            data=_data,
                            guild=cast("Guild", ctx.guild),
                        )
                    else:
                        arg = Object(id=int(arg))
                elif (
                    _data := resolved.get(f"{op.input_type.name}s", {}).get(arg)
                ) is not None:
                    if (
                        op.input_type is SlashCommandOptionType.channel
                        and (cached := await _resolve_cached_channel(ctx, int(arg)))
                        is not None
                    ):
                        _data["_invoke_flag"] = True
                        if isinstance(cached, Thread):
                            arg = await ctx.interaction._state._build_thread(
                                cast("Guild", ctx.guild), _data
                            )
                        else:
                            cached._update(ctx.guild, _data)
                            arg = cached
                    else:
                        obj_type: Any = None
                        kw: dict[str, Any] = {}
                        if op.input_type is SlashCommandOptionType.user:
                            obj_type = User
                        elif op.input_type is SlashCommandOptionType.role:
                            obj_type = Role
                            kw["guild"] = ctx.guild
                        elif op.input_type is SlashCommandOptionType.channel:
                            # NOTE:
                            # This is a fallback in case the channel/thread is not found in the
                            # guild's channels/threads. For channels, if this fallback occurs, at the very minimum,
                            # permissions will be incorrect due to a lack of permission_overwrite data.
                            # For threads, if this fallback occurs, info like thread owner id, message count,
                            # flags, and more will be missing due to a lack of data sent by Discord.
                            obj_type = _threaded_guild_channel_factory(_data["type"])[0]
                            kw["guild"] = ctx.guild
                        elif op.input_type is SlashCommandOptionType.attachment:
                            obj_type = Attachment
                        arg = obj_type(state=ctx.interaction._state, data=_data, **kw)
                else:
                    # We couldn't resolve the object, so we just return an empty object
                    arg = Object(id=int(arg))

            elif (
                op.input_type == SlashCommandOptionType.string
                and (converter := op.converter) is not None
            ):
                from discord.ext.commands import Converter

                if isinstance(converter, Converter):
                    if isinstance(converter, type):
                        arg = await converter().convert(
                            cast("Context[Any]", ctx), cast("str", arg)
                        )
                    else:
                        arg = await converter.convert(
                            cast("Context[Any]", ctx), cast("str", arg)
                        )

            elif op._raw_type in (
                SlashCommandOptionType.integer,
                SlashCommandOptionType.number,
                SlashCommandOptionType.string,
                SlashCommandOptionType.boolean,
            ):
                pass

            elif issubclass(op._raw_type, Enum):
                if isinstance(arg, str) and arg.isdigit():
                    try:
                        arg = op._raw_type(int(arg))
                    except ValueError:
                        arg = op._raw_type(arg)
                elif choice := next((c for c in op.choices if c.value == arg), None):
                    arg = getattr(op._raw_type, choice.name)

            kwargs[op._parameter_name] = arg

        for o in self.options:
            if o._parameter_name not in kwargs:
                kwargs[o._parameter_name] = o.default

        if self.cog is not None:
            await self._call_callback(self.cog, ctx, **kwargs)
        elif self.parent is not None and self.attached_to_group is True:
            await self._call_callback(self.parent, ctx, **kwargs)
        else:
            await self._call_callback(ctx, **kwargs)

    async def invoke_autocomplete_callback(self, ctx: AutocompleteContext) -> None:
        """|coro|

        Invokes the autocomplete callback of the focused option.

        Parameters
        ----------
        ctx: :class:`.AutocompleteContext`
            The autocomplete context to invoke the callback with.
        """
        values: dict[str, Any] = {cast("str", i.name): i.default for i in self.options}
        data = _interaction_data(ctx)

        for op in data.get("options", []):
            if op.get("focused", False):
                option = next((o for o in self.options if o.name == op["name"]), None)
                if option is None:
                    raise ClientException(
                        f"The option {op['name']!r} was not found in the command"
                        f" {self.qualified_name!r}."
                    )
                values.update({i["name"]: i["value"] for i in data["options"]})
                ctx.command = self
                ctx.focused = option
                ctx.value = op.get("value")
                ctx.options = values

                autocomplete = cast("Callable[..., Any]", option.autocomplete)
                if option._autocomplete_is_instance_method:
                    instance = getattr(option.autocomplete, "__self__", ctx.cog)
                    result = autocomplete(instance, ctx)
                else:
                    result = autocomplete(ctx)

                if inspect.isawaitable(result):
                    result = await result

                choices = [
                    o if isinstance(o, OptionChoice) else OptionChoice(o)
                    for o in cast("Iterable[Any]", result)
                ][:25]
                await ctx.interaction.response.send_autocomplete_result(choices=choices)
                return

    def copy(self) -> Self:
        """Creates a copy of this command.

        Returns
        -------
        :class:`SlashCommand`
            A new instance of this command.
        """
        ret = self.__class__(self.callback, **self.__original_kwargs__)
        return self._ensure_assignment_on_copy(ret)


class SlashCommandGroup(ApplicationCommand[Any, ..., Any]):
    r"""A class that implements the protocol for a slash command group.

    These can be created manually, but they should be created via the
    decorator or functional interface.

    Attributes
    ----------
    name: :class:`str`
        The name of the command.
    description: Optional[:class:`str`]
        The description for the command.
    guild_ids: Optional[List[:class:`int`]]
        The ids of the guilds where this command will be registered.
    parent: Optional[:class:`SlashCommandGroup`]
        The parent group that this group belongs to. ``None`` if there
        isn't one.
    guild_only: :class:`bool`
        Whether the command should only be usable inside a guild.

        .. deprecated:: 2.6
            Use the :attr:`contexts` parameter instead.
    nsfw: :class:`bool`
        Whether the command should be restricted to 18+ channels and users.
        Apps intending to be listed in the App Directory cannot have NSFW commands.
    default_member_permissions: :class:`~discord.Permissions`
        The default permissions a member needs to be able to run the command.
    checks: List[Callable[[:class:`.ApplicationContext`], :class:`bool`]]
        A list of predicates that verifies if the command could be executed
        with the given :class:`.ApplicationContext` as the sole parameter. If an exception
        is necessary to be thrown to signal failure, then one inherited from
        :exc:`.ApplicationCommandError` should be used. Note that if the checks fail then
        :exc:`.CheckFailure` exception is raised to the :func:`.on_application_command_error`
        event.
    name_localizations: Dict[:class:`str`, :class:`str`]
        The name localizations for this command. The values of this should be ``"locale": "name"``. See
        `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    description_localizations: Dict[:class:`str`, :class:`str`]
        The description localizations for this command. The values of this should be ``"locale": "description"``.
        See `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    integration_types: Set[:class:`IntegrationType`]
        The type of installation this command should be available to. For instance, if set to
        :attr:`IntegrationType.user_install`, the command will only be available to users with
        the application installed on their account. Not applicable for guild commands.
    contexts: Set[:class:`InteractionContextType`]
        The location where this command can be used. Not applicable for guild commands.
    """

    __initial_commands__: list[SlashCommand | SlashCommandGroup]
    type = 1

    def __new__(cls, *_args: Any, **kwargs: Any) -> Self:
        """Creates the command, keeping the keyword arguments to copy it later."""
        self = super().__new__(cls)
        self.__original_kwargs__ = kwargs.copy()

        self.__initial_commands__ = []
        for member in cls.__dict__.values():
            entry: object = member
            if isinstance(entry, type) and SlashCommandGroup in entry.__bases__:
                entry = cast("type[SlashCommandGroup]", entry)(
                    entry.__name__,
                    (
                        inspect.cleandoc(cls.__doc__).splitlines()[0]
                        if cls.__doc__ is not None
                        else "No description provided"
                    ),
                )
            if _is_slash_member(entry):
                entry.parent = self
                entry.attached_to_group = True
                self.__initial_commands__.append(entry)

        return self

    def __init__(
        self,
        name: str,
        description: str | None = None,
        guild_ids: list[int] | None = None,
        parent: SlashCommandGroup | None = None,
        cooldown: CooldownMapping | None = None,
        max_concurrency: MaxConcurrency | None = None,
        **kwargs: Any,
    ) -> None:
        for key, value in (
            ("guild_ids", guild_ids),
            ("cooldown", cooldown),
            ("max_concurrency", max_concurrency),
        ):
            if value is not None:
                self.__original_kwargs__.setdefault(key, value)

        self.name = str(name)
        self.description = description or "No description provided"
        validate_chat_input_name(self.name)
        validate_chat_input_description(self.description)
        self.input_type = SlashCommandOptionType.sub_command_group
        self.subcommands: list[SlashCommand | SlashCommandGroup] = (
            self.__initial_commands__
        )
        self.guild_ids = guild_ids
        self.parent = parent
        self.attached_to_group: bool = False
        self.checks = kwargs.get("checks", [])

        self._before_invoke = None
        self._after_invoke = None
        self.cog = None
        self.id = None

        # Permissions
        self.default_member_permissions: Permissions | None = kwargs.get(
            "default_member_permissions"
        )
        self.nsfw: bool | None = kwargs.get("nsfw", False)

        integration_types = kwargs.get("integration_types")
        contexts = kwargs.get("contexts")
        guild_only = kwargs.get("guild_only", MISSING)
        if guild_only is not MISSING:
            warn_deprecated("guild_only", "contexts", "2.6")
        if contexts and guild_only:
            raise InvalidArgument(
                "cannot pass both 'contexts' and 'guild_only' to ApplicationCommand"
            )
        if self.guild_ids and (
            (contexts is not None) or guild_only or integration_types
        ):
            raise InvalidArgument(
                "the 'contexts' and 'integration_types' parameters are not available for guild commands"
            )

        # These are set to None and their defaults are then set when added to the bot
        self.contexts: set[InteractionContextType] | None = contexts
        if guild_only:
            self.guild_only = guild_only
        self.integration_types: set[IntegrationType] | None = integration_types

        self.name_localizations: dict[str, str] = kwargs.get(
            "name_localizations", MISSING
        )
        self.description_localizations: dict[str, str] = kwargs.get(
            "description_localizations", MISSING
        )

        self._buckets: CooldownMapping
        self._max_concurrency: MaxConcurrency | None
        self._buckets, self._max_concurrency = resolve_cooldown_settings(
            cooldown=cooldown, max_concurrency=max_concurrency
        )

    @property
    def module(self) -> str | None:  # pyright: ignore[reportIncompatibleVariableOverride]
        """The name of the module this group was defined in."""
        return self.__module__

    @property
    def guild_only(self) -> bool:
        """Whether the command is only usable inside a guild.

        .. deprecated:: 2.6
            Use :attr:`contexts` instead.
        """
        warn_deprecated("guild_only", "contexts", "2.6")
        return (
            self.contexts is not None
            and InteractionContextType.guild in self.contexts
            and len(self.contexts) == 1
        )

    @guild_only.setter
    def guild_only(self, value: bool) -> None:
        warn_deprecated("guild_only", "contexts", "2.6")
        if value:
            self.contexts = {InteractionContextType.guild}
        else:
            self.contexts = {
                InteractionContextType.guild,
                InteractionContextType.bot_dm,
                InteractionContextType.private_channel,
            }

    def to_dict(self) -> dict[str, Any]:
        """Converts this group into the payload sent to Discord."""
        as_dict: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "options": [c.to_dict() for c in self.subcommands],
        }
        if self.name_localizations is not MISSING:
            as_dict["name_localizations"] = self.name_localizations
        if self.description_localizations is not MISSING:
            as_dict["description_localizations"] = self.description_localizations

        if self.parent is not None:
            as_dict["type"] = self.input_type.value

        if self.nsfw is not None:
            as_dict["nsfw"] = self.nsfw

        if self.default_member_permissions is not None:
            as_dict["default_member_permissions"] = (
                self.default_member_permissions.value
            )

        if not self.guild_ids and self.parent is None:
            as_dict["integration_types"] = _enum_values(self.integration_types)
            as_dict["contexts"] = _enum_values(self.contexts)

        return as_dict

    def add_command(self, command: SlashCommand | SlashCommandGroup) -> None:
        """Adds a :class:`.SlashCommand` or :class:`.SlashCommandGroup` as a subcommand.

        This is usually not called, instead the :meth:`command` or
        other shortcut decorators are used instead.

        .. versionadded:: 2.9

        Parameters
        ----------
        command: Union[:class:`.SlashCommand`, :class:`.SlashCommandGroup`]
            The command to add.
        """
        if command.cog is None and self.cog is not None:
            command.cog = self.cog

        command.parent = self
        self.subcommands.append(command)

    @overload
    def command(
        self, cls: type[SlashCommandT], **kwargs: Any
    ) -> Callable[[Callable[..., Any]], SlashCommandT]: ...

    @overload
    def command(
        self, **kwargs: Any
    ) -> Callable[[Callback[CogT, P, T]], SlashCommand[CogT, P, T]]: ...

    def command(
        self, cls: type[SlashCommand[Any, ..., Any]] = SlashCommand, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], SlashCommand[Any, ..., Any]]:
        """A shortcut decorator for adding a subcommand to this slash command group.

        Returns
        -------
        Callable[..., :class:`SlashCommand`]
            A decorator that converts the provided function into a :class:`.SlashCommand`,
            adds it to this group, then returns it.
        """

        def wrap(func: Callable[..., Any]) -> SlashCommand[Any, ..., Any]:
            command = cls(func, **kwargs)
            self.add_command(command)
            return command

        return wrap

    def create_subgroup(
        self,
        name: str,
        description: str | None = None,
        guild_ids: list[int] | None = None,
        **kwargs: Any,
    ) -> SlashCommandGroup:
        """
        Creates a new subgroup under this slash command group.

        Parameters
        ----------
        name: :class:`str`
            The name of the group to create.
        description: Optional[:class:`str`]
            The description of the group to create.
        guild_ids: Optional[List[:class:`int`]]
            A list of the IDs of each guild this group should be added to, making it a guild command.
            This will be a global command if ``None`` is passed.
        guild_only: :class:`bool`
            Whether the command should only be usable inside a guild.
        nsfw: :class:`bool`
            Whether the command should be restricted to 18+ channels and users.
            Apps intending to be listed in the App Directory cannot have NSFW commands.
        default_member_permissions: :class:`~discord.Permissions`
            The default permissions a member needs to be able to run the command.
        checks: List[Callable[[:class:`.ApplicationContext`], :class:`bool`]]
            A list of predicates that verifies if the command could be executed
            with the given :class:`.ApplicationContext` as the sole parameter. If an exception
            is necessary to be thrown to signal failure, then one inherited from
            :exc:`.ApplicationCommandError` should be used. Note that if the checks fail then
            :exc:`.CheckFailure` exception is raised to the :func:`.on_application_command_error`
            event.
        name_localizations: Dict[:class:`str`, :class:`str`]
            The name localizations for this command. The values of this should be ``"locale": "name"``. See
            `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
        description_localizations: Dict[:class:`str`, :class:`str`]
            The description localizations for this command. The values of this should be ``"locale": "description"``.
            See `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.

        Returns
        -------
        SlashCommandGroup
            The slash command group that was created.
        """
        if self.parent is not None:
            raise ClientException(
                "A subcommand group cannot be added to a subcommand group"
            )

        sub_command_group = SlashCommandGroup(
            name, description, guild_ids, parent=self, **kwargs
        )
        self.subcommands.append(sub_command_group)
        return sub_command_group

    def subgroup(
        self,
        name: str | None = None,
        description: str | None = None,
        guild_ids: list[int] | None = None,
    ) -> Callable[[type[SlashCommandGroup]], SlashCommandGroup]:
        """A shortcut decorator that initializes the provided subclass of :class:`.SlashCommandGroup` as a subgroup.

        .. versionadded:: 2.0

        Parameters
        ----------
        name: Optional[:class:`str`]
            The name of the group to create. This will resolve to the name of the decorated class if ``None`` is passed.
        description: Optional[:class:`str`]
            The description of the group to create.
        guild_ids: Optional[List[:class:`int`]]
            A list of the IDs of each guild this group should be added to, making it a guild command.
            This will be a global command if ``None`` is passed.

        Returns
        -------
        Callable[[Type[SlashCommandGroup]], SlashCommandGroup]
            The slash command group that was created.
        """

        def inner(cls: type[SlashCommandGroup]) -> SlashCommandGroup:
            group = cls(
                name or cls.__name__,
                description
                or (
                    inspect.cleandoc(cls.__doc__).splitlines()[0]
                    if cls.__doc__ is not None
                    else "No description provided"
                ),
                guild_ids=guild_ids,
            )
            self.add_command(group)
            return group

        return inner

    def _resolve_leaf(self, ctx: ApplicationContext) -> ApplicationCommand:
        command: ApplicationCommand = self
        data = ctx.interaction.data or {}
        while isinstance(command, SlashCommandGroup):
            options = data.get("options")
            if not options:
                break
            data = options[0]
            found = None
            for subcommand in command.subcommands:
                if subcommand.name == data["name"]:
                    found = subcommand
                    break
            if found is None:
                break
            command = found
        return command

    async def prepare(self, ctx: ApplicationContext) -> None:
        """|coro|

        Prepares the context to invoke the subcommand the interaction targets.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context to prepare.
        """
        await self._prepare(ctx, self._resolve_leaf(ctx))

    def _find_subcommand(self, name: str) -> SlashCommand | SlashCommandGroup:
        for subcommand in self.subcommands:
            if subcommand.name == name:
                return subcommand
        raise ClientException(
            f"The command {name!r} of the group {self.qualified_name!r} was not found."
        )

    async def _invoke(self, ctx: ApplicationContext) -> None:
        data = _interaction_data(ctx)
        option = data["options"][0]
        resolved = data.get("resolved", None)
        command = self._find_subcommand(option["name"])
        option["resolved"] = resolved
        ctx.interaction.data = cast("InteractionData", option)
        await command.invoke(ctx)

    async def invoke_autocomplete_callback(self, ctx: AutocompleteContext) -> None:
        """|coro|

        Invokes the autocomplete callback of the subcommand being typed.

        Parameters
        ----------
        ctx: :class:`.AutocompleteContext`
            The autocomplete context to invoke the callback with.
        """
        option = _interaction_data(ctx)["options"][0]
        command = self._find_subcommand(option["name"])
        ctx.interaction.data = cast("InteractionData", option)
        await command.invoke_autocomplete_callback(ctx)

    async def call_before_hooks(self, ctx: ApplicationContext) -> None:
        """|coro|

        Calls the pre-invoke hook of this group, if it has one.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context the hook is called with.
        """
        # only call local hooks
        cog = self.cog
        if self._before_invoke is not None:
            await _call_local_hook(self._before_invoke, cog, ctx)

    async def call_after_hooks(self, ctx: ApplicationContext) -> None:
        """|coro|

        Calls the post-invoke hook of this group, if it has one.

        Parameters
        ----------
        ctx: :class:`.ApplicationContext`
            The invocation context the hook is called with.
        """
        cog = self.cog
        if self._after_invoke is not None:
            await _call_local_hook(self._after_invoke, cog, ctx)

    def walk_commands(self) -> Generator[SlashCommand | SlashCommandGroup]:
        """An iterator that recursively walks through all slash commands and groups in this group.

        Yields
        ------
        :class:`.SlashCommand` | :class:`.SlashCommandGroup`
            A nested slash command or slash command group from the group.
        """
        for command in self.subcommands:
            if isinstance(command, SlashCommandGroup):
                yield from command.walk_commands()
            yield command

    def copy(self) -> Self:
        """Creates a copy of this command group.

        Returns
        -------
        :class:`SlashCommandGroup`
            A new instance of this command group.
        """
        ret = self.__class__(
            name=self.name,
            description=self.description,
            **{
                param: value
                for param, value in self.__original_kwargs__.items()
                if param not in ("name", "description")
            },
        )
        return self._ensure_group_assignment_on_copy(ret)

    def _ensure_group_assignment_on_copy(self, other: Self) -> Self:
        other.parent = self.parent

        other._before_invoke = self._before_invoke
        other._after_invoke = self._after_invoke

        if self.subcommands != other.subcommands:
            other.subcommands = self.subcommands.copy()

        if self.checks != other.checks:
            other.checks = self.checks.copy()

        return other

    def _update_copy(self, kwargs: dict[str, Any]) -> Self:
        if kwargs:
            kw = kwargs.copy()
            kw.update(self.__original_kwargs__)
            kw.update(name=self.name, description=self.description)
            copy = self.__class__(**kw)
            return self._ensure_group_assignment_on_copy(copy)
        return self.copy()

    def _set_cog(self, cog: Cog | None) -> None:
        super()._set_cog(cog)
        for subcommand in self.subcommands:
            if not subcommand._is_owned_by_other(cog):
                subcommand._set_cog(cog)

    def _attach_member(
        self, member: SlashCommand | SlashCommandGroup, cog: Cog | None = None
    ) -> bool:
        for existing in self.subcommands:
            if existing is member:
                return False
            if existing.name == member.name:
                raise ClientException(
                    f"The command {member.name!r} of the group {self.qualified_name!r} is "
                    f"already provided by {_describe_cog(existing)}, it cannot be "
                    f"registered by {_describe_cog(member, cog)}"
                )
        member.parent = self
        self.subcommands.append(member)
        return True

    def _detach_member(self, member: SlashCommand | SlashCommandGroup) -> bool:
        for index, existing in enumerate(self.subcommands):
            if existing is member:
                del self.subcommands[index]
                return True
        return False

    def _prune_inactive(self) -> bool:
        changed = False
        for member in list(self.subcommands):
            if member._cog_class is not None and member.cog is None:
                self._detach_member(member)
                changed = True
            elif isinstance(member, SlashCommandGroup) and member.subcommands:
                changed |= member._prune_inactive()
                if not member.subcommands:
                    self._detach_member(member)
                    changed = True
        return changed


class ContextMenuCommand(ApplicationCommand[CogT, P, T]):
    r"""A class that implements the protocol for context menu commands.

    These are not created manually, instead they are created via the
    decorator or functional interface.

    .. versionadded:: 2.0

    Attributes
    ----------
    name: :class:`str`
        The name of the command.
    callback: :ref:`coroutine <coroutine>`
        The coroutine that is executed when the command is called.
    guild_ids: Optional[List[:class:`int`]]
        The ids of the guilds where this command will be registered.
    guild_only: :class:`bool`
        Whether the command should only be usable inside a guild.

        .. deprecated:: 2.6
            Use the ``contexts`` parameter instead.
    nsfw: :class:`bool`
        Whether the command should be restricted to 18+ channels and users.
        Apps intending to be listed in the App Directory cannot have NSFW commands.
    default_member_permissions: :class:`~discord.Permissions`
        The default permissions a member needs to be able to run the command.
    cog: Optional[:class:`Cog`]
        The cog that this command belongs to. ``None`` if there isn't one.
    checks: List[Callable[[:class:`.ApplicationContext`], :class:`bool`]]
        A list of predicates that verifies if the command could be executed
        with the given :class:`.ApplicationContext` as the sole parameter. If an exception
        is necessary to be thrown to signal failure, then one inherited from
        :exc:`.ApplicationCommandError` should be used. Note that if the checks fail then
        :exc:`.CheckFailure` exception is raised to the :func:`.on_application_command_error`
        event.
    cooldown: Optional[:class:`~discord.ext.commands.Cooldown`]
        The cooldown applied when the command is invoked. ``None`` if the command
        doesn't have a cooldown.
    name_localizations: Dict[:class:`str`, :class:`str`]
        The name localizations for this command. The values of this should be ``"locale": "name"``. See
        `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    integration_types: Set[:class:`IntegrationType`]
        The installation contexts where this command is available. Not applicable for guild commands.
    contexts: Set[:class:`InteractionContextType`]
        The interaction contexts where this command is available. Not applicable for guild commands.
    """

    type: int

    def __new__(cls, *_args: Any, **kwargs: Any) -> Self:
        """Creates the command, keeping the keyword arguments to copy it later."""
        self = super().__new__(cls)

        self.__original_kwargs__ = kwargs.copy()
        return self

    def __init__(self, func: Callback[CogT, P, T], *args: Any, **kwargs: Any) -> None:
        super().__init__(func, **kwargs)
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Callback must be a coroutine.")
        self.callback = func

        self.name_localizations: dict[str, str] = kwargs.get(
            "name_localizations", MISSING
        )

        # Discord API doesn't support setting descriptions for context menu commands, so it must be empty
        self.description = ""
        if not _is_str(self.name):
            raise TypeError("Name of a command must be a string.")

        self.cog = None
        self.id = None

        self._before_invoke = None
        self._after_invoke = None

        self.validate_parameters()

        # Context Menu commands can't have parents
        self.parent = None

    def validate_parameters(self) -> None:
        """Validates that the callback takes the context and the target."""
        params = self._get_signature_parameters()
        names = iter(params)
        if next(iter(params), None) == "self":
            next(names)

        # next we have the 'ctx' as the next parameter
        if next(names, None) is None:
            raise ClientException(
                f'Callback for {self.name} command is missing "ctx" parameter.'
            )

        # next we have the 'user/message' as the next parameter
        if next(names, None) is None:
            cmd = "user" if type(self) is UserCommand else "message"
            raise ClientException(
                f'Callback for {self.name} command is missing "{cmd}" parameter.'
            )

        # next there should be no more parameters
        if next(names, None) is not None:
            raise ClientException(
                f"Callback for {self.name} command has too many parameters."
            )

    @property
    def qualified_name(self) -> str:
        """The name of the command, context menu commands have no parent."""
        return self.name

    def to_dict(self) -> dict[str, Any]:
        """Converts this command into the payload sent to Discord."""
        as_dict: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "type": self.type,
        }

        if not self.guild_ids:
            as_dict["integration_types"] = _enum_values(self.integration_types)
            as_dict["contexts"] = _enum_values(self.contexts)

        if self.nsfw is not None:
            as_dict["nsfw"] = self.nsfw

        if self.default_member_permissions is not None:
            as_dict["default_member_permissions"] = (
                self.default_member_permissions.value
            )

        if self.name_localizations:
            as_dict["name_localizations"] = self.name_localizations

        return as_dict


class UserCommand(ContextMenuCommand[CogT, P, T]):
    r"""A class that implements the protocol for user context menu commands.

    These are not created manually, instead they are created via the
    decorator or functional interface.

    Attributes
    ----------
    name: :class:`str`
        The name of the command.
    callback: :ref:`coroutine <coroutine>`
        The coroutine that is executed when the command is called.
    guild_ids: Optional[List[:class:`int`]]
        The ids of the guilds where this command will be registered.
    guild_only: :class:`bool`
        Whether the command should only be usable inside a guild.

        .. deprecated:: 2.6
            Use the ``contexts`` parameter instead.
    nsfw: :class:`bool`
        Whether the command should be restricted to 18+ channels and users.
        Apps intending to be listed in the App Directory cannot have NSFW commands.
    default_member_permissions: :class:`~discord.Permissions`
        The default permissions a member needs to be able to run the command.
    cog: Optional[:class:`Cog`]
        The cog that this command belongs to. ``None`` if there isn't one.
    checks: List[Callable[[:class:`.ApplicationContext`], :class:`bool`]]
        A list of predicates that verifies if the command could be executed
        with the given :class:`.ApplicationContext` as the sole parameter. If an exception
        is necessary to be thrown to signal failure, then one inherited from
        :exc:`.ApplicationCommandError` should be used. Note that if the checks fail then
        :exc:`.CheckFailure` exception is raised to the :func:`.on_application_command_error`
        event.
    cooldown: Optional[:class:`~discord.ext.commands.Cooldown`]
        The cooldown applied when the command is invoked. ``None`` if the command
        doesn't have a cooldown.
    name_localizations: Dict[:class:`str`, :class:`str`]
        The name localizations for this command. The values of this should be ``"locale": "name"``. See
        `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    integration_types: Set[:class:`IntegrationType`]
        The installation contexts where this command is available. Not applicable for guild commands.
    contexts: Set[:class:`InteractionContextType`]
        The interaction contexts where this command is available. Not applicable for guild commands.
    """

    type = 2

    async def _invoke(self, ctx: ApplicationContext) -> None:
        resolved = _interaction_data(ctx)["resolved"]
        if "members" not in resolved:
            user = _last_resolved(resolved["users"])
            target: User | Member = User(state=ctx.interaction._state, data=user)
        else:
            member = _last_resolved(resolved["members"])
            user = _last_resolved(resolved["users"])
            member["user"] = user
            target = await _resolve_interaction_member(ctx, member, user["id"])
        if self.cog is not None:
            await self._call_callback(self.cog, ctx, target)
        else:
            await self._call_callback(ctx, target)

    def copy(self) -> Self:
        """Creates a copy of this command.

        Returns
        -------
        :class:`UserCommand`
            A new instance of this command.
        """
        ret = self.__class__(self.callback, **self.__original_kwargs__)
        return self._ensure_assignment_on_copy(ret)


class MessageCommand(ContextMenuCommand[CogT, P, T]):
    r"""A class that implements the protocol for message context menu commands.

    These are not created manually, instead they are created via the
    decorator or functional interface.

    Attributes
    ----------
    name: :class:`str`
        The name of the command.
    callback: :ref:`coroutine <coroutine>`
        The coroutine that is executed when the command is called.
    guild_ids: Optional[List[:class:`int`]]
        The ids of the guilds where this command will be registered.
    guild_only: :class:`bool`
        Whether the command should only be usable inside a guild.

        .. deprecated:: 2.6
            Use the ``contexts`` parameter instead.
    nsfw: :class:`bool`
        Whether the command should be restricted to 18+ channels and users.
        Apps intending to be listed in the App Directory cannot have NSFW commands.
    default_member_permissions: :class:`~discord.Permissions`
        The default permissions a member needs to be able to run the command.
    cog: Optional[:class:`Cog`]
        The cog that this command belongs to. ``None`` if there isn't one.
    checks: List[Callable[[:class:`.ApplicationContext`], :class:`bool`]]
        A list of predicates that verifies if the command could be executed
        with the given :class:`.ApplicationContext` as the sole parameter. If an exception
        is necessary to be thrown to signal failure, then one inherited from
        :exc:`.ApplicationCommandError` should be used. Note that if the checks fail then
        :exc:`.CheckFailure` exception is raised to the :func:`.on_application_command_error`
        event.
    cooldown: Optional[:class:`~discord.ext.commands.Cooldown`]
        The cooldown applied when the command is invoked. ``None`` if the command
        doesn't have a cooldown.
    name_localizations: Dict[:class:`str`, :class:`str`]
        The name localizations for this command. The values of this should be ``"locale": "name"``. See
        `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    integration_types: Set[:class:`IntegrationType`]
        The installation contexts where this command is available. Not applicable for guild commands.
    contexts: Set[:class:`InteractionContextType`]
        The interaction contexts where this command is available. Not applicable for guild commands.
    """

    type = 3

    async def _invoke(self, ctx: ApplicationContext) -> None:
        message = _last_resolved(_interaction_data(ctx)["resolved"]["messages"])
        channel = ctx.interaction.channel
        if channel is None or channel.id != int(message["channel_id"]):
            # we got weird stuff going on, make up a channel
            channel = PartialMessageable(
                state=ctx.interaction._state, id=int(message["channel_id"])
            )

        target = Message(
            state=ctx.interaction._state,
            channel=cast("MessageableChannel", channel),
            data=message,
        )
        await ctx.interaction._state._populate_message(target, message)

        if self.cog is not None:
            await self._call_callback(self.cog, ctx, target)
        else:
            await self._call_callback(ctx, target)

    def copy(self) -> Self:
        """Creates a copy of this command.

        Returns
        -------
        :class:`MessageCommand`
            A new instance of this command.
        """
        ret = self.__class__(self.callback, **self.__original_kwargs__)
        return self._ensure_assignment_on_copy(ret)


class EntryPointCommand(ApplicationCommand[CogT, P, T]):
    r"""A class that implements the protocol for an entry point command.

    These are not created manually, instead they are created via the
    decorator or functional interface.

    .. versionadded:: 3.0

    Attributes
    ----------
    name: :class:`str`
        The name of the command.
    callback: :ref:`coroutine <coroutine>`
        The coroutine that is executed when the command is called.
        It is not called when the handler is :attr:`EntryPointHandler.discord_launch_activity`,
        as Discord launches the activity without sending an interaction to the application.
    description: :class:`str`
        The description for the command.
    nsfw: :class:`bool`
        Whether the command should be restricted to 18+ channels and users.
        Apps intending to be listed in the App Directory cannot have NSFW commands.
    default_member_permissions: :class:`~discord.Permissions`
        The default permissions a member needs to be able to run the command.
    cog: Optional[:class:`Cog`]
        The cog that this command belongs to. ``None`` if there isn't one.
    checks: List[Callable[[:class:`.ApplicationContext`], :class:`bool`]]
        A list of predicates that verifies if the command could be executed
        with the given :class:`.ApplicationContext` as the sole parameter. If an exception
        is necessary to be thrown to signal failure, then one inherited from
        :exc:`.ApplicationCommandError` should be used. Note that if the checks fail then
        :exc:`.CheckFailure` exception is raised to the :func:`.on_application_command_error`
        event.
    cooldown: Optional[:class:`~discord.ext.commands.Cooldown`]
        The cooldown applied when the command is invoked. ``None`` if the command
        doesn't have a cooldown.
    name_localizations: Dict[:class:`str`, :class:`str`]
        The name localizations for this command. The values of this should be ``"locale": "name"``. See
        `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    description_localizations: Dict[:class:`str`, :class:`str`]
        The description localizations for this command. The values of this should be ``"locale": "description"``.
        See `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    integration_types: Set[:class:`IntegrationType`]
        The installation contexts where this command is available.
    contexts: Set[:class:`InteractionContextType`]
        The interaction contexts where this command is available.
    handler: :class:`EntryPointHandler`
        The action to take when the user executes this command. If it is not set, Discord
        uses the handler the command already has, or :attr:`EntryPointHandler.app_handler`
        for a new command.
    """

    type = 4

    def __new__(cls, *_args: Any, **kwargs: Any) -> Self:
        """Creates the command, keeping the keyword arguments to copy it later."""
        self = super().__new__(cls)

        self.__original_kwargs__ = kwargs.copy()
        return self

    def __init__(self, func: Callback[CogT, P, T], **kwargs: Any) -> None:
        super().__init__(func, **kwargs)
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Callback must be a coroutine.")
        if self.guild_ids:
            raise InvalidArgument("entry point commands cannot be guild commands")
        self.callback = func

        self.name_localizations: dict[str, str] = kwargs.get(
            "name_localizations", MISSING
        )
        _validate_names(self)

        description = kwargs.get("description") or (
            inspect.cleandoc(func.__doc__).splitlines()[0]
            if func.__doc__ is not None
            else "No description provided"
        )

        self.description: str = description
        self.description_localizations: dict[str, str] = kwargs.get(
            "description_localizations", MISSING
        )
        _validate_descriptions(self)

        handler = kwargs.get("handler", MISSING)
        if handler is not MISSING and not isinstance(handler, EntryPointHandler):
            raise TypeError("handler must be an EntryPointHandler.")
        self.handler: EntryPointHandler = handler

        self.cog = None
        self.id = None

        self._before_invoke = None
        self._after_invoke = None

        self._validate_parameters()

        self.parent = None

    def _validate_parameters(self) -> None:
        names = list(self._get_signature_parameters())
        if names and names[0] == "self":
            names.pop(0)

        # we only have the 'ctx' parameter
        if not names:
            raise ClientException(
                f'Callback for {self.name} command is missing "ctx" parameter.'
            )

        if len(names) > 1:
            raise ClientException(
                f"Callback for {self.name} command has too many parameters."
            )

    @property
    def mention(self) -> str:
        """A string that allows you to mention the entry point command."""
        return f"</{self.qualified_name}:{self.qualified_id}>"

    def to_dict(self) -> dict[str, Any]:
        """Converts this command into the payload sent to Discord."""
        as_dict: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "type": self.type,
        }
        if self.name_localizations is not MISSING:
            as_dict["name_localizations"] = self.name_localizations
        if self.description_localizations is not MISSING:
            as_dict["description_localizations"] = self.description_localizations

        if self.nsfw is not None:
            as_dict["nsfw"] = self.nsfw

        if self.default_member_permissions is not None:
            as_dict["default_member_permissions"] = (
                self.default_member_permissions.value
            )

        if self.handler is not MISSING:
            as_dict["handler"] = self.handler.value

        as_dict["integration_types"] = _enum_values(self.integration_types)
        as_dict["contexts"] = _enum_values(self.contexts)

        return as_dict

    async def _invoke(self, ctx: ApplicationContext) -> None:
        if self.cog is not None:
            await self._call_callback(self.cog, ctx)
        else:
            await self._call_callback(ctx)

    def copy(self) -> Self:
        """Creates a copy of this command.

        Returns
        -------
        :class:`EntryPointCommand`
            A new instance of this command.
        """
        ret = self.__class__(self.callback, **self.__original_kwargs__)
        return self._ensure_assignment_on_copy(ret)


def slash_command(
    *,
    checks: list[Callable[[ApplicationContext], bool]] | None = MISSING,
    cog: Cog | None = MISSING,
    contexts: set[InteractionContextType] | None = MISSING,
    cooldown: Cooldown | None = MISSING,
    default_member_permissions: Permissions | None = MISSING,
    description: str | None = MISSING,
    description_localizations: dict[str, str] | None = MISSING,
    guild_ids: list[int] | None = MISSING,
    guild_only: bool | None = MISSING,
    integration_types: set[IntegrationType] | None = MISSING,
    name: str | None = MISSING,
    name_localizations: dict[str, str] | None = MISSING,
    nsfw: bool | None = MISSING,
    options: list[Option] | None = MISSING,
    parent: SlashCommandGroup | None = MISSING,
    **kwargs: Never,
) -> Callable[[Callback[CogT, P, T]], SlashCommand[CogT, P, T]]:
    """Decorator for slash commands that invokes :func:`application_command`.

    .. versionadded:: 2.0

    Returns
    -------
    Callable[..., :class:`.SlashCommand`]
        A decorator that converts the provided method into a :class:`.SlashCommand`.
    """
    return application_command(
        cls=SlashCommand,
        checks=checks,
        cog=cog,
        contexts=contexts,
        cooldown=cooldown,
        default_member_permissions=default_member_permissions,
        description=description,
        description_localizations=description_localizations,
        guild_ids=guild_ids,
        guild_only=guild_only,
        integration_types=integration_types,
        name=name,
        name_localizations=name_localizations,
        nsfw=nsfw,
        options=options,
        parent=parent,
        **kwargs,
    )


def user_command(
    *,
    checks: list[Callable[[ApplicationContext], bool]] | None = MISSING,
    cog: Cog | None = MISSING,
    contexts: set[InteractionContextType] | None = MISSING,
    cooldown: Cooldown | None = MISSING,
    default_member_permissions: Permissions | None = MISSING,
    guild_ids: list[int] | None = MISSING,
    guild_only: bool | None = MISSING,
    integration_types: set[IntegrationType] | None = MISSING,
    name: str | None = MISSING,
    name_localizations: dict[str, str] | None = MISSING,
    nsfw: bool | None = MISSING,
    **kwargs: Never,
) -> Callable[[Callback[CogT, P, T]], UserCommand[CogT, P, T]]:
    """Decorator for user commands that invokes :func:`application_command`.

    .. versionadded:: 2.0

    Returns
    -------
    Callable[..., :class:`.UserCommand`]
        A decorator that converts the provided method into a :class:`.UserCommand`.
    """
    return application_command(
        cls=UserCommand,
        checks=checks,
        cog=cog,
        contexts=contexts,
        cooldown=cooldown,
        default_member_permissions=default_member_permissions,
        guild_ids=guild_ids,
        guild_only=guild_only,
        integration_types=integration_types,
        name=name,
        name_localizations=name_localizations,
        nsfw=nsfw,
        **kwargs,
    )


def message_command(
    *,
    checks: list[Callable[[ApplicationContext], bool]] | None = MISSING,
    cog: Cog | None = MISSING,
    contexts: set[InteractionContextType] | None = MISSING,
    cooldown: Cooldown | None = MISSING,
    default_member_permissions: Permissions | None = MISSING,
    guild_ids: list[int] | None = MISSING,
    guild_only: bool | None = MISSING,
    integration_types: set[IntegrationType] | None = MISSING,
    name: str | None = MISSING,
    name_localizations: dict[str, str] | None = MISSING,
    nsfw: bool | None = MISSING,
    **kwargs: Never,
) -> Callable[[Callback[CogT, P, T]], MessageCommand[CogT, P, T]]:
    """Decorator for message commands that invokes :func:`application_command`.

    .. versionadded:: 2.0

    Returns
    -------
    Callable[..., :class:`.MessageCommand`]
        A decorator that converts the provided method into a :class:`.MessageCommand`.
    """
    return application_command(
        cls=MessageCommand,
        checks=checks,
        cog=cog,
        contexts=contexts,
        cooldown=cooldown,
        default_member_permissions=default_member_permissions,
        guild_ids=guild_ids,
        guild_only=guild_only,
        integration_types=integration_types,
        name=name,
        name_localizations=name_localizations,
        nsfw=nsfw,
        **kwargs,
    )


def entry_point_command(
    *,
    checks: list[Callable[[ApplicationContext], bool]] | None = MISSING,
    cog: Cog | None = MISSING,
    contexts: set[InteractionContextType] | None = MISSING,
    cooldown: Cooldown | None = MISSING,
    default_member_permissions: Permissions | None = MISSING,
    description: str | None = MISSING,
    description_localizations: dict[str, str] | None = MISSING,
    integration_types: set[IntegrationType] | None = MISSING,
    name: str | None = MISSING,
    name_localizations: dict[str, str] | None = MISSING,
    nsfw: bool | None = MISSING,
    handler: EntryPointHandler = MISSING,
    **kwargs: Never,
) -> Callable[[Callback[CogT, P, T]], EntryPointCommand[CogT, P, T]]:
    """Decorator for entry point commands that invokes :func:`application_command`.

    Entry point commands are how users launch the activity of an application.
    They are always global commands.

    .. versionadded:: 3.0

    Returns
    -------
    Callable[..., :class:`.EntryPointCommand`]
        A decorator that converts the provided method into a :class:`.EntryPointCommand`.
    """
    return application_command(
        cls=EntryPointCommand,
        checks=checks,
        cog=cog,
        contexts=contexts,
        cooldown=cooldown,
        default_member_permissions=default_member_permissions,
        description=description,
        description_localizations=description_localizations,
        integration_types=integration_types,
        name=name,
        name_localizations=name_localizations,
        nsfw=nsfw,
        handler=handler,
        **kwargs,
    )


def application_command(
    *,
    cls: type[CommandT] = SlashCommand,
    checks: list[Callable[[ApplicationContext], bool]] | None = MISSING,
    cog: Cog | None = MISSING,
    contexts: set[InteractionContextType] | None = MISSING,
    cooldown: Cooldown | None = MISSING,
    default_member_permissions: Permissions | None = MISSING,
    description: str | None = MISSING,
    description_localizations: dict[str, str] | None = MISSING,
    guild_ids: list[int] | None = MISSING,
    guild_only: bool | None = MISSING,
    integration_types: set[IntegrationType] | None = MISSING,
    name: str | None = MISSING,
    name_localizations: dict[str, str] | None = MISSING,
    nsfw: bool | None = MISSING,
    options: list[Option] | None = MISSING,
    parent: SlashCommandGroup | None = MISSING,
    **kwargs: Any,
) -> Callable[[Callable[..., Any]], CommandT]:
    """A decorator that transforms a function into an :class:`.ApplicationCommand`.

    More specifically, usually one of :class:`.SlashCommand`,
    :class:`.UserCommand`, or :class:`.MessageCommand`. The exact class
    depends on the ``cls`` parameter.

    By default, the ``description`` attribute is received automatically from the
    docstring of the function and is cleaned up with the use of
    ``inspect.cleandoc``. If the docstring is ``bytes``, then it is decoded
    into :class:`str` using utf-8 encoding.
    The ``name`` attribute also defaults to the function name unchanged.

    .. versionadded:: 2.0

    Parameters
    ----------
    cls: :class:`.ApplicationCommand`
        The class to construct with. By default, this is :class:`.SlashCommand`.
        You usually do not change this.
    attrs
        Keyword arguments to pass into the construction of the class denoted
        by ``cls``.

    Returns
    -------
    Callable[..., :class:`.ApplicationCommand`]
        A decorator that converts the provided method into an :class:`.ApplicationCommand`, or subclass of it.

    Raises
    ------
    TypeError
        If the function is not a coroutine or is already a command.
    """
    params = {
        "checks": checks,
        "cog": cog,
        "contexts": contexts,
        "cooldown": cooldown,
        "default_member_permissions": default_member_permissions,
        "description": description,
        "description_localizations": description_localizations,
        "guild_ids": guild_ids,
        "guild_only": guild_only,
        "integration_types": integration_types,
        "name": name,
        "name_localizations": name_localizations,
        "nsfw": nsfw,
        "options": options,
        "parent": parent,
        **kwargs,
    }
    kwargs = {k: v for k, v in params.items() if v is not MISSING}

    def decorator(func: Callable[..., Any]) -> CommandT:
        if isinstance(func, ApplicationCommand):
            func = cast("ApplicationCommand[Any, ..., Any]", func).callback
        elif not callable(func):
            raise TypeError(
                "func needs to be a callable or a subclass of ApplicationCommand."
            )
        return cls(func, **kwargs)

    return decorator


def command(
    **kwargs: Any,
) -> Callable[[Callable[..., Any]], ApplicationCommand[Any, ..., Any]]:
    """An alias for :meth:`application_command`.

    .. note::
        This decorator is overridden by :func:`ext.commands.command`.

    .. versionadded:: 2.0

    Returns
    -------
    Callable[..., :class:`.ApplicationCommand`]
        A decorator that converts the provided method into an :class:`.ApplicationCommand`.
    """
    return application_command(**kwargs)


docs = "https://docs.discord.com/developers"
valid_locales = [
    "id",
    "da",
    "de",
    "en-GB",
    "en-US",
    "es-ES",
    "es-419",
    "fr",
    "hr",
    "it",
    "lt",
    "hu",
    "nl",
    "no",
    "pl",
    "pt-BR",
    "ro",
    "fi",
    "sv-SE",
    "vi",
    "tr",
    "cs",
    "el",
    "bg",
    "ru",
    "uk",
    "hi",
    "th",
    "zh-CN",
    "ja",
    "zh-TW",
    "ko",
]


# Validation
def validate_chat_input_name(name: Any, locale: str | None = None) -> None:
    # Must meet the regex ^[-_\w\d\u0901-\u097D\u0E00-\u0E7F]{1,32}$
    if locale is not None and locale not in valid_locales:
        raise ValidationError(
            f"Locale '{locale}' is not a valid locale, see {docs}/reference#locales for"
            " list of supported locales."
        )
    error = None
    if not isinstance(name, str):
        error = TypeError(
            f'Command names and options must be of type str. Received "{name}"'
        )
    elif not re.match(r"^[-_\w\d\u0901-\u097D\u0E00-\u0E7F]{1,32}$", name):
        error = ValidationError(
            r"Command names and options must follow the regex"
            r" \"^[-_\w\d\u0901-\u097D\u0E00-\u0E7F]{1,32}$\". "
            "For more information, see"
            f" {docs}/interactions/application-commands#application-command-object-"
            f'application-command-naming. Received "{name}"'
        )
    elif (
        name.lower() != name
    ):  # Can't use islower() as it fails if none of the chars can be lowered. See #512.
        error = ValidationError(
            f'Command names and options must be lowercase. Received "{name}"'
        )

    if error:
        if locale:
            error.args = (f"{error.args[0]} in locale {locale}",)
        raise error


def validate_chat_input_description(
    description: Any, locale: str | None = None
) -> None:
    if locale is not None and locale not in valid_locales:
        raise ValidationError(
            f"Locale '{locale}' is not a valid locale, see {docs}/reference#locales for"
            " list of supported locales."
        )
    error = None
    if not isinstance(description, str):
        error = TypeError(
            "Command and option description must be of type str. Received"
            f' "{description}"'
        )
    elif not 1 <= len(description) <= 100:
        error = ValidationError(
            "Command and option description must be 1-100 characters long. Received"
            f' "{description}"'
        )

    if error:
        if locale:
            error.args = (f"{error.args[0]} in locale {locale}",)
        raise error
