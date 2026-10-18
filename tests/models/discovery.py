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
import importlib
import importlib.util
import inspect
import pkgutil
import sys
import types
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_args, get_origin

import typing_extensions as te

import discord
from discord import types as t
from tests.payloads.generator import FALLBACK_NAMESPACE, branches, unwrap

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

SKIPPED_PACKAGES = (
    "discord.types",
    "discord.ui",
    "discord.ext",
    "discord.voice",
    "discord.bin",
    "discord.__main__",
)
PAYLOAD_PARAMS = ("data", "payload")
PAYLOAD_OVERRIDES: dict[str, Any] = {
    "discord.embeds.Embed.from_dict": t.embed.Embed,
    "discord.embeds.EmbedAuthor.from_dict": t.embed.EmbedAuthor,
    "discord.embeds.EmbedFooter.from_dict": t.embed.EmbedFooter,
    "discord.embeds.EmbedProvider.from_dict": t.embed.EmbedProvider,
    "discord.embeds.EmbedField.from_dict": t.embed.EmbedField,
    "discord.embeds.EmbedMedia.from_dict": t.embed.EmbedImage,
    "discord.webhook.async_.PartialWebhookChannel": t.channel.PartialChannel,
    "discord.webhook.async_.PartialWebhookGuild": t.webhook.SourceGuild,
}
UNION_ORIGINS = (typing.Union, types.UnionType)


@dataclass(frozen=True)
class Skipped:
    target: str
    reason: str


@dataclass(frozen=True)
class ModelCase:
    cls: type
    ctor: str
    payload_param: str
    payload_type: Any
    context_params: tuple[str, ...]

    @property
    def id(self) -> str:
        suffix = "" if self.ctor == "__init__" else f".{self.ctor}"
        return f"{self.cls.__module__.removeprefix('discord.')}.{self.cls.__name__}{suffix}"

    @property
    def factory(self) -> Callable[..., Any]:
        return self.cls if self.ctor == "__init__" else getattr(self.cls, self.ctor)

    def build(self, payload: Any, provide: Callable[[ModelCase, str], Any]) -> Any:
        kwargs = {name: provide(self, name) for name in self.context_params}
        kwargs[self.payload_param] = payload
        return self.factory(**kwargs)


