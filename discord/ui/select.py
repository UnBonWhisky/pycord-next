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
from functools import partial
from typing import TYPE_CHECKING, Any, Generic, Literal, cast, overload

from typing_extensions import Self, TypeVar, override

from ..channel import _threaded_guild_channel_factory
from ..components import SelectDefaultValue, SelectMenu, SelectOption
from ..enums import ChannelType, ComponentType, SelectDefaultValueType
from ..errors import InvalidArgument
from ..interactions import Interaction
from ..limits import ComponentLimits
from ..member import Member
from ..role import Role
from ..threads import Thread
from ..user import User
from ..utils import MISSING
from ._fields import (
    Field,
    custom_id_checks,
    get_row,
    in_range,
    length_limit,
    list_of,
    set_row,
    track_custom_id,
    type_check,
)
from .item import ItemCallbackType, ModalItem, ViewItem, _mark_callback

__all__ = (
    "ChannelSelect",
    "MentionableSelect",
    "RoleSelect",
    "Select",
    "StringSelect",
    "UserSelect",
    "channel_select",
    "mentionable_select",
    "role_select",
    "select",
    "string_select",
    "user_select",
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from ..abc import GuildChannel, Snowflake
    from ..components import Component
    from ..emoji import AppEmoji, GuildEmoji
    from ..partial_emoji import PartialEmoji
    from ..types.components import SelectMenu as SelectMenuPayload
    from .modal import DesignerModal
    from .view import BaseView

ST_co = TypeVar("ST_co", bound="Snowflake | str", covariant=True, default=Any)
V_co = TypeVar("V_co", bound="BaseView", covariant=True, default="BaseView")
M_co = TypeVar("M_co", bound="DesignerModal", covariant=True, default="DesignerModal")


class Select(ViewItem[V_co], ModalItem[M_co], Generic[V_co, ST_co, M_co]):
    """Represents a UI select menu.

    This is usually represented as a drop down menu.

    In order to get the selected items that the user has chosen, use :attr:`Select.values`.

    .. versionadded:: 2.0

    .. versionchanged:: 2.3

        Added support for :attr:`discord.ComponentType.string_select`, :attr:`discord.ComponentType.user_select`,
        :attr:`discord.ComponentType.role_select`, :attr:`discord.ComponentType.mentionable_select`,
        and :attr:`discord.ComponentType.channel_select`.

    .. versionchanged:: 2.7

        Can now be sent in :class:`discord.ui.DesignerModal`.

    Parameters
    ----------
    select_type: :class:`discord.ComponentType`
        The type of select to create. Must be one of
        :attr:`discord.ComponentType.string_select`, :attr:`discord.ComponentType.user_select`,
        :attr:`discord.ComponentType.role_select`, :attr:`discord.ComponentType.mentionable_select`,
        or :attr:`discord.ComponentType.channel_select`.

        The default is :attr:`discord.ComponentType.string_select`, but if this is created using any of the provided
        aliases: :class:`StringSelect`, :class:`RoleSelect`, :class:`UserSelect`, :class:`MentionableSelect`, or
        :class:`ChannelSelect`, the default will be its respective select type.
    custom_id: :class:`str`
        The ID of the select menu that gets received during an interaction.
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
    disabled: :class:`bool`
        Whether the select is disabled or not. Only useable in views. Defaults to ``False`` in views.
    row: Optional[:class:`int`]
        The relative row this select menu belongs to. A Discord component can only have 5
        rows. By default, items are arranged automatically into those 5 rows. If you'd
        like to control the relative positioning of the row then passing an index is advised.
        For example, row=1 will show up before row=2. Defaults to ``None``, which is automatic
        ordering. The row number must be between 0 and 4 (i.e. zero indexed). Does not work in :class:`ActionRow` or :class:`Label`.
    id: Optional[:class:`int`]
        The select menu's ID.
    required: Optional[:class:`bool`]
        Whether the select is required or not. Only useable when added to :class:`Label` for modals. Defaults to ``True`` in modals.

        .. versionadded:: 2.7
    default_values: Optional[Sequence[Union[:class:`discord.SelectDefaultValue`, :class:`discord.abc.Snowflake`]]]
        The default values of this select. Only applicable if :attr:`.select_type` is not :attr:`discord.ComponentType.string_select`.

        These can be either :class:`discord.SelectDefaultValue` instances or models, which will be converted into :class:`discord.SelectDefaultValue`
        instances.

        Below, is a table defining the model instance type and the default value type it will be mapped:

        +-----------------------------------+--------------------------------------------------------------------------+
        | Model Type                        | Default Value Type                                                       |
        +-----------------------------------+--------------------------------------------------------------------------+
        | :class:`discord.User`             | :attr:`discord.SelectDefaultValueType.user`                              |
        +-----------------------------------+--------------------------------------------------------------------------+
        | :class:`discord.Member`           | :attr:`discord.SelectDefaultValueType.user`                              |
        +-----------------------------------+--------------------------------------------------------------------------+
        | :class:`discord.Role`             | :attr:`discord.SelectDefaultValueType.role`                              |
        +-----------------------------------+--------------------------------------------------------------------------+
        | :class:`discord.abc.GuildChannel` | :attr:`discord.SelectDefaultValueType.channel`                           |
        +-----------------------------------+--------------------------------------------------------------------------+
        | :class:`discord.Object`           | depending on :attr:`discord.Object.type`, it will be mapped to any above |
        +-----------------------------------+--------------------------------------------------------------------------+

        If you pass a model that is not defined in the table, ``TypeError`` will be raised.

        .. note::

            The :class:`discord.abc.GuildChannel` protocol includes :class:`discord.TextChannel`, :class:`discord.VoiceChannel`, :class:`discord.StageChannel`,
            :class:`discord.ForumChannel`, :class:`discord.Thread`, :class:`discord.MediaChannel`. This list is not exhaustive, and is bound to change
            based of the new channel types Discord adds.

        .. versionadded:: 2.7
    """

    __item_repr_attributes__: tuple[str, ...] = (
        "type",
        "placeholder",
        "min_values",
        "max_values",
        "options",
        "channel_types",
        "disabled",
        "custom_id",
        "id",
        "required",
        "default_values",
    )

    @overload
    def __init__(
        self,
        select_type: Literal[ComponentType.string_select] = ...,
        *,
        custom_id: str | None = ...,
        placeholder: str | None = ...,
        min_values: int = ...,
        max_values: int = ...,
        options: list[SelectOption] | None = ...,
        disabled: bool = ...,
        row: int | None = ...,
        id: int | None = ...,
        required: bool | None = ...,
    ) -> None: ...

    @overload
    def __init__(
        self,
        select_type: Literal[ComponentType.channel_select] = ...,
        *,
        custom_id: str | None = ...,
        placeholder: str | None = ...,
        min_values: int = ...,
        max_values: int = ...,
        channel_types: list[ChannelType] | None = ...,
        disabled: bool = ...,
        row: int | None = ...,
        id: int | None = ...,
        required: bool | None = ...,
        default_values: Sequence[SelectDefaultValue | ST_co] | None = ...,
    ) -> None: ...

    @overload
    def __init__(
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
        disabled: bool = ...,
        row: int | None = ...,
        id: int | None = ...,
        required: bool | None = ...,
        default_values: Sequence[SelectDefaultValue | ST_co] | None = ...,
    ) -> None: ...

    @overload
    def __init__(
        self,
        select_type: ComponentType = ...,
        *,
        custom_id: str | None = ...,
        placeholder: str | None = ...,
        min_values: int = ...,
        max_values: int = ...,
        options: list[SelectOption] | None = ...,
        channel_types: list[ChannelType] | None = ...,
        disabled: bool = ...,
        row: int | None = ...,
        id: int | None = ...,
        required: bool | None = ...,
        default_values: Sequence[SelectDefaultValue | ST_co] | None = ...,
    ) -> None: ...

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
        select_type: ComponentType = ComponentType.string_select,
        *,
        custom_id: str | None = None,
        placeholder: str | None = None,
        min_values: int = 1,
        max_values: int = 1,
        options: list[SelectOption] | None = None,
        channel_types: list[ChannelType] | None = None,
        disabled: bool = False,
        row: int | None = None,
        id: int | None = None,
        required: bool | None = None,
        default_values: Sequence[SelectDefaultValue | ST_co] | None = None,
    ) -> None:
        self._row: int | None = None
        self._rendered_row: int | None = None
        if options and select_type is not ComponentType.string_select:
            raise InvalidArgument("options parameter is only valid for string selects")
        if channel_types and select_type is not ComponentType.channel_select:
            raise InvalidArgument(
                "channel_types parameter is only valid for channel selects"
            )
        if required and min_values < 1:
            raise ValueError("min_values must be greater than 0 when required=True")
        super().__init__()
        self._selected_values: list[str] = []
        self._interaction: Interaction | None = None
        self._resolved_values: list[Any] | None = None
        self._provided_custom_id = custom_id is not None
        self.row = row
        self._build_underlying(
            custom_id=custom_id,
            type=select_type,
            placeholder=placeholder,
            min_values=min_values,
            max_values=max_values,
            disabled=disabled,
            options=[],
            channel_types=channel_types or [],
            id=id,
            required=required,
            default_values=self._handle_default_values(default_values, select_type),
        )
        if options:
            self.options = options

    def _handle_default_values(
        self,
        default_values: Sequence[Snowflake | ST_co] | None,
        select_type: ComponentType,
    ) -> list[SelectDefaultValue]:
        if not default_values:
            return []

        ret: list[SelectDefaultValue] = []

        valid_default_types = {
            ComponentType.user_select: (SelectDefaultValueType.user,),
            ComponentType.role_select: (SelectDefaultValueType.role,),
            ComponentType.channel_select: (SelectDefaultValueType.channel,),
            ComponentType.mentionable_select: (
                SelectDefaultValueType.user,
                SelectDefaultValueType.role,
            ),
        }

        for dv in default_values:
            if isinstance(dv, SelectDefaultValue):
                try:
                    valid_types = valid_default_types[select_type]
                except KeyError:
                    raise TypeError(
                        f"select default values are not allowed for this select type ({select_type.name})"
                    ) from None

                if dv.type not in valid_types:
                    raise TypeError(
                        f"{dv.type.name} is not a valid select default value for selects of type {select_type.name}"
                    )

                ret.append(dv)
                continue
            if isinstance(dv, str):
                # this should not be here anyways, but guarding it
                continue

            ret.append(SelectDefaultValue._handle_model(dv, select_type))

        return ret

    __component__ = SelectMenu
    __component_type__ = ComponentType.string_select

    if TYPE_CHECKING:

        @property
        def underlying(self) -> SelectMenu:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    custom_id: Field[str] = Field(
        "The ID of the select menu that gets received during an interaction.",
        *custom_id_checks,
        on_set=track_custom_id,
    )
    placeholder: Field[str | None] = Field(
        "The placeholder text that is shown if nothing is selected, if any.",
        type_check(str, nullable=True),
        length_limit(ComponentLimits.SELECT_PLACEHOLDER_MAX),
    )
    min_values: Field[int] = Field(
        "The minimum number of items that must be chosen for this select menu.",
        in_range(
            ComponentLimits.SELECT_MIN_VALUES_MIN,
            ComponentLimits.SELECT_MIN_VALUES_MAX,
        ),
        coerce=int,
    )
    max_values: Field[int] = Field(
        "The maximum number of items that must be chosen for this select menu.",
        in_range(
            ComponentLimits.SELECT_MAX_VALUES_MIN,
            ComponentLimits.SELECT_MAX_VALUES_MAX,
        ),
        coerce=int,
    )
    disabled: Field[bool] = Field("Whether the select is disabled or not.", coerce=bool)
    required: Field[bool | None] = Field(
        "Whether the select is required or not. Only applicable in modal selects."
    )

    @property
    def channel_types(self) -> list[ChannelType]:
        """A list of channel types that can be selected in this menu."""
        return self.underlying.channel_types

    @channel_types.setter
    def channel_types(self, value: list[ChannelType]) -> None:
        if self.underlying.type is not ComponentType.channel_select:
            raise InvalidArgument("channel_types can only be set on channel selects")
        self.underlying.channel_types = value

    @property
    def options(self) -> list[SelectOption]:
        """A list of options that can be selected in this menu."""
        return self.underlying.options

    @options.setter
    def options(self, value: list[SelectOption]) -> None:
        if self.underlying.type is not ComponentType.string_select:
            raise InvalidArgument("options can only be set on string selects")
        list_of(SelectOption)("options", value)
        if len(value) > ComponentLimits.SELECT_OPTIONS_MAX:
            raise ValueError(
                f"you may only provide up to {ComponentLimits.SELECT_OPTIONS_MAX} options."
            )

        self.underlying.options = value

    @property
    def default_values(self) -> list[SelectDefaultValue]:
        """A list of the select's default values. This is only applicable if the select type is not :attr:`discord.ComponentType.string_select`.

        .. versionadded:: 2.7
        """
        return self.underlying.default_values

    @default_values.setter
    def default_values(
        self, values: Sequence[SelectDefaultValue | Snowflake] | None
    ) -> None:
        default_values = self._handle_default_values(values, self.type)
        self.underlying.default_values = default_values

    def add_default_value(
        self,
        *,
        id: int,
        type: SelectDefaultValueType = MISSING,
    ) -> Self:
        """Adds a default value to the select menu.

        To append a pre-existing :class:`discord.SelectDefaultValue` use the
        :meth:`append_default_value` method instead.

        .. versionadded:: 2.7

        Parameters
        ----------
        id: :class:`int`
            The ID of the entity to add as a default.
        type: :class:`discord.SelectDefaultValueType`
            The default value type of the ID. This is only required if the select ``type`` is
            :attr:`discord.ComponentType.mentionable_select`.

        Raises
        ------
        TypeError
            The select type is a mentionable_select and type was not provided, or the select
            type is string_select.
        ValueError
            The number of default select values exceeds 25.
        """
        if type is MISSING and self.type is ComponentType.mentionable_select:
            raise TypeError(
                "type is required when select is of type mentionable_select"
            )

        types = {
            ComponentType.user_select: SelectDefaultValueType.user,
            ComponentType.role_select: SelectDefaultValueType.role,
            ComponentType.channel_select: SelectDefaultValueType.channel,
        }

        def_type = types.get(self.type, type)
        self.append_default_value(SelectDefaultValue(id=id, type=def_type))
        return self

    def append_default_value(
        self,
        value: SelectDefaultValue | Snowflake,
        /,
    ) -> Self:
        """Appends a default value to this select menu.

        .. versionadded:: 2.7

        Parameters
        ----------
        value: Union[:class:`discord.SelectDefaultValue`, :class:`discord.abc.Snowflake`]
            The default value to append to this select.

            These can be either :class:`discord.SelectDefaultValue` instances or models, which will be converted into :class:`discord.SelectDefaultvalue`
            instances.

            Below, is a table defining the model instance type and the default value type it will be mapped:

            +-----------------------------------+--------------------------------------------------------------------------+
            | Model Type                        | Default Value Type                                                       |
            +-----------------------------------+--------------------------------------------------------------------------+
            | :class:`discord.User`             | :attr:`discord.SelectDefaultValueType.user`                              |
            +-----------------------------------+--------------------------------------------------------------------------+
            | :class:`discord.Member`           | :attr:`discord.SelectDefaultValueType.user`                              |
            +-----------------------------------+--------------------------------------------------------------------------+
            | :class:`discord.Role`             | :attr:`discord.SelectDefaultValueType.role`                              |
            +-----------------------------------+--------------------------------------------------------------------------+
            | :class:`discord.abc.GuildChannel` | :attr:`discord.SelectDefaultValueType.channel`                           |
            +-----------------------------------+--------------------------------------------------------------------------+
            | :class:`discord.Object`           | depending on :attr:`discord.Object.type`, it will be mapped to any above |
            +-----------------------------------+--------------------------------------------------------------------------+

            If you pass a model that is not defined in the table, ``TypeError`` will be raised.

            .. note::

                The :class:`discord.abc.GuildChannel` protocol includes :class:`discord.TextChannel`, :class:`discord.VoiceChannel`, :class:`discord.StageChannel`,
                :class:`discord.ForumChannel`, :class:`discord.Thread`, :class:`discord.MediaChannel`. This list is not exhaustive, and is bound to change
                based of the new channel types Discord adds.

        Raises
        ------
        TypeError
            The select type is string_select, which does not allow for default_values
        ValueError
            The number of default select values exceeds 25.
        """
        if self.type is ComponentType.string_select:
            raise TypeError("string_select selects do not allow default_values")

        if len(self.default_values) >= ComponentLimits.SELECT_DEFAULT_VALUES_MAX:
            raise ValueError(
                f"maximum number of default values exceeded ({ComponentLimits.SELECT_DEFAULT_VALUES_MAX})"
            )

        if not isinstance(value, SelectDefaultValue):
            value = SelectDefaultValue._handle_model(value)

        self.underlying.default_values.append(value)
        return self

    def add_option(
        self,
        *,
        label: str,
        value: str = MISSING,
        description: str | None = None,
        emoji: str | GuildEmoji | AppEmoji | PartialEmoji | None = None,
        default: bool = False,
    ) -> Self:
        """Adds an option to the select menu.

        To append a pre-existing :class:`discord.SelectOption` use the
        :meth:`append_option` method instead.

        Parameters
        ----------
        label: :class:`str`
            The label of the option. This is displayed to users.
            Can only be up to 100 characters.
        value: :class:`str`
            The value of the option. This is not displayed to users.
            If not given, defaults to the label. Can only be up to 100 characters.
        description: Optional[:class:`str`]
            An additional description of the option, if any.
            Can only be up to 100 characters.
        emoji: Optional[Union[:class:`str`, :class:`GuildEmoji`, :class:`AppEmoji`, :class:`.PartialEmoji`]]
            The emoji of the option, if available. This can either be a string representing
            the custom or unicode emoji or an instance of :class:`.PartialEmoji`, :class:`GuildEmoji`, or :class:`AppEmoji`.
        default: :class:`bool`
            Whether this option is selected by default.

        Raises
        ------
        ValueError
            The number of options exceeds 25.
        """
        if self.underlying.type is not ComponentType.string_select:
            raise InvalidArgument("options can only be set on string selects")

        option = SelectOption(
            label=label,
            value=value,
            description=description,
            emoji=emoji,
            default=default,
        )

        return self.append_option(option)

    def append_option(self, option: SelectOption) -> Self:
        """Appends an option to the select menu.

        Parameters
        ----------
        option: :class:`discord.SelectOption`
            The option to append to the select menu.

        Raises
        ------
        ValueError
            The number of options exceeds 25.
        """
        if self.underlying.type is not ComponentType.string_select:
            raise InvalidArgument("options can only be set on string selects")

        if len(self.underlying.options) >= ComponentLimits.SELECT_OPTIONS_MAX:
            raise ValueError(
                f"maximum number of options already provided ({ComponentLimits.SELECT_OPTIONS_MAX})"
            )

        self.underlying.options.append(option)
        return self

    def _resolution_context(self) -> tuple[Any, Any, dict[str, Any]] | None:
        interaction = self._interaction
        data = getattr(interaction, "data", None)
        if interaction is None or data is None:
            return None
        guild = interaction.guild
        if guild is None:
            return None
        resolved = cast(
            "dict[str, Any]", cast("Mapping[str, Any]", data).get("resolved", {})
        )
        return interaction._state, guild, resolved

    def _resolution_ids(
        self, resolved_data: dict[str, Any]
    ) -> tuple[list[int], list[int]]:
        select_type = self.underlying.type
        selected_values = set(self._selected_values)
        channel_ids: list[int] = []
        member_ids: list[int] = []
        if select_type is ComponentType.channel_select:
            channel_ids = [
                int(channel_id)
                for channel_id in resolved_data.get("channels", {})
                if channel_id in selected_values
            ]
        elif select_type in (
            ComponentType.user_select,
            ComponentType.mentionable_select,
        ):
            resolved_users = resolved_data.get("users", {})
            resolved_members = resolved_data.get("members", {})
            member_ids = [
                int(_id)
                for _id in self._selected_values
                if _id in resolved_users and _id in resolved_members
            ]
        return channel_ids, member_ids

    def _build_values(
        self,
        state: Any,
        guild: Any,
        resolved_data: dict[str, Any],
        channels: dict[int, Any],
        members: dict[int, Member],
    ) -> list[ST_co]:
        select_type = self.underlying.type
        resolved: list[Any] = []
        selected_values = list(self._selected_values)
        if select_type is ComponentType.channel_select:
            for channel_id, _data in resolved_data.get("channels", {}).items():
                if channel_id not in selected_values:
                    continue
                result = channels.get(int(channel_id))
                if result is not None:
                    _data["_invoke_flag"] = True
                    (
                        result._update(_data)
                        if isinstance(result, Thread)
                        else result._update(guild, _data)
                    )
                else:
                    # NOTE:
                    # This is a fallback in case the channel/thread is not found in the
                    # guild's channels/threads. For channels, if this fallback occurs, at the very minimum,
                    # permissions will be incorrect due to a lack of permission_overwrite data.
                    # For threads, if this fallback occurs, info like thread owner id, message count,
                    # flags, and more will be missing due to a lack of data sent by Discord.
                    obj_type = _threaded_guild_channel_factory(_data["type"])[0]
                    if obj_type is None:
                        # should not be None, but assert anyways
                        continue
                    result = obj_type(state=state, data=_data, guild=guild)
                resolved.append(result)
        elif select_type in (
            ComponentType.user_select,
            ComponentType.mentionable_select,
        ):
            cache_flag = state.member_cache_flags.interaction
            resolved_user_data = resolved_data.get("users", {})
            resolved_member_data = resolved_data.get("members", {})
            for _id in selected_values:
                if (_data := resolved_user_data.get(_id)) is not None:
                    if (_member_data := resolved_member_data.get(_id)) is not None:
                        member_data: Any = dict(_member_data)
                        member_data["user"] = _data
                        result = members.get(int(_id))
                        if result is not None:
                            if cache_flag:
                                result._update(member_data)
                        else:
                            # NOTE:
                            # This is a fallback in case the member is not found in the guild's members.
                            # If this fallback occurs, multiple aspects of the Member
                            # class will be incorrect such as status and activities.
                            result = Member(guild=guild, state=state, data=member_data)
                    else:
                        result = User(state=state, data=_data)
                    resolved.append(result)
        if select_type in (ComponentType.role_select, ComponentType.mentionable_select):
            for role_id, _data in resolved_data.get("roles", {}).items():
                if role_id not in selected_values:
                    continue
                resolved.append(Role(guild=guild, state=state, data=_data))
        return resolved

    @property
    def values(self) -> list[ST_co] | None:
        """List[:class:`str`] | List[:class:`discord.Member` | :class:`discord.User`]] | List[:class:`discord.Role`]] | List[:class:`discord.Member` | :class:`discord.User` | :class:`discord.Role`]] | List[:class:`discord.abc.GuildChannel`] | None:

        A list of values that have been selected by the user. This will be ``None`` if the select has not been interacted with yet.

        The values are resolved from the interaction payload and, with the in-process
        cache, from the cache. They are resolved once when the interaction is dispatched,
        so this works with any cache backend inside callbacks; use :meth:`get_values`
        outside of them.
        """
        if getattr(self._interaction, "data", None) is None:
            # The select has not been interacted with yet
            return None
        select_type = self.underlying.type
        if select_type is ComponentType.string_select:
            return cast("list[ST_co]", self._selected_values)
        if self._resolved_values is not None:
            return list(self._resolved_values)
        context = self._resolution_context()
        if context is None:
            return []
        state, guild, resolved_data = context
        channels: dict[int, Any] = {}
        members: dict[int, Member] = {}
        if state.cache.supports_sync:
            channel_ids, member_ids = self._resolution_ids(resolved_data)
            channel_bucket = state._guild_bucket("channels", guild.id)
            thread_bucket = state._guild_bucket("threads", guild.id)
            for channel_id in channel_ids:
                found = channel_bucket.get_nowait(
                    channel_id
                ) or thread_bucket.get_nowait(channel_id)
                if found is not None:
                    channels[channel_id] = found
            member_bucket = state._guild_bucket("members", guild.id)
            for member_id in member_ids:
                found_member = member_bucket.get_nowait(member_id)
                if found_member is not None:
                    members[member_id] = found_member
        return self._build_values(state, guild, resolved_data, channels, members)

    async def get_values(self) -> list[ST_co] | None:
        """|coro|

        Resolves the values that have been selected by the user with any cache backend.

        Selected channels, threads and members are looked up in the cache, using the
        interaction payload for everything else. Members are cached according to
        :attr:`MemberCacheFlags.interaction`.

        Returns
        -------
        Optional[List[Union[:class:`str`, :class:`discord.Member`, :class:`discord.User`, :class:`discord.Role`, :class:`discord.abc.GuildChannel`]]]
            The selected values, or ``None`` if the select has not been interacted with yet.
        """
        if getattr(self._interaction, "data", None) is None:
            return None
        if self.underlying.type is ComponentType.string_select:
            return cast("list[ST_co]", self._selected_values)
        if self._resolved_values is None:
            await self._resolve_state()
        return list(self._resolved_values or [])

    async def _resolve_state(self) -> None:
        self._resolved_values = None
        if self.underlying.type is ComponentType.string_select:
            return
        context = self._resolution_context()
        if context is None:
            self._resolved_values = []
            return
        state, guild, resolved_data = context
        channel_ids, member_ids = self._resolution_ids(resolved_data)
        channels: dict[int, Any] = {}
        members: dict[int, Member] = {}
        if channel_ids:
            channels.update(
                await state._guild_bucket("threads", guild.id).get_many(channel_ids)
            )
            channels.update(
                await state._guild_bucket("channels", guild.id).get_many(channel_ids)
            )
        member_bucket = state._guild_bucket("members", guild.id)
        if member_ids:
            members.update(await member_bucket.get_many(member_ids))
        resolved = self._build_values(state, guild, resolved_data, channels, members)
        if state.member_cache_flags.interaction:
            for value in resolved:
                if isinstance(value, Member):
                    await member_bucket.set(value.id, value)
        self._resolved_values = resolved

    @property
    def width(self) -> int:
        """Gets the width of the item in the UI layout.

        The width determines how much horizontal space this item occupies within its row.

        Returns
        -------
        :class:`int`
            The width of the item. Select menus have a width of 5.
        """
        return 5

    @override
    def to_component_dict(self) -> SelectMenuPayload:
        return cast("SelectMenuPayload", super().to_component_dict())

    @override
    def refresh_state(self, interaction: Interaction | Mapping[str, Any]) -> None:
        data = cast(
            "Mapping[str, Any]",
            interaction.data if isinstance(interaction, Interaction) else interaction,
        )
        self._selected_values = data.get("values", [])
        self._interaction = cast("Interaction", interaction)
        self._resolved_values = None

    @override
    def refresh_from_modal(
        self, interaction: Interaction | Mapping[str, Any], data: Mapping[str, Any]
    ) -> None:
        self._selected_values = data.get("values", [])
        self._interaction = cast("Interaction", interaction)
        self._resolved_values = None

    @classmethod
    @override
    def from_component(cls, component: SelectMenu) -> Self:
        return cls(
            select_type=component.type,
            custom_id=component.custom_id,
            placeholder=component.placeholder,
            min_values=component.min_values,
            max_values=component.max_values,
            options=component.options,
            channel_types=component.channel_types,
            disabled=component.disabled,
            row=None,
            id=component.id,
            required=component.required,
            default_values=component.default_values,
        )

    @override
    def is_dispatchable(self) -> bool:
        return (bool(self.view._store) if self.view else True) and (
            bool(self.modal._store) if self.modal else True
        )

    @override
    def is_storable(self) -> bool:
        return self.is_dispatchable()


