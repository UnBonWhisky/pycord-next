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

import datetime as dt
import functools
import importlib
import pkgutil
import random
import re
import types
import typing
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Union, get_args, get_origin

import typing_extensions as te

import discord.types
from discord.enums import Enum as DiscordEnum
from discord.flags import BaseFlags
from tests.payloads.overrides import OVERRIDES

NoneType = type(None)

DISCORD_EPOCH = 1420070400000
BASE_TIMESTAMP_MS = 1_700_000_000_000
MAX_DEPTH = 6
HARD_DEPTH = 24
MAX_CHOICES = 8
UNION_TYPES = (Union, types.UnionType)
OPTIONAL_WRAPPERS = (te.NotRequired, te.Required, typing.NotRequired, typing.Required)

HEX_FIELDS = frozenset(
    {"avatar", "icon", "banner", "splash", "discovery_splash", "hash"}
)
URL_FIELDS = frozenset({"url", "proxy_url", "icon_url", "proxy_icon_url", "avatar_url"})
NUMERIC_STRING_FIELDS = frozenset(
    {
        "permissions",
        "permissions_new",
        "allow",
        "deny",
        "allow_new",
        "deny_new",
        "default_member_permissions",
        "member_permissions",
        "app_permissions",
        "bitrate",
        "version",
    }
)
TIMESTAMP_SUFFIXES = (
    "_at",
    "_time",
    "_since",
    "_until",
    "_start",
    "_end",
    "_date",
    "expiry",
)
SMALL_INT_FIELDS = frozenset(
    {"position", "count", "max_age", "max_uses", "uses", "size"}
)


def _load_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    for info in pkgutil.iter_modules(discord.types.__path__):
        module = importlib.import_module(f"discord.types.{info.name}")
        for name, value in vars(module).items():
            if name.startswith("_") or name in namespace:
                continue
            if te.is_typeddict(value) or get_origin(value) is not None:
                namespace[name] = value
    return namespace


FALLBACK_NAMESPACE: dict[str, Any] = _load_namespace()
FALLBACK_NAMESPACE["InteractionChannel"] = FALLBACK_NAMESPACE["Channel"]


def is_union(tp: Any) -> bool:
    return get_origin(tp) in UNION_TYPES


def is_snowflake(tp: Any) -> bool:
    return is_union(tp) and {a for a in get_args(tp) if a is not NoneType} == {str, int}


