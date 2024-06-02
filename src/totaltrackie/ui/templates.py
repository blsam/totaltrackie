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

from PySide6 import QtCore
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from totaltrackie.ui._utils import connect_event
from totaltrackie.ui.icons import IconResource


class TemplatesDialog(QDialog):
    def __init__(self, parent: QWidget, current_templates: dict[str, bool]):
        super().__init__(parent)
        self.setWindowTitle("Task templates")

        self._current_templates = current_templates

        layout = QVBoxLayout()
        self.setLayout(layout)

        layout.addWidget(QLabel("List of available templates:"))

        self._templates_list = QListView()
        self._templates_list_model = QStandardItemModel()
        self._templates_list.setModel(self._templates_list_model)

        for index, item in enumerate(current_templates):
            self._insert_new_item_on_model(item, current_templates[item], index)

        # noinspection PyUnresolvedReferences
        self._templates_list.selectionModel().selectionChanged.connect(self._on_item_selection_changed)

        layout.addWidget(self._templates_list)

        insert_layout = QHBoxLayout()
        insert_layout.addWidget(QLabel("Task Name:"))
        self._new_template_name = QLineEdit()
        connect_event(self._new_template_name.textChanged, self._on_new_template_name_entered)
        insert_layout.addWidget(self._new_template_name)
        self._insert_button = QPushButton(IconResource.ADD.get_icon(), "Add template")
        self._insert_button.setEnabled(False)
        insert_layout.addWidget(self._insert_button)
        connect_event(self._insert_button.clicked, self._on_add_new_template_clicked)
        self._delete_button = QPushButton(IconResource.REMOVE.get_icon(), "Delete template")
        connect_event(self._delete_button.clicked, self._on_delete_template_clicked)
        insert_layout.addWidget(self._delete_button)
        self._delete_button.setEnabled(False)

        layout.addLayout(insert_layout)

        self._insert_templates_to_tasks = QPushButton(
            IconResource.TEMPLATES.get_icon(),
            "Create new tasks with selected templates",
        )
        connect_event(self._insert_templates_to_tasks.clicked, self.accept)
        layout.addWidget(self._insert_templates_to_tasks)

    def _on_new_template_name_entered(self):
        self._insert_button.setEnabled(len(self._new_template_name.text()) > 0)

    def _insert_new_item_on_model(self, name: str, checked: bool, index: int = -1):
        q_item = QStandardItem(name)
        q_item.setCheckable(True)
        q_item.setCheckState(QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked)
        if index == -1:
            index = self._templates_list_model.rowCount()

        self._templates_list_model.setItem(index, 0, q_item)

    def _on_add_new_template_clicked(self):
        new_template = self._new_template_name.text()

        for row in range(self._templates_list_model.rowCount()):
            if new_template == self._templates_list_model.item(row).text():
                box = QMessageBox(
                    QMessageBox.Icon.Warning,
                    "Warning",
                    f"Task template '{new_template}' already exists",
                )
                box.setStandardButtons(QMessageBox.StandardButton.Ok)
                box.setDefaultButton(QMessageBox.StandardButton.Ok)
                box.setWindowIcon(self.windowIcon())
                box.exec()
                break
        else:
            self._insert_new_item_on_model(new_template, False)
            self._new_template_name.setText("")

    def _on_item_selection_changed(self):
        self._delete_button.setEnabled(len(self._templates_list.selectionModel().selectedRows()) > 0)

    def _on_delete_template_clicked(self):
        selected_rows = self._templates_list.selectionModel().selectedRows()
        if selected_rows:
            self._templates_list_model.removeRow(selected_rows[0].row())

    def get_selected_tasks_for_inserting(self) -> set[str]:
        result = set()
        for index in range(self._templates_list_model.rowCount()):
            item = self._templates_list_model.item(index)
            if item.isCheckable() and item.checkState() == QtCore.Qt.CheckState.Checked:
                result.add(item.text())
        return result

    def get_entered_templates(self) -> dict[str, bool]:
        items = [self._templates_list_model.item(index) for index in range(self._templates_list_model.rowCount())]
        return {item.text(): item.checkState() is QtCore.Qt.CheckState.Checked for item in items}
