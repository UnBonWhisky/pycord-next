import discord
from discord.ui import (
    ActionRow,
    Button,
    DesignerModal,
    DesignerView,
    InputText,
    MediaGallery,
    Section,
    TextDisplay,
    button,
)

bot = discord.Bot()


class FeedbackModal(DesignerModal):
    def __init__(self) -> None:
        super().__init__(title="Feedback", custom_id="feedback")
        self.add_text("Tell us what you think.")
        self.add_label(
            "Your feedback",
            InputText(custom_id="feedback_text", style=discord.InputTextStyle.long),
            description="Be as detailed as you like.",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        text = self.get_item("feedback_text").value
        await interaction.response.send_message(f"Thanks: {text}", ephemeral=True)


class Controls(ActionRow):
    @button(label="Add bread", custom_id="add_bread", id=20)
    async def add_bread(self, button: Button, interaction: discord.Interaction):
        self.view.add_item(TextDisplay("- bread"), after=3)
        await interaction.response.edit_message(view=self.view)

    @button(label="Replace eggs", custom_id="replace_eggs", id=21)
    async def replace_eggs(self, button: Button, interaction: discord.Interaction):
        self.view.replace_item(3, TextDisplay("- 12 eggs", id=3))
        await interaction.response.edit_message(view=self.view)

    @button(label="Feedback", custom_id="feedback", id=22)
    async def feedback(self, button: Button, interaction: discord.Interaction):
        await interaction.response.send_modal(FeedbackModal())


class EditableView(DesignerView):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.add_container(
            TextDisplay("**Shopping list**", id=1),
            TextDisplay("- milk", id=2),
            TextDisplay("- eggs", id=3),
            id=10,
        )
        self.add_item(Controls(id=11))


@bot.command()
async def shopping(ctx: discord.ApplicationContext) -> None:
    """Edit a view after it was sent: insert, replace and look up items."""

    view = EditableView()
    # Items can be inserted at a position or into another item
    view.add_item(TextDisplay("-# Edited live"), into=10, index=0)
    # Lookups accept ids, custom ids and any attribute
    assert view.get_item(label="Add bread") is view.get_item("add_bread")
    # The 40 component limit also counts the nested items
    print(f"{len(view)} of {discord.ComponentLimits.VIEW_CHILDREN_MAX} components used")

    await ctx.respond(view=view)


@bot.command()
async def gallery(ctx: discord.ApplicationContext) -> None:
    """Build a gallery from the avatar of the author and send it back as files."""

    media = MediaGallery.from_assets(ctx.author.display_avatar, new=True)
    files = await media.to_files()
    view = DesignerView(
        Section(
            TextDisplay("Your avatar"),
            accessory=Button(label="Open", url=ctx.author.display_avatar.url),
        ),
        media,
    )
    await ctx.respond(view=view, files=files)


bot.run("TOKEN")
