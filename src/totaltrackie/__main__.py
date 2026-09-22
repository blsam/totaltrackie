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
import sys

from totaltrackie.core import APP_NAME
from totaltrackie.ui._utils import start_gui_app
from totaltrackie.ui.main import MainWindow

_logger = logging.getLogger(APP_NAME)


def main() -> int:
    _application, persistent_store = start_gui_app(logger=_logger, log_stderr=False, log_name="app")

    _application.setQuitOnLastWindowClosed(False)

    _main_window = MainWindow(persistent_store)
    _main_window.show()

    _logger.debug("Starting application...")
    _application.exec()
    _logger.debug("Application stop.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