def _try_hints(
    tp: Any, localns: dict[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        return te.get_type_hints(tp, localns=localns or None, include_extras=True), None
    except NameError as exc:
        return None, exc.name


@functools.cache
def type_hints(tp: Any) -> dict[str, Any]:
    localns: dict[str, Any] = {}
    while True:
        hints, missing = _try_hints(tp, localns)
        if hints is not None:
            return hints
        if missing is None or missing in localns or missing not in FALLBACK_NAMESPACE:
            raise NameError(missing)
        localns[missing] = FALLBACK_NAMESPACE[missing]


def unwrap(tp: Any) -> tuple[Any, bool | None]:
    optional: bool | None = None
    while True:
        origin = get_origin(tp)
        if origin in (te.NotRequired, typing.NotRequired):
            optional = True
            tp = get_args(tp)[0]
        elif origin in (te.Required, typing.Required):
            optional = False
            tp = get_args(tp)[0]
        elif origin is te.Annotated:
            tp = get_args(tp)[0]
        else:
            return tp, optional


def snowflake(rng: random.Random) -> str:
    timestamp = BASE_TIMESTAMP_MS + rng.randrange(0, 86_400_000 * 365)
    return str(((timestamp - DISCORD_EPOCH) << 22) | rng.getrandbits(22))


def iso_timestamp(rng: random.Random) -> str:
    moment = dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(
        seconds=rng.randrange(0, 86_400 * 365)
    )
    return moment.isoformat()


@dataclass
class Generator:
    seed: int = 0
    minimal: bool = False
    choice: int = 0
    arity: int = 1
    _path: list[str] = field(default_factory=list)

    def rng(self) -> random.Random:
        return random.Random(f"{self.seed}/{'.'.join(self._path)}")  # noqa: S311

    def _choose(self, count: int) -> int:
        self.arity = max(self.arity, min(count, MAX_CHOICES))
        return self.choice % count

    def value(self, tp: Any, name: str, depth: int) -> Any:
        if depth > HARD_DEPTH:
            raise RecursionError(".".join(self._path))
        tp, _ = unwrap(tp)
        shallow = self.minimal or depth > MAX_DEPTH
        if tp is Any or tp is object:
            return "value"
        if tp is None or tp is NoneType:
            return None
        origin = get_origin(tp)
        if origin is Literal:
            args = get_args(tp)
            return args[self._choose(len(args))]
        if origin in UNION_TYPES:
            args = get_args(tp)
            rest = [a for a in args if a is not NoneType]
            if len(rest) != len(args) and shallow:
                return None
            if is_snowflake(tp):
                return snowflake(self.rng())
            return self.value(rest[self._choose(len(rest))], name, depth)
        if te.is_typeddict(tp):
            return self.typeddict(tp, depth)
        if origin in (list, set, frozenset, Sequence, typing.Sequence, tuple):
            if depth > MAX_DEPTH:
                return []
            args = get_args(tp)
            inner = args[0] if args else Any
            self._path.append("0")
            try:
                return [self.value(inner, name, depth + 1)]
            finally:
                self._path.pop()
        if origin in (dict, Mapping, typing.Mapping):
            args = get_args(tp)
            key_tp, val_tp = args if len(args) == 2 else (str, Any)
            self._path.append("k")
            try:
                key = self.value(key_tp, "key", depth + 1)
                if key_tp is str:
                    key = "key"
                return {key: self.value(val_tp, name, depth + 1)}
            finally:
                self._path.pop()
        if tp is dict:
            return {}
        if tp is list:
            return []
        return self.scalar(tp, name)

    def scalar(self, tp: Any, name: str) -> Any:
        rng = self.rng()
        if tp is bool:
            return rng.random() < 0.5
        if tp is int:
            if name.endswith(("color", "colour")) or name in ("colors", "colours"):
                return rng.randrange(0, 0xFFFFFF)
            if name in SMALL_INT_FIELDS:
                return rng.randrange(1, 50)
            return rng.randrange(1, 1000)
        if tp is float:
            return round(rng.uniform(1.0, 100.0), 3)
        if tp is bytes:
            return b"data"
        if tp is str:
            return self.string(name, rng)
        if isinstance(tp, type) and issubclass(tp, BaseFlags):
            return 0
        if isinstance(tp, type) and issubclass(tp, DiscordEnum):
            values = list(tp._enum_value_map_)
            return values[self._choose(len(values))]
        raise TypeError(f"cannot generate {tp!r} for field {'.'.join(self._path)}")

    def string(self, name: str, rng: random.Random) -> str:
        if (
            name.endswith(TIMESTAMP_SUFFIXES)
            or "timestamp" in name
            or name in ("start", "end")
        ):
            return iso_timestamp(rng)
        if name in NUMERIC_STRING_FIELDS or name.endswith("_permissions"):
            return str(rng.randrange(0, 2**20))
        if name in HEX_FIELDS or name.endswith(("_hash", "_icon", "_banner")):
            return f"{rng.getrandbits(128):032x}"
        if name in URL_FIELDS or name.endswith("_url"):
            return f"https://example.com/{name}/{rng.randrange(1000)}"
        if name == "burst_colors":
            return f"#{rng.randrange(0, 0xFFFFFF):06x}"
        if name == "id" or name.endswith("_id"):
            return snowflake(rng)
        if name == "discriminator":
            return f"{rng.randrange(0, 10000):04d}"
        if name == "locale":
            return "en-US"
        return f"{name}-{rng.randrange(1000)}"

    def typeddict(self, tp: Any, depth: int) -> dict[str, Any]:
        hints = type_hints(tp)
        required = tp.__required_keys__
        result: dict[str, Any] = {}
        for key, raw_hint in hints.items():
            hint, optional = unwrap(raw_hint)
            is_required = key in required if optional is None else not optional
            if not is_required and (self.minimal or depth >= MAX_DEPTH):
                continue
            self._path.append(key)
            try:
                result[key] = self.value(hint, key, depth + 1)
            finally:
                self._path.pop()
        override = OVERRIDES.get(tp)
        if override is not None:
            result = override(result)
        return result


def generate(tp: Any, *, seed: int = 0, minimal: bool = False, choice: int = 0) -> Any:
    return Generator(seed=seed, minimal=minimal, choice=choice).value(tp, "", 0)


def branches(tp: Any) -> list[Any]:
    tp, _ = unwrap(tp)
    if is_union(tp) and not is_snowflake(tp):
        return [a for a in get_args(tp) if a is not NoneType]
    return [tp]


@dataclass(frozen=True)
class Variant:
    id: str
    payload: Any


def variants(tp: Any, *, seed: int = 0) -> Iterator[Variant]:
    seen: set[str] = set()
    for branch in branches(tp):
        label = getattr(branch, "__name__", None) or re.sub(r"\W+", "_", str(branch))
        for minimal in (False, True):
            probe = Generator(seed=seed, minimal=minimal, choice=0)
            probe.value(branch, "", 0)
            for choice in range(probe.arity):
                payload = generate(branch, seed=seed, minimal=minimal, choice=choice)
                fingerprint = repr(payload)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                yield Variant(
                    f"{label}-{'min' if minimal else 'full'}-{choice}", payload
                )
