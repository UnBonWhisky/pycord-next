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

"""Discord API routes for the monetization resource."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..base import HTTPBase
from ..route import Route

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...types import (
        monetization,
    )
    from ...types.snowflake import Snowflake
    from ..base import Response

__all__ = ("MonetizationRoutes",)


class MonetizationRoutes(HTTPBase):
    """Endpoints of the monetization resource."""

    def list_skus(
        self,
        application_id: Snowflake,
    ) -> Response[list[monetization.SKU]]:
        """Fetch the SKUs of an application."""
        r = Route(
            "GET",
            "/applications/{application_id}/skus",
            application_id=application_id,
        )
        return self.request(r)

    def list_entitlements(
        self,
        application_id: Snowflake,
        *,
        user_id: Snowflake | None = None,
        sku_ids: Sequence[Snowflake] | None = None,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
        limit: int | None = None,
        guild_id: Snowflake | None = None,
        exclude_ended: bool | None = None,
    ) -> Response[list[monetization.Entitlement]]:
        """Fetch the entitlements of an application."""
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = user_id
        if sku_ids is not None:
            params["sku_ids"] = ",".join(str(sku_id) for sku_id in sku_ids)
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        if limit is not None:
            params["limit"] = limit
        if guild_id is not None:
            params["guild_id"] = guild_id
        if exclude_ended is not None:
            params["exclude_ended"] = int(exclude_ended)

        r = Route(
            "GET",
            "/applications/{application_id}/entitlements",
            application_id=application_id,
        )
        return self.request(r, params=params)

    def consume_entitlement(
        self,
        application_id: Snowflake,
        entitlement_id: Snowflake,
    ) -> Response[None]:
        """Consume an entitlement."""
        r = Route(
            "POST",
            "/applications/{application_id}/entitlements/{entitlement_id}/consume",
            application_id=application_id,
            entitlement_id=entitlement_id,
        )
        return self.request(r)

    def create_test_entitlement(
        self,
        application_id: Snowflake,
        payload: monetization.CreateTestEntitlementPayload,
    ) -> Response[monetization.Entitlement]:
        """Create a test entitlement."""
        r = Route(
            "POST",
            "/applications/{application_id}/entitlements",
            application_id=application_id,
        )
        return self.request(r, json=payload)

    def delete_test_entitlement(
        self,
        application_id: Snowflake,
        entitlement_id: Snowflake,
    ) -> Response[None]:
        """Delete a test entitlement."""
        r = Route(
            "DELETE",
            "/applications/{application_id}/entitlements/{entitlement_id}",
            application_id=application_id,
            entitlement_id=entitlement_id,
        )
        return self.request(r)

    def list_sku_subscriptions(
        self,
        sku_id: Snowflake,
        *,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
        limit: int = 50,
        user_id: Snowflake | None = None,
    ) -> Response[list[monetization.Subscription]]:
        """Fetch the subscriptions of a SKU."""
        params: dict[str, Any] = {}
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        params["limit"] = limit
        if user_id is not None:
            params["user_id"] = user_id
        return self.request(
            Route("GET", "/skus/{sku_id}/subscriptions", sku_id=sku_id),
            params=params,
        )

    def get_subscription(
        self,
        sku_id: Snowflake,
        subscription_id: Snowflake,
    ) -> Response[monetization.Subscription]:
        """Fetch a subscription of a SKU."""
        return self.request(
            Route(
                "GET",
                "/skus/{sku_id}/subscriptions/{subscription_id}",
                sku_id=sku_id,
                subscription_id=subscription_id,
            )
        )
