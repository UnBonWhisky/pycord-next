# Several cogs can add commands to the same slash command group.
# The group is sent to Discord once, with the commands of every loaded cog,
# and unloading a cog only removes the commands that cog declared.

import discord
from discord.ext import commands

bot = discord.Bot(debug_guilds=[...], owner_id=...)  # Main file

admin = discord.SlashCommandGroup("admin", "Admin commands")  # Shared module


class Moderation(commands.Cog):
    @admin.command()  # `self` is the Moderation cog
    async def ban(self, ctx: discord.ApplicationContext, member: discord.Member):
        await ctx.respond(f"{member.mention} would be banned by {self.qualified_name}")


class Settings(commands.Cog):
    config = admin.create_subgroup("config", "Bot configuration")  # /admin config

    @config.command()  # `self` is the Settings cog
    async def prefix(self, ctx: discord.ApplicationContext, value: str):
        await ctx.respond(f"The prefix is now {value}")


class Owner(commands.Cog):
    # A cog can also own the group. Its cog_check runs for every /admin command
    # and its cog_command_error receives the errors of the other cogs' commands.
    owned_admin = admin

    async def cog_check(self, ctx: discord.ApplicationContext) -> bool:
        return await ctx.bot.is_owner(ctx.author)

    async def cog_command_error(
        self, ctx: discord.ApplicationContext, error: discord.DiscordException
    ):
        if isinstance(error, discord.CheckFailure):
            await ctx.respond("Only the owner can use /admin.", ephemeral=True)

    @owned_admin.command()
    async def shutdown(self, ctx: discord.ApplicationContext):
        await ctx.respond("Shutting down...")
        await ctx.bot.close()


bot.add_cog(Moderation())  # Put in a setup function for cog files
bot.add_cog(Settings())
bot.add_cog(Owner())

# bot.remove_cog("Settings") removes /admin config prefix only.
# Loading or unloading a cog while the bot is running syncs the group again
# when auto_sync_commands is enabled.

bot.run("TOKEN")  # Main file
