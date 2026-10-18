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

from typing import TYPE_CHECKING, Any

from typing_extensions import override

from ..components import CheckboxGroup as CheckboxGroupComponent, CheckboxGroupOption
from ..enums import ComponentType
from ..limits import ComponentLimits
from ..utils import MISSING
from ._fields import (
    Field,
    count_limit,
    custom_id_checks,
    in_range,
    list_of,
    new_custom_id,
    type_check,
)
from .item import ModalItem

__all__ = ("CheckboxGroup",)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from typing_extensions import Self

    from ..components import Component
    from ..interactions import Interaction
    from ..types.components import (
        CheckboxGroupComponent as CheckboxGroupComponentPayload,
    )


class CheckboxGroup(ModalItem):
    """Represents a UI Checkbox Group component.

    .. versionadded:: 2.8

    Parameters
    ----------
    custom_id: Optional[:class:`str`]
        The ID of the checkbox group that gets received during an interaction.
    options: List[:class:`discord.CheckboxGroupOption`]
        A list of options that can be selected in this group.
    min_values: Optional[:class:`int`]
        The minimum number of options that must be selected.
        Defaults to 0 and must be between 0 and 10, inclusive.
    max_values: Optional[:class:`int`]
        The maximum number of options that can be selected.
        Must be between 1 and 10, inclusive.
    required: :class:`bool`
        Whether an option selection is required or not. Defaults to ``True``.
    id: Optional[:class:`int`]
        The checkbox group's ID.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "options",
        "required",
        "min_values",
        "max_values",
        "custom_id",
        "id",
    )

    __component__ = CheckboxGroupComponent
    __component_type__ = ComponentType.checkbox_group

    if TYPE_CHECKING:

        @property
        def underlying(self) -> CheckboxGroupComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    custom_id: Field[str] = Field(
        "The custom id that gets received during an interaction.",
        *custom_id_checks,
        default=new_custom_id,
    )
    min_values: Field[int | None] = Field(
        "The minimum number of options that must be selected.",
        type_check(int, nullable=True),
        in_range(
            ComponentLimits.CHECKBOX_MIN_VALUES_MIN,
            ComponentLimits.CHECKBOX_MIN_VALUES_MAX,
            skip_falsy=True,
        ),
    )
    max_values: Field[int | None] = Field(
        "The maximum number of options that can be selected.",
        type_check(int, nullable=True),
        in_range(
            ComponentLimits.CHECKBOX_MAX_VALUES_MIN,
            ComponentLimits.CHECKBOX_MAX_VALUES_MAX,
            skip_falsy=True,
        ),
    )
    required: Field[bool] = Field(
        "Whether an option selection is required or not. Defaults to ``True``",
        type_check(bool),
    )
    options: Field[list[CheckboxGroupOption]] = Field(
        "A list of options that can be selected in this group.",
        list_of(CheckboxGroupOption),
        count_limit(ComponentLimits.CHECKBOX_OPTIONS_MAX),
    )

    def __init__(
        self,
        *,
        custom_id: str | None = None,
        options: list[CheckboxGroupOption] | None = None,
        min_values: int | None = None,
        max_values: int | None = None,
        required: bool = True,
        id: int | None = None,
    ) -> None:
        super().__init__()
        self._selected_values: list[str] | None = None

        self._build_underlying(
            custom_id=custom_id,
            options=options or [],
            min_values=min_values,
            max_values=max_values,
            required=required,
            id=id,
        )

    @property
    def values(self) -> list[str] | None:
        """The values selected by the user. This will be ``None`` if the checkbox group has not been submitted in a modal yet."""
        return self._selected_values

    def add_option(
        self,
        *,
        label: str,
        value: str = MISSING,
        description: str | None = None,
        default: bool = False,
    ) -> Self:
        """Adds an option to the checkbox group.

        To append a pre-existing :class:`discord.CheckboxGroupOption` use the
        :meth:`append_option` method instead.

        Parameters
        ----------
        label: :class:`str`
            The label of the option. This is displayed to users.
            Can only be up to 100 characters.
        value: :class:`str`
            The value of the option. This is not displayed to users.
            If not given, defaults to the label. Can only be up to 100 characters.
        description: Optional[:class:`str`]
            An additional description of the option, if any.
            Can only be up to 100 characters.
        default: :class:`bool`
            Whether this option is selected by default.

        Raises
        ------
        ValueError
            The number of options exceeds 10.
        """
        option = CheckboxGroupOption(
            label=label,
            value=value,
            description=description,
            default=default,
        )

        return self.append_option(option)

    def append_option(self, option: CheckboxGroupOption) -> Self:
        """Appends an option to the checkbox group.

        Parameters
        ----------
        option: :class:`discord.CheckboxGroupOption`
            The option to append to the checkbox group.

        Raises
        ------
        ValueError
            The number of options exceeds 10.
        """
        if len(self.underlying.options) >= ComponentLimits.CHECKBOX_OPTIONS_MAX:
            raise ValueError(
                f"maximum number of options already provided ({ComponentLimits.CHECKBOX_OPTIONS_MAX})"
            )

        self.underlying.options.append(option)
        return self

    def clear_options(self) -> Self:
        """Remove all options from the checkbox group."""
        self.underlying.options.clear()
        return self

    @override
    def to_component_dict(self) -> CheckboxGroupComponentPayload:
        return self.underlying.to_dict()

    @override
    def refresh_state(self, data: Mapping[str, Any]) -> None:
        self._selected_values = data.get("values", [])

    @override
    def refresh_from_modal(
        self, interaction: Interaction, data: CheckboxGroupComponentPayload
    ) -> None:
        return self.refresh_state(data)
