.. currentmodule:: discord.cache

.. _discord_api_cache:

Cache
=====

The state of the client (guilds, channels, members, messages...) lives in a
:class:`CacheStore`. The default store keeps everything in the process, other
backends can keep it elsewhere, see :class:`SyncCacheAccessError` for the
consequences on the synchronous accessors.

Stores and buckets
------------------

.. attributetable:: CacheStore

.. autoclass:: CacheStore
    :members:

.. attributetable:: CacheBucket

.. autoclass:: CacheBucket
    :members:

Indexes
-------

.. attributetable:: KeyIndex

.. autoclass:: KeyIndex
    :members:

.. attributetable:: InProcessIndex

.. autoclass:: InProcessIndex
    :members:

.. attributetable:: RedisIndex

.. autoclass:: RedisIndex
    :members:

Serializers
-----------

.. attributetable:: ModelSerializer

.. autoclass:: ModelSerializer
    :members:
