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
from abc import ABC
from collections.abc import Callable
from datetime import date, timedelta
from enum import Flag, auto
from functools import cached_property
from importlib.metadata import entry_points
from pathlib import Path
from typing import TypeAlias

# pylint: disable=no-name-in-module
from PySide6.QtCore import Slot, QObject
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
# pylint: enable=no-name-in-module

from totaltrackie.core import APP_NAME, Task, get_current_utc_time
from totaltrackie.persistent import PersistenceManager, Settings
from totaltrackie.ui._utils import python_date_to_q_date, q_date_to_python_date
from totaltrackie.ui.icons import IconResource

_logger = logging.getLogger(__name__)


class PluginSettings(ABC):
    def get(self, key: str) -> str:
        raise NotImplementedError

    def set(self, key: str, value: str) -> None:
        raise NotImplementedError


class PluginSettingsPersistentStore(PluginSettings):
    def __init__(self, persist_manager: PersistenceManager, plugin_name: str) -> None:
        self._manager = persist_manager
        self._plugin_name = plugin_name

    @cached_property
    def _settings(self) -> Settings:
        return self._manager.load_settings()

    def get(self, key: str) -> str:
        value = self._settings.plugins_settings.get(self._plugin_name, {}).get(key, "")
        _logger.debug("Plugin '%s' accessed setting '%s': '%s'", self._plugin_name, key, value)
        return value

    def set(self, key: str, value: str) -> None:
        if not isinstance(key, str) or not isinstance(value, str):
            _logger.debug(  # type: ignore[unreachable]
                "Setting '%s': '%s' not saved, as key/value is not a string [plugin '%s']",
                key,
                value,
                self._plugin_name,
            )
            raise TypeError

        settings = self._settings
        if self._plugin_name not in settings.plugins_settings:
            settings.plugins_settings[self._plugin_name] = {}

        settings.plugins_settings[self._plugin_name][key] = value
        self._manager.save_settings(settings)
        _logger.debug("Plugin '%s' saved setting '%s': '%s'", self._plugin_name, key, value)
        del self._settings
        _logger.debug("Clear cache for settings of plugin '%s'", self._plugin_name)


_PLUGIN_CALLABLE: TypeAlias = Callable[[Callable[..., None], QObject | None, dict[date, list[Task]], PluginSettings], None]


class PluginSupportedFeatures(Flag):
    NONE = 0
    MULTI_DAY = auto()


class PluginRegistry:
    _registry: dict[int, tuple[PluginSupportedFeatures, _PLUGIN_CALLABLE]] = {}

    @classmethod
    def register(
        cls, version: int, features: PluginSupportedFeatures
    ) -> Callable[[_PLUGIN_CALLABLE], _PLUGIN_CALLABLE]:
        def _wrapper(fn: _PLUGIN_CALLABLE) -> _PLUGIN_CALLABLE:
            _logger.debug("Registered plugin wrapper: %s (features: %s)", fn, features)
            cls._registry[version] = (features, fn)
            return fn

        return _wrapper

    @classmethod
    def get_versions(cls) -> set[int]:
        return set(cls._registry.keys())

    @classmethod
    def get_supported_versions(cls, features: PluginSupportedFeatures) -> set[int]:
        result = set()
        for item, item_def in cls._registry.items():
            plugin_features = item_def[0]
            if features & plugin_features == features:
                result.add(item)
        _logger.debug("Supported versions of plugins for '%s' feature set: '%s'", features, result)
        return result

    @classmethod
    def invoke(cls, version: int) -> _PLUGIN_CALLABLE:
        return cls._registry[version][1]


@PluginRegistry.register(1, PluginSupportedFeatures.NONE)
def _v1_plugins(fn: Callable[..., None], p: QObject | None, d: dict[date, list[Task]], _: PluginSettings) -> None:
    i = next(iter(d.items()))
    fn(p, i[0], [1])


@PluginRegistry.register(2, PluginSupportedFeatures.MULTI_DAY)
def _v2_plugins(fn: Callable[..., None], p: QObject | None, d: dict[date, list[Task]], settings: PluginSettings) -> None:
    fn(p, d, settings)


