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

from typing import TYPE_CHECKING, Any, ClassVar, cast

from typing_extensions import TypeVar, override

from ..components import Section as SectionComponent
from ..enums import ButtonStyle, ComponentType
from ..limits import ComponentLimits
from .button import Button
from .core import _insertion_index, _item_getter, _validate_position
from .item import ItemCallbackType, ViewItem, _callback_item, _set_disabled
from .text_display import TextDisplay
from .thumbnail import Thumbnail

__all__ = ("Section",)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from typing_extensions import Self

    from ..components import Component
    from ..emoji import AppEmoji, GuildEmoji
    from ..partial_emoji import PartialEmoji
    from ..types.components import SectionComponent as SectionComponentPayload
    from .view import DesignerView


V_co = TypeVar("V_co", bound="DesignerView", covariant=True, default="DesignerView")


class Section(ViewItem[V_co]):
    """Represents a UI section. Sections must have 1-3 (inclusive) items and an accessory set.

    .. versionadded:: 2.7

    .. container:: operations

        .. describe:: len(x)

            Returns the total count of all items in this section.
            This includes the section itself, counting towards Discord's component limits.

    Parameters
    ----------
    *items: :class:`ViewItem`
        The initial items contained in this section, up to 3.
        Currently only supports :class:`~discord.ui.TextDisplay`.
        Sections must have at least 1 item before being sent.
    accessory: Optional[:class:`ViewItem`]
        The section's accessory. This is displayed in the top right of the section.
        Currently only supports :class:`~discord.ui.Button` and :class:`~discord.ui.Thumbnail`.
        Sections must have an accessory attached before being sent.
    id: Optional[:class:`int`]
        The section's ID.

    Attributes
    ----------
    items: List[:class:`ViewItem`]
        The list of items in this section.
    accessory: :class:`ViewItem`
        The section's accessory, displayed in the top right of the section.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "items",
        "accessory",
        "id",
    )

    __component__ = SectionComponent
    __component_type__ = ComponentType.section

    if TYPE_CHECKING:

        @property
        def underlying(self) -> SectionComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    __section_accessory_item__: ClassVar[list[ItemCallbackType[ViewItem]]] = []

    def __init_subclass__(cls) -> None:
        accessory: list[ItemCallbackType[ViewItem]] = []
        for base in reversed(cls.__mro__):
            accessory.extend(
                member
                for member in base.__dict__.values()
                if hasattr(member, "__discord_ui_model_type__")
            )

        cls.__section_accessory_item__ = accessory

    def __init__(
        self,
        *items: ViewItem,
        accessory: ViewItem | None = None,
        id: int | None = None,
    ) -> None:
        super().__init__()

        self.items: list[ViewItem] = []
        self.accessory: ViewItem | None = None

        self._build_underlying(id=id, components=[], accessory=None)
        for func in self.__section_accessory_item__:
            item: ViewItem = _callback_item(self, func)
            self.set_accessory(item)
            setattr(self, func.__name__, item)
        if accessory:
            self.set_accessory(accessory)
        for i in items:
            self.add_item(i)

    def __len__(self) -> int:
        total = sum(len(i) for i in self.items) + 1
        return total + 1 if self.accessory else total

    def _add_component_from_item(self, item: ViewItem) -> None:
        self.underlying.components.append(item.underlying)

    def _set_components(self, items: list[ViewItem]) -> None:
        self.underlying.components.clear()
        for item in items:
            self._add_component_from_item(item)

    def _generate_underlying(self) -> SectionComponent:
        section = cast("SectionComponent", super()._generate_underlying())
        section.components = [i._generate_underlying() for i in self.items]
        section.accessory = (
            self.accessory._generate_underlying() if self.accessory else None
        )
        return section

    def add_item(
        self,
        item: ViewItem,
        *,
        index: int | None = None,
        before: ViewItem[V_co] | str | int | None = None,
        after: ViewItem[V_co] | str | int | None = None,
    ) -> Self:
        """Adds an item to the section.

        .. versionchanged:: 3.0
            Added the ``index``, ``before`` and ``after`` parameters.

        Parameters
        ----------
        item: :class:`ViewItem`
            The item to add to the section.
        index: Optional[:class:`int`]
            Add the new item at the specific index of :attr:`items`. Same behavior as Python's :func:`~list.insert`.
        before: Optional[Union[:class:`ViewItem`, :class:`int`, :class:`str`]]
            Add the new item **before** the specified item. If an :class:`int` is provided, the item will be detected by ``id``, otherwise by ``custom_id``.
        after: Optional[Union[:class:`ViewItem`, :class:`int`, :class:`str`]]
            Add the new item **after** the specified item. If an :class:`int` is provided, the item will be detected by ``id``, otherwise by ``custom_id``.

        Raises
        ------
        TypeError
            An :class:`ViewItem` was not passed.
        ValueError
            More than one of ``index``, ``before`` and ``after`` was given,
            the maximum number of items has been exceeded (3),
            or a searched item could not be found in the section.
        """
        _validate_position(index, before, after)

        if len(self.items) >= ComponentLimits.SECTION_CHILDREN_MAX:
            raise ValueError(
                f"maximum number of children exceeded ({ComponentLimits.SECTION_CHILDREN_MAX})"
            )

        if not isinstance(cast("object", item), ViewItem):
            raise TypeError(f"expected ViewItem not {item.__class__!r}")

        position = _insertion_index(
            self, self.items, index, before, after, "the section"
        )

        item.parent = self
        if position is None:
            self.items.append(item)
            self._add_component_from_item(item)
        else:
            self.items.insert(position, item)
            self._underlying = self._generate_underlying()
        return self

    def remove_item(self, item: ViewItem | str | int) -> Self:
        """Removes an item from the section. If an :class:`int` or :class:`str` is passed, the item will be removed by Item ``id`` or ``custom_id`` respectively.

        Parameters
        ----------
        item: Union[:class:`ViewItem`, :class:`int`, :class:`str`]
            The item, item ``id``, or item ``custom_id`` to remove from the section.
        """
        if isinstance(item, (str, int)):
            found = self.get_item(item)
            if found is None:
                return self
            item = found
        try:
            if item is self.accessory:
                self.accessory = None
            else:
                self.items.remove(item)
            item.parent = None
        except ValueError:
            pass
        return self

    def replace_item(
        self, original_item: ViewItem | str | int, new_item: ViewItem
    ) -> Self:
        """Directly replace an item in this section, including its :attr:`accessory`.

        If an :class:`int` is provided, the item will be replaced by ``id``, otherwise by ``custom_id``.

        .. versionadded:: 3.0

        Parameters
        ----------
        original_item: Union[:class:`ViewItem`, :class:`int`, :class:`str`]
            The item, item ``id``, or item ``custom_id`` to replace in the section.
        new_item: :class:`ViewItem`
            The new item to insert into the section.

        Raises
        ------
        TypeError
            The new item is not a :class:`ViewItem`.
        ValueError
            The original item could not be found in the section.
        """
        if not isinstance(cast("object", new_item), ViewItem):
            raise TypeError(
                f"expected new_item to be ViewItem, not {new_item.__class__!r}"
            )

        if isinstance(original_item, (str, int)):
            found = self.get_item(original_item)
            if found is None:
                raise ValueError(f"Could not find {original_item!r} in the section.")
            original_item = found
        if original_item is self.accessory:
            self.accessory = new_item
        else:
            try:
                i = self.items.index(original_item)
            except ValueError:
                raise ValueError(
                    f"Could not find {original_item!r} in the section."
                ) from None
            self.items[i] = new_item
        original_item.parent = None
        new_item.parent = self
        self._underlying = self._generate_underlying()
        return self

    def get_item(self, id: int | str | None = None, **attrs: Any) -> ViewItem | None:
        r"""Get an item from this section, including its :attr:`accessory`. Alias for `utils.get(section.walk_items(), ...)`.

        If an ``int`` is provided, it will be retrieved by ``id``, otherwise it will check the ``custom_id``.
        If ``attrs`` are provided, they are all checked (logical AND) as done in :func:`~discord.utils.get`.
        To have a nested attribute search (i.e. search by ``x.y``) then pass in ``x__y`` as the keyword argument.

        .. versionchanged:: 3.0
            Added support for ``attrs``.

        Parameters
        ----------
        id: Optional[Union[:class:`str`, :class:`int`]]
            The id or custom_id of the item to get.
        \*\*attrs
            Keyword arguments that denote attributes to search with.

        Returns
        -------
        Optional[:class:`ViewItem`]
            The item with the matching ``id``, ``custom_id`` or ``attrs`` if it exists.
        """
        if id:
            attr = "id" if isinstance(id, int) else "custom_id"
            attrs[attr] = id
        return cast("ViewItem | None", _item_getter(self.walk_items(), **attrs))

    def add_text(self, content: str, *, id: int | None = None) -> Self:
        """Adds a :class:`TextDisplay` to the section.

        Parameters
        ----------
        content: :class:`str`
            The content of the text display.
        id: Optional[:class:`int`]
            The text display's ID.

        Raises
        ------
        ValueError
            Maximum number of items has been exceeded (3).
        """
        if len(self.items) >= ComponentLimits.SECTION_CHILDREN_MAX:
            raise ValueError(
                f"maximum number of children exceeded ({ComponentLimits.SECTION_CHILDREN_MAX})"
            )

        text = TextDisplay(content, id=id)

        return self.add_item(text)

    def set_accessory(self, item: ViewItem) -> Self:
        """Set an item as the section's :attr:`accessory`.

        Parameters
        ----------
        item: :class:`ViewItem`
            The item to set as accessory.
            Currently only supports :class:`~discord.ui.Button` and :class:`~discord.ui.Thumbnail`.

        Raises
        ------
        TypeError
            An :class:`ViewItem` was not passed.
        """
        if not isinstance(cast("object", item), ViewItem):
            raise TypeError(f"expected ViewItem not {item.__class__!r}")

        item.parent = self

        self.accessory = item
        self.underlying.accessory = item._generate_underlying()
        return self

    def set_thumbnail(
        self,
        url: str,
        *,
        description: str | None = None,
        spoiler: bool = False,
        id: int | None = None,
    ) -> Self:
        """Sets a :class:`Thumbnail` with the provided URL as the section's :attr:`accessory`.

        Parameters
        ----------
        url: :class:`str`
            The url of the thumbnail.
        description: Optional[:class:`str`]
            The thumbnail's description, up to 1024 characters.
        spoiler: Optional[:class:`bool`]
            Whether the thumbnail has the spoiler overlay. Defaults to ``False``.
        id: Optional[:class:`int`]
            The thumbnail's ID.
        """
        thumbnail = Thumbnail(url, description=description, spoiler=spoiler, id=id)

        return self.set_accessory(thumbnail)

    def set_button(
        self,
        *,
        style: ButtonStyle = ButtonStyle.secondary,
        label: str | None = None,
        disabled: bool = False,
        custom_id: str | None = None,
        url: str | None = None,
        emoji: str | GuildEmoji | AppEmoji | PartialEmoji | None = None,
        sku_id: int | None = None,
        id: int | None = None,
    ) -> Self:
        """Sets a :class:`Button` as the section's :attr:`accessory`.

        .. versionadded:: 3.0

        Parameters
        ----------
        style: :class:`discord.ButtonStyle`
            The style of the button.
        custom_id: Optional[:class:`str`]
            The custom ID of the button that gets received during an interaction.
            If this button is for a URL, it does not have a custom ID.
        url: Optional[:class:`str`]
            The URL this button sends you to.
        disabled: :class:`bool`
            Whether the button is disabled or not.
        label: Optional[:class:`str`]
            The label of the button, if any. Maximum of 80 chars.
        emoji: Optional[Union[:class:`.PartialEmoji`, :class:`GuildEmoji`, :class:`AppEmoji`, :class:`str`]]
            The emoji of the button, if any.
        sku_id: Optional[:class:`int`]
            The ID of the SKU this button refers to.
        id: Optional[:class:`int`]
            The button's ID.
        """
        button = Button(
            style=style,
            label=label,
            disabled=disabled,
            custom_id=custom_id,
            url=url,
            emoji=emoji,
            sku_id=sku_id,
            id=id,
        )

        return self.set_accessory(button)

    def copy_text(self) -> str:
        """Returns the text of all :class:`~discord.ui.TextDisplay` items in this section.

        Equivalent to the `Copy Text` option on Discord clients.
        """
        return "\n".join(t for i in self.items if (t := i.copy_text()))

    @override
    def is_dispatchable(self) -> bool:
        return bool(self.accessory and self.accessory.is_dispatchable())

    @override
    def is_persistent(self) -> bool:
        if not isinstance(self.accessory, Button):
            return True
        return self.accessory.is_persistent()

    @override
    def refresh_component(self, component: SectionComponent) -> None:
        self.underlying = component
        for x, y in zip(self.items, component.components, strict=False):
            x.refresh_component(y)
        if self.accessory and component.accessory:
            self.accessory.refresh_component(component.accessory)

    def disable_all_items(self, *, exclusions: list[ViewItem] | None = None) -> Self:
        """Disables all buttons and select menus in the section.

        At the moment, this only disables :attr:`accessory` if it is a button.

        Parameters
        ----------
        exclusions: Optional[List[:class:`ViewItem`]]
            A list of items in `self.items` to not disable from the view.
        """
        for item in self.walk_items():
            if hasattr(item, "disabled") and (
                exclusions is None or item not in exclusions
            ):
                _set_disabled(item, True)
        return self

    def enable_all_items(self, *, exclusions: list[ViewItem] | None = None) -> Self:
        """Enables all buttons and select menus in the section.

        At the moment, this only enables :attr:`accessory` if it is a button.

        Parameters
        ----------
        exclusions: Optional[List[:class:`ViewItem`]]
            A list of items in `self.items` to not enable from the view.
        """
        for item in self.walk_items():
            if hasattr(item, "disabled") and (
                exclusions is None or item not in exclusions
            ):
                _set_disabled(item, False)
        return self

    def walk_items(self) -> Iterator[ViewItem]:
        """Iterates over the items of this section, its accessory included."""
        r = self.items
        if self.accessory:
            yield from [*r, self.accessory]
        else:
            yield from r

    @override
    def to_component_dict(self) -> SectionComponentPayload:
        self._underlying = self._generate_underlying()
        return cast("SectionComponentPayload", super().to_component_dict())

    @classmethod
    @override
    def from_component(cls, component: SectionComponent) -> Self:
        from .view import _component_to_item

        items = [_component_to_item(c) for c in component.components]
        accessory = (
            _component_to_item(component.accessory) if component.accessory else None
        )
        return cls(*items, accessory=accessory, id=component.id)

    callback = None  # pyright: ignore[reportAssignmentType]
