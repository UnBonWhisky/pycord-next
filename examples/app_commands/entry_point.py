# This example requires an application with Activities enabled.

import discord

bot = discord.Bot()


# Entry point commands are always global commands.
# With EntryPointHandler.discord_launch_activity, Discord launches the Activity
# itself and the callback is never called.
@bot.entry_point_command(
    name="launch",
    description="Launch the Activity",
    handler=discord.EntryPointHandler.app_handler,
)
async def launch(ctx: discord.ApplicationContext):
    # With the app handler the bot answers the interaction itself.
    # Launching the Activity is one of the possible answers.
    await ctx.interaction.response.launch_activity()


bot.run("TOKEN")
