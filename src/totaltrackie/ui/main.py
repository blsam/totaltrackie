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
from typing import List

from PySide6.QtCore import QDate, QModelIndex, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFont, QStandardItem, QStandardItemModel
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
from totaltrackie.ui._utils import connect_event
from totaltrackie.ui.about import AboutDialog
from totaltrackie.ui.icons import IconResource
from totaltrackie.ui.report import ReportGenerateDialog
from totaltrackie.ui.settings import SettingsWindow
from totaltrackie.ui.task import EditTaskDialogWindow
from totaltrackie.ui.templates import TemplatesDialog

logger = logging.getLogger(__name__)


@dataclass
class _MenuActions:
    start: QAction
    relax: QAction
    report: QAction
    templates: QAction
    settings: QAction


class MainWindow(QMainWindow):
    def __init__(self, store: PersistenceManager):
        super().__init__()
        self.setWindowIcon(IconResource.APP.get_icon())
        self._tray_icon = QSystemTrayIcon(self.windowIcon())
        connect_event(self._tray_icon.activated, self._on_tray_icon_clicked)

        self._menu_actions = self._build_action_menu()

        self._persistent_store = store
        self._task_manager: TasksManager = TasksManager()

        self._settings = store.load_settings()

        tray_menu = QMenu()
        quit_action = QAction("Exit", self)
        connect_event(quit_action.triggered, self._on_application_exit)

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
        connect_event(self._relax_button.clicked, self._on_relax_button_clicked)

        self._add_button = QPushButton(IconResource.ADD.get_icon(), "Add Task")
        connect_event(self._add_button.clicked, self._on_task_add_button_clicked)
        self._remove_button = QPushButton(IconResource.REMOVE.get_icon(), "Remove Task")
        connect_event(self._remove_button.clicked, self._on_task_remove_button_clicked)

        self._edit_button = QPushButton(IconResource.EDIT.get_icon(), "Edit Task")
        connect_event(self._edit_button.clicked, self._on_task_edit_button_clicked)

        self._tasks_model = TaskStorageDataModel()
        self._tasks_view = QTableView()
        self._tasks_view.horizontalHeader().setStretchLastSection(True)
        self._tasks_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tasks_view.setShowGrid(True)
        self._tasks_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._tasks_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tasks_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        connect_event(self._tasks_view.doubleClicked, self._on_start_button_clicked)
        self._tasks_view.setModel(self._tasks_model)

        connect_event(
            self._tasks_view.selectionModel().selectionChanged,
            self._on_task_selection_changed,
        )

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

        connect_event(self._update_timer.timeout, self._on_update_timer_tick)
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
        connect_event(self._day_selector.dateChanged, self._on_current_date_changed)
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
        connect_event(stop_action.triggered, self._on_relax_button_clicked)

        start_action = QAction(IconResource.START.get_icon(), "Start", self)
        connect_event(start_action.triggered, self._on_start_button_clicked)

        report_action = QAction(IconResource.REPORT.get_icon(), "Build &report...", self)
        connect_event(report_action.triggered, self._on_report_button_click)

        task_menu.addActions((start_action, stop_action))
        task_menu.addSeparator()
        task_menu.addAction(report_action)

        settings_action = QAction(IconResource.SETTINGS.get_icon(), "Settings", self)
        connect_event(settings_action.triggered, self._on_settings_button_clicked)

        template_action = QAction(IconResource.TEMPLATES.get_icon(), "Templates...", self)
        connect_event(template_action.triggered, self._on_templates_button_click)

        preferences_menu = self.menuBar().addMenu("&Preferences")
        preferences_menu.addAction(settings_action)
        preferences_menu.addAction(template_action)

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("About", self)
        connect_event(about_action.triggered, self._on_about_clicked)

        open_storage_action = QAction("Open persistent &storage location...", self)
        connect_event(open_storage_action.triggered, self._on_open_storage_clicked)

        help_menu.addAction(open_storage_action)
        help_menu.addSeparator()
        help_menu.addAction(about_action)

        return _MenuActions(
            start=start_action,
            relax=stop_action,
            report=report_action,
            templates=template_action,
            settings=settings_action,
        )

    def _on_open_storage_clicked(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._persistent_store.store_dir)))

    def _on_about_clicked(self):
        about_dialog = AboutDialog(self)
        about_dialog.exec()

    def _on_tray_icon_clicked(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            logger.debug("Show application main window as tray icon double-clicked")
            self.show()

    def _on_templates_button_click(self):
        templates_dialog = TemplatesDialog(self, self._settings.templates)
        code = templates_dialog.exec()

        templates_to_insert = templates_dialog.get_selected_tasks_for_inserting()
        new_templates = templates_dialog.get_entered_templates()

        if code == QDialog.DialogCode.Accepted:
            for task in templates_to_insert:
                self._task_manager.add(Task(task, "", []))

            self._tasks_model.refresh(self._task_manager, force=True)

        if self._settings.templates != new_templates:
            self._settings.templates.clear()
            self._settings.templates.update(new_templates)
            self._persistent_store.save_settings(self._settings)

    def _on_application_exit(self):
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

        if should_exit:
            QApplication.instance().quit()

    def closeEvent(self, event):
        event.ignore()
        logger.debug("Hiding main window...")
        self.hide()

        logger.debug("Stopping update timer...")
        self._update_timer.stop()

    def show(self):
        self._tray_icon.show()
        super().show()

        if self._task_manager.active() is not None:
            logger.debug("Starting update timer as there active task found")
            self._update_timer.start()

    @property
    def selected_task(self) -> int:
        selection: List[QModelIndex] = self._tasks_view.selectedIndexes()
        if not selection:
            return -1
        return selection[0].row()

    @property
    def selected_date(self) -> date:
        gui_date = self._day_selector.date()
        return date(year=gui_date.year(), month=gui_date.month(), day=gui_date.day())

    def _control_relax_action(self, status: bool):
        self._relax_button.setEnabled(status)
        self._menu_actions.relax.setEnabled(status)

    def _on_current_date_changed(self):
        self._persistent_store.load_tasks(self.selected_date, self._task_manager)
        self._tasks_model.refresh(self._task_manager, force=True)

        self._update_buttons_state()
        self._on_update_timer_tick()
        if self._task_manager.active() is not None:
            logger.debug("Activating update timer after changing date...")
            self._update_timer.start()

    def _on_settings_button_clicked(self):
        settings_window = SettingsWindow(self, self._settings)
        settings_window.exec()

        result = settings_window.get_result()
        if result is not None:
            logger.debug("Settings changed into %s", result)
            self._settings = result
            self._on_update_timer_tick()
            self._persistent_store.save_settings(self._settings)

    def _on_update_timer_tick(self):
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
            active_task_time = str(timedelta(seconds=int(self._task_manager.active().total_seconds())))
            self._time_task_label.setText(active_task_time)
        else:
            self._time_left_label_prefix.setText("End of work at:")
            if self.selected_date == date.today() and left_time > 0:
                active_task_time = datetime.now() + timedelta(seconds=left_time)
                self._time_task_label.setText(active_task_time.strftime("%H:%M:%S"))
            else:
                self._time_task_label.setText("N/A")

    def _update_buttons_state(self):
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
                self._menu_actions.start.setEnabled(not self._task_manager.get(self.selected_task).is_started())
            else:
                self._menu_actions.start.setEnabled(False)
                self._edit_button.setEnabled(False)
                self._remove_button.setEnabled(False)
            self._control_relax_action(self._task_manager.active() is not None)

    def _on_start_button_clicked(self):
        # This is also called when double-clicked, so, here additional check
        if not self._menu_actions.start.isEnabled():
            return

        logger.debug("Clicked starting button, starting selected task %s", self.selected_task)
        self._task_manager.start(self.selected_task)
        self._update_buttons_state()

        if self._update_timer.isActive() is False:
            self._update_timer.start()

        self._persistent_store.save_tasks(self.selected_date, self._task_manager)
        self._on_update_timer_tick()

        self._tasks_model.invalidate()
        self._tasks_model.refresh(self._task_manager)

    def _on_relax_button_clicked(self):
        logger.debug("Starting relax...")
        index = self._task_manager.active_index()

        self._task_manager.stop_active()

        self._tasks_model.invalidate(index)
        self._tasks_model.refresh(self._task_manager)

        self._update_buttons_state()
        self._on_update_timer_tick()

        logger.debug("Scheduling save...")
        self._persistent_store.save_tasks(self.selected_date, self._task_manager)

    def _on_task_remove_button_clicked(self):
        task = self._task_manager.get(self.selected_task)
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

    def _on_task_add_button_clicked(self):
        add_dialog = EditTaskDialogWindow(self)
        dialog_result = None

        while dialog_result is None:
            dialog_result = add_dialog.exec()
            task = add_dialog.get_result_as_task()
            if task is not None:
                logger.debug("Trying to add a new task %s", task.name)
                if self._task_manager.has(task.name):
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

    def _on_task_edit_button_clicked(self):
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

    def _on_task_selection_changed(self):
        self._update_buttons_state()
        self._on_update_timer_tick()

    def _on_report_button_click(self):
        if self._task_manager.active() is not None:
            box = QMessageBox(QMessageBox.Icon.Warning, "Warning", "Active tasks must be completed")
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.setWindowIcon(self.windowIcon())
            box.exec()
            return

        dialog = ReportGenerateDialog(self, self.selected_date, self._task_manager.get_tasks())
        dialog.exec()


class TaskStorageDataModel(QStandardItemModel):
    def __init__(self):
        super().__init__(0, 3)
        self.setHorizontalHeaderLabels(["Task", "Duration", "Comments"])

        self._invalidated_rows: list[int] = []
        self._invalidate_all: bool = False

    def invalidate(self, row: int = -1):
        if row <= -1:
            self._invalidate_all = True
        else:
            self._invalidated_rows.append(row)

    def refresh(self, manager: TasksManager, force: bool = False):
        if force:
            self._invalidate_all = True

        if self._invalidate_all:
            self.removeRows(0, self.rowCount())
            for index, task in enumerate(manager.get_tasks()):
                self._format_task_entry(index, task)
        else:
            for row in self._invalidated_rows:
                task = manager.get(row)
                if task is None:
                    continue
                self._format_task_entry(row, task)
        self._invalidated_rows.clear()
        self._invalidate_all = False

    def _format_task_entry(self, row: int, task: Task):
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
