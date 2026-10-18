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

from typing import TYPE_CHECKING, Any, Literal, cast

from typing_extensions import override

from ..components import InputText as InputTextComponent
from ..enums import ComponentType, InputTextStyle
from ..limits import ComponentLimits
from ._fields import (
    Field,
    custom_id_checks,
    in_range,
    length_limit,
    new_custom_id,
    type_check,
)
from .item import ModalItem

__all__ = ("InputText", "TextInput")

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ..components import Component
    from ..interactions import Interaction
    from ..types.components import InputText as InputTextComponentPayload


def _submitted_value(item: InputText, value: str | None) -> str | None:
    if item._input_value is not False:
        return item._input_value
    return value


class InputText(ModalItem):
    """Represents a UI text input field.

    .. versionadded:: 2.0

    Parameters
    ----------
    style: :class:`~discord.InputTextStyle`
        The style of the input text field.
    custom_id: Optional[:class:`str`]
        The ID of the input text field that gets received during an interaction.
    label: :class:`str`
        The label for the input text field.
        Must be 45 characters or fewer.
    placeholder: Optional[:class:`str`]
        The placeholder text that is shown if nothing is selected, if any.
        Must be 100 characters or fewer.
    min_length: Optional[:class:`int`]
        The minimum number of characters that must be entered.
        Defaults to 0 and must be less than 4000.
    max_length: Optional[:class:`int`]
        The maximum number of characters that can be entered.
        Must be between 1 and 4000.
    required: Optional[:class:`bool`]
        Whether the input text field is required or not. Defaults to ``True``.
    value: Optional[:class:`str`]
        Pre-fills the input text field with this value.
        Must be 4000 characters or fewer.
    row: Optional[:class:`int`]
        The relative row this input text field belongs to. A modal dialog can only have 5
        rows. By default, items are arranged automatically into those 5 rows. If you'd
        like to control the relative positioning of the row then passing an index is advised.
        For example, row=1 will show up before row=2. Defaults to ``None``, which is automatic
        ordering. The row number must be between 0 and 4 (i.e. zero indexed).
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "label",
        "placeholder",
        "value",
        "required",
        "style",
        "min_length",
        "max_length",
        "custom_id",
        "id",
    )

    __component__ = InputTextComponent
    __component_type__ = ComponentType.input_text

    if TYPE_CHECKING:

        @property
        def underlying(self) -> InputTextComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    style: Field[InputTextStyle] = Field(
        "The style of the input text field.", type_check(InputTextStyle)
    )
    custom_id: Field[str] = Field(
        "The ID of the input text field that gets received during an interaction.",
        *custom_id_checks,
        default=new_custom_id,
    )
    label: Field[str] = Field(
        "The label of the input text field.",
        type_check(str),
        length_limit(ComponentLimits.TEXT_INPUT_LABEL_MAX),
    )
    placeholder: Field[str | None] = Field(
        "The placeholder text that is shown before anything is entered, if any.",
        type_check(str, nullable=True),
        length_limit(ComponentLimits.TEXT_INPUT_PLACEHOLDER_MAX),
    )
    min_length: Field[int | None] = Field(
        "The minimum number of characters that must be entered. Defaults to 0.",
        type_check(int, nullable=True),
        in_range(
            ComponentLimits.TEXT_INPUT_MIN_LENGTH_MIN,
            ComponentLimits.TEXT_INPUT_MIN_LENGTH_MAX,
            skip_falsy=True,
        ),
    )
    max_length: Field[int | None] = Field(
        "The maximum number of characters that can be entered.",
        type_check(int, nullable=True),
        in_range(
            ComponentLimits.TEXT_INPUT_MAX_LENGTH_MIN,
            ComponentLimits.TEXT_INPUT_MAX_LENGTH_MAX,
            skip_falsy=True,
        ),
    )
    required: Field[bool | None] = Field(
        "Whether the input text field is required or not. Defaults to ``True``.",
        type_check(bool),
    )
    value: Field[str | None] = Field(
        "The value entered in the text field.",
        type_check(str, nullable=True),
        length_limit(ComponentLimits.TEXT_INPUT_VALUE_MAX),
        read=_submitted_value,
    )

    def __init__(
        self,
        *,
        style: InputTextStyle = InputTextStyle.short,
        custom_id: str | None = None,
        label: str | None = None,
        placeholder: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        required: bool | None = True,
        value: str | None = None,
        row: int | None = None,
        id: int | None = None,
    ) -> None:
        super().__init__()
        self._input_value: str | Literal[False] | None = False
        self.row = row
        self._rendered_row: int | None = None

        self._build_underlying(
            style=style,
            custom_id=custom_id,
            label=label,
            placeholder=placeholder,
            min_length=min_length,
            max_length=max_length,
            required=required,
            value=value,
            id=id,
        )

    @property
    def width(self) -> int:
        """Gets the width of the item in the UI layout.

        The width determines how much horizontal space this item occupies within its row.

        Returns
        -------
        :class:`int`
            The width of the item.
        """
        return 5

    @override
    def to_component_dict(self) -> InputTextComponentPayload:
        return cast("InputTextComponentPayload", super().to_component_dict())

    @override
    def refresh_state(self, data: Mapping[str, Any]) -> None:
        self._input_value = data.get("value", None)

    @override
    def refresh_from_modal(
        self, interaction: Interaction, data: InputTextComponentPayload
    ) -> None:
        return self.refresh_state(data)


TextInput = InputText
