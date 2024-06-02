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

from PySide6.QtWidgets import QDialog, QGridLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QWidget

from totaltrackie.core import Task
from totaltrackie.ui._utils import connect_event
from totaltrackie.ui.icons import IconResource


class EditTaskDialogWindow(QDialog):
    def __init__(self, parent: QWidget, task_base: Task | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit/Add a task")
        layout = QGridLayout()
        self.setLayout(layout)
        confirm_button = QPushButton(IconResource.OK.get_icon(), "Confirm")
        connect_event(confirm_button.clicked, self.accept)
        cancel_button = QPushButton(IconResource.CANCEL.get_icon(), "Cancel")
        connect_event(cancel_button.clicked, self.reject)

        self.task_name_edit = QLineEdit()
        self.task_name_edit.setPlaceholderText("Example Task Name")
        self.task_comments_edit = QTextEdit()

        layout.addWidget(QLabel("Task name: "), 0, 0, 1, 1)
        layout.addWidget(self.task_name_edit, 0, 1, 1, 1)
        layout.addWidget(QLabel("Comments: "), 1, 0, 1, 2)
        layout.addWidget(self.task_comments_edit, 2, 0, 1, 2)
        layout.addWidget(confirm_button, 3, 0, 1, 1)
        layout.addWidget(cancel_button, 3, 1, 1, 1)

        self._task_base = task_base
        if self._task_base is not None:
            self.task_name_edit.setText(self._task_base.name)
            self.task_comments_edit.setPlainText(self._task_base.comments)

    def get_result_as_task(self) -> Task | None:
        if self.result() == QDialog.DialogCode.Accepted:
            return Task(
                self.task_name_edit.text().strip(),
                self.task_comments_edit.toPlainText(),
                self._task_base.timespans if self._task_base else [],
            )
        return None
