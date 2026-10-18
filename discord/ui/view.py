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

import asyncio
import contextlib
import logging
import os
import sys
import time
from functools import partial
from itertools import groupby
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    cast,
)

from typing_extensions import override

from ..components import (
    ActionRow as ActionRowComponent,
    Button as ButtonComponent,
    Checkbox as CheckboxComponent,
    CheckboxGroup as CheckboxGroupComponent,
    Component,
    Container as ContainerComponent,
    FileComponent,
    FileUpload as FileUploadComponent,
    InputText as InputTextComponent,
    Label as LabelComponent,
    MediaGallery as MediaGalleryComponent,
    RadioGroup as RadioGroupComponent,
    Section as SectionComponent,
    SelectMenu as SelectComponent,
    Separator as SeparatorComponent,
    TextDisplay as TextDisplayComponent,
    Thumbnail as ThumbnailComponent,
    _component_factory,
)
from ..enums import ChannelType, SeparatorSpacingSize
from ..errors import Forbidden, NotFound
from ..limits import ComponentLimits
from .core import (
    ItemInterface,
    _insertion_index,
    _resolve_item,
    _validate_position,
)
from .item import (
    Item,
    ItemCallbackType,
    ViewItem,
    _callback_item,
    _set_disabled,
    _walk_nested,
)

__all__ = (
    "BaseView",
    "DesignerView",
    "View",
    "_component_to_item",
    "_walk_all_components",
)


if TYPE_CHECKING:
    from collections.abc import Coroutine, Iterator, Sequence

    from typing_extensions import Self

    from ..components import MediaGalleryItem
    from ..interactions import Interaction, InteractionMessage
    from ..message import Message
    from ..state import ConnectionState
    from ..types.components import Component as ComponentPayload
    from .action_row import ActionRow

_log = logging.getLogger(__name__)


def _walk_all_components(components: list[Component]) -> Iterator[Component]:
    for item in components:
        if isinstance(item, ActionRowComponent):
            yield from item.children
        else:
            yield item


def _component_to_item(component: Component) -> Any:
    """Converts a component to its item.

    The item is a :class:`ViewItem` or a :class:`ModalItem`, depending on the component.
    """
    if isinstance(component, ButtonComponent):
        from .button import Button

        return Button.from_component(component)
    if isinstance(component, SelectComponent):
        from .select import Select

        return Select.from_component(component)
    if isinstance(component, SectionComponent):
        from .section import Section

        return Section.from_component(component)
    if isinstance(component, TextDisplayComponent):
        from .text_display import TextDisplay

        return TextDisplay.from_component(component)
    if isinstance(component, ThumbnailComponent):
        from .thumbnail import Thumbnail

        return Thumbnail.from_component(component)
    if isinstance(component, MediaGalleryComponent):
        from .media_gallery import MediaGallery

        return MediaGallery.from_component(component)
    if isinstance(component, FileComponent):
        from .file import File

        return File.from_component(component)
    if isinstance(component, SeparatorComponent):
        from .separator import Separator

        return Separator.from_component(component)
    if isinstance(component, ContainerComponent):
        from .container import Container

        return Container.from_component(component)
    if isinstance(component, ActionRowComponent):
        from .action_row import ActionRow

        return ActionRow.from_component(component)
    if isinstance(component, LabelComponent):
        from .label import Label

        return Label.from_component(component)
    if isinstance(component, InputTextComponent):
        from .input_text import InputText

        return InputText.from_component(component)
    if isinstance(component, FileUploadComponent):
        from .file_upload import FileUpload

        return FileUpload.from_component(component)
    if isinstance(component, RadioGroupComponent):
        from .radio_group import RadioGroup

        return RadioGroup.from_component(component)
    if isinstance(component, CheckboxGroupComponent):
        from .checkbox_group import CheckboxGroup

        return CheckboxGroup.from_component(component)
    if isinstance(component, CheckboxComponent):
        from .checkbox import Checkbox

        return Checkbox.from_component(component)
    return Item.from_component(component)


def _row_key(item: ViewItem) -> int:
    return sys.maxsize if item.row is None else item.row


class _ViewWeights:
    __slots__ = ("weights",)

    def __init__(self, children: list[ViewItem]) -> None:
        self.weights: list[int] = [0] * ComponentLimits.LEGACY_VIEW_ROWS_MAX

        children = sorted(children, key=_row_key)
        for _row, group in groupby(children, key=_row_key):
            for item in group:
                self.add_item(item)

    def find_open_space(self, item: ViewItem) -> int:
        for index, weight in enumerate(self.weights):
            # check if open space AND (next row has no items OR this is the last row)
            if (weight + item.width <= ComponentLimits.ACTION_ROW_CHILDREN_MAX) and (
                (index < len(self.weights) - 1 and self.weights[index + 1] == 0)
                or index == len(self.weights) - 1
            ):
                return index

        raise ValueError("could not find open space for item")

    def add_item(self, item: ViewItem) -> None:
        if item.row is not None:
            total = self.weights[item.row] + item.width
            if total > ComponentLimits.ACTION_ROW_CHILDREN_MAX:
                raise ValueError(
                    f"item would not fit at row {item.row} ({total} > {ComponentLimits.ACTION_ROW_CHILDREN_MAX} width)"
                )
            self.weights[item.row] = total
            item._rendered_row = item.row
        else:
            index = self.find_open_space(item)
            self.weights[index] += item.width
            item._rendered_row = index

    def remove_item(self, item: ViewItem) -> None:
        if item._rendered_row is not None:
            self.weights[item._rendered_row] -= item.width
            item._rendered_row = None

    def clear(self) -> None:
        self.weights = [0] * ComponentLimits.LEGACY_VIEW_ROWS_MAX


