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
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from typing_extensions import override

import discord
from discord.errors import DiscordException
from discord.ext.bridge import BridgeContext
from discord.ext.commands import Context

if TYPE_CHECKING:
    from discord.file import File
    from discord.member import Member
    from discord.user import User

    PageContent = (
        str | discord.Embed | list[discord.Embed] | discord.File | list[discord.File]
    )

__all__ = (
    "Page",
    "PageGroup",
    "Paginator",
    "PaginatorButton",
    "PaginatorMenu",
)

from ...utils import warn_deprecated


def _embeds_of(page: Page) -> list[discord.Embed]:
    return cast("list[discord.Embed]", page.embeds)


def _files_of(page: Page) -> list[discord.File]:
    return cast("list[discord.File]", page.files)


class PaginatorButton(discord.ui.Button):
    """Creates a button used to navigate the paginator.

    Parameters
    ----------
    button_type: :class:`str`
        The type of button being created.
        Must be one of ``first``, ``prev``, ``next``, ``last``, or ``page_indicator``.
    label: :class:`str`
        The label shown on the button.
        Defaults to a capitalized version of ``button_type`` (e.g. "Next", "Prev", etc.)
    emoji: Union[:class:`str`, :class:`discord.GuildEmoji`, :class:`discord.AppEmoji`, :class:`discord.PartialEmoji`]
        The emoji shown on the button in front of the label.
    disabled: :class:`bool`
        Whether to initially show the button as disabled.
    loop_label: :class:`str`
        The label shown on the button when ``loop_pages`` is set to ``True`` in the Paginator class.

    Attributes
    ----------
    paginator: :class:`Paginator`
        The paginator class where this button is being used.
        Assigned to the button when ``Paginator.add_button`` is called.
    """

    def __init__(
        self,
        button_type: str,
        label: str | None = None,
        emoji: (
            str | discord.GuildEmoji | discord.AppEmoji | discord.PartialEmoji | None
        ) = None,
        style: discord.ButtonStyle = discord.ButtonStyle.green,
        disabled: bool = False,
        custom_id: str | None = None,
        row: int = 0,
        loop_label: str | None = None,
    ) -> None:
        super().__init__(
            label=label if label or emoji else button_type.capitalize(),
            emoji=emoji,
            style=style,
            disabled=disabled,
            custom_id=custom_id,
            row=row,
        )
        self.button_type: str = button_type
        self.label = label if label or emoji else button_type.capitalize()
        self.emoji: (
            str | discord.GuildEmoji | discord.AppEmoji | discord.PartialEmoji | None
        ) = emoji
        self.style = style
        self.disabled = disabled
        self.loop_label: str | None = loop_label or self.label
        self.paginator: Paginator | None = None

    async def callback(self, interaction: discord.Interaction) -> None:
        """|coro|

        The coroutine that is called when the navigation button is clicked.

        Parameters
        ----------
        interaction: :class:`discord.Interaction`
            The interaction created by clicking the navigation button.
        """
        paginator = cast("Paginator", self.paginator)
        new_page = paginator.current_page
        if self.button_type == "first":
            new_page = 0
        elif self.button_type == "prev":
            if paginator.loop_pages and paginator.current_page == 0:
                new_page = paginator.page_count
            else:
                new_page -= 1
        elif self.button_type == "next":
            if paginator.loop_pages and paginator.current_page == paginator.page_count:
                new_page = 0
            else:
                new_page += 1
        elif self.button_type == "last":
            new_page = paginator.page_count
        await paginator.goto_page(page_number=new_page, interaction=interaction)


class Page:
    """Represents a page shown in the paginator.

    Allows for directly referencing and modifying each page as a class instance.

    Parameters
    ----------
    content: :class:`str`
        The content of the page. Corresponds to the :class:`discord.Message.content` attribute.
    embeds: Optional[List[Union[List[:class:`discord.Embed`], :class:`discord.Embed`]]]
        The embeds of the page. Corresponds to the :class:`discord.Message.embeds` attribute.
    files: Optional[List[:class:`discord.File`]]
        A list of local files to be shown with the page.
    custom_view: Optional[:class:`discord.ui.View`]
        The custom view shown when the page is visible. Overrides the `custom_view` attribute of the main paginator.
    """

    def __init__(
        self,
        content: str | None = None,
        embeds: list[list[discord.Embed] | discord.Embed] | None = None,
        custom_view: discord.ui.View | None = None,
        files: list[discord.File] | None = None,
        **kwargs: Any,
    ) -> None:
        if content is None and embeds is None and custom_view is None:
            raise discord.InvalidArgument(
                "A page must at least have content, embeds, or custom_view set."
            )
        self._content = content
        self._embeds = embeds or []
        self._custom_view = custom_view
        self._files = files or []

    async def callback(self, interaction: discord.Interaction | None = None) -> None:
        """|coro|

        The coroutine associated with a specific page. If `Paginator.page_action()` is used, this coroutine is called.

        Parameters
        ----------
        interaction: Optional[:class:`discord.Interaction`]
            The interaction associated with the callback, if any.
        """

    def update_files(self) -> list[discord.File] | None:
        """Updates :class:`discord.File` objects so that they can be sent multiple times.

        This is called internally each time the page is sent.

        """
        for file in cast("list[discord.File]", self._files):
            if file.fp.closed and (fn := getattr(file.fp, "name", None)):
                file.fp = Path(fn).open("rb")
            file.reset()
            cast("Any", file.fp).close = lambda: None
        return self._files

    @property
    def content(self) -> str | None:
        """Gets the content for the page."""
        return self._content

    @content.setter
    def content(self, value: str | None) -> None:
        """Sets the content for the page."""
        self._content = value

    @property
    def embeds(self) -> list[list[discord.Embed] | discord.Embed] | None:
        """Gets the embeds for the page."""
        return self._embeds

    @embeds.setter
    def embeds(self, value: list[list[discord.Embed] | discord.Embed] | None) -> None:
        """Sets the embeds for the page."""
        self._embeds = value

    @property
    def custom_view(self) -> discord.ui.View | None:
        """Gets the custom view assigned to the page."""
        return self._custom_view

    @custom_view.setter
    def custom_view(self, value: discord.ui.View | None) -> None:
        """Assigns a custom view to be shown when the page is displayed."""
        self._custom_view = value

    @property
    def files(self) -> list[discord.File] | None:
        """Gets the files associated with the page."""
        return self._files

    @files.setter
    def files(self, value: list[discord.File] | None) -> None:
        """Sets the files associated with the page."""
        self._files = value


