Welcome to Pycord
=================

.. image:: /images/snake.svg
.. image:: /images/snake_dark.svg

Pycord is a modern, easy to use, feature-rich, and async ready API wrapper
for Discord.

**Features:**

- Modern Pythonic API using ``async``\/``await`` syntax
- Sane rate limit handling that prevents 429s
- Command extension to aid with bot creation
- Easy to use with an object oriented design
- Optimised for both speed and memory

Getting started
---------------

Is this your first time using the library? This is the place to get started!

- **First steps:** :doc:`installing` | :doc:`quickstart` | :doc:`logging` | :doc:`faq` | :resource:`Guide <guide>`
- **Working with Discord:** :doc:`discord` | :doc:`intents`
- **Running a bot at scale:** :doc:`caching` | :doc:`gateway`
- **Coming from pycord:** :doc:`migrating_to_next`
- **Examples:** Many examples are available in the :resource:`repository <examples>`.

Getting help
------------

If you're having trouble with something, these resources might help.

- Try the :doc:`faq` first, it's got answers to all common questions.
- Ask us and hang out with us in our :resource:`Discord <discord>` server.
- If you're looking for something specific, try the :ref:`index <genindex>` or :ref:`searching <search>`.
- Report bugs in the :resource:`issue tracker <issues>`.

Manuals
-------

These pages go into great detail about everything the API can do.

Core API
~~~~~~~~

.. toctree::
  :maxdepth: 1

  api/index.rst

Extensions
~~~~~~~~~~

These extensions help you during development when it comes to common tasks.

.. toctree::
  :caption: Extensions
  :maxdepth: 1
  :hidden:

  ext/commands/index.rst
  ext/tasks/index.rst
  ext/pages/index.rst
  ext/bridge/index.rst

- :doc:`ext/commands/index` - Bot commands framework
- :doc:`ext/tasks/index` - asyncio.Task helpers
- :doc:`ext/pages/index` - A pagination extension module
- :doc:`ext/bridge/index` - A module that bridges slash commands to prefixed commands

Guides
~~~~~~

.. toctree::
  :caption: Guides
  :maxdepth: 1
  :hidden:

  caching
  gateway

- :doc:`caching` - In-process and remote (Redis, Memcached) caches, synchronous and awaitable accessors.
- :doc:`gateway` - Transports, sharding, rate limits, and the Redis Streams proxy and workers.

Meta
----

If you're looking for something related to the project itself, it's here.

.. toctree::
  :caption: Meta
  :maxdepth: 1
  :hidden:

  changelog
  changes
  version_guarantees
  migrating_to_next
  migrating_to_v1
  migrating_to_v2

- :doc:`changelog` - The changelog for the library.
- :doc:`changes` - Every difference between Pycord and Pycord Next.
- :doc:`version_guarantees` - The version guarantees for the library.
- :doc:`migrating_to_next` - How to migrate from Pycord to Pycord Next.
- :doc:`migrating_to_v1` - How to migrate from v0.x to v1.x.
- :doc:`migrating_to_v2` - How to migrate from v1.x to v2.x.