class BaseView(ItemInterface[ViewItem]):
    """The base class for UI views used in messages.

    .. versionadded:: 2.7
    """

    __discord_ui_view__: ClassVar[bool] = True
    MAX_ITEMS: int

    def __init__(
        self,
        *items: ViewItem,
        timeout: float | None = 180.0,
        disable_on_timeout: bool = False,
        store: bool = True,
    ) -> None:
        super().__init__(*items, timeout=timeout, store=store)
        self.disable_on_timeout = disable_on_timeout
        self.id: str = os.urandom(16).hex()
        self._message: Message | InteractionMessage | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()
        self.parent: Interaction | None = None

    def add_item(self, item: ViewItem) -> Self:
        """Adds an item to the view.

        Parameters
        ----------
        item: :class:`ViewItem`
            The item to add to the view.

        Raises
        ------
        TypeError
            An :class:`ViewItem` was not passed.
        ValueError
            Maximum number of children has been exceeded
        """
        if len(self) >= self.MAX_ITEMS:
            raise ValueError("maximum number of children exceeded")

        if not isinstance(cast("object", item), ViewItem):
            raise TypeError(f"expected ViewItem not {item.__class__!r}")

        item.parent = self
        self.children.append(item)
        return self

    def remove_item(self, item: ViewItem | int | str) -> Self:
        """Removes an item from the view. If an :class:`int` or :class:`str` is passed, the item will be removed by ViewItem ``id`` or ``custom_id`` respectively.

        Parameters
        ----------
        item: Union[:class:`ViewItem`, :class:`int`, :class:`str`]
            The item, item ``id``, or item ``custom_id`` to remove from the view.

        Returns
        -------
        :class:`BaseView`
            The view instance.
        """
        if isinstance(item, (str, int)):
            found = self.get_item(item)
            if found is None:
                return self
            item = found
        try:
            if item.parent is self:
                self.children.remove(item)
                item.parent = None
            else:
                cast("Any", item.parent).remove_item(item)
        except (ValueError, AttributeError):
            pass
        return self

    def clear_items(self) -> Self:
        """Removes all items from this view."""
        for child in self.children:
            child.parent = None
        self.children.clear()
        return self

    async def interaction_check(self, interaction: Interaction) -> bool:
        """|coro|

        A callback that is called when an interaction happens within the view
        that checks whether the view should process item callbacks for the interaction.

        This is useful to override if, for example, you want to ensure that the
        interaction author is a given user.

        The default implementation of this returns ``True``.

        If this returns ``False``, :meth:`on_check_failure` is called.

        .. note::

            If an exception occurs within the body then the check
            is considered a failure and :meth:`on_error` is called.

        Parameters
        ----------
        interaction: :class:`~discord.Interaction`
            The interaction that occurred.

        Returns
        -------
        :class:`bool`
            Whether the view children's callbacks should be called.
        """
        return True

    async def on_timeout(self) -> None:
        """|coro|

        A callback that is called when a view's timeout elapses without being explicitly stopped.
        """
        if self.disable_on_timeout:
            self.disable_all_items()

            if (
                not self._message
                or self._message.flags.ephemeral
                or (self._message.channel.type == ChannelType.private)
            ):
                message = self.parent
            else:
                message = self.message

            if message:
                with contextlib.suppress(NotFound, Forbidden):
                    m = await message.edit(view=self)
                    if m:
                        self._message = m

    async def on_check_failure(self, interaction: Interaction) -> None:
        """|coro|

        A callback that is called when a :meth:`BaseView.interaction_check` returns ``False``.

        This can be used to send a response when a check failure occurs.

        Parameters
        ----------
        interaction: :class:`~discord.Interaction`
            The interaction that occurred.
        """

    async def on_error(
        self, error: Exception, item: ViewItem, interaction: Interaction
    ) -> None:
        """|coro|

        A callback that is called when an item's callback or :meth:`interaction_check`
        fails with an error.

        The default implementation prints the traceback to stderr.

        Parameters
        ----------
        error: :class:`Exception`
            The exception that was raised.
        item: :class:`ViewItem`
            The item that failed the dispatch.
        interaction: :class:`~discord.Interaction`
            The interaction that led to the failure.
        """
        interaction.client.dispatch("view_error", error, item, interaction)

    def is_components_v2(self) -> bool:
        """Whether the view contains V2 components.

        A view containing V2 components cannot be sent alongside message content or embeds.
        """
        return any(item.underlying.is_v2() for item in self.children)

    async def _scheduled_task(self, item: ViewItem, interaction: Interaction) -> None:
        try:
            if self.timeout:
                self._timeout_expiry = time.monotonic() + self.timeout

            await item._resolve_state()

            allow = await self.interaction_check(interaction)
            if not allow:
                return await self.on_check_failure(interaction)

            await item.callback(interaction)
        except Exception as e:
            return await self.on_error(e, item, interaction)

    def _start_listening_from_store(self, store: ViewStore) -> None:
        self._cancel_callback = partial(store.remove_view)
        if self.timeout:
            loop = asyncio.get_running_loop()
            if self._timeout_task is not None:
                self._timeout_task.cancel()

            self._timeout_expiry = time.monotonic() + self.timeout
            self._timeout_task = loop.create_task(self._timeout_task_impl())

    def _spawn(self, coro: Coroutine[Any, Any, None], name: str) -> None:
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _dispatch_timeout(self) -> None:
        if self._stopped.done():
            return

        self._stopped.set_result(True)
        self._spawn(self.on_timeout(), f"discord-ui-view-timeout-{self.id}")

    def _dispatch_item(self, item: ViewItem, interaction: Interaction) -> None:
        if self._stopped.done():
            return

        if interaction.message:
            self.message = interaction.message

        self._spawn(
            self._scheduled_task(item, interaction),
            f"discord-ui-view-dispatch-{self.id}",
        )

    def is_finished(self) -> bool:
        """Whether the view has finished interacting."""
        return self._stopped.done()

    def is_dispatchable(self) -> bool:
        """Whether any item of this view can receive interactions."""
        return any(item.is_dispatchable() for item in self.children)

    def is_dispatching(self) -> bool:
        """Whether the view has been added for dispatching purposes."""
        return self._cancel_callback is not None

    def is_persistent(self) -> bool:
        """Whether the view is set up as persistent.

        A persistent view has all their components with a set ``custom_id`` and
        a :attr:`timeout` set to ``None``.
        """
        return self.timeout is None and all(
            item.is_persistent() for item in self.children
        )

    def stop(self) -> None:
        """Stops listening to interaction events from this view.

        This operation cannot be undone.
        """
        if not self._stopped.done():
            self._stopped.set_result(False)

        self._timeout_expiry = None
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            self._timeout_task = None

        if self._cancel_callback:
            self._cancel_callback(self)
            self._cancel_callback = None

    async def wait(self) -> bool:
        """Waits until the view has finished interacting.

        A view is considered finished when :meth:`stop`
        is called, or it times out.

        Returns
        -------
        :class:`bool`
            If ``True``, then the view timed out. If ``False`` then
            the view finished normally.
        """
        return await self._stopped

    def disable_all_items(self, *, exclusions: list[ViewItem] | None = None) -> Self:
        """
        Disables all buttons and select menus in the view.

        Parameters
        ----------
        exclusions: Optional[List[:class:`ViewItem`]]
            A list of items in `self.children` to not disable from the view.
        """
        for child in self.children:
            if hasattr(child, "disabled") and (
                exclusions is None or child not in exclusions
            ):
                _set_disabled(child, True)
            if hasattr(child, "disable_all_items"):
                cast("Any", child).disable_all_items(exclusions=exclusions)
        return self

    def enable_all_items(self, *, exclusions: list[ViewItem] | None = None) -> Self:
        """
        Enables all buttons and select menus in the view.

        Parameters
        ----------
        exclusions: Optional[List[:class:`ViewItem`]]
            A list of items in `self.children` to not enable from the view.
        """
        for child in self.children:
            if hasattr(child, "disabled") and (
                exclusions is None or child not in exclusions
            ):
                _set_disabled(child, False)
            if hasattr(child, "enable_all_items"):
                cast("Any", child).enable_all_items(exclusions=exclusions)
        return self

    def copy_text(self) -> str:
        """Returns the text of all :class:`~discord.ui.TextDisplay` items in this View.

        Equivalent to the `Copy Text` option on Discord clients.
        """
        return "\n".join(t for i in self.children if (t := i.copy_text()))

    def walk_children(self) -> Iterator[ViewItem]:
        """Iterates over the children of this view, nested items included."""
        for item in self.children:
            yield from _walk_nested(item)

    @property
    def message(self) -> Message | InteractionMessage | None:
        """The message that this view is attached to.

        If ``None`` then the view has not been sent with a message.
        """
        return self._message

    @message.setter
    def message(self, value: Message | InteractionMessage | None) -> None:
        self._message = value

    def _refresh(self, components: list[Component]) -> None:
        raise NotImplementedError

    @classmethod
    def from_message(
        cls,
        message: Message,
        /,
        *,
        timeout: float | None = 180.0,
        disable_on_timeout: bool = False,
        store: bool = True,
    ) -> BaseView:
        """Converts a message's components into this kind of view.

        Subclasses override this to convert the components of a message in the way
        that fits their component rules, see :meth:`View.from_message` and :meth:`DesignerView.from_message`.

        .. versionadded:: 3.0

        Parameters
        ----------
        message: :class:`.Message`
            The message with components to convert into a view.
        timeout: Optional[:class:`float`]
            The timeout of the converted view.
        disable_on_timeout: :class:`bool`
            Whether to disable the view when the timeout is reached. Defaults to ``False``.
        store: :class:`bool`
            Whether this view should be stored for callback listening. Defaults to ``True``.

        Returns
        -------
        :class:`BaseView`
            The converted view.
        """
        view = cls(timeout=timeout, disable_on_timeout=disable_on_timeout, store=store)
        for component in message.components:
            view.add_item(_component_to_item(component))
        return view


