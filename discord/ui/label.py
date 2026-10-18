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

from typing import TYPE_CHECKING, Any, Literal, cast, overload

from typing_extensions import TypeVar, override

from ..components import (
    CheckboxGroupOption,
    Label as LabelComponent,
    RadioGroupOption,
    SelectDefaultValue,
    SelectOption,
)
from ..enums import ChannelType, ComponentType, InputTextStyle
from ..limits import ComponentLimits
from ._fields import Field, length_limit
from .checkbox import Checkbox
from .checkbox_group import CheckboxGroup
from .core import _item_getter
from .file_upload import FileUpload
from .input_text import InputText
from .item import ModalItem
from .radio_group import RadioGroup
from .select import Select

__all__ = ("Label",)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from typing_extensions import Self

    from ..components import Component
    from ..interactions import Interaction
    from ..types.components import LabelComponent as LabelComponentPayload
    from .modal import DesignerModal


M_co = TypeVar("M_co", bound="DesignerModal", covariant=True, default="DesignerModal")


class Label(ModalItem[M_co]):
    """Represents a UI Label used in :class:`discord.ui.DesignerModal`.

    The items currently supported are as follows:

    - :class:`discord.ui.Select`
    - :class:`discord.ui.InputText`
    - :class:`discord.ui.FileUpload`
    - :class:`discord.ui.RadioGroup`
    - :class:`discord.ui.CheckboxGroup`
    - :class:`discord.ui.Checkbox`

    .. versionadded:: 2.7

    .. container:: operations

        .. describe:: len(x)

            Returns the total count of items in this label, including the label itself.

    Parameters
    ----------
    label: :class:`str`
        The label text. Must be 45 characters or fewer.
    item: :class:`ModalItem`
        The initial item attached to this label.
    description: Optional[:class:`str`]
        The description for this label. Must be 100 characters or fewer.
    id: Optional[:class:`int`]
        The label's ID.

    Attributes
    ----------
    item: :class:`ViewItem`
        The label's attached item.
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "item",
        "id",
        "label",
        "description",
    )

    __component__ = LabelComponent
    __component_type__ = ComponentType.label

    if TYPE_CHECKING:

        @property
        def underlying(self) -> LabelComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    label: Field[str] = Field(
        "The label text. Must be 45 characters or fewer.",
        length_limit(ComponentLimits.LABEL_TEXT_MAX),
    )
    description: Field[str | None] = Field(
        "The description for this label. Must be 100 characters or fewer.",
        length_limit(ComponentLimits.LABEL_DESCRIPTION_MAX),
    )

    def __init__(
        self,
        label: str,
        item: ModalItem | None = None,
        *,
        description: str | None = None,
        id: int | None = None,
    ) -> None:
        super().__init__()

        self.item: ModalItem | None = None

        self._build_underlying(
            id=id, label=label, description=description, component=None
        )

        if item:
            self.set_item(item)

    def __len__(self) -> int:
        return 2 if self.item else 1

    @property
    def modal(self) -> M_co | None:
        """Gets the parent modal associated with this label.

        Setting it also sets the modal of the attached item.

        Returns
        -------
        Optional[:class:`BaseModal`]
            The parent modal of this label, or ``None`` if the label is not attached to any modal.
        """
        return self._modal

    @modal.setter
    def modal(self, value: M_co | None) -> None:
        self._modal = value
        if self.item:
            self.item.modal = value

    def _set_component_from_item(self, item: ModalItem) -> None:
        self.underlying.component = item._generate_underlying()

    def _generate_underlying(self) -> LabelComponent:
        label = cast("LabelComponent", super()._generate_underlying())
        label.component = self.item._generate_underlying() if self.item else None
        return label

    def set_item(self, item: ModalItem) -> Self:
        """Set this label's item.

        Parameters
        ----------
        item: Union[:class:`ModalItem`]
            The item to set.

        Raises
        ------
        TypeError
            A :class:`ModalItem` was not passed.
        """
        if not isinstance(cast("object", item), ModalItem):
            raise TypeError(f"expected ModalItem not {item.__class__!r}")
        if isinstance(item, InputText) and item.label:
            raise ValueError("InputText.label cannot be set inside Label")
        if self.modal:
            item.modal = self.modal
        item.parent = self

        self.item = item
        self._set_component_from_item(item)
        return self

    def get_item(self, id: str | int | None = None, **attrs: Any) -> ModalItem | None:
        r"""Get the item from this label if it matches the provided id or attributes.

        If an ``int`` is provided, the item will match by ``id``, otherwise by ``custom_id``.
        If ``attrs`` are provided, they are all checked (logical AND) as done in :func:`~discord.utils.get`.

        .. versionchanged:: 3.0
            Added support for ``attrs``.

        Parameters
        ----------
        id: Optional[Union[:class:`str`, :class:`int`]]
            The id or custom_id of the item to match.
        \*\*attrs
            Keyword arguments that denote attributes to search with.

        Returns
        -------
        Optional[:class:`ModalItem`]
            The item if it matches.
        """
        if self.item is None:
            return None
        if id:
            attr = "id" if isinstance(id, int) else "custom_id"
            attrs[attr] = id
        return cast("ModalItem | None", _item_getter([self.item], **attrs))

    def set_input_text(
        self,
        *,
        style: InputTextStyle = InputTextStyle.short,
        custom_id: str | None = None,
        placeholder: str | None = None,
        min_length: int | None = None,
        max_length: int | None = None,
        required: bool | None = True,
        value: str | None = None,
        id: int | None = None,
    ) -> Self:
        """Set this label's item to an input text.

        To set a pre-existing :class:`InputText`, use the
        :meth:`set_item` method, instead.

        Parameters
        ----------
        style: :class:`~discord.InputTextStyle`
            The style of the input text field.
        custom_id: Optional[:class:`str`]
            The ID of the input text field that gets received during an interaction.
        placeholder: Optional[:class:`str`]
            The placeholder text that is shown if nothing is selected, if any.
            Must be 100 characters or fewer.
        min_length: Optional[:class:`int`]
            The minimum number of characters that must be entered.
            Defaults to 0 and must be less than 4000.
        max_length: Optional[:class:`int`]
            The maximum number of characters that can be entered.
            Must be between 1 and 4000.
        required: Optional[:class:`bool`]
            Whether the input text field is required or not. Defaults to ``True``.
        value: Optional[:class:`str`]
            Pre-fills the input text field with this value.
            Must be 4000 characters or fewer.
        id: Optional[:class:`int`]
            The button's ID.
        """
        text = InputText(
            style=style,
            custom_id=custom_id,
            placeholder=placeholder,
            min_length=min_length,
            max_length=max_length,
            required=required,
            value=value,
            id=id,
        )

        return self.set_item(text)

    @overload
    def set_select(
        self,
        select_type: Literal[ComponentType.string_select] = ...,
        *,
        custom_id: str | None = ...,
        placeholder: str | None = ...,
        min_values: int = ...,
        max_values: int = ...,
        options: list[SelectOption] | None = ...,
        required: bool = ...,
        id: int | None = ...,
    ) -> Self: ...

    @overload
    def set_select(
        self,
        select_type: Literal[ComponentType.channel_select] = ...,
        *,
        custom_id: str | None = ...,
        placeholder: str | None = ...,
        min_values: int = ...,
        max_values: int = ...,
        channel_types: list[ChannelType] | None = ...,
        required: bool = ...,
        id: int | None = ...,
        default_values: Sequence[SelectDefaultValue] | None = ...,
    ) -> Self: ...

    @overload
    def set_select(
        self,
        select_type: Literal[
            ComponentType.user_select,
            ComponentType.role_select,
            ComponentType.mentionable_select,
        ] = ...,
        *,
        custom_id: str | None = ...,
        placeholder: str | None = ...,
        min_values: int = ...,
        max_values: int = ...,
        required: bool = ...,
        id: int | None = ...,
        default_values: Sequence[SelectDefaultValue] | None = ...,
    ) -> Self: ...

    def set_select(
        self,
        select_type: ComponentType = ComponentType.string_select,
        *,
        custom_id: str | None = None,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        options: list[SelectOption] | None = None,
        channel_types: list[ChannelType] | None = None,
        required: bool = True,
        id: int | None = None,
        default_values: Sequence[SelectDefaultValue] | None = None,
    ) -> Self:
        """Set this label's item to a select menu.

        Parameters
        ----------
        select_type: :class:`discord.ComponentType`
            The type of select to create. Must be one of
            :attr:`discord.ComponentType.string_select`, :attr:`discord.ComponentType.user_select`,
            :attr:`discord.ComponentType.role_select`, :attr:`discord.ComponentType.mentionable_select`,
            or :attr:`discord.ComponentType.channel_select`.
        custom_id: :class:`str`
            The custom ID of the select menu that gets received during an interaction.
            If not given then one is generated for you.
        placeholder: Optional[:class:`str`]
            The placeholder text that is shown if nothing is selected, if any.
        min_values: :class:`int`
            The minimum number of items that must be chosen for this select menu.
            Defaults to 1 and must be between 1 and 25.
        max_values: :class:`int`
            The maximum number of items that must be chosen for this select menu.
            Defaults to 1 and must be between 1 and 25.
        options: List[:class:`discord.SelectOption`]
            A list of options that can be selected in this menu.
            Only valid for selects of type :attr:`discord.ComponentType.string_select`.
        channel_types: List[:class:`discord.ChannelType`]
            A list of channel types that can be selected in this menu.
            Only valid for selects of type :attr:`discord.ComponentType.channel_select`.
        required: :class:`bool`
            Whether the select is required or not. Defaults to ``True``.
        id: Optional[:class:`int`]
            The select menu's ID.
        default_values: Optional[Sequence[Union[:class:`discord.SelectDefaultValue`, :class:`discord.abc.Snowflake`]]]
            The default values of this select. Only applicable if :attr:`.select_type` is not :attr:`discord.ComponentType.string_select`.

            These can be either :class:`discord.SelectDefaultValue` instances or models, which will be converted into :class:`discord.SelectDefaultValue`
            instances.
        """
        select = Select(
            select_type=select_type,
            custom_id=custom_id,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            options=options or [],
            channel_types=channel_types or [],
            required=required,
            id=id,
            default_values=default_values,
        )

        return self.set_item(select)

    def set_file_upload(
        self,
        *,
        custom_id: str | None = None,
        min_values: int | None = None,
        max_values: int | None = None,
        required: bool = True,
        id: int | None = None,
    ) -> Self:
        """Set this label's item to a file upload.

        To set a pre-existing :class:`FileUpload`, use the
        :meth:`set_item` method, instead.

        Parameters
        ----------
        custom_id: Optional[:class:`str`]
            The ID of the input text field that gets received during an interaction.
        min_values: Optional[:class:`int`]
            The minimum number of files that must be uploaded.
            Defaults to 0 and must be between 0 and 10, inclusive.
        max_values: Optional[:class:`int`]
            The maximum number of files that can be uploaded.
            Must be between 1 and 10, inclusive.
        required: :class:`bool`
            Whether the file upload field is required or not. Defaults to ``True``.
        id: Optional[:class:`int`]
            The file upload field's ID.
        """
        upload = FileUpload(
            custom_id=custom_id,
            min_values=min_values,
            max_values=max_values,
            required=required,
            id=id,
        )

        return self.set_item(upload)

    def set_radio_group(
        self,
        *,
        custom_id: str | None = None,
        options: list[RadioGroupOption] | None = None,
        required: bool = True,
        id: int | None = None,
    ) -> Self:
        """Set this label's item to a radio group.

        To set a pre-existing :class:`RadioGroup`, use the
        :meth:`set_item` method, instead.

        Parameters
        ----------
        custom_id: Optional[:class:`str`]
            The ID of the radio group that gets received during an interaction.
        options: List[:class:`discord.RadioGroupOption`]
            A list of options that can be selected from this group.
        required: :class:`bool`
            Whether an option selection is required or not. Defaults to ``True``.
        id: Optional[:class:`int`]
            The radio group's ID.
        """
        radio = RadioGroup(
            custom_id=custom_id,
            options=options,
            required=required,
            id=id,
        )

        return self.set_item(radio)

    def set_checkbox_group(
        self,
        *,
        custom_id: str | None = None,
        options: list[CheckboxGroupOption] | None = None,
        min_values: int | None = None,
        max_values: int | None = None,
        required: bool = True,
        id: int | None = None,
    ) -> Self:
        """Set this label's item to a checkbox group.

        To set a pre-existing :class:`CheckboxGroup`, use the
        :meth:`set_item` method, instead.

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
        checkboxes = CheckboxGroup(
            custom_id=custom_id,
            options=options,
            min_values=min_values,
            max_values=max_values,
            required=required,
            id=id,
        )

        return self.set_item(checkboxes)

    def set_checkbox(
        self,
        *,
        custom_id: str | None = None,
        default: bool | None = False,
        id: int | None = None,
    ) -> Self:
        """Set this label's item to a checkbox.

        To set a pre-existing :class:`Checkbox`, use the
        :meth:`set_item` method, instead.

        Parameters
        ----------
        custom_id: Optional[:class:`str`]
            The ID of the checkbox that gets received during an interaction.
        default: Optional[:class:`bool`]
            Whether this checkbox is selected by default or not.
        id: Optional[:class:`int`]
            The checkbox's ID.
        """
        checkbox = Checkbox(
            custom_id=custom_id,
            default=default,
            id=id,
        )

        return self.set_item(checkbox)

    @override
    def is_dispatchable(self) -> bool:
        return self.item is not None and self.item.is_dispatchable()

    @override
    def is_persistent(self) -> bool:
        return self.item is None or self.item.is_persistent()

    @override
    def refresh_component(self, component: LabelComponent) -> None:
        self.underlying = component
        if self.item is not None:
            self.item.refresh_component(component.component)

    def walk_items(self) -> Iterator[ModalItem]:
        """Iterates over the item of this label."""
        if self.item is not None:
            yield self.item

    @override
    def to_component_dict(self) -> LabelComponentPayload:
        if self.item is not None:
            self._set_component_from_item(self.item)
        return cast("LabelComponentPayload", super().to_component_dict())

    @override
    def refresh_from_modal(
        self, interaction: Interaction, data: LabelComponentPayload
    ) -> None:
        if self.item is not None:
            self.item.refresh_from_modal(interaction, data.get("component", {}))

    @classmethod
    @override
    def from_component(cls, component: LabelComponent) -> Self:
        from .view import _component_to_item

        item = (
            _component_to_item(component.component)
            if component.component is not None
            else None
        )
        return cls(
            label=component.label,
            item=item,
            id=component.id,
            description=component.description,
        )
