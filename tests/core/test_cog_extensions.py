# The MIT License (MIT)
#
# Copyright (c) 2015-2021 Rapptz
# Copyright (c) 2021-present Pycord Development
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

from __future__ import annotations

import sys
import textwrap
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import errors
from discord.cog import Cog, _is_submodule

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    before = set(sys.modules)
    yield tmp_path
    for name in set(sys.modules) - before:
        sys.modules.pop(name, None)


def write(root: Path, name: str, source: str) -> None:
    path = root.joinpath(*name.split(".")).with_suffix(".py")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source))


GOOD = """
    import discord

    class Thing(discord.Cog):
        @discord.Cog.listener()
        async def on_ping(self):
            pass

    def setup(bot):
        bot.add_cog(Thing())

    def teardown(bot):
        bot.torn_down = True
"""


def test_extension_lifecycle(workdir: Path) -> None:
    write(workdir, "pycord_ext_good", GOOD)
    bot = discord.Bot()

    assert bot.load_extension("pycord_ext_good") == ["pycord_ext_good"]
    assert list(bot.extensions) == ["pycord_ext_good"]
    assert list(bot.cogs) == ["Thing"]
    assert "on_ping" in bot._event_handlers

    with pytest.raises(errors.ExtensionAlreadyLoaded):
        bot.load_extension("pycord_ext_good")

    bot.reload_extension("pycord_ext_good")
    assert list(bot.cogs) == ["Thing"]
    assert bot.extensions["pycord_ext_good"] is sys.modules["pycord_ext_good"]

    bot.unload_extension("pycord_ext_good")
    assert bot.extensions == {}
    assert bot.cogs == {}
    assert bot.torn_down is True  # type: ignore[attr-defined]
    assert "pycord_ext_good" not in sys.modules
    assert bot._event_handlers.get("on_ping", []) == []

    with pytest.raises(errors.ExtensionNotLoaded):
        bot.unload_extension("pycord_ext_good")
    with pytest.raises(errors.ExtensionNotLoaded):
        bot.reload_extension("pycord_ext_good")


def test_extension_errors(workdir: Path) -> None:
    write(workdir, "pycord_ext_broken", "raise RuntimeError('boom')\n")
    write(workdir, "pycord_ext_nosetup", "x = 1\n")
    write(
        workdir,
        "pycord_ext_badsetup",
        """
        def setup(bot):
            raise ValueError("bad setup")

        def teardown(bot):
            bot.cleaned = True
        """,
    )
    bot = discord.Bot()

    with pytest.raises(errors.ExtensionNotFound):
        bot.load_extension("pycord_ext_missing")
    with pytest.raises(errors.ExtensionNotFound):
        bot.load_extension("..relative")
    with pytest.raises(errors.ExtensionFailed) as broken:
        bot.load_extension("pycord_ext_broken")
    assert isinstance(broken.value.original, RuntimeError)
    with pytest.raises(errors.NoEntryPointError):
        bot.load_extension("pycord_ext_nosetup")
    with pytest.raises(errors.ExtensionFailed) as bad:
        bot.load_extension("pycord_ext_badsetup")
    assert isinstance(bad.value.original, ValueError)
    assert bot.cleaned is True  # type: ignore[attr-defined]
    assert bot.extensions == {}


def test_load_extension_can_store_errors(workdir: Path) -> None:
    write(workdir, "pycord_ext_good", GOOD)
    write(workdir, "pycord_ext_broken", "raise RuntimeError('boom')\n")
    bot = discord.Bot()

    result = bot.load_extension("pycord_ext_good", store=True)
    assert result == {"pycord_ext_good": True}
    again = bot.load_extension("pycord_ext_good", store=True)
    assert isinstance(again["pycord_ext_good"], errors.ExtensionAlreadyLoaded)  # type: ignore[index]
    broken = bot.load_extension("pycord_ext_broken", store=True)
    assert isinstance(broken["pycord_ext_broken"], errors.ExtensionFailed)  # type: ignore[index]
    missing = bot.load_extension("pycord_ext_missing", store=True)
    assert isinstance(missing["pycord_ext_missing"], errors.ExtensionNotFound)  # type: ignore[index]


def test_relative_names_use_the_package(workdir: Path) -> None:
    write(workdir, "pycord_pkg.__init__", "")
    write(workdir, "pycord_pkg.sub", GOOD)
    bot = discord.Bot()
    assert bot.load_extension(".sub", package="pycord_pkg") == ["pycord_pkg.sub"]
    bot.unload_extension(".sub", package="pycord_pkg")