def _get_plugin_entrypoints(version: int) -> dict[str, Callable[..., None]]:
    generators = {}
    lowered_app_name = APP_NAME.lower()
    group = f"{lowered_app_name}.plugins"
    if version > 1:
        group = f"{group}_v{version}"
    plugins = entry_points(group=group)
    for entrypoint in plugins:
        try:
            plugin_generator = entrypoint.load()
        except Exception as error:  # pylint: disable=broad-exception-caught
            _logger.debug("Issue when loading plugin entrypoint ['%s']: %s", entrypoint, error, exc_info=error)
            continue

        if not callable(plugin_generator):
            _logger.debug("The plugin entrypoint ['%s']: is not a callable, ignore", entrypoint)
            continue
        gen_name = f"{entrypoint.name} [{entrypoint.dist.name if entrypoint.dist else 'unknown'}]"
        _logger.debug("Registered generator: '%s' as '%s'", plugin_generator, gen_name)
        generators[gen_name] = plugin_generator
    return generators


class ReportDialog(QDialog):
    def __init__(self, parent: QWidget, current_date: date, *, persistent_manager: PersistenceManager):
        super().__init__(parent)
        self.setModal(True)
        self.setWindowTitle("Report generation")
        layout = QVBoxLayout()
        self.setLayout(layout)

        date_selector_layout = QHBoxLayout()
        date_selector_layout.addWidget(QLabel("Time range:"))
        self._start_date = QDateEdit()
        self._start_date.setCalendarPopup(True)
        self._start_date.setMaximumDate(python_date_to_q_date(get_current_utc_time().date()))
        self._start_date.setDate(python_date_to_q_date(get_current_utc_time().date()))
        self._start_date.dateChanged.connect(self._on_start_date_changed)
        date_selector_layout.addWidget(self._start_date)
        self._end_date = QDateEdit()
        self._end_date.setCalendarPopup(True)
        self._end_date.setMaximumDate(python_date_to_q_date(get_current_utc_time().date()))
        self._end_date.setDate(python_date_to_q_date(get_current_utc_time().date()))
        self._end_date.dateChanged.connect(self._on_end_date_changed)
        date_selector_layout.addWidget(self._end_date)
        layout.addLayout(date_selector_layout)

        confirm_button = QPushButton(IconResource.OK.get_icon(), "Confirm")
        confirm_button.clicked.connect(self.accept)
        cancel_button = QPushButton(IconResource.CANCEL.get_icon(), "Cancel")
        cancel_button.clicked.connect(self.reject)

        generator_select_layout = QHBoxLayout()
        self._generator_selector = QComboBox()

        generator_select_layout.addWidget(QLabel("Report Generator: "))
        generator_select_layout.addWidget(self._generator_selector)
        layout.addLayout(generator_select_layout)

        confirm_layout = QHBoxLayout()
        confirm_layout.addWidget(confirm_button)
        confirm_layout.addWidget(cancel_button)
        layout.addLayout(confirm_layout)

        self.current_date = current_date
        self._persistent_manager = persistent_manager
        self._settings = self._persistent_manager.load_settings()

        self._generators: dict[str, tuple[int, Callable[..., None]]] = {}
        for version in PluginRegistry.get_versions():
            for gen, cl in _get_plugin_entrypoints(version).items():
                self._generators[gen] = (version, cl)
                self._generator_selector.addItem(gen)

        self._last_supported_flags: PluginSupportedFeatures = PluginSupportedFeatures.NONE
        self._force_generators_enabled(self._last_supported_flags)

    def _determine_features(self) -> PluginSupportedFeatures:
        features = PluginSupportedFeatures.NONE

        start = q_date_to_python_date(self._start_date.date())
        end = q_date_to_python_date(self._end_date.date())
        if start != end:
            features |= PluginSupportedFeatures.MULTI_DAY

        return features

    def _force_generators_enabled(self, features: PluginSupportedFeatures) -> None:
        self._generator_selector.clear()
        versions = PluginRegistry.get_supported_versions(features)
        for gen, gen_def in self._generators.items():
            if gen_def[0] in versions:
                self._generator_selector.addItem(gen)
                if gen == self._settings.preferred_report_generator:
                    self._generator_selector.setCurrentIndex(self._generator_selector.count() - 1)

    def _set_generators_enabled(self) -> None:
        features = self._determine_features()
        if features == self._last_supported_flags:
            return
        self._force_generators_enabled(features)
        self._last_supported_flags = features  # cache

    @Slot()
    def _on_start_date_changed(self) -> None:
        start = q_date_to_python_date(self._start_date.date())
        end = q_date_to_python_date(self._end_date.date())
        end = max(end, start)
        self._end_date.setDate(python_date_to_q_date(end))
        self._set_generators_enabled()

    @Slot()
    def _on_end_date_changed(self) -> None:
        start = q_date_to_python_date(self._start_date.date())
        end = q_date_to_python_date(self._end_date.date())
        start = min(start, end)
        self._start_date.setDate(python_date_to_q_date(start))
        self._set_generators_enabled()

    def accept(self) -> None:
        super().accept()

        self._settings.preferred_report_generator = self._generator_selector.currentText()
        self._persistent_manager.save_settings(self._settings)

        version, fn = self._generators[self._generator_selector.currentText()]
        start_date = q_date_to_python_date(self._start_date.date())
        end_date = q_date_to_python_date(self._end_date.date())
        days = [start_date + timedelta(days=dt) for dt in range((end_date - start_date).days + 1)]

        plugin_settings = PluginSettingsPersistentStore(
            self._persistent_manager, self._generator_selector.currentText()
        )

        tasks = {d: self._persistent_manager.load_tasks_raw(d) for d in days}
        tasks = {k: v for k, v in tasks.items() if v}  # filter out empty tasks days

        if not tasks:
            box = QMessageBox(
                QMessageBox.Icon.Warning,
                self.windowTitle(),
                "No tasks to report in this period!",
            )
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.setDefaultButton(QMessageBox.StandardButton.Ok)
            box.setWindowIcon(self.windowIcon())
            box.exec()
            return

        try:
            PluginRegistry.invoke(version)(fn, self.parent(), tasks, plugin_settings)
        except Exception as error:  # pylint: disable=broad-exception-caught
            _logger.exception(
                "Exception happened in plugin '%s': %s", self._generator_selector.currentText(), error, exc_info=error
            )
            box = QMessageBox(
                QMessageBox.Icon.Critical,
                "Error",
                f"Report generator '{self._generator_selector.currentText()}' have failed during generation. "
                f"Please report to developers.",
            )
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.setWindowIcon(self.windowIcon())
            box.exec()
            return


