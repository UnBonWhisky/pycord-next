.. currentmodule:: discord

.. _migrating_to_next:

Migrating from Pycord to Pycord Next
====================================

Pycord Next keeps the API of pycord. A bot that runs on pycord needs few changes: this page lists every
breaking change, with the code before and after. Everything else (new features, fixes) is in
:doc:`changes`, which is the source of this page; the test ``tests/docs/test_migration_guide_sync.py``
fails when a breaking entry of ``CHANGES.md`` has no section here.

The rule behind every breaking change is the same: it exists to prevent a later break. The cache can
live in Redis and the gateway can come from a broker, so what may do I/O is awaited.

What did not change
-------------------

With the default in-process cache, the **synchronous accessors of pycord stay synchronous**:
``client.guilds``, ``guild.members``, ``guild.channels``, ``guild.roles``, ``guild.me``, ``member.roles``,
``member.top_role``, ``member.guild_permissions``, ``channel.permissions_for()``, ``message.channel``,
``message.guild``... keep their name, their behaviour and their type. Each one has an awaitable twin
(``await guild.get_members()``) for the remote cache backends, see :doc:`caching`. Without any option
the bot connects to Discord as before, see :doc:`gateway`.

If you only run in one process on the default cache, the sections below are all you have to do.

.. _migrating_next_caching:

Caching
-------

.. _migrating_next_client_lookups:

``client.get_channel(id)`` and the other lookups by ID
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``Client.get_channel``, ``get_message``, ``get_stage_instance``, ``get_guild``, ``get_user``,
``get_emoji``, ``get_sticker``, ``get_poll`` and ``get_sound`` are coroutines. Why: they read the cache one
entity at a time, which is I/O on a remote backend.

.. code-block:: python3

    # pycord
    guild = client.get_guild(1234567)
    channel = client.get_channel(7654321)

    # pycord-next
    guild = await client.get_guild(1234567)
    channel = await client.get_channel(7654321)

.. _migrating_next_client_generators:

``client.get_all_channels()`` and ``client.get_all_members()``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The two generators are asynchronous generators, as they walk the whole cache.

.. code-block:: python3

    # pycord
    for member in client.get_all_members():
        ...

    # pycord-next
    async for member in client.get_all_members():
        ...

.. _migrating_next_client_clear:

``client.clear()``
~~~~~~~~~~~~~~~~~~

The backend may need I/O to be emptied.

.. code-block:: python3

    # pycord
    client.clear()

    # pycord-next
    await client.clear()

.. _migrating_next_guild_lookups:

``guild.get_channel(id)`` and the other lookups of a guild
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``Guild.get_channel``, ``get_thread``, ``get_channel_or_thread``, ``get_member``, ``get_member_named``,
``get_role``, ``get_emoji``, ``get_stage_instance``, ``get_scheduled_event`` and ``get_sound`` are
coroutines (``await guild.get_sticker(id)`` is new). The properties and the other methods of
:class:`Guild` (``channels``, ``members``, ``roles``, ``me``, ``owner``, ``chunked``, ``by_category()``...) are unchanged.

.. code-block:: python3

    # pycord
    role = guild.get_role(role_id)
    member = guild.get_member(user_id)

    # pycord-next
    role = await guild.get_role(role_id)
    member = await guild.get_member(user_id)

.. _migrating_next_get_star:

The ``get_*`` lookups and generators
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In short: every ``get_*`` that looks an entity up by ID, and every generator or coroutine that walks or
empties the cache (``get_all_channels()``, ``get_all_members()``, ``clear()``), is awaited. Everything else
that reads the cache keeps its form. A synchronous lookup left as it was returns a coroutine, which
Python reports as ``RuntimeWarning: coroutine ... was never awaited``; search your code for ``.get_``.

.. _migrating_next_state_internals:

