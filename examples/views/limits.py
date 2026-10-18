import os

import discord

# ComponentLimits holds the limits of Discord for every component, so you do not
# have to hardcode them: the library validates with the same constants.
limits = discord.ComponentLimits

bot = discord.Bot()


class PickView(discord.ui.View):
    def __init__(self, options: list[str]):
        super().__init__(timeout=60)
        # A select menu holds at most SELECT_OPTIONS_MAX options.
        options = options[: limits.SELECT_OPTIONS_MAX]
        self.add_item(
            discord.ui.Select(
                placeholder="Pick a value"[: limits.SELECT_PLACEHOLDER_MAX],
                options=[
                    discord.SelectOption(
                        label=name[: limits.SELECT_OPTION_LABEL_MAX],
                        value=name[: limits.SELECT_OPTION_VALUE_MAX],
                    )
                    for name in options
                ],
            )
        )


@bot.slash_command(guild_ids=[...])
async def pick(ctx: discord.ApplicationContext):
    names = [f"Option {i}" for i in range(100)]
    await ctx.respond(
        f"Showing {limits.SELECT_OPTIONS_MAX} of {len(names)} options.",
        view=PickView(names),
    )


@bot.slash_command(guild_ids=[...])
async def embed(ctx: discord.ApplicationContext, text: str):
    # EmbedLimits documents the limits of an embed, Discord rejects what exceeds them.
    description = text[: discord.EmbedLimits.DESCRIPTION_MAX]
    await ctx.respond(embed=discord.Embed(description=description))


bot.run(os.environ["DISCORD_TOKEN"])
