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

import importlib
import inspect
import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs"

PACKAGES = (
    "discord",
    "discord.ui",
    "discord.ext.commands",
    "discord.ext.bridge",
    "discord.ext.pages",
    "discord.ext.tasks",
    "discord.cache",
    "discord.gateway",
    "discord.http",
    "discord.state",
)

# Names that pycord (master) never documented either and that are internal
# plumbing exposed only because they are importable: base mixins of the bot and
# the cogs, the enum base class, the HTTP layer and the connection state.
_INTERNAL_HTTP = {
    "API_VERSION",
    "HTTPClient",
    "MaybeUnlock",
    "Route",
    "parse_response",
    "MISSING",
    "DiscordClientWebSocketResponse",
}
EXCLUDED: dict[str, set[str]] = {
    "discord": {"ApplicationCommandMixin", "CogMixin", "Enum"} | _INTERNAL_HTTP,
    # the registry of waiting modals, used by the connection state only
    "discord.ui": {"ModalStore"},
    "discord.ext.commands": set(),
    "discord.ext.bridge": set(),
    "discord.ext.pages": set(),
    "discord.ext.tasks": set(),
    "discord.cache": set(),
    "discord.gateway": set(),
    "discord.http": _INTERNAL_HTTP,
    "discord.state": {
        "AutoShardedConnectionState",
        "ChunkRequest",
        "ConnectionState",
        "logging_coroutine",
    },
}

DIRECTIVE = re.compile(
    r"^\s*\.\.\s+(?:auto\w+|py:\w+|attributetable|class|function|data|exception)::\s*([A-Za-z_][\w.]*)",
    re.MULTILINE,
)


def _public_names(package: str) -> set[str]:
    module = importlib.import_module(package)
    exported = getattr(module, "__all__", None)
    if exported is not None:
        return {name for name in exported if not name.startswith("_")}
    names = set()
    for name, obj in vars(module).items():
        if name.startswith("_") or inspect.ismodule(obj):
            continue
        owner = getattr(obj, "__module__", None)
        if isinstance(owner, str) and (
            owner == package or owner.startswith(package + ".")
        ):
            names.add(getattr(obj, "__name__", name) if inspect.isclass(obj) else name)
    return names


def _documented_names() -> set[str]:
    documented: set[str] = set()
    for path in DOCS.rglob("*.rst"):
        if "_build" in path.parts or "locales" in path.parts:
            continue
        for match in DIRECTIVE.finditer(path.read_text(encoding="utf-8")):
            documented.add(match.group(1).rsplit(".", 1)[-1])
    return documented


@pytest.mark.parametrize("package", PACKAGES)
def test_public_api_is_documented(package: str) -> None:
    documented = _documented_names()
    missing = sorted(_public_names(package) - documented - EXCLUDED[package])
    assert not missing, f"{package}: undocumented public names: {', '.join(missing)}"
