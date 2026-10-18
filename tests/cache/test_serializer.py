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

from __future__ import annotations

import enum
from array import array
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from msgspec import msgpack

from discord.asset import Asset
from discord.cache import ModelSerializer, serializers
from discord.cache.serializers import register
from discord.colour import Colour
from discord.enums import ChannelType, MessageType
from discord.flags import MessageFlags
from discord.permissions import PermissionOverwrite, Permissions
from discord.utils import MISSING, SnowflakeList

STATE = SimpleNamespace(name="state")


@register
class Mode(enum.Enum):
    fast = "fast"
    slow = "slow"


@register
class Level(enum.IntEnum):
    low = 1
    high = 2


@register
class Leaf:
    __slots__ = ("_cs_memo", "_state", "tags", "value")

    def __init__(self, value: Any, tags: Any = None) -> None:
        self._state: Any = STATE
        self.value = value
        self.tags = tags


@register
class Branch(Leaf):
    __slots__ = ("__hidden", "children", "created", "mode")

    def __init__(self) -> None:
        super().__init__(1)
        self.__hidden = "kept"
        self.children: list[Leaf] = []
        self.created: datetime | None = None
        self.mode: Mode | None = None


@register
class Plain:
    pass


@register
class Linked:
    __slots__ = ("back", "items", "name")
    __cache_skip__ = ("back",)

    def __init__(self, name: str) -> None:
        self.name = name
        self.items: list[Linked] = []
        self.back: Linked | None = None

    def __cache_restore__(self) -> None:
        for item in self.items:
            item.back = self


@register
class Holder:
    __slots__ = ("item",)

    def __init__(self, item: Any) -> None:
        self.item = item


class Unregistered(enum.Enum):
    a = 1


class NotRegistered:
    __slots__ = ("x",)

    def __init__(self) -> None:
        self.x = 1


class Counter(dict):  # type: ignore[type-arg]
    __slots__ = ()


@pytest.fixture
def serializer() -> ModelSerializer:
    return ModelSerializer(STATE)  # type: ignore[arg-type]


def roundtrip(serializer: ModelSerializer, value: Any) -> Any:
    data = serializer.dumps(value)
    assert isinstance(data, bytes)
    return serializer.loads(data)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        0,
        -5,
        2**63,
        1.5,
        "text",
        b"\x00bytes",
        [1, [2, 3]],
        (1, (2, "x")),
        {1, 2, 3},
        frozenset({"a"}),
        {"a": 1, 2: [3], (1, 2): {"nested": None}},
        [(), [], {}],
    ],
)
def test_builtin_roundtrip(serializer: ModelSerializer, value: Any) -> None:
    restored = roundtrip(serializer, value)
    assert restored == value
    assert type(restored) is type(value)


def test_loads_none(serializer: ModelSerializer) -> None:
    assert serializer.loads(None) is None
    assert serializer.encoding is None


def test_tuple_and_list_stay_distinct(serializer: ModelSerializer) -> None:
    restored = roundtrip(serializer, [(1, 2), [1, 2]])
    assert restored == [(1, 2), [1, 2]]
    assert isinstance(restored[0], tuple)
    assert isinstance(restored[1], list)


def test_datetime_and_timedelta(serializer: ModelSerializer) -> None:
    aware = datetime(2024, 5, 17, 12, 30, 1, 250, tzinfo=timezone.utc)
    naive = datetime(2020, 1, 2, 3, 4, 5)  # noqa: DTZ001
    delta = timedelta(days=3, seconds=4, microseconds=5)
    assert roundtrip(serializer, [aware, naive, delta]) == [aware, naive, delta]
    assert roundtrip(serializer, aware).tzinfo is not None


def test_missing_sentinel(serializer: ModelSerializer) -> None:
    assert roundtrip(serializer, [MISSING, 1])[0] is MISSING


def test_stdlib_enums(serializer: ModelSerializer) -> None:
    assert roundtrip(serializer, Mode.slow) is Mode.slow
    assert roundtrip(serializer, Level.high) is Level.high
    assert roundtrip(serializer, [Level.low]) == [Level.low]


