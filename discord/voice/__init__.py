"""Voice support for the Discord API.

Copyright (c) 2015-2021 Rapptz
Copyright (c) 2021-present Pycord Development

:license: MIT, see LICENSE for more details.
"""

from __future__ import annotations

from ..errors import MissingVoiceDependenciesError
from ..utils import get_missing_voice_dependencies

if missing := get_missing_voice_dependencies():
    raise MissingVoiceDependenciesError(missing=missing)

from ._types import *
from .client import *
from .packets import *
