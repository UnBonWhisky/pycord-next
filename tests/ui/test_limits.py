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

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

import discord
from discord import ComponentLimits, EmbedLimits, ui
from discord.enums import ComponentType

if TYPE_CHECKING:
    from collections.abc import Callable


def constants(cls: type) -> dict[str, int]:
    return {
        name: value
        for name, value in vars(cls).items()
        if not name.startswith("_") and isinstance(value, int)
    }


COMPONENT_LIMITS = constants(ComponentLimits)
EMBED_LIMITS = constants(EmbedLimits)

DOCUMENTED_COMPONENT_LIMITS = {
    "VIEW_CHILDREN_MAX": 40,
    "LEGACY_VIEW_ROWS_MAX": 5,
    "ACTION_ROW_CHILDREN_MAX": 5,
    "BUTTON_LABEL_MAX": 80,
    "CUSTOM_ID_MAX": 100,
    "SELECT_PLACEHOLDER_MAX": 150,
    "SELECT_OPTIONS_MAX": 25,
    "SELECT_DEFAULT_VALUES_MAX": 25,
    "SELECT_MIN_VALUES_MIN": 0,
    "SELECT_MIN_VALUES_MAX": 25,
    "SELECT_MAX_VALUES_MIN": 1,
    "SELECT_MAX_VALUES_MAX": 25,
    "SELECT_OPTION_LABEL_MAX": 100,
    "SELECT_OPTION_VALUE_MAX": 100,
    "SELECT_OPTION_DESCRIPTION_MAX": 100,
    "SECTION_CHILDREN_MAX": 3,
    "THUMBNAIL_DESCRIPTION_MAX": 1024,
    "MEDIA_GALLERY_ITEM_DESCRIPTION_MAX": 1024,
    "MEDIA_GALLERY_ITEMS_MAX": 10,
    "TEXT_INPUT_LABEL_MAX": 45,
    "TEXT_INPUT_PLACEHOLDER_MAX": 100,
    "TEXT_INPUT_VALUE_MAX": 4000,
    "TEXT_INPUT_MIN_LENGTH_MIN": 0,
    "TEXT_INPUT_MIN_LENGTH_MAX": 4000,
    "TEXT_INPUT_MAX_LENGTH_MIN": 1,
    "TEXT_INPUT_MAX_LENGTH_MAX": 4000,
    "LABEL_TEXT_MAX": 45,
    "LABEL_DESCRIPTION_MAX": 100,
    "RADIO_OPTIONS_MIN": 2,
    "RADIO_OPTIONS_MAX": 10,
    "CHECKBOX_OPTIONS_MAX": 10,
    "CHECKBOX_MIN_VALUES_MIN": 0,
    "CHECKBOX_MIN_VALUES_MAX": 10,
    "CHECKBOX_MAX_VALUES_MIN": 1,
    "CHECKBOX_MAX_VALUES_MAX": 10,
    "FILE_UPLOAD_MIN_VALUES_MIN": 0,
    "FILE_UPLOAD_MIN_VALUES_MAX": 10,
    "FILE_UPLOAD_MAX_VALUES_MIN": 1,
    "FILE_UPLOAD_MAX_VALUES_MAX": 10,
    "MODAL_TITLE_MAX": 45,
    "MODAL_COMPONENTS_MAX": 5,
}

DOCUMENTED_EMBED_LIMITS = {
    "TITLE_MAX": 256,
    "DESCRIPTION_MAX": 4096,
    "FIELDS_MAX": 25,
    "FIELD_NAME_MAX": 256,
    "FIELD_VALUE_MAX": 1024,
    "FOOTER_TEXT_MAX": 2048,
    "AUTHOR_NAME_MAX": 256,
    "TOTAL_MAX": 6000,
}


def text(n: int) -> str:
    return "x" * n


def option(n: int = 1) -> discord.SelectOption:
    return discord.SelectOption(label=text(n), value=text(n))


def radio_options(n: int) -> list[discord.RadioGroupOption]:
    return [discord.RadioGroupOption(label=str(i)) for i in range(n)]


def checkbox_options(n: int) -> list[discord.CheckboxGroupOption]:
    return [discord.CheckboxGroupOption(label=str(i)) for i in range(n)]


