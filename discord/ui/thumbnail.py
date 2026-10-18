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

from ..components import Thumbnail as ThumbnailComponent, UnfurledMediaItem
from ..enums import ComponentType
from ..limits import ComponentLimits
from ._fields import Field, length_limit
from .item import ViewItem

__all__ = ("Thumbnail",)

if TYPE_CHECKING:
    from typing_extensions import Self

    from ..components import Component
    from ..types.components import ThumbnailComponent as ThumbnailComponentPayload
    from .view import DesignerView


V_co = TypeVar("V_co", bound="DesignerView", covariant=True, default="DesignerView")


class Thumbnail(ViewItem[V_co]):
    """Represents a UI Thumbnail.

    .. versionadded:: 2.7

    Parameters
    ----------
    url: :class:`str`
        The url of the thumbnail. This can either be an arbitrary URL or an ``attachment://`` URL to work with local files.
    description: Optional[:class:`str`]
        The thumbnail's description, up to 1024 characters.
    spoiler: Optional[:class:`bool`]
        Whether the thumbnail has the spoiler overlay. Defaults to ``False``.
    id: Optional[:class:`int`]
        The thumbnail's ID.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "url",
        "description",
        "spoiler",
        "id",
    )

    __component__ = ThumbnailComponent
    __component_type__ = ComponentType.thumbnail

    if TYPE_CHECKING:

        @property
        def underlying(self) -> ThumbnailComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    media: Field[UnfurledMediaItem] = Field("The thumbnail's underlying media item.")
    description: Field[str | None] = Field(
        "The thumbnail's description, up to 1024 characters.",
        length_limit(ComponentLimits.THUMBNAIL_DESCRIPTION_MAX),
    )
    spoiler: Field[bool] = Field(
        "Whether the thumbnail has the spoiler overlay. Defaults to ``False``."
    )

    def __init__(
        self,
        url: str,
        *,
        description: str | None = None,
        spoiler: bool | None = False,
        id: int | None = None,
    ) -> None:
        super().__init__()

        self._build_underlying(
            id=id,
            media=UnfurledMediaItem(url),
            description=description,
            spoiler=spoiler,
        )

    @property
    def url(self) -> str:
        """The URL of this thumbnail's media. This can either be an arbitrary URL or an ``attachment://`` URL."""
        return self.underlying.media and self.underlying.media.url

    @url.setter
    def url(self, value: str) -> None:
        self.underlying.media.url = value

    @override
    def to_component_dict(self) -> ThumbnailComponentPayload:
        return cast("ThumbnailComponentPayload", super().to_component_dict())

    @classmethod
    @override
    def from_component(cls, component: ThumbnailComponent) -> Self:
        return cls(
            component.media and component.media.url,
            description=component.description,
            spoiler=component.spoiler,
            id=component.id,
        )

    callback = None  # pyright: ignore[reportAssignmentType]
