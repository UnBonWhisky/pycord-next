# The MIT License (MIT)
#
# Copyright (c) 2015-2021 Rapptz
# Copyright (c) 2021-present Pycord Development
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

"""Entitlement and subscription gateway event parsers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...monetization import Entitlement, Subscription

if TYPE_CHECKING:
    from ...types.monetization import (
        Entitlement as EntitlementPayload,
        Subscription as SubscriptionPayload,
    )
    from ..state import ConnectionState


async def parse_entitlement_create(
    state: ConnectionState, data: EntitlementPayload
) -> None:
    """Handle the ``ENTITLEMENT_CREATE`` gateway event."""
    event = Entitlement(data=data, state=state)
    state.dispatch("entitlement_create", event)


async def parse_entitlement_update(
    state: ConnectionState, data: EntitlementPayload
) -> None:
    """Handle the ``ENTITLEMENT_UPDATE`` gateway event."""
    event = Entitlement(data=data, state=state)
    state.dispatch("entitlement_update", event)


async def parse_entitlement_delete(
    state: ConnectionState, data: EntitlementPayload
) -> None:
    """Handle the ``ENTITLEMENT_DELETE`` gateway event."""
    event = Entitlement(data=data, state=state)
    state.dispatch("entitlement_delete", event)


async def parse_subscription_create(
    state: ConnectionState, data: SubscriptionPayload
) -> None:
    """Handle the ``SUBSCRIPTION_CREATE`` gateway event."""
    event = Subscription(data=data, state=state)
    state.dispatch("subscription_create", event)


async def parse_subscription_update(
    state: ConnectionState, data: SubscriptionPayload
) -> None:
    """Handle the ``SUBSCRIPTION_UPDATE`` gateway event."""
    event = Subscription(data=data, state=state)
    state.dispatch("subscription_update", event)


async def parse_subscription_delete(
    state: ConnectionState, data: SubscriptionPayload
) -> None:
    """Handle the ``SUBSCRIPTION_DELETE`` gateway event."""
    event = Subscription(data=data, state=state)
    state.dispatch("subscription_delete", event)
