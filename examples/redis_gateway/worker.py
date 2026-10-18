"""A bot reading its gateway events from Redis Streams instead of connecting to Discord.

One gateway proxy keeps the connection to Discord and forwards the raw events to
Redis, any number of workers like this one consume them and can be restarted or
scaled without reconnecting to Discord.

Install the extra first::

    pip install "py-cord[redis]"

Start the gateway proxy, it handles the shards 0 to 3 of 4 (use the same prefix
as the workers)::

    export DISCORD_TOKEN="your token"
    python -m discord gateway-proxy --redis-url redis://localhost:6379/0 \
        --prefix mybot --shard-ids 0-3 --shard-count 4 --intents 53575421

Start one or more workers, the workers of a consumer group share the events and
take over the events of a worker that crashed::

    export DISCORD_TOKEN="your token"
    python examples/redis_gateway/worker.py

Workers must share their cache, so the cache lives in the same Redis server.
"""

from __future__ import annotations

import os

from aiocache import RedisCache

import discord
from discord.gateway.brokers import RedisStreamsTransport

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_URL = f"redis://{REDIS_HOST}:6379/0"
SHARD_COUNT = 4

bot = discord.AutoShardedBot(
    intents=discord.Intents.default(),
    shard_count=SHARD_COUNT,
    gateway=RedisStreamsTransport.factory(
        url=REDIS_URL, prefix="mybot", group="workers"
    ),
    cache_backend=RedisCache(endpoint=REDIS_HOST),
    cache_namespace="mybot",
)


@bot.event
async def on_ready() -> None:
    print(f"{bot.user} is ready on {bot.shard_count} shards")


@bot.slash_command()
async def ping(ctx: discord.ApplicationContext) -> None:
    await ctx.respond(f"Pong! {bot.latency * 1000:.0f} ms to the gateway proxy")


@bot.slash_command()
async def status(ctx: discord.ApplicationContext, text: str) -> None:
    await bot.change_presence(activity=discord.Game(text))
    await ctx.respond("The proxy updated the presence.")


bot.run(os.environ["DISCORD_TOKEN"])