def many_texts(owner: Any, n: int) -> None:
    for i in range(n):
        owner.add_item(ui.TextDisplay(str(i)))


def many_buttons(owner: Any, n: int) -> None:
    for i in range(n):
        owner.add_item(ui.Button(label=str(i), custom_id=str(i)))


def legacy_rows(n: int) -> None:
    view = ui.View()
    for row in range(n):
        view.add_item(ui.Button(label=str(row), custom_id=str(row), row=row))


def default_values(n: int) -> None:
    select = ui.Select(ComponentType.user_select, max_values=25)
    for i in range(n):
        select.add_default_value(id=i + 1, type="user")


def media_gallery(n: int) -> None:
    gallery = ui.MediaGallery()
    for i in range(n):
        gallery.add_item(f"https://example.com/{i}.png")


def select_options_setter(n: int) -> None:
    ui.Select(options=[option() for _ in range(n)])


def select_options_append(n: int) -> None:
    select = ui.Select()
    for _ in range(n):
        select.append_option(option())


def radio_options_append(n: int) -> None:
    group = ui.RadioGroup()
    for i in range(n):
        group.add_option(label=str(i))


def checkbox_options_append(n: int) -> None:
    group = ui.CheckboxGroup()
    for i in range(n):
        group.add_option(label=str(i))


CASES: dict[str, tuple[Callable[[int], Any], int | None]] = {
    "VIEW_CHILDREN_MAX": (lambda n: many_texts(ui.DesignerView(), n), None),
    "LEGACY_VIEW_ROWS_MAX": (legacy_rows, None),
    "ACTION_ROW_CHILDREN_MAX": (lambda n: many_buttons(ui.ActionRow(), n), None),
    "BUTTON_LABEL_MAX": (lambda n: ui.Button(label=text(n)), None),
    "CUSTOM_ID_MAX": (lambda n: ui.Button(custom_id=text(n)), None),
    "SELECT_PLACEHOLDER_MAX": (lambda n: ui.Select(placeholder=text(n)), None),
    "SELECT_OPTIONS_MAX": (select_options_setter, None),
    "SELECT_DEFAULT_VALUES_MAX": (default_values, None),
    "SELECT_MIN_VALUES_MIN": (lambda n: ui.Select(min_values=n), None),
    "SELECT_MIN_VALUES_MAX": (lambda n: ui.Select(min_values=n), None),
    "SELECT_MAX_VALUES_MIN": (lambda n: ui.Select(max_values=n), None),
    "SELECT_MAX_VALUES_MAX": (lambda n: ui.Select(max_values=n), None),
    "SELECT_OPTION_LABEL_MAX": (lambda n: discord.SelectOption(label=text(n)), None),
    "SELECT_OPTION_VALUE_MAX": (
        lambda n: discord.SelectOption(label="a", value=text(n)),
        None,
    ),
    "SELECT_OPTION_DESCRIPTION_MAX": (
        lambda n: discord.SelectOption(label="a", description=text(n)),
        None,
    ),
    "SECTION_CHILDREN_MAX": (
        lambda n: many_texts(ui.Section(accessory=ui.Button(custom_id="a")), n),
        None,
    ),
    "THUMBNAIL_DESCRIPTION_MAX": (
        lambda n: ui.Thumbnail("https://example.com/a.png", description=text(n)),
        None,
    ),
    "MEDIA_GALLERY_ITEM_DESCRIPTION_MAX": (
        lambda n: discord.MediaGalleryItem(
            "https://example.com/a.png", description=text(n)
        ),
        None,
    ),
    "MEDIA_GALLERY_ITEMS_MAX": (media_gallery, None),
    "TEXT_INPUT_LABEL_MAX": (lambda n: ui.InputText(label=text(n)), None),
    "TEXT_INPUT_PLACEHOLDER_MAX": (
        lambda n: ui.InputText(label="a", placeholder=text(n)),
        None,
    ),
    "TEXT_INPUT_VALUE_MAX": (lambda n: ui.InputText(label="a", value=text(n)), None),
    "TEXT_INPUT_MIN_LENGTH_MIN": (
        lambda n: ui.InputText(label="a", min_length=n),
        -1,
    ),
    "TEXT_INPUT_MIN_LENGTH_MAX": (
        lambda n: ui.InputText(label="a", min_length=n),
        None,
    ),
    "TEXT_INPUT_MAX_LENGTH_MIN": (
        lambda n: ui.InputText(label="a", max_length=n),
        -1,
    ),
    "TEXT_INPUT_MAX_LENGTH_MAX": (
        lambda n: ui.InputText(label="a", max_length=n),
        None,
    ),
    "LABEL_TEXT_MAX": (lambda n: ui.Label(text(n)), None),
    "LABEL_DESCRIPTION_MAX": (lambda n: ui.Label("a", description=text(n)), None),
    "RADIO_OPTIONS_MIN": (lambda n: ui.RadioGroup(options=radio_options(n)), None),
    "RADIO_OPTIONS_MAX": (lambda n: ui.RadioGroup(options=radio_options(n)), None),
    "CHECKBOX_OPTIONS_MAX": (
        lambda n: ui.CheckboxGroup(options=checkbox_options(n)),
        None,
    ),
    "CHECKBOX_MIN_VALUES_MIN": (lambda n: ui.CheckboxGroup(min_values=n), -1),
    "CHECKBOX_MIN_VALUES_MAX": (lambda n: ui.CheckboxGroup(min_values=n), None),
    "CHECKBOX_MAX_VALUES_MIN": (lambda n: ui.CheckboxGroup(max_values=n), -1),
    "CHECKBOX_MAX_VALUES_MAX": (lambda n: ui.CheckboxGroup(max_values=n), None),
    "FILE_UPLOAD_MIN_VALUES_MIN": (lambda n: ui.FileUpload(min_values=n), -1),
    "FILE_UPLOAD_MIN_VALUES_MAX": (lambda n: ui.FileUpload(min_values=n), None),
    "FILE_UPLOAD_MAX_VALUES_MIN": (lambda n: ui.FileUpload(max_values=n), -1),
    "FILE_UPLOAD_MAX_VALUES_MAX": (lambda n: ui.FileUpload(max_values=n), None),
    "MODAL_TITLE_MAX": (lambda n: ui.Modal(title=text(n)), None),
    "MODAL_COMPONENTS_MAX": (
        lambda n: many_texts(ui.DesignerModal(title="a"), n),
        None,
    ),
}

