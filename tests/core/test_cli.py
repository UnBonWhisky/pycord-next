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

import argparse
import ast
import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

import discord
from discord import __main__ as cli


def run(monkeypatch: pytest.MonkeyPatch, *argv: str) -> None:
    monkeypatch.setattr(sys, "argv", ["discord", *argv])
    cli.main()


def test_version_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run(monkeypatch, "--version")
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("- Python v")
    assert any(line.startswith("- py-cord v") for line in lines)
    assert any(line.startswith("- aiohttp v") for line in lines)
    assert lines[-1].startswith("- system info: ")


def test_version_mentions_the_installed_metadata_for_prereleases(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    info = discord.version_info._replace(releaselevel="alpha")
    monkeypatch.setattr(discord, "version_info", info)
    monkeypatch.setattr(cli.importlib.metadata, "version", lambda _name: "9.9.9")
    cli.show_version()
    assert "importlib.metadata: v9.9.9" in capsys.readouterr().out


def test_running_without_arguments_prints_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run(monkeypatch)
    assert capsys.readouterr().out == ""


def parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(prog="discord")


def test_to_path_sanitises_names() -> None:
    p = parser()
    assert cli.to_path(p, "a<b>c") == Path("a-b-c")
    assert cli.to_path(p, "name?*|") == Path("name---")
    assert cli.to_path(p, "with\x01control") == Path("withcontrol")
    assert cli.to_path(p, "has space", replace_spaces=True) == Path("has-space")
    assert cli.to_path(p, "has space") == Path("has space")
    existing = Path("kept?")
    assert cli.to_path(p, existing) is existing


def test_to_path_rejects_reserved_windows_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.sys, "platform", "win32")
    p = parser()
    with pytest.raises(SystemExit):
        cli.to_path(p, "con")
    with pytest.raises(SystemExit):
        cli.to_path(p, "LPT3")
    assert cli.to_path(p, "console") == Path("console")


def test_to_path_keeps_the_windows_drive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.sys, "platform", "win32")
    p = parser()
    assert cli.to_path(p, "C:\\bots\\my:bot") == Path("C:\\bots\\my-bot")
    assert cli.to_path(p, "relative:name") == Path("relative-name")


def test_newbot_creates_the_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(monkeypatch, "newbot", "mybot", str(tmp_path), "--prefix", "!")

    root = tmp_path / "mybot"
    assert (root / "cogs" / "__init__.py").exists()
    assert (root / "config.py").read_text(
        encoding="utf-8"
    ) == 'token = "place your token here"\ncogs = []\n'
    bot = (root / "bot.py").read_text(encoding="utf-8")
    assert "class Bot(commands.Bot)" in bot
    assert "when_mentioned_or('!')" in bot
    ast.parse(bot)
    assert "config.py" in (root / ".gitignore").read_text(encoding="utf-8")
    assert f"successfully made bot at {root}" in capsys.readouterr().out


def test_newbot_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run(monkeypatch, "newbot", "sharded", str(tmp_path), "--sharded", "--no-git")
    root = tmp_path / "sharded"
    assert "commands.AutoShardedBot" in (root / "bot.py").read_text(encoding="utf-8")
    assert not (root / ".gitignore").exists()


def test_newbot_reports_filesystem_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    with pytest.raises(SystemExit):
        run(monkeypatch, "newbot", "bot", str(blocker))
    assert "could not create our bot directory" in capsys.readouterr().err

    original = Path.mkdir

    def fail_cogs(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.name == "cogs":
            raise OSError("no cogs")
        original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_cogs)
    run(monkeypatch, "newbot", "nocogs", str(tmp_path))
    assert "warning: could not create cogs directory" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("failing", "message"),
    [
        ("config.py", "could not create config file"),
        ("bot.py", "could not create bot file"),
    ],
)
def test_newbot_reports_write_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failing: str,
    message: str,
) -> None:
    original = Path.open

    def fail(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.name == failing:
            raise OSError("denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    with pytest.raises(SystemExit):
        run(monkeypatch, "newbot", "bot", str(tmp_path))
    assert message in capsys.readouterr().err


def test_newbot_warns_when_the_gitignore_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = Path.open

    def fail(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.name == ".gitignore":
            raise OSError("denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail)
    run(monkeypatch, "newbot", "bot", str(tmp_path))
    assert "warning: could not create .gitignore file" in capsys.readouterr().out


def test_newbot_warns_when_the_cogs_package_cannot_be_created(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = Path.touch

    def fail(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.name == "__init__.py":
            raise OSError("denied")
        original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "touch", fail)
    run(monkeypatch, "newbot", "bot", str(tmp_path))
    assert "warning: could not create cogs directory" in capsys.readouterr().out


def test_newcog_creates_a_cog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run(monkeypatch, "newcog", "my_cool-cog", str(tmp_path / "cogs"))

    path = tmp_path / "cogs" / "my_cool-cog.py"
    source = path.read_text(encoding="utf-8")
    ast.parse(source)
    assert "class MyCoolCog(commands.Cog)" in source
    assert "def cog_unload" not in source
    assert f"successfully made cog at {path}" in capsys.readouterr().out


def test_newcog_options(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    run(
        monkeypatch,
        "newcog",
        "Plain",
        str(tmp_path),
        "--class-name",
        "Custom",
        "--display-name",
        "Pretty",
        "--hide-commands",
        "--full",
    )
    source = (tmp_path / "Plain.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert (
        'class Custom(commands.Cog, name="Pretty", command_attrs=dict(hidden=True))'
        in source
    )
    assert "def cog_unload" in source
    assert "async def cog_after_invoke" in source

    run(monkeypatch, "newcog", "single", str(tmp_path))
    assert "class Single(commands.Cog)" in (tmp_path / "single.py").read_text(
        encoding="utf-8"
    )


def test_newcog_reports_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("x")
    with pytest.raises(SystemExit):
        run(monkeypatch, "newcog", "cog", str(blocker / "sub"))
    assert "could not create cog file" in capsys.readouterr().err

    def fail(self: Path, *args: Any, **kwargs: Any) -> None:
        raise OSError("denied")

    monkeypatch.setattr(Path, "mkdir", fail)
    run(monkeypatch, "newcog", "cog", str(tmp_path))
    assert "warning: could not create cogs directory" in capsys.readouterr().out


def test_gateway_proxy_exits_on_library_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    proxy_module = importlib.import_module("discord.gateway.proxy")

    class Failing:
        def __init__(self, token: str, **options: Any) -> None: ...

        async def run(self) -> None:
            raise discord.DiscordException("login failed")

    monkeypatch.setattr(proxy_module, "GatewayProxy", Failing)
    with pytest.raises(SystemExit) as info:
        run(monkeypatch, "gateway-proxy", "--token", "abc")
    assert info.value.code == 1
    assert "error: login failed" in capsys.readouterr().err


def test_gateway_proxy_ignores_keyboard_interrupts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proxy_module = importlib.import_module("discord.gateway.proxy")

    class Interrupted:
        def __init__(self, token: str, **options: Any) -> None: ...

        async def run(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(proxy_module, "GatewayProxy", Interrupted)
    run(monkeypatch, "gateway-proxy", "--token", "abc")
