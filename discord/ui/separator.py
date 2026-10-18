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

from typing import TYPE_CHECKING, cast

from typing_extensions import TypeVar, override

from ..components import Separator as SeparatorComponent
from ..enums import ComponentType, SeparatorSpacingSize
from ._fields import Field
from .item import ViewItem

__all__ = ("Separator",)

if TYPE_CHECKING:
    from ..components import Component
    from ..types.components import SeparatorComponent as SeparatorComponentPayload
    from .view import DesignerView


V_co = TypeVar("V_co", bound="DesignerView", covariant=True, default="DesignerView")


class Separator(ViewItem[V_co]):
    """Represents a UI Separator.

    .. versionadded:: 2.7

    Parameters
    ----------
    divider: :class:`bool`
        Whether the separator is a divider. Defaults to ``True``.
    spacing: :class:`~discord.SeparatorSpacingSize`
        The spacing size of the separator. Defaults to :attr:`~discord.SeparatorSpacingSize.small`.
    id: Optional[:class:`int`]
        The separator's ID.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "divider",
        "spacing",
        "id",
    )

    __component__ = SeparatorComponent
    __component_type__ = ComponentType.separator

    if TYPE_CHECKING:

        @property
        def underlying(self) -> SeparatorComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    divider: Field[bool] = Field(
        "Whether the separator is a divider. Defaults to ``True``."
    )
    spacing: Field[SeparatorSpacingSize] = Field(
        "The spacing size of the separator. Defaults to :attr:`~discord.SeparatorSpacingSize.small`."
    )

    def __init__(
        self,
        *,
        divider: bool = True,
        spacing: SeparatorSpacingSize = SeparatorSpacingSize.small,
        id: int | None = None,
    ) -> None:
        super().__init__()

        self._build_underlying(id=id, divider=divider, spacing=spacing)

    @override
    def to_component_dict(self) -> SeparatorComponentPayload:
        return cast("SeparatorComponentPayload", super().to_component_dict())

    callback = None  # pyright: ignore[reportAssignmentType]