class View(BaseView):
    """Represents a legacy UI view for V1 components :class:`~discord.ui.Button` and :class:`~discord.ui.Select`.

    This object must be inherited to create a UI within Discord.

    .. versionadded:: 2.0

    .. versionchanged:: 2.7

        Now inherits from :class:`BaseView`

    Parameters
    ----------
    *items: :class:`ViewItem`
        The initial items attached to this view.
    timeout: Optional[:class:`float`]
        Timeout in seconds from last interaction with the UI before no longer accepting input. Defaults to 180.0.
        If ``None`` then there is no timeout.
    disable_on_timeout: :class:`bool`
        Whether to disable the view when the timeout is reached. Defaults to ``False``.
    store: Optional[:class:`bool`]
        Whether this view should be stored for callback listening. Setting it to ``False`` will ignore item callbacks and prevent their values from being refreshed. Defaults to ``True``.

    Attributes
    ----------
    timeout: Optional[:class:`float`]
        Timeout from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.
    children: List[:class:`ViewItem`]
        The list of children attached to this view.
    message: Optional[:class:`.Message`]
        The message that this view is attached to.
        If ``None`` then the view has not been sent with a message.
    parent: Optional[:class:`.Interaction`]
        The parent interaction which this view was sent from.
        If ``None`` then the view was not sent using :meth:`InteractionResponse.send_message`.
    """

    __view_children_items__: ClassVar[list[ItemCallbackType[ViewItem]]] = []
    MAX_ITEMS: int = (
        ComponentLimits.LEGACY_VIEW_ROWS_MAX * ComponentLimits.ACTION_ROW_CHILDREN_MAX
    )

    def __init_subclass__(cls) -> None:
        children: list[ItemCallbackType[ViewItem]] = []
        for base in reversed(cls.__mro__):
            children.extend(
                member
                for member in base.__dict__.values()
                if hasattr(member, "__discord_ui_model_type__")
            )

        if len(children) > ComponentLimits.VIEW_CHILDREN_MAX:
            raise TypeError(
                f"View cannot have more than {ComponentLimits.VIEW_CHILDREN_MAX} children"
            )

        cls.__view_children_items__ = children

    def __init__(
        self,
        *items: ViewItem,
        timeout: float | None = 180.0,
        disable_on_timeout: bool = False,
        store: bool = True,
    ) -> None:
        super().__init__(
            timeout=timeout, disable_on_timeout=disable_on_timeout, store=store
        )

        for func in self.__view_children_items__:
            item: ViewItem = _callback_item(self, func)
            item.parent = self
            setattr(self, func.__name__, item)
            self.children.append(item)

        self.__weights = _ViewWeights(self.children)
        for item in items:
            self.add_item(item)

    @override
    def to_components(self) -> list[ComponentPayload]:
        def key(item: ViewItem) -> int:
            return item._rendered_row or 0

        children = sorted(self.children, key=key)
        components: list[ComponentPayload] = []
        for _, group in groupby(children, key=key):
            items = list(group)
            row = [item.to_component_dict() for item in items]
            if not row:
                continue

            components.append(
                cast(
                    "ComponentPayload",
                    {
                        "type": 1,
                        "components": row,
                    },
                )
            )

        return components

    @classmethod
    def from_message(
        cls,
        message: Message,
        /,
        *,
        timeout: float | None = 180.0,
        disable_on_timeout: bool = False,
        store: bool = True,
    ) -> View:
        """Converts a message's components into a :class:`View`.

        The :attr:`.Message.components` of a message are read-only
        and separate types from those in the ``discord.ui`` namespace.
        In order to modify and edit message components they must be
        converted into a :class:`View` first.

        Parameters
        ----------
        message: :class:`.Message`
            The message with components to convert into a view.
        timeout: Optional[:class:`float`]
            The timeout of the converted view.
        disable_on_timeout: :class:`bool`
            Whether to disable the view when the timeout is reached. Defaults to ``False``.
        store: Optional[:class:`bool`]
            Whether this view should be stored for callback listening. Setting it to ``False`` will ignore item callbacks and prevent their values from being refreshed. Defaults to ``True``.

        Returns
        -------
        :class:`View`
            The converted view. This always returns a :class:`View` and not
            one of its subclasses.
        """
        view = View(timeout=timeout, disable_on_timeout=disable_on_timeout, store=store)
        for component in _walk_all_components(message.components):
            view.add_item(_component_to_item(component))
        return view

    @classmethod
    def from_dict(
        cls,
        data: list[ComponentPayload],
        /,
        *,
        timeout: float | None = 180.0,
        disable_on_timeout: bool = False,
        store: bool = True,
    ) -> View:
        """Converts a list of component dicts into a :class:`View`.

        Parameters
        ----------
        data: List[:class:`.Component`]
            The list of components to convert into a view.
        timeout: Optional[:class:`float`]
            The timeout of the converted view.
        disable_on_timeout: :class:`bool`
            Whether to disable the view when the timeout is reached. Defaults to ``False``.
        store: Optional[:class:`bool`]
            Whether this view should be stored for callback listening. Setting it to ``False`` will ignore item callbacks and prevent their values from being refreshed. Defaults to ``True``.

        Returns
        -------
        :class:`View`
            The converted view. This always returns a :class:`View` and not
            one of its subclasses.
        """
        view = View(timeout=timeout, disable_on_timeout=disable_on_timeout, store=store)
        components = [_component_factory(d) for d in data]
        for component in _walk_all_components(components):
            view.add_item(_component_to_item(component))
        return view

    def add_item(self, item: ViewItem) -> Self:
        """Adds an item to the view. Attempting to add a :class:`~discord.ui.ActionRow` will add its children instead.

        Parameters
        ----------
        item: :class:`ViewItem`
            The item to add to the view.

        Raises
        ------
        TypeError
            An :class:`ViewItem` was not passed.
        ValueError
            Maximum number of children has been exceeded (25)
            or the row the item is trying to be added to is full.
        """
        if not isinstance(cast("object", item), ViewItem):
            raise TypeError(f"expected ViewItem not {item.__class__!r}")
        if item.underlying.is_v2():
            raise ValueError(
                "cannot use V2 components in View. Use DesignerView instead."
            )
        if isinstance(item.underlying, ActionRowComponent):
            for i in cast("ActionRow", item).children:
                self.add_item(i)
            return self

        super().add_item(item)
        self.__weights.add_item(item)
        return self

    def remove_item(self, item: ViewItem | int | str) -> Self:
        """Removes an item from the view. If an :class:`int` or :class:`str` is passed, the item will be removed by Item ``id`` or ``custom_id`` respectively.

        Parameters
        ----------
        item: Union[:class:`ViewItem`, :class:`int`, :class:`str`]
            The item, item ``id``, or item ``custom_id`` to remove from the view.
        """
        if isinstance(item, (str, int)):
            found = self.get_item(item)
            if found is None:
                return self
            item = found
        super().remove_item(item)
        with contextlib.suppress(ValueError):
            self.__weights.remove_item(item)
        return self

    def clear_items(self) -> Self:
        """Removes all items from the view."""
        super().clear_items()
        self.__weights.clear()
        return self

    def _refresh(self, components: list[Component]) -> None:
        # This is pretty hacky at the moment
        old_state: dict[tuple[int, Any], ViewItem] = {
            (item.type.value, cast("Any", item).custom_id): item
            for item in self.children
            if item.is_dispatchable()
        }
        children: list[ViewItem] = [
            item for item in self.children if not item.is_dispatchable()
        ]
        for component in _walk_all_components(components):
            older = old_state.get(
                (component.type.value, getattr(component, "custom_id", None))
            )
            if older is None:
                item = _component_to_item(component)
                if not item.is_dispatchable():
                    continue
                children.append(item)
            else:
                older.refresh_component(component)
                children.append(older)

        self.children = children

    def is_components_v2(self) -> bool:
        """Whether the view contains V2 components.

        A view containing V2 components cannot be sent alongside message content or embeds.

        This is always ``False`` for :class:`View`.
        """
        return False


