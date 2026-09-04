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
import ctypes
import logging
import sys
import traceback
from argparse import ArgumentParser
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any

# pylint: disable=no-name-in-module
from PySide6.QtWidgets import QApplication, QMessageBox

from totaltrackie.core import APP_NAME
from totaltrackie.persistent import PersistenceManager
from totaltrackie.ui.main import MainWindow

# pylint: enable=no-name-in-module

_logger = logging.getLogger(APP_NAME)


def _configure_logging(log_base_dir: Path, logger_obj: logging.Logger, level: str) -> None:
    handler = RotatingFileHandler(
        log_base_dir / "app.log",
        backupCount=5,
        maxBytes=1024 * 1024,
    )
    handler.setLevel(level)
    logger_obj.setLevel(level)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger_obj.addHandler(handler)


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--debug", action="store_true", default=False, help="Enable debug log")
    parser.add_argument(
        "--persistent-store",
        type=Path,
        default=Path.home() / ("." + APP_NAME.lower()) / "storage",
        help="Path to folder where settings will be stored",
    )
    args = parser.parse_args()
    level = "DEBUG" if args.debug else "INFO"
    persistent_store = PersistenceManager(args.persistent_store)
    persistent_store.logs_folder.mkdir(exist_ok=True, parents=True)

    _configure_logging(persistent_store.logs_folder, _logger, level)

    def _exc_handler(exc_type: type[BaseException], exc: BaseException, trace: TracebackType | None) -> Any:
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            sys.__excepthook__(exc_type, exc, trace)
            return

        _logger.critical("Critical unhandled error: %s", exc, exc_info=exc)

        if (app := QApplication.instance()) is not None:
            message = "".join(traceback.format_exception(exc_type, exc, trace))

            try:
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setText(
                    f"An unexpected critical error occurred, please report to developers:\n\n {exc} \n\n"
                    f"App now closes."
                )
                msg.setDetailedText(message)
                msg.setWindowTitle("Critical error")
                msg.exec()
            except Exception as error:  # pylint: disable=broad-exception-caught
                _logger.critical("Could not display the error dialog.", exc_info=error)
            finally:
                app.exit(5)

        sys.__excepthook__(exc_type, exc, trace)

    sys.excepthook = _exc_handler

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"python.app.{__package__}")
    except AttributeError:
        pass

    _application = QApplication(sys.argv)

    _application.setQuitOnLastWindowClosed(False)

    _main_window = MainWindow(persistent_store)
    _main_window.show()

    _logger.debug("Starting application...")
    _application.exec()
    _logger.debug("Application stop.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
