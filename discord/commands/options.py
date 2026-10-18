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

import inspect
import logging
import sys
import types
from collections.abc import Awaitable, Callable, Iterable
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypeVar,
    Union,
    cast,
    get_args,
)

if sys.version_info >= (3, 12):
    from typing import TypeAliasType
else:
    from typing_extensions import TypeAliasType

from ..abc import GuildChannel, Mentionable
from ..channel import (
    CategoryChannel,
    DMChannel,
    ForumChannel,
    MediaChannel,
    StageChannel,
    TextChannel,
    Thread,
    VoiceChannel,
)
from ..commands import ApplicationContext, AutocompleteContext
from ..enums import ChannelType, Enum as DiscordEnum, SlashCommandOptionType
from ..utils import MISSING, basic_autocomplete

if TYPE_CHECKING:
    from ..cog import Cog
    from ..ext.commands import Converter
    from ..member import Member
    from ..message import Attachment
    from ..role import Role
    from ..user import User

    InputType = (
        type[
            str
            | bool
            | int
            | float
            | GuildChannel
            | Thread
            | Member
            | User
            | Attachment
            | Role
            | Mentionable
            | Converter[Any]
            | Enum
            | DiscordEnum
        ]
        | SlashCommandOptionType
        | Converter[Any]
    )

    AutocompleteReturnType = (
        Iterable["OptionChoice"] | Iterable[str] | Iterable[int] | Iterable[float]
    )
    T = TypeVar("T", bound=AutocompleteReturnType)
    MaybeAwaitable = T | Awaitable[T]
    AutocompleteFunction = (
        Callable[[AutocompleteContext], MaybeAwaitable[AutocompleteReturnType]]
        | Callable[[Cog, AutocompleteContext], MaybeAwaitable[AutocompleteReturnType]]
        | Callable[
            [AutocompleteContext, Any],
            MaybeAwaitable[AutocompleteReturnType],
        ]
        | Callable[
            [Cog, AutocompleteContext, Any],
            MaybeAwaitable[AutocompleteReturnType],
        ]
    )


F = TypeVar("F", bound=Callable[..., Any])

__all__ = (
    "Option",
    "OptionChoice",
    "ThreadOption",
    "option",
)

CHANNEL_TYPE_MAP = {
    TextChannel: ChannelType.text,
    VoiceChannel: ChannelType.voice,
    StageChannel: ChannelType.stage_voice,
    CategoryChannel: ChannelType.category,
    Thread: ChannelType.public_thread,
    ForumChannel: ChannelType.forum,
    MediaChannel: ChannelType.media,
    DMChannel: ChannelType.private,
}

_log = logging.getLogger(__name__)


def _input_type_of(datatype: Any) -> SlashCommandOptionType:
    # Only the type of a command context resolves to ``None``, it is not an option.
    return cast(
        "SlashCommandOptionType", SlashCommandOptionType.from_datatype(datatype)
    )


def _tuple_members(value: object) -> tuple[Any, ...] | None:
    if isinstance(value, tuple):
        return cast("tuple[Any, ...]", value)
    return None


def _is_enum_type(value: object) -> bool:
    return isinstance(value, type) and issubclass(value, (Enum, DiscordEnum))


def _is_converter(value: object) -> bool:
    from ..ext.commands import Converter

    return isinstance(value, Converter) or (
        isinstance(value, type) and issubclass(value, Converter)
    )


def _channel_raw_types(raw_type: object, datatype: Any) -> tuple[Any, ...]:
    members = _tuple_members(raw_type)
    if members is not None:
        return members
    args = getattr(datatype, "__args__", MISSING)
    return (datatype,) if args is MISSING else args


def _is_instance(value: object, types_: tuple[type, ...]) -> bool:
    return isinstance(value, types_)


