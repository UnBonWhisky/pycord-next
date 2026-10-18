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
import contextvars
import datetime as dt
import inspect
import sys
import traceback
from collections.abc import Awaitable, Callable, Coroutine, Sequence
from typing import Any, Generic, TypeVar, cast

import aiohttp

import discord
from discord.backoff import ExponentialBackoff
from discord.utils import MISSING, _get_event_loop

__all__ = ("loop",)

T = TypeVar("T")
_func = Callable[..., Awaitable[Any]]
LF = TypeVar("LF", bound=_func)
FT = TypeVar("FT", bound=_func)
ET = TypeVar("ET", bound=Callable[[Any, BaseException], Awaitable[Any]])
_current_loop_ctx: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "_current_loop_ctx", default=None
)


class SleepHandle:
    __slots__ = ("future", "handle", "loop")

    def __init__(self, when: dt.datetime, *, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.future = future = loop.create_future()
        relative_delta = discord.utils.compute_timedelta(when)
        self.handle = loop.call_later(relative_delta, future.set_result, True)

    def _set_result_safe(self) -> None:
        if not self.future.done():
            self.future.set_result(True)

    def recalculate(self, dt: dt.datetime) -> None:
        self.handle.cancel()
        relative_delta = discord.utils.compute_timedelta(dt)
        self.handle = self.loop.call_later(relative_delta, self._set_result_safe)

    def wait(self) -> asyncio.Future[Any]:
        return self.future

    def done(self) -> bool:
        return self.future.done()

    def cancel(self) -> None:
        self.handle.cancel()
        self.future.cancel()


class Loop(Generic[LF]):
    """A background task helper that abstracts the loop and reconnection logic for you.

    The main interface to create this is through :func:`loop`.
    """

    _run_with_semaphore: Callable[..., Coroutine[Any, Any, None]]

    def __init__(
        self,
        coro: LF,
        seconds: float,
        hours: float,
        minutes: float,
        time: dt.time | Sequence[dt.time],
        count: int | None,
        reconnect: bool,
        loop: asyncio.AbstractEventLoop,
        overlap: bool | int,
    ) -> None:
        self.coro: LF = coro
        self.reconnect: bool = reconnect
        self.loop: asyncio.AbstractEventLoop = loop
        self.overlap: bool | int = overlap
        self.count: int | None = count
        self._current_loop = 0
        self._handle: SleepHandle = MISSING
        self._task: asyncio.Task[None] = MISSING
        self._injected = None
        self._valid_exception = (
            OSError,
            discord.GatewayNotFound,
            discord.ConnectionClosed,
            aiohttp.ClientError,
            asyncio.TimeoutError,
        )

        self._before_loop = None
        self._after_loop = None
        self._before_loop_running = False
        self._after_loop_running = False
        self._is_being_cancelled = False
        self._has_failed = False
        self._stop_next_iteration = False
        self._tasks: set[asyncio.Task[Any]] = set()

        if self.count is not None and self.count <= 0:
            raise ValueError("count must be greater than 0 or None.")

        self.change_interval(seconds=seconds, minutes=minutes, hours=hours, time=time)
        self._last_iteration_failed = False
        self._last_iteration: dt.datetime = MISSING
        self._next_iteration = None

        if not inspect.iscoroutinefunction(self.coro):
            raise TypeError(
                f"Expected coroutine function, not {type(self.coro).__name__!r}."
            )
        overlap_value = cast("object", overlap)
        if isinstance(overlap_value, bool):
            if overlap_value:
                self._run_with_semaphore = self._run_direct
        elif isinstance(overlap_value, int):
            if overlap_value <= 1:
                raise ValueError("overlap as an integer must be greater than 1.")
            self._semaphore = asyncio.Semaphore(overlap_value)
            self._run_with_semaphore = self._semaphore_runner_factory()
        else:
            raise TypeError("overlap must be a bool or a positive integer.")

    async def _run_direct(self, *args: Any, **kwargs: Any) -> None:
        """Run the coroutine directly."""
        await self.coro(*args, **kwargs)

    def _semaphore_runner_factory(self) -> Callable[..., Coroutine[Any, Any, None]]:
        """Return a function that runs the coroutine with a semaphore."""

        async def runner(*args: Any, **kwargs: Any) -> None:
            async with self._semaphore:
                await self.coro(*args, **kwargs)

        return runner

    async def _call_loop_function(self, name: str, *args: Any, **kwargs: Any) -> None:
        coro = getattr(self, f"_{name}")
        if coro is None:
            return

        if name.endswith("_loop"):
            setattr(self, f"_{name}_running", True)

        if self._injected is not None:
            await coro(self._injected, *args, **kwargs)
        else:
            await coro(*args, **kwargs)

        if name.endswith("_loop"):
            setattr(self, f"_{name}_running", False)

    def _try_sleep_until(self, when: dt.datetime) -> asyncio.Future[Any]:
        self._handle = SleepHandle(when=when, loop=self.loop)
        return self._handle.wait()

    async def _loop(self, *args: Any, **kwargs: Any) -> None:
        backoff = ExponentialBackoff()
        await self._call_loop_function("before_loop")
        self._last_iteration_failed = False
        if self._time is not MISSING:
            # the time index should be prepared every time the internal loop is started
            self._prepare_time_index()
            self._next_iteration = self._get_next_sleep_time()
        else:
            self._next_iteration = dt.datetime.now(dt.timezone.utc)
        try:
            await self._try_sleep_until(self._next_iteration)
            while True:
                if not self._last_iteration_failed:
                    self._last_iteration = self._next_iteration
                    self._next_iteration = self._get_next_sleep_time()
                try:
                    token = _current_loop_ctx.set(self._current_loop)
                    if not self.overlap:
                        await self.coro(*args, **kwargs)
                    else:
                        task = asyncio.create_task(
                            self._run_with_semaphore(*args, **kwargs),
                            name=f"pycord-loop-{self.coro.__name__}-{self._current_loop}",
                        )
                        task.add_done_callback(self._tasks.discard)
                        self._tasks.add(task)

                    _current_loop_ctx.reset(token)
                    self._last_iteration_failed = False
                    backoff = ExponentialBackoff()
                except self._valid_exception:
                    self._last_iteration_failed = True
                    if not self.reconnect:
                        raise
                    await asyncio.sleep(backoff.delay())
                else:
                    await self._try_sleep_until(self._next_iteration)

                    if self._stop_next_iteration:
                        return

                    now = dt.datetime.now(dt.timezone.utc)
                    if now > self._next_iteration:
                        self._next_iteration = now
                        if self._time is not MISSING:
                            self._prepare_time_index(now)

                    self._current_loop += 1
                    if self._current_loop == self.count:
                        break

        except asyncio.CancelledError:
            self._is_being_cancelled = True
            for task in self._tasks:
                task.cancel()
            await asyncio.gather(*self._tasks, return_exceptions=True)
            raise
        except Exception as exc:
            self._has_failed = True
            await self._call_loop_function("error", exc)
            raise
        finally:
            await self._call_loop_function("after_loop")
            self._handle.cancel()
            self._is_being_cancelled = False
            self._current_loop = 0
            self._stop_next_iteration = False
            self._has_failed = False

    def __get__(self, obj: T, objtype: type[T]) -> Loop[LF]:
        if obj is None:
            return self

        copy: Loop[LF] = Loop(
            self.coro,
            seconds=self._seconds,
            hours=self._hours,
            minutes=self._minutes,
            time=self._time,
            count=self.count,
            reconnect=self.reconnect,
            loop=self.loop,
            overlap=self.overlap,
        )
        copy._injected = obj
        copy._before_loop = self._before_loop
        copy._after_loop = self._after_loop
        copy._error = self._error
        setattr(obj, self.coro.__name__, copy)
        return copy

    @property
    def seconds(self) -> float | None:
        """Read-only value for the number of seconds between each iteration.

        ``None`` if an explicit ``time`` value was passed instead.

        .. versionadded:: 2.0
        """
        if self._seconds is not MISSING:
            return self._seconds
        return None

    @property
    def minutes(self) -> float | None:
        """Read-only value for the number of minutes between each iteration.

        ``None`` if an explicit ``time`` value was passed instead.

        .. versionadded:: 2.0
        """
        if self._minutes is not MISSING:
            return self._minutes
        return None

    @property
    def hours(self) -> float | None:
        """Read-only value for the number of hours between each iteration.

        ``None`` if an explicit ``time`` value was passed instead.

        .. versionadded:: 2.0
        """
        if self._hours is not MISSING:
            return self._hours
        return None

    @property
    def time(self) -> list[dt.time] | None:
        """Read-only list for the exact times this loop runs at.

        ``None`` if relative times were passed instead.

        .. versionadded:: 2.0
        """
        if self._time is not MISSING:
            return self._time.copy()
        return None

    @property
    def current_loop(self) -> int:
        """The current iteration of the loop."""
        ctx_loop = _current_loop_ctx.get()
        return ctx_loop if ctx_loop is not None else self._current_loop

    @property
    def next_iteration(self) -> dt.datetime | None:
        """When the next iteration of the loop will occur.

        .. versionadded:: 1.3
        """
        if (
            self._task is MISSING
            or (self._task and self._task.done())
            or self._stop_next_iteration
        ):
            return None
        return self._next_iteration

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        r"""|coro|

        Calls the internal callback that the task holds.

        .. versionadded:: 1.6

        Parameters
        ----------
        \*args
            The arguments to use.
        \*\*kwargs
            The keyword arguments to use.
        """
        if self._injected is not None:
            args = (self._injected, *args)

        return await self.coro(*args, **kwargs)

    def start(self, *args: Any, **kwargs: Any) -> asyncio.Task[None]:
        r"""Starts the internal task in the event loop.

        Parameters
        ----------
        \*args
            The arguments to use.
        \*\*kwargs
            The keyword arguments to use.

        Raises
        ------
        RuntimeError
            A task has already been launched and is running.

        Returns
        -------
        :class:`asyncio.Task`
            The task that has been created.
        """
        if self._task is not MISSING and not self._task.done():
            raise RuntimeError("Task is already launched and is not completed.")

        if self._injected is not None:
            args = (self._injected, *args)

        if self.loop is MISSING:
            self.loop = _get_event_loop()

        self._task = self.loop.create_task(self._loop(*args, **kwargs))
        return self._task

    def stop(self) -> None:
        r"""Gracefully stops the task from running.

        Unlike :meth:`cancel`\, this allows the task to finish its
        current iteration before gracefully exiting.

        .. note::

            If the internal function raises an error that can be
            handled before finishing then it will retry until
            it succeeds.

            If this is undesirable, either remove the error handling
            before stopping via :meth:`clear_exception_types` or
            use :meth:`cancel` instead.

        .. versionadded:: 1.2
        """
        if self._task is not MISSING and not self._task.done():
            self._stop_next_iteration = True

    def _can_be_cancelled(self) -> bool:
        return bool(
            not self._is_being_cancelled and self._task and not self._task.done()
        )

    def cancel(self) -> None:
        """Cancels the internal task, if it is running."""
        if self._can_be_cancelled():
            self._task.cancel()

    def restart(self, *args: Any, **kwargs: Any) -> None:
        r"""A convenience method to restart the internal task.

        .. note::

            Due to the way this function works, the task is not
            returned like :meth:`start`.

        Parameters
        ----------
        \*args
            The arguments to use.
        \*\*kwargs
            The keyword arguments to use.
        """

        def restart_when_over(
            _fut: Any, *, args: Any = args, kwargs: Any = kwargs
        ) -> None:
            self._task.remove_done_callback(restart_when_over)
            self.start(*args, **kwargs)

        if self._can_be_cancelled():
            self._task.add_done_callback(restart_when_over)
            self._task.cancel()

    def add_exception_type(self, *exceptions: type[BaseException]) -> None:
        r"""Adds exception types to be handled during the reconnect logic.

        By default, the exception types handled are those handled by
        :meth:`discord.Client.connect`\, which includes a lot of internet disconnection
        errors.

        This function is useful if you're interacting with a 3rd party library that
        raises its own set of exceptions.

        Parameters
        ----------
        \*exceptions: Type[:class:`BaseException`]
            An argument list of exception classes to handle.

        Raises
        ------
        TypeError
            An exception passed is either not a class or not inherited from :class:`BaseException`.
        """
        candidates = cast("tuple[object, ...]", exceptions)
        for exc in candidates:
            if not inspect.isclass(exc):
                raise TypeError(f"{exc!r} must be a class.")
            if not issubclass(exc, BaseException):
                raise TypeError(f"{exc!r} must inherit from BaseException.")

        self._valid_exception = (*self._valid_exception, *exceptions)

    def clear_exception_types(self) -> None:
        """Removes all exception types that are handled.

        .. note::

            This operation obviously cannot be undone!
        """
        self._valid_exception = ()

    def remove_exception_type(self, *exceptions: type[BaseException]) -> bool:
        r"""Removes exception types from being handled during the reconnect logic.

        Parameters
        ----------
        \*exceptions: Type[:class:`BaseException`]
            An argument list of exception classes to handle.

        Returns
        -------
        :class:`bool`
            Whether all exceptions were successfully removed.
        """
        old_length = len(self._valid_exception)
        self._valid_exception = tuple(
            x for x in self._valid_exception if x not in exceptions
        )
        return len(self._valid_exception) == old_length - len(exceptions)

    def get_task(self) -> asyncio.Task[None] | None:
        """Fetches the internal task or ``None`` if there isn't one running."""
        return self._task if self._task is not MISSING else None

    def is_being_cancelled(self) -> bool:
        """Whether the task is being cancelled."""
        return self._is_being_cancelled

    def failed(self) -> bool:
        """Whether the internal task has failed.

        .. versionadded:: 1.2
        """
        return self._has_failed

    def is_running(self) -> bool:
        """Check if the task is currently running.

        .. versionadded:: 1.4
        """
        return not bool(self._task.done()) if self._task is not MISSING else False

    async def _error(self, *args: Any) -> None:
        exception: Exception = args[-1]
        sys.stderr.write(
            f"Unhandled exception in internal background task {self.coro.__name__!r}.\n"
        )
        traceback.print_exception(
            type(exception), exception, exception.__traceback__, file=sys.stderr
        )

    def before_loop(self, coro: FT) -> FT:
        """A decorator that registers a coroutine to be called before the loop starts running.

        This is useful if you want to wait for some bot state before the loop starts,
        such as :meth:`discord.Client.wait_until_ready`.

        The coroutine must take no arguments (except ``self`` in a class context).

        Parameters
        ----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register before the loop runs.

        Raises
        ------
        TypeError
            The function was not a coroutine.
        """
        if not inspect.iscoroutinefunction(coro):
            raise TypeError(
                f"Expected coroutine function, received {coro.__class__.__name__!r}."
            )

        self._before_loop = coro
        return coro

    def after_loop(self, coro: FT) -> FT:
        """A decorator that register a coroutine to be called after the loop finished running.

        The coroutine must take no arguments (except ``self`` in a class context).

        .. note::

            This coroutine is called even during cancellation. If it is desirable
            to tell apart whether something was cancelled or not, check to see
            whether :meth:`is_being_cancelled` is ``True`` or not.

        Parameters
        ----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register after the loop finishes.

        Raises
        ------
        TypeError
            The function was not a coroutine.
        """
        if not inspect.iscoroutinefunction(coro):
            raise TypeError(
                f"Expected coroutine function, received {coro.__class__.__name__!r}."
            )

        self._after_loop = coro
        return coro

    def error(self, coro: ET) -> ET:
        """A decorator that registers a coroutine to be called if the task encounters an unhandled exception.

        The coroutine must take only one argument the exception raised (except ``self`` in a class context).

        By default, this prints to :data:`sys.stderr` however it could be
        overridden to have a different implementation.

        .. versionadded:: 1.4

        Parameters
        ----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register in the event of an unhandled exception.

        Raises
        ------
        TypeError
            The function was not a coroutine.
        """
        if not inspect.iscoroutinefunction(coro):
            raise TypeError(
                f"Expected coroutine function, received {coro.__class__.__name__!r}."
            )

        cast("Any", self)._error = coro
        return coro

    def _get_next_sleep_time(self) -> dt.datetime:
        if self._sleep is not MISSING:
            return self._last_iteration + dt.timedelta(seconds=self._sleep)

        if self._time_index >= len(self._time):
            self._time_index = 0
            if self._current_loop == 0:
                # if we're at the last index on the first iteration, we need to sleep until tomorrow
                return dt.datetime.combine(
                    dt.datetime.now(self._time[0].tzinfo or dt.timezone.utc)
                    + dt.timedelta(days=1),
                    self._time[0],
                )

        next_time = self._time[self._time_index]

        if self._current_loop == 0:
            self._time_index += 1
            if (
                next_time
                > dt.datetime.now(next_time.tzinfo or dt.timezone.utc).timetz()
            ):
                return dt.datetime.combine(
                    dt.datetime.now(next_time.tzinfo or dt.timezone.utc),
                    next_time,
                )
            return dt.datetime.combine(
                dt.datetime.now(next_time.tzinfo or dt.timezone.utc)
                + dt.timedelta(days=1),
                next_time,
            )

        next_date = self._last_iteration.astimezone(next_time.tzinfo)
        if next_time < next_date.timetz():
            next_date += dt.timedelta(days=1)

        self._time_index += 1
        return dt.datetime.combine(next_date, next_time)

    def _prepare_time_index(self, now: dt.datetime = MISSING) -> None:
        # now kwarg should be a datetime.datetime representing the time "now"
        # to calculate the next time index from

        # pre-condition: self._time is set
        time_now = (
            now
            if now is not MISSING
            else dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        )
        for idx, time in enumerate(self._time):
            if time >= time_now.astimezone(time.tzinfo).timetz():
                self._time_index = idx
                break
        else:
            self._time_index = 0

    def _get_time_parameter(
        self,
        time: dt.time | Sequence[dt.time],
        *,
        utc: dt.timezone = dt.timezone.utc,
    ) -> list[dt.time]:
        value = cast("object", time)
        if isinstance(value, dt.time):
            inner = value if value.tzinfo is not None else value.replace(tzinfo=utc)
            return [inner]
        if not isinstance(value, Sequence):
            raise TypeError(
                "Expected datetime.time or a sequence of datetime.time for ``time``,"
                f" received {type(value)!r} instead."
            )
        if not value:
            raise ValueError("time parameter must not be an empty sequence.")

        ret: list[dt.time] = []
        for index, t in enumerate(cast("Sequence[object]", value)):
            if not isinstance(t, dt.time):
                raise TypeError(
                    f"Expected a sequence of {dt.time!r} for ``time``, received"
                    f" {type(t).__name__!r} at index {index} instead."
                )
            ret.append(t if t.tzinfo is not None else t.replace(tzinfo=utc))

        return sorted(set(ret))  # de-dupe and sort times

    def change_interval(
        self,
        *,
        seconds: float = 0,
        minutes: float = 0,
        hours: float = 0,
        time: dt.time | Sequence[dt.time] = MISSING,
    ) -> None:
        """Changes the interval for the sleep time.

        .. versionadded:: 1.2

        Parameters
        ----------
        seconds: :class:`float`
            The number of seconds between every iteration.
        minutes: :class:`float`
            The number of minutes between every iteration.
        hours: :class:`float`
            The number of hours between every iteration.
        time: Union[:class:`datetime.time`, Sequence[:class:`datetime.time`]]
            The exact times to run this loop at. Either a non-empty list or a single
            value of :class:`datetime.time` should be passed.
            This cannot be used in conjunction with the relative time parameters.

            .. versionadded:: 2.0

            .. note::

                Duplicate times will be ignored, and only run once.

        Raises
        ------
        ValueError
            An invalid value was given.
        TypeError
            An invalid value for the ``time`` parameter was passed, or the
            ``time`` parameter was passed in conjunction with relative time parameters.
        """
        if time is MISSING:
            seconds = seconds or 0
            minutes = minutes or 0
            hours = hours or 0
            sleep = seconds + (minutes * 60.0) + (hours * 3600.0)
            if sleep < 0:
                raise ValueError("Total number of seconds cannot be less than zero.")

            self._sleep = sleep
            self._seconds = float(seconds)
            self._hours = float(hours)
            self._minutes = float(minutes)
            self._time: list[dt.time] = MISSING
        else:
            if any((seconds, minutes, hours)):
                raise TypeError("Cannot mix explicit time with relative time")
            self._time = self._get_time_parameter(time)
            self._sleep = self._seconds = self._minutes = self._hours = MISSING

        if self.is_running() and not (
            self._before_loop_running or self._after_loop_running
        ):
            if self._time is not MISSING:
                # prepare the next time index starting from after the last iteration
                self._prepare_time_index(now=self._last_iteration)

            self._next_iteration = self._get_next_sleep_time()
            if not self._handle.done():
                # the loop is sleeping, recalculate based on new interval
                self._handle.recalculate(self._next_iteration)


def loop(
    *,
    seconds: float = MISSING,
    minutes: float = MISSING,
    hours: float = MISSING,
    time: dt.time | Sequence[dt.time] = MISSING,
    count: int | None = None,
    reconnect: bool = True,
    loop: asyncio.AbstractEventLoop = MISSING,
    overlap: bool | int = False,
) -> Callable[[LF], Loop[LF]]:
    """A decorator that schedules a task in the background for you with optional reconnect logic.

    The decorator returns a :class:`Loop`.

    Parameters
    ----------
    seconds: :class:`float`
        The number of seconds between every iteration.
    minutes: :class:`float`
        The number of minutes between every iteration.
    hours: :class:`float`
        The number of hours between every iteration.
    time: Union[:class:`datetime.time`, Sequence[:class:`datetime.time`]]
        The exact times to run this loop at. Either a non-empty list or a single
        value of :class:`datetime.time` should be passed. Timezones are supported.
        If no timezone is given for the times, it is assumed to represent UTC time.

        This cannot be used in conjunction with the relative time parameters.

        .. note::

            Duplicate times will be ignored, and only run once.

        .. versionadded:: 2.0

    count: Optional[:class:`int`]
        The number of loops to do, ``None`` if it should be an
        infinite loop.
    reconnect: :class:`bool`
        Whether to handle errors and restart the task
        using an exponential back-off algorithm similar to the
        one used in :meth:`discord.Client.connect`.
    loop: :class:`asyncio.AbstractEventLoop`
        The loop to use to register the task, if not given the default event loop is used via
        :func:`asyncio.get_event_loop()` if it exists or one is created via :func:`asyncio.new_event_loop()`.
    overlap: Union[:class:`bool`, :class:`int`]
        Controls whether overlapping executions of the task loop are allowed.
        Set to False (default) to run iterations one at a time, True for unlimited overlap, or an int to cap the number of concurrent runs.

        .. versionadded:: 2.7

    Raises
    ------
    ValueError
        An invalid value was given.
    TypeError
        The function was not a coroutine, an invalid value for the ``time`` parameter was passed,
        or ``time`` parameter was passed in conjunction with relative time parameters.
    """

    def decorator(func: LF) -> Loop[LF]:
        return Loop[LF](
            func,
            seconds=seconds,
            minutes=minutes,
            hours=hours,
            count=count,
            time=time,
            reconnect=reconnect,
            loop=loop,
            overlap=overlap,
        )

    return decorator
