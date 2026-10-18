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

from typing import Final

__all__ = (
    "ComponentLimits",
    "EmbedLimits",
)


class ComponentLimits:
    """The limits Discord applies to components.

    They are documented in the
    `component reference <https://discord.com/developers/docs/components/reference>`_.

    Every attribute is a plain :class:`int` and is the value the library validates against.

    .. versionadded:: 3.0

    Attributes
    ----------
    VIEW_CHILDREN_MAX
        Total number of components (nested ones included) in a message that uses
        Components V2.
    LEGACY_VIEW_ROWS_MAX
        Number of action rows in a message that only uses legacy components.
    ACTION_ROW_CHILDREN_MAX
        Number of buttons in an action row, or the width an action row can hold.
    BUTTON_LABEL_MAX
        Maximum length of a button label.
    CUSTOM_ID_MAX
        Maximum length of a ``custom_id``, for every interactive component.
    SELECT_PLACEHOLDER_MAX
        Maximum length of a select placeholder.
    SELECT_OPTIONS_MAX
        Maximum number of options of a string select.
    SELECT_DEFAULT_VALUES_MAX
        Maximum number of default values of an auto-populated select.
    SELECT_MIN_VALUES_MIN, SELECT_MIN_VALUES_MAX
        Range of ``min_values`` of a select.
    SELECT_MAX_VALUES_MIN, SELECT_MAX_VALUES_MAX
        Range of ``max_values`` of a select.
    SELECT_OPTION_LABEL_MAX, SELECT_OPTION_VALUE_MAX, SELECT_OPTION_DESCRIPTION_MAX
        Maximum length of the label, value and description of a select option
        (also used for radio group and checkbox group options).
    SECTION_CHILDREN_MAX
        Maximum number of components of a section.
    THUMBNAIL_DESCRIPTION_MAX, MEDIA_GALLERY_ITEM_DESCRIPTION_MAX
        Maximum length of the alt text of a thumbnail or media gallery item.
    MEDIA_GALLERY_ITEMS_MAX
        Maximum number of items of a media gallery.
    TEXT_INPUT_LABEL_MAX, TEXT_INPUT_PLACEHOLDER_MAX, TEXT_INPUT_VALUE_MAX
        Maximum length of the label, placeholder and pre-filled value of a text input.
    TEXT_INPUT_MIN_LENGTH_MIN, TEXT_INPUT_MIN_LENGTH_MAX
        Range of ``min_length`` of a text input.
    TEXT_INPUT_MAX_LENGTH_MIN, TEXT_INPUT_MAX_LENGTH_MAX
        Range of ``max_length`` of a text input.
    LABEL_TEXT_MAX, LABEL_DESCRIPTION_MAX
        Maximum length of the text and description of a label.
    RADIO_OPTIONS_MIN, RADIO_OPTIONS_MAX
        Range of the number of options of a radio group.
    CHECKBOX_OPTIONS_MAX
        Maximum number of options of a checkbox group.
    CHECKBOX_MIN_VALUES_MIN, CHECKBOX_MIN_VALUES_MAX
        Range of ``min_values`` of a checkbox group.
    CHECKBOX_MAX_VALUES_MIN, CHECKBOX_MAX_VALUES_MAX
        Range of ``max_values`` of a checkbox group.
    FILE_UPLOAD_MIN_VALUES_MIN, FILE_UPLOAD_MIN_VALUES_MAX
        Range of ``min_values`` of a file upload.
    FILE_UPLOAD_MAX_VALUES_MIN, FILE_UPLOAD_MAX_VALUES_MAX
        Range of ``max_values`` of a file upload.
    MODAL_TITLE_MAX
        Maximum length of the title of a modal.
    MODAL_COMPONENTS_MAX
        Maximum number of components of a modal.
    """

    VIEW_CHILDREN_MAX: Final = 40
    LEGACY_VIEW_ROWS_MAX: Final = 5

    ACTION_ROW_CHILDREN_MAX: Final = 5

    BUTTON_LABEL_MAX: Final = 80

    CUSTOM_ID_MAX: Final = 100

    SELECT_PLACEHOLDER_MAX: Final = 150
    SELECT_OPTIONS_MAX: Final = 25
    SELECT_DEFAULT_VALUES_MAX: Final = 25
    SELECT_MIN_VALUES_MIN: Final = 0
    SELECT_MIN_VALUES_MAX: Final = 25
    SELECT_MAX_VALUES_MIN: Final = 1
    SELECT_MAX_VALUES_MAX: Final = 25

    SELECT_OPTION_LABEL_MAX: Final = 100
    SELECT_OPTION_VALUE_MAX: Final = 100
    SELECT_OPTION_DESCRIPTION_MAX: Final = 100

    SECTION_CHILDREN_MAX: Final = 3

    THUMBNAIL_DESCRIPTION_MAX: Final = 1024
    MEDIA_GALLERY_ITEM_DESCRIPTION_MAX: Final = 1024
    MEDIA_GALLERY_ITEMS_MAX: Final = 10

    TEXT_INPUT_LABEL_MAX: Final = 45
    TEXT_INPUT_PLACEHOLDER_MAX: Final = 100
    TEXT_INPUT_VALUE_MAX: Final = 4000
    TEXT_INPUT_MIN_LENGTH_MIN: Final = 0
    TEXT_INPUT_MIN_LENGTH_MAX: Final = 4000
    TEXT_INPUT_MAX_LENGTH_MIN: Final = 1
    TEXT_INPUT_MAX_LENGTH_MAX: Final = 4000

    LABEL_TEXT_MAX: Final = 45
    LABEL_DESCRIPTION_MAX: Final = 100

    RADIO_OPTIONS_MIN: Final = 2
    RADIO_OPTIONS_MAX: Final = 10

    CHECKBOX_OPTIONS_MAX: Final = 10
    CHECKBOX_MIN_VALUES_MIN: Final = 0
    CHECKBOX_MIN_VALUES_MAX: Final = 10
    CHECKBOX_MAX_VALUES_MIN: Final = 1
    CHECKBOX_MAX_VALUES_MAX: Final = 10

    FILE_UPLOAD_MIN_VALUES_MIN: Final = 0
    FILE_UPLOAD_MIN_VALUES_MAX: Final = 10
    FILE_UPLOAD_MAX_VALUES_MIN: Final = 1
    FILE_UPLOAD_MAX_VALUES_MAX: Final = 10

    MODAL_TITLE_MAX: Final = 45
    MODAL_COMPONENTS_MAX: Final = 5


