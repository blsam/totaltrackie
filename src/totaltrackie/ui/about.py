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

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from totaltrackie.core import APP_NAME
from totaltrackie.ui._utils import connect_event
from totaltrackie.ui.icons import IconResource


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(self.minimumSize())
        self.setWindowTitle("About")
        layout = QVBoxLayout()
        self.setLayout(layout)
        confirm_button = QPushButton(IconResource.OK.get_icon(), "OK")
        connect_event(confirm_button.clicked, self.accept)

        main_layout = QVBoxLayout(self)
        about_label = QLabel(f"{APP_NAME} is minimalist daily time tracker app under MIT license")
        about_label.setOpenExternalLinks(True)
        main_layout.addWidget(about_label)

        main_layout.addWidget(QLabel("Made with <3, PySide6 and Qt framework:"))
        py_side6_label = QLabel('- <a href="https://wiki.qt.io/Qt_for_Python">PySide6</a> package')
        qt_framework_label = QLabel('- <a href="https://www.qt.io/">Qt Framework</a>')
        py_side6_label.setOpenExternalLinks(True)
        qt_framework_label.setOpenExternalLinks(True)

        main_layout.addWidget(py_side6_label)
        main_layout.addWidget(qt_framework_label)

        layout.addLayout(main_layout)

        confirm_layout = QHBoxLayout(self)
        confirm_layout.addWidget(confirm_button)

        layout.addLayout(confirm_layout)