``ConnectionState`` helpers (subclasses and extensions)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every store and lookup helper of ``ConnectionState`` is a coroutine (``store_user``, ``_get_guild``,
``_add_guild``, ``get_channel``, ``chunk_guild``, ``is_guild_evicted()``, ``process_chunk_requests()``...). The
properties ``guilds``, ``emojis``, ``stickers``, ``polls``, ``private_channels`` and ``sounds`` still read the
in-process cache. The event parsers are coroutine functions awaited by ``Client._handle_event``, so a state
subclass overriding ``parse_x`` must define ``async def parse_x``. Why: the parsers read and write the cache.

.. code-block:: python3

    # pycord
    class MyState(ConnectionState):
        def parse_message_create(self, data):
            ...
            self.dispatch("message", message)

    # pycord-next
    class MyState(ConnectionState):
        async def parse_message_create(self, data):
            ...
            self.dispatch("message", message)

.. _migrating_next_models_cache:

Models and ``state._populate_guild``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Models are built synchronously and never read the cache in their constructors. What used to be resolved
there is done by the state afterwards (``await state._populate_guild(guild, data)``,
``await state._create_message(...)``) or lazily by a property. :class:`Guild`, :class:`Thread` and :class:`Message`
no longer hold dictionaries of other entities, so ``Guild._sync`` and ``Message._rebind_cached_references``
are removed. This only matters if you construct models yourself (tests, custom states).

.. code-block:: python3

    # pycord
    guild = Guild(data=data, state=state)

    # pycord-next
    guild = Guild(data=data, state=state)
    await state._populate_guild(guild, data)

.. _migrating_next_guild_internals:

``Guild._add_channel`` and the other private mutators
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``Guild._add_channel``, ``_add_member``, ``_remove_member``, ``_add_role``, ``_remove_role``, ``_add_thread``,
``_update_voice_state``, ``_get_and_update_member`` and ``Thread._add_member`` / ``_pop_member`` are
coroutines, as they write to the cache. They are private, only subclasses are affected.

.. code-block:: python3

    # pycord
    guild._add_role(role)

    # pycord-next
    await guild._add_role(role)

.. _migrating_next_gateway:

Gateway
-------

.. _migrating_next_client_ws:

``Client.ws``
~~~~~~~~~~~~~

``Client.ws`` is a read-only property: the shard-0 :class:`~discord.gateway.DiscordWebSocket` while
connected with the default transport, ``None`` otherwise (custom transport, not connected,
:class:`AutoShardedClient` before its shards launched). ``DiscordWebSocket`` no longer has ``change_presence``,
``request_chunks``, ``voice_state`` and ``request_soundboard_sounds``: they are methods of the
:class:`~discord.gateway.GatewayTransport`, which ``client._get_websocket(guild_id)`` returns. Use the public
methods of the client where there is one.

.. code-block:: python3

    # pycord
    await client.ws.change_presence(activity=activity)
    await client.ws.request_chunks(guild.id, None, limit=0)

    # pycord-next
    await client.change_presence(activity=activity)
    await client._get_websocket(guild.id).request_chunks(guild.id, limit=0)

.. _migrating_next_launch_shard:

``AutoShardedClient.launch_shard()`` and ``launch_shards()``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``AutoShardedClient.launch_shard()``, ``launch_shards()`` and the internal ``Shard``, ``EventType`` and
``EventItem`` of ``discord.shard`` are removed. The shards are owned by
:class:`~discord.gateway.ShardManager`. Subclasses that customised the launch should pass a ``gateway``
factory (see :doc:`gateway`) or use ``shard_ids`` / ``shard_count``; :attr:`AutoShardedClient.shards`,
``get_shard()``, ``latencies`` and ``shard_ids`` are unchanged.

.. code-block:: python3

    # pycord
    class MyBot(discord.AutoShardedBot):
        async def launch_shards(self):
            await super().launch_shards()

    # pycord-next
    bot = discord.AutoShardedBot(shard_count=16, shard_ids=[0, 1, 2, 3])

.. _migrating_next_identify_hook:

``Client.before_identify_hook``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The default :meth:`Client.before_identify_hook` no longer sleeps 5 seconds: the library handles the identify
concurrency of Discord. Overrides are called with the same arguments. Remove any sleep you copied from the
old default; keep the hook for your own purposes.