if TYPE_CHECKING:
    StringSelect = Select[V_co, str]
    """A typed alias for :class:`Select` for string values.

    When creating an instance with this, it will automatically provide the ``select_type``
    parameter as a :attr:`discord.ComponentType.string_select`.
    """
    UserSelect = Select[V_co, User | Member]
    """A typed alias for :class:`Select` for user-like values.

    When creating an instance with this, it will automatically provide the ``select_type``
    parameter as a :attr:`discord.ComponentType.user_select`.
    """
    RoleSelect = Select[V_co, Role]
    """A typed alias for :class:`Select` for role values.

    When creating an instance with this, it will automatically provide the ``select_type``
    parameter as a :attr:`discord.ComponentType.role_select`.
    """
    MentionableSelect = Select[V_co, User | Member | Role]
    """A typed alias for :class:`Select` for mentionable (role and user-like) values.

    When creating an instance with this, it will automatically provide the ``select_type``
    parameter as a :attr:`discord.ComponentType.mentionable_select`.
    """
    ChannelSelect = Select[V_co, GuildChannel | Thread]
    """A typed alias for :class:`Select` for channel values.

    When creating an instance with this, it will automatically provide the ``select_type``
    parameter as a :attr:`discord.ComponentType.channel_select`.
    """
else:
    StringSelect: Select[V_co, str] = partial(
        Select, select_type=ComponentType.string_select
    )
    """An alias for :class:`Select` that will pass :attr:`discord.ComponentType.string_select`
    as its default ``select_type``.
    """
    UserSelect: Select[V_co, User | Member] = partial(
        Select, select_type=ComponentType.user_select
    )
    """An alias for :class:`Select` that will pass :attr:`discord.ComponentType.user_select`
    as its default ``select_type``.
    """
    RoleSelect: Select[V_co, Role] = partial(
        Select, select_type=ComponentType.role_select
    )
    """An alias for :class:`Select` that will pass :attr:`discord.ComponentType.role_select`
    as its default ``select_type``.
    """
    MentionableSelect: Select[V_co, Role | User | Member] = partial(
        Select, select_type=ComponentType.mentionable_select
    )
    """An alias for :class:`Select` that will pass :attr:`discord.ComponentType.mentionable_select`
    as its default ``select_type``.
    """
    ChannelSelect: Select[V_co, GuildChannel | Thread] = partial(
        Select, select_type=ComponentType.channel_select
    )
    """An alias for :class:`Select` that will pass :attr:`discord.ComponentType.channel_select`
    as its default ``select_type``.
    """


