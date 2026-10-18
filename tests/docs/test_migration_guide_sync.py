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

ROOT = Path(__file__).resolve().parents[2]
CHANGES = ROOT / "CHANGES.md"
GUIDE = ROOT / "docs" / "migrating_to_next.rst"

CODE = re.compile(r"`([^`]+)`")
DOTTED = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+")
WORD = re.compile(r"[A-Za-z_]\w*")


def breaking_section() -> str:
    text = CHANGES.read_text(encoding="utf-8")
    match = re.search(r"^## Breaking\s*$(.*?)^## ", text, re.DOTALL | re.MULTILINE)
    assert match, "CHANGES.md has no '## Breaking' section"
    return match.group(1)


def identifier(entry: str) -> str | None:
    """The identifier an entry is matched on.

    It is the first dotted name (``Client.ws``, ``client.get_channel``) of the first code span
    of the entry, else the first word of that span. The guide must contain it.
    """
    for span in CODE.findall(entry):
        dotted = DOTTED.search(span)
        if dotted:
            return dotted.group(0)
        word = WORD.search(span)
        if word:
            return word.group(0)
    return None


def entries() -> list[tuple[str, str]]:
    """Return ``(heading, entry)`` for every table row and top-level bullet of Breaking."""
    result: list[tuple[str, str]] = []
    heading = ""
    for line in breaking_section().splitlines():
        if line.startswith("### "):
            heading = line[4:].strip()
        elif line.startswith("- "):
            result.append((heading, line[2:]))
        elif line.startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not cells[0] or set(cells[0]) <= {"-", " "} or cells[0] == "Old":
                continue
            result.append((heading, cells[0]))
    return result


def test_breaking_entries_exist() -> None:
    assert entries(), "no Breaking entry found, the parser is out of date"


def test_every_breaking_entry_is_in_the_guide() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    missing = []
    for heading, entry in entries():
        name = identifier(entry)
        if name is None or name not in guide:
            missing.append(f"{heading}: {name!r} ({entry[:60]})")
    assert not missing, (
        "docs/migrating_to_next.rst has no section for these Breaking entries of "
        "CHANGES.md (the first dotted code identifier of the entry must appear in the guide):\n"
        + "\n".join(missing)
    )


def test_every_breaking_category_has_a_section() -> None:
    guide = GUIDE.read_text(encoding="utf-8")
    for heading in {heading for heading, _ in entries()}:
        assert re.search(rf"^{re.escape(heading)}\n-+$", guide, re.MULTILINE), (
            f"docs/migrating_to_next.rst has no '{heading}' section"
        )
