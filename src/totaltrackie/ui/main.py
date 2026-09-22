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
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, QModelIndex, QTimer, QUrl, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from totaltrackie.core import APP_NAME, Task, TasksManager
from totaltrackie.persistent import PersistenceManager
from totaltrackie.ui._utils import q_date_to_python_date
from totaltrackie.ui.about import AboutDialog
from totaltrackie.ui.icons import IconResource
from totaltrackie.ui.report import ReportDialog
from totaltrackie.ui.settings import SettingsWindow
from totaltrackie.ui.task import EditTaskDialogWindow
from totaltrackie.ui.templates import TemplatesDialog
from totaltrackie.ui.transfer import TransferTimeDialog
from totaltrackie.ui.update import UpdateDialog
from totaltrackie.update_helper import is_update_functionality_enabled

logger = logging.getLogger(__name__)


@dataclass
class _MenuActions:
    start: QAction
    relax: QAction
    report: QAction
    templates: QAction
    settings: QAction


class MainWindow(QMainWindow):
    # pylint: disable-next=too-many-statements
    def __init__(self, store: PersistenceManager):
        super().__init__()
        self.setWindowIcon(IconResource.APP.get_icon())
        self._tray_icon = QSystemTrayIcon(self.windowIcon())
        self._tray_icon.activated.connect(self._on_tray_icon_clicked)

        self._menu_actions = self._build_action_menu()

        self._persistent_store = store
        self._task_manager: TasksManager = TasksManager()

        self._settings = store.load_settings()

        tray_menu = QMenu()
        quit_action = QAction("Exit", self)
        quit_action.triggered.connect(self._on_application_exit)

        tray_menu.addAction(self._menu_actions.relax)
        tray_menu.addAction(self._menu_actions.settings)
        tray_menu.addAction(quit_action)
        self._tray_icon.setContextMenu(tray_menu)

        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(500, 400)
        self._relax_button = QPushButton(IconResource.RELAX.get_icon(), "Relax")
        relax_font = QFont()
        relax_font.setBold(True)
        relax_font.setPointSize(14)
        self._relax_button.setFont(relax_font)
        self._relax_button.clicked.connect(self._on_relax_button_clicked)

        self._add_button = QPushButton(IconResource.ADD.get_icon(), "Add Task")
        self._add_button.clicked.connect(self._on_task_add_button_clicked)
        self._remove_button = QPushButton(IconResource.REMOVE.get_icon(), "Remove Task")
        self._remove_button.clicked.connect(self._on_task_remove_button_clicked)

        self._edit_button = QPushButton(IconResource.EDIT.get_icon(), "Edit Task")
        self._edit_button.clicked.connect(self._on_task_edit_button_clicked)

        self._tasks_model = TaskStorageDataModel()
        self._tasks_view = QTableView()
        self._tasks_view.horizontalHeader().setStretchLastSection(True)
        self._tasks_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tasks_view.setShowGrid(True)
        self._tasks_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._tasks_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tasks_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tasks_view.doubleClicked.connect(self._on_start_button_clicked)
        self._tasks_view.setModel(self._tasks_model)

        self._tasks_view.selectionModel().selectionChanged.connect(self._on_task_selection_changed)

        time_left_label_prefix = QLabel("Work Time left:")
        self._time_left_label = QLabel("N/A")
        time_font = QFont()
        time_font.setBold(True)
        time_font.setPointSize(18)
        self._time_left_label.setFont(time_font)
        self._time_left_label_prefix = QLabel("Active task time:")
        self._time_task_label = QLabel("N/A")
        self._time_task_label.setFont(time_font)

        self._update_timer = QTimer(self)
        self._update_timer.setInterval(1 * 1000)
        self._update_timer.setSingleShot(False)

        self._update_timer.timeout.connect(self._on_update_timer_tick)
        self._update_timer.start()

        layout = QVBoxLayout()

        time_layout = QHBoxLayout()
        time_layout.addWidget(time_left_label_prefix)
        time_layout.addWidget(self._time_left_label)
        time_layout.addWidget(self._time_left_label_prefix)
        time_layout.addWidget(self._time_task_label)

        layout.addLayout(time_layout)

        task_control_layout = QHBoxLayout()
        task_control_layout.addWidget(self._relax_button)
        layout.addLayout(task_control_layout)

        layout.addWidget(self._tasks_view)

        footer_layout = QHBoxLayout()
        footer_layout.addWidget(self._add_button)
        footer_layout.addWidget(self._edit_button)
        footer_layout.addWidget(self._remove_button)

        self._day_selector = QDateEdit()
        self._day_selector.setCalendarPopup(True)
        date_now = date.today()
        self._day_selector.dateChanged.connect(self._on_current_date_changed)
        self._day_selector.setDate(QDate(date_now.year, date_now.month, date_now.day))
        footer_layout.addWidget(self._day_selector)

        layout.addLayout(footer_layout)

        central_widget = QWidget()
        central_widget.setLayout(layout)

        self.setCentralWidget(central_widget)

        self._update_buttons_state()
        self._on_update_timer_tick()
        self._on_task_selection_changed()

    def _build_action_menu(self) -> _MenuActions:
        task_menu = self.menuBar().addMenu("&Tasks")

        stop_action = QAction(IconResource.RELAX.get_icon(), "Relax", self)
        stop_action.triggered.connect(self._on_relax_button_clicked)

        start_action = QAction(IconResource.START.get_icon(), "Start", self)
        start_action.triggered.connect(self._on_start_button_clicked)

        report_action = QAction(IconResource.REPORT.get_icon(), "Build &report...", self)
        report_action.triggered.connect(self._on_report_button_click)

        transfer_time_action = QAction(IconResource.START.get_icon(), "&Transfer time...", self)
        transfer_time_action.triggered.connect(self._on_task_transfer_time_menu_clicked)

        task_menu.addActions((start_action, stop_action))
        task_menu.addSeparator()
        task_menu.addAction(transfer_time_action)
        task_menu.addSeparator()
        task_menu.addAction(report_action)

        settings_action = QAction(IconResource.SETTINGS.get_icon(), "Settings", self)
        settings_action.triggered.connect(self._on_settings_button_clicked)

        template_action = QAction(IconResource.TEMPLATES.get_icon(), "Templates...", self)
        template_action.triggered.connect(self._on_templates_button_click)

        preferences_menu = self.menuBar().addMenu("&Preferences")
        preferences_menu.addAction(settings_action)
        preferences_menu.addAction(template_action)

        help_menu = self.menuBar().addMenu("&About")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._on_about_clicked)

        open_storage_action = QAction("Open persistent &storage location...", self)
        open_storage_action.triggered.connect(self._on_open_storage_clicked)

        update_action = QAction("Updates and plugins manager...", self)
        update_action.triggered.connect(self._on_update_clicked)
        update_action.setEnabled(is_update_functionality_enabled())

        help_menu.addAction(open_storage_action)
        help_menu.addAction(update_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)

        return _MenuActions(
            start=start_action,
            relax=stop_action,
            report=report_action,
            templates=template_action,
            settings=settings_action,
        )

    @Slot()
    def _on_update_clicked(self) -> None:
        dialog = UpdateDialog(self, self._persistent_store)
        dialog.exec()

    @Slot()
    def _on_open_storage_clicked(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._persistent_store.store_dir)))

    @Slot()
    def _on_about_clicked(self) -> None:
        about_dialog = AboutDialog(self)
        about_dialog.exec()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_tray_icon_clicked(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            logger.debug("Show application main window as tray icon double-clicked")
            self.show()

    @Slot()
    def _on_templates_button_click(self) -> None:
        templates_dialog = TemplatesDialog(self, self._settings.templates)
        code = templates_dialog.exec()

        templates_to_insert = templates_dialog.get_selected_tasks_for_inserting()
        new_templates = templates_dialog.get_entered_templates()

        if code == QDialog.DialogCode.Accepted:
            active_tasks = set(item.name for item in self._task_manager.get_tasks())

            for task in templates_to_insert:
                if task in active_tasks:
                    continue

                self._task_manager.add(Task(task, "", []))

            self._tasks_model.refresh(self._task_manager, force=True)

        if self._settings.templates != new_templates:
            self._settings.templates.clear()
            self._settings.templates.update(new_templates)
            self._persistent_store.save_settings(self._settings)

    @Slot()
    def _on_application_exit(self) -> None:
        active_task = self._task_manager.active()
        should_exit = True
        if active_task is not None:
            box = QMessageBox(
                QMessageBox.Icon.Warning,
                "Warning",
                f'Are you sure you want to exit while task "{active_task.name}" is running?',
            )
            box.setStandardButtons(QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(QMessageBox.StandardButton.Cancel)
            box.setWindowIcon(self.windowIcon())
            box.exec()

            if box.result() == QMessageBox.StandardButton.Cancel:
                should_exit = False

        if should_exit and (app := QApplication.instance()) is not None:
            app.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        logger.debug("Hiding main window...")
        self.hide()

        logger.debug("Stopping update timer...")
        self._update_timer.stop()

    def show(self) -> None:
        self._tray_icon.show()
        super().show()

        if self._task_manager.active() is not None:
            logger.debug("Starting update timer as there active task found")
            self._update_timer.start()

    @property
    def selected_task(self) -> int:
        selection: list[QModelIndex] = self._tasks_view.selectedIndexes()
        if not selection:
            return -1
        return selection[0].row()

    @property
    def selected_date(self) -> date:
        gui_date = self._day_selector.date()
        return q_date_to_python_date(gui_date)

    def _control_relax_action(self, status: bool) -> None:
        self._relax_button.setEnabled(status)
        self._menu_actions.relax.setEnabled(status)

    @Slot()
    def _on_current_date_changed(self) -> None:
        self._persistent_store.load_tasks(self.selected_date, self._task_manager)
        self._tasks_model.refresh(self._task_manager, force=True)

        self._update_buttons_state()
        self._on_update_timer_tick()
        if self._task_manager.active() is not None:
            logger.debug("Activating update timer after changing date...")
            self._update_timer.start()

    @Slot()
    def _on_settings_button_clicked(self) -> None:
        settings_window = SettingsWindow(self, self._settings)
        settings_window.exec()

        result = settings_window.get_result()
        if result is not None:
            logger.debug("Settings changed into %s", result)
            self._settings = result
            self._on_update_timer_tick()
            self._persistent_store.save_settings(self._settings)

    @Slot()
    def _on_update_timer_tick(self) -> None:
        active_task = self._task_manager.active()
        left_time: int = int(
            self._settings.work_time_as_timedelta.total_seconds() - self._task_manager.get_tasks_cumulative_time()
        )

        if left_time < 0:
            delta = timedelta(seconds=-left_time)
            self._time_left_label.setText(f"Overtime {delta}")
        else:
            delta = timedelta(seconds=left_time)
            self._time_left_label.setText(str(delta))

        if active_task is not None:
            self._time_left_label_prefix.setText("Active task time:")
            active_task_time = str(timedelta(seconds=int(active_task.total_seconds())))
            self._time_task_label.setText(active_task_time)
        else:
            self._time_left_label_prefix.setText("End of work at:")
            if self.selected_date == date.today() and left_time > 0:
                active_task_time = (datetime.now() + timedelta(seconds=left_time)).strftime("%H:%M:%S")
                self._time_task_label.setText(active_task_time)
            else:
                self._time_task_label.setText("N/A")

    def _update_buttons_state(self) -> None:
        if self.selected_date != date.today():
            self._edit_button.setEnabled(False)
            self._remove_button.setEnabled(False)
            self._menu_actions.start.setEnabled(False)
            self._control_relax_action(False)
            self._add_button.setEnabled(False)
            self._menu_actions.templates.setEnabled(False)
        else:
            self._menu_actions.templates.setEnabled(True)
            self._add_button.setEnabled(True)
            self._edit_button.setEnabled(True)
            self._remove_button.setEnabled(True)
            if self.selected_task != -1:
                task = self._task_manager.get(self.selected_task)
                enable = False if task is None else (not task.is_started())
                self._menu_actions.start.setEnabled(enable)
            else:
                self._menu_actions.start.setEnabled(False)
                self._edit_button.setEnabled(False)
                self._remove_button.setEnabled(False)
            self._control_relax_action(self._task_manager.active() is not None)

    @Slot()
    def _on_start_button_clicked(self) -> None:
        # This is also called when double-clicked, so, here additional check
        if not self._menu_actions.start.isEnabled():
            return

        logger.debug("Clicked starting button, starting selected task %s", self.selected_task)
        self._task_manager.start(self.selected_task)
        self._update_buttons_state()

        if not self._update_timer.isActive():
            self._update_timer.start()

        self._persistent_store.save_tasks(self.selected_date, self._task_manager)
        self._on_update_timer_tick()

        self._tasks_model.invalidate()
        self._tasks_model.refresh(self._task_manager)

    @Slot()
    def _on_relax_button_clicked(self) -> None:
        logger.debug("Starting relax...")
        index = self._task_manager.active_index()
        if index is None:
            return

        self._task_manager.stop_active()

        self._tasks_model.invalidate(index)
        self._tasks_model.refresh(self._task_manager)

        self._update_buttons_state()
        self._on_update_timer_tick()

        logger.debug("Scheduling save...")
        self._persistent_store.save_tasks(self.selected_date, self._task_manager)

    @Slot()
    def _on_task_remove_button_clicked(self) -> None:
        task = self._task_manager.get(self.selected_task)
        if task is None:
            return

        box = QMessageBox(
            QMessageBox.Icon.Question,
            "Deletion confirmation",
            f"Are you sure you want to delete '{task.name}'?",
        )
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setWindowIcon(self.windowIcon())
        result = box.exec()

        if result == QMessageBox.StandardButton.Yes:
            logger.debug("Removing selected task %s", self.selected_task)
            self._task_manager.remove(self.selected_task)
            self._on_update_timer_tick()

            logger.debug("Scheduling save...")
            self._persistent_store.save_tasks(self.selected_date, self._task_manager)

            self._tasks_model.refresh(self._task_manager, force=True)

    @Slot()
    def _on_task_add_button_clicked(self) -> None:
        add_dialog = EditTaskDialogWindow(self)
        dialog_result = None

        while dialog_result is None:
            dialog_result = add_dialog.exec()
            task = add_dialog.get_result_as_task()
            if task is not None:
                logger.debug("Trying to add a new task %s", task.name)
                if not task.name:
                    box = QMessageBox(
                        QMessageBox.Icon.Warning,
                        "Warning",
                        "Cannot create task with empty name!",
                    )
                    box.setStandardButtons(QMessageBox.StandardButton.Ok)
                    box.setWindowIcon(self.windowIcon())
                    box.exec()
                    dialog_result = None
                elif self._task_manager.has(task.name):
                    box = QMessageBox(
                        QMessageBox.Icon.Warning,
                        "Warning",
                        f"There are already a task with name '{task.name}'",
                    )
                    box.setStandardButtons(QMessageBox.StandardButton.Ok)
                    box.setWindowIcon(self.windowIcon())
                    box.exec()
                    dialog_result = None
                else:
                    self._task_manager.add(task)
                    logger.debug("Scheduling save...")
                    self._persistent_store.save_tasks(self.selected_date, self._task_manager)
                    self._tasks_model.refresh(self._task_manager, force=True)

    @Slot()
    def _on_task_transfer_time_menu_clicked(self) -> None:
        has_valid_tasks = any(item.timespans and item.total_seconds() >= 60 for item in self._task_manager.get_tasks())

        if not self._task_manager.has_tasks() or not has_valid_tasks:
            box = QMessageBox(QMessageBox.Icon.Warning, "Warning", "No tasks to transfer time for!")
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.setWindowIcon(self.windowIcon())
            box.exec()
            return

        dialog = TransferTimeDialog(self, self._task_manager)
        dialog.exec()
        self._tasks_model.invalidate()
        self._tasks_model.refresh(self._task_manager)
        self._persistent_store.save_tasks(self.selected_date, self._task_manager)

    @Slot()
    def _on_task_edit_button_clicked(self) -> None:
        task = self._task_manager.get(self.selected_task)
        if task is None:
            return

        dialog = EditTaskDialogWindow(self, task)
        dialog.exec()
        new_task = dialog.get_result_as_task()
        if new_task is not None:
            logger.debug("Task edited: %s -> %s", task.name, new_task.name)
            self._task_manager.edit(self.selected_task, new_task)
            self._persistent_store.save_tasks(self.selected_date, self._task_manager)

            self._tasks_model.invalidate(self.selected_task)
            self._tasks_model.refresh(self._task_manager)

    @Slot()
    def _on_task_selection_changed(self) -> None:
        self._update_buttons_state()
        self._on_update_timer_tick()

    @Slot()
    def _on_report_button_click(self) -> None:
        if self._task_manager.active() is not None:
            box = QMessageBox(QMessageBox.Icon.Warning, "Warning", "Active tasks must be completed")
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.setWindowIcon(self.windowIcon())
            box.exec()
            return

        dialog = ReportDialog(self, self.selected_date, persistent_manager=self._persistent_store)
        dialog.exec()


class TaskStorageDataModel(QStandardItemModel):
    def __init__(self) -> None:
        super().__init__(0, 3)
        self.setHorizontalHeaderLabels(["Task", "Duration", "Comments"])

        self._invalidated_rows: list[int] = []
        self._invalidate_all: bool = False

    def invalidate(self, row: int = -1) -> None:
        if row <= -1:
            self._invalidate_all = True
        else:
            self._invalidated_rows.append(row)

    def refresh(self, manager: TasksManager, force: bool = False) -> None:
        if force:
            self._invalidate_all = True

        if self._invalidate_all:
            self.removeRows(0, self.rowCount())
            for index, task in enumerate(manager.get_tasks()):
                self._format_task_entry(index, task)
        else:
            for row in self._invalidated_rows:
                row_task = manager.get(row)
                if row_task is None:
                    continue
                self._format_task_entry(row, row_task)
        self._invalidated_rows.clear()
        self._invalidate_all = False

    def _format_task_entry(self, row: int, task: Task) -> None:
        self.setItem(row, 0, QStandardItem(task.name))
        last_comment_line: str = "" if not task.comments else task.comments.splitlines()[-1]
        self.setItem(row, 2, QStandardItem(last_comment_line))
        if not task.is_started():
            duration_item = QStandardItem(str(timedelta(seconds=int(task.total_seconds()))))
            self.setItem(row, 1, duration_item)
            font = QFont()
            font.setBold(False)
            for col in range(self.columnCount()):
                self.item(row, col).setFont(font)
        else:
            self.setItem(row, 1, QStandardItem("In Progress"))
            font = QFont()
            font.setBold(True)
            for col in range(self.columnCount()):
                self.item(row, col).setFont(font)
