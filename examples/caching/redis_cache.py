"""Keep the cache of the bot in Redis so that several processes can share it.

Install the extra first::

    pip install "py-cord[redis]"

With a remote backend the cache is not in the memory of the process anymore, so
the synchronous accessors (``guild.members``, ``client.guilds``...) cannot read
it and raise ``SyncCacheAccessError``. Every one of them has an awaitable twin
(``await guild.get_members()``, ``await client.get_guilds()``...) that works with
every backend, and the ``get_*`` lookups by ID are always awaited.
"""

import os

from aiocache import RedisCache

import discord

bot = discord.Bot(
    intents=discord.Intents.default() | discord.Intents(members=True),
    cache_backend=RedisCache(endpoint=os.environ.get("REDIS_HOST", "localhost")),
    # Bots sharing the same namespace share the same cache, use another one per bot.
    cache_namespace="mybot",
    # Also store the result of every fetch_* call (users, guilds, channels, ...).
    cache_fetch=True,
)


@bot.slash_command(guild_ids=[...])
async def members(ctx: discord.ApplicationContext):
    guild = await ctx.get_guild()
    if guild is None:
        await ctx.respond("This command only works in a server.")
        return

    try:
        # The synchronous property reads the in-process cache, which Redis is not.
        count = len(guild.members)
    except discord.SyncCacheAccessError as error:
        # The message names the awaitable twin to use instead.
        print(error)
        # The async twin works with every backend.
        count = len(await guild.get_members())

    await ctx.respond(f"{count} members are cached.")


@bot.slash_command(guild_ids=[...])
async def whois(ctx: discord.ApplicationContext, user_id: str):
    # Lookups by ID are awaited, they return None when the entity is not cached.
    user = await bot.get_user(int(user_id))
    if user is None:
        # With cache_fetch=True this also stores the user for the next lookup.
        user = await bot.fetch_user(int(user_id))
    await ctx.respond(
        f"{user} was created on {discord.utils.format_dt(user.created_at)}"
    )


@bot.slash_command(guild_ids=[...])
async def roles(ctx: discord.ApplicationContext):
    # ctx.guild never raises: with Redis it can be a partial handle built from
    # the ID, so use get_guild() to read the cached guild.
    guild = await ctx.get_guild()
    member = await guild.get_member(ctx.author.id) if guild else None
    # Member.top_role is the synchronous accessor, get_top_role() its twin.
    top_role = await member.get_top_role() if member else None
    await ctx.respond(f"Your top role is {top_role.mention if top_role else 'none'}.")


bot.run(os.environ["DISCORD_TOKEN"])