class ThreadOption:
    """Represents a class that can be passed as the ``input_type`` for an :class:`Option` class.

    .. versionadded:: 2.0

    Parameters
    ----------
    thread_type: Literal["public", "private", "news"]
        The thread type to expect for this options input.
    """

    def __init__(self, thread_type: Literal["public", "private", "news"]) -> None:
        type_map = {
            "public": ChannelType.public_thread,
            "private": ChannelType.private_thread,
            "news": ChannelType.news_thread,
        }
        self._type = type_map[thread_type]


class Option:
    """Represents a selectable option for a slash command.

    Attributes
    ----------
    input_type: Union[Type[:class:`str`], Type[:class:`bool`], Type[:class:`int`], Type[:class:`float`], Type[:class:`.abc.GuildChannel`], Type[:class:`Thread`], Type[:class:`Member`], Type[:class:`User`], Type[:class:`Attachment`], Type[:class:`Role`], Type[:class:`.abc.Mentionable`], :class:`SlashCommandOptionType`, Type[:class:`.ext.commands.Converter`], Type[:class:`enums.Enum`], Type[:class:`Enum`]]
        The type of input that is expected for this option. This can be a :class:`SlashCommandOptionType`,
        an associated class, a channel type, a :class:`Converter`, a converter class or an :class:`enum.Enum`.
        If a :class:`enum.Enum` is used and it has up to 25 values, :attr:`choices` will be automatically filled. If the :class:`enum.Enum` has more than 25 values, :attr:`autocomplete` will be implemented with :func:`discord.utils.basic_autocomplete` instead.
    name: :class:`str`
        The name of this option visible in the UI.
        Inherits from the variable name if not provided as a parameter.
    description: Optional[:class:`str`]
        The description of this option.
        Must be 100 characters or fewer. If :attr:`input_type` is a :class:`enum.Enum` and :attr:`description` is not specified, :attr:`input_type`'s docstring will be used.
    choices: Optional[List[Union[:class:`Any`, :class:`OptionChoice`]]]
        The list of available choices for this option.
        Can be a list of values or :class:`OptionChoice` objects (which represent a name:value pair).
        If provided, the input from the user must match one of the choices in the list.
    required: Optional[:class:`bool`]
        Whether this option is required.
    default: Optional[:class:`Any`]
        The default value for this option. If provided, ``required`` will be considered ``False``.
    min_value: Optional[:class:`int`]
        The minimum value that can be entered.
        Only applies to Options with an :attr:`.input_type` of :class:`int` or :class:`float`.
    max_value: Optional[:class:`int`]
        The maximum value that can be entered.
        Only applies to Options with an :attr:`.input_type` of :class:`int` or :class:`float`.
    min_length: Optional[:class:`int`]
        The minimum length of the string that can be entered. Must be between 0 and 6000 (inclusive).
        Only applies to Options with an :attr:`input_type` of :class:`str`.
    max_length: Optional[:class:`int`]
        The maximum length of the string that can be entered. Must be between 1 and 6000 (inclusive).
        Only applies to Options with an :attr:`input_type` of :class:`str`.
    channel_types: list[:class:`discord.ChannelType`] | None
        A list of channel types that can be selected in this option.
        Only applies to Options with an :attr:`input_type` of :class:`discord.SlashCommandOptionType.channel`.
        If this argument is used, :attr:`input_type` will be ignored.
    name_localizations: Dict[:class:`str`, :class:`str`]
        The name localizations for this option. The values of this should be ``"locale": "name"``.
        See `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    description_localizations: Dict[:class:`str`, :class:`str`]
        The description localizations for this option. The values of this should be ``"locale": "description"``.
        See `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.

    Examples
    --------
    Basic usage: ::

        @bot.slash_command(guild_ids=[...])
        async def hello(
            ctx: discord.ApplicationContext,
            name: Option(str, "Enter your name"),
            age: Option(int, "Enter your age", min_value=1, max_value=99, default=18),
            # passing the default value makes an argument optional
            # you also can create optional argument using:
            # age: Option(int, "Enter your age") = 18
        ):
            await ctx.respond(
                f"Hello! Your name is {name} and you are {age} years old."
            )

    .. versionadded:: 2.0
    """

    input_type: SlashCommandOptionType
    converter: Converter[Any] | type[Converter[Any]] | None = None

    def __init__(
        self,
        input_type: InputType = str,
        /,
        description: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.name: str | None = kwargs.pop("name", None)
        if self.name is not None:
            self.name = str(self.name)
        self._parameter_name = self.name  # default
        resolved_type: Any = self._strip_none_type(self._parse_type_alias(input_type))
        self._raw_type: Any = resolved_type

        enum_choices: list[OptionChoice] = []
        if _is_enum_type(resolved_type):
            if description is None and resolved_type.__doc__ is not None:
                description = inspect.cleandoc(resolved_type.__doc__)
                if description and len(description) > 100:
                    description = description[:97] + "..."
                    _log.warning(
                        "Option %s's description was truncated due to Enum %s's docstring exceeding 100 characters.",
                        self.name,
                        resolved_type,
                    )
            enum_choices = [OptionChoice(e.name, e.value) for e in resolved_type]
            value_class = enum_choices[0].value.__class__
            if value_class in SlashCommandOptionType.__members__ and all(
                isinstance(elem.value, value_class) for elem in enum_choices
            ):
                resolved_type = _input_type_of(enum_choices[0].value.__class__)
            else:
                enum_choices = [
                    OptionChoice(e.name, str(e.value)) for e in resolved_type
                ]
                resolved_type = SlashCommandOptionType.string

        self.description = description or "No description provided"
        self.channel_types: list[ChannelType] = kwargs.pop("channel_types", [])

        if self.channel_types:
            self.input_type = SlashCommandOptionType.channel
        elif isinstance(resolved_type, SlashCommandOptionType):
            self.input_type = resolved_type
        else:
            if (members := _tuple_members(resolved_type)) is not None:
                context_type = next(
                    (op for op in members if issubclass(op, ApplicationContext)), None
                )
                if context_type is not None:
                    resolved_type = context_type

            if _is_converter(resolved_type):
                self.converter = resolved_type
                self._raw_type = str
                self.input_type = SlashCommandOptionType.string
            else:
                try:
                    self.input_type = _input_type_of(resolved_type)
                except TypeError:
                    from ..ext.commands.converter import CONVERTER_MAPPING

                    if resolved_type not in CONVERTER_MAPPING:
                        raise
                    self.converter = CONVERTER_MAPPING[resolved_type]
                    self._raw_type = str
                    self.input_type = SlashCommandOptionType.string
                else:
                    if self.input_type == SlashCommandOptionType.channel:
                        raw_types = _channel_raw_types(self._raw_type, resolved_type)
                        self._raw_type = raw_types
                        if not self.channel_types:
                            self.channel_types = [
                                CHANNEL_TYPE_MAP[t]
                                for t in raw_types
                                if t is not GuildChannel
                            ]
        self.required: bool = (
            kwargs.pop("required", True) if "default" not in kwargs else False
        )
        self.default: Any = kwargs.pop("default", None)

        self._autocomplete: AutocompleteFunction | None = None
        self._autocomplete_is_instance_method: bool = False
        self.autocomplete = kwargs.pop("autocomplete", None)
        if len(enum_choices) > 25:
            self.choices: list[OptionChoice] = []
            for e in enum_choices:
                e.value = str(e.value)
            self.autocomplete = basic_autocomplete(enum_choices)
            self.input_type = SlashCommandOptionType.string
        else:
            self.choices: list[OptionChoice] = enum_choices or [
                o if isinstance(o, OptionChoice) else OptionChoice(o)
                for o in kwargs.pop("choices", [])
            ]

        minmax_types: tuple[type, ...]
        minmax_length_types: tuple[type, ...]
        if self.input_type == SlashCommandOptionType.integer:
            minmax_types = (int, type(None))
            minmax_typehint = "int | None"
        elif self.input_type == SlashCommandOptionType.number:
            minmax_types = (int, float, type(None))
            minmax_typehint = "int | float | None"
        else:
            minmax_types = (type(None),)
            minmax_typehint = "None"

        if self.input_type == SlashCommandOptionType.string:
            minmax_length_types = (int, type(None))
            minmax_length_typehint = "int | None"
        else:
            minmax_length_types = (type(None),)
            minmax_length_typehint = "None"

        min_value: Any = kwargs.pop("min_value", None)
        max_value: Any = kwargs.pop("max_value", None)
        min_length: Any = kwargs.pop("min_length", None)
        max_length: Any = kwargs.pop("max_length", None)
        self.min_value: int | float | None = min_value
        self.max_value: int | float | None = max_value
        self.min_length: int | None = min_length
        self.max_length: int | None = max_length

        if self.input_type not in (
            SlashCommandOptionType.integer,
            SlashCommandOptionType.number,
        ) and (self.min_value or self.max_value):
            raise AttributeError(
                "Option does not take min_value or max_value if not of type "
                "SlashCommandOptionType.integer or SlashCommandOptionType.number"
            )
        if self.input_type != SlashCommandOptionType.string and (
            self.min_length or self.max_length
        ):
            raise AttributeError(
                "Option does not take min_length or max_length if not of type str"
            )

        if min_value is not None and not _is_instance(min_value, minmax_types):
            raise TypeError(
                f"Expected {minmax_typehint} for min_value, got"
                f' "{type(min_value).__name__}"'
            )
        if max_value is not None and not _is_instance(max_value, minmax_types):
            raise TypeError(
                f"Expected {minmax_typehint} for max_value, got"
                f' "{type(max_value).__name__}"'
            )

        if min_length is not None:
            if not _is_instance(min_length, minmax_length_types):
                raise TypeError(
                    f"Expected {minmax_length_typehint} for min_length,"
                    f' got "{type(min_length).__name__}"'
                )
            if min_length < 0 or min_length > 6000:
                raise AttributeError(
                    "min_length must be between 0 and 6000 (inclusive)"
                )
        if max_length is not None:
            if not _is_instance(max_length, minmax_length_types):
                raise TypeError(
                    f"Expected {minmax_length_typehint} for max_length,"
                    f' got "{type(max_length).__name__}"'
                )
            if max_length < 1 or max_length > 6000:
                raise AttributeError("max_length must between 1 and 6000 (inclusive)")

        self.name_localizations = kwargs.pop("name_localizations", MISSING)
        self.description_localizations = kwargs.pop(
            "description_localizations", MISSING
        )

        if resolved_type is None:
            raise TypeError("input_type cannot be NoneType.")

    @staticmethod
    def _parse_type_alias(input_type: Any) -> Any:
        if isinstance(input_type, TypeAliasType):
            return input_type.__value__
        return input_type

    @staticmethod
    def _strip_none_type(input_type: Any) -> Any:
        if isinstance(input_type, SlashCommandOptionType):
            return input_type

        if input_type is type(None):
            raise TypeError("Option type cannot be only NoneType")

        args: tuple[Any, ...] = ()
        if (
            isinstance(input_type, types.UnionType)
            or getattr(input_type, "__origin__", None) is Union
        ):
            args = get_args(input_type)
        elif (members := _tuple_members(input_type)) is not None:
            args = members

        if args:
            filtered = tuple(t for t in args if t is not type(None))
            if not filtered:
                raise TypeError("Option type cannot be only NoneType")
            if len(filtered) == 1:
                return filtered[0]

            return filtered

        return input_type

    def to_dict(self) -> dict[str, Any]:
        """Converts this option into the payload sent to Discord."""
        as_dict: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "type": self.input_type.value,
            "required": self.required,
            "choices": [c.to_dict() for c in self.choices],
            "autocomplete": bool(self.autocomplete),
        }
        if self.name_localizations is not MISSING:
            as_dict["name_localizations"] = self.name_localizations
        if self.description_localizations is not MISSING:
            as_dict["description_localizations"] = self.description_localizations
        if self.channel_types:
            as_dict["channel_types"] = [t.value for t in self.channel_types]
        if self.min_value is not None:
            as_dict["min_value"] = self.min_value
        if self.max_value is not None:
            as_dict["max_value"] = self.max_value
        if self.min_length is not None:
            as_dict["min_length"] = self.min_length
        if self.max_length is not None:
            as_dict["max_length"] = self.max_length

        return as_dict

    def __repr__(self) -> str:
        return f"<discord.commands.{self.__class__.__name__} name={self.name}>"

    @property
    def autocomplete(self) -> AutocompleteFunction | None:
        """The autocomplete handler for the option.

        Accepts a callable (sync or async) that takes a single required argument of :class:`AutocompleteContext` or two arguments
        of :class:`discord.Cog` (being the command's cog) and :class:`AutocompleteContext`.
        The callable must return an iterable of :class:`str` or :class:`OptionChoice`.
        Alternatively, :func:`discord.utils.basic_autocomplete` may be used in place of the callable.

        Returns
        -------
        Optional[AutocompleteFunction]

        .. versionchanged:: 2.7

        .. note::
            Does not validate the input value against the autocomplete results.
        """
        return self._autocomplete

    @autocomplete.setter
    def autocomplete(self, value: AutocompleteFunction | None) -> None:
        self._autocomplete = value
        # this is done here so it does not have to be computed every time the autocomplete is invoked
        if self._autocomplete is not None:
            self._autocomplete_is_instance_method = (
                sum(
                    1
                    for param in inspect.signature(
                        self._autocomplete
                    ).parameters.values()
                    if param.default == param.empty
                    and param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD)
                )
                == 2
            )


