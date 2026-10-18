"""
The MIT License (MIT)

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

# ruff: noqa: PT018, ASYNC110

from __future__ import annotations

import asyncio
import datetime as dt
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord.ext import tasks
from discord.ext.tasks import Loop, SleepHandle

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

FAST = 0.001


@pytest.fixture(autouse=True)
def instant_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    class Backoff:
        def delay(self) -> float:
            return 0

    monkeypatch.setattr(tasks, "ExponentialBackoff", Backoff)


def run(loop: asyncio.AbstractEventLoop, coro: Coroutine[Any, Any, Any]) -> Any:
    return loop.run_until_complete(asyncio.wait_for(coro, 5))


def make(
    loop: asyncio.AbstractEventLoop,
    callback: Callable[..., Coroutine[Any, Any, Any]],
    **kwargs: Any,
) -> Loop:
    kwargs.setdefault("seconds", FAST)
    return tasks.loop(loop=loop, **kwargs)(callback)


class TestConstruction:
    def test_decorator_returns_a_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        async def tick() -> None: ...

        task = make(loop, tick, seconds=1, minutes=2, hours=3)
        assert isinstance(task, Loop)
        assert (task.seconds, task.minutes, task.hours, task.time) == (1, 2, 3, None)
        assert task.count is None and task.reconnect and task.overlap is False

    def test_time_property(self, loop: asyncio.AbstractEventLoop) -> None:
        async def tick() -> None: ...

        t = dt.time(10, 30)
        task = tasks.loop(time=[t, dt.time(8)], loop=loop)(tick)
        assert task.time == [
            dt.time(8, tzinfo=dt.timezone.utc),
            t.replace(tzinfo=dt.timezone.utc),
        ]
        assert (task.seconds, task.minutes, task.hours) == (None, None, None)
        task.time.clear()
        assert len(task.time) == 2

    def test_invalid_count(self, loop: asyncio.AbstractEventLoop) -> None:
        async def tick() -> None: ...

        with pytest.raises(ValueError, match="count"):
            make(loop, tick, count=0)

    def test_callback_must_be_a_coroutine(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        with pytest.raises(TypeError, match="Expected coroutine function"):
            make(loop, lambda: None)

    @pytest.mark.parametrize(
        ("overlap", "error"),
        [(1, ValueError), (0.5, TypeError), ("x", TypeError)],
    )
    def test_invalid_overlap(
        self, loop: asyncio.AbstractEventLoop, overlap: Any, error: type[Exception]
    ) -> None:
        async def tick() -> None: ...

        with pytest.raises(error):
            make(loop, tick, overlap=overlap)

    def test_negative_interval(self, loop: asyncio.AbstractEventLoop) -> None:
        async def tick() -> None: ...

        with pytest.raises(ValueError, match="less than zero"):
            make(loop, tick, seconds=-1)

    def test_time_cannot_be_mixed(self, loop: asyncio.AbstractEventLoop) -> None:
        async def tick() -> None: ...

        with pytest.raises(TypeError, match="mix"):
            tasks.loop(seconds=1, time=dt.time(1), loop=loop)(tick)

    @pytest.mark.parametrize(
        ("value", "error"),
        [(5, TypeError), ([], ValueError), ([dt.time(1), 5], TypeError)],
    )
    def test_invalid_time(
        self, loop: asyncio.AbstractEventLoop, value: Any, error: type[Exception]
    ) -> None:
        async def tick() -> None: ...

        with pytest.raises(error):
            tasks.loop(time=value, loop=loop)(tick)

    def test_time_values_are_deduplicated_and_sorted(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick() -> None: ...

        task = tasks.loop(time=[dt.time(5), dt.time(1), dt.time(5)], loop=loop)(tick)
        assert [t.hour for t in task.time] == [1, 5]


class TestRunning:
    def test_count_limited_loop_with_hooks(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        log: list[Any] = []

        async def tick() -> None:
            log.append(("tick", task.current_loop))

        task = make(loop, tick, count=3)

        @task.before_loop
        async def before() -> None:
            log.append("before")

        @task.after_loop
        async def after() -> None:
            log.append(("after", task.is_being_cancelled()))

        started = task.start()
        assert task.get_task() is started
        assert task.is_running()
        run(loop, started)
        assert log == [
            "before",
            ("tick", 0),
            ("tick", 1),
            ("tick", 2),
            ("after", False),
        ]
        assert not task.is_running()
        assert task.current_loop == 0
        assert task.next_iteration is None
        assert not task.failed()

    def test_next_iteration_while_running(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick() -> None: ...

        task = make(loop, tick, seconds=60)
        assert task.next_iteration is None
        assert task.get_task() is None
        assert not task.is_running()

        async def scenario() -> None:
            task.start()
            await asyncio.sleep(0.01)
            assert isinstance(task.next_iteration, dt.datetime)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task.get_task()

        run(loop, scenario())
        assert task.next_iteration is None

    def test_start_twice(self, loop: asyncio.AbstractEventLoop) -> None:
        async def tick() -> None: ...

        task = make(loop, tick, seconds=60)

        async def scenario() -> None:
            task.start()
            with pytest.raises(RuntimeError, match="already launched"):
                task.start()
            task.cancel()
            task.cancel()
            await asyncio.sleep(0)

        run(loop, scenario())

    def test_start_without_a_loop_uses_the_default_one(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick() -> None: ...

        task = tasks.loop(seconds=60, count=1)(tick)

        async def scenario() -> None:
            task.start()
            assert task.loop is asyncio.get_running_loop()
            task.cancel()
            await asyncio.sleep(0)

        run(loop, scenario())

    def test_stop_lets_the_iteration_finish(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        calls = 0

        async def tick() -> None:
            nonlocal calls
            calls += 1
            task.stop()

        task = make(loop, tick)
        run(loop, task.start())
        assert calls == 1
        task.stop()
        assert not task.is_running()

    def test_restart(self, loop: asyncio.AbstractEventLoop) -> None:
        seen: list[tuple[Any, ...]] = []

        async def tick(*args: Any) -> None:
            seen.append(args)

        task = make(loop, tick, seconds=60, count=1)

        async def scenario() -> None:
            task.start("a")
            await asyncio.sleep(0.01)
            task.restart("b")
            await asyncio.sleep(0.01)
            assert task.is_running()
            task.cancel()
            await asyncio.sleep(0)

        run(loop, scenario())
        assert seen == [("a",), ("b",)]

    def test_restart_when_not_running_does_nothing(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick() -> None: ...

        task = make(loop, tick)
        task.restart()
        assert task.get_task() is None

    def test_call_runs_the_callback_directly(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick(a: int) -> int:
            return a + 1

        assert run(loop, make(loop, tick)(1)) == 2

    def test_callback_arguments(self, loop: asyncio.AbstractEventLoop) -> None:
        seen: list[Any] = []

        async def tick(a: int, b: int = 0) -> None:
            seen.append((a, b))

        run(loop, make(loop, tick, count=1).start(1, b=2))
        assert seen == [(1, 2)]


class TestErrors:
    def test_unhandled_exception_goes_to_the_error_handler(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        seen: list[Exception] = []
        order: list[str] = []

        async def tick() -> None:
            raise ValueError("bad")

        task = make(loop, tick)

        @task.error
        async def on_error(exc: Exception) -> None:
            seen.append(exc)
            order.append("error")

        @task.after_loop
        async def after() -> None:
            order.append("after")

        with pytest.raises(ValueError):
            run(loop, task.start())
        assert [str(e) for e in seen] == ["bad"]
        assert order == ["error", "after"]
        assert not task.failed()

    def test_default_error_handler_prints(
        self, loop: asyncio.AbstractEventLoop, capsys: pytest.CaptureFixture[str]
    ) -> None:
        async def tick() -> None:
            raise ValueError("bad")

        task = make(loop, tick)
        with pytest.raises(ValueError):
            run(loop, task.start())
        err = capsys.readouterr().err
        assert "Unhandled exception in internal background task 'tick'" in err
        assert "ValueError: bad" in err

    def test_failed_is_true_during_the_error_handler(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        states: list[bool] = []

        async def tick() -> None:
            raise ValueError

        task = make(loop, tick)

        @task.error
        async def on_error(exc: Exception) -> None:
            states.append(task.failed())

        with pytest.raises(ValueError):
            run(loop, task.start())
        assert states == [True]

    def test_reconnect_retries_valid_exceptions(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        attempts = 0

        async def tick() -> None:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise OSError("flaky")

        task = make(loop, tick, count=1)
        run(loop, task.start())
        assert attempts == 3

    def test_no_reconnect_raises(self, loop: asyncio.AbstractEventLoop) -> None:
        async def tick() -> None:
            raise OSError("flaky")

        task = make(loop, tick, reconnect=False)

        @task.error
        async def on_error(exc: Exception) -> None: ...

        with pytest.raises(OSError):
            run(loop, task.start())

    def test_exception_type_management(self, loop: asyncio.AbstractEventLoop) -> None:
        async def tick() -> None:
            raise KeyError("k")

        task = make(loop, tick, count=1)
        with pytest.raises(TypeError, match="must be a class"):
            task.add_exception_type(5)
        with pytest.raises(TypeError, match="inherit from BaseException"):
            task.add_exception_type(int)
        task.add_exception_type(KeyError)
        assert KeyError in task._valid_exception
        assert task.remove_exception_type(KeyError) is True
        assert task.remove_exception_type(KeyError) is False
        task.clear_exception_types()
        assert task._valid_exception == ()

    def test_custom_exception_is_retried(self, loop: asyncio.AbstractEventLoop) -> None:
        attempts = 0

        async def tick() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise KeyError

        task = make(loop, tick, count=1)
        task.add_exception_type(KeyError)
        run(loop, task.start())
        assert attempts == 2

    def test_hook_decorators_require_coroutines(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick() -> None: ...

        task = make(loop, tick)
        for decorator in (task.before_loop, task.after_loop, task.error):
            with pytest.raises(TypeError, match="Expected coroutine function"):
                decorator(lambda *a: None)

    def test_cancellation_runs_after_loop(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        seen: list[bool] = []

        async def tick() -> None: ...

        task = make(loop, tick, seconds=60)

        @task.after_loop
        async def after() -> None:
            seen.append(task.is_being_cancelled())

        async def scenario() -> None:
            task.start()
            await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.sleep(0.01)

        run(loop, scenario())
        assert seen == [True]
        assert not task.is_being_cancelled()


class TestOverlap:
    def test_default_runs_iterations_one_at_a_time(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        running = peak = 0

        async def tick() -> None:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.005)
            running -= 1

        run(loop, make(loop, tick, count=3).start())
        assert peak == 1

    def test_true_allows_unlimited_overlap(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        running = peak = 0
        done: list[int] = []

        async def tick() -> None:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.03)
            running -= 1
            done.append(1)

        task = make(loop, tick, count=4, overlap=True, seconds=0.002)

        async def scenario() -> None:
            await task.start()
            while len(done) < 4:
                await asyncio.sleep(0.005)

        run(loop, scenario())
        assert peak > 1

    def test_integer_caps_the_overlap(self, loop: asyncio.AbstractEventLoop) -> None:
        running = peak = 0
        done: list[int] = []

        async def tick() -> None:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.02)
            running -= 1
            done.append(1)

        task = make(loop, tick, count=6, overlap=2, seconds=0.001)

        async def scenario() -> None:
            await task.start()
            while len(done) < 6:
                await asyncio.sleep(0.005)

        run(loop, scenario())
        assert peak == 2

    def test_cancelling_cancels_the_overlapping_runs(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        cancelled: list[int] = []

        async def tick() -> None:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(1)
                raise

        task = make(loop, tick, overlap=True, seconds=0.001)

        async def scenario() -> None:
            task.start()
            await asyncio.sleep(0.02)
            task.cancel()
            await asyncio.sleep(0.02)

        run(loop, scenario())
        assert cancelled


class TestDescriptor:
    def test_loop_in_a_class_is_bound_per_instance(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        seen: list[Any] = []

        class Cog:
            @tasks.loop(seconds=FAST, count=1, loop=loop)
            async def tick(self, extra: int) -> None:
                seen.append((self, extra))

            @tick.before_loop
            async def before(self) -> None:
                seen.append(("before", self))

            @tick.after_loop
            async def after(self) -> None:
                seen.append(("after", self))

            @tick.error
            async def on_error(self, exc: Exception) -> None:
                seen.append(("error", self))

        a, b = Cog(), Cog()
        assert Cog.tick is Cog.__dict__["tick"]
        assert a.tick is a.tick
        assert a.tick is not b.tick
        assert a.tick._injected is a
        run(loop, a.tick.start(7))
        assert seen == [("before", a), (a, 7), ("after", a)]
        assert run(loop, b.tick.__call__(1)) is None
        assert seen[-1] == (b, 1)

    def test_error_handler_is_copied_to_instances(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        seen: list[Any] = []

        class Cog:
            @tasks.loop(seconds=FAST, loop=loop)
            async def tick(self) -> None:
                raise ValueError

            @tick.error
            async def on_error(self, exc: Exception) -> None:
                seen.append(self)

        cog = Cog()
        with pytest.raises(ValueError):
            run(loop, cog.tick.start())
        assert seen == [cog]


class TestIntervals:
    def test_change_interval_while_running(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick() -> None: ...

        task = make(loop, tick, seconds=60)

        async def scenario() -> None:
            task.start()
            await asyncio.sleep(0.01)
            first = task.next_iteration
            task.change_interval(seconds=120)
            assert task.next_iteration > first
            task.change_interval(seconds=0.001)
            assert task.seconds == 0.001
            task.cancel()
            await asyncio.sleep(0)

        run(loop, scenario())

    def test_change_to_times_while_running(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick() -> None: ...

        task = make(loop, tick, seconds=60)

        async def scenario() -> None:
            task.start()
            await asyncio.sleep(0.01)
            task.change_interval(time=dt.time(3, 0))
            assert task.time == [dt.time(3, 0, tzinfo=dt.timezone.utc)]
            assert task.seconds is None
            task.change_interval(hours=1)
            assert task.hours == 1
            task.cancel()
            await asyncio.sleep(0)

        run(loop, scenario())

    def test_time_based_loop_runs_at_the_given_time(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        ran: list[dt.datetime] = []

        async def tick() -> None:
            ran.append(dt.datetime.now(dt.timezone.utc))
            task.cancel()

        target = dt.datetime.now(dt.timezone.utc) + dt.timedelta(milliseconds=40)
        task = tasks.loop(time=target.timetz(), loop=loop)(tick)
        started = task.start()
        with pytest.raises(asyncio.CancelledError):
            run(loop, started)
        assert len(ran) == 1
        assert ran[0] >= target - dt.timedelta(milliseconds=5)

    def test_time_based_loop_with_several_times(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        ran: list[int] = []

        async def tick() -> None:
            ran.append(1)
            if len(ran) == 2:
                task.cancel()

        now = dt.datetime.now(dt.timezone.utc)
        times = [
            (now + dt.timedelta(milliseconds=30)).timetz(),
            (now + dt.timedelta(milliseconds=60)).timetz(),
        ]
        task = tasks.loop(time=times, loop=loop)(tick)
        started = task.start()
        with pytest.raises(asyncio.CancelledError):
            run(loop, started)
        assert ran == [1, 1]

    def test_next_sleep_time_for_times_already_passed(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick() -> None: ...

        past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).timetz()
        task = tasks.loop(time=past, loop=loop)(tick)
        task._prepare_time_index()
        nxt = task._get_next_sleep_time()
        assert nxt > dt.datetime.now(dt.timezone.utc)
        assert nxt - dt.datetime.now(dt.timezone.utc) < dt.timedelta(days=1)

    def test_next_sleep_time_wraps_to_the_next_day(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick() -> None: ...

        task = tasks.loop(time=[dt.time(1), dt.time(2)], loop=loop)(tick)
        task._time_index = 2
        nxt = task._get_next_sleep_time()
        tomorrow = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).date()
        assert task._time_index == 0
        assert (nxt.date(), nxt.hour) == (tomorrow, 1)

    def test_next_sleep_time_after_the_first_iteration(
        self, loop: asyncio.AbstractEventLoop
    ) -> None:
        async def tick() -> None: ...

        task = tasks.loop(time=[dt.time(1), dt.time(2)], loop=loop)(tick)
        task._current_loop = 1
        task._time_index = 0
        task._last_iteration = dt.datetime(2030, 1, 1, 1, 0, tzinfo=dt.timezone.utc)
        assert task._get_next_sleep_time() == dt.datetime(
            2030, 1, 1, 1, 0, tzinfo=dt.timezone.utc
        )
        task._last_iteration = dt.datetime(2030, 1, 1, 3, 0, tzinfo=dt.timezone.utc)
        task._time_index = 1
        assert task._get_next_sleep_time() == dt.datetime(
            2030, 1, 2, 2, 0, tzinfo=dt.timezone.utc
        )

    def test_prepare_time_index(self, loop: asyncio.AbstractEventLoop) -> None:
        async def tick() -> None: ...

        task = tasks.loop(time=[dt.time(1), dt.time(5)], loop=loop)(tick)
        task._prepare_time_index(dt.datetime(2030, 1, 1, 2, tzinfo=dt.timezone.utc))
        assert task._time_index == 1
        task._prepare_time_index(dt.datetime(2030, 1, 1, 23, tzinfo=dt.timezone.utc))
        assert task._time_index == 0


class TestSleepHandle:
    def test_fires_and_recalculates(self, loop: asyncio.AbstractEventLoop) -> None:
        async def scenario() -> None:
            far = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
            handle = SleepHandle(far, loop=asyncio.get_running_loop())
            assert not handle.done()
            handle.recalculate(dt.datetime.now(dt.timezone.utc))
            assert await asyncio.wait_for(handle.wait(), 1) is True
            assert handle.done()
            handle._set_result_safe()

        run(loop, scenario())

    def test_cancel(self, loop: asyncio.AbstractEventLoop) -> None:
        async def scenario() -> None:
            far = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
            handle = SleepHandle(far, loop=asyncio.get_running_loop())
            handle.cancel()
            assert handle.done()
            with pytest.raises(asyncio.CancelledError):
                await handle.wait()

        run(loop, scenario())


def test_library_exception_types_are_valid_by_default(
    loop: asyncio.AbstractEventLoop,
) -> None:
    async def tick() -> None: ...

    task = make(loop, tick)
    assert discord.ConnectionClosed in task._valid_exception
    assert discord.GatewayNotFound in task._valid_exception
