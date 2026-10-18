"""
The MIT License (MIT)

Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from typing_extensions import NotRequired

from .member import Member
from .snowflake import Snowflake
from .user import User

ScheduledEventStatus = Literal[1, 2, 3, 4]
ScheduledEventEntityType = Literal[1, 2, 3]
ScheduledEventLocationType = ScheduledEventEntityType
ScheduledEventPrivacyLevel = Literal[2]
ScheduledEventRecurrenceFrequency = Literal[0, 1, 2, 3]
ScheduledEventWeekday = Literal[0, 1, 2, 3, 4, 5, 6]
ScheduledEventMonth = Literal[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]


class ScheduledEventNWeekdayRecurrence(TypedDict):
    n: int
    day: ScheduledEventWeekday


class ScheduledEventRecurrenceRule(TypedDict):
    start: str
    end: NotRequired[str | None]
    frequency: ScheduledEventRecurrenceFrequency
    interval: int
    by_weekday: NotRequired[list[ScheduledEventWeekday] | None]
    by_n_weekday: NotRequired[list[ScheduledEventNWeekdayRecurrence] | None]
    by_month: NotRequired[list[ScheduledEventMonth] | None]
    by_month_day: NotRequired[list[int] | None]
    by_year_day: NotRequired[list[int] | None]
    count: NotRequired[int | None]


class ScheduledEvent(TypedDict):
    id: Snowflake
    guild_id: Snowflake
    channel_id: Snowflake | None
    creator_id: NotRequired[Snowflake | None]
    name: str
    description: NotRequired[str | None]
    image: NotRequired[str | None]
    scheduled_start_time: str
    scheduled_end_time: str | None
    privacy_level: ScheduledEventPrivacyLevel
    status: ScheduledEventStatus
    entity_type: ScheduledEventEntityType
    entity_id: Snowflake | None
    entity_metadata: ScheduledEventEntityMetadata | None
    creator: NotRequired[User]
    user_count: NotRequired[int]
    recurrence_rule: NotRequired[ScheduledEventRecurrenceRule | None]


class ScheduledEventEntityMetadata(TypedDict):
    location: NotRequired[str]


class ScheduledEventSubscriber(TypedDict):
    guild_scheduled_event_id: Snowflake
    user_id: Snowflake
    user: User
    member: Member | None