UPPER_BOUNDS = {name for name in COMPONENT_LIMITS if name.endswith("_MAX")}
LOWER_BOUNDS = set(COMPONENT_LIMITS) - UPPER_BOUNDS


class TestDocumentedValues:
    def test_component_limits_are_the_documented_ones(self) -> None:
        assert COMPONENT_LIMITS == DOCUMENTED_COMPONENT_LIMITS

    def test_embed_limits_are_the_documented_ones(self) -> None:
        assert EMBED_LIMITS == DOCUMENTED_EMBED_LIMITS

    def test_limits_are_exported(self) -> None:
        assert discord.ComponentLimits is ui.ComponentLimits
        assert discord.EmbedLimits is discord.embeds.EmbedLimits

    @pytest.mark.parametrize("name", sorted(COMPONENT_LIMITS))
    def test_ranges_are_consistent(self, name: str) -> None:
        if name.endswith("_MIN"):
            bound = name.removesuffix("_MIN") + "_MAX"
            if bound in COMPONENT_LIMITS:
                assert COMPONENT_LIMITS[name] <= COMPONENT_LIMITS[bound]
        assert COMPONENT_LIMITS[name] >= 0


class TestEnforcement:
    def test_every_constant_has_a_case(self) -> None:
        assert set(CASES) == set(COMPONENT_LIMITS)

    @pytest.mark.parametrize("name", sorted(COMPONENT_LIMITS))
    async def test_limit_is_accepted(self, name: str) -> None:
        build, _ = CASES[name]
        build(COMPONENT_LIMITS[name])

    @pytest.mark.parametrize("name", sorted(COMPONENT_LIMITS))
    async def test_past_the_limit_is_rejected(self, name: str) -> None:
        build, override = CASES[name]
        limit = COMPONENT_LIMITS[name]
        if override is not None:
            beyond = override
        elif name in UPPER_BOUNDS:
            beyond = limit + 1
        else:
            beyond = limit - 1
        with pytest.raises(ValueError):
            build(beyond)

    @pytest.mark.parametrize("name", sorted(COMPONENT_LIMITS))
    async def test_constant_is_used_by_the_library(self, name: str) -> None:
        root = Path(discord.__file__).parent
        used = [
            path
            for path in root.rglob("*.py")
            if path.name != "limits.py"
            and re.search(
                rf"ComponentLimits\.{name}\b", path.read_text(encoding="utf-8")
            )
        ]
        assert used, f"ComponentLimits.{name} is not used anywhere"


