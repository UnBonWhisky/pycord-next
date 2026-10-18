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

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCH = re.compile(r"""dispatch\(\s*["']([a-z0-9_]+)["']""")
DIRECTIVE = re.compile(
    r"^(?:\.\. function:: |[ ]{14})(?:discord\.ext\.\w+\.)?(on_[a-z0-9_]+)\(",
    re.MULTILINE,
)

# Events master pycord never documents as events either.
EXCLUDED: set[str] = {
    # Only documented as the Bot.on_application_command_auto_complete method.
    "application_command_auto_complete",
    # Documented only as the View.on_error / Modal.on_error methods.
    "view_error",
    "modal_error",
}


def _dispatched() -> set[str]:
    names: set[str] = set()
    for path in (ROOT / "discord").rglob("*.py"):
        names.update(DISPATCH.findall(path.read_text(encoding="utf-8")))
    return names


def _documented() -> set[str]:
    names: set[str] = set()
    for path in (ROOT / "docs").rglob("*.rst"):
        if "locales" in path.parts:
            continue
        names.update(DIRECTIVE.findall(path.read_text(encoding="utf-8")))
    return names


def test_dispatch_sites_found() -> None:
    assert len(_dispatched()) > 50


@pytest.mark.parametrize("name", sorted(_dispatched() - EXCLUDED))
def test_event_is_documented(name: str) -> None:
    assert f"on_{name}" in _documented(), f"on_{name} is dispatched but not documented"
