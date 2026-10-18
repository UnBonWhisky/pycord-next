import datetime as dt

import discord

bot = discord.Bot(debug_guilds=[...])


@bot.slash_command()
async def timeout(
    ctx: discord.ApplicationContext, member: discord.Member, minutes: int
):
    """Apply a timeout to a member."""

    duration = dt.timedelta(minutes=minutes)
    await member.timeout_for(duration)
    await ctx.respond(f"Member timed out for {minutes} minutes.")

    """
    The method used above is a shortcut for:

    until = discord.utils.utcnow() + dt.timedelta(minutes=minutes)
    await member.timeout(until)
    """


bot.run("TOKEN")
