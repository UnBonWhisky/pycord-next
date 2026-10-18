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

from ..components import TextDisplay as TextDisplayComponent
from ..enums import ComponentType
from ._fields import Field
from .item import ModalItem, ViewItem

__all__ = ("TextDisplay",)

if TYPE_CHECKING:
    from ..components import Component
    from ..types.components import TextDisplayComponent as TextDisplayComponentPayload
    from .modal import DesignerModal
    from .view import DesignerView


V_co = TypeVar("V_co", bound="DesignerView", covariant=True, default="DesignerView")
M_co = TypeVar("M_co", bound="DesignerModal", covariant=True, default="DesignerModal")


class TextDisplay(ViewItem[V_co], ModalItem[M_co]):
    """Represents a UI text display. A message can have up to 4000 characters across all :class:`TextDisplay` objects combined.

    .. versionadded:: 2.7

    Parameters
    ----------
    content: :class:`str`
        The text display's content, up to 4000 characters.
    id: Optional[:class:`int`]
        The text display's ID.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "content",
        "id",
    )

    __component__ = TextDisplayComponent
    __component_type__ = ComponentType.text_display

    if TYPE_CHECKING:

        @property
        def underlying(self) -> TextDisplayComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    content: Field[str] = Field("The text display's content.")

    def __init__(
        self,
        content: str,
        id: int | None = None,
    ) -> None:
        super().__init__()

        self._build_underlying(id=id, content=content)

    @override
    def to_component_dict(self) -> TextDisplayComponentPayload:
        return cast("TextDisplayComponentPayload", super().to_component_dict())

    def copy_text(self) -> str:
        """Returns the content of this text display. Equivalent to the `Copy Text` option on Discord clients."""
        return self.content

    callback = None  # pyright: ignore[reportAssignmentType]
