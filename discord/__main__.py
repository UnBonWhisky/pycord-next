"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz
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

import argparse
import asyncio
import contextlib
import importlib
import importlib.metadata
import logging
import ntpath
import os
import platform
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp

import discord

if TYPE_CHECKING:
    _SubParsers = argparse._SubParsersAction[argparse.ArgumentParser]


def show_version() -> None:
    """Print the versions of Python, the library and its main dependency."""
    entries = [
        f"- Python v{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}-{sys.version_info.releaselevel}"
    ]

    version_info = discord.version_info
    entries.append(
        f"- py-cord v{version_info.major}.{version_info.minor}.{version_info.micro}-{version_info.releaselevel}"
    )
    if version_info.releaselevel != "final":
        version = importlib.metadata.version("py-cord")
        if version:
            entries.append(f"    - py-cord importlib.metadata: v{version}")

    entries.append(f"- aiohttp v{aiohttp.__version__}")
    uname = platform.uname()
    entries.append(f"- system info: {uname.system} {uname.release} {uname.version}")
    print("\n".join(entries))


def core(_parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Handle the top-level command (``--version``)."""
    if args.version:
        show_version()


_bot_template = """#!/usr/bin/env python3

from discord.ext import commands
import discord
import config

class Bot(commands.{base}):
    def __init__(self, **kwargs):
        super().__init__(command_prefix=commands.when_mentioned_or('{prefix}'), **kwargs)
        for cog in config.cogs:
            try:
                self.load_extension(cog)
            except Exception as exc:
                print(f'Could not load extension {{cog}} due to {{exc.__class__.__name__}}: {{exc}}')

    async def on_ready(self):
        print(f'Logged on as {{self.user}} (ID: {{self.user.id}})')


bot = Bot()

# write general commands here

bot.run(config.token)
"""

_gitignore_template = """# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
env/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
*.egg-info/
.installed.cfg
*.egg

# Our configuration files
config.py
"""

_cog_template = '''from discord.ext import commands
import discord

class {name}(commands.Cog{attrs}):
    """The description for {name} goes here."""

    def __init__(self, bot):
        self.bot = bot
{extra}
def setup(bot):
    bot.add_cog({name}(bot))
'''

_cog_extras = """
    def cog_unload(self):
        # clean up logic goes here
        pass

    async def cog_check(self, ctx):
        # checks that apply to every command in here
        return True

    async def bot_check(self, ctx):
        # checks that apply to every command to the bot
        return True

    async def bot_check_once(self, ctx):
        # check that apply to every command but is guaranteed to be called only once
        return True

    async def cog_command_error(self, ctx, error):
        # error handling to every command in here
        pass

    async def cog_before_invoke(self, ctx):
        # called before a command is called here
        pass

    async def cog_after_invoke(self, ctx):
        # called after a command is called here
        pass

"""


# certain file names and directory names are forbidden
# see: https://msdn.microsoft.com/en-us/library/windows/desktop/aa365247%28v=vs.85%29.aspx
# although some of this doesn't apply to Linux, we might as well be consistent
_base_table: dict[str, str | None] = {
    "<": "-",
    ">": "-",
    ":": "-",
    '"': "-",
    # '/': '-', these are fine
    # '\\': '-',
    "|": "-",
    "?": "-",
    "*": "-",
}

# NUL (0) and 1-31 are disallowed
_base_table.update((chr(i), None) for i in range(32))

_translation_table = str.maketrans(_base_table)


def to_path(
    parser: argparse.ArgumentParser,
    name: str | Path,
    *,
    replace_spaces: bool = False,
) -> Path:
    """Convert a user given name to a safe :class:`~pathlib.Path`."""
    if isinstance(name, Path):
        return name

    if sys.platform == "win32":
        forbidden = (
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        )
        if len(name) <= 4 and name.upper() in forbidden:
            parser.error("invalid directory name given, use a different one")
        drive, name = ntpath.splitdrive(name)
    else:
        drive = ""

    name = drive + name.translate(_translation_table)
    if replace_spaces:
        name = name.replace(" ", "-")
    return Path(name)


def newbot(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Create a new bot project."""
    new_directory = to_path(parser, args.directory) / to_path(parser, args.name)

    # as a note exist_ok for Path is a 3.5+ only feature
    # since we already checked above that we're >3.5
    try:
        new_directory.mkdir(exist_ok=True, parents=True)
    except OSError as exc:
        parser.error(f"could not create our bot directory ({exc})")

    cogs = new_directory / "cogs"

    try:
        cogs.mkdir(exist_ok=True)
        init = cogs / "__init__.py"
        init.touch()
    except OSError as exc:
        print(f"warning: could not create cogs directory ({exc})")

    try:
        with (new_directory / "config.py").open("w", encoding="utf-8") as fp:
            fp.write('token = "place your token here"\ncogs = []\n')
    except OSError as exc:
        parser.error(f"could not create config file ({exc})")

    try:
        with (new_directory / "bot.py").open("w", encoding="utf-8") as fp:
            base = "Bot" if not args.sharded else "AutoShardedBot"
            fp.write(_bot_template.format(base=base, prefix=args.prefix))
    except OSError as exc:
        parser.error(f"could not create bot file ({exc})")

    if not args.no_git:
        try:
            with (new_directory / ".gitignore").open("w", encoding="utf-8") as fp:
                fp.write(_gitignore_template)
        except OSError as exc:
            print(f"warning: could not create .gitignore file ({exc})")

    print("successfully made bot at", new_directory)


def newcog(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Create a new cog file."""
    cog_dir = to_path(parser, args.directory)
    try:
        cog_dir.mkdir(exist_ok=True)
    except OSError as exc:
        print(f"warning: could not create cogs directory ({exc})")

    directory = cog_dir / to_path(parser, args.name)
    directory = directory.with_suffix(".py")
    try:
        with directory.open("w", encoding="utf-8") as fp:
            attrs = ""
            extra = _cog_extras if args.full else ""
            if args.class_name:
                name = args.class_name
            else:
                name = str(directory.stem)
                if "-" in name or "_" in name:
                    translation = str.maketrans("-_", "  ")
                    name = name.translate(translation).title().replace(" ", "")
                else:
                    name = name.title()

            if args.display_name:
                attrs += f', name="{args.display_name}"'
            if args.hide_commands:
                attrs += ", command_attrs=dict(hidden=True)"
            fp.write(_cog_template.format(name=name, extra=extra, attrs=attrs))
    except OSError as exc:
        parser.error(f"could not create cog file ({exc})")
    else:
        print("successfully made cog at", directory)


def add_newbot_args(subparser: _SubParsers) -> None:
    """Register the ``newbot`` sub-command."""
    parser = subparser.add_parser(
        "newbot", help="creates a command bot project quickly"
    )
    parser.set_defaults(func=newbot)

    parser.add_argument("name", help="the bot project name")
    parser.add_argument(
        "directory",
        help="the directory to place it in (default: .)",
        nargs="?",
        default=Path.cwd(),
    )
    parser.add_argument(
        "--prefix", help="the bot prefix (default: $)", default="$", metavar="<prefix>"
    )
    parser.add_argument(
        "--sharded", help="whether to use AutoShardedBot", action="store_true"
    )
    parser.add_argument(
        "--no-git",
        help="do not create a .gitignore file",
        action="store_true",
        dest="no_git",
    )


def add_newcog_args(subparser: _SubParsers) -> None:
    """Register the ``newcog`` sub-command."""
    parser = subparser.add_parser("newcog", help="creates a new cog template quickly")
    parser.set_defaults(func=newcog)

    parser.add_argument("name", help="the cog name")
    parser.add_argument(
        "directory",
        help="the directory to place it in (default: cogs)",
        nargs="?",
        default=Path("cogs"),
    )
    parser.add_argument(
        "--class-name",
        help="the class name of the cog (default: <name>)",
        dest="class_name",
    )
    parser.add_argument("--display-name", help="the cog name (default: <name>)")
    parser.add_argument(
        "--hide-commands",
        help="whether to hide all commands in the cog",
        action="store_true",
    )
    parser.add_argument(
        "--full", help="add all special methods as well", action="store_true"
    )


def parse_shard_ids(value: str) -> list[int]:
    """Parse a shard ID list such as ``0-7,9`` into a list of unique IDs."""
    shard_ids: list[int] = []
    for part in value.split(","):
        bounds = part.strip().split("-")
        try:
            numbers = [int(bound) for bound in bounds]
        except ValueError:
            numbers = []
        if not 1 <= len(numbers) <= 2 or any(number < 0 for number in numbers):
            raise argparse.ArgumentTypeError(
                f"invalid shard IDs {value!r}, expected a list like '0-7,9'"
            )
        first, last = numbers[0], numbers[-1]
        if first > last:
            raise argparse.ArgumentTypeError(
                f"invalid shard range {part.strip()!r}, the first shard is after the last"
            )
        shard_ids.extend(range(first, last + 1))
    return list(dict.fromkeys(shard_ids))


def gateway_proxy(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Run the gateway proxy."""
    try:
        brokers = importlib.import_module("discord.gateway.brokers")
        proxy_module = importlib.import_module("discord.gateway.proxy")
    except ImportError as exc:
        parser.exit(1, f"error: {exc}\n")

    if not args.token:
        parser.error("a token is required, use --token or DISCORD_TOKEN")
    if args.shard_ids is not None:
        if args.shard_count is None:
            parser.error("--shard-ids needs --shard-count")
        if max(args.shard_ids) >= args.shard_count:
            parser.error("--shard-ids must be lower than --shard-count")
    if args.shard_count is not None and args.shard_count < 1:
        parser.error("--shard-count must be at least 1")

    try:
        config = brokers.RedisStreamsConfig(
            url=args.redis_url, prefix=args.prefix, maxlen=args.maxlen
        )
    except ValueError as exc:
        parser.error(str(exc))

    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    proxy = proxy_module.GatewayProxy(
        args.token,
        config=config,
        intents=discord.Intents._from_value(args.intents),
        shard_ids=args.shard_ids,
        shard_count=args.shard_count,
        compression=None if args.compression == "none" else args.compression,
    )
    with contextlib.suppress(KeyboardInterrupt):
        try:
            asyncio.run(proxy.run())
        except discord.DiscordException as exc:
            parser.exit(1, f"error: {exc}\n")


def add_gateway_proxy_args(subparser: _SubParsers) -> None:
    """Register the ``gateway-proxy`` sub-command."""
    parser = subparser.add_parser(
        "gateway-proxy",
        help="runs a gateway proxy forwarding the events to Redis Streams",
    )
    parser.set_defaults(func=gateway_proxy)
    parser.add_argument(
        "--token",
        default=os.environ.get("DISCORD_TOKEN"),
        help="the bot token (default: the DISCORD_TOKEN environment variable)",
    )
    parser.add_argument(
        "--redis-url",
        default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        help="the Redis URL (default: REDIS_URL or redis://localhost:6379/0)",
    )
    parser.add_argument(
        "--prefix",
        default="pycord",
        help="the prefix of the Redis keys, shared with the workers (default: pycord)",
    )
    parser.add_argument(
        "--shard-ids",
        type=parse_shard_ids,
        help="the shards to run, such as '0-7,9' (default: all, otherwise needs --shard-count)",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        help="the total number of shards (default: the one Discord recommends)",
    )
    parser.add_argument(
        "--intents",
        type=int,
        default=discord.Intents.default().value,
        help="the intents as an integer (default: the non privileged intents)",
    )
    parser.add_argument(
        "--compression",
        choices=["zlib-stream", "zstd-stream", "none"],
        default="zlib-stream",
        help="the transport compression of the gateway (default: zlib-stream)",
    )
    parser.add_argument(
        "--maxlen",
        type=int,
        default=10000,
        help="the approximate number of events kept per shard (default: 10000)",
    )
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="the logging level (default: INFO)",
    )


def parse_args() -> tuple[argparse.ArgumentParser, argparse.Namespace]:
    """Build the argument parser and parse the command line."""
    parser = argparse.ArgumentParser(
        prog="discord", description="Tools for helping with Pycord"
    )
    parser.add_argument(
        "-v", "--version", action="store_true", help="shows the library version"
    )
    parser.set_defaults(func=core)

    subparser = parser.add_subparsers(dest="subcommand", title="subcommands")
    add_newbot_args(subparser)
    add_newcog_args(subparser)
    add_gateway_proxy_args(subparser)
    return parser, parser.parse_args()


def main() -> None:
    """Run the command line interface."""
    parser, args = parse_args()
    args.func(parser, args)


if __name__ == "__main__":
    main()
