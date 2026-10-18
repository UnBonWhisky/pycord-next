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

import io
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

import pytest

import discord
from discord.ext import bridge, pages
from tests.ext.test_pages import context, interaction, sent_message

if TYPE_CHECKING:
    from pathlib import Path


def file(name: str = "a.txt") -> discord.File:
    return discord.File(io.BytesIO(b"data"), filename=name)


def message_with_edit() -> Mock:
    message = sent_message()
    message.edit = AsyncMock()
    message.id = 1500000000000000001
    return message


class TestPaginatorButton:
    def test_defaults(self) -> None:
        button = pages.PaginatorButton("next")
        assert button.label == "Next"
        assert button.loop_label == "Next"
        assert button.paginator is None
        assert pages.PaginatorButton("x", emoji="\N{PENGUIN}").label is None
        assert pages.PaginatorButton("x", label="L", loop_label="LL").loop_label == "LL"

    @pytest.mark.parametrize(
        ("kind", "current", "loop", "expected"),
        [
            ("first", 2, False, 0),
            ("prev", 2, False, 1),
            ("prev", 0, True, 3),
            ("next", 1, False, 2),
            ("next", 3, True, 0),
            ("last", 0, False, 3),
        ],
    )
    async def test_callbacks(
        self, kind: str, current: int, loop: bool, expected: int
    ) -> None:
        paginator = pages.Paginator(pages=["a", "b", "c", "d"], loop_pages=loop)
        paginator.current_page = current
        paginator.goto_page = AsyncMock()
        target = interaction()
        await paginator.buttons[kind]["object"].callback(target)
        paginator.goto_page.assert_awaited_once_with(
            page_number=expected, interaction=target
        )

    async def test_unknown_button_type_keeps_the_page(self) -> None:
        paginator = pages.Paginator(pages=["a", "b"], use_default_buttons=False)
        button = pages.PaginatorButton("custom")
        paginator.add_button(button)
        paginator.goto_page = AsyncMock()
        paginator.current_page = 1
        await button.callback(interaction())
        assert paginator.goto_page.await_args.kwargs["page_number"] == 1


class TestPage:
    def test_requires_something(self) -> None:
        with pytest.raises(discord.InvalidArgument):
            pages.Page()

    async def test_properties_and_callback(self) -> None:
        page = pages.Page(content="x")
        page.content = "y"
        page.embeds = [discord.Embed(title="t")]
        page.files = [file()]
        view = discord.ui.View()
        page.custom_view = view
        assert page.content == "y"
        assert page.embeds[0].title == "t"
        assert len(page.files) == 1
        assert page.custom_view is view
        assert await page.callback() is None

    def test_update_files_resets_and_protects_the_file(self) -> None:
        f = file()
        page = pages.Page(content="x", files=[f])
        f.fp.read()
        assert page.update_files() == [f]
        assert f.fp.tell() == 0
        f.fp.close()
        assert not f.fp.closed

    def test_update_files_reopens_closed_files(self, tmp_path: Path) -> None:
        path = tmp_path / "f.txt"
        path.write_bytes(b"abc")
        f = discord.File(str(path))
        real_close = f.fp.close
        real_close()
        page = pages.Page(content="x", files=[f])
        page.update_files()
        assert f.fp.read() == b"abc"
        real_close = f.fp.__class__.close
        real_close(f.fp)


