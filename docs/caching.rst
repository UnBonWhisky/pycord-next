.. currentmodule:: discord

.. _caching:

Caching
=======

Pycord keeps the guilds, channels, members, roles, messages and the other entities the gateway
sends in a cache. By default the cache lives in the memory of your process and works exactly as in
pycord. It can also live in Redis or Memcached, so that several processes share it.

This page explains the two modes, how to choose one and how the API differs between them. The
reference is in :ref:`discord_api_cache`.

In-process cache
----------------

Without any option the cache is in-process: the entities are live Python objects, reading them costs
a dictionary lookup, and the synchronous properties and methods of pycord keep working.

.. code-block:: python3

    import discord

    bot = discord.Bot(intents=discord.Intents.default() | discord.Intents(members=True))

    @bot.event
    async def on_ready():
        print(len(bot.guilds))                       # synchronous, reads the cache
        guild = await bot.get_guild(1234567)         # lookups by ID are awaited
        if guild is not None:
            print(len(guild.members))                # synchronous, reads the cache

The ``get_*`` lookups by ID (``await client.get_guild(id)``, ``await guild.get_member(id)``...) and the
generators that walk the whole cache (``async for channel in client.get_all_channels()``) are awaited
on every backend. This is the only difference with pycord for a bot that stays on the in-process
cache, see :doc:`migrating_to_next`.

.. _caching_remote:

Remote backends
---------------

The cache is built on `aiocache <https://aiocache.aio-libs.org>`_. Pass any aiocache backend with
``cache_backend`` to keep the cache there:

- Redis: ``pip install "py-cord[redis]"``, then ``aiocache.RedisCache``.
- Memcached: ``pip install "py-cord[memcached]"``, then ``aiocache.MemcachedCache``.

Models are stored with a generic msgpack serializer, so every cached entity survives the trip to the
backend. With Redis the order of the keys (for ``max_messages`` and the other limits) is kept in a
sorted set, so several processes can share the same cache.

.. code-block:: python3

    import os

    from aiocache import RedisCache

    import discord

    bot = discord.Bot(
        intents=discord.Intents.default() | discord.Intents(members=True),
        cache_backend=RedisCache(endpoint=os.environ.get("REDIS_HOST", "localhost")),
        cache_namespace="mybot",
        cache_fetch=True,
    )

    bot.run(os.environ["DISCORD_TOKEN"])

``cache_backend``, ``cache_namespace`` and ``cache_fetch`` are accepted by :class:`Client`,
:class:`Bot`, :class:`AutoShardedClient` and :class:`AutoShardedBot`:

``cache_backend``
    The aiocache backend. ``None`` (the default) is the in-process cache.

``cache_namespace``
    The prefix of the keys, ``"pycord"`` by default. Bots that share a namespace share a cache, give
    each bot its own unless that is what you want.

``cache_fetch``
    When ``True``, the result of every ``fetch_*`` call that returns a cacheable entity (users, guilds,
    channels, messages, members, roles...) is stored too, with the same limits as the gateway events
    (``max_messages``, :class:`MemberCacheFlags`). The default ``False`` keeps the pycord behaviour.

See ``examples/caching/redis_cache.py`` for a complete bot. Combined with the Redis Streams gateway
(:doc:`gateway`), the workers of a bot share one cache.

Limits
------

Nothing in the cache ever expires: there is no TTL. The limits are counts, the same as in pycord:

- ``max_messages`` keeps that many messages and evicts the oldest first (``None`` disables the
  message cache). It is also used when ``cache_fetch=True``.
- The cache of private channels keeps the 128 most recently used ones.
- :class:`MemberCacheFlags` and ``chunk_guilds_at_startup`` decide which members are cached, as before.

.. _caching_sync_async:

Synchronous accessors and their awaitable twins
-----------------------------------------------

A cache read on a remote backend is I/O, which a plain property cannot do. Pycord next therefore has
two forms of every accessor that reads the cache:

- the **synchronous** one, the one pycord has (``guild.members``, ``member.roles``,
  ``channel.permissions_for(member)``...). It reads the in-process cache.
- the **awaitable twin**, which works with every backend (``await guild.get_members()``,
  ``await member.get_roles()``, ``await channel.get_permissions_for(member)``...).

The twin is named after the accessor it replaces:

===============================  ====================================  =====================================
Synchronous accessor             Awaitable twin                        Example
===============================  ====================================  =====================================
property ``x``                   ``await get_x()``                     ``guild.members`` / ``await guild.get_members()``
boolean property ``x``           ``await is_x()``                      ``guild.chunked`` / ``await guild.is_chunked()``
predicate ``is_x()``             ``await check_x()``                   ``emoji.is_usable()`` / ``await emoji.check_usable()``
method ``m(...)``                ``await get_m(...)``                  ``channel.permissions_for(m)`` / ``await channel.get_permissions_for(m)``
===============================  ====================================  =====================================

A twin returns the same type as the accessor and the same value on the in-process cache. The full list
is the table of "Synchronous accessors for the in-process cache" in :doc:`changes`.

.. code-block:: python3

    members = guild.members                  # in-process cache only
    members = await guild.get_members()      # every backend

    async for member in guild.iter_members():   # streams the cached members by batches
        ...

.. _caching_sync_error:

SyncCacheAccessError
~~~~~~~~~~~~~~~~~~~~

With a remote backend, a synchronous accessor cannot read the cache and raises
:exc:`SyncCacheAccessError`. The message names the awaitable twin to use:

.. code-block:: python3

    try:
        count = len(guild.members)
    except discord.SyncCacheAccessError as error:
        print(error)                         # tells you to use ``await guild.get_members()``
        count = len(await guild.get_members())

The simplest way to stay portable is to use the twins everywhere; ``examples/caching/sync_vs_async.py``
shows both forms side by side.

Relationship attributes
~~~~~~~~~~~~~~~~~~~~~~~

Attributes that point to another entity (``message.channel``, ``message.guild``, ``member.guild``,
``role.guild``, ``thread.parent``, ``reaction.message``, ``ctx.guild``...) never raise. With the
in-process cache they return the cached object, as in pycord, or a partial handle built from the ID
when it is not cached. With a remote backend they always return the partial handle:
:class:`PartialGuild`, :class:`PartialMessageable`, :class:`PartialGuildChannel`,
:class:`PartialMessage` or :class:`Object`.

A partial handle has the ID and every action that only needs it (sending a message, banning a member,
fetching...). To read cached data, resolve it:

.. code-block:: python3

    guild = message.guild                    # Guild, or PartialGuild
    guild = await message.get_guild()        # the cached Guild, or None
    guild = await message.guild.fetch()      # always a Guild, from the API

``examples/caching/redis_cache.py`` uses ``await ctx.get_guild()`` for that reason. Every model also
exposes the IDs that need no lookup (``member.guild_id``, ``message.channel_id``,
``reaction.message_id``...).

Choosing a backend
------------------

Stay on the in-process cache for a bot that runs in one process: it is the fastest and needs no
changes to a pycord bot. Use Redis when several processes must see the same state (workers behind a
gateway proxy, a restart that must not lose the cache) and accept that the synchronous accessors are
replaced by their twins.