.. code-block:: python3

    # pycord
    async def before_identify_hook(self, shard_id, *, initial=False):
        if not initial:
            await asyncio.sleep(5.0)

    # pycord-next: the IdentifyLimiter spaces the IDENTIFYs, nothing to do
    async def before_identify_hook(self, shard_id, *, initial=False):
        ...

.. _migrating_next_commands:

Commands
--------

.. _migrating_next_desynced:

``Bot.get_desynced_commands()``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``command`` of a ``"delete"`` action is the payload Discord returned (a ``dict`` with ``id``, ``name``...)
instead of the command name. Only code that overrides the sync or reads that list is affected.

.. code-block:: python3

    # pycord
    for action in await bot.get_desynced_commands():
        if action["action"] == "delete":
            print(action["command"])             # "ping"

    # pycord-next
    for action in await bot.get_desynced_commands():
        if action["action"] == "delete":
            print(action["command"]["name"])     # "ping"

.. _migrating_next_converters:

Converters and checks
~~~~~~~~~~~~~~~~~~~~~

``GuildChannelConverter._resolve_channel()`` / ``_resolve_thread()`` and
``PartialMessageConverter._resolve_channel()`` are coroutines, and the predicates created by ``has_role``,
``has_any_role``, ``bot_has_role``, ``bot_has_any_role``, ``has_permissions``, ``bot_has_permissions``,
``has_guild_permissions``, ``bot_has_guild_permissions`` and ``is_nsfw`` are coroutine functions
(``check.predicate`` was already awaitable). Only code that subclasses the converters or calls an entry of
``Command.checks`` directly is affected.

.. code-block:: python3

    # pycord
    class MyChannelConverter(commands.GuildChannelConverter):
        @staticmethod
        def _resolve_channel(ctx, argument, attribute, type):
            ...

    result = command.checks[0](ctx)

    # pycord-next
    class MyChannelConverter(commands.GuildChannelConverter):
        @staticmethod
        async def _resolve_channel(ctx, argument, attribute, type):
            ...

    result = await discord.utils.maybe_coroutine(command.checks[0], ctx)

.. _migrating_next_voice:

Voice
-----

These are internals of the voice receive pipeline and connection, not documented.

``discord.voice.utils.buffer.Buffer``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``discord.voice.utils.buffer.Buffer`` and ``BaseBuff`` are removed, ``JitterBuffer`` stands alone (``len()``,
``is_ready()``), and ``PacketDecoder`` no longer makes ``FakePacket``\s for lost packets (the jitter buffer skips
them).

.. code-block:: python3

    # pycord
    from discord.voice.utils.buffer import Buffer

    # pycord-next
    from discord.voice.utils.buffer import JitterBuffer

``VoiceConnectionState.self_voice_state``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The property reading ``guild.me.voice`` is replaced by ``await VoiceConnectionState.get_self_voice_state()``
and ``_update_voice_channel()`` is a coroutine.

.. code-block:: python3

    # pycord
    state = connection.self_voice_state

    # pycord-next
    state = await connection.get_self_voice_state()

.. _migrating_next_models:

Models
------

.. _migrating_next_attachment:

``Attachment.to_dict()``
~~~~~~~~~~~~~~~~~~~~~~~~

``Attachment.to_dict()["spoiler"]`` is now ``["is_spoiler"]``, the documented attachment request field
(``"flags"`` is included when set): ``spoiler`` is not a Discord field, so the flag was silently ignored when
attachments were sent back with ``Message.edit(attachments=...)``. An empty description is sent as ``""``
(only ``None`` is left out) so that :meth:`Attachment.with_changes` can clear it.

.. code-block:: python3

    # pycord
    data = attachment.to_dict()
    if data.get("spoiler"):
        ...

    # pycord-next
    data = attachment.to_dict()
    if data.get("is_spoiler"):
        ...

    await message.edit(attachments=[attachment.with_changes(description="")])
