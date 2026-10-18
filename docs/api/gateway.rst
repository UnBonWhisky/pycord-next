.. currentmodule:: discord.gateway

.. _discord_api_gateway:

Gateway
=======

The gateway connection is split in a transport, which moves the frames, and the
shard manager, which owns the shards of a client. Replacing the transport lets a
bot read its events from somewhere else than the Discord websocket.

Transports
----------

.. attributetable:: GatewayTransport

.. autoclass:: GatewayTransport
    :members:

.. data:: GatewayTransportFactory

    The type of the callable that builds a :class:`GatewayTransport` from a
    ``(shard_id, shard_count)`` pair.

.. attributetable:: DiscordGatewayTransport

.. autoclass:: DiscordGatewayTransport
    :members:

.. attributetable:: BaseWebSocket

.. autoclass:: BaseWebSocket
    :members:

.. attributetable:: DiscordWebSocket

.. autoclass:: DiscordWebSocket
    :members:

.. attributetable:: DiscordClientWebSocketResponse

.. autoclass:: DiscordClientWebSocketResponse
    :members:

.. attributetable:: KeepAliveHandler

.. autoclass:: KeepAliveHandler
    :members:

.. attributetable:: EventListener

.. autoclass:: EventListener
    :members:

.. attributetable:: WebSocketClosure

.. autoclass:: WebSocketClosure
    :members:

.. autoexception:: ReconnectWebSocket
    :members:

Sharding
--------

.. attributetable:: ShardManager

.. autoclass:: ShardManager
    :members:

.. attributetable:: GatewayRatelimiter

.. autoclass:: GatewayRatelimiter
    :members:

.. attributetable:: IdentifyLimiter

.. autoclass:: IdentifyLimiter
    :members:

Models
------

.. autoclass:: Opcode
    :members:
    :undoc-members:

.. attributetable:: GatewayEvent

.. autoclass:: GatewayEvent
    :members:

.. attributetable:: GatewayInfo

.. autoclass:: GatewayInfo
    :members:

.. attributetable:: SessionStartLimit

.. autoclass:: SessionStartLimit
    :members:

.. autofunction:: resume_url

.. autodata:: NO_RECONNECT_CLOSE_CODES
    :no-value:

    The close codes after which the connection must not be reopened.

.. autodata:: NEW_SESSION_CLOSE_CODES
    :no-value:

    The close codes after which a new session has to be started instead of a resume.

Compression
-----------

.. data:: GatewayCompression

    The compression names accepted by the client: ``"zlib-stream"`` or ``"zstd-stream"``.

.. autoclass:: Inflater
    :members:

.. autoclass:: ZlibStreamInflater
    :members:

.. autoclass:: ZstdStreamInflater
    :members:

.. autofunction:: create_inflater

Redis Streams
-------------

.. currentmodule:: discord.gateway

.. autoclass:: discord.gateway.proxy.GatewayProxy
    :members:

.. autoclass:: discord.gateway.brokers.RedisStreamsConfig
    :members:

.. autoclass:: discord.gateway.brokers.RedisStreamsOptions
    :members:

.. autoclass:: discord.gateway.brokers.RedisStreamsPublisher
    :members:

.. autoclass:: discord.gateway.brokers.RedisStreamsTransport
    :members:
