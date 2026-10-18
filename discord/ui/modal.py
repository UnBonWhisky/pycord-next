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

import asyncio
import contextlib
import os
import sys
import time
from functools import partial
from itertools import groupby
from typing import TYPE_CHECKING, Any, Generic, cast

from typing_extensions import TypeVar, override

from ..components import _component_factory
from ..limits import ComponentLimits
from ..utils import _get_event_loop
from .core import ItemInterface
from .input_text import InputText
from .item import ModalItem, _walk_nested
from .label import Label
from .text_display import TextDisplay
from .view import _component_to_item

__all__ = (
    "BaseModal",
    "DesignerModal",
    "Modal",
    "ModalStore",
)


if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from typing_extensions import Self

    from ..interactions import Interaction
    from ..state import ConnectionState
    from ..types.components import Component as ComponentPayload, Modal as ModalPayload

ModalItemT = TypeVar("ModalItemT", bound="ModalItem", default=Any)


class BaseModal(ItemInterface[ModalItemT], Generic[ModalItemT]):
    """The base class for creating pop-up modals.

    .. versionadded:: 2.7
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "title",
        "children",
        "timeout",
    )

    def __init__(
        self,
        *children: ModalItemT,
        title: str,
        custom_id: str | None = None,
        timeout: float | None = None,
        store: bool = True,
    ) -> None:
        if not isinstance(cast("object", custom_id), str) and custom_id is not None:
            raise TypeError(
                f"expected custom_id to be str, not {custom_id.__class__.__name__}"
            )
        self._custom_id: str = custom_id or os.urandom(16).hex()
        if len(title) > ComponentLimits.MODAL_TITLE_MAX:
            raise ValueError(
                f"title must be {ComponentLimits.MODAL_TITLE_MAX} characters or fewer"
            )
        self._children: list[ModalItemT] = []
        super().__init__(timeout=timeout, store=store)
        for item in children:
            self.add_item(item)
        self._title = title
        self.loop = _get_event_loop()

    def __repr__(self) -> str:
        attrs = " ".join(
            f"{key}={getattr(self, key)!r}" for key in self.__item_repr_attributes__
        )
        return f"<{self.__class__.__name__} {attrs}>"

    def _start_listening_from_store(self, store: ModalStore) -> None:
        self._cancel_callback = partial(store.remove_modal)
        if self.timeout:
            loop = asyncio.get_running_loop()
            if self._timeout_task is not None:
                self._timeout_task.cancel()

            self._timeout_expiry = time.monotonic() + self.timeout
            self._timeout_task = loop.create_task(self._timeout_task_impl())

    def _dispatch_timeout(self) -> None:
        if self._stopped.done():
            return

        self._stopped.set_result(True)
        self.loop.create_task(
            self.on_timeout(), name=f"discord-ui-view-timeout-{self.custom_id}"
        )

    @property
    def title(self) -> str:
        """The title of the modal."""
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        if not isinstance(cast("object", value), str):
            raise TypeError(f"expected title to be str, not {value.__class__.__name__}")
        if len(value) > ComponentLimits.MODAL_TITLE_MAX:
            raise ValueError(
                f"title must be {ComponentLimits.MODAL_TITLE_MAX} characters or fewer"
            )
        self._title = value

    @property
    def children(self) -> list[ModalItemT]:
        """The child items attached to the modal."""
        return self._children

    @children.setter
    def children(self, value: list[ModalItemT]) -> None:
        for item in value:
            if not isinstance(cast("object", item), ModalItem):
                raise TypeError(
                    "all BaseModal children must be ModalItem, not"
                    f" {item.__class__.__name__}"
                )
        self._children = value

    @property
    def custom_id(self) -> str:
        """The ID of the modal that gets received during an interaction."""
        return self._custom_id

    @custom_id.setter
    def custom_id(self, value: str) -> None:
        if not isinstance(cast("object", value), str):
            raise TypeError(
                f"expected custom_id to be str, not {value.__class__.__name__}"
            )
        if len(value) > ComponentLimits.CUSTOM_ID_MAX:
            raise ValueError(
                f"custom_id must be {ComponentLimits.CUSTOM_ID_MAX} characters or fewer"
            )
        self._custom_id = value

    async def callback(self, interaction: Interaction) -> None:
        """|coro|

        The coroutine that is called when the modal is submitted.
        Should be overridden to handle the values submitted by the user.

        Parameters
        ----------
        interaction: :class:`~discord.Interaction`
            The interaction that submitted the modal.
        """
        self.stop()

    def add_item(self, item: ModalItemT) -> Self:
        """Adds a component to the modal.

        Parameters
        ----------
        item: Union[:class:`ModalItem`]
            The item to add to the modal
        """
        if len(self._children) >= ComponentLimits.MODAL_COMPONENTS_MAX:
            raise ValueError(
                f"You can only have up to {ComponentLimits.MODAL_COMPONENTS_MAX} items in a modal."
            )

        if not isinstance(cast("object", item), ModalItem):
            raise TypeError(f"expected ModalItem, not {item.__class__!r}")

        self._children.append(item)
        return self

    def remove_item(self, item: ModalItemT) -> Self:
        """Removes a component from the modal.

        Parameters
        ----------
        item: :class:`ModalItem`
            The item to remove from the modal.
        """
        with contextlib.suppress(ValueError):
            self._children.remove(item)
        return self

    def stop(self) -> None:
        """Stops listening to interaction events from the modal."""
        if not self._stopped.done():
            self._stopped.set_result(True)
        self._timeout_expiry = None
        if self._timeout_task is not None:
            self._timeout_task.cancel()
            self._timeout_task = None

    async def wait(self) -> bool:
        """Waits for the modal to be submitted."""
        return await self._stopped

    def to_dict(self) -> ModalPayload:
        """Converts this modal to the payload sent to Discord.

        Returns
        -------
        :class:`dict`
            The modal payload.
        """
        return cast(
            "ModalPayload",
            {
                "title": self.title,
                "custom_id": self.custom_id,
                "components": self.to_components(),
            },
        )

    async def on_error(self, error: Exception, interaction: Interaction) -> None:
        """|coro|

        A callback that is called when the modal's callback fails with an error.

        The default implementation prints the traceback to stderr.

        Parameters
        ----------
        error: :class:`Exception`
            The exception that was raised.
        interaction: :class:`~discord.Interaction`
            The interaction that led to the failure.
        """
        interaction.client.dispatch("modal_error", error, interaction)

    async def on_timeout(self) -> None:
        """|coro|

        A callback that is called when a modal's timeout elapses without being explicitly stopped.
        """

    def _refresh(
        self, interaction: Interaction, data: Sequence[Mapping[str, Any]]
    ) -> None:
        raise NotImplementedError

    def walk_children(self) -> Iterator[ModalItem]:
        """Iterates over the children of this modal, nested items included."""
        for item in self.children:
            yield from _walk_nested(item)


class Modal(BaseModal[InputText]):
    """Represents a legacy UI modal for InputText components.

    This object must be inherited to create a UI within Discord.

    .. versionadded:: 2.0

    .. versionchanged:: 2.7

        Now inherits from :class:`BaseModal`

    Parameters
    ----------
    children: Union[:class:`InputText`]
        The initial items that are displayed in the modal. Only supports :class:`discord.ui.InputText`; for newer modal features, see :class:`DesignerModal`.
    title: :class:`str`
        The title of the modal.
        Must be 45 characters or fewer.
    custom_id: Optional[:class:`str`]
        The ID of the modal that gets received during an interaction.
        Must be 100 characters or fewer.
    timeout: Optional[:class:`float`]
        Timeout in seconds from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.
    store: Optional[:class:`bool`]
        Whether this modal should be stored for callback listening. Setting it to ``False`` will ignore its callback and prevent item values from being refreshed. Defaults to ``True``.
    """

    def __init__(
        self,
        *children: InputText,
        title: str,
        custom_id: str | None = None,
        timeout: float | None = None,
        store: bool = True,
    ) -> None:
        super().__init__(
            *children, title=title, custom_id=custom_id, timeout=timeout, store=store
        )
        self._weights = _ModalWeights(self._children)

    @property
    @override
    def children(self) -> list[InputText]:
        return self._children

    @children.setter
    def children(self, value: list[InputText]) -> None:
        for item in value:
            if not isinstance(cast("object", item), InputText):
                raise TypeError(
                    "all Modal children must be InputText, not"
                    f" {item.__class__.__name__}"
                )
        self._children = value
        self._weights = _ModalWeights(value)

    @override
    def to_components(self) -> list[ComponentPayload]:
        def key(item: InputText) -> int:
            return item._rendered_row or 0

        children = sorted(self._children, key=key)
        components: list[ComponentPayload] = []
        for _, group in groupby(children, key=key):
            row = [item.to_component_dict() for item in group]
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

    def add_item(self, item: InputText) -> Self:
        """Adds an InputText component to the modal.

        Parameters
        ----------
        item: :class:`InputText`
            The item to add to the modal
        """
        if not isinstance(cast("object", item), InputText):
            raise TypeError(f"expected InputText not {item.__class__!r}")

        self._weights.add_item(item)
        super().add_item(item)
        return self

    def remove_item(self, item: InputText) -> Self:
        """Removes an InputText from the modal.

        Parameters
        ----------
        item: Union[class:`InputText`]
            The item to remove from the modal.
        """
        super().remove_item(item)
        with contextlib.suppress(ValueError):
            self._weights.remove_item(item)
        return self

    @override
    def _refresh(
        self, interaction: Interaction, data: Sequence[Mapping[str, Any]]
    ) -> None:
        components = [
            component
            for parent_component in data
            for component in parent_component["components"]
        ]
        for component in components:
            for child in self.children:
                if child.custom_id == component["custom_id"]:
                    child.refresh_from_modal(interaction, component)
                    break


class DesignerModal(BaseModal[ModalItem]):
    """Represents a UI modal compatible with all modal features.

    This object must be inherited to create a UI within Discord.

    .. versionadded:: 2.7

    Parameters
    ----------
    children: Union[:class:`ModalItem`]
        The initial items that are displayed in the modal..
    title: :class:`str`
        The title of the modal.
        Must be 45 characters or fewer.
    custom_id: Optional[:class:`str`]
        The ID of the modal that gets received during an interaction.
        Must be 100 characters or fewer.
    timeout: Optional[:class:`float`]
        Timeout in seconds from last interaction with the UI before no longer accepting input.
        If ``None`` then there is no timeout.
    store: Optional[:class:`bool`]
        Whether this modal should be stored for callback listening. Setting it to ``False`` will ignore its callback and prevent item values from being refreshed. Defaults to ``True``.
    """

    def __init__(
        self,
        *children: ModalItem,
        title: str,
        custom_id: str | None = None,
        timeout: float | None = None,
        store: bool = True,
    ) -> None:
        super().__init__(
            *children, title=title, custom_id=custom_id, timeout=timeout, store=store
        )

    @property
    @override
    def children(self) -> list[ModalItem]:
        return self._children

    @children.setter
    def children(self, value: list[ModalItem]) -> None:
        for item in value:
            if not isinstance(cast("object", item), ModalItem):
                raise TypeError(
                    "all DesignerModal children must be ModalItem, not"
                    f" {item.__class__.__name__}"
                )
            if isinstance(item, (InputText,)):
                raise TypeError(
                    "DesignerModal does not accept InputText directly. Use Label instead."
                )
        self._children = value

    @classmethod
    def from_dict(
        cls,
        data: ModalPayload,
        /,
        *,
        timeout: float | None = None,
    ) -> DesignerModal:
        """Converts a modal payload into a :class:`DesignerModal`.

        .. versionadded:: 3.0

        Parameters
        ----------
        data: ModalPayload
            The dict representing a modal.
        timeout: Optional[:class:`float`]
            The timeout of the converted modal.

        Returns
        -------
        :class:`DesignerModal`
            The converted modal. This always returns a :class:`DesignerModal` and not
            one of its subclasses.
        """
        modal = DesignerModal(
            title=data["title"],
            custom_id=data.get("custom_id"),
            timeout=timeout,
        )
        components = [_component_factory(d) for d in data.get("components", [])]
        for component in components:
            modal.add_item(_component_to_item(component))
        return modal

    def add_item(self, item: ModalItem) -> Self:
        """Adds a component to the modal.

        Parameters
        ----------
        item: Union[:class:`ModalItem`]
            The item to add to the modal
        """
        if isinstance(item, (InputText,)):
            raise TypeError(
                "DesignerModal does not accept InputText directly. Use Label instead."
            )

        super().add_item(item)
        return self

    def add_label(
        self,
        label: str,
        item: ModalItem | None = None,
        *,
        description: str | None = None,
        id: int | None = None,
    ) -> Self:
        """Adds a :class:`Label` to the modal.

        To append a pre-existing :class:`Label`, use :meth:`add_item` instead.

        .. versionadded:: 3.0

        Parameters
        ----------
        label: :class:`str`
            The label text. Must be 45 characters or fewer.
        item: Optional[:class:`ModalItem`]
            The initial item attached to this label.
        description: Optional[:class:`str`]
            The description for this label. Must be 100 characters or fewer.
        id: Optional[:class:`int`]
            The label's ID.
        """
        return self.add_item(Label(label, item, description=description, id=id))

    def add_text(self, content: str, id: int | None = None) -> Self:
        """Adds a :class:`TextDisplay` to the modal.

        .. versionadded:: 3.0

        Parameters
        ----------
        content: :class:`str`
            The content of the text display.
        id: Optional[:class:`int`]
            The text display's ID.
        """
        return self.add_item(TextDisplay(content, id=id))

    @override
    def _refresh(
        self, interaction: Interaction, data: Sequence[Mapping[str, Any]]
    ) -> None:
        for component, child in zip(data, self.children, strict=False):
            child.refresh_from_modal(interaction, component)


def _row_key(item: InputText) -> int:
    return sys.maxsize if item.row is None else item.row


class _ModalWeights:
    __slots__ = ("weights",)

    def __init__(self, children: list[InputText]) -> None:
        self.weights: list[int] = [0] * ComponentLimits.MODAL_COMPONENTS_MAX

        children = sorted(children, key=_row_key)
        for _row, group in groupby(children, key=_row_key):
            for item in group:
                self.add_item(item)

    def find_open_space(self, item: InputText) -> int:
        for index, weight in enumerate(self.weights):
            if weight + item.width <= ComponentLimits.ACTION_ROW_CHILDREN_MAX:
                return index

        raise ValueError("could not find open space for item")

    def add_item(self, item: InputText) -> None:
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

    def remove_item(self, item: InputText) -> None:
        if item._rendered_row is not None:
            self.weights[item._rendered_row] -= item.width
            item._rendered_row = None

    def clear(self) -> None:
        self.weights = [0] * ComponentLimits.MODAL_COMPONENTS_MAX


class ModalStore:
    """Stores the modals waiting for a submission, by user and custom ID."""

    def __init__(self, state: ConnectionState) -> None:
        # (user_id, custom_id) : Modal
        self._modals: dict[tuple[int, str], BaseModal] = {}
        self._state: ConnectionState = state

    def add_modal(self, modal: BaseModal, user_id: int) -> None:
        """Stores a modal and starts listening to its submission.

        Parameters
        ----------
        modal
            The modal to store.
        user_id
            The ID of the user the modal was sent to.
        """
        if not modal._store:
            return
        self._modals[(user_id, modal.custom_id)] = modal
        modal._start_listening_from_store(self)

    def remove_modal(self, modal: BaseModal, user_id: int) -> None:
        """Stops and forgets a stored modal.

        Parameters
        ----------
        modal
            The modal to remove.
        user_id
            The ID of the user the modal was sent to.
        """
        modal.stop()
        self._modals.pop((user_id, modal.custom_id))

    async def dispatch(
        self, user_id: int, custom_id: str, interaction: Interaction
    ) -> None:
        """|coro|

        Dispatches a modal submission to the stored modal.

        Parameters
        ----------
        user_id
            The ID of the user that submitted the modal.
        custom_id
            The custom ID of the submitted modal.
        interaction
            The interaction of the submission.
        """
        key = (user_id, custom_id)
        modal = self._modals.get(key)
        if modal is None:
            return None
        interaction.modal = modal

        try:
            components = cast("Mapping[str, Any]", interaction.data)["components"]
            modal._refresh(interaction, components)
            for child in modal.walk_children():
                await child._resolve_state()
            await modal.callback(interaction)
            self.remove_modal(modal, user_id)
        except Exception as e:
            return await modal.on_error(e, interaction)