class EmbedLimits:
    """The limits Discord applies to embeds.

    They are documented in the
    `message resource <https://discord.com/developers/docs/resources/message#embed-object-embed-limits>`_.

    Every attribute is a plain :class:`int`. Lengths are measured inclusively and leading and
    trailing whitespace is not counted, as Discord trims it.

    .. versionadded:: 3.0

    Attributes
    ----------
    TITLE_MAX
        Maximum length of the title.
    DESCRIPTION_MAX
        Maximum length of the description.
    FIELDS_MAX
        Maximum number of fields.
    FIELD_NAME_MAX
        Maximum length of a field name.
    FIELD_VALUE_MAX
        Maximum length of a field value.
    FOOTER_TEXT_MAX
        Maximum length of the footer text.
    AUTHOR_NAME_MAX
        Maximum length of the author name.
    TOTAL_MAX
        Maximum combined number of characters of the title, description, field names, field values,
        footer text and author name across all the embeds of a message.
    """

    TITLE_MAX: Final = 256
    DESCRIPTION_MAX: Final = 4096
    FIELDS_MAX: Final = 25
    FIELD_NAME_MAX: Final = 256
    FIELD_VALUE_MAX: Final = 1024
    FOOTER_TEXT_MAX: Final = 2048
    AUTHOR_NAME_MAX: Final = 256
    TOTAL_MAX: Final = 6000
