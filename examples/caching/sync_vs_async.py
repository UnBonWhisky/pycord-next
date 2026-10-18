"""The default in-process cache keeps the synchronous API of pycord.

Properties like ``guild.members`` or ``client.guilds`` read the cache without any
I/O, so they stay synchronous. Lookups by ID, and the generators walking the
whole cache, are awaited so the code does not change when the bot switches to
another cache backend (see ``redis_cache.py``).
"""

import os

import discord

intents = discord.Intents.default()
intents.members = True

bot = discord.Bot(intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # A property: synchronous with the default cache.
    print(f"{len(bot.guilds)} guilds")
    # Its awaitable twin: the same list, works with every backend.
    print(f"{len(await bot.get_guilds())} guilds")

    # Lookups by ID are awaited and return None when the entity is not cached.
    guild = await bot.get_guild(1234567)  # Your guild ID goes here
    if guild is None:
        return

    # Same members, once with the property and once with the twin.
    print(len(guild.members), len(await guild.get_members()))

    # Stream the members instead of building the whole list.
    async for member in guild.iter_members():
        print(member)

    # Walking the whole cache is an async generator.
    async for channel in bot.get_all_channels():
        print(channel)

    owner = await guild.get_member(guild.owner_id)
    if owner is not None:
        # Both forms of the same value.
        print(owner.top_role, await owner.get_top_role())


bot.run(os.environ["DISCORD_TOKEN"])
