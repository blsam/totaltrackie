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

from typing import Union

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from totaltrackie.persistent import Settings
from totaltrackie.ui._utils import connect_event
from totaltrackie.ui.icons import IconResource


class SettingsWindow(QDialog):
    def __init__(self, parent: QWidget, settings_base: Settings):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.work_time_hours = QSpinBox()
        self.work_time_hours.setMaximum(12)
        self.work_time_hours.setMinimum(0)
        self.work_time_hours.setValue(settings_base.work_time_hours)

        self.work_time_minutes = QSpinBox()
        self.work_time_minutes.setMaximum(59)
        self.work_time_minutes.setMinimum(0)
        self.work_time_minutes.setValue(settings_base.work_time_minutes)

        worktime_layout = QHBoxLayout(self)

        worktime_layout.addWidget(QLabel("Work time:"))
        worktime_layout.addWidget(self.work_time_hours)
        worktime_layout.addWidget(QLabel("hours"))
        worktime_layout.addWidget(self.work_time_minutes)
        worktime_layout.addWidget(QLabel("minutes"))

        layout.addLayout(worktime_layout)

        confirm_layout = QHBoxLayout(self)
        confirm_button = QPushButton(IconResource.OK.get_icon(), "Confirm")
        connect_event(confirm_button.clicked, self.accept)
        cancel_button = QPushButton(IconResource.CANCEL.get_icon(), "Cancel")
        connect_event(cancel_button.clicked, self.reject)
        confirm_layout.addWidget(confirm_button)
        confirm_layout.addWidget(cancel_button)

        layout.addLayout(confirm_layout)

        self._settings_base = settings_base

    def get_result(self) -> Union[Settings, None]:
        if self.result() == QDialog.DialogCode.Accepted:
            return Settings(
                work_time_hours=self.work_time_hours.value(),
                work_time_minutes=self.work_time_minutes.value(),
                templates=self._settings_base.templates,
            )
        return None
