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
from urllib.parse import urlparse

from typing_extensions import TypeVar, override

from ..components import FileComponent, UnfurledMediaItem
from ..enums import ComponentType
from ._fields import Field
from .item import ViewItem

__all__ = ("File",)

if TYPE_CHECKING:
    from typing_extensions import Self

    from ..components import Component
    from ..types.components import FileComponent as FileComponentPayload
    from .view import DesignerView


V_co = TypeVar("V_co", bound="DesignerView", covariant=True, default="DesignerView")


class File(ViewItem[V_co]):
    """Represents a UI File.

    .. note::
        This component does not show media previews. Use :class:`MediaGallery` for previews instead.

    .. versionadded:: 2.7

    Parameters
    ----------
    url: :class:`str`
        The URL of this file. This must be an ``attachment://`` URL referring to a local file used with :class:`~discord.File`.
    spoiler: Optional[:class:`bool`]
        Whether this file has the spoiler overlay.
    id: Optional[:class:`int`]
        The file component's ID.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "file",
        "spoiler",
        "id",
    )

    __component__ = FileComponent
    __component_type__ = ComponentType.file

    if TYPE_CHECKING:

        @property
        def underlying(self) -> FileComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    file: Field[UnfurledMediaItem] = Field("The file's underlying media item.")
    spoiler: Field[bool] = Field(
        "Whether the file has the spoiler overlay. Defaults to ``False``."
    )
    name: Field[str | None] = Field(
        "The name of this file, if provided by Discord.", readonly=True
    )
    size: Field[int | None] = Field(
        "The size of this file in bytes, if provided by Discord.", readonly=True
    )

    def __init__(
        self, url: str, *, spoiler: bool | None = False, id: int | None = None
    ) -> None:
        super().__init__()

        self._build_underlying(id=id, file=UnfurledMediaItem(url), spoiler=spoiler)

    @property
    def url(self) -> str:
        """The URL of this file's underlying media. This must be an ``attachment://`` URL that references a :class:`~discord.File`."""
        return self.underlying.file and self.underlying.file.url

    @url.setter
    def url(self, value: str) -> None:
        self.underlying.file.url = value

    @override
    def refresh_component(self, component: FileComponent) -> None:
        original = self.underlying.file
        component.file._static_url = original._static_url
        self.underlying = component

    @override
    def to_component_dict(self) -> FileComponentPayload:
        return cast("FileComponentPayload", super().to_component_dict())

    @classmethod
    @override
    def from_component(cls, component: FileComponent) -> Self:
        url = component.file and component.file.url
        if not url.startswith("attachment://"):
            url = "attachment://" + urlparse(url).path.rsplit("/", 1)[-1]
        return cls(
            url,
            spoiler=component.spoiler,
            id=component.id,
        )

    callback = None  # pyright: ignore[reportAssignmentType]
