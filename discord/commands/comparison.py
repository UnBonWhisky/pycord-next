# The MIT License (MIT)
#
# Copyright (c) 2015-2021 Rapptz
# Copyright (c) 2021-present Pycord Development
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

"""Rules that decide whether a local application command matches the one registered on Discord."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeAlias, cast

from typing_extensions import override

from ..utils import MISSING
from .core import ApplicationCommand, EntryPointCommand, SlashCommandGroup

__all__ = (
    "COMMAND_DEFAULTS",
    "COMMAND_OPTION_DEFAULTS",
    "OPTIONS_CHOICES_DEFAULTS",
    "PARENT_SUBCOMMAND_DEFAULTS",
    "SUBCOMMAND_DEFAULTS",
    "DefaultComparison",
    "DefaultSetComparison",
    "LocalOptionalComparison",
    "NestedComparison",
    "commands_match",
    "defaults_for_scope",
    "is_primary_entry_point",
)


def _as_set(value: Any) -> Any:
    try:
        return set(value)
    except TypeError:
        return value


class DefaultComparison:
    """Comparison rule for default values that should be considered equivalent.

    Allows for a custom check to be passed for further control over equality.

    Attributes
    ----------
    defaults: :class:`tuple`
        The values that should be considered equivalent to each other
    callback: Callable[[Any, Any], bool]
        A callable that will do additional comparison on the objects if neither are a default value.
        Defaults to a `==` comparison.
        It should accept local and remote command objects as arguments and return True if they should be considered equivalent
        and False otherwise.
    """

    def __init__(
        self,
        defaults: tuple[Any, ...],
        callback: Callable[[Any, Any], bool] = lambda x, y: x == y,
    ) -> None:
        self.defaults = defaults
        self.callback = callback

    def _is_default(self, value: Any) -> bool:
        return value in self.defaults

    def _check_defaults(self, local: Any, remote: Any) -> bool | None:
        defaults = self._is_default(local) + self._is_default(remote)
        if defaults == 2:
            return True
        if defaults == 0:
            return None
        return False

    def check(self, local: Any, remote: Any) -> bool:
        """
        Compares the local and remote objects.

        Returns
        -------
        bool
            True if local and remote are deemed to be equivalent. False otherwise.
        """
        if (rtn := self._check_defaults(local, remote)) is not None:
            return rtn
        return self.callback(local, remote)


class DefaultSetComparison(DefaultComparison):
    """A :class:`DefaultComparison` that compares collections regardless of their order."""

    @override
    def _is_default(self, value: Any) -> bool:
        return value in self.defaults or _as_set(value) in self.defaults

    @override
    def check(self, local: Any, remote: Any) -> bool:
        if (rtn := self._check_defaults(local, remote)) is not None:
            return rtn
        return self.callback(_as_set(local), _as_set(remote))


class LocalOptionalComparison(DefaultComparison):
    """A :class:`DefaultComparison` that accepts any remote value while the local one is unset."""

    @override
    def check(self, local: Any, remote: Any) -> bool:
        if local is MISSING or local is None:
            return True
        return super().check(local, remote)


NestedComparison: TypeAlias = dict[str, "NestedComparison | DefaultComparison"]


def _compare_defaults(obj: Any, match: Any, schema: NestedComparison) -> bool:
    if not isinstance(match, Mapping) or not isinstance(obj, Mapping):
        return obj is match or obj == match
    for field, comparison in schema.items():
        remote: Any = cast("Mapping[str, Any]", match).get(field, MISSING)
        local: Any = cast("Mapping[str, Any]", obj).get(field, MISSING)
        if isinstance(comparison, dict):
            if not _compare_defaults(local, remote, comparison):
                return False
        elif not comparison.check(local, remote):
            return False
    return True


def _sequence_check(
    schema: Callable[[], NestedComparison],
) -> Callable[[Any, Any], bool]:
    def check(local: Any, remote: Any) -> bool:
        return len(local) == len(remote) and all(
            _compare_defaults(x, y, schema())
            for x, y in zip(local, remote, strict=True)
        )

    return check


def _permissions_check(local: Any, remote: Any) -> bool:
    return str(local) == str(remote)


OPTION_DEFAULT_VALUES: tuple[Any, ...] = ([], MISSING)
CHOICES_DEFAULT_VALUES: tuple[Any, ...] = ([], MISSING)
LOCALIZATION_DEFAULT_VALUES: tuple[Any, ...] = (None, {}, MISSING)

_option_comparison_check = _sequence_check(lambda: COMMAND_OPTION_DEFAULTS)
_choices_comparison_check = _sequence_check(lambda: OPTIONS_CHOICES_DEFAULTS)


COMMAND_DEFAULTS: NestedComparison = {
    "type": DefaultComparison((1, MISSING)),
    "name": DefaultComparison(()),
    "description": DefaultComparison(("", MISSING)),
    "name_localizations": DefaultComparison(LOCALIZATION_DEFAULT_VALUES),
    "description_localizations": DefaultComparison(LOCALIZATION_DEFAULT_VALUES),
    "options": DefaultComparison(OPTION_DEFAULT_VALUES, _option_comparison_check),
    "default_member_permissions": DefaultComparison(
        (None, MISSING), _permissions_check
    ),
    "nsfw": DefaultComparison((False, MISSING)),
    "handler": LocalOptionalComparison((MISSING,)),
    "integration_types": DefaultSetComparison(
        (None, MISSING), lambda x, y: set(x) == set(y)
    ),
    "contexts": DefaultSetComparison((None, MISSING), lambda x, y: set(x) == set(y)),
}
SUBCOMMAND_DEFAULTS: NestedComparison = {
    "type": DefaultComparison(()),
    "name": DefaultComparison(()),
    "description": DefaultComparison(()),
    "name_localizations": DefaultComparison(LOCALIZATION_DEFAULT_VALUES),
    "description_localizations": DefaultComparison(LOCALIZATION_DEFAULT_VALUES),
    "options": DefaultComparison(OPTION_DEFAULT_VALUES, _option_comparison_check),
}
PARENT_SUBCOMMAND_DEFAULTS: NestedComparison = SUBCOMMAND_DEFAULTS.copy()
del PARENT_SUBCOMMAND_DEFAULTS["options"]
COMMAND_OPTION_DEFAULTS: NestedComparison = {
    "type": DefaultComparison(()),
    "name": DefaultComparison(()),
    "description": DefaultComparison(()),
    "name_localizations": DefaultComparison(LOCALIZATION_DEFAULT_VALUES),
    "description_localizations": DefaultComparison(LOCALIZATION_DEFAULT_VALUES),
    "required": DefaultComparison((False, MISSING)),
    "choices": DefaultComparison(CHOICES_DEFAULT_VALUES, _choices_comparison_check),
    "channel_types": DefaultSetComparison(([], MISSING, None)),
    "min_value": DefaultComparison((MISSING, None)),
    "max_value": DefaultComparison((MISSING, None)),
    "min_length": DefaultComparison((MISSING, None)),
    "max_length": DefaultComparison((MISSING, None)),
    "autocomplete": DefaultComparison((MISSING, False)),
}
OPTIONS_CHOICES_DEFAULTS: NestedComparison = {
    "name": DefaultComparison(()),
    "name_localizations": DefaultComparison(LOCALIZATION_DEFAULT_VALUES),
    "value": DefaultComparison(()),
}


def defaults_for_scope(
    defaults: NestedComparison, *, guild_id: int | None
) -> NestedComparison:
    """Returns ``defaults`` without the fields Discord only stores on global commands when ``guild_id`` is set."""
    if guild_id is None:
        return defaults
    return {
        field: rule
        for field, rule in defaults.items()
        if field not in ("contexts", "integration_types")
    }


def is_primary_entry_point(payload: Mapping[str, Any]) -> bool:
    """Whether a command payload is a ``PRIMARY_ENTRY_POINT`` command, which sync never deletes."""
    return payload.get("type") == EntryPointCommand.type


def commands_match(
    cmd: ApplicationCommand[Any, ..., Any],
    match: Mapping[str, Any],
    defaults: NestedComparison = COMMAND_DEFAULTS,
) -> bool:
    """Returns whether ``cmd`` is equivalent to the registered command payload ``match``.

    Fields are compared the way Discord stores them, so a field that is left out locally
    and a field Discord fills with its documented default are considered equal.
    """
    top_level = getattr(cmd, "parent", None) is None
    schema = defaults if top_level else SUBCOMMAND_DEFAULTS
    if not isinstance(cmd, SlashCommandGroup):
        return _compare_defaults(
            cmd.to_dict(),
            match,
            schema,
        )

    own = {field: rule for field, rule in schema.items() if field != "options"}
    if not _compare_defaults(
        cmd.to_dict(),
        match,
        own,
    ):
        return False
    remote_options: list[Mapping[str, Any]] = match.get("options") or []
    if len(cmd.subcommands) != len(remote_options):
        return False
    for subcommand in cmd.subcommands:
        remote = next(
            (o for o in remote_options if o.get("name") == subcommand.name), None
        )
        if remote is None or not commands_match(subcommand, remote, defaults):
            return False
    return True