class TestSelectOptionLimits:
    async def test_append_option_stops_at_the_limit(self) -> None:
        select_options_append(ComponentLimits.SELECT_OPTIONS_MAX)
        with pytest.raises(ValueError):
            select_options_append(ComponentLimits.SELECT_OPTIONS_MAX + 1)

    async def test_radio_and_checkbox_append_stop_at_the_limit(self) -> None:
        radio_options_append(ComponentLimits.RADIO_OPTIONS_MAX)
        with pytest.raises(ValueError):
            radio_options_append(ComponentLimits.RADIO_OPTIONS_MAX + 1)
        checkbox_options_append(ComponentLimits.CHECKBOX_OPTIONS_MAX)
        with pytest.raises(ValueError):
            checkbox_options_append(ComponentLimits.CHECKBOX_OPTIONS_MAX + 1)

    async def test_option_classes_share_the_limits(self) -> None:
        too_long = text(ComponentLimits.SELECT_OPTION_LABEL_MAX + 1)
        for cls in (
            discord.SelectOption,
            discord.RadioGroupOption,
            discord.CheckboxGroupOption,
        ):
            with pytest.raises(ValueError, match="label"):
                cls(label=too_long)
            with pytest.raises(ValueError, match="value"):
                cls(label="a", value=too_long)
            with pytest.raises(ValueError, match="description"):
                cls(label="a", description=too_long)

    async def test_setters_use_the_same_limits(self) -> None:
        select = ui.Select()
        with pytest.raises(ValueError):
            select.placeholder = text(ComponentLimits.SELECT_PLACEHOLDER_MAX + 1)
        with pytest.raises(ValueError):
            select.custom_id = text(ComponentLimits.CUSTOM_ID_MAX + 1)
        with pytest.raises(ValueError):
            select.min_values = ComponentLimits.SELECT_MIN_VALUES_MAX + 1
        with pytest.raises(ValueError):
            select.max_values = ComponentLimits.SELECT_MAX_VALUES_MIN - 1
        button = ui.Button()
        with pytest.raises(ValueError):
            button.label = text(ComponentLimits.BUTTON_LABEL_MAX + 1)
        with pytest.raises(ValueError):
            button.custom_id = text(ComponentLimits.CUSTOM_ID_MAX + 1)


class TestEmbedLimits:
    @pytest.mark.parametrize("name", sorted(EMBED_LIMITS))
    def test_values_are_positive_integers(self, name: str) -> None:
        assert type(EMBED_LIMITS[name]) is int
        assert EMBED_LIMITS[name] > 0

    def test_total_covers_the_counted_fields(self) -> None:
        embed = discord.Embed(
            title=text(EmbedLimits.TITLE_MAX),
            description=text(EmbedLimits.DESCRIPTION_MAX),
        )
        embed.set_footer(text=text(EmbedLimits.FOOTER_TEXT_MAX))
        embed.set_author(name=text(EmbedLimits.AUTHOR_NAME_MAX))
        for _ in range(EmbedLimits.FIELDS_MAX):
            embed.add_field(
                name=text(EmbedLimits.FIELD_NAME_MAX),
                value=text(EmbedLimits.FIELD_VALUE_MAX),
            )
        assert len(embed.fields) == EmbedLimits.FIELDS_MAX
        assert len(embed) > EmbedLimits.TOTAL_MAX

    def test_len_matches_the_total_definition(self) -> None:
        embed = discord.Embed(title="abc", description="defg")
        embed.add_field(name="n", value="vv")
        embed.set_footer(text="f")
        embed.set_author(name="aa")
        assert len(embed) == 3 + 4 + 1 + 2 + 1 + 2
