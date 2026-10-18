import os

import discord

# Lobbies are managed with the bot token, see
# https://docs.discord.com/developers/resources/lobby
bot = discord.Bot()


@bot.slash_command(guild_ids=[...])
async def lobby(ctx: discord.ApplicationContext, member: discord.Member):
    """Create a lobby with you and another member."""
    created = await bot.create_lobby(
        metadata={"game": "chess"},
        members=[
            discord.LobbyMemberUpdate(ctx.author, additional_name="Host"),
            discord.LobbyMemberUpdate(member, additional_name="Guest"),
        ],
        idle_timeout_seconds=600,
    )
    await ctx.respond(
        f"Lobby {created.id} created with {len(created.members)} members."
    )


@bot.slash_command(guild_ids=[...])
async def close_lobby(ctx: discord.ApplicationContext, lobby_id: str):
    """Delete a lobby."""
    found = await bot.fetch_lobby(int(lobby_id))
    for lobby_member in found.members:
        # LobbyMember.user reads the cache, get_user() works with every backend.
        user = await lobby_member.get_user()
        print(user)
    await found.delete()
    await ctx.respond("The lobby was deleted.")


bot.run(os.environ["DISCORD_TOKEN"])