class DesignerView(BaseView):
    """Represents a UI view compatible with v2 components.

    This object must be inherited to create a UI within Discord.

    .. versionadded:: 2.7

    Parameters
    ----------
    *items: :class:`ViewItem`
        The initial items attached to this view.
    timeout: Optional[:class:`float`]
        Timeout in seconds from last interaction with the UI before no longer accepting input. Defaults to 180.0.
        If ``None`` then there is no timeout.
    disable_on_timeout: :class:`bool`
        Whether to disable the view's items when the timeout is reached. Defaults to ``False``.
    store: Optional[:class:`bool`]
        Whether this view should be stored for callback listening. Setting it to ``False`` will ignore item callbacks and prevent their values from being refreshed. Defaults to ``True``.

    Attributes
    ----------
    timeout: Optional[:class:`float`]
        Timeout from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.
    children: List[:class:`ViewItem`]
        The list of items attached to this view.
    message: Optional[:class:`.Message`]
        The message that this view is attached to.
        If ``None`` then the view has not been sent with a message.
    parent: Optional[:class:`.Interaction`]
        The parent interaction which this view was sent from.
        If ``None`` then the view was not sent using :meth:`InteractionResponse.send_message`.
    """

    MAX_ITEMS: int = ComponentLimits.VIEW_CHILDREN_MAX

    def __init_subclass__(cls) -> None:
        for base in reversed(cls.__mro__):
            for member in base.__dict__.values():
                if hasattr(member, "__discord_ui_model_type__"):
                    raise ValueError(
                        "The @button and @select decorators are incompatible with DesignerView. Use ActionRow instead."
                    )

    def __init__(
        self,
        *items: ViewItem,
        timeout: float | None = 180.0,
        disable_on_timeout: bool = False,
        store: bool = True,
    ) -> None:
        super().__init__(
            *items, timeout=timeout, disable_on_timeout=disable_on_timeout, store=store
        )

    @property
    def items(self) -> list[ViewItem]:
        """The items of this view, an alias of :attr:`children`."""
        return self.children

    @items.setter
    def items(self, value: list[ViewItem]) -> None:
        self.children = value

    @classmethod
    def from_message(
        cls,
        message: Message,
        /,
        *,
        timeout: float | None = 180.0,
        disable_on_timeout: bool = False,
        store: bool = True,
    ) -> DesignerView:
        """Converts a message's components into a :class:`DesignerView`.

        The :attr:`.Message.components` of a message are read-only
        and separate types from those in the ``discord.ui`` namespace.
        In order to modify and edit message components they must be
        converted into a :class:`DesignerView` first.

        Parameters
        ----------
        message: :class:`.Message`
            The message with components to convert into a view.
        timeout: Optional[:class:`float`]
            The timeout of the converted view.
        disable_on_timeout: :class:`bool`
            Whether to disable the view when the timeout is reached. Defaults to ``False``.
        store: Optional[:class:`bool`]
            Whether this view should be stored for callback listening. Setting it to ``False`` will ignore item callbacks and prevent their values from being refreshed. Defaults to ``True``.

        Returns
        -------
        :class:`DesignerView`
            The converted view. This always returns a :class:`DesignerView` and not
            one of its subclasses.
        """
        view = DesignerView(
            timeout=timeout, disable_on_timeout=disable_on_timeout, store=store
        )
        for component in message.components:
            view.add_item(_component_to_item(component))
        return view

    @classmethod
    def from_dict(
        cls,
        data: list[ComponentPayload],
        /,
        *,
        timeout: float | None = 180.0,
        disable_on_timeout: bool = False,
        store: bool = True,
    ) -> DesignerView:
        """Converts a list of component dicts into a :class:`DesignerView`.

        Parameters
        ----------
        data: List[:class:`.Component`]
            The list of components to convert into a view.
        timeout: Optional[:class:`float`]
            The timeout of the converted view.
        disable_on_timeout: :class:`bool`
            Whether to disable the view when the timeout is reached. Defaults to ``False``.
        store: Optional[:class:`bool`]
            Whether this view should be stored for callback listening. Setting it to ``False`` will ignore item callbacks and prevent their values from being refreshed. Defaults to ``True``.

        Returns
        -------
        :class:`DesignerView`
            The converted view. This always returns a :class:`DesignerView` and not
            one of its subclasses.
        """
        view = DesignerView(
            timeout=timeout, disable_on_timeout=disable_on_timeout, store=store
        )
        components = [_component_factory(d) for d in data]
        for component in components:
            view.add_item(_component_to_item(component))
        return view

    def add_item(
        self,
        item: ViewItem,
        *,
        index: int | None = None,
        before: ViewItem | str | int | None = None,
        after: ViewItem | str | int | None = None,
        into: ViewItem | str | int | None = None,
    ) -> Self:
        """Adds an item to the view.

        .. warning::

            You may specify only **one** of ``index``, ``before`` and ``after``. ``into`` works together with those parameters.

        .. versionchanged:: 3.0
            Added the ``index``, ``before``, ``after`` and ``into`` parameters.
            The maximum of 40 items now counts nested items too, see :func:`len`.

        Parameters
        ----------
        item: :class:`ViewItem`
            The item to add to the view.
        index: Optional[:class:`int`]
            Add the new item at the specific index of :attr:`children`. Same behavior as Python's :func:`~list.insert`.
        before: Optional[Union[:class:`ViewItem`, :class:`int`, :class:`str`]]
            Add the new item **before** the specified item. If an :class:`int` is provided, the item will be detected by ``id``, otherwise by ``custom_id``.
            Nested items are searched too, the new item is added to the parent of the specified item.
        after: Optional[Union[:class:`ViewItem`, :class:`int`, :class:`str`]]
            Add the new item **after** the specified item. If an :class:`int` is provided, the item will be detected by ``id``, otherwise by ``custom_id``.
            Nested items are searched too, the new item is added to the parent of the specified item.
        into: Optional[Union[:class:`ViewItem`, :class:`int`, :class:`str`]]
            Add the new item **into** the specified item. This is equivalent to ``into.add_item(item)``.
            If an :class:`int` is provided, the item will be detected by ``id``, otherwise by ``custom_id``.

        Raises
        ------
        TypeError
            A :class:`ViewItem` was not passed.
        ValueError
            More than one of ``index``, ``before`` and ``after`` was given,
            the maximum number of items has been exceeded (40),
            or a searched item could not be found in the view.
        """
        _validate_position(index, before, after)

        if not isinstance(cast("object", item), ViewItem):
            raise TypeError(f"expected item to be ViewItem, not {item.__class__!r}")

        if len(self) + len(item) > self.MAX_ITEMS:
            raise ValueError(f"maximum number of children exceeded ({self.MAX_ITEMS})")

        if into is not None:
            target = _resolve_item(self, into, "the view")
            if target is not self:
                target.add_item(item, index=index, before=before, after=after)
                return self

        if before is not None or after is not None:
            ref = _resolve_item(
                self, before if before is not None else after, "the view"
            )
            if ref.parent is not self:
                owner = ref.parent
                if owner is None or not hasattr(owner, "add_item"):
                    raise ValueError(f"Could not find {ref!r} in the view.")
                if before is not None:
                    owner.add_item(item, before=ref)
                else:
                    owner.add_item(item, after=ref)
                return self

        is_legacy_interactive = isinstance(
            item.underlying, (SelectComponent, ButtonComponent)
        )
        if is_legacy_interactive:
            raise ValueError(
                "cannot add Select or Button to DesignerView directly. Use ActionRow instead."
            )

        position = _insertion_index(
            self, self.children, index, before, after, "the view"
        )

        item.parent = self
        if position is None:
            self.children.append(item)
        else:
            self.children.insert(position, item)
        return self

    def replace_item(
        self, original_item: ViewItem | str | int, new_item: ViewItem
    ) -> Self:
        """Directly replace an item in this view, including nested items.

        If an :class:`int` is provided, the item will be replaced by ``id``, otherwise by ``custom_id``.

        .. versionadded:: 3.0

        Parameters
        ----------
        original_item: Union[:class:`ViewItem`, :class:`int`, :class:`str`]
            The item, item ``id``, or item ``custom_id`` to replace in the view.
        new_item: :class:`ViewItem`
            The new item to insert into the view.

        Returns
        -------
        :class:`DesignerView`
            The view instance.

        Raises
        ------
        TypeError
            The new item is not a :class:`ViewItem`.
        ValueError
            The original item could not be found in the view.
        """
        if not isinstance(cast("object", new_item), ViewItem):
            raise TypeError(
                f"expected new_item to be ViewItem, not {new_item.__class__!r}"
            )

        original = _resolve_item(self, original_item, "the view")
        if original.parent is self:
            if isinstance(new_item.underlying, (SelectComponent, ButtonComponent)):
                raise ValueError(
                    "cannot add Select or Button to DesignerView directly. Use ActionRow instead."
                )
            try:
                i = self.children.index(original)
            except ValueError:
                raise ValueError(
                    f"Could not find {original_item!r} in the view."
                ) from None
            new_item.parent = self
            self.children[i] = new_item
            original.parent = None
        else:
            owner = original.parent
            if owner is None or not hasattr(owner, "replace_item"):
                raise ValueError(f"Could not find {original_item!r} in the view.")
            owner.replace_item(original, new_item)
        return self

    def add_row(
        self,
        *items: ViewItem,
        id: int | None = None,
    ) -> Self:
        """Adds an :class:`ActionRow` to the view.

        To append a pre-existing :class:`ActionRow`, use :meth:`add_item` instead.

        .. versionadded:: 3.0

        Parameters
        ----------
        *items: Union[:class:`Button`, :class:`Select`]
            The items this action row contains.
        id: Optional[:class:`int`]
            The action row's ID.
        """
        from .action_row import ActionRow

        row = ActionRow(*items, id=id)

        return self.add_item(row)

    def add_container(
        self,
        *items: ViewItem,
        id: int | None = None,
    ) -> Self:
        """Adds a :class:`Container` to the view.

        To append a pre-existing :class:`Container`, use :meth:`add_item` instead.

        .. versionadded:: 3.0

        Parameters
        ----------
        *items: :class:`ViewItem`
            The items contained in this container.
        id: Optional[:class:`int`]
            The container's ID.
        """
        from .container import Container

        container = Container(*items, id=id)

        return self.add_item(container)

    def add_section(
        self,
        *items: ViewItem,
        accessory: ViewItem,
        id: int | None = None,
    ) -> Self:
        """Adds a :class:`Section` to the view.

        To append a pre-existing :class:`Section`, use :meth:`add_item` instead.

        .. versionadded:: 3.0

        Parameters
        ----------
        *items: :class:`ViewItem`
            The items contained in this section, up to 3.
            Currently only supports :class:`~discord.ui.TextDisplay`.
        accessory: :class:`ViewItem`
            The section's accessory. This is displayed in the top right of the section.
            Currently only supports :class:`~discord.ui.Button` and :class:`~discord.ui.Thumbnail`.
        id: Optional[:class:`int`]
            The section's ID.
        """
        from .section import Section

        section = Section(*items, accessory=accessory, id=id)

        return self.add_item(section)

    def add_text(self, content: str, id: int | None = None) -> Self:
        """Adds a :class:`TextDisplay` to the view.

        .. versionadded:: 3.0

        Parameters
        ----------
        content: :class:`str`
            The content of the TextDisplay
        id: Optional[:class:`int`]
            The text display's ID.
        """
        from .text_display import TextDisplay

        text = TextDisplay(content, id=id)

        return self.add_item(text)

    def add_gallery(
        self,
        *items: MediaGalleryItem,
        id: int | None = None,
    ) -> Self:
        """Adds a :class:`MediaGallery` to the view.

        To append a pre-existing :class:`MediaGallery`, use :meth:`add_item` instead.

        .. versionadded:: 3.0

        Parameters
        ----------
        *items: :class:`MediaGalleryItem`
            The media this gallery contains.
        id: Optional[:class:`int`]
            The gallery's ID.
        """
        from .media_gallery import MediaGallery

        gallery = MediaGallery(*items, id=id)

        return self.add_item(gallery)

    def add_file(self, url: str, spoiler: bool = False, id: int | None = None) -> Self:
        """Adds a :class:`File` to the view.

        .. versionadded:: 3.0

        Parameters
        ----------
        url: :class:`str`
            The URL of this file's media. This must be an ``attachment://`` URL that references a :class:`~discord.File`.
        spoiler: Optional[:class:`bool`]
            Whether the file has the spoiler overlay. Defaults to ``False``.
        id: Optional[:class:`int`]
            The file's ID.
        """
        from .file import File

        file = File(url, spoiler=spoiler, id=id)

        return self.add_item(file)

    def add_separator(
        self,
        *,
        divider: bool = True,
        spacing: SeparatorSpacingSize = SeparatorSpacingSize.small,
        id: int | None = None,
    ) -> Self:
        """Adds a :class:`Separator` to the view.

        .. versionadded:: 3.0

        Parameters
        ----------
        divider: :class:`bool`
            Whether the separator is a divider. Defaults to ``True``.
        spacing: :class:`~discord.SeparatorSpacingSize`
            The spacing size of the separator. Defaults to :attr:`~discord.SeparatorSpacingSize.small`.
        id: Optional[:class:`int`]
            The separator's ID.
        """
        from .separator import Separator

        separator = Separator(divider=divider, spacing=spacing, id=id)

        return self.add_item(separator)

    def _refresh(self, components: list[Component]) -> None:
        # Refreshes view data using discord's values
        # Assumes the components and items are identical
        if not components:
            return

        for item, c in zip(self.children, components, strict=False):
            item.refresh_component(c)

    @override
    def is_components_v2(self) -> bool:
        return (
            len(self.children) > ComponentLimits.LEGACY_VIEW_ROWS_MAX
            or super().is_components_v2()
        )