_select_types = (
    ComponentType.string_select,
    ComponentType.user_select,
    ComponentType.role_select,
    ComponentType.mentionable_select,
    ComponentType.channel_select,
)


def select(
    select_type: ComponentType = ComponentType.string_select,
    *,
    placeholder: str | None = None,
    custom_id: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    options: list[SelectOption] = MISSING,
    channel_types: list[ChannelType] = MISSING,
    disabled: bool = False,
    row: int | None = None,
    id: int | None = None,
    default_values: Sequence[SelectDefaultValue | Snowflake] | None = None,
) -> Callable[[ItemCallbackType[Select[V_co, ST_co]]], Select[V_co, ST_co]]:
    """A decorator that attaches a select menu to a component.

    The function being decorated should have three parameters, ``self`` representing
    the :class:`discord.ui.View`, :class:`discord.ui.ActionRow` or :class:`discord.ui.Section`, the :class:`discord.ui.Select` being pressed and
    the :class:`discord.Interaction` you receive.

    In order to get the selected items that the user has chosen within the callback
    use :attr:`Select.values`.

    .. versionchanged:: 2.3

        Creating select menus of different types is now supported.

    Parameters
    ----------
    select_type: :class:`discord.ComponentType`
        The type of select to create. Must be one of
        :attr:`discord.ComponentType.string_select`, :attr:`discord.ComponentType.user_select`,
        :attr:`discord.ComponentType.role_select`, :attr:`discord.ComponentType.mentionable_select`,
        or :attr:`discord.ComponentType.channel_select`.
    placeholder: Optional[:class:`str`]
        The placeholder text that is shown if nothing is selected, if any.
    custom_id: :class:`str`
        The ID of the select menu that gets received during an interaction.
        It is recommended not to set this parameter to prevent conflicts.
    row: Optional[:class:`int`]
        The relative row this select menu belongs to. A Discord component can only have 5
        rows. By default, items are arranged automatically into those 5 rows. If you'd
        like to control the relative positioning of the row then passing an index is advised.
        For example, row=1 will show up before row=2. Defaults to ``None``, which is automatic
        ordering. The row number must be between 0 and 4 (i.e. zero indexed).
    min_values: :class:`int`
        The minimum number of items that must be chosen for this select menu.
        Defaults to 1 and must be between 0 and 25.
    max_values: :class:`int`
        The maximum number of items that must be chosen for this select menu.
        Defaults to 1 and must be between 1 and 25.
    options: List[:class:`discord.SelectOption`]
        A list of options that can be selected in this menu.
        Only valid for the :attr:`discord.ComponentType.string_select` type.
    channel_types: List[:class:`discord.ChannelType`]
        The channel types that should be selectable.
        Only valid for the :attr:`discord.ComponentType.channel_select` type.
        Defaults to all channel types.
    disabled: :class:`bool`
        Whether the select is disabled or not. Defaults to ``False``.
    id: Optional[:class:`int`]
        The select menu's ID.
    default_values: Optional[Sequence[Union[:class:`discord.SelectDefaultValue`, :class:`discord.abc.Snowflake`]]]
        The default values of this select. Only applicable if :attr:`.select_type` is not :attr:`discord.ComponentType.string_select`.

        This can be either :class:`discord.SelectDefaultValue` instances or models, which will be converted into :class:`discord.SelectDefaultValue`
        instances.

        Below, is a table defining the model instance type and the default value type it will be mapped:

        +-----------------------------------+--------------------------------------------------------------------------+
        | Model Type                        | Default Value Type                                                       |
        +-----------------------------------+--------------------------------------------------------------------------+
        | :class:`discord.User`             | :attr:`discord.SelectDefaultValueType.user`                              |
        +-----------------------------------+--------------------------------------------------------------------------+
        | :class:`discord.Member`           | :attr:`discord.SelectDefaultValueType.user`                              |
        +-----------------------------------+--------------------------------------------------------------------------+
        | :class:`discord.Role`             | :attr:`discord.SelectDefaultValueType.role`                              |
        +-----------------------------------+--------------------------------------------------------------------------+
        | :class:`discord.abc.GuildChannel` | :attr:`discord.SelectDefaultValueType.channel`                           |
        +-----------------------------------+--------------------------------------------------------------------------+
        | :class:`discord.Object`           | depending on :attr:`discord.Object.type`, it will be mapped to any above |
        +-----------------------------------+--------------------------------------------------------------------------+

        If you pass a model that is not defined in the table, ``TypeError`` will be raised.

        .. note::

            The :class:`discord.abc.GuildChannel` protocol includes :class:`discord.TextChannel`, :class:`discord.VoiceChannel`, :class:`discord.StageChannel`,
            :class:`discord.ForumChannel`, :class:`discord.Thread`, :class:`discord.MediaChannel`. This list is not exhaustive, and is bound to change
            based of the new channel types Discord adds.

        .. versionadded:: 2.7
    """
    if select_type not in _select_types:
        raise ValueError(
            "select_type must be one of " + ", ".join([i.name for i in _select_types])
        )

    if options is not MISSING and select_type not in (
        ComponentType.select,
        ComponentType.string_select,
    ):
        raise TypeError("options may only be specified for string selects")

    if channel_types is not MISSING and select_type is not ComponentType.channel_select:
        raise TypeError("channel_types may only be specified for channel selects")

    if default_values is not None and select_type is ComponentType.string_select:
        raise TypeError(
            "default_values may only be specified for selects other than string selects"
        )

    def decorator(func: ItemCallbackType) -> ItemCallbackType:
        if not inspect.iscoroutinefunction(func):
            raise TypeError("select function must be a coroutine function")

        model_kwargs: dict[str, Any] = {
            "select_type": select_type,
            "placeholder": placeholder,
            "custom_id": custom_id,
            "row": row,
            "min_values": min_values,
            "max_values": max_values,
            "disabled": disabled,
            "id": id,
            "default_values": default_values,
        }
        if options:
            model_kwargs["options"] = options
        if channel_types:
            model_kwargs["channel_types"] = channel_types

        _mark_callback(func, Select, model_kwargs)

        return func

    # lie to the type checkers because after a View is instated the select callback is converted into a Select instance
    return cast(
        "Callable[[ItemCallbackType[Select[V_co, ST_co]]], Select[V_co, ST_co]]",
        decorator,
    )


