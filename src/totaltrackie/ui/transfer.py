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
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Final

# pylint: disable=no-name-in-module
from PySide6.QtCore import QRect, QSize, Qt, QTime, Slot
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

# pylint: enable=no-name-in-module

from totaltrackie.core import Task, TasksManager, TimeSpan, get_current_utc_time, transfer_time_from_task
from totaltrackie.ui.icons import IconResource

GOLDEN_RATIO_CONJUGATE: Final[float] = 0.618033988749895


def get_color_for(index: int) -> QColor:
    h = (GOLDEN_RATIO_CONJUGATE * index) % 1.0
    return QColor.fromHsv(int(h * 360), int(0.5 * 255), int(0.8 * 255))


class ColorSquare(QWidget):
    def __init__(self, color: QColor) -> None:
        self.color: Final[QColor] = color
        super().__init__()
        self.setMinimumSize(QSize(16, 16))
        self.setFixedSize(QSize(16, 16))

    # pylint: disable-next=no-self-use
    def sizeHint(self, /) -> QSize:
        return QSize(16, 16)

    def paintEvent(self, _event: QPaintEvent, /) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), self.color)


class TimeLine(QWidget):
    def __init__(self, tasks: Iterable[Task]) -> None:
        super().__init__()
        self.setMaximumHeight(32)
        self.setMinimumHeight(32)
        self.setMinimumWidth(256)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum)
        self._offset: int = 4

        self._tasks: list[Task] = list(tasks)
        self._selection_task: tuple[str, datetime, timedelta] | None = None

    def set_tasks(self, t: Iterable[Task]) -> None:
        self._tasks = list(t)
        self.update()

    def reset_display(self) -> None:
        self._selection_task = None
        self.update()

    def display(self, source_task: str, offset: datetime, duration: timedelta) -> None:
        self._selection_task = (source_task, offset, duration)
        self.update()

    def sizeHint(self, /) -> QSize:
        return QSize(self.maximumHeight(), self.width())

    def minimumSizeHint(self, /) -> QSize:
        return QSize(self.minimumHeight(), self.width())

    def _get_tasks_min_max_time(self) -> tuple[int, int]:
        s_val: int | None = None
        d_val: int | None = None
        for task in self._tasks:
            for timeframe in task.timespans:
                s, d = self.timespan_to_seconds(timeframe)
                if s_val is None or s < s_val:
                    s_val = s
                if d_val is None or d > d_val:
                    d_val = d
        if s_val is None:
            raise ValueError
        if d_val is None:
            raise ValueError
        return s_val, d_val

    @staticmethod
    def time_to_day_seconds(s_time: datetime) -> int:
        return int(s_time.timestamp())

    @staticmethod
    def timespan_to_seconds(timeframe: TimeSpan) -> tuple[int, int]:
        s_time = timeframe.start
        s = TimeLine.time_to_day_seconds(s_time)
        d_time = timeframe.stop or get_current_utc_time()
        d = TimeLine.time_to_day_seconds(d_time)
        return s, d

    # pylint: disable-next=too-many-locals
    def paintEvent(self, _event: QPaintEvent, /) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        painter.fillRect(QRect(0, 0, self.width(), self.height()), QColor.fromRgb(255, 255, 255))

        s_min, d_max = self._get_tasks_min_max_time()
        total_width = d_max - s_min

        for index, task in enumerate(self._tasks):
            for timeframe in task.timespans:
                s, d = self.timespan_to_seconds(timeframe)

                s -= s_min
                d -= s_min

                x_start_pos = int(self.width() * (s / total_width))
                x_end_pos = int(self.width() * (d / total_width))
                target_rect = QRect(
                    x_start_pos, self._offset, x_end_pos - x_start_pos, self.height() - self._offset * 2
                )
                if target_rect.width() == 0:
                    continue

                painter.fillRect(target_rect, get_color_for(index))

        if self._selection_task is None:
            return
        task_name = self._selection_task[0]
        for item in self._tasks:
            if item.name == task_name:
                task = item
                break
        else:
            return

        duration = self._selection_task[2]
        _, spans = transfer_time_from_task(task, self._selection_task[1], duration)

        for span in spans:
            x1, x2 = self.timespan_to_seconds(span)
            x1 -= s_min
            x2 -= s_min
            x1 = int(self.width() * (x1 / total_width))
            x2 = int(self.width() * (x2 / total_width))
            painter.fillRect(QRect(x1, 0, x2 - x1, self.height()), QColor.fromRgb(0, 0, 0, 100))