def test_loading_a_directory(workdir: Path) -> None:
    write(workdir, "pycord_cogs.alpha", GOOD.replace("Thing", "Alpha"))
    write(workdir, "pycord_cogs.nested.beta", GOOD.replace("Thing", "Beta"))
    write(workdir, "pycord_cogs._private", "raise RuntimeError('never loaded')\n")
    bot = discord.Bot()

    shallow = bot.load_extension("pycord_cogs")
    assert shallow == ["pycord_cogs.alpha"]
    assert sorted(bot.cogs) == ["Alpha"]

    deep = discord.Bot()
    assert sorted(deep.load_extension("pycord_cogs", recursive=True)) == [
        "pycord_cogs.alpha",
        "pycord_cogs.nested.beta",
    ]

    stored = discord.Bot()
    assert stored.load_extension("pycord_cogs", recursive=True, store=True) == {
        "pycord_cogs.alpha": True,
        "pycord_cogs.nested.beta": True,
    }


def test_load_extensions_collects_results(workdir: Path) -> None:
    write(workdir, "pycord_ext_one", GOOD.replace("Thing", "One"))
    write(workdir, "pycord_ext_two", GOOD.replace("Thing", "Two"))
    bot = discord.Bot()
    assert bot.load_extensions("pycord_ext_one", "pycord_ext_two") == [
        "pycord_ext_one",
        "pycord_ext_two",
    ]
    stored = discord.Bot()
    result = stored.load_extensions("pycord_ext_one", "pycord_ext_nope", store=True)
    assert result["pycord_ext_one"] is True  # type: ignore[index]
    assert isinstance(result["pycord_ext_nope"], errors.ExtensionNotFound)  # type: ignore[index]


def test_reload_restores_the_old_module_on_failure(workdir: Path) -> None:
    write(workdir, "pycord_ext_reload", GOOD)
    bot = discord.Bot()
    bot.load_extension("pycord_ext_reload")
    original = bot.extensions["pycord_ext_reload"]

    write(workdir, "pycord_ext_reload", "raise RuntimeError('broken update')\n")
    with pytest.raises(errors.ExtensionFailed):
        bot.reload_extension("pycord_ext_reload")
    assert bot.extensions["pycord_ext_reload"] is original
    assert list(bot.cogs) == ["Thing"]


def test_cog_registration_rules() -> None:
    bot = discord.Bot()

    class First(Cog):
        pass

    with pytest.raises(TypeError, match="derive from Cog"):
        bot.add_cog(object())  # type: ignore[arg-type]
    bot.add_cog(First())
    with pytest.raises(discord.ClientException, match="already loaded"):
        bot.add_cog(First())
    replacement = First()
    bot.add_cog(replacement, override=True)
    assert bot.cogs["First"] is replacement
    assert bot.remove_cog("Nothing") is None
    assert bot.remove_cog("First") is replacement
    assert bot.cogs == {}


def test_cog_metadata_and_listeners() -> None:
    class Described(Cog, name="Pretty", description="A cog"):
        @Cog.listener()
        async def on_ready(self) -> None: ...

        @Cog.listener("on_ping", once=True)
        async def renamed(self) -> None: ...

    cog = Described()
    assert Described.__cog_name__ == "Pretty"
    assert cog.qualified_name == "Pretty"
    assert cog.description == "A cog"
    cog.description = "Changed"
    assert cog.description == "Changed"
    assert sorted(name for name, _ in cog.get_listeners()) == ["on_ping", "on_ready"]
    assert cog.cog_check(None) is True  # type: ignore[arg-type]
    assert cog.bot_check(None) is True  # type: ignore[arg-type]
    assert cog.bot_check_once(None) is True  # type: ignore[arg-type]


def test_listener_validation() -> None:
    with pytest.raises(TypeError, match="expected str"):
        Cog.listener(5)  # type: ignore[arg-type]

    def not_a_coroutine() -> None: ...

    with pytest.raises(TypeError, match="coroutine function"):
        Cog.listener()(not_a_coroutine)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="must not start with cog_ or bot_"):

        class Bad(Cog):
            @Cog.listener()
            async def cog_something(self) -> None: ...


def test_cog_checks_are_installed_when_overridden() -> None:
    bot = discord.Bot()

    class Guarded(Cog):
        def bot_check(self, ctx: Any) -> bool:
            return False

        def bot_check_once(self, ctx: Any) -> bool:
            return False

    cog = Guarded()
    bot.add_cog(cog)
    assert cog.bot_check in bot._checks
    assert cog.bot_check_once in bot._check_once
    bot.remove_cog("Guarded")
    assert cog.bot_check not in bot._checks
    assert cog.bot_check_once not in bot._check_once


def test_cog_unload_errors_are_swallowed() -> None:
    bot = discord.Bot()
    calls: list[str] = []

    class Noisy(Cog):
        def cog_unload(self) -> None:
            calls.append("unload")
            raise RuntimeError("ignored")

    bot.add_cog(Noisy())
    bot.remove_cog("Noisy")
    assert calls == ["unload"]


def test_is_submodule() -> None:
    assert _is_submodule("a", "a")
    assert _is_submodule("a", "a.b.c")
    assert not _is_submodule("a", "ab")
    assert not _is_submodule("a.b", "a")