class PageGroup:
    """Creates a group of pages which the user can switch between.

    Each group of pages can have its own options, custom buttons, custom views, etc.

    .. note::

        If multiple :class:`PageGroup` objects have different options,
        they should all be set explicitly when creating each instance.

    Parameters
    ----------
    pages: Union[List[:class:`str`], List[:class:`Page`], List[Union[List[:class:`discord.Embed`], :class:`discord.Embed`]]]
        The list of :class:`Page` objects, strings, embeds, or list of embeds to include in the page group.
    label: :class:`str`
        The label shown on the corresponding PaginatorMenu dropdown option.
        Also used as the SelectOption value.
    description: Optional[:class:`str`]
        The description shown on the corresponding PaginatorMenu dropdown option.
    emoji: Union[:class:`str`, :class:`discord.GuildEmoji`, :class:`discord.AppEmoji`, :class:`discord.PartialEmoji`]
        The emoji shown on the corresponding PaginatorMenu dropdown option.
    default: Optional[:class:`bool`]
        Whether the page group should be the default page group initially shown when the paginator response is sent.
        Only one ``PageGroup`` can be the default page group.
    show_disabled: :class:`bool`
        Whether to show disabled buttons.
    show_indicator: :class:`bool`
        Whether to show the page indicator when using the default buttons.
    author_check: :class:`bool`
        Whether only the original user of the command can change pages.
    disable_on_timeout: :class:`bool`
        Whether the buttons get disabled when the paginator view times out.
    use_default_buttons: :class:`bool`
        Whether to use the default buttons (i.e. ``first``, ``prev``, ``page_indicator``, ``next``, ``last``)
    default_button_row: :class:`int`
        The row where the default paginator buttons are displayed. Has no effect if custom buttons are used.
    loop_pages: :class:`bool`
        Whether to loop the pages when clicking prev/next while at the first/last page in the list.
    custom_view: Optional[:class:`discord.ui.View`]
        A custom view whose items are appended below the pagination buttons.
    timeout: Optional[:class:`float`]
        Timeout in seconds from last interaction with the paginator before no longer accepting input.
    custom_buttons: Optional[List[:class:`PaginatorButton`]]
        A list of PaginatorButtons to initialize the Paginator with.
        If ``use_default_buttons`` is ``True``, this parameter is ignored.
    trigger_on_display: :class:`bool`
        Whether to automatically trigger the callback associated with a `Page` whenever it is displayed.
        Has no effect if no callback exists for a `Page`.
    """

    def __init__(
        self,
        pages: list[str] | list[Page] | list[list[discord.Embed] | discord.Embed],
        label: str,
        description: str | None = None,
        emoji: (
            str | discord.GuildEmoji | discord.AppEmoji | discord.PartialEmoji | None
        ) = None,
        default: bool | None = None,
        show_disabled: bool | None = None,
        show_indicator: bool | None = None,
        author_check: bool | None = None,
        disable_on_timeout: bool | None = None,
        use_default_buttons: bool | None = None,
        default_button_row: int = 0,
        loop_pages: bool | None = None,
        custom_view: discord.ui.View | None = None,
        timeout: float | None = None,
        custom_buttons: list[PaginatorButton] | None = None,
        trigger_on_display: bool | None = None,
    ) -> None:
        self.label: str = label
        self.description: str | None = description
        self.emoji: (
            str | discord.GuildEmoji | discord.AppEmoji | discord.PartialEmoji | None
        ) = emoji
        self.pages: (
            list[str] | list[Page] | list[list[discord.Embed] | discord.Embed]
        ) = pages
        self.default: bool | None = default
        self.show_disabled: bool | None = show_disabled
        self.show_indicator: bool | None = show_indicator
        self.author_check: bool | None = author_check
        self.disable_on_timeout: bool | None = disable_on_timeout
        self.use_default_buttons: bool | None = use_default_buttons
        self.default_button_row: int = default_button_row
        self.loop_pages: bool | None = loop_pages
        self.custom_view: discord.ui.View | None = custom_view
        self.timeout: float | None = timeout
        self.custom_buttons: list[PaginatorButton] | None = custom_buttons
        self.trigger_on_display: bool | None = trigger_on_display


