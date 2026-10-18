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

Migrate a bot written for pycord to pycord-next.

Usage::

    python migrate.py path/to/bot            # show the changes as a diff
    python migrate.py path/to/bot --write    # apply them
    python migrate.py path/to/bot --check    # exit with 1 when changes are needed

The script only uses the standard library (Python 3.10+). It rewrites what can be
rewritten safely and reports, with ``file:line``, what needs a decision:

- the cache lookups by id of ``Client`` / ``Bot`` and ``Guild`` are awaited
  (``await bot.get_guild(id)``, ``(await guild.get_member(id)).name``);
- ``get_all_channels()`` / ``get_all_members()`` are iterated with ``async for``;
- ``Client.clear()`` is awaited;
- ``parse_*`` overrides of a ``ConnectionState`` subclass become ``async def``;
- ``Attachment.to_dict()["spoiler"]`` reads ``"is_spoiler"``.

A call is only rewritten when its receiver is known to be a client or a guild
(``bot``, ``client``, ``guild``, ``ctx.bot``, ``interaction.client``, ``message.guild``,
annotated parameters, ``self`` in a ``Client`` subclass, ...). ``--aggressive`` also
rewrites the method names that only exist on ``Client`` / ``Guild`` when the receiver
is unknown. See ``docs/migrating_to_next.rst`` for every change.
"""

from __future__ import annotations

import argparse
import ast
import difflib
import io
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

Kind = Literal["client", "guild", "state"]

DISCORD_MODULES = frozenset({"discord", "commands", "bridge", "ext", "pages", "tasks"})
CLIENT_TYPES = frozenset({"Client", "Bot", "AutoShardedClient", "AutoShardedBot"})
GUILD_TYPES = frozenset({"Guild"})
STATE_TYPES = frozenset({"ConnectionState", "AutoShardedConnectionState"})
CONVERTER_TYPES = frozenset({"GuildChannelConverter", "PartialMessageConverter"})

CLIENT_COROUTINES = frozenset(
    {
        "get_channel",
        "get_message",
        "get_stage_instance",
        "get_guild",
        "get_user",
        "get_emoji",
        "get_sticker",
        "get_poll",
        "get_sound",
        "clear",
    }
)
CLIENT_ASYNC_GENERATORS = frozenset({"get_all_channels", "get_all_members"})
GUILD_COROUTINES = frozenset(
    {
        "get_channel",
        "get_thread",
        "get_channel_or_thread",
        "get_member",
        "get_member_named",
        "get_role",
        "get_emoji",
        "get_stage_instance",
        "get_scheduled_event",
        "get_sound",
        "_add_channel",
        "_add_member",
        "_remove_member",
        "_add_role",
        "_remove_role",
        "_add_thread",
        "_update_voice_state",
        "_get_and_update_member",
    }
)
STATE_COROUTINES = frozenset(
    {
        "store_user",
        "store_emoji",
        "store_sticker",
        "maybe_store_app_emoji",
        "store_poll",
        "_get_guild",
        "_add_guild",
        "_remove_guild",
        "_get_message",
        "_get_private_channel",
        "_add_private_channel",
        "add_dm_channel",
        "get_channel",
        "get_user",
        "get_emoji",
        "get_sticker",
        "get_poll",
        "_get_sound",
        "deref_user",
        "chunk_guild",
        "is_guild_evicted",
        "process_chunk_requests",
    }
)
UNIQUE_CLIENT_METHODS = frozenset(
    {"get_guild", "get_user", "get_message", "get_poll", "get_sticker"}
)
UNIQUE_GUILD_METHODS = frozenset(
    {"get_channel_or_thread", "get_member_named", "get_scheduled_event"}
)
CLIENT_ATTRIBUTES = frozenset({"bot", "client"})
GUILD_ATTRIBUTES = frozenset({"guild"})
STATE_ATTRIBUTES = frozenset({"_connection", "_state"})
CLIENT_NAMES = frozenset({"bot", "client"})
GUILD_NAMES = frozenset({"guild"})
STATE_NAMES = frozenset({"state", "_state", "connection", "_connection"})
WEBSOCKET_COMMANDS = frozenset(
    {"change_presence", "request_chunks", "voice_state", "request_soundboard_sounds"}
)
ITEM = "_item"
SENTINELS: dict[str, Kind | None] = {
    "<client>": "client",
    "<guild>": "guild",
    "<state>": "state",
    "<None>": None,
}

GUIDE = "docs/migrating_to_next.rst"


@dataclass(frozen=True)
class Note:
    """A change made to a file, or something to review by hand."""

    line: int
    column: int
    level: Literal["rewrite", "warning"]
    message: str


@dataclass(order=True)
class Edit:
    """A text replacement, sorted so that nested inserts at one offset compose."""

    start: int
    rank: tuple[int, int]
    end: int = field(compare=False)
    text: str = field(compare=False)


@dataclass
class Result:
    """The outcome of migrating one source file."""

    source: str
    migrated: str
    notes: list[Note]
    error: str | None = None

    @property
    def changed(self) -> bool:
        return self.migrated != self.source


def _discord_name(node: ast.expr) -> str | None:
    """Return the name of ``X`` or ``discord.X``, ``None`` for names of other modules."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        root = node.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name) and root.id in DISCORD_MODULES:
            return node.attr
    return None