class OptionChoice:
    """
    Represents a name:value pairing for a selected :class:`.Option`.

    .. versionadded:: 2.0

    Attributes
    ----------
    name: :class:`str`
        The name of the choice. Shown in the UI when selecting an option.
    value: Optional[Union[:class:`str`, :class:`int`, :class:`float`]]
        The value of the choice. If not provided, will use the value of ``name``.
    name_localizations: Dict[:class:`str`, :class:`str`]
        The name localizations for this choice. The values of this should be ``"locale": "name"``.
        See `here <https://docs.discord.com/developers/reference#locales>`_ for a list of valid locales.
    """

    def __init__(
        self,
        name: str,
        value: str | float | None = None,
        name_localizations: dict[str, str] = MISSING,
    ) -> None:
        self.name = str(name)
        self.value = value if value is not None else name
        self.name_localizations = name_localizations

    def to_dict(self) -> dict[str, Any]:
        """Converts this choice into the payload sent to Discord."""
        as_dict: dict[str, Any] = {"name": self.name, "value": self.value}
        if self.name_localizations is not MISSING:
            as_dict["name_localizations"] = self.name_localizations

        return as_dict


def option(
    name: str, input_type: InputType | None = None, **kwargs: Any
) -> Callable[[F], F]:
    """A decorator that can be used instead of typehinting :class:`.Option`.

    .. versionadded:: 2.0

    Attributes
    ----------
    parameter_name: :class:`str`
        The name of the target function parameter this option is mapped to.
        This allows you to have a separate UI ``name`` and parameter name.
    """

    def decorator(func: F) -> F:
        annotations: dict[str, Any] = func.__annotations__
        resolved_name: str = kwargs.pop("parameter_name", None) or name
        itype = (
            kwargs.pop("type", None)
            or input_type
            or annotations.get(resolved_name, str)
        )
        annotations[resolved_name] = Option(itype, name=name, **kwargs)
        return func

    return decorator