class TransferTimeDialog(QDialog):
    # pylint: disable-next=too-many-statements
    def __init__(self, parent: QWidget, task_manager: TasksManager) -> None:
        super().__init__(parent)
        self._task_manager = task_manager
        _tasks = list(task_manager.get_tasks())
        self.setMinimumWidth(512)
        self.setWindowTitle("Transfer time between tasks")

        layout = QVBoxLayout()
        self.setLayout(layout)

        source_task_layout = QHBoxLayout()
        source_task_layout.addWidget(QLabel("Source task:"))
        dest_task_layout = QHBoxLayout()
        dest_task_layout.addWidget(QLabel("Destination task:"))

        self._source_task_combo = QComboBox()
        self._destination_task_combo = QComboBox()
        for item in _tasks:
            if len(item.timespans) == 0 or item.total_seconds() < 60:
                # task too small to transfer time for
                continue
            self._source_task_combo.addItem(item.name)
        source_task_layout.addWidget(self._source_task_combo)
        dest_task_layout.addWidget(self._destination_task_combo)

        layout.addLayout(source_task_layout)
        layout.addLayout(dest_task_layout)

        self._time_edit = QTimeEdit()
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Duration:"))
        duration_layout.addWidget(self._time_edit)

        layout.addLayout(duration_layout)

        self._timeline = TimeLine(_tasks)
        layout.addWidget(self._timeline)
        self._slider = QSlider()
        self._slider.setOrientation(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        self._slider.setMaximum(100)
        self._slider.setTickInterval(1)

        self._slider.sliderMoved.connect(self._on_slider_moved)
        self._source_task_combo.currentIndexChanged.connect(self._on_source_task_changed)
        self._time_edit.timeChanged.connect(self._on_duration_time_changed)

        layout.addWidget(self._slider)

        legend_layout = QGridLayout()
        for index, task in enumerate(_tasks):
            hbox = QHBoxLayout()
            hbox.addWidget(ColorSquare(get_color_for(index)))
            hbox.addWidget(QLabel(task.name))
            legend_layout.addLayout(hbox, index // 3, index % 3)
        layout.addLayout(legend_layout)

        self._transfer_button = QPushButton("Transfer")
        self._transfer_button.setIcon(IconResource.START.get_icon())
        self._transfer_button.setDisabled(True)
        self._transfer_button.clicked.connect(self._on_transfer_button_clicked)
        layout.addWidget(self._transfer_button)

        self._reset_slider()
        self._time_edit.setTime(QTime(0, 30))
        self._source_task_combo.setCurrentIndex(0)

        self._on_source_task_changed(0)
        self._on_slider_moved(100)
        self._on_duration_time_changed(QTime(0, 30))

    def _reset_slider(self) -> None:
        self._slider.setValue(100)

    @Slot()
    def _on_transfer_button_clicked(self) -> None:
        if (params := self._get_display_params()) is None:
            self._transfer_button.setEnabled(False)
            self._timeline.reset_display()
            return
        task_name, offset, duration = params
        destination_task = self._destination_task_combo.currentText()

        self._task_manager.transfer_time(task_name, destination_task, offset, duration)
        self._timeline.set_tasks(self._task_manager.get_tasks())
        self._reset_slider()
        self._update_selection_on_timeline()

    def _get_display_params(self) -> tuple[str, datetime, timedelta] | None:
        source_task = self._task_manager.get(self._source_task_combo.currentText())
        if source_task is None:
            return None
        duration = timedelta(milliseconds=self._time_edit.time().msecsSinceStartOfDay())
        if duration.total_seconds() < 60:
            return None
        transfer_offset = timedelta(
            seconds=(source_task.total_seconds() - duration.total_seconds()) * (self._slider.value() / 100)
        )
        start_time = min(t.start for t in source_task.timespans)

        return source_task.name, start_time + transfer_offset, duration

    def _update_selection_on_timeline(self) -> None:
        if (params := self._get_display_params()) is not None:
            self._timeline.display(*params)
            self._transfer_button.setEnabled(True)
        else:
            self._transfer_button.setEnabled(False)
            self._timeline.reset_display()

    @Slot(int)
    def _on_source_task_changed(self, _index: int) -> None:
        source_task = self._task_manager.get(self._source_task_combo.currentText())
        if source_task is None:
            return
        self._destination_task_combo.clear()
        for item in self._task_manager.get_tasks():
            if source_task.name == item.name:
                continue
            self._destination_task_combo.addItem(item.name)

        self._reset_slider()
        self._time_edit.setMaximumTime(QTime.fromMSecsSinceStartOfDay(int(source_task.total_seconds() * 1000)))
        self._time_edit.setMinimumTime(QTime.fromMSecsSinceStartOfDay(0))
        self._update_selection_on_timeline()

    @Slot(int)
    def _on_slider_moved(self, _value: int) -> None:
        self._update_selection_on_timeline()

    @Slot(QTime)
    def _on_duration_time_changed(self, _value: QTime) -> None:
        self._update_selection_on_timeline()