def _type_names(annotation: ast.expr | None) -> set[str]:
    if annotation is None:
        return set()
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            annotation = ast.parse(annotation.value, mode="eval").body
        except SyntaxError:
            return set()
    names: set[str] = set()
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name | ast.Attribute):
            name = _discord_name(node)
            if name is not None:
                names.add(name)
    return names


def _kind_of_annotation(annotation: ast.expr | None) -> Kind | None:
    names = _type_names(annotation)
    if names & CLIENT_TYPES:
        return "client"
    if names & GUILD_TYPES:
        return "guild"
    if names & STATE_TYPES:
        return "state"
    return None


def _base_names(node: ast.ClassDef) -> set[str]:
    return {name for base in node.bases if (name := _discord_name(base)) is not None}


class Migrator:
    """Rewrite one module for pycord-next."""

    def __init__(self, source: str, *, aggressive: bool = False) -> None:
        self.source = source
        self.aggressive = aggressive
        self.tree = ast.parse(source)
        self.parents: dict[ast.AST, ast.AST] = {}
        self.depths: dict[ast.AST, int] = {self.tree: 0}
        for parent in ast.walk(self.tree):
            for child in ast.iter_child_nodes(parent):
                self.parents[child] = parent
                self.depths[child] = self.depths[parent] + 1
        self.line_starts = [0]
        for match in re.finditer("\n", source):
            self.line_starts.append(match.end())
        self.lines = source.split("\n")
        self.envs: dict[ast.AST, dict[str, Kind | None]] = {}
        self.client_classes = set(CLIENT_TYPES)
        classes = [n for n in ast.walk(self.tree) if isinstance(n, ast.ClassDef)]
        for _ in classes:
            for node in classes:
                if _base_names(node) & self.client_classes:
                    self.client_classes.add(node.name)
        self.edits: list[Edit] = []
        self.notes: list[Note] = []

    def offset(self, line: int, column: int) -> int:
        """Convert an AST position (1-based line, UTF-8 column) to a text offset."""
        text = self.lines[line - 1].encode()[:column].decode(errors="replace")
        return self.line_starts[line - 1] + len(text)

    def start(self, node: ast.expr | ast.stmt) -> int:
        return self.offset(node.lineno, node.col_offset)

    def end(self, node: ast.expr | ast.stmt) -> int:
        line = node.lineno if node.end_lineno is None else node.end_lineno
        column = node.col_offset if node.end_col_offset is None else node.end_col_offset
        return self.offset(line, column)

    def note(
        self, node: ast.AST, level: Literal["rewrite", "warning"], message: str
    ) -> None:
        self.notes.append(
            Note(
                getattr(node, "lineno", 0),
                getattr(node, "col_offset", 0) + 1,
                level,
                message,
            )
        )

    def insert(self, offset: int, text: str, node: ast.AST, *, closing: bool) -> None:
        depth = self.depths[node]
        rank = (0, -depth) if closing else (2, depth)
        self.edits.append(Edit(offset, rank, offset, text))

    def replace(self, start: int, end: int, text: str) -> None:
        self.edits.append(Edit(start, (1, 0), end, text))

    def scope_of(self, node: ast.AST) -> ast.AST:
        """Return the function, lambda, class or module whose body evaluates ``node``."""
        child, parent = node, self.parents.get(node)
        while parent is not None:
            if isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef):
                if child in parent.body:
                    return parent
            elif isinstance(parent, ast.Lambda | ast.ClassDef):
                if isinstance(parent, ast.Lambda) and child is parent.body:
                    return parent
                if isinstance(parent, ast.ClassDef) and child in parent.body:
                    return parent
            child, parent = parent, self.parents.get(parent)
        return self.tree

    def await_blocker(self, node: ast.AST) -> str | None:
        """Explain why ``await`` cannot be added in front of ``node``, if it cannot."""
        child, parent = node, self.parents.get(node)
        while parent is not None:
            if isinstance(parent, ast.JoinedStr):
                return "it is inside an f-string"
            if (
                isinstance(parent, ast.GeneratorExp)
                and child is not parent.generators[0].iter
            ):
                return "it is inside a generator expression"
            if isinstance(parent, ast.Lambda) and child is parent.body:
                return "it is inside a lambda"
            if isinstance(parent, ast.ClassDef) and child in parent.body:
                return f"it is in the body of the class {parent.name!r}"
            if isinstance(parent, ast.AsyncFunctionDef) and child in parent.body:
                return None
            if isinstance(parent, ast.FunctionDef) and child in parent.body:
                return f"the function {parent.name!r} is not async"
            child, parent = parent, self.parents.get(parent)
        return "it runs at module level"

    def env_of(self, scope: ast.AST) -> dict[str, Kind | None]:
        if scope in self.envs:
            return self.envs[scope]
        env: dict[str, Kind | None] = {}
        self.envs[scope] = env
        if isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            arguments = scope.args
            for arg in (
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
            ):
                if arg.annotation is not None:
                    env[arg.arg] = _kind_of_annotation(arg.annotation)
            owner = self.parents.get(scope)
            if isinstance(owner, ast.ClassDef) and arguments.args:
                bases = _base_names(owner)
                first = arguments.args[0].arg
                if bases & self.client_classes:
                    env.setdefault(first, "client")
                elif bases & STATE_TYPES:
                    env.setdefault(first, "state")
        fixed = dict(env)
        for _ in range(2):
            found: dict[str, set[Kind | None]] = {}
            for node in self.scope_nodes(scope):
                for name, value in self.bindings(node):
                    found.setdefault(name, set()).add(self.kind(value))
            for name, kinds in found.items():
                merged: set[Kind | None] = set(kinds)
                if name in fixed:
                    merged.add(fixed[name])
                env[name] = merged.pop() if len(merged) == 1 else None
        return env

    def scope_nodes(self, scope: ast.AST) -> Iterator[ast.AST]:
        stack = list(ast.iter_child_nodes(scope))
        while stack:
            node = stack.pop()
            yield node
            if isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef
            ):
                continue
            stack.extend(ast.iter_child_nodes(node))

    def bindings(self, node: ast.AST) -> Iterator[tuple[str, ast.expr]]:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    yield target.id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            kind = _kind_of_annotation(node.annotation)
            yield node.target.id, ast.Name(id=f"<{kind}>")
        elif isinstance(node, ast.NamedExpr):
            yield node.target.id, node.value
        elif (
            isinstance(node, ast.For | ast.AsyncFor | ast.comprehension)
            and isinstance(node.target, ast.Name)
            and self.iterates_guilds(node.iter)
        ):
            yield node.target.id, ast.Name(id="<guild>")

    def iterates_guilds(self, node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "guilds"
            and self.kind(node.value) == "client"
        )

    def lookup(self, node: ast.Name) -> Kind | None:
        if node.id in SENTINELS:
            return SENTINELS[node.id]
        scope = self.scope_of(node)
        while True:
            env = self.env_of(scope)
            if node.id in env:
                return env[node.id]
            if scope is self.tree:
                break
            scope = self.scope_of(scope)
        if node.id in CLIENT_NAMES:
            return "client"
        if node.id in GUILD_NAMES:
            return "guild"
        if node.id in STATE_NAMES:
            return "state"
        return None

    def kind(self, node: ast.expr) -> Kind | None:
        """Tell whether ``node`` evaluates to a client, a guild or a connection state."""
        if isinstance(node, ast.Await):
            return self.kind(node.value)
        if isinstance(node, ast.Name):
            return self.lookup(node)
        if isinstance(node, ast.Attribute):
            if node.attr in CLIENT_ATTRIBUTES:
                return "client"
            if node.attr in GUILD_ATTRIBUTES:
                return "guild"
            if node.attr in STATE_ATTRIBUTES:
                return "state"
            return None
        if isinstance(node, ast.Subscript):
            if self.iterates_guilds(node.value):
                return "guild"
            return None
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in {"get_guild", "fetch_guild"}
                and self.kind(func.value) == "client"
            ):
                return "guild"
            name = _discord_name(func)
            if name == "get" and node.args and self.iterates_guilds(node.args[0]):
                return "guild"
            if name in self.client_classes:
                return "client"
        return None

    def run(self) -> str:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.visit_method_call(node, node.func)
            elif isinstance(node, ast.Attribute):
                self.visit_attribute(node)
            elif isinstance(node, ast.Subscript):
                self.visit_subscript(node)
            elif isinstance(node, ast.ClassDef):
                self.visit_class(node)
            elif isinstance(node, ast.ImportFrom):
                self.visit_import(node)
            elif isinstance(node, ast.Assign | ast.AugAssign | ast.AnnAssign):
                self.visit_assignment(node)
        return self.apply()

    def visit_method_call(self, node: ast.Call, func: ast.Attribute) -> None:
        name = func.attr
        kind = self.kind(func.value)
        if name in {"launch_shard", "launch_shards"}:
            self.note(
                node,
                "warning",
                f"{name}() was removed, the shards are launched by discord.gateway.ShardManager"
                " when the client connects",
            )
            return
        if (
            name in WEBSOCKET_COMMANDS
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "ws"
        ):
            self.note(
                node,
                "warning",
                f"DiscordWebSocket.{name}() moved to the gateway transport: use"
                " client._get_websocket(guild_id) or the public Client / Guild methods",
            )
            return
        if name == "get_desynced_commands":
            self.note(
                node,
                "warning",
                'the "command" of a "delete" action is now the payload dict Discord returned,'
                " not the command name",
            )
            return
        if kind == "client" and name in CLIENT_ASYNC_GENERATORS:
            self.async_iteration(node, f"{name}() is an async generator")
            return
        coroutine = (
            (kind == "client" and name in CLIENT_COROUTINES)
            or (kind == "guild" and name in GUILD_COROUTINES)
            or (kind == "state" and name in STATE_COROUTINES)
        )
        if not coroutine and kind is None and self.receiver_may_be_http(func.value):
            return
        if not coroutine and kind is None:
            unique = name in UNIQUE_CLIENT_METHODS | UNIQUE_GUILD_METHODS
            if unique and self.aggressive:
                coroutine = True
            elif unique or (name in CLIENT_ASYNC_GENERATORS):
                self.note(
                    node,
                    "warning",
                    f"{name}() is awaited in pycord-next when called on a Client or a Guild;"
                    " the receiver could not be identified, review this call",
                )
                return
        if coroutine:
            self.add_await(node, f"{name}() is a coroutine")

    def receiver_may_be_http(self, node: ast.expr) -> bool:
        return isinstance(node, ast.Attribute) and node.attr in {"http", "_http"}

    def add_await(self, node: ast.Call, reason: str) -> None:
        parent = self.parents.get(node)
        if isinstance(parent, ast.Await):
            return
        blocker = self.await_blocker(node)
        if blocker is not None:
            self.note(
                node, "warning", f"{reason} but cannot be awaited here: {blocker}"
            )
            return
        wrap = (
            isinstance(parent, ast.Attribute | ast.Subscript) and parent.value is node
        ) or (isinstance(parent, ast.Call) and parent.func is node)
        self.insert(
            self.start(node), "(await " if wrap else "await ", node, closing=False
        )
        if wrap:
            self.insert(self.end(node), ")", node, closing=True)
        self.note(node, "rewrite", f"{reason}, added await")

    def async_iteration(self, node: ast.Call, reason: str) -> None:
        parent = self.parents.get(node)
        if isinstance(parent, ast.AsyncFor) or (
            isinstance(parent, ast.comprehension) and parent.is_async
        ):
            return
        if isinstance(parent, ast.For) and parent.iter is node:
            blocker = self.await_blocker(parent)
            if blocker is not None:
                self.note(
                    node,
                    "warning",
                    f"{reason} but cannot use async for here: {blocker}",
                )
                return
            self.insert(self.start(parent), "async ", parent, closing=False)
            self.note(node, "rewrite", f"{reason}, changed to async for")
            return
        if isinstance(parent, ast.comprehension) and parent.iter is node:
            owner = self.parents[parent]
            if not isinstance(owner, ast.ListComp | ast.SetComp | ast.DictComp):
                self.note(
                    node,
                    "warning",
                    f"{reason}: iterate it with a list comprehension and async for",
                )
                return
            blocker = self.await_blocker(owner)
            if blocker is not None:
                self.note(
                    node,
                    "warning",
                    f"{reason} but cannot use async for here: {blocker}",
                )
                return
            keyword = self.for_keyword(owner, parent)
            if keyword is None:
                self.note(
                    node, "warning", f"{reason}: use async for in this comprehension"
                )
                return
            self.insert(keyword, "async ", parent.target, closing=False)
            self.note(node, "rewrite", f"{reason}, changed to async for")
            return
        blocker = self.await_blocker(node)
        if blocker is not None:
            self.note(
                node, "warning", f"{reason} but cannot be collected here: {blocker}"
            )
            return
        opening = f"[{ITEM} async for {ITEM} in "
        if (
            isinstance(parent, ast.Call)
            and isinstance(parent.func, ast.Name)
            and parent.func.id == "list"
            and parent.args == [node]
            and not parent.keywords
        ):
            self.replace(self.start(parent), self.start(node), opening)
            self.replace(self.end(node), self.end(parent), "]")
        else:
            self.insert(self.start(node), opening, node, closing=False)
            self.insert(self.end(node), "]", node, closing=True)
        self.note(node, "rewrite", f"{reason}, collected with async for")

    def for_keyword(
        self,
        owner: ast.ListComp | ast.SetComp | ast.DictComp,
        generator: ast.comprehension,
    ) -> int | None:
        index = owner.generators.index(generator)
        if index == 0:
            before: ast.expr = (
                owner.value if isinstance(owner, ast.DictComp) else owner.elt
            )
        else:
            previous = owner.generators[index - 1]
            before = previous.ifs[-1] if previous.ifs else previous.iter
        text = self.source[self.end(before) : self.start(generator.target)]
        matches = list(re.finditer(r"\bfor\b", text))
        if not matches:
            return None
        return self.end(before) + matches[-1].start()

    def visit_attribute(self, node: ast.Attribute) -> None:
        if node.attr == "self_voice_state":
            self.note(
                node,
                "warning",
                "VoiceConnectionState.self_voice_state was replaced by"
                " await VoiceConnectionState.get_self_voice_state()",
            )

    def visit_subscript(self, node: ast.Subscript) -> None:
        value = node.value
        key = node.slice
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "to_dict"
            and isinstance(key, ast.Constant)
            and key.value == "spoiler"
        ):
            quote = self.source[self.start(key)]
            self.replace(self.start(key), self.end(key), f"{quote}is_spoiler{quote}")
            self.note(
                key,
                "rewrite",
                'Attachment.to_dict() uses the documented "is_spoiler" key',
            )

    def visit_class(self, node: ast.ClassDef) -> None:
        bases = _base_names(node)
        for item in node.body:
            if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            sync = isinstance(item, ast.FunctionDef)
            if sync and bases & STATE_TYPES and item.name.startswith("parse_"):
                self.make_async(item, "ConnectionState parsers are coroutines")
            elif (
                sync
                and bases & CONVERTER_TYPES
                and item.name in {"_resolve_channel", "_resolve_thread"}
            ):
                self.make_async(item, f"{item.name}() is a coroutine")
            elif bases & self.client_classes and item.name == "before_identify_hook":
                self.note(
                    item,
                    "warning",
                    "the default before_identify_hook no longer sleeps 5 seconds, the identify"
                    " concurrency is handled by the library",
                )

    def make_async(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, reason: str
    ) -> None:
        start = self.offset(node.lineno, node.col_offset)
        self.insert(start, "async ", node, closing=False)
        self.note(
            node,
            "rewrite",
            f"{reason}, changed to async def: await the coroutines it calls",
        )

    def visit_import(self, node: ast.ImportFrom) -> None:
        if node.module == "discord.voice.utils.buffer":
            removed = [a.name for a in node.names if a.name in {"Buffer", "BaseBuff"}]
            if removed:
                self.note(
                    node,
                    "warning",
                    f"{', '.join(removed)} were removed, JitterBuffer stands alone",
                )

    def visit_assignment(
        self, node: ast.Assign | ast.AugAssign | ast.AnnAssign
    ) -> None:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "ws"
                and self.kind(target.value) == "client"
            ):
                self.note(node, "warning", "Client.ws is a read-only property")

    def apply(self) -> str:
        output: list[str] = []
        cursor = 0
        for edit in sorted(self.edits):
            if edit.start < cursor:
                continue
            output.append(self.source[cursor : edit.start])
            output.append(edit.text)
            cursor = edit.end
        output.append(self.source[cursor:])
        return "".join(output)


