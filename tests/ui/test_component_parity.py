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

import inspect
from dataclasses import dataclass, field
from typing import Any

import pytest

from discord import components, ui
from discord.components import _component_factory
from discord.enums import (
    ButtonStyle,
    ChannelType,
    ComponentType,
    InputTextStyle,
    SeparatorSpacingSize,
)
from discord.utils import get_slots

TEXT_PAYLOAD = {"type": 10, "id": 3, "content": "inner"}
BUTTON_PAYLOAD = {
    "type": 2,
    "id": 5,
    "style": 1,
    "label": "go",
    "custom_id": "go",
    "disabled": True,
    "emoji": {"name": "🔥"},
}


@dataclass
class Case:
    kwargs: dict[str, Any]
    payload: dict[str, Any]
    args: tuple[Any, ...] = field(default_factory=tuple)


CASES: dict[type, list[Case]] = {
    ui.TextDisplay: [
        Case({"id": 7}, {"type": 10, "id": 7, "content": "hello"}, ("hello",)),
    ],
    ui.Separator: [
        Case(
            {
                "divider": False,
                "spacing": SeparatorSpacingSize.large,
                "id": 7,
            },
            {"type": 14, "id": 7, "divider": False, "spacing": 2},
        ),
    ],
    ui.Thumbnail: [
        Case(
            {"description": "alt", "spoiler": True, "id": 7},
            {
                "type": 11,
                "id": 7,
                "media": {"url": "https://example.com/a.png"},
                "description": "alt",
                "spoiler": True,
            },
            ("https://example.com/a.png",),
        ),
    ],
    ui.File: [
        Case(
            {"spoiler": True, "id": 7},
            {
                "type": 13,
                "id": 7,
                "file": {"url": "attachment://a.txt"},
                "spoiler": True,
            },
            ("attachment://a.txt",),
        ),
    ],
    ui.MediaGallery: [
        Case(
            {"id": 7},
            {
                "type": 12,
                "id": 7,
                "items": [
                    {
                        "media": {"url": "https://example.com/a.png"},
                        "description": "alt",
                        "spoiler": True,
                    }
                ],
            },
            (
                components.MediaGalleryItem(
                    "https://example.com/a.png", description="alt", spoiler=True
                ),
            ),
        ),
    ],
    ui.Button: [
        Case(
            {
                "style": ButtonStyle.primary,
                "label": "go",
                "disabled": True,
                "custom_id": "go",
                "emoji": "🔥",
                "id": 5,
            },
            BUTTON_PAYLOAD,
        ),
        Case(
            {"label": "link", "url": "https://example.com", "id": 5},
            {
                "type": 2,
                "id": 5,
                "style": 5,
                "label": "link",
                "url": "https://example.com",
            },
        ),
        Case(
            {"sku_id": 123, "id": 5},
            {"type": 2, "id": 5, "style": 6, "sku_id": 123},
        ),
    ],
    ui.Select: [
        Case(
            {
                "select_type": ComponentType.string_select,
                "custom_id": "pick",
                "placeholder": "choose",
                "min_values": 1,
                "max_values": 2,
                "options": [components.SelectOption(label="a", value="1")],
                "disabled": True,
                "required": False,
                "id": 5,
            },
            {
                "type": 3,
                "id": 5,
                "custom_id": "pick",
                "placeholder": "choose",
                "min_values": 1,
                "max_values": 2,
                "options": [{"label": "a", "value": "1", "default": False}],
                "disabled": True,
                "required": False,
            },
        ),
        Case(
            {
                "select_type": ComponentType.channel_select,
                "custom_id": "pick",
                "channel_types": [ChannelType.text],
                "default_values": [
                    components.SelectDefaultValue(
                        id=1, type=components.SelectDefaultValueType.channel
                    )
                ],
            },
            {
                "type": 8,
                "custom_id": "pick",
                "channel_types": [0],
                "default_values": [{"id": 1, "type": "channel"}],
            },
        ),
    ],
    ui.InputText: [
        Case(
            {
                "style": InputTextStyle.long,
                "custom_id": "text",
                "label": "name",
                "placeholder": "p",
                "min_length": 2,
                "max_length": 20,
                "required": False,
                "value": "v",
                "id": 5,
            },
            {
                "type": 4,
                "id": 5,
                "style": 2,
                "custom_id": "text",
                "label": "name",
                "placeholder": "p",
                "min_length": 2,
                "max_length": 20,
                "required": False,
                "value": "v",
            },
        ),
    ],
    ui.FileUpload: [
        Case(
            {
                "custom_id": "up",
                "min_values": 1,
                "max_values": 3,
                "required": False,
                "id": 5,
            },
            {
                "type": 19,
                "id": 5,
                "custom_id": "up",
                "min_values": 1,
                "max_values": 3,
                "required": False,
            },
        ),
    ],
    ui.RadioGroup: [
        Case(
            {
                "custom_id": "radio",
                "options": [
                    components.RadioGroupOption(label="a"),
                    components.RadioGroupOption(label="b", default=True),
                ],
                "required": False,
                "id": 5,
            },
            {
                "type": 21,
                "id": 5,
                "custom_id": "radio",
                "options": [
                    {"label": "a", "value": "a", "default": False},
                    {"label": "b", "value": "b", "default": True},
                ],
                "required": False,
            },
        ),
    ],
    ui.CheckboxGroup: [
        Case(
            {
                "custom_id": "boxes",
                "options": [components.CheckboxGroupOption(label="a")],
                "min_values": 0,
                "max_values": 1,
                "required": False,
                "id": 5,
            },
            {
                "type": 22,
                "id": 5,
                "custom_id": "boxes",
                "options": [{"label": "a", "value": "a", "default": False}],
                "min_values": 0,
                "max_values": 1,
                "required": False,
            },
        ),
    ],
    ui.Checkbox: [
        Case(
            {"custom_id": "box", "default": True, "id": 5},
            {"type": 23, "id": 5, "custom_id": "box", "default": True},
        ),
    ],
    ui.ActionRow: [
        Case(
            {"id": 9},
            {"type": 1, "id": 9, "components": [BUTTON_PAYLOAD]},
            (
                ui.Button(
                    style=ButtonStyle.primary,
                    label="go",
                    disabled=True,
                    custom_id="go",
                    emoji="🔥",
                    id=5,
                ),
            ),
        ),
    ],
    ui.Section: [
        Case(
            {"accessory": ui.Button(label="b", custom_id="b", id=5), "id": 9},
            {
                "type": 9,
                "id": 9,
                "components": [TEXT_PAYLOAD],
                "accessory": {
                    "type": 2,
                    "id": 5,
                    "style": 2,
                    "label": "b",
                    "custom_id": "b",
                },
            },
            (ui.TextDisplay("inner", id=3),),
        ),
    ],
    ui.Container: [
        Case(
            {"colour": 0x112233, "spoiler": True, "id": 9},
            {
                "type": 17,
                "id": 9,
                "accent_color": 0x112233,
                "spoiler": True,
                "components": [TEXT_PAYLOAD],
            },
            (ui.TextDisplay("inner", id=3),),
        ),
    ],
    ui.Label: [
        Case(
            {
                "item": ui.InputText(custom_id="c", style=InputTextStyle.short),
                "description": "d",
                "id": 4,
            },
            {
                "type": 18,
                "id": 4,
                "label": "lbl",
                "description": "d",
                "component": {"type": 4, "style": 1, "custom_id": "c"},
            },
            ("lbl",),
        ),
    ],
}