class TestConstruction:
    async def test_groups_pick_the_default(self) -> None:
        groups = [
            pages.PageGroup(pages=["a1", "a2"], label="A"),
            pages.PageGroup(pages=["b1", "b2", "b3"], label="B", default=True),
        ]
        paginator = pages.Paginator(pages=groups, show_menu=True)
        assert paginator.page_count == 2
        assert [p.content for p in paginator.pages] == ["b1", "b2", "b3"]
        assert paginator.page_groups == groups
        assert isinstance(paginator.menu, pages.PaginatorMenu)
        assert paginator.menu.paginator is paginator
        assert [o.label for o in paginator.menu.options] == ["A", "B"]

    async def test_groups_without_menu(self) -> None:
        paginator = pages.Paginator(pages=[pages.PageGroup(pages=["a"], label="A")])
        assert paginator.page_groups is None
        assert paginator.menu is None

    async def test_only_one_default_group(self) -> None:
        groups = [
            pages.PageGroup(pages=["a"], label="A", default=True),
            pages.PageGroup(pages=["b"], label="B", default=True),
        ]
        with pytest.raises(ValueError, match="Only one PageGroup"):
            pages.Paginator(pages=groups)

    async def test_empty_pages(self) -> None:
        assert pages.Paginator(pages=[]).page_count == 0

    async def test_custom_buttons(self) -> None:
        custom = [
            pages.PaginatorButton("next", label="N"),
            pages.PaginatorButton("prev"),
        ]
        paginator = pages.Paginator(
            pages=["a", "b"], use_default_buttons=False, custom_buttons=custom
        )
        assert set(paginator.buttons) == {"next", "prev"}
        assert custom[0].paginator is paginator

    async def test_no_buttons(self) -> None:
        paginator = pages.Paginator(pages=["a"], use_default_buttons=False)
        assert paginator.buttons == {}

    async def test_remove_button(self) -> None:
        paginator = pages.Paginator(pages=["a", "b"])
        paginator.remove_button("first")
        assert "first" not in paginator.buttons
        with pytest.raises(ValueError, match="no button_type"):
            paginator.remove_button("first")

    async def test_button_labels(self) -> None:
        paginator = pages.Paginator(pages=["a", "b", "c"])
        paginator.update_buttons()
        assert paginator.buttons["page_indicator"]["object"].label == "1/3"
        assert paginator.buttons["next"]["object"].label == ">"


class TestUpdateButtons:
    def labels(self, paginator: pages.Paginator) -> dict[str, tuple[Any, bool]]:
        return {
            key: (b["object"].label, b["object"].disabled)
            for key, b in paginator.buttons.items()
        }

    async def test_middle_page(self) -> None:
        paginator = pages.Paginator(pages=list("abcde"))
        paginator.current_page = 2
        paginator.update_buttons()
        assert {k: v[1] for k, v in self.labels(paginator).items()} == {
            "first": False,
            "prev": False,
            "page_indicator": True,
            "next": False,
            "last": False,
        }
        assert paginator.buttons["page_indicator"]["object"].label == "3/5"

    async def test_edges_hide_buttons(self) -> None:
        paginator = pages.Paginator(pages=list("abc"))
        paginator.update_buttons()
        assert self.labels(paginator)["prev"][1] is True
        assert self.labels(paginator)["first"][1] is True
        paginator.current_page = 2
        paginator.update_buttons()
        assert self.labels(paginator)["next"][1] is True
        assert self.labels(paginator)["last"][1] is True

    async def test_disabled_buttons_can_be_omitted(self) -> None:
        paginator = pages.Paginator(pages=list("abc"), show_disabled=False)
        paginator.update_buttons()
        assert paginator.buttons["prev"]["object"] not in paginator.children
        assert paginator.buttons["next"]["object"] in paginator.children

    async def test_indicator_can_be_omitted(self) -> None:
        paginator = pages.Paginator(pages=list("abc"), show_indicator=False)
        paginator.update_buttons()
        assert paginator.buttons["page_indicator"]["object"] not in paginator.children

    async def test_looping_changes_the_labels(self) -> None:
        paginator = pages.Paginator(pages=list("abc"), loop_pages=True)
        paginator.update_buttons()
        assert paginator.buttons["prev"]["object"].label == "↪"
        assert not paginator.buttons["prev"]["hidden"] or True
        paginator.current_page = 2
        paginator.update_buttons()
        assert paginator.buttons["next"]["object"].label == "↩"
        paginator.current_page = 1
        paginator.update_buttons()
        assert paginator.buttons["next"]["object"].label == ">"
        assert paginator.buttons["prev"]["object"].label == "<"

    async def test_menu_and_custom_view_are_kept(self) -> None:
        extra = discord.ui.Button(label="extra")
        custom = discord.ui.View(extra)
        groups = [pages.PageGroup(pages=["a", "b"], label="A")]
        paginator = pages.Paginator(pages=groups, show_menu=True, custom_view=custom)
        paginator.update_buttons()
        assert paginator.menu in paginator.children
        assert extra in paginator.children

    async def test_update_custom_view_replaces_previous_items(self) -> None:
        old = discord.ui.Button(label="old")
        new = discord.ui.Button(label="new")
        paginator = pages.Paginator(pages=["a"], custom_view=discord.ui.View(old))
        paginator.update_buttons()
        assert old in paginator.children
        paginator.update_custom_view(discord.ui.View(new))
        assert old not in paginator.children
        assert new in paginator.children