def test_discord_enums(serializer: ModelSerializer) -> None:
    assert roundtrip(serializer, ChannelType.forum) is ChannelType.forum
    assert roundtrip(serializer, MessageType.reply) is MessageType.reply


def test_discord_enum_unknown_value(serializer: ModelSerializer) -> None:
    unknown = ChannelType.try_value(9999)
    assert roundtrip(serializer, ChannelType.try_value(0)) is ChannelType.text
    assert not isinstance(unknown, ChannelType) or unknown.value == 9999


def test_slotted_object_roundtrip(serializer: ModelSerializer) -> None:
    leaf = Leaf({"k": [1, 2]}, tags=("a", "b"))
    restored = roundtrip(serializer, leaf)
    assert type(restored) is Leaf
    assert restored.value == {"k": [1, 2]}
    assert restored.tags == ("a", "b")
    assert restored is not leaf


def test_state_is_not_stored_and_is_rebound(serializer: ModelSerializer) -> None:
    other = ModelSerializer(SimpleNamespace(name="other"))  # type: ignore[arg-type]
    data = serializer.dumps(Leaf(1))
    assert b"state" not in data
    assert other.loads(data)._state.name == "other"


def test_memo_slots_are_skipped(serializer: ModelSerializer) -> None:
    leaf = Leaf(1)
    leaf._cs_memo = "expensive"
    assert b"expensive" not in serializer.dumps(leaf)
    assert not hasattr(roundtrip(serializer, leaf), "_cs_memo")


def test_unset_slots_stay_unset(serializer: ModelSerializer) -> None:
    leaf = Leaf.__new__(Leaf)
    leaf.value = 3
    restored = roundtrip(serializer, leaf)
    assert restored.value == 3
    assert not hasattr(restored, "tags")


def test_inherited_and_name_mangled_slots(serializer: ModelSerializer) -> None:
    branch = Branch()
    branch.tags = ["t"]
    branch.created = datetime(2024, 1, 1, tzinfo=timezone.utc)
    branch.mode = Mode.fast
    branch.children = [Leaf(1), Leaf(2, tags=[Leaf(3)])]
    restored = roundtrip(serializer, branch)
    assert type(restored) is Branch
    assert restored._Branch__hidden == "kept"
    assert restored.tags == ["t"]
    assert restored.created == branch.created
    assert restored.mode is Mode.fast
    assert [c.value for c in restored.children] == [1, 2]
    assert restored.children[1].tags[0].value == 3
    assert restored.children[1]._state is STATE


def test_real_value_objects(serializer: ModelSerializer) -> None:
    colour = roundtrip(serializer, Colour(0x5865F2))
    assert colour == Colour(0x5865F2)

    perms = roundtrip(serializer, Permissions(administrator=True, send_messages=True))
    assert perms == Permissions(administrator=True, send_messages=True)
    assert perms.administrator

    flags = roundtrip(serializer, MessageFlags(crossposted=True, ephemeral=True))
    assert flags == MessageFlags(crossposted=True, ephemeral=True)

    overwrite = roundtrip(serializer, PermissionOverwrite(read_messages=True))
    assert overwrite == PermissionOverwrite(read_messages=True)


def test_asset_like_object_rebinds_state(serializer: ModelSerializer) -> None:
    asset = Asset(
        STATE, url="https://cdn.discordapp.com/a.png", key="abc", animated=True
    )
    restored = roundtrip(serializer, asset)
    assert restored._state is STATE
    assert restored._url == asset._url
    assert restored._key == "abc"
    assert restored._animated is True


def test_nested_real_objects(serializer: ModelSerializer) -> None:
    asset = Asset(STATE, url="https://cdn.discordapp.com/a.png", key="abc")
    holder = Holder(
        {
            "colour": Colour(7),
            "assets": [asset, None],
            "type": ChannelType.text,
            "perms": (Permissions.all(), Permissions.none()),
        }
    )
    restored = roundtrip(serializer, holder)
    item = restored.item
    assert item["colour"] == Colour(7)
    assert item["assets"][0]._url == asset._url
    assert item["assets"][1] is None
    assert item["type"] is ChannelType.text
    assert item["perms"] == (Permissions.all(), Permissions.none())