_TYPE_CHECKING_NAMES: dict[str, dict[str, Any]] = {}


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _import(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except (ImportError, discord.MissingVoiceDependenciesError):
        return None


def _from_import_names(item: ast.ImportFrom, package: str) -> dict[str, Any]:
    target = importlib.util.resolve_name(
        "." * item.level + (item.module or ""), package
    )
    source = _import(target)
    if source is None:
        return {}
    names: dict[str, Any] = {}
    for alias in item.names:
        value = getattr(source, alias.name, None) or _import(f"{target}.{alias.name}")
        if value is not None:
            names[alias.asname or alias.name] = value
    return names


def type_checking_names(module: ModuleType) -> dict[str, Any]:
    cached = _TYPE_CHECKING_NAMES.get(module.__name__)
    if cached is not None:
        return cached
    names: dict[str, Any] = {}
    filename = getattr(module, "__file__", None)
    if filename:
        tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
        for node in tree.body:
            if not (isinstance(node, ast.If) and _is_type_checking(node.test)):
                continue
            for item in ast.walk(node):
                if isinstance(item, ast.ImportFrom):
                    names.update(_from_import_names(item, module.__package__ or ""))
                elif isinstance(item, ast.Import):
                    for alias in item.names:
                        imported = _import(alias.name)
                        if imported is not None:
                            names[alias.asname or alias.name.split(".")[0]] = imported
    _TYPE_CHECKING_NAMES[module.__name__] = names
    return names


def resolve_annotation(annotation: Any, module: ModuleType) -> Any:
    if not isinstance(annotation, str):
        return annotation
    localns = {**FALLBACK_NAMESPACE, **type_checking_names(module)}
    return eval(annotation, dict(vars(module)), localns)  # noqa: S307


def contains_typeddict(tp: Any) -> bool:
    tp, _ = unwrap(tp)
    if te.is_typeddict(tp):
        return True
    origin = get_origin(tp)
    if origin in UNION_ORIGINS or origin in (list, set, frozenset, tuple):
        return any(contains_typeddict(arg) for arg in get_args(tp))
    return False


def narrow_for_subclass(tp: Any, cls: type) -> Any:
    options = branches(tp)
    matching = [
        option for option in options if getattr(option, "__name__", "") == cls.__name__
    ]
    if matching and len(options) > 1:
        return matching[0]
    return tp


def _payload_type(
    target: str, param: inspect.Parameter, module: ModuleType
) -> tuple[Any, str | None]:
    if target in PAYLOAD_OVERRIDES:
        return PAYLOAD_OVERRIDES[target], None
    if param.annotation is inspect.Parameter.empty:
        return None, "payload parameter is not annotated"
    try:
        payload_type = resolve_annotation(param.annotation, module)
    except Exception as exc:  # noqa: BLE001
        return None, f"payload annotation cannot be resolved: {exc!r}"
    if not contains_typeddict(payload_type):
        return None, f"payload annotation is not a TypedDict ({param.annotation})"
    return payload_type, None


def _describe(
    cls: type,
    ctor: str,
    func: Callable[..., Any],
    module: ModuleType,
    skipped: list[Skipped],
) -> ModelCase | None:
    target = f"{cls.__module__}.{cls.__qualname__}" + (
        "" if ctor == "__init__" else f".{ctor}"
    )
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return None
    params = list(signature.parameters.values())[1:]
    payload_param = next((p for p in params if p.name in PAYLOAD_PARAMS), None)
    if payload_param is None:
        return None
    if any(
        p.kind is p.VAR_KEYWORD or p.kind is p.VAR_POSITIONAL for p in params
    ) or any(p.kind is p.POSITIONAL_ONLY for p in params):
        skipped.append(
            Skipped(
                target, "signature uses *args, **kwargs or positional-only parameters"
            )
        )
        return None
    payload_type, reason = _payload_type(target, payload_param, module)
    if reason is not None:
        skipped.append(Skipped(target, reason))
        return None
    if ctor == "__init__" and "__init__" not in cls.__dict__:
        payload_type = narrow_for_subclass(payload_type, cls)
    context = tuple(
        p.name for p in params if p.name != payload_param.name and p.default is p.empty
    )
    return ModelCase(cls, ctor, payload_param.name, payload_type, context)


def _classes(module: ModuleType) -> list[type]:
    return [
        value
        for value in vars(module).values()
        if inspect.isclass(value) and value.__module__ == module.__name__
    ]


def _modules() -> list[ModuleType]:
    modules = []
    pending = [(discord.__path__, "discord.")]
    while pending:
        path, prefix = pending.pop()
        for info in pkgutil.iter_modules(path, prefix):
            if info.name.startswith(SKIPPED_PACKAGES):
                continue
            module = importlib.import_module(info.name)
            modules.append(module)
            if info.ispkg:
                pending.append((module.__path__, f"{info.name}."))
    return modules


def discover() -> tuple[list[ModelCase], list[Skipped]]:
    cases: list[ModelCase] = []
    skipped: list[Skipped] = []
    for module in _modules():
        for cls in _classes(module):
            init_owner = next(
                (k for k in cls.__mro__ if "__init__" in k.__dict__), None
            )
            if init_owner is not None and init_owner is not object:
                owner_module = sys.modules[init_owner.__module__]
                case = _describe(
                    cls,
                    "__init__",
                    init_owner.__dict__["__init__"],
                    owner_module,
                    skipped,
                )
                if case is not None:
                    cases.append(case)
            for name, attribute in cls.__dict__.items():
                if isinstance(attribute, classmethod) and not name.startswith("__"):
                    case = _describe(cls, name, attribute.__func__, module, skipped)
                    if case is not None:
                        cases.append(case)
    return cases, skipped