class ViewStore:
    def __init__(self, state: ConnectionState) -> None:
        # maps (component_type, message_id, custom_id) to (BaseView, ViewItem)
        self._views: dict[tuple[int, int | None, str], tuple[BaseView, ViewItem]] = {}
        # the views synced to a message, by message ID
        self._synced_message_views: dict[int, BaseView] = {}
        self._state: ConnectionState = state

    @property
    def persistent_views(self) -> Sequence[BaseView]:
        views = {
            view.id: view
            for (_, (view, _)) in self._views.items()
            if view.is_persistent()
        }
        return list(views.values())

    def __verify_integrity(self) -> None:
        to_remove: list[tuple[int, int | None, str]] = []
        for k, (view, _) in self._views.items():
            if view.is_finished():
                to_remove.append(k)

        for k in to_remove:
            del self._views[k]

    def add_view(self, view: BaseView, message_id: int | None = None) -> None:
        if not view._store:
            return
        self.__verify_integrity()

        view._start_listening_from_store(self)
        for item in view.walk_children():
            if item.is_storable():
                self._views[
                    (item.type.value, message_id, cast("Any", item).custom_id)
                ] = (view, item)

        if message_id is not None:
            self._synced_message_views[message_id] = view

    def remove_view(self, view: BaseView) -> None:
        keys_to_remove = [
            key for key, (stored_view, _) in self._views.items() if stored_view is view
        ]
        for key in keys_to_remove:
            del self._views[key]

        for key, value in self._synced_message_views.items():
            if value.id == view.id:
                self.remove_message_view(key)
                break

    def remove_message_view(self, message_id: int) -> None:
        del self._synced_message_views[message_id]

    def get_message_view(self, message_id: int) -> BaseView | None:
        return self._synced_message_views.get(message_id)

    def dispatch(
        self, component_type: int, custom_id: str, interaction: Interaction
    ) -> None:
        self.__verify_integrity()
        message_id: int | None = interaction.message and interaction.message.id
        key = (component_type, message_id, custom_id)
        # Fallback to None message_id searches in case a persistent view
        # was added without an associated message_id
        value = self._views.get(key) or self._views.get(
            (component_type, None, custom_id)
        )
        if value is None:
            return

        view, item = value
        interaction.view = view
        item.refresh_state(interaction)
        view._dispatch_item(item, interaction)

    def is_message_tracked(self, message_id: int) -> bool:
        return message_id in self._synced_message_views

    def remove_message_tracking(self, message_id: int) -> BaseView | None:
        return self._synced_message_views.pop(message_id, None)

    def update_from_message(
        self, message_id: int, components: list[ComponentPayload]
    ) -> None:
        # pre-req: is_message_tracked == true
        view = self._synced_message_views[message_id]
        converted = [_component_factory(d, state=self._state) for d in components]
        try:
            view._refresh(converted)
        except Exception:
            _log.exception(
                f"Failed to refresh View {view} from Message {message_id} due to mismatched state. Items may not have complete data."
            )