def test_discord_classes_resolve_without_registration(
    serializer: ModelSerializer,
) -> None:
    serializers._REGISTRY.pop("discord.colour:Colour", None)
    assert roundtrip(serializer, Colour(3)) == Colour(3)


def test_unregistered_class_is_rejected_on_dump(serializer: ModelSerializer) -> None:
    with pytest.raises(TypeError, match=r"NotRegistered.*not registered"):
        serializer.dumps(NotRegistered())
    with pytest.raises(TypeError, match=r"Unregistered.*slot Holder\.item"):
        serializer.dumps(Holder(Unregistered.a))


def test_unsupported_value_names_class_and_slot(serializer: ModelSerializer) -> None:
    with pytest.raises(TypeError, match=r"function.*slot Leaf\.value"):
        serializer.dumps(Leaf(lambda: None))
    with pytest.raises(TypeError, match=r"NotRegistered.*slot Holder\.item"):
        serializer.dumps(Holder([1, NotRegistered()]))


def test_local_classes_are_rejected(serializer: ModelSerializer) -> None:
    class Local:
        __slots__ = ()

    with pytest.raises(TypeError, match="Local"):
        serializer.dumps(Local())


def test_unsupported_top_level_value(serializer: ModelSerializer) -> None:
    with pytest.raises(TypeError, match=r"object"):
        serializer.dumps(object())


def test_nested_unsupported_value_reports_owner_slot(
    serializer: ModelSerializer,
) -> None:
    holder = Holder([1, {"a": (2, Holder(object()))}])
    with pytest.raises(TypeError, match=r"builtins\.object.*slot Holder\.item"):
        serializer.dumps(holder)


def test_builtin_subclasses_are_rejected(serializer: ModelSerializer) -> None:
    with pytest.raises(TypeError, match="Counter"):
        serializer.dumps(Holder(Counter(a=1)))


def test_undeclared_instance_attributes_are_rejected(
    serializer: ModelSerializer,
) -> None:
    plain = Plain()
    plain.x = 1  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match=r"Plain.*not declared in __slots__"):
        serializer.dumps(plain)


def test_cyclic_structures_are_rejected(serializer: ModelSerializer) -> None:
    holder = Holder(None)
    holder.item = holder
    with pytest.raises(TypeError, match="cyclic"):
        serializer.dumps(holder)


def test_corrupt_payloads(serializer: ModelSerializer) -> None:
    with pytest.raises(TypeError, match="unknown tag"):
        serializer.loads(msgpack.encode([99, 1]))
    with pytest.raises(TypeError, match="unknown slots"):
        serializer.loads(
            msgpack.encode([11, "tests.cache.test_serializer:Leaf", {"bogus": 1}])
        )
    with pytest.raises(TypeError, match="unknown or unregistered"):
        serializer.loads(msgpack.encode([11, "os:system", {}]))
    with pytest.raises(TypeError, match="unknown or unregistered"):
        serializer.loads(msgpack.encode([11, "discord.colour:Missing", {}]))


def test_skipped_slots_are_restored_by_the_hook(serializer: ModelSerializer) -> None:
    parent = Linked("parent")
    child = Linked("child")
    child.back = parent
    parent.items.append(child)

    loaded = serializer.loads(serializer.dumps(parent))

    assert loaded.name == "parent"
    assert loaded.items[0].name == "child"
    assert loaded.items[0].back is loaded
    assert not hasattr(loaded, "back")


def test_array_subclasses_round_trip(serializer: ModelSerializer) -> None:
    snowflakes = SnowflakeList([3, 1, 2])
    loaded = serializer.loads(serializer.dumps(snowflakes))
    plain = serializer.loads(serializer.dumps(array("Q", [5, 6])))

    assert type(loaded) is SnowflakeList
    assert list(loaded) == [1, 2, 3]
    assert loaded.has(2)
    assert type(plain) is array
    assert plain.typecode == "Q"
    assert list(plain) == [5, 6]


def test_classes_are_stored_by_name(serializer: ModelSerializer) -> None:
    loaded = serializer.loads(serializer.dumps(Holder(Leaf)))
    assert loaded.item is Leaf

    with pytest.raises(TypeError, match="not registered"):
        serializer.dumps(Holder(type("Local", (), {})))
