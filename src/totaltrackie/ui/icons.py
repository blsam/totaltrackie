#  Copyright 2024 blsam
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy of
#  this software and associated documentation files (the “Software”), to deal in
#  the Software without restriction, including without limitation the rights to use,
#  copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the
#  Software, and to permit persons to whom the Software is furnished to do so,
#  subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND,
#  EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
#  OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
#  NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
#  HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
#  WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
#  OTHER DEALINGS IN THE SOFTWARE.
#
import logging
from enum import Enum, auto
from importlib.resources import as_file, files
from pathlib import PurePosixPath

# pylint: disable=no-name-in-module
from PySide6.QtGui import QIcon
# pylint: enable=no-name-in-module

from totaltrackie.core import APP_NAME

_logger = logging.getLogger(__name__)


class IconResource(Enum):
    APP = auto()
    START = auto()
    ADD = auto()
    REMOVE = auto()
    EDIT = auto()
    OK = auto()
    CANCEL = auto()
    RELAX = auto()
    SETTINGS = auto()
    REPORT = auto()
    TEMPLATES = auto()

    def get_icon(self) -> QIcon:
        relative_path = PurePosixPath("icon_data", f"{self.name.lower()}.svg")
        with as_file(files(APP_NAME).joinpath(str(relative_path))) as real_path:
            _logger.debug("Loading resource icon from package %s...", real_path)
            return QIcon(str(real_path))
