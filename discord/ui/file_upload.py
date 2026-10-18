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

from typing import TYPE_CHECKING, Any, cast

from typing_extensions import override

from ..components import FileUpload as FileUploadComponent
from ..enums import ComponentType
from ..limits import ComponentLimits
from ..message import Attachment
from ._fields import (
    Field,
    custom_id_checks,
    in_range,
    new_custom_id,
    type_check,
)
from .item import ModalItem

__all__ = ("FileUpload",)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ..components import Component
    from ..interactions import Interaction
    from ..types.components import FileUploadComponent as FileUploadComponentPayload


class FileUpload(ModalItem):
    """Represents a UI File Upload component.

    .. versionadded:: 2.7

    Parameters
    ----------
    custom_id: Optional[:class:`str`]
        The ID of the file upload field that gets received during an interaction.
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

    __item_repr_attributes__: tuple[str, ...] = (
        "required",
        "min_values",
        "max_values",
        "custom_id",
        "id",
    )

    __component__ = FileUploadComponent
    __component_type__ = ComponentType.file_upload

    if TYPE_CHECKING:

        @property
        def underlying(self) -> FileUploadComponent:
            """The component wrapped by this item."""
            ...

        @underlying.setter
        def underlying(self, value: Component) -> None: ...

    custom_id: Field[str] = Field(
        "The custom id that gets received during an interaction.",
        *custom_id_checks,
        default=new_custom_id,
    )
    min_values: Field[int | None] = Field(
        "The minimum number of files that must be uploaded. Defaults to 0.",
        type_check(int, nullable=True),
        in_range(
            ComponentLimits.FILE_UPLOAD_MIN_VALUES_MIN,
            ComponentLimits.FILE_UPLOAD_MIN_VALUES_MAX,
            skip_falsy=True,
        ),
    )
    max_values: Field[int | None] = Field(
        "The maximum number of files that can be uploaded.",
        type_check(int, nullable=True),
        in_range(
            ComponentLimits.FILE_UPLOAD_MAX_VALUES_MIN,
            ComponentLimits.FILE_UPLOAD_MAX_VALUES_MAX,
            skip_falsy=True,
        ),
    )
    required: Field[bool] = Field(
        "Whether the input file upload is required or not. Defaults to ``True``.",
        type_check(bool),
    )

    def __init__(
        self,
        *,
        custom_id: str | None = None,
        min_values: int | None = None,
        max_values: int | None = None,
        required: bool = True,
        id: int | None = None,
    ) -> None:
        super().__init__()
        self._attachments: list[Attachment] | None = None

        self._build_underlying(
            custom_id=custom_id,
            min_values=min_values,
            max_values=max_values,
            required=required,
            id=id,
        )

    @property
    def values(self) -> list[Attachment] | None:
        """The files that were uploaded to the field. This will be ``None`` if the file upload has not been submitted via a modal yet."""
        return self._attachments

    @override
    def to_component_dict(self) -> FileUploadComponentPayload:
        return self.underlying.to_dict()

    @override
    def refresh_from_modal(
        self, interaction: Interaction, data: Mapping[str, Any]
    ) -> None:
        values = data.get("values", [])
        resolved = cast("Mapping[str, Any]", interaction.data)["resolved"]
        self._attachments = [
            Attachment(
                state=interaction._state,
                data=resolved["attachments"][attachment_id],
            )
            for attachment_id in values
        ]
