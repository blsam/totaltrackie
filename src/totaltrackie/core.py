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

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone

APP_NAME: str = "TotalTrackie"


def get_current_utc_time() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class TimeSpan:
    start: datetime
    stop: datetime | None


@dataclass
class Task:
    name: str
    comments: str
    timespans: list[TimeSpan]

    def total_seconds(self) -> int:
        if self.timespans:
            last_time_span = self.timespans[-1]
            seconds = sum((x.stop - x.start).total_seconds() for x in self.timespans[:-1])
            last_term_end = last_time_span.stop if last_time_span.stop is not None else get_current_utc_time()
            seconds += (last_term_end - last_time_span.start).total_seconds()
            return seconds
        return 0

    def is_started(self) -> bool:
        if self.timespans:
            return self.timespans[-1].stop is None
        return False


class TaskManagerError(Exception):
    pass


class TaskAlreadyExists(TaskManagerError):
    pass


class TasksManager:
    def __init__(self):
        self._tasks: list[Task] = []
        self._active_task: int | None = None

    def get_tasks(self) -> list[Task]:
        return deepcopy(self._tasks)

    def clear(self):
        self._tasks.clear()
        self._active_task = None

    def has(self, name: str) -> bool:
        return any(name == x.name for x in self._tasks)

    def add(self, task: Task):
        if self.has(task.name):
            raise TaskAlreadyExists(task.name)

        self._tasks.append(task)

        if task.is_started():
            self._active_task = len(self._tasks) - 1

    def remove(self, index: int):
        if 0 <= index < len(self._tasks):
            if index == self._active_task:
                self._active_task = None
            self._tasks.remove(self._tasks[index])

    def get(self, index: int) -> Task | None:
        if 0 <= index < len(self._tasks):
            return self._tasks[index]
        return None

    def edit(self, index: int, task: Task):
        if 0 <= index < len(self._tasks):
            if self._tasks[index] == self._active_task:
                self._active_task = task
            self._tasks[index] = task

    def start(self, index: int):
        if 0 <= index < len(self._tasks):
            self.stop_active()

            self._active_task = index
            self._tasks[index].timespans.append(TimeSpan(get_current_utc_time(), None))

    def stop(self, index: int):
        if 0 <= index < len(self._tasks):
            self._tasks[index].timespans[-1].stop = get_current_utc_time()
            last_timespan = self._tasks[index].timespans[-1]
            if (last_timespan.stop - last_timespan.start).total_seconds() < 2:
                self._tasks[index].timespans.pop(-1)
            self._active_task = None

    def stop_active(self) -> bool:
        index = self.active_index()
        if index is not None:
            self.stop(index)
            return True
        return False

    def active(self) -> Task | None:
        index = self.active_index()
        if index is not None:
            return self.get(index)
        return None

    def active_index(self) -> int | None:
        return self._active_task

    def get_tasks_cumulative_time(self) -> int:
        return sum(x.total_seconds() for x in self._tasks)