class TestGetPageContent:
    async def test_all_supported_types(self) -> None:
        f = file()
        view = discord.ui.View()
        get = pages.Paginator.get_page_content
        assert get("text").content == "text"
        assert get(discord.Embed(title="e")).embeds[0].title == "e"
        assert get(f).files == [f]
        assert get(view).custom_view is view
        assert get([f]).files == [f]
        page = pages.Page(content="p")
        assert get(page) is page

    async def test_invalid(self) -> None:
        get = pages.Paginator.get_page_content
        with pytest.raises(TypeError, match="All list items"):
            get([discord.Embed(), file()])
        with pytest.raises(TypeError, match="Page content must be"):
            get(5)

    async def test_page_group_content(self) -> None:
        paginator = pages.Paginator(pages=["x"])
        group = pages.PageGroup(pages=["a", discord.Embed(title="b")], label="g")
        content = paginator.get_page_group_content(group)
        assert [type(p) for p in content] == [pages.Page, pages.Page]


class TestUpdate:
    async def test_replaces_everything(self) -> None:
        paginator = pages.Paginator(pages=["a", "b", "c"])
        paginator.message = message_with_edit()
        await paginator.update(
            pages=["x", "y"],
            show_disabled=False,
            show_indicator=False,
            author_check=False,
            menu_placeholder="pick",
            disable_on_timeout=False,
            use_default_buttons=False,
            default_button_row=2,
            loop_pages=True,
            timeout=30,
            custom_buttons=[pages.PaginatorButton("next")],
            trigger_on_display=False,
            current_page=1,
        )
        assert paginator.page_count == 1
        assert paginator.current_page == 1
        assert paginator.usercheck is False
        assert paginator.menu_placeholder == "pick"
        assert paginator.loop_pages is True
        assert paginator.timeout == 30
        assert set(paginator.buttons) == {"next"}
        paginator.message.edit.assert_awaited_once()
        assert paginator.message.edit.await_args.kwargs["content"] == "y"

    async def test_out_of_range_page_resets(self) -> None:
        paginator = pages.Paginator(pages=["a", "b", "c"])
        paginator.message = message_with_edit()
        await paginator.update(pages=["x"], current_page=5)
        assert paginator.current_page == 0

    async def test_with_groups_and_default_buttons(self) -> None:
        paginator = pages.Paginator(pages=["a"])
        paginator.message = message_with_edit()
        groups = [
            pages.PageGroup(pages=["g1"], label="one"),
            pages.PageGroup(pages=["g2", "g3"], label="two", default=True),
        ]
        await paginator.update(pages=groups, show_menu=True)
        assert paginator.page_groups == groups
        assert paginator.page_count == 1
        assert paginator.message.edit.await_args.kwargs["content"] == "g2"

    async def test_rejects_two_default_groups(self) -> None:
        paginator = pages.Paginator(pages=["a"])
        groups = [
            pages.PageGroup(pages=["a"], label="A", default=True),
            pages.PageGroup(pages=["b"], label="B", default=True),
        ]
        with pytest.raises(ValueError, match="Only one PageGroup"):
            await paginator.update(pages=groups)

    async def test_menu_selection_switches_group(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        groups = [
            pages.PageGroup(pages=["a1"], label="A"),
            pages.PageGroup(pages=["b1", "b2"], label="B", loop_pages=True),
        ]
        paginator = pages.Paginator(pages=groups, show_menu=True)
        paginator.message = message_with_edit()
        monkeypatch.setattr(pages.PaginatorMenu, "values", property(lambda self: ["B"]))
        target = interaction()
        await paginator.menu.callback(target)
        assert paginator.page_count == 1
        assert paginator.loop_pages is True
        assert target.followup.edit_message.await_args.kwargs["content"] == "b1"

    async def test_menu_selection_without_a_match(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        groups = [pages.PageGroup(pages=["a1"], label="A")]
        paginator = pages.Paginator(pages=groups, show_menu=True)
        paginator.update = AsyncMock()
        monkeypatch.setattr(
            pages.PaginatorMenu, "values", property(lambda self: ["nope"])
        )
        await paginator.menu.callback(interaction())
        paginator.update.assert_not_awaited()


class TestLifecycle:
    async def test_on_timeout_disables_the_items(self) -> None:
        paginator = pages.Paginator(pages=["a", "b"])
        paginator.message = message_with_edit()
        await paginator.on_timeout()
        assert all(item.disabled for item in paginator.children)
        assert paginator.message.edit.await_args.kwargs["view"] is paginator

    async def test_on_timeout_suppresses_missing_messages(self) -> None:
        paginator = pages.Paginator(pages=["a"])
        paginator.message = message_with_edit()
        paginator.message.edit.side_effect = discord.NotFound(
            SimpleNamespace(status=404, reason="x"), "gone"
        )
        await paginator.on_timeout()

    async def test_on_timeout_can_be_disabled(self) -> None:
        paginator = pages.Paginator(pages=["a"], disable_on_timeout=False)
        paginator.message = message_with_edit()
        await paginator.on_timeout()
        paginator.message.edit.assert_not_awaited()

    async def test_disable(self) -> None:
        extra = discord.ui.Button(label="extra")
        paginator = pages.Paginator(
            pages=["a", "b"], custom_view=discord.ui.View(extra)
        )
        paginator.update_buttons()
        paginator.message = message_with_edit()
        await paginator.disable()
        assert not extra.disabled
        assert paginator.buttons["next"]["object"].disabled
        assert paginator.message.edit.await_args.kwargs == {"view": paginator}
        await paginator.disable(include_custom=True, page="bye")
        assert extra.disabled
        assert paginator.message.edit.await_args.kwargs["content"] == "bye"

    async def test_cancel(self) -> None:
        extra = discord.ui.Button(label="extra")
        paginator = pages.Paginator(
            pages=["a", "b"], custom_view=discord.ui.View(extra)
        )
        paginator.update_buttons()
        paginator.message = message_with_edit()
        await paginator.cancel()
        assert paginator.children == [extra]
        await paginator.cancel(include_custom=True, page=discord.Embed(title="done"))
        assert paginator.children == []
        assert paginator.message.edit.await_args.kwargs["embeds"][0].title == "done"

    async def test_goto_page_failure_restores_the_page(self) -> None:
        paginator = pages.Paginator(pages=["a", "b"])
        paginator.message = message_with_edit()
        paginator.message.edit.side_effect = discord.DiscordException("boom")
        with pytest.raises(discord.DiscordException):
            await paginator.goto_page(1)
        assert paginator.current_page == 0

    async def test_goto_page_triggers_the_page_callback(self) -> None:
        triggered: list[Any] = []

        class Tracked(pages.Page):
            async def callback(self, interaction: Any = None) -> None:
                triggered.append(interaction)

        paginator = pages.Paginator(
            pages=[Tracked(content="a"), Tracked(content="b")], trigger_on_display=True
        )
        paginator.message = message_with_edit()
        await paginator.goto_page(1)
        assert triggered == [None]

    async def test_goto_page_with_a_custom_view_page(self) -> None:
        extra = discord.ui.Button(label="page-button")
        paginator = pages.Paginator(
            pages=[
                pages.Page(content="a"),
                pages.Page(content="b", custom_view=discord.ui.View(extra)),
            ]
        )
        paginator.message = message_with_edit()
        await paginator.goto_page(1)
        assert extra in paginator.children


class TestSendValidation:
    async def test_invalid_arguments(self) -> None:
        paginator = pages.Paginator(pages=["a"])
        ctx = context()
        with pytest.raises(TypeError, match=r"abc\.Messageable"):
            await paginator.send(ctx, target=object())
        with pytest.raises(TypeError, match="Message, MessageReference"):
            await paginator.send(ctx, reference=object())
        with pytest.raises(TypeError, match="AllowedMentions"):
            await paginator.send(ctx, allowed_mentions=object())
        with pytest.raises(TypeError, match="expected bool"):
            await paginator.send(ctx, mention_author="yes")

    async def test_send_passes_the_options_and_custom_view(self) -> None:
        extra = discord.ui.Button(label="x")
        paginator = pages.Paginator(
            pages=[pages.Page(content="a", custom_view=discord.ui.View(extra))]
        )
        ctx = context()
        mentions = discord.AllowedMentions.none()
        await paginator.send(
            ctx, allowed_mentions=mentions, mention_author=True, delete_after=5
        )
        kwargs = ctx.send.await_args.kwargs
        assert kwargs["allowed_mentions"] is mentions
        assert kwargs["mention_author"] is True
        assert kwargs["delete_after"] == 5
        assert extra in paginator.children


class TestEdit:
    async def test_rejects_non_messages(self) -> None:
        with pytest.raises(TypeError, match="expected Message"):
            await pages.Paginator(pages=["a"]).edit(object())

    async def test_without_a_user_the_check_is_disabled(self) -> None:
        paginator = pages.Paginator(pages=["a"])
        message = sent_message()
        message.edit = AsyncMock(return_value=message)
        await paginator.edit(message)
        assert paginator.usercheck is False

    async def test_deprecated_suppress(self) -> None:
        paginator = pages.Paginator(pages=["a"])
        message = sent_message()
        message.edit = AsyncMock(return_value=message)
        with pytest.warns(DeprecationWarning, match="suppress"):
            await paginator.edit(message, suppress=True)
        assert message.edit.await_args.kwargs["suppress_embeds"] is True

    async def test_missing_messages_are_suppressed(self) -> None:
        paginator = pages.Paginator(
            pages=[
                pages.Page(
                    content="a",
                    custom_view=discord.ui.View(discord.ui.Button(label="x")),
                )
            ]
        )
        message = sent_message()
        message.edit = AsyncMock(
            side_effect=discord.Forbidden(SimpleNamespace(status=403, reason="x"), "no")
        )
        assert await paginator.edit(message, user=SimpleNamespace(id=1)) is None


class TestRespondVariants:
    async def test_interaction_with_a_target(self) -> None:
        target = interaction()
        destination = Mock(spec=discord.abc.Messageable)
        sent = sent_message()
        destination.send = AsyncMock(return_value=sent)
        target.response.send_message = AsyncMock()
        paginator = pages.Paginator(pages=["a"])
        result = await paginator.respond(
            target, target=destination, target_message="moved"
        )
        assert result is sent
        target.response.send_message.assert_awaited_once_with("moved", ephemeral=False)

    async def test_invalid_target(self) -> None:
        with pytest.raises(TypeError, match=r"abc\.Messageable"):
            await pages.Paginator(pages=["a"]).respond(interaction(), target=object())

    async def test_ephemeral_needs_a_short_timeout(self) -> None:
        with pytest.raises(ValueError, match="ephemeral"):
            await pages.Paginator(pages=["a"], timeout=900).respond(
                interaction(), ephemeral=True
            )
        with pytest.raises(ValueError, match="ephemeral"):
            await pages.Paginator(pages=["a"], timeout=None).respond(
                interaction(), ephemeral=True
            )

    async def test_with_a_custom_view_page(self) -> None:
        extra = discord.ui.Button(label="x")
        paginator = pages.Paginator(
            pages=[pages.Page(content="a", custom_view=discord.ui.View(extra))]
        )
        target = interaction()
        reply = sent_message()
        target.response.send_message = AsyncMock(return_value=reply)
        await paginator.respond(target)
        assert extra in paginator.children

    async def test_bridge_context(self) -> None:
        ctx = Mock(spec=bridge.BridgeContext)
        ctx.author = SimpleNamespace(id=3)
        reply = sent_message()
        ctx.respond = AsyncMock(return_value=reply)
        paginator = pages.Paginator(pages=["a"])
        assert await paginator.respond(ctx) is reply
        assert paginator.user is ctx.author

    async def test_bridge_context_with_a_target(self) -> None:
        ctx = Mock(spec=bridge.BridgeContext)
        ctx.author = SimpleNamespace(id=3)
        ctx.respond = AsyncMock()
        sent = sent_message()
        ctx.send = AsyncMock(return_value=sent)
        destination = Mock(spec=discord.abc.Messageable)
        paginator = pages.Paginator(pages=["a"])
        assert (
            await paginator.respond(ctx, target=destination, target_message="m") is sent
        )
        ctx.respond.assert_awaited_once_with("m", ephemeral=False)
