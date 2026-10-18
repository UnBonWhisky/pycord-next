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

from __future__ import annotations

import ast
import collections
import inspect
import pathlib
import py_compile
import runpy
import sys

import pytest

import discord
import discord.ext.commands
import discord.gateway

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
FILES = sorted(EXAMPLES.rglob("*.py"))
IDS = [str(f.relative_to(EXAMPLES)) for f in FILES]

# Sync on some class, so only flagged when the receiver is not one of these names.
SYNC_RECEIVERS = {"author", "member", "user", "lobby", "cog", "self_member"}


def _collect_getters() -> tuple[set[str], set[str], set[str]]:
    coroutines: dict[str, set[str]] = collections.defaultdict(set)
    generators: dict[str, set[str]] = collections.defaultdict(set)
    sync: dict[str, set[str]] = collections.defaultdict(set)
    seen: set[type] = set()
    for module in list(sys.modules.values()):
        if not getattr(module, "__name__", "").startswith("discord"):
            continue
        for value in list(vars(module).values()):
            if not inspect.isclass(value) or value in seen:
                continue
            if not value.__module__.startswith("discord"):
                continue
            seen.add(value)
            for name, attr in vars(value).items():
                if not name.startswith("get_"):
                    continue
                func = getattr(attr, "__func__", attr)
                if inspect.isasyncgenfunction(func):
                    generators[name].add(value.__name__)
                elif inspect.iscoroutinefunction(func):
                    coroutines[name].add(value.__name__)
                elif callable(func):
                    sync[name].add(value.__name__)
    return set(coroutines), set(generators), set(sync)


COROUTINE_GETTERS, GENERATOR_GETTERS, SYNC_GETTERS = _collect_getters()
AMBIGUOUS = (COROUTINE_GETTERS | GENERATOR_GETTERS) & SYNC_GETTERS
SCHEDULERS = {
    "gather",
    "create_task",
    "ensure_future",
    "run_until_complete",
    "wait_for",
}


def _receiver(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        value = func.value
        if isinstance(value, ast.Attribute):
            return value.attr
        if isinstance(value, ast.Name):
            return value.id
    return None


def find_unawaited_getters(source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    problems: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        name = node.func.attr
        if name not in COROUTINE_GETTERS | GENERATOR_GETTERS:
            continue
        if name in AMBIGUOUS and _receiver(node) in SYNC_RECEIVERS:
            continue
        parent = parents.get(node)
        if name in GENERATOR_GETTERS:
            if isinstance(parent, ast.comprehension) and parent.is_async:
                continue
            if isinstance(parent, ast.AsyncFor):
                continue
            problems.append(
                (node.lineno, f"{name}() is an async generator, use `async for`")
            )
            continue
        if isinstance(parent, ast.Await):
            continue
        if isinstance(parent, ast.Call):
            func = parent.func
            called = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            if called in SCHEDULERS:
                continue
        problems.append((node.lineno, f"{name}() must be awaited"))
    return problems


def test_example_files_found() -> None:
    assert len(FILES) > 40
    assert (EXAMPLES / "caching" / "redis_cache.py").is_file()


def test_getter_lists_cover_the_breaking_table() -> None:
    for name in (
        "get_guild",
        "get_user",
        "get_channel",
        "get_member",
        "get_role",
        "get_emoji",
    ):
        assert name in COROUTINE_GETTERS
    assert {"get_all_channels", "get_all_members"} <= GENERATOR_GETTERS


@pytest.mark.parametrize("path", FILES, ids=IDS)
def test_compiles(path: pathlib.Path, tmp_path: pathlib.Path) -> None:
    py_compile.compile(str(path), cfile=str(tmp_path / "out.pyc"), doraise=True)


@pytest.mark.parametrize("path", FILES, ids=IDS)
def test_no_unawaited_getters(path: pathlib.Path) -> None:
    problems = find_unawaited_getters(path.read_text(encoding="utf-8"))
    assert not problems, f"{path.relative_to(ROOT)}: {problems}"


@pytest.mark.parametrize("path", FILES, ids=IDS)
def test_imports_without_network(
    path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> None:
        return None

    async def fake_start(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(discord.Client, "run", fake_run)
    monkeypatch.setattr(discord.Client, "start", fake_start)
    monkeypatch.setattr(discord.Client, "login", fake_start)
    for var in ("DISCORD_TOKEN", "TOKEN", "BOT_TOKEN"):
        monkeypatch.setenv(var, "token")
    monkeypatch.syspath_prepend(str(path.parent))
    monkeypatch.setattr(sys, "argv", [str(path)])
    before = set(sys.modules)
    try:
        runpy.run_path(str(path), run_name="__main__")
    except ModuleNotFoundError as error:
        if error.name and error.name.split(".")[0] != "discord":
            pytest.skip(f"optional dependency {error.name} is not installed")
        raise
    finally:
        for name in set(sys.modules) - before:
            module = sys.modules[name]
            file = getattr(module, "__file__", None)
            if file and str(EXAMPLES) in str(file):
                del sys.modules[name]


def test_checker_flags_unawaited_calls() -> None:
    source = (
        "async def f(bot, guild, message):\n"
        "    a = bot.get_guild(1)\n"
        "    b = await guild.get_member(1)\n"
        "    c = message.author.get_role(1)\n"
        "    for x in bot.get_all_members():\n"
        "        pass\n"
        "    async for y in bot.get_all_channels():\n"
        "        pass\n"
    )
    found = find_unawaited_getters(source)
    assert [line for line, _ in found] == [2, 5]
