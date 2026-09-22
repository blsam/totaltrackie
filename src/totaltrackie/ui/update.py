#  Copyright 2026 blsam
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
import importlib.metadata
import logging
import os
import sys
from importlib.metadata import PackageNotFoundError

from PySide6.QtCore import QModelIndex, QProcess, QSize, Slot
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from totaltrackie.core import APP_NAME
from totaltrackie.persistent import PersistenceManager
from totaltrackie.ui._utils import set_layout_enabled_recursive
from totaltrackie.update_helper import (
    PackageReference,
    SubProcessDialog,
    UpdateData,
    UpdateWorkspace,
    get_interpreter_path_for_venv,
    get_update_data,
    is_valid_python_package_name,
    venv_unique_id,
)

_logger = logging.getLogger(__name__)


class InternalUpdateError(Exception):
    pass


class AddPluginDialog(QDialog):
    def __init__(self, parent: QWidget, restrict_names: set[str]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add plugin")
        self.setModal(True)
        self.resize(QSize(2**10, 0))

        self._update_data: UpdateData | None = get_update_data()

        layout = QVBoxLayout()
        self.setLayout(layout)

        self._combo_box = QComboBox()
        if self._update_data is not None:
            self._combo_box.addItems(list(self._update_data.known_plugins.keys()))
        self._combo_box.addItem("Custom plugin...")
        self._combo_box.currentIndexChanged.connect(self._on_combo_index_changed)

        layout.addWidget(self._combo_box)

        self._custom_plugin_layout = QVBoxLayout()
        custom_plugin_name_layout = QHBoxLayout()
        custom_plugin_name_layout.addWidget(QLabel("Name:"))
        self._custom_plugin_name_edit = QLineEdit()
        self._custom_plugin_name_edit.textChanged.connect(self._on_custom_plugin_name_changed)
        custom_plugin_name_layout.addWidget(self._custom_plugin_name_edit)
        self._custom_plugin_updatable = QCheckBox("Updatable")
        self._custom_plugin_updatable.setToolTip(
            "Check if plugin ref is an URL that support update protocol (like GitHub)"
        )
        custom_plugin_name_layout.addWidget(self._custom_plugin_updatable)
        self._custom_plugin_layout.addLayout(custom_plugin_name_layout)

        custom_plugin_reference_layout = QHBoxLayout()
        custom_plugin_reference_layout.addWidget(QLabel("Reference:"))
        self._custom_plugin_reference_edit = QLineEdit()
        self._custom_plugin_reference_edit.textChanged.connect(self._on_custom_plugin_reference_changed)
        custom_plugin_reference_layout.addWidget(self._custom_plugin_reference_edit)
        self._custom_plugin_layout.addLayout(custom_plugin_reference_layout)

        layout.addLayout(self._custom_plugin_layout)

        self._error_label = QLabel("")
        layout.addWidget(self._error_label)
        self._error_label.setStyleSheet("color: red;")
        self._error_label.hide()

        self._confirm_button = QPushButton("Add plugin")
        layout.addWidget(self._confirm_button)
        self._confirm_button.setEnabled(False)
        self._confirm_button.clicked.connect(self._on_confirm_clicked)

        self._restrict_names = restrict_names

        self._control_state_of_custom_plugin_controls()

    @Slot()
    def _on_custom_plugin_name_changed(self) -> None:
        self._verify_data()

    @Slot()
    def _on_custom_plugin_reference_changed(self) -> None:
        self._verify_data()

    @Slot()
    def _on_confirm_clicked(self) -> None:
        self.accept()

    def _verify_data(self) -> None:
        pkg_name = self._custom_plugin_name_edit.text()
        ref = self._custom_plugin_reference_edit.text()
        error_reason = ""
        if not is_valid_python_package_name(pkg_name):
            error_reason = "The provided plugin name is not a valid Python package name!"
        if pkg_name in self._restrict_names:
            error_reason = f"The package name '{pkg_name}' is already used by other installed plugin!"
        if not ref:
            error_reason = "Reference is empty"

        if error_reason:
            self._error_label.setText(error_reason)
            self._error_label.show()
            self._confirm_button.setEnabled(False)
        else:
            self._error_label.hide()
            self._confirm_button.setEnabled(True)

    @Slot()
    def _on_combo_index_changed(self) -> None:
        self._control_state_of_custom_plugin_controls()

    def _control_state_of_custom_plugin_controls(self) -> None:
        enable = self._combo_box.currentIndex() == (self._combo_box.count() - 1)
        set_layout_enabled_recursive(self._custom_plugin_layout, enable)
        if not enable:
            if self._update_data is None:
                raise InternalUpdateError("No update data available")
            ref = self._update_data.known_plugins[self._combo_box.currentText()]
            self._custom_plugin_name_edit.setText(self._combo_box.currentText())
            self._custom_plugin_reference_edit.setText(ref.ref)
            self._custom_plugin_updatable.setChecked(ref.updatable)
        else:
            self._custom_plugin_reference_edit.setText("")
            self._custom_plugin_name_edit.setText("")
            self._custom_plugin_updatable.setChecked(False)

    def get_pkg(self) -> tuple[str, PackageReference]:
        if not self.accepted:
            raise ValueError

        name = self._custom_plugin_name_edit.text()
        ref = self._custom_plugin_reference_edit.text()
        updatable = self._custom_plugin_updatable.isChecked()
        return name, PackageReference(ref=ref, updatable=updatable)


class UpdateDialog(QDialog):
    # pylint: disable-next=too-many-statements
    def __init__(self, parent: QWidget, persistence_manager: PersistenceManager):
        super().__init__(parent)
        self.setWindowTitle("Updates & Plugins Manager")
        self.setModal(True)
        self.resize(QSize(2**9, 2**9))

        layout = QVBoxLayout()
        self.setLayout(layout)

        self._persistence_manager = persistence_manager
        self._current_venv_storage = venv_unique_id(persistence_manager.store_dir)

        self._table_view = QTableView()
        layout.addWidget(self._table_view)

        self._packages_table_model = QStandardItemModel(0, 3, self)
        self._table_view.setModel(self._packages_table_model)

        self._packages_table_model.setHorizontalHeaderLabels(["Package", "Installed", "Update"])

        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table_view.setShowGrid(True)
        self._table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table_view.selectionModel().selectionChanged.connect(self._on_selection_index_changed)
        header = self._table_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)

        self._workspace = UpdateWorkspace(self._current_venv_storage)

        for pkg in self._workspace.update_env.list():
            pkg_col = QStandardItem(pkg)
            pkg_col.setEditable(False)

            try:
                version = importlib.metadata.version(pkg)
            except PackageNotFoundError:
                version = "[not installed]"

            version_col = QStandardItem(version)
            version_col.setEditable(False)

            update_version_col = QStandardItem("")
            update_version_col.setEditable(False)

            self._packages_table_model.appendRow([pkg_col, version_col, update_version_col])

        control_layout = QHBoxLayout()
        self._add_plugin_button = QPushButton("Add plugin...")
        self._add_plugin_button.clicked.connect(self._on_add_plugin_clicked)
        control_layout.addWidget(self._add_plugin_button)
        self._remove_plugin_button = QPushButton("Remove plugin...")
        self._remove_plugin_button.clicked.connect(self._on_remove_plugin_clicked)
        self._remove_plugin_button.setEnabled(False)
        control_layout.addWidget(self._remove_plugin_button)
        layout.addLayout(control_layout)

        self._check_updates_button = QPushButton("Check updates...")
        self._check_updates_button.clicked.connect(self._on_check_updates_button_clicked)
        layout.addWidget(self._check_updates_button)

        self._update_and_restart_button = QPushButton("Apply changes")
        self._update_and_restart_button.clicked.connect(self._on_apply_updates_button_clicked)
        layout.addWidget(self._update_and_restart_button)
        self._update_and_restart_button.setEnabled(False)

        self._on_selection_index_changed()
        self._update_versions_of_pkgs_in_table()

    @Slot()
    def _on_apply_updates_button_clicked(self) -> None:
        self._workspace.update_env.save()
        d = SubProcessDialog(
            self,
            "Perform update",
            [sys.executable, "-us", "-m", f"{APP_NAME}.update_helper", "side-update", self._workspace.root],
        )
        if d.exec() != QDialog.DialogCode.Accepted:
            return

        if (app := QApplication.instance()) is None:
            # should not happen really
            raise InternalUpdateError("Unable to find current app instance!")

        detached_interpreter = str(get_interpreter_path_for_venv(self._workspace.side_venv))
        detached_update_args = [
            "-us",
            "-m",
            f"{APP_NAME}.update_helper",
            "main-update",
            "--",
            str(self._workspace.root),
            str(os.getpid()),
            sys.executable,
            *(str(item) for item in sys.argv),
        ]
        _logger.info("Detached process start with: %s %s", detached_interpreter, " ".join(detached_update_args))

        started, pid = QProcess.startDetached(
            detached_interpreter,
            detached_update_args,
        )
        if not started:
            raise InternalUpdateError("Sub process is not started!")
        _logger.info("Detached process started as PID: %s", pid)
        app.quit()

    @Slot()
    def _on_check_updates_button_clicked(self) -> None:
        self._workspace.update_env.save()
        d = SubProcessDialog(
            self,
            "Verify updates",
            [sys.executable, "-us", "-m", f"{APP_NAME}.update_helper", "check-updates", self._workspace.root],
        )
        if d.exec() != QDialog.DialogCode.Accepted:
            return
        self._update_versions_of_pkgs_in_table()

    def _update_versions_of_pkgs_in_table(self) -> None:
        allow_for_update = False
        packages_missed_in_cache = False
        for row in range(self._packages_table_model.rowCount()):
            pkg_name_index = self._packages_table_model.index(row, 0)
            pkg_name = self._packages_table_model.data(pkg_name_index)

            try:
                install_version = importlib.metadata.version(pkg_name)
            except PackageNotFoundError:
                install_version = "[not installed]"

            installed_version_index = self._packages_table_model.index(row, 1)
            self._packages_table_model.setData(installed_version_index, install_version)

            last_version = self._workspace.whl_cache.get_last_version_for(pkg_name)
            if last_version is None:
                packages_missed_in_cache = True
                last_version = "[N/A]"

            update_version_index = self._packages_table_model.index(row, 2)
            self._packages_table_model.setData(update_version_index, last_version)

            if install_version != last_version:
                allow_for_update = True

        _logger.debug("There is a difference in installed versions: %s", allow_for_update)
        if self._workspace.has_env_changes():
            _logger.debug("The update workspace has env changes!")
            allow_for_update = True

        if packages_missed_in_cache:
            allow_for_update = False

        self._update_and_restart_button.setEnabled(allow_for_update)

    @Slot()
    def _on_add_plugin_clicked(self) -> None:
        restrict_names: set[str] = set()
        for row in range(self._packages_table_model.rowCount()):
            index = self._packages_table_model.index(row, 0)
            restrict_names.add(self._packages_table_model.data(index))
        dialog = AddPluginDialog(self, restrict_names)
        res = dialog.exec()
        if res != QDialog.DialogCode.Accepted:
            return
        name, ref = dialog.get_pkg()
        self._workspace.update_env.add(name, ref)
        pkg_col = QStandardItem(name)
        pkg_col.setEditable(False)

        self._packages_table_model.appendRow([pkg_col, QStandardItem("[N/A]"), QStandardItem("[N/A]")])
        self._update_versions_of_pkgs_in_table()

    @Slot()
    def _on_remove_plugin_clicked(self) -> None:
        selected_rows: list[QModelIndex] = self._table_view.selectedIndexes()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        index = self._packages_table_model.index(row, 0)
        pkg_name = self._packages_table_model.data(index)
        self._packages_table_model.removeRow(row)
        self._workspace.update_env.remove(pkg_name)
        self._update_versions_of_pkgs_in_table()

    @Slot()
    def _on_selection_index_changed(self) -> None:
        selected_rows: list[QModelIndex] = self._table_view.selectedIndexes()
        if not selected_rows:
            self._remove_plugin_button.setEnabled(False)
            return
        row = selected_rows[0].row()
        self._remove_plugin_button.setEnabled(
            self._packages_table_model.data(self._packages_table_model.index(row, 0)) != APP_NAME
        )
