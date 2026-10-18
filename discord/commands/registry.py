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

"""The per-bot registry that merges slash command groups shared by several cogs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .core import SlashCommand, SlashCommandGroup

if TYPE_CHECKING:
    from ..cog import Cog

__all__ = ("GroupKey", "GroupRegistry", "declared_parent")

GroupKey = tuple[str, tuple[int, ...] | None]
Member = SlashCommand | SlashCommandGroup


def declared_parent(command: Member) -> SlashCommandGroup | None:
    """Returns the group ``command`` was declared on, whatever group it is attached to now."""
    return command.__dict__.setdefault("_declared_parent", command.parent)


class Attachment:
    __slots__ = ("attached", "claimed", "registered")

    def __init__(self) -> None:
        self.attached: list[tuple[SlashCommandGroup, Member]] = []
        self.claimed: list[SlashCommandGroup] = []
        self.registered: list[SlashCommandGroup] = []


class GroupRegistry:
    """Keeps one canonical :class:`.SlashCommandGroup` per name and set of guilds.

    Cogs contribute the subcommands they declare to the canonical group when
    they are loaded and take them back when they are unloaded.

    The cog that keeps a group as a class attribute owns it. The owner takes
    part in every invocation of the group, including the commands of other cogs:

    - ``cog_check`` runs before the checks of the group and of the leaf cog.
    - ``cog_before_invoke`` runs before the one of the leaf cog, and
      ``cog_after_invoke`` after it. With nested groups owned by different cogs,
      the outermost owner runs first before the command and last after it.
    - ``cog_command_error`` runs after the one of the leaf cog.

    An owner that is also the cog of the leaf is only called once.
    """

    def __init__(self, bot: Any) -> None:
        self._bot: Any = bot
        self.groups: dict[GroupKey, SlashCommandGroup] = {}
        self._auto: list[SlashCommandGroup] = []

    def key_for(self, group: SlashCommandGroup) -> GroupKey:
        """Returns the key ``group`` is registered under."""
        guild_ids = group.guild_ids
        if guild_ids is None and self._bot.debug_guilds:
            guild_ids = self._bot.debug_guilds
        return group.name, tuple(sorted(guild_ids)) if guild_ids else None

    def get(self, group: SlashCommandGroup) -> SlashCommandGroup | None:
        """Returns the canonical group registered for the key of ``group``."""
        return self.groups.get(self.key_for(group))

    def register(self, group: SlashCommandGroup) -> None:
        """Registers a top level group the bot has been given."""
        if group.parent is None:
            self.groups.setdefault(self.key_for(group), group)
            group._prune_inactive()

    def unregister(self, group: SlashCommandGroup) -> None:
        """Forgets ``group`` after the bot dropped it."""
        for key, registered in list(self.groups.items()):
            if registered is group:
                del self.groups[key]
        self._auto = [g for g in self._auto if g is not group]

    def attach(self, cog: Cog) -> bool:
        """Adds the groups and subcommands declared by ``cog``, returns whether a group changed."""
        cls = type(cog)
        attachment = Attachment()
        changed = False
        try:
            for command in cls.__cog_commands__:
                if isinstance(command, SlashCommandGroup):
                    changed |= self._attach_home(cog, command, attachment)
            for member in cls.__cog_group_members__:
                declared = declared_parent(member)
                if declared is None:
                    continue
                parent = self._canonical_parent(declared, cog, attachment)
                if parent._attach_member(member, cog):
                    changed = True
                attachment.attached.append((parent, member))
            for group in {id(g): g for g in self._tops(attachment)}.values():
                changed |= group._prune_inactive()
        except BaseException:
            self._rollback(cog, attachment)
            raise
        cog.__cog_attachment__ = attachment
        return changed

    def detach(self, cog: Cog) -> bool:
        """Takes back what :meth:`attach` added for ``cog``, returns whether a group changed."""
        attachment: Attachment | None = getattr(cog, "__cog_attachment__", None)
        if attachment is None:
            return False
        cog.__cog_attachment__ = None
        return self._rollback(cog, attachment)

    def _tops(self, attachment: Attachment) -> list[SlashCommandGroup]:
        tops: list[SlashCommandGroup] = list(attachment.registered)
        for parent, _ in attachment.attached:
            tops.append(self._top_of(parent))
        tops.extend(attachment.claimed)
        return [t for t in tops if self.groups.get(self.key_for(t)) is t]

    @staticmethod
    def _top_of(group: SlashCommandGroup) -> SlashCommandGroup:
        while group.parent is not None:
            group = group.parent
        return group

    def _home_of(self, cog: Cog, group: SlashCommandGroup) -> SlashCommandGroup:
        for original, copy in type(cog).__cog_group_copies__:
            if original is group:
                return copy
        return group

    def _attach_home(
        self, cog: Cog, home: SlashCommandGroup, attachment: Attachment
    ) -> bool:
        canonical = self.get(home)
        if canonical is None:
            self._bot.add_application_command(home)
            self._auto.append(home)
            attachment.registered.append(home)
            for child in home.subcommands:
                child.parent = home
                if isinstance(child, SlashCommandGroup):
                    for grandchild in child.subcommands:
                        grandchild.parent = child
            return True

        changed = False
        if canonical is not home:
            for child in list(home.subcommands):
                if canonical._attach_member(child, cog):
                    changed = True
                attachment.attached.append((canonical, child))
        if canonical.cog is None:
            canonical.cog = cog
            attachment.claimed.append(canonical)
        return changed

    def _canonical_parent(
        self, node: SlashCommandGroup, cog: Cog, attachment: Attachment
    ) -> SlashCommandGroup:
        parent = declared_parent(node)
        if parent is None:
            home = self._home_of(cog, node)
            canonical = self.get(home)
            if canonical is None:
                self._bot.add_application_command(home)
                self._auto.append(home)
                attachment.registered.append(home)
                canonical = home
            return canonical

        canonical_parent = self._canonical_parent(parent, cog, attachment)
        for existing in canonical_parent.subcommands:
            if isinstance(existing, SlashCommandGroup) and existing.name == node.name:
                return existing
        canonical_parent._attach_member(node, cog)
        attachment.attached.append((canonical_parent, node))
        return node

    def _rollback(self, cog: Cog, attachment: Attachment) -> bool:
        changed = False
        parents: list[SlashCommandGroup] = []
        for parent, member in reversed(attachment.attached):
            if isinstance(member, SlashCommandGroup) and member.subcommands:
                continue
            if parent._detach_member(member):
                changed = True
                member.parent = declared_parent(member)
                if member.cog is cog:
                    member._unset_cog()
                parents.append(parent)
        for group in attachment.claimed:
            if group.cog is cog:
                group._unset_cog()
        for group in attachment.registered:
            if group.cog is cog:
                group._unset_cog()

        for parent in parents:
            node = parent
            while node.parent is not None and not node.subcommands:
                up = node.parent
                up._detach_member(node)
                node.parent = declared_parent(node)
                node = up

        for group in attachment.registered + attachment.claimed:
            if self.groups.get(self.key_for(group)) is group:
                group._prune_inactive()
                if (
                    group.cog is None
                    and not group.subcommands
                    and any(g is group for g in self._auto)
                ):
                    self._bot.remove_application_command(group)
                    changed = True
        for parent in parents:
            top = self._top_of(parent)
            if top.parent is None and self.groups.get(self.key_for(top)) is top:
                top._prune_inactive()
                if (
                    top.cog is None
                    and not top.subcommands
                    and any(g is top for g in self._auto)
                ):
                    self._bot.remove_application_command(top)
                    changed = True
        return changed
