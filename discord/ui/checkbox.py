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

from ..components import Checkbox as CheckboxComponent
from ..enums import ComponentType
from ._fields import Field, custom_id_checks, new_custom_id, type_check
from .item import ModalItem

__all__ = ("Checkbox",)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ..components import Component
    from ..interactions import Interaction
    from ..types.components import CheckboxComponent as CheckboxComponentPayload


class Checkbox(ModalItem):
    """Represents a UI Checkbox component.

    .. versionadded:: 2.8

    Parameters
    ----------
    custom_id: Optional[:class:`str`]
        The ID of the checkbox that gets received during an interaction.
    default: :class:`bool`
        Whether this checkbox is selected by default or not. Defaults to ``False``.
    id: Optional[:class:`int`]
        The checkbox's ID.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "default",
        "custom_id",
        "id",
    )

    __component__ = CheckboxComponent
    __component_type__ = ComponentType.checkbox

    if TYPE_CHECKING:

        @property
        def underlying(self) -> CheckboxComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    custom_id: Field[str] = Field(
        "The custom id that gets received during an interaction.",
        *custom_id_checks,
        default=new_custom_id,
    )
    default: Field[bool] = Field(
        "Whether this checkbox is selected by default or not. Defaults to ``False``",
        type_check(bool),
    )

    def __init__(
        self,
        *,
        custom_id: str | None = None,
        default: bool | None = False,
        id: int | None = None,
    ) -> None:
        super().__init__()
        self._value: bool | None = None

        self._build_underlying(custom_id=custom_id, default=default, id=id)

    @property
    def value(self) -> bool | None:
        """Whether this checkbox was selected or not by the user. This will be ``None`` if the checkbox has not been submitted via a modal yet."""
        return self._value

    @override
    def to_component_dict(self) -> CheckboxComponentPayload:
        return self.underlying.to_dict()

    @override
    def refresh_state(self, data: Mapping[str, Any]) -> None:
        self._value = data.get("value", None)

    @override
    def refresh_from_modal(
        self, interaction: Interaction, data: CheckboxComponentPayload
    ) -> None:
        return self.refresh_state(data)