def string_select(
    *,
    placeholder: str | None = None,
    custom_id: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    options: list[SelectOption] = MISSING,
    disabled: bool = False,
    row: int | None = None,
    id: int | None = None,
) -> Callable[[ItemCallbackType[StringSelect[V_co]]], StringSelect[V_co]]:
    """A shortcut for :meth:`discord.ui.select` with select type :attr:`discord.ComponentType.string_select`.

    .. versionadded:: 2.3
    """
    return select(
        ComponentType.string_select,
        placeholder=placeholder,
        custom_id=custom_id,
        min_values=min_values,
        max_values=max_values,
        options=options,
        disabled=disabled,
        row=row,
        id=id,
    )


def user_select(
    *,
    placeholder: str | None = None,
    custom_id: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    disabled: bool = False,
    row: int | None = None,
    id: int | None = None,
    default_values: Sequence[SelectDefaultValue | Snowflake] | None = None,
) -> Callable[[ItemCallbackType[UserSelect[V_co]]], UserSelect[V_co]]:
    """A shortcut for :meth:`discord.ui.select` with select type :attr:`discord.ComponentType.user_select`.

    .. versionadded:: 2.3
    """
    return select(
        ComponentType.user_select,
        placeholder=placeholder,
        custom_id=custom_id,
        min_values=min_values,
        max_values=max_values,
        disabled=disabled,
        row=row,
        id=id,
        default_values=default_values,
    )