def migrate_source(source: str, *, aggressive: bool = False) -> Result:
    """Migrate the text of one module."""
    try:
        migrator = Migrator(source, aggressive=aggressive)
    except SyntaxError as exc:
        return Result(
            source, source, [], f"could not parse: {exc.msg} (line {exc.lineno})"
        )
    migrated = migrator.run()
    notes = sorted(set(migrator.notes), key=lambda n: (n.line, n.column, n.message))
    if migrated != source:
        try:
            ast.parse(migrated)
        except SyntaxError as exc:
            return Result(
                source,
                source,
                notes,
                f"the migrated code would not parse ({exc.msg}, line {exc.lineno}),"
                " nothing was changed",
            )
    return Result(source, migrated, notes)


def read(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding), encoding


def python_files(paths: Iterable[Path]) -> Iterator[Path]:
    skipped = {".git", ".hg", ".venv", "venv", "__pycache__", "build", "dist", ".tox"}
    for path in paths:
        if path.is_dir():
            for file in sorted(path.rglob("*.py")):
                if not skipped & set(file.relative_to(path).parts[:-1]):
                    yield file
        elif path.suffix == ".py" or path.is_file():
            yield path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate a bot written for pycord to pycord-next.",
        epilog=f"Every change is explained in {GUIDE} and CHANGES.md.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="files or directories")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="apply the changes")
    mode.add_argument(
        "--check", action="store_true", help="exit with 1 when a file needs changes"
    )
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help="also await Client/Guild-only lookups on receivers that cannot be identified",
    )
    parser.add_argument("--quiet", action="store_true", help="only print the warnings")
    args = parser.parse_args(argv)

    changed = warnings = errors = 0
    for path in python_files(args.paths):
        try:
            source, encoding = read(path)
        except (OSError, UnicodeDecodeError, SyntaxError) as exc:
            print(f"{path}: error: {exc}", file=sys.stderr)
            errors += 1
            continue
        result = migrate_source(source, aggressive=args.aggressive)
        if result.error is not None:
            print(f"{path}: error: {result.error}", file=sys.stderr)
            errors += 1
        for note in result.notes:
            if note.level == "warning":
                warnings += 1
            elif args.quiet:
                continue
            print(f"{path}:{note.line}:{note.column}: {note.level}: {note.message}")
        if not result.changed:
            continue
        changed += 1
        if args.write:
            with path.open("w", encoding=encoding, newline="") as file:
                file.write(result.migrated)
        elif not args.check and not args.quiet:
            sys.stdout.writelines(
                difflib.unified_diff(
                    result.source.splitlines(keepends=True),
                    result.migrated.splitlines(keepends=True),
                    f"a/{path}",
                    f"b/{path}",
                )
            )

    action = "migrated" if args.write else "to migrate"
    print(
        f"{changed} file(s) {action}, {warnings} warning(s) to review, {errors} error(s)."
        f" See {GUIDE}.",
        file=sys.stderr,
    )
    if errors:
        return 2
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
