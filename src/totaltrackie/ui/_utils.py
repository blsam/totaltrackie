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
import argparse
import ctypes
import logging
import sys
import time
import traceback
from datetime import date
from logging import StreamHandler
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import Any

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QLayout, QLayoutItem, QMessageBox

from totaltrackie.core import APP_NAME
from totaltrackie.persistent import PersistenceManager

_logger = logging.getLogger(__name__)


def q_date_to_python_date(d: QDate) -> date:
    return date(year=d.year(), month=d.month(), day=d.day())


def python_date_to_q_date(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


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
                f"An unexpected critical error occurred, please report to developers:\n\n {exc} \n\n" f"App now closes."
            )
            msg.setDetailedText(message)
            msg.setWindowTitle("Critical error")
            msg.exec()
        except Exception as error:  # pylint: disable=broad-exception-caught
            _logger.critical("Could not display the error dialog.", exc_info=error)
        finally:
            app.exit(5)

    sys.__excepthook__(exc_type, exc, trace)


def set_gui_except_hook() -> None:
    # pylint: disable-next=comparison-with-callable
    if sys.excepthook != _exc_handler:
        sys.excepthook = _exc_handler


def fix_windows_taskbar_icon() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"python.app.{__package__}")
    except AttributeError:
        pass


def configure_logging(
    log_base_dir: Path, logger_obj: logging.Logger, level: str, log_name: str = "app", stderr: bool = False
) -> None:
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s "
        "[log=%(name)s] "
        "[%(module)s:%(funcName)s:%(lineno)d]"
        "[threadName=%(threadName)s] "
        "- %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%Z",
    )
    formatter.converter = time.localtime

    handler = RotatingFileHandler(
        log_base_dir / f"{log_name}.log",
        backupCount=5,
        maxBytes=1024 * 1024,
    )
    handler.setLevel(level)
    logger_obj.setLevel(level)
    handler.setFormatter(formatter)
    logger_obj.addHandler(handler)

    if stderr:
        stream_handler = StreamHandler()
        stream_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
        logger_obj.addHandler(stream_handler)


def set_layout_enabled_recursive(l: QLayout, enabled: bool) -> None:
    for widget_idx in range(l.count()):
        item: QLayoutItem = l.itemAt(widget_idx)
        if widget := item.widget():
            widget.setEnabled(enabled)
        elif layout := item.layout():
            set_layout_enabled_recursive(layout, enabled)


def start_gui_app(
    args: list[str] | None = None, *, logger: logging.Logger, log_name: str, log_stderr: bool
) -> tuple[QApplication, PersistenceManager]:
    if args is None:
        args = sys.argv

    parser = argparse.ArgumentParser(prog=args[0])
    parser.add_argument("--debug", action="store_true", default=False, help="Enable debug log")
    parser.add_argument(
        "--persistent-store",
        type=Path,
        default=Path.home() / ("." + APP_NAME.lower()) / "storage",
        help="Path to folder where settings will be stored",
    )
    sub_args = parser.parse_args(args[1:])
    level = "DEBUG" if sub_args.debug else "INFO"
    persistent_store = PersistenceManager(sub_args.persistent_store)
    persistent_store.logs_folder.mkdir(exist_ok=True, parents=True)

    configure_logging(persistent_store.logs_folder, logger, level, log_name=log_name, stderr=log_stderr)

    set_gui_except_hook()
    fix_windows_taskbar_icon()

    _application = QApplication(sys.argv)

    return _application, persistent_store
