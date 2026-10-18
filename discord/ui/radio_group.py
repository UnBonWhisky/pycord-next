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

from ..components import RadioGroup as RadioGroupComponent, RadioGroupOption
from ..enums import ComponentType
from ..limits import ComponentLimits
from ..utils import MISSING
from ._fields import (
    Field,
    custom_id_checks,
    list_of,
    new_custom_id,
    type_check,
)
from .item import ModalItem

__all__ = ("RadioGroup",)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from typing_extensions import Self

    from ..components import Component
    from ..interactions import Interaction
    from ..types.components import RadioGroupComponent as RadioGroupComponentPayload


def _check_option_count(_name: str, value: list[RadioGroupOption]) -> None:
    if value and not (
        ComponentLimits.RADIO_OPTIONS_MIN
        <= len(value)
        <= ComponentLimits.RADIO_OPTIONS_MAX
    ):
        raise ValueError(
            f"you must provide between {ComponentLimits.RADIO_OPTIONS_MIN} and {ComponentLimits.RADIO_OPTIONS_MAX} options."
        )


def _check_single_default(_name: str, value: list[RadioGroupOption]) -> None:
    if sum(1 for option in value if option.default) > 1:
        raise ValueError("only 1 option can be set as default.")


class RadioGroup(ModalItem):
    """Represents a UI Radio Group component.

    .. versionadded:: 2.8
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "options",
        "required",
        "custom_id",
        "id",
    )

    __component__ = RadioGroupComponent
    __component_type__ = ComponentType.radio_group

    if TYPE_CHECKING:

        @property
        def underlying(self) -> RadioGroupComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    custom_id: Field[str] = Field(
        "The custom id that gets received during an interaction.",
        *custom_id_checks,
        default=new_custom_id,
    )
    required: Field[bool] = Field(
        "Whether an option selection is required or not. Defaults to ``True``",
        type_check(bool),
    )
    options: Field[list[RadioGroupOption]] = Field(
        "A list of options that can be selected in this group.",
        list_of(RadioGroupOption),
        _check_option_count,
        _check_single_default,
    )

    def __init__(
        self,
        *,
        custom_id: str | None = None,
        options: list[RadioGroupOption] | None = None,
        required: bool = True,
        id: int | None = None,
    ) -> None:
        super().__init__()
        self._selected_value: str | None = None

        self._build_underlying(
            custom_id=custom_id, options=options or [], required=required, id=id
        )

    @property
    def value(self) -> str | None:
        """The value selected by the user. May return ``None`` if this radio group is optional or has not been sent yet."""
        return self._selected_value

    def add_option(
        self,
        *,
        label: str,
        value: str = MISSING,
        description: str | None = None,
        default: bool = False,
    ) -> Self:
        """Adds an option to the radio group.

        To append a pre-existing :class:`discord.RadioGroupOption` use the
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
        option = RadioGroupOption(
            label=label,
            value=value,
            description=description,
            default=default,
        )

        return self.append_option(option)

    def append_option(self, option: RadioGroupOption) -> Self:
        """Appends an option to the radio group.

        Parameters
        ----------
        option: :class:`discord.RadioGroupOption`
            The option to append to the radio group.

        Raises
        ------
        ValueError
            The number of options exceeds 10.
        """
        if len(self.underlying.options) >= ComponentLimits.RADIO_OPTIONS_MAX:
            raise ValueError(
                f"maximum number of options already provided ({ComponentLimits.RADIO_OPTIONS_MAX})"
            )

        self.underlying.options.append(option)
        return self

    def clear_options(self) -> Self:
        """Remove all options from the radio group."""
        self.underlying.options.clear()
        return self

    @override
    def to_component_dict(self) -> RadioGroupComponentPayload:
        return self.underlying.to_dict()

    @override
    def refresh_state(self, data: Mapping[str, Any]) -> None:
        self._selected_value = data.get("value", None)

    @override
    def refresh_from_modal(
        self, interaction: Interaction, data: RadioGroupComponentPayload
    ) -> None:
        return self.refresh_state(data)
