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

from datetime import date
from importlib.metadata import entry_points
from pathlib import Path
from typing import Callable, List

from PySide6.QtWidgets import QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from totaltrackie.core import APP_NAME, Task
from totaltrackie.ui._utils import connect_event
from totaltrackie.ui.icons import IconResource


def _build_generator_list() -> dict[str, Callable[[QWidget, date, list[Task]], None]]:
    generators = {}
    lowered_app_name = APP_NAME.lower()
    plugins = entry_points(group=f"{lowered_app_name}.plugins")
    for entrypoint in plugins:
        plugin_generator = entrypoint.load()
        if not callable(plugin_generator):
            continue
        generators[entrypoint.name] = plugin_generator

    generators["Default Generator"] = generic_report_generator
    return generators


class ReportGenerateDialog(QDialog):
    def __init__(self, parent: QWidget, current_date: date, tasks: List[Task]):
        super().__init__(parent)
        self.setWindowTitle("Report generation")
        layout = QVBoxLayout()
        self.setLayout(layout)
        confirm_button = QPushButton(IconResource.OK.get_icon(), "Confirm")
        connect_event(confirm_button.clicked, self.accept)
        cancel_button = QPushButton(IconResource.CANCEL.get_icon(), "Cancel")
        connect_event(cancel_button.clicked, self.reject)

        generator_select_layout = QHBoxLayout(self)
        self._generator_selector = QComboBox()

        self._generator_map = _build_generator_list()
        self._generator_selector.addItems(tuple(self._generator_map.keys()))
        generator_select_layout.addWidget(QLabel("Report Generator: "))
        generator_select_layout.addWidget(self._generator_selector)

        layout.addLayout(generator_select_layout)

        confirm_layout = QHBoxLayout(self)
        confirm_layout.addWidget(confirm_button)
        confirm_layout.addWidget(cancel_button)

        layout.addLayout(confirm_layout)
        self.tasks = tasks
        self.current_date = current_date

    def accept(self):
        super().accept()
        self._generator_map[self._generator_selector.currentText()](self.parent(), self.current_date, self.tasks)


def generic_report_generator(parent: QWidget, current_date: date, tasks: list[Task]):
    strings = []

    for index, task in enumerate(tasks, start=1):
        task_duration_percentile = task.total_seconds() / 60 / 60
        comments = "\n\t".join(task.comments.splitlines())
        base_string = f"{index}. {task.name} - {task_duration_percentile:.2f}h"
        if comments:
            strings.append(f"{base_string} - {comments}")
        else:
            strings.append(base_string)
        strings.append("\n")

    default_name = current_date.strftime("%Y-%m-%d")
    path, _ = QFileDialog.getSaveFileName(parent, filter="*.txt", dir=f"{default_name}.txt")
    if path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wt", encoding="utf-8") as file_handle:
            for line in strings:
                file_handle.write(line)