class Paginator(discord.ui.View):
    """Creates a paginator which can be sent as a message and uses buttons for navigation.

    Parameters
    ----------
    pages: Union[List[:class:`PageGroup`], List[:class:`Page`], List[:class:`str`], List[Union[List[:class:`discord.Embed`], :class:`discord.Embed`]]]
        The list of :class:`PageGroup` objects, :class:`Page` objects, strings, embeds, or list of embeds to paginate.
        If a list of :class:`PageGroup` objects is provided and `show_menu` is ``False``,
        only the first page group will be displayed.
    show_disabled: :class:`bool`
        Whether to show disabled buttons.
    show_indicator: :class:`bool`
        Whether to show the page indicator when using the default buttons.
    show_menu: :class:`bool`
        Whether to show a select menu that allows the user to switch between groups of pages.
    menu_placeholder: :class:`str`
        The placeholder text to show in the page group menu when no page group has been selected yet.
        Defaults to "Select Page Group" if not provided.
    author_check: :class:`bool`
        Whether only the original user of the command can change pages.
    disable_on_timeout: :class:`bool`
        Whether the buttons get disabled when the paginator view times out.
    use_default_buttons: :class:`bool`
        Whether to use the default buttons (i.e. ``first``, ``prev``, ``page_indicator``, ``next``, ``last``)
    default_button_row: :class:`int`
        The row where the default paginator buttons are displayed. Has no effect if custom buttons are used.
    loop_pages: :class:`bool`
        Whether to loop the pages when clicking prev/next while at the first/last page in the list.
    custom_view: Optional[:class:`discord.ui.View`]
        A custom view whose items are appended below the pagination components.
        If the currently displayed page has a `custom_view` assigned, it will replace these
        view components when that page is displayed.
    timeout: Optional[:class:`float`]
        Timeout in seconds from last interaction with the paginator before no longer accepting input.
    custom_buttons: Optional[List[:class:`PaginatorButton`]]
        A list of PaginatorButtons to initialize the Paginator with.
        If ``use_default_buttons`` is ``True``, this parameter is ignored.
    trigger_on_display: :class:`bool`
        Whether to automatically trigger the callback associated with a `Page` whenever it is displayed.
        Has no effect if no callback exists for a `Page`.

    Attributes
    ----------
    menu: Optional[List[:class:`PaginatorMenu`]]
        The page group select menu associated with this paginator.
    page_groups: Optional[List[:class:`PageGroup`]]
        List of :class:`PageGroup` objects the user can switch between.
    default_page_group: Optional[:class:`int`]
        The index of the default page group shown when the paginator is initially sent.
        Defined by setting ``default`` to ``True`` on a :class:`PageGroup`.
    current_page: :class:`int`
        A zero-indexed value showing the current page number.
    page_count: :class:`int`
        A zero-indexed value showing the total number of pages.
    buttons: Dict[:class:`str`, Dict[:class:`str`, Union[:class:`~PaginatorButton`, :class:`bool`]]]
        A dictionary containing the :class:`~PaginatorButton` objects included in this paginator.
    user: Optional[Union[:class:`~discord.User`, :class:`~discord.Member`]]
        The user or member that invoked the paginator.
    message: Union[:class:`~discord.Message`, :class:`~discord.WebhookMessage`]
        The message the paginator is attached to.
    """

    def __init__(
        self,
        pages: (
            list[PageGroup]
            | list[Page]
            | list[str]
            | list[list[discord.Embed] | discord.Embed]
        ),
        show_disabled: bool = True,
        show_indicator: bool = True,
        show_menu: bool = False,
        menu_placeholder: str = "Select Page Group",
        author_check: bool = True,
        disable_on_timeout: bool = True,
        use_default_buttons: bool = True,
        default_button_row: int = 0,
        loop_pages: bool = False,
        custom_view: discord.ui.View | None = None,
        timeout: float | None = 180.0,
        custom_buttons: list[PaginatorButton] | None = None,
        trigger_on_display: bool | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.timeout: float | None = timeout
        self.pages: (
            list[PageGroup]
            | list[str]
            | list[Page]
            | list[list[discord.Embed] | discord.Embed]
        ) = pages
        self.current_page: int = 0
        self.menu: PaginatorMenu | None = None
        self.show_menu: bool = show_menu
        self.menu_placeholder: str = menu_placeholder
        self.page_groups: list[PageGroup] | None = None
        self.default_page_group: int = 0

        if pages and all(isinstance(pg, PageGroup) for pg in pages):
            groups = cast("list[PageGroup]", pages)
            if sum(pg.default is True for pg in groups) > 1:
                raise ValueError("Only one PageGroup can be set as the default.")

            default_pg_index = 0
            for pg in groups:
                if pg.default:
                    default_pg_index = groups.index(pg)
                    break

            self.pages = self.get_page_group_content(groups[default_pg_index])

            self.page_groups = groups if show_menu else None
        self.page_count: int = max(len(self.pages) - 1, 0)
        self.buttons: dict[str, dict[str, Any]] = {}
        self.custom_buttons: list[PaginatorButton] | None = custom_buttons
        self.show_disabled: bool = show_disabled
        self.show_indicator: bool = show_indicator
        self.disable_on_timeout: bool = disable_on_timeout
        self.use_default_buttons: bool = use_default_buttons
        self.default_button_row: int = default_button_row
        self.loop_pages: bool = loop_pages
        self.custom_view: discord.ui.View | None = custom_view
        self.trigger_on_display: bool | None = trigger_on_display
        self.message: discord.Message | discord.WebhookMessage | None = None

        if self.custom_buttons and not self.use_default_buttons:
            for button in self.custom_buttons:
                self.add_button(button)
        elif not self.custom_buttons and self.use_default_buttons:
            self.add_default_buttons()

        if self.show_menu:
            self.add_menu()

        self.usercheck: bool = author_check
        self.user: User | Member | None = None

    async def update(
        self,
        pages: (
            list[PageGroup]
            | list[Page]
            | list[str]
            | list[list[discord.Embed] | discord.Embed]
            | None
        ) = None,
        show_disabled: bool | None = None,
        show_indicator: bool | None = None,
        show_menu: bool | None = None,
        author_check: bool | None = None,
        menu_placeholder: str | None = None,
        disable_on_timeout: bool | None = None,
        use_default_buttons: bool | None = None,
        default_button_row: int | None = None,
        loop_pages: bool | None = None,
        custom_view: discord.ui.View | None = None,
        timeout: float | None = None,
        custom_buttons: list[PaginatorButton] | None = None,
        trigger_on_display: bool | None = None,
        interaction: discord.Interaction | None = None,
        current_page: int = 0,
    ) -> None:
        """Updates the existing :class:`Paginator` instance with the provided options.

        Parameters
        ----------
        pages: Optional[Union[List[:class:`PageGroup`], List[:class:`Page`], List[:class:`str`], List[Union[List[:class:`discord.Embed`], :class:`discord.Embed`]]]]
            The list of :class:`PageGroup` objects, :class:`Page` objects, strings,
            embeds, or list of embeds to paginate.
        show_disabled: :class:`bool`
            Whether to show disabled buttons.
        show_indicator: :class:`bool`
            Whether to show the page indicator when using the default buttons.
        show_menu: :class:`bool`
            Whether to show a select menu that allows the user to switch between groups of pages.
        author_check: :class:`bool`
            Whether only the original user of the command can change pages.
        menu_placeholder: :class:`str`
            The placeholder text to show in the page group menu when no page group has been selected yet.
            Defaults to "Select Page Group" if not provided.
        disable_on_timeout: :class:`bool`
            Whether the buttons get disabled when the paginator view times out.
        use_default_buttons: :class:`bool`
            Whether to use the default buttons (i.e. ``first``, ``prev``, ``page_indicator``, ``next``, ``last``)
        default_button_row: Optional[:class:`int`]
            The row where the default paginator buttons are displayed. Has no effect if custom buttons are used.
        loop_pages: :class:`bool`
            Whether to loop the pages when clicking prev/next while at the first/last page in the list.
        custom_view: Optional[:class:`discord.ui.View`]
            A custom view whose items are appended below the pagination components.
        timeout: Optional[:class:`float`]
            Timeout in seconds from last interaction with the paginator before no longer accepting input.
        custom_buttons: Optional[List[:class:`PaginatorButton`]]
            A list of PaginatorButtons to initialize the Paginator with.
            If ``use_default_buttons`` is ``True``, this parameter is ignored.
        trigger_on_display: :class:`bool`
            Whether to automatically trigger the callback associated with a `Page` whenever it is displayed.
            Has no effect if no callback exists for a `Page`.
        interaction: Optional[:class:`discord.Interaction`]
            The interaction to use when updating the paginator. If not provided, the paginator will be updated
            by using its stored :attr:`message` attribute instead.
        current_page: :class:`int`
            The initial page number to display when updating the paginator.
        """
        # Update pages and reset current_page to 0 (default)
        self.pages = pages if pages is not None else self.pages
        self.show_menu = show_menu if show_menu is not None else self.show_menu
        if pages and all(isinstance(pg, PageGroup) for pg in pages):
            groups = cast("list[PageGroup]", pages)
            if sum(pg.default is True for pg in groups) > 1:
                raise ValueError("Only one PageGroup can be set as the default.")

            default_pg_index = 0
            for pg in groups:
                if pg.default:
                    default_pg_index = groups.index(pg)
                    break

            self.pages = self.get_page_group_content(groups[default_pg_index])

            self.page_groups = groups if show_menu else None
        self.page_count = max(len(self.pages) - 1, 0)
        self.current_page = current_page if current_page <= self.page_count else 0
        # Apply config changes, if specified
        self.show_disabled = (
            show_disabled if show_disabled is not None else self.show_disabled
        )
        self.show_indicator = (
            show_indicator if show_indicator is not None else self.show_indicator
        )
        self.usercheck = author_check if author_check is not None else self.usercheck
        self.menu_placeholder = (
            menu_placeholder if menu_placeholder is not None else self.menu_placeholder
        )
        self.disable_on_timeout = (
            disable_on_timeout
            if disable_on_timeout is not None
            else self.disable_on_timeout
        )
        self.use_default_buttons = (
            use_default_buttons
            if use_default_buttons is not None
            else self.use_default_buttons
        )
        self.default_button_row = (
            default_button_row
            if default_button_row is not None
            else self.default_button_row
        )
        self.loop_pages = loop_pages if loop_pages is not None else self.loop_pages
        self.custom_view = custom_view
        self.timeout = timeout if timeout is not None else self.timeout
        self.custom_buttons = (
            custom_buttons if custom_buttons is not None else self.custom_buttons
        )
        self.trigger_on_display = (
            trigger_on_display
            if trigger_on_display is not None
            else self.trigger_on_display
        )
        self.buttons = {}
        if self.use_default_buttons:
            self.add_default_buttons()
        elif self.custom_buttons:
            for button in self.custom_buttons:
                self.add_button(button)

        await self.goto_page(self.current_page, interaction=interaction)

    async def on_timeout(self) -> None:
        """Disables all buttons when the view times out."""
        if self.disable_on_timeout:
            for item in self.walk_children():
                if hasattr(item, "disabled"):
                    cast("Any", item).disabled = True
            page = self.get_page_content(self._page_at(self.current_page))
            files = page.update_files()
            with contextlib.suppress(discord.NotFound, discord.Forbidden):
                await self._current_message().edit(
                    view=self,
                    files=files or [],
                    attachments=[],
                )

    async def disable(
        self,
        include_custom: bool = False,
        page: str | Page | list[discord.Embed] | discord.Embed | None = None,
    ) -> None:
        """Stops the paginator, disabling all of its components.

        Parameters
        ----------
        include_custom: :class:`bool`
            Whether to disable components added via custom views.
        page: Optional[Union[:class:`str`, Union[List[:class:`discord.Embed`], :class:`discord.Embed`]]]
            The page content to show after disabling the paginator.
        """
        page_content = (
            None if page is None else self.get_page_content(cast("PageContent", page))
        )
        for item in self.walk_children():
            if (
                include_custom
                or not self.custom_view
                or item not in self.custom_view.children
            ) and hasattr(item, "disabled"):
                cast("Any", item).disabled = True
        if page_content:
            await self._current_message().edit(
                content=page_content.content,
                embeds=_embeds_of(page_content),
                view=self,
            )
        else:
            await self._current_message().edit(view=self)

    async def cancel(
        self,
        include_custom: bool = False,
        page: str | Page | list[discord.Embed] | discord.Embed | None = None,
    ) -> None:
        """Cancels the paginator, removing all of its components from the message.

        Parameters
        ----------
        include_custom: :class:`bool`
            Whether to remove components added via custom views.
        page: Optional[Union[:class:`str`, Union[List[:class:`discord.Embed`], :class:`discord.Embed`]]]
            The page content to show after canceling the paginator.
        """
        items = self.children.copy()
        page_content = (
            None if page is None else self.get_page_content(cast("PageContent", page))
        )
        for item in items:
            if (
                include_custom
                or not self.custom_view
                or item not in self.custom_view.children
            ):
                self.remove_item(item)
        if page_content:
            await self._current_message().edit(
                content=page_content.content,
                embeds=_embeds_of(page_content),
                view=self,
            )
        else:
            await self._current_message().edit(view=self)

    def _goto_page(self, page_number: int = 0) -> tuple[Page, list[File] | None]:
        self.current_page = page_number
        self.update_buttons()

        page = self.get_page_content(self._page_at(page_number))

        if page.custom_view:
            self.update_custom_view(page.custom_view)

        files = page.update_files()

        return page, files

    async def goto_page(
        self, page_number: int = 0, *, interaction: discord.Interaction | None = None
    ) -> None:
        """Updates the paginator message to show the specified page number.

        Parameters
        ----------
        page_number: :class:`int`
            The page to display.

            .. note::

                Page numbers are zero-indexed when referenced internally,
                but appear as one-indexed when shown to the user.

        interaction: Optional[:class:`discord.Interaction`]
            The interaction to use when editing the message. If not provided, the message will be
            edited using the paginator's stored :attr:`message` attribute instead.

        Returns
        -------
        :class:`~discord.Message`
            The message associated with the paginator.
        """
        old_page = self.current_page
        page, files = self._goto_page(page_number)

        try:
            if interaction:
                await (
                    interaction.response.defer()
                )  # needed to force webhook message edit route for files kwarg support
                await interaction.followup.edit_message(
                    message_id=self._current_message().id,
                    content=page.content,
                    embeds=_embeds_of(page),
                    attachments=[],
                    files=files or [],
                    view=self,
                )
            else:
                await self._current_message().edit(
                    content=page.content,
                    embeds=_embeds_of(page),
                    attachments=[],
                    files=files or [],
                    view=self,
                )
        except DiscordException:
            # Something went wrong, and the paginator couldn't be updated.
            # Revert our changes and propagate the error.
            self._goto_page(old_page)
            raise

        if self.trigger_on_display:
            await self.page_action(interaction=interaction)

    @override
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.usercheck:
            return self.user == interaction.user
        return True

    def add_menu(self) -> None:
        """Adds the default :class:`PaginatorMenu` instance to the paginator."""
        self.menu = PaginatorMenu(
            cast("list[PageGroup]", self.page_groups), placeholder=self.menu_placeholder
        )
        self.menu.paginator = self
        self.add_item(self.menu)

    def add_default_buttons(self) -> None:
        """Adds the full list of default buttons that can be used with the paginator.

        Includes ``first``, ``prev``, ``page_indicator``, ``next``, and ``last``.

        """
        default_buttons = [
            PaginatorButton(
                "first",
                label="<<",
                style=discord.ButtonStyle.blurple,
                row=self.default_button_row,
            ),
            PaginatorButton(
                "prev",
                label="<",
                style=discord.ButtonStyle.red,
                loop_label="↪",
                row=self.default_button_row,
            ),
            PaginatorButton(
                "page_indicator",
                style=discord.ButtonStyle.gray,
                disabled=True,
                row=self.default_button_row,
            ),
            PaginatorButton(
                "next",
                label=">",
                style=discord.ButtonStyle.green,
                loop_label="↩",
                row=self.default_button_row,
            ),
            PaginatorButton(
                "last",
                label=">>",
                style=discord.ButtonStyle.blurple,
                row=self.default_button_row,
            ),
        ]
        for button in default_buttons:
            self.add_button(button)

    def add_button(self, button: PaginatorButton) -> None:
        """Adds a :class:`PaginatorButton` to the paginator."""
        self.buttons[button.button_type] = {
            "object": discord.ui.Button(
                style=button.style,
                label=(
                    button.label
                    if button.label or button.emoji
                    else (
                        button.button_type.capitalize()
                        if button.button_type != "page_indicator"
                        else f"{self.current_page + 1}/{self.page_count + 1}"
                    )
                ),
                disabled=button.disabled,
                custom_id=button.custom_id,
                emoji=button.emoji,
                row=button.row,
            ),
            "label": button.label,
            "loop_label": button.loop_label,
            "hidden": (
                button.disabled
                if button.button_type != "page_indicator"
                else not self.show_indicator
            ),
        }
        self.buttons[button.button_type]["object"].callback = button.callback
        button.paginator = self

    def remove_button(self, button_type: str) -> None:
        """Removes a :class:`PaginatorButton` from the paginator."""
        if button_type not in self.buttons:
            raise ValueError(
                f"no button_type {button_type} was found in this paginator."
            )
        self.buttons.pop(button_type)

    def update_buttons(self) -> dict[str, dict[str, Any]]:
        """Updates the display state of the buttons (disabled/hidden)

        Returns
        -------
        Dict[:class:`str`, Dict[:class:`str`, Union[:class:`~PaginatorButton`, :class:`bool`]]]
            The dictionary of buttons that were updated.
        """
        for key, button in self.buttons.items():
            if key == "first":
                if self.current_page <= 1:
                    button["hidden"] = True
                elif self.current_page >= 1:
                    button["hidden"] = False
            elif key == "last":
                if self.current_page >= self.page_count - 1:
                    button["hidden"] = True
                if self.current_page < self.page_count - 1:
                    button["hidden"] = False
            elif key == "next":
                if self.current_page == self.page_count:
                    if not self.loop_pages:
                        button["hidden"] = True
                        button["object"].label = button["label"]
                    else:
                        button["object"].label = button["loop_label"]
                elif self.current_page < self.page_count:
                    button["hidden"] = False
                    button["object"].label = button["label"]
            elif key == "prev":
                if self.current_page <= 0:
                    if not self.loop_pages:
                        button["hidden"] = True
                        button["object"].label = button["label"]
                    else:
                        button["object"].label = button["loop_label"]
                elif self.current_page >= 0:
                    button["hidden"] = False
                    button["object"].label = button["label"]
        self.clear_items()
        if self.show_indicator:
            with contextlib.suppress(KeyError):
                self.buttons["page_indicator"][
                    "object"
                ].label = f"{self.current_page + 1}/{self.page_count + 1}"
        for key, button in self.buttons.items():
            if key != "page_indicator":
                if button["hidden"]:
                    button["object"].disabled = True
                    if self.show_disabled:
                        self.add_item(button["object"])
                else:
                    button["object"].disabled = False
                    self.add_item(button["object"])
            elif self.show_indicator:
                self.add_item(button["object"])

        if self.show_menu:
            self.add_menu()

        # We're done adding standard buttons and menus, so we can now add any specified custom view items below them
        # The bot developer should handle row assignments for their view before passing it to Paginator
        if self.custom_view:
            self.update_custom_view(self.custom_view)

        return self.buttons

    def update_custom_view(self, custom_view: discord.ui.View) -> None:
        """Updates the custom view shown on the paginator."""
        if isinstance(self.custom_view, discord.ui.View):
            for item in self.custom_view.children:
                if item in self.children:
                    self.remove_item(item)
        for item in custom_view.children:
            self.add_item(item)

    def _page_at(self, index: int) -> Page | PageContent:
        return cast("Page | PageContent", self.pages[index])

    def _current_message(self) -> discord.Message | discord.WebhookMessage:
        return cast("discord.Message | discord.WebhookMessage", self.message)

    def get_page_group_content(self, page_group: PageGroup) -> list[Page]:
        """Returns a converted list of `Page` objects for the given page group based on the content of its pages."""
        return [self.get_page_content(page) for page in page_group.pages]

    @staticmethod
    def get_page_content(page: Page | PageContent) -> Page:
        """Converts a page into a :class:`Page` object based on its content."""
        if isinstance(page, Page):
            return page
        if isinstance(page, str):
            return Page(content=page, embeds=[], files=[])
        if isinstance(page, discord.Embed):
            return Page(content=None, embeds=[page], files=[])
        if isinstance(page, discord.File):
            return Page(content=None, embeds=[], files=[page])
        if isinstance(page, discord.ui.View):
            return Page(content=None, embeds=[], files=[], custom_view=page)
        if isinstance(cast("object", page), list):
            items = cast("list[Any]", page)
            if all(isinstance(x, discord.Embed) for x in items):
                return Page(content=None, embeds=items, files=[])
            if all(isinstance(x, discord.File) for x in items):
                return Page(content=None, embeds=[], files=items)
            raise TypeError("All list items must be embeds or files.")
        raise TypeError(
            "Page content must be a Page object, string, an embed, a view, a list of"
            " embeds, a file, or a list of files."
        )

    async def page_action(self, interaction: discord.Interaction | None = None) -> None:
        """Triggers the callback associated with the current page, if any.

        Parameters
        ----------
        interaction: Optional[:class:`discord.Interaction`]
            The interaction that was used to trigger the page action.
        """
        page = self.get_page_content(self._page_at(self.current_page))
        await page.callback(interaction=interaction)

    async def send(
        self,
        ctx: Context[Any],
        target: discord.abc.Messageable | None = None,
        target_message: str | None = None,
        reference: (
            discord.Message | discord.MessageReference | discord.PartialMessage | None
        ) = None,
        allowed_mentions: discord.AllowedMentions | None = None,
        mention_author: bool | None = None,
        delete_after: float | None = None,
    ) -> discord.Message:
        """Sends a message with the paginated items.

        Parameters
        ----------
        ctx: Union[:class:`~discord.ext.commands.Context`]
            A command's invocation context.
        target: Optional[:class:`~discord.abc.Messageable`]
            A target where the paginated message should be sent, if different from the original :class:`Context`
        target_message: Optional[:class:`str`]
            An optional message shown when the paginator message is sent elsewhere.
        reference: Optional[Union[:class:`discord.Message`, :class:`discord.MessageReference`, :class:`discord.PartialMessage`]]
            A reference to the :class:`~discord.Message` to which you are replying with the paginator.
            This can be created using :meth:`~discord.Message.to_reference` or passed directly as a
            :class:`~discord.Message`. You can control whether this mentions the author of the referenced message
            using the :attr:`~discord.AllowedMentions.replied_user` attribute of ``allowed_mentions`` or by
            setting ``mention_author``.
        allowed_mentions: Optional[:class:`~discord.AllowedMentions`]
            Controls the mentions being processed in this message. If this is
            passed, then the object is merged with :attr:`~discord.Client.allowed_mentions`.
            The merging behaviour only overrides attributes that have been explicitly passed
            to the object, otherwise it uses the attributes set in :attr:`~discord.Client.allowed_mentions`.
            If no object is passed at all then the defaults given by :attr:`~discord.Client.allowed_mentions`
            are used instead.
        mention_author: Optional[:class:`bool`]
            If set, overrides the :attr:`~discord.AllowedMentions.replied_user` attribute of ``allowed_mentions``.
        delete_after: Optional[:class:`float`]
            If set, deletes the paginator after the specified time.

        Returns
        -------
        :class:`~discord.Message`
            The message that was sent with the paginator.
        """
        if not isinstance(cast("object", ctx), Context):
            raise TypeError(f"expected Context not {ctx.__class__!r}")

        target_obj = cast("object", target)
        if target_obj is not None and not isinstance(
            target_obj, discord.abc.Messageable
        ):
            raise TypeError(f"expected abc.Messageable not {target_obj.__class__!r}")

        reference_obj = cast("object", reference)
        if reference_obj is not None and not isinstance(
            reference_obj,
            (discord.Message, discord.MessageReference, discord.PartialMessage),
        ):
            raise TypeError(
                "expected Message, MessageReference, or PartialMessage not"
                f" {reference_obj.__class__!r}"
            )

        mentions_obj = cast("object", allowed_mentions)
        if mentions_obj is not None and not isinstance(
            mentions_obj, discord.AllowedMentions
        ):
            raise TypeError(f"expected AllowedMentions not {mentions_obj.__class__!r}")

        author_obj = cast("object", mention_author)
        if author_obj is not None and not isinstance(author_obj, bool):
            raise TypeError(f"expected bool not {author_obj.__class__!r}")

        self.update_buttons()
        page_content = self.get_page_content(self._page_at(self.current_page))

        if page_content.custom_view:
            self.update_custom_view(page_content.custom_view)

        self.user = ctx.author

        sender: discord.abc.Messageable = ctx
        if target:
            if target_message:
                await sender.send(
                    target_message,
                    reference=reference,
                    allowed_mentions=allowed_mentions,
                    mention_author=mention_author,
                )
            sender = target

        self.message = await sender.send(
            content=page_content.content,
            embeds=_embeds_of(page_content),
            files=_files_of(page_content),
            view=self,
            reference=reference,
            allowed_mentions=allowed_mentions,
            mention_author=mention_author,
            delete_after=delete_after,
        )

        return self.message

    async def edit(
        self,
        message: discord.Message,
        suppress: bool | None = None,
        suppress_embeds: bool | None = None,
        allowed_mentions: discord.AllowedMentions | None = None,
        delete_after: float | None = None,
        user: User | Member | None = None,
    ) -> discord.Message | None:
        """Edits an existing message to replace it with the paginator contents.

        .. note::

            If invoked from an interaction, you will still need to respond to the interaction.

        Parameters
        ----------
        message: :class:`discord.Message`
            The message to edit with the paginator.
        suppress: :class:`bool`
            Whether to suppress embeds for the message. This removes
            all the embeds if set to ``True``. If set to ``False``
            this brings the embeds back if they were suppressed.
            Using this parameter requires :attr:`~.Permissions.manage_messages`.

            .. deprecated:: 2.8
        suppress_embeds: :class:`bool`
            Whether to suppress embeds for the message. This removes
            all the embeds if set to ``True``. If set to ``False``
            this brings the embeds back if they were suppressed.
            Using this parameter requires :attr:`~.Permissions.manage_messages`.

            .. versionadded:: 2.8
        allowed_mentions: Optional[:class:`~discord.AllowedMentions`]
            Controls the mentions being processed in this message. If this is
            passed, then the object is merged with :attr:`~discord.Client.allowed_mentions`.
            The merging behaviour only overrides attributes that have been explicitly passed
            to the object, otherwise it uses the attributes set in :attr:`~discord.Client.allowed_mentions`.
            If no object is passed at all then the defaults given by :attr:`~discord.Client.allowed_mentions`
            are used instead.
        delete_after: Optional[:class:`float`]
            If set, deletes the paginator after the specified time.
        user: Optional[Union[:class:`~discord.User`, :class:`~discord.Member`]]
            If set, changes the user that this paginator belongs to.

        Returns
        -------
        Optional[:class:`discord.Message`]
            The message that was edited. Returns ``None`` if the operation failed.
        """
        message_obj = cast("object", message)
        if not isinstance(message_obj, discord.Message):
            raise TypeError(f"expected Message not {message_obj.__class__!r}")

        self.update_buttons()

        page_content: Page = self.get_page_content(self._page_at(self.current_page))

        if page_content.custom_view:
            self.update_custom_view(page_content.custom_view)

        self.user = user or self.user

        if not self.user:
            self.usercheck = False

        if suppress is not None:
            warn_deprecated("suppress", "suppress_embeds", "2.8")
            if suppress_embeds is None:
                suppress_embeds = suppress

        with contextlib.suppress(discord.NotFound, discord.Forbidden):
            self.message = await message.edit(
                content=page_content.content,
                embeds=_embeds_of(page_content),
                files=_files_of(page_content),
                attachments=[],
                view=self,
                suppress_embeds=cast("bool", suppress_embeds),
                allowed_mentions=allowed_mentions,
                delete_after=delete_after,
            )

        return self.message

    async def respond(
        self,
        interaction: discord.Interaction | BridgeContext,
        ephemeral: bool = False,
        target: discord.abc.Messageable | None = None,
        target_message: str = "Paginator sent!",
    ) -> discord.Message | discord.WebhookMessage:
        """Sends an interaction response or followup with the paginated items.

        Parameters
        ----------
        interaction: Union[:class:`discord.Interaction`, :class:`BridgeContext`]
            The interaction or BridgeContext which invoked the paginator.
            If passing a BridgeContext object, you cannot make this an ephemeral paginator.
        ephemeral: :class:`bool`
            Whether the paginator message and its components are ephemeral.
            If ``target`` is specified, the ephemeral message content will be ``target_message`` instead.

            .. warning::

                If your paginator is ephemeral, it cannot have a timeout
                longer than 15 minutes (and cannot be persistent).

        target: Optional[:class:`~discord.abc.Messageable`]
            A target where the paginated message should be sent,
            if different from the original :class:`discord.Interaction`
        target_message: :class:`str`
            The content of the interaction response shown when the paginator message is sent elsewhere.

        Returns
        -------
        Union[:class:`~discord.Message`, :class:`~discord.WebhookMessage`]
            The :class:`~discord.Message` or :class:`~discord.WebhookMessage` that was sent with the paginator.
        """
        interaction_obj = cast("object", interaction)
        if not isinstance(interaction_obj, (discord.Interaction, BridgeContext)):
            raise TypeError(
                f"expected Interaction or BridgeContext, not {interaction_obj.__class__!r}"
            )

        target_obj = cast("object", target)
        if target_obj is not None and not isinstance(
            target_obj, discord.abc.Messageable
        ):
            raise TypeError(f"expected abc.Messageable not {target_obj.__class__!r}")

        if ephemeral and (self.timeout is None or self.timeout >= 900):
            raise ValueError(
                "paginator responses cannot be ephemeral if the paginator timeout is 15"
                " minutes or greater"
            )

        self.update_buttons()

        page_content: Page = self.get_page_content(self._page_at(self.current_page))

        if page_content.custom_view:
            self.update_custom_view(page_content.custom_view)

        if isinstance(interaction, discord.Interaction):
            self.user = interaction.user

            if target:
                await interaction.response.send_message(
                    target_message, ephemeral=ephemeral
                )
                msg: Any = await target.send(
                    content=page_content.content,
                    embeds=_embeds_of(page_content),
                    files=_files_of(page_content),
                    view=self,
                )
            elif interaction.response.is_done():
                msg = await interaction.followup.send(
                    content=cast("str", page_content.content),
                    embeds=_embeds_of(page_content),
                    files=_files_of(page_content),
                    view=self,
                    ephemeral=ephemeral,
                )
                # convert from WebhookMessage to Message reference to bypass
                # 15min webhook token timeout (non-ephemeral messages only)
                if not ephemeral and not msg.flags.ephemeral:
                    msg = await msg.channel.fetch_message(msg.id)
            else:
                msg = await interaction.response.send_message(
                    content=page_content.content,
                    embeds=_embeds_of(page_content),
                    files=_files_of(page_content),
                    view=self,
                    ephemeral=ephemeral,
                )
        else:
            ctx = cast("Any", interaction)
            self.user = ctx.author
            if target:
                await ctx.respond(target_message, ephemeral=ephemeral)
                msg = await ctx.send(
                    content=page_content.content,
                    embeds=_embeds_of(page_content),
                    files=_files_of(page_content),
                    view=self,
                )
            else:
                msg = await ctx.respond(
                    content=page_content.content,
                    embeds=_embeds_of(page_content),
                    files=_files_of(page_content),
                    view=self,
                )
        if isinstance(msg, (discord.Message, discord.WebhookMessage)):
            self.message = msg
        elif isinstance(msg, discord.Interaction):
            self.message = await msg.original_response()

        return self._current_message()


class PaginatorMenu(discord.ui.Select):
    """Creates a select menu used to switch between page groups, which can each have their own set of buttons.

    Parameters
    ----------
    placeholder: :class:`str`
        The placeholder text that is shown if nothing is selected.

    Attributes
    ----------
    paginator: :class:`Paginator`
        The paginator class where this menu is being used.
        Assigned to the menu when ``Paginator.add_menu`` is called.
    """

    def __init__(
        self,
        page_groups: list[PageGroup],
        placeholder: str | None = None,
        custom_id: str | None = None,
    ) -> None:
        self.page_groups: list[PageGroup] = page_groups
        self.paginator: Paginator | None = None
        opts = [
            discord.SelectOption(
                label=page_group.label,
                value=page_group.label,
                description=page_group.description,
                emoji=page_group.emoji,
            )
            for page_group in self.page_groups
        ]
        super().__init__(
            placeholder=placeholder,
            max_values=1,
            min_values=1,
            options=opts,
            custom_id=custom_id,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """|coro|

        The coroutine that is called when a menu option is selected.

        Parameters
        ----------
        interaction: :class:`discord.Interaction`
            The interaction created by selecting the menu option.
        """
        selection = cast("list[str]", self.values)[0]
        paginator = cast("Paginator", self.paginator)
        for page_group in self.page_groups:
            if selection == page_group.label:
                await paginator.update(
                    pages=page_group.pages,
                    show_disabled=page_group.show_disabled,
                    show_indicator=page_group.show_indicator,
                    author_check=page_group.author_check,
                    disable_on_timeout=page_group.disable_on_timeout,
                    use_default_buttons=page_group.use_default_buttons,
                    default_button_row=page_group.default_button_row,
                    loop_pages=page_group.loop_pages,
                    custom_view=page_group.custom_view,
                    timeout=page_group.timeout,
                    custom_buttons=page_group.custom_buttons,
                    trigger_on_display=page_group.trigger_on_display,
                    interaction=interaction,
                )
                return
