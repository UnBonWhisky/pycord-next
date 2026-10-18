.. currentmodule:: discord

.. _gateway_guide:

Gateway
=======

The gateway is the websocket Discord sends events through. Pycord next splits it in two parts: a
**transport** moves the frames, a :class:`~discord.gateway.ShardManager` owns the transports of the
shards of your client. By default the transport connects straight to Discord, and a bot that does not
configure anything behaves as it always did. This page covers the other cases. The classes are in
:ref:`discord_api_gateway`.

Direct connection
-----------------

``Client.run()`` and :class:`AutoShardedClient` use :class:`~discord.gateway.DiscordGatewayTransport`:
one websocket per shard, heartbeat, resume and reconnect handled for you, resuming on the
``resume_gateway_url`` Discord gave.

Three options tune it, they are accepted by :class:`Client` and every subclass:

.. code-block:: python3

    bot = discord.AutoShardedBot(
        gateway_compression="zstd-stream",   # "zlib-stream" (default), "zstd-stream" or None
        large_threshold=100,                 # 50 to 250, 250 by default
    )
    print(bot.session_start_limit)           # total, remaining, reset_after, max_concurrency

:ref:`Zstandard <gateway_zstd>` compression needs ``pip install "py-cord[zstd]"``.
:attr:`Client.session_start_limit` is the :class:`~discord.gateway.SessionStartLimit` of the last
*Get Gateway Bot* request.

.. _gateway_zstd:

Compression
~~~~~~~~~~~

Discord compresses the whole connection (transport compression), the library inflates it. ``zlib-stream``
is the default; ``zstd-stream`` uses less bandwidth and CPU on busy bots and needs the ``zstd`` extra.
The library handles transport compression only, so the ``compress`` flag of the IDENTIFY payload is not
sent.

Sharding
--------

Use :class:`AutoShardedClient` or :class:`AutoShardedBot` for a bot that needs more than one shard.
``shard_count`` and ``shard_ids`` pick the shards a process runs, which is how a bot is split over
several processes or machines (clustering): each process gets a subset of ``shard_ids`` with the same
``shard_count``.

.. code-block:: python3

    bot = discord.AutoShardedBot(shard_count=16, shard_ids=[0, 1, 2, 3])

Launching shards is done by the :class:`~discord.gateway.ShardManager`. Discord allows
``max_concurrency`` IDENTIFYs per 5 seconds (from *Get Gateway Bot*), in buckets of
``shard_id % max_concurrency``. The manager launches the buckets in parallel and the shards of a
bucket one after the other, and an :class:`~discord.gateway.IdentifyLimiter` keeps 5 seconds between
two IDENTIFYs of a bucket, also when a shard identifies again later. Big bots start much faster than
with the former fixed pause. :meth:`Client.before_identify_hook` is still called for every shard; its
default no longer sleeps.

.. _gateway_rate_limits:

Rate limits
-----------

The gateway has its own rate limit (120 commands per minute; the library keeps 110 for your commands so
heartbeats always fit). The transport applies it to what you send (presence, voice state, member requests).

When Discord answers a request with a ``RATE_LIMITED`` event the client dispatches the
:func:`on_gateway_rate_limited` event, where ``payload`` is a :class:`~discord.GatewayRateLimit`
with ``opcode``, ``retry_after``, ``meta``, ``guild_id`` and ``nonce``. A *Request Guild Members* that
was rate limited makes :meth:`Guild.query_members` and :meth:`Guild.chunk` raise
:exc:`GatewayRateLimited` (with ``retry_after``) instead of waiting for the timeout:

.. code-block:: python3

    @bot.event
    async def on_gateway_rate_limited(payload):
        print(f"opcode {payload.opcode} limited, retry in {payload.retry_after}s")

    try:
        await guild.chunk()
    except discord.GatewayRateLimited as error:
        await asyncio.sleep(error.retry_after)

.. _gateway_redis:

Redis Streams: proxy and workers
--------------------------------

For a bot that must restart or scale without reconnecting to Discord, split it in two:

- a **gateway proxy** keeps the connections to Discord and appends every raw dispatch event to a
  Redis stream, one stream per shard so that the events of a guild stay in order;
- any number of **workers** read those streams and run your bot code. The workers of one consumer
  group share the events and take over those of a worker that crashed.

The proxy runs no cache and no parser. Commands your workers send (presence, voice state, member
requests, soundboard sounds, channel info) are appended to a command stream and executed by the proxy,
so the gateway rate limit is applied once. Install ``py-cord[redis]`` on both sides.

Start the proxy:

.. code-block:: shell

    $ export DISCORD_TOKEN="your token"
    $ python -m discord gateway-proxy --redis-url redis://localhost:6379/0 \
          --prefix mybot --shard-ids 0-3 --shard-count 4 --intents 53575421

``--prefix`` must be the one of the workers. The other options are ``--compression``
(``zlib-stream``, ``zstd-stream`` or ``none``), ``--maxlen`` (events kept per shard, count based,
10000 by default), and ``--log-level``. The proxy stops cleanly on SIGINT and SIGTERM.

Start as many workers as you want:

.. code-block:: python3

    from aiocache import RedisCache

    import discord
    from discord.gateway.brokers import RedisStreamsTransport

    bot = discord.AutoShardedBot(
        shard_count=4,
        gateway=RedisStreamsTransport.factory(
            url="redis://localhost:6379/0", prefix="mybot", group="workers"
        ),
        cache_backend=RedisCache(endpoint="localhost"),
        cache_namespace="mybot",
    )

Workers should share their cache (:doc:`caching`), since the events of a shard are split between them.
:attr:`Client.latency` is the heartbeat latency measured by the proxy. The complete worker is
``examples/redis_gateway/worker.py``. The streams are configured with
:class:`~discord.gateway.brokers.RedisStreamsConfig`, and
:class:`~discord.gateway.brokers.RedisStreamsPublisher` can feed them from another source.

Writing a custom transport
--------------------------

Any other broker (or a test double) only needs a :class:`~discord.gateway.GatewayTransport`. The
client reads the events of one transport per shard and sends its commands through it. Implement:

- ``connect()``: open the connection;
- ``events()``: an async iterator of :class:`~discord.gateway.GatewayEvent` (dispatch events only,
  ``READY`` first), ending when the transport is closed;
- ``send(op, d)``: send a command;
- ``close(code=1000)``, ``latency``, ``is_ratelimited()`` and ``is_closed()``.

``change_presence``, ``request_chunks``, ``voice_state``, ``request_soundboard_sounds`` and
``request_channel_info`` are provided on top of ``send()``. Pass a factory taking the ``shard_id`` and
``shard_count`` to the client:

.. code-block:: python3

    def factory(shard_id, shard_count):
        return MyBrokerTransport(shard_id, shard_count)

    bot = discord.Bot(gateway=factory)

``examples/gateway/custom_transport.py`` is a runnable skeleton.