UNDERLYING: dict[type, type] = {
    ui.TextDisplay: components.TextDisplay,
    ui.Separator: components.Separator,
    ui.Thumbnail: components.Thumbnail,
    ui.File: components.FileComponent,
    ui.MediaGallery: components.MediaGallery,
    ui.Button: components.Button,
    ui.Select: components.SelectMenu,
    ui.InputText: components.InputText,
    ui.FileUpload: components.FileUpload,
    ui.RadioGroup: components.RadioGroup,
    ui.CheckboxGroup: components.CheckboxGroup,
    ui.Checkbox: components.Checkbox,
    ui.ActionRow: components.ActionRow,
    ui.Section: components.Section,
    ui.Container: components.Container,
    ui.Label: components.Label,
}

LAYOUT_ONLY = {"row", "color"}

RENAMED = {
    (ui.Container, "accent_color"): "colour",
    (ui.Container, "components"): "items",
    (ui.Section, "components"): "items",
    (ui.Label, "component"): "item",
    (ui.ActionRow, "components"): "items",
}


def build(cls: type, case: Case) -> Any:
    return cls(*case.args, **case.kwargs)


def expected(case: Case) -> Any:
    return _component_factory(case.payload)


def normalise(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [normalise(item) for item in value]
    if hasattr(value, "to_component_dict"):
        return value.to_component_dict()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


def public_attributes(cls: type) -> set[str]:
    names = {name for name in get_slots(cls) if not name.startswith("_")}
    for klass in cls.__mro__:
        names |= {
            name
            for name, value in vars(klass).items()
            if isinstance(value, property) and not name.startswith("_")
        }
    return names


PARAMS = [
    pytest.param(cls, case, id=f"{cls.__name__}-{index}")
    for cls, cases in CASES.items()
    for index, case in enumerate(cases)
]


class TestParity:
    def test_every_ui_class_is_covered(self) -> None:
        exported = {
            value
            for value in vars(ui).values()
            if inspect.isclass(value)
            and issubclass(value, ui.Item)
            and getattr(value, "__component__", None) is not None
        }
        assert exported == set(CASES) == set(UNDERLYING)

    @pytest.mark.parametrize("cls", sorted(CASES, key=lambda c: c.__name__))
    def test_every_constructor_parameter_is_exercised(self, cls: type) -> None:
        signature = inspect.signature(cls)
        supported = set(signature.parameters) - LAYOUT_ONLY
        exercised: set[str] = set()
        for case in CASES[cls]:
            bound = signature.bind(*case.args, **case.kwargs)
            exercised |= set(bound.arguments)
        assert supported <= exercised, supported - exercised

    @pytest.mark.parametrize("cls", sorted(CASES, key=lambda c: c.__name__))
    def test_underlying_class_is_the_documented_one(self, cls: type) -> None:
        assert cls.__component__ is UNDERLYING[cls]

    @pytest.mark.parametrize(("cls", "case"), PARAMS)
    def test_serialisation_matches_the_component(self, cls: type, case: Case) -> None:
        item = build(cls, case)
        assert item.to_component_dict() == expected(case).to_dict()

    @pytest.mark.parametrize(("cls", "case"), PARAMS)
    def test_round_trips_through_the_component(self, cls: type, case: Case) -> None:
        item = build(cls, case)
        rebuilt = cls.from_component(expected(case))
        assert rebuilt.to_component_dict() == item.to_component_dict()

    @pytest.mark.parametrize(("cls", "case"), PARAMS)
    def test_every_public_component_attribute_is_reachable(
        self, cls: type, case: Case
    ) -> None:
        item = build(cls, case)
        reference = expected(case)
        for name in sorted(public_attributes(UNDERLYING[cls])):
            mirrored = RENAMED.get((cls, name), name)
            assert hasattr(item, mirrored), f"{cls.__name__}.{mirrored}"
            assert normalise(getattr(item, mirrored)) == normalise(
                getattr(reference, name)
            ), f"{cls.__name__}.{mirrored}"

    @pytest.mark.parametrize(("cls", "case"), PARAMS)
    def test_assignment_reaches_the_component(self, cls: type, case: Case) -> None:
        item = build(cls, case)
        for name, field_ in cls.__fields__.items():
            if field_.readonly:
                with pytest.raises(AttributeError):
                    setattr(item, field_.name, getattr(item, field_.name))
                continue
            setattr(item, field_.name, getattr(item, field_.name))
            assert getattr(item.underlying, name) == getattr(item, field_.name)