def _convert_tasks_to_default_report(tasks: list[Task]) -> str:
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
    return "".join(strings)


def generic_report_generator_single_day(parent: QWidget, current_date: date, tasks: list[Task]) -> None:
    strings = _convert_tasks_to_default_report(tasks)

    default_name = current_date.strftime("%Y-%m-%d")
    path_str, _ = QFileDialog.getSaveFileName(parent, filter="*.txt", dir=f"{default_name}.txt")
    if path_str:
        path = Path(path_str)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wt", encoding="utf-8") as file_handle:
            file_handle.write(strings)


def generic_report_generator(parent: QWidget, tasks: dict[date, list[Task]], settings: PluginSettings) -> None:
    default_report_name = "report.txt"
    if len(tasks) == 1:
        default_report_name = list(tasks)[0].strftime("%Y-%m-%d.txt")
    _logger.debug("Default report generator: will use save filename: '%s'", default_report_name)

    save_dir = settings.get("save_dir")
    if not save_dir:
        save_dir = "."
    _logger.debug("Default report generator: will use next default folder to show save dialog: %s", save_dir)
    path_str, _ = QFileDialog.getSaveFileName(parent, filter="*.txt", dir=str(Path(save_dir, default_report_name)))
    _logger.debug("Default report generator: user provided path '%s' for saving report", path_str)
    if path_str:
        path = Path(path_str)
        path.parent.mkdir(parents=True, exist_ok=True)
        if save_dir != str(path.parent):
            settings.set("save_dir", str(path.parent))

        with open(path, "wt", encoding="utf-8") as file_handle:
            for d, t in tasks.items():
                if not t:
                    continue
                file_handle.write("--- ")
                file_handle.write(d.strftime("%Y-%m-%d"))
                file_handle.write(" ---\n\n")
                file_handle.write(_convert_tasks_to_default_report(t))
                file_handle.write("\n\n")
