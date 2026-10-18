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

import contextlib
from typing import TYPE_CHECKING, cast

from typing_extensions import TypeVar, override

from ..asset import AssetMixin
from ..components import MediaGallery as MediaGalleryComponent, MediaGalleryItem
from ..enums import ComponentType
from ..limits import ComponentLimits
from ._fields import Field, count_limit, list_of
from .item import ViewItem

__all__ = ("MediaGallery",)

if TYPE_CHECKING:
    from typing_extensions import Self

    from ..components import Component
    from ..file import File
    from ..message import Attachment
    from ..types.components import MediaGalleryComponent as MediaGalleryComponentPayload
    from .view import DesignerView


V_co = TypeVar("V_co", bound="DesignerView", covariant=True, default="DesignerView")


class MediaGallery(ViewItem[V_co]):
    """Represents a UI Media Gallery. Galleries may contain up to 10 :class:`MediaGalleryItem` objects.

    .. versionadded:: 2.7

    Parameters
    ----------
    *items: :class:`~discord.MediaGalleryItem`
        The initial items contained in this gallery, up to 10.
    id: Optional[:class:`int`]
        The gallery's ID.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "items",
        "id",
    )

    __component__ = MediaGalleryComponent
    __component_type__ = ComponentType.media_gallery

    if TYPE_CHECKING:

        @property
        def underlying(self) -> MediaGalleryComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    items: Field[list[MediaGalleryItem]] = Field(
        "The list of media items in this gallery.",
        list_of(MediaGalleryItem),
        count_limit(ComponentLimits.MEDIA_GALLERY_ITEMS_MAX),
    )

    def __init__(self, *items: MediaGalleryItem, id: int | None = None) -> None:
        super().__init__()

        self._build_underlying(id=id, items=list(items))

    def append_item(self, item: MediaGalleryItem) -> Self:
        """Adds a :attr:`MediaGalleryItem` to the gallery.

        Parameters
        ----------
        item: :class:`MediaGalleryItem`
            The gallery item to add to the gallery.

        Raises
        ------
        TypeError
            A :class:`MediaGalleryItem` was not passed.
        ValueError
            Maximum number of items has been exceeded (10).
        """
        if len(self.items) >= ComponentLimits.MEDIA_GALLERY_ITEMS_MAX:
            raise ValueError(
                f"maximum number of items exceeded ({ComponentLimits.MEDIA_GALLERY_ITEMS_MAX})"
            )

        if not isinstance(cast("object", item), MediaGalleryItem):
            raise TypeError(f"expected MediaGalleryItem not {item.__class__!r}")

        self.underlying.items.append(item)
        return self

    def add_item(
        self,
        url: str,
        *,
        description: str | None = None,
        spoiler: bool = False,
    ) -> Self:
        """Adds a new media item to the gallery.

        Parameters
        ----------
        url: :class:`str`
            The URL of the media item. This can either be an arbitrary URL or an ``attachment://`` URL.
        description: Optional[:class:`str`]
            The media item's description, up to 1024 characters.
        spoiler: Optional[:class:`bool`]
            Whether the media item has the spoiler overlay.

        Raises
        ------
        ValueError
            Maximum number of items has been exceeded (10).
        """
        item = MediaGalleryItem(url, description=description, spoiler=spoiler)

        return self.append_item(item)

    def remove_item(self, index: int) -> Self:
        """Removes an item from the gallery.

        Parameters
        ----------
        index: :class:`int`
            The index of the item to remove from the gallery.
        """
        with contextlib.suppress(IndexError):
            self.items.pop(index)
        return self

    def replace_item(self, index: int, new_item: MediaGalleryItem) -> Self:
        """Directly replace an item in this gallery by index.

        .. versionadded:: 3.0

        Parameters
        ----------
        index: :class:`int`
            The index of the item to replace in this gallery.
        new_item: :class:`MediaGalleryItem`
            The new item to insert into the gallery.

        Raises
        ------
        TypeError
            A :class:`MediaGalleryItem` was not passed.
        IndexError
            The index is out of range.
        """
        if not isinstance(cast("object", new_item), MediaGalleryItem):
            raise TypeError(f"expected MediaGalleryItem not {new_item.__class__!r}")
        self.items[index] = new_item
        return self

    def _generate_underlying(self) -> MediaGalleryComponent:
        gallery = cast("MediaGalleryComponent", super()._generate_underlying())
        gallery.items = list(self.items)
        return gallery

    @override
    def to_component_dict(self) -> MediaGalleryComponentPayload:
        self._underlying = self._generate_underlying()
        return cast("MediaGalleryComponentPayload", super().to_component_dict())

    @classmethod
    def from_assets(
        cls,
        *assets: Attachment | AssetMixin,
        id: int | None = None,
        new: bool = False,
    ) -> Self:
        r"""Converts a list of :class:`discord.Attachment` or :class:`discord.Asset` to a gallery.

        .. versionadded:: 3.0

        Parameters
        ----------
        \*assets: Union[:class:`discord.Attachment`, :class:`discord.AssetMixin`]
            An argument list of assets to add to the gallery. These can be attachments, emojis, stickers, avatars, or any other model served by Discord.
        id: Optional[:class:`int`]
            The gallery's ID.
        new: :class:`bool`
            If ``True``, uses local ``attachment://`` URLs instead of the CDN URLs. Ideal when reuploading assets.

        Raises
        ------
        ValueError
            More than 10 assets were given.
        """
        gallery = cls(id=id)
        for a in assets:
            if isinstance(a, AssetMixin):
                name = a.cdn_name
                if new and name is None:
                    raise ValueError(f"could not determine a filename for {a!r}.")
                spoiler = False
            else:
                name = a.filename
                spoiler = a.is_spoiler()
            gallery.add_item(
                url=f"attachment://{name}" if new else a.url,
                description=getattr(a, "description", None),
                spoiler=spoiler,
            )
        return gallery

    @classmethod
    def from_files(cls, *files: File, id: int | None = None) -> Self:
        r"""Converts a list of local :class:`discord.File` to a gallery.

        .. versionadded:: 3.0

        Parameters
        ----------
        \*files: :class:`discord.File`
            An argument list of :class:`discord.File` to add to the gallery.
        id: Optional[:class:`int`]
            The gallery's ID.

        Raises
        ------
        ValueError
            More than 10 files were given.
        """
        gallery = cls(id=id)
        for f in files:
            gallery.add_item(
                url=f"attachment://{f.filename}",
                description=f.description,
                spoiler=f.spoiler,
            )
        return gallery

    async def to_files(self) -> list[File]:
        """|coro|

        Converts this gallery to a list of :class:`discord.File` for use with :meth:`abc.Messageable.send`.

        .. versionadded:: 3.0
        """
        return [
            await i.media.to_file(description=i.description, spoiler=bool(i.spoiler))
            for i in self.items
        ]

    @classmethod
    @override
    def from_component(cls, component: MediaGalleryComponent) -> Self:
        return cls(*component.items, id=component.id)

    callback = None  # pyright: ignore[reportAssignmentType]
