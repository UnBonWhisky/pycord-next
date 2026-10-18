"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz
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

import inspect
from typing import TYPE_CHECKING, cast

from typing_extensions import Self, TypeVar, override

from ..components import Button as ButtonComponent
from ..enums import ButtonStyle, ComponentType
from ..limits import ComponentLimits
from ..partial_emoji import PartialEmoji, _EmojiTag
from ._fields import (
    Field,
    get_row,
    length_limit,
    new_custom_id,
    set_row,
    track_custom_id,
    type_check,
)
from .item import ItemCallbackType, ViewItem, _mark_callback

__all__ = (
    "Button",
    "button",
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..components import Component
    from ..emoji import AppEmoji, GuildEmoji
    from ..types.components import ButtonComponent as ButtonComponentPayload
    from .view import BaseView

V_co = TypeVar("V_co", bound="BaseView", covariant=True, default="BaseView")


def _resolve_emoji(value: object) -> PartialEmoji:
    if isinstance(value, str):
        return PartialEmoji.from_str(value)
    if isinstance(value, _EmojiTag):
        return value._to_partial()
    raise TypeError(
        f"expected str, GuildEmoji, AppEmoji, or PartialEmoji, received {value.__class__} instead"
    )


class Button(ViewItem[V_co]):
    """Represents a UI button.

    .. versionadded:: 2.0

    Parameters
    ----------
    style: :class:`discord.ButtonStyle`
        The style of the button.
    custom_id: Optional[:class:`str`]
        The ID of the button that gets received during an interaction.
        If this button is for a URL, it does not have a custom ID.
    url: Optional[:class:`str`]
        The URL this button sends you to.
    disabled: :class:`bool`
        Whether the button is disabled or not.
    label: Optional[:class:`str`]
        The label of the button, if any. Maximum of 80 chars.
    emoji: Optional[Union[:class:`.PartialEmoji`, :class:`GuildEmoji`, :class:`AppEmoji`, :class:`str`]]
        The emoji of the button, if available.
    sku_id: Optional[Union[:class:`int`]]
        The ID of the SKU this button refers to.
    row: Optional[:class:`int`]
        The relative row this button belongs to. A Discord component can only have 5
        rows. By default, items are arranged automatically into those 5 rows. If you'd
        like to control the relative positioning of the row then passing an index is advised.
        For example, row=1 will show up before row=2. Defaults to ``None``, which is automatic
        ordering. The row number must be between 0 and 4 (i.e. zero indexed).

        .. warning::

            This parameter does not work in :class:`ActionRow`.

    id: Optional[:class:`int`]
        The button's ID.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "style",
        "url",
        "disabled",
        "label",
        "emoji",
        "sku_id",
        "row",
        "custom_id",
        "id",
    )

    __component__ = ButtonComponent
    __component_type__ = ComponentType.button

    if TYPE_CHECKING:

        @property
        def underlying(self) -> ButtonComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    style: Field[ButtonStyle] = Field("The style of the button.")
    custom_id: Field[str | None] = Field(
        """The ID of the button that gets received during an interaction.

        If this button is for a URL, it does not have a custom ID.
        """,
        type_check(str, nullable=True),
        length_limit(ComponentLimits.CUSTOM_ID_MAX),
        on_set=track_custom_id,
    )
    url: Field[str | None] = Field(
        "The URL this button sends you to.", type_check(str, nullable=True)
    )
    disabled: Field[bool] = Field("Whether the button is disabled or not.", coerce=bool)
    label: Field[str | None] = Field(
        "The label of the button, if available.",
        length_limit(ComponentLimits.BUTTON_LABEL_MAX),
        coerce=str,
    )
    emoji: Field[
        PartialEmoji | None, str | GuildEmoji | AppEmoji | PartialEmoji | None
    ] = Field("The emoji of the button, if available.", coerce=_resolve_emoji)
    sku_id: Field[int | None] = Field(
        "The ID of the SKU this button refers to.", type_check(int, nullable=True)
    )

    @property
    def row(self) -> int | None:
        """Gets or sets the row position of this item within its parent view.

        The row position determines the vertical placement of the item in the UI.
        The value must be an integer between 0 and 4 (inclusive), or ``None`` to indicate
        that no specific row is set.
        This attribute is not compatible with :class:`discord.ui.DesignerView`.

        Returns
        -------
        Optional[:class:`int`]
            The row position of the item, or ``None`` if not explicitly set.

        Raises
        ------
        ValueError
            If the row value is not ``None`` and is outside the range [0, 4].
        """
        return get_row(self)

    @row.setter
    def row(self, value: int | None) -> None:
        set_row(self, value)

    def __init__(
        self,
        *,
        style: ButtonStyle = ButtonStyle.secondary,
        label: str | None = None,
        disabled: bool = False,
        custom_id: str | None = None,
        url: str | None = None,
        emoji: str | GuildEmoji | AppEmoji | PartialEmoji | None = None,
        sku_id: int | None = None,
        row: int | None = None,
        id: int | None = None,
    ) -> None:
        self._row: int | None = None
        self._rendered_row: int | None = None
        super().__init__()
        if custom_id is not None and url is not None:
            raise TypeError("cannot mix both url and custom_id with Button")
        if sku_id is not None and url is not None:
            raise TypeError("cannot mix both url and sku_id with Button")
        if custom_id is not None and sku_id is not None:
            raise TypeError("cannot mix both sku_id and custom_id with Button")

        self._provided_custom_id = custom_id is not None
        if url is None and custom_id is None and sku_id is None:
            custom_id = new_custom_id()

        if url is not None:
            style = ButtonStyle.link
        if sku_id is not None:
            style = ButtonStyle.premium

        self.row = row
        self._build_underlying(
            custom_id=custom_id,
            url=url,
            disabled=disabled,
            label=label,
            style=style,
            emoji=emoji,
            sku_id=sku_id,
            id=id,
        )

    @property
    def width(self) -> int:
        """Gets the width of the item in the UI layout.

        The width determines how much horizontal space this item occupies within its row.

        Returns
        -------
        :class:`int`
            The width of the item. Buttons have a width of 1.
        """
        return 1

    @classmethod
    @override
    def from_component(cls, button: ButtonComponent) -> Self:  # pyright: ignore[reportIncompatibleMethodOverride]
        return super().from_component(button)

    @override
    def refresh_component(self, button: ButtonComponent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        super().refresh_component(button)

    @override
    def to_component_dict(self) -> ButtonComponentPayload:
        return cast("ButtonComponentPayload", super().to_component_dict())

    @override
    def is_dispatchable(self) -> bool:
        return (self.custom_id is not None) and (
            bool(self.view._store) if self.view else True
        )

    @override
    def is_storable(self) -> bool:
        return self.is_dispatchable()

    @override
    def is_persistent(self) -> bool:
        if self.style is ButtonStyle.link:
            return self.url is not None
        return super().is_persistent()


def button(
    *,
    label: str | None = None,
    custom_id: str | None = None,
    disabled: bool = False,
    style: ButtonStyle = ButtonStyle.secondary,
    emoji: str | GuildEmoji | AppEmoji | PartialEmoji | None = None,
    row: int | None = None,
    id: int | None = None,
) -> Callable[[ItemCallbackType[Button[V_co]]], Button[V_co]]:
    """A decorator that attaches a button to a component.

    The function being decorated should have three parameters, ``self`` representing
    the :class:`discord.ui.View`, :class:`discord.ui.ActionRow` or :class:`discord.ui.Section`, the :class:`discord.ui.Button` being pressed, and
    the :class:`discord.Interaction` you receive.

    .. note::

        Premium and link buttons cannot be created with this decorator. Consider
        creating a :class:`Button` object manually instead. These types of
        buttons do not have a callback associated since Discord doesn't handle
        them when clicked.

    Parameters
    ----------
    label: Optional[:class:`str`]
        The label of the button, if any.
    custom_id: Optional[:class:`str`]
        The ID of the button that gets received during an interaction.
        It is recommended not to set this parameter to prevent conflicts.
    style: :class:`.ButtonStyle`
        The style of the button. Defaults to :attr:`.ButtonStyle.grey`.
    disabled: :class:`bool`
        Whether the button is disabled or not. Defaults to ``False``.
    emoji: Optional[Union[:class:`str`, :class:`GuildEmoji`, :class:`AppEmoji`, :class:`.PartialEmoji`]]
        The emoji of the button. This can be in string form or a :class:`.PartialEmoji`
        or a full :class:`GuildEmoji` or :class:`AppEmoji`.
    row: Optional[:class:`int`]
        The relative row this button belongs to. A Discord component can only have 5
        rows. By default, items are arranged automatically into those 5 rows. If you'd
        like to control the relative positioning of the row then passing an index is advised.
        For example, row=1 will show up before row=2. Defaults to ``None``, which is automatic
        ordering. The row number must be between 0 and 4 (i.e. zero indexed).

        .. warning::

            This parameter does not work in :class:`ActionRow`.
    """

    def decorator(func: ItemCallbackType) -> ItemCallbackType:
        if not inspect.iscoroutinefunction(func):
            raise TypeError("button function must be a coroutine function")

        _mark_callback(
            func,
            Button,
            {
                "style": style,
                "custom_id": custom_id,
                "url": None,
                "disabled": disabled,
                "label": label,
                "emoji": emoji,
                "row": row,
                "id": id,
            },
        )
        return func

    # lie to the type checkers, because after a View is instated, the button callback is converted into a Button instance
    return cast("Callable[[ItemCallbackType[Button[V_co]]], Button[V_co]]", decorator)