def role_select(
    *,
    placeholder: str | None = None,
    custom_id: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    disabled: bool = False,
    row: int | None = None,
    id: int | None = None,
    default_values: Sequence[SelectDefaultValue | Snowflake] | None = None,
) -> Callable[[ItemCallbackType[RoleSelect[V_co]]], RoleSelect[V_co]]:
    """A shortcut for :meth:`discord.ui.select` with select type :attr:`discord.ComponentType.role_select`.

    .. versionadded:: 2.3
    """
    return select(
        ComponentType.role_select,
        placeholder=placeholder,
        custom_id=custom_id,
        min_values=min_values,
        max_values=max_values,
        disabled=disabled,
        row=row,
        id=id,
        default_values=default_values,
    )


def mentionable_select(
    *,
    placeholder: str | None = None,
    custom_id: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    disabled: bool = False,
    row: int | None = None,
    id: int | None = None,
    default_values: Sequence[SelectDefaultValue | Snowflake] | None = None,
) -> Callable[
    [ItemCallbackType[MentionableSelect[V_co]]],
    MentionableSelect[V_co],
]:
    """A shortcut for :meth:`discord.ui.select` with select type :attr:`discord.ComponentType.mentionable_select`.

    .. versionadded:: 2.3
    """
    return select(
        ComponentType.mentionable_select,
        placeholder=placeholder,
        custom_id=custom_id,
        min_values=min_values,
        max_values=max_values,
        disabled=disabled,
        row=row,
        id=id,
        default_values=default_values,
    )


def channel_select(
    *,
    placeholder: str | None = None,
    custom_id: str | None = None,
    min_values: int = 1,
    max_values: int = 1,
    disabled: bool = False,
    channel_types: list[ChannelType] = MISSING,
    row: int | None = None,
    id: int | None = None,
    default_values: Sequence[SelectDefaultValue | Snowflake] | None = None,
) -> Callable[
    [ItemCallbackType[ChannelSelect[V_co]]],
    ChannelSelect[V_co],
]:
    """A shortcut for :meth:`discord.ui.select` with select type :attr:`discord.ComponentType.channel_select`.

    .. versionadded:: 2.3
    """
    return select(
        ComponentType.channel_select,
        placeholder=placeholder,
        custom_id=custom_id,
        min_values=min_values,
        max_values=max_values,
        disabled=disabled,
        channel_types=channel_types,
        row=row,
        id=id,
        default_values=default_values,
    )
