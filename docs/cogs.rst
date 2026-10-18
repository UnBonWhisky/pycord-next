:orphan:

.. currentmodule:: discord
.. _cogs:

Cogs
====

There comes a point in your bot's development when you want to organize a collection of commands, listeners, and some state into one class. Cogs allow you to do just that.

The gist:

- Each cog is a Python class that subclasses :class:`.Cog`.
- Every command is marked with the :func:`discord.command` decorator or the corresponding shortcut command decorator.
- Every listener is marked with the :meth:`.Cog.listener` decorator.
- Cogs are then registered with the :meth:`.Bot.add_cog` call.
- Cogs are subsequently removed with the :meth:`.Bot.remove_cog` call.

Quick Example
-------------

This example cog defines a ``Greetings`` category for your commands, with a single slash command named ``hello`` as well as a listener to listen to an :ref:`Event <discord-api-events>`.

.. code-block:: python3

    class Greetings(discord.Cog):
        def __init__(self, bot):
            self.bot = bot
            self._last_member = None

        @discord.Cog.listener()
        async def on_member_join(self, member):
            channel = member.guild.system_channel
            if channel is not None:
                await channel.send(f'Welcome {member.mention}.')

        @discord.slash_command()
        async def hello(self, ctx, *, member: discord.Member = None):
            """Says hello"""
            member = member or ctx.author
            if self._last_member is None or self._last_member.id != member.id:
                await ctx.send(f'Hello {member.name}~')
            else:
                await ctx.send(f'Hello {member.name}... This feels familiar.')
            self._last_member = member

A couple of technical notes to take into consideration:

- All listeners must be explicitly marked via decorator, :meth:`~.Cog.listener`.
- The name of the cog is automatically derived from the class name but can be overridden.
- All commands must now take a ``self`` parameter to allow usage of instance attributes that can be used to maintain state.

Cog Registration
----------------

Once you have defined your cogs, you need to tell the bot to register the cogs to be used. We do this via the :meth:`~.Bot.add_cog` method.

.. code-block:: python3

    bot.add_cog(Greetings(bot))

This binds the cog to the bot, adding all commands and listeners to the bot automatically.

Using Cogs
----------

Just as we remove a cog by its name, we can also retrieve it by its name as well. This allows us to use a cog as an inter-command communication protocol to share data. For example:

.. code-block:: python3
    :emphasize-lines: 22,24

    class Economy(discord.Cog):
        ...

        async def withdraw_money(self, member, money):
            # implementation here
            ...

        async def deposit_money(self, member, money):
            # implementation here
            ...

    class Gambling(discord.Cog):
        def __init__(self, bot):
            self.bot = bot

        def coinflip(self):
            return random.randint(0, 1)

        @discord.slash_command()
        async def gamble(self, ctx, money: int):
            """Gambles some money."""
            economy = self.bot.get_cog('Economy')
            if economy is not None:
                await economy.withdraw_money(ctx.author, money)
                if self.coinflip() == 1:
                    await economy.deposit_money(ctx.author, money * 1.5)

Slash command groups across cogs
--------------------------------

Several cogs can add commands to the same :class:`SlashCommandGroup`. Create the group once, in a module
the cogs share, and use its decorators in each cog. The bot keeps one canonical group for a name and a set of
guilds (two groups with the same name and guilds are merged) and sends a single payload to Discord.

.. code-block:: python3

    admin = discord.SlashCommandGroup("admin", "Admin commands")

    class Moderation(discord.Cog):
        @admin.command()                        # /admin ban, `self` is the Moderation cog
        async def ban(self, ctx, member: discord.Member): ...

    class Settings(discord.Cog):
        config = admin.create_subgroup("config")   # /admin config, owned by Settings

        @config.command()                       # /admin config prefix
        async def prefix(self, ctx, value: str): ...

- Each subcommand is bound to the cog that declares it, so ``self`` is that cog and its ``cog_before_invoke``,
  ``cog_after_invoke`` and ``cog_command_error`` apply to it.
- Cogs load and unload in any order. Unloading a cog removes only the commands it declared, and the group is
  unregistered when nothing is left in it. A duplicate subcommand name raises :exc:`ClientException` naming
  both cogs.
- Loading or unloading a cog on a ready bot syncs the commands once, when ``auto_sync_commands`` is enabled.
- :class:`discord.ext.bridge.BridgeCommandGroup` works the same way.

A cog can also **own** the group by keeping it as a class attribute (``owned_admin = admin``). Its ``cog_check``,
hooks and error handler then apply to every command of the group, in this order for a subcommand:

1. the ``cog_check`` of the cog that owns the group;
2. the group checks, then the subgroup checks;
3. the ``cog_check`` of the cog that owns the subcommand, then the checks of the subcommand.

For hooks, the owner's ``cog_before_invoke`` runs first, then the one of the subcommand's cog, the command,
the subcommand cog's ``cog_after_invoke`` and the owner's ``cog_after_invoke`` last. A cog that owns both the
group and the command runs its hooks once. Errors go to the ``cog_command_error`` of the subcommand's cog
first, then to the owner's if they were not handled.

See ``examples/app_commands/slash_multi_cog_groups.py`` for a complete example and
``examples/app_commands/slash_cog_groups.py`` for a group inside a single cog.
