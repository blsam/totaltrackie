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
from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

APP_NAME: str = __package__


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
        return int(sum(
            ((x.stop if x.stop is not None else get_current_utc_time()) - x.start).total_seconds() for x in self.timespans
        ))

    def is_started(self) -> bool:
        if self.timespans:
            return self.timespans[-1].stop is None
        return False


class TaskManagerError(Exception):
    pass


class TaskAlreadyExists(TaskManagerError):
    pass


def transfer_time_from_task(
    task: Task, offset: datetime, duration: timedelta
) -> tuple[Sequence[TimeSpan], Sequence[TimeSpan]]:
    if (offset + duration) > max((t.stop or get_current_utc_time() for t in task.timespans)):
        raise ValueError

    cur_pos = offset
    cur_pos_stop = cur_pos + duration

    original_task_timespans: list[TimeSpan] = []
    new_task_timespans: list[TimeSpan] = []

    task_dur_sum = min(t.start for t in task.timespans)
    for timespan in sorted(task.timespans, key=lambda x: x.start):
        s = timespan.start
        d = timespan.stop or get_current_utc_time()
        curr_span_size = d - s
        if cur_pos_stop <= task_dur_sum or cur_pos >= (task_dur_sum + curr_span_size):
            task_dur_sum += curr_span_size
            original_task_timespans.append(timespan)
            continue

        st = max(cur_pos, task_dur_sum) - task_dur_sum
        ed = min(cur_pos_stop, task_dur_sum + curr_span_size) - task_dur_sum
        if st.total_seconds() > 0:
            original_task_timespans.append(TimeSpan(timespan.start, timespan.start + st))

        new_task_timespans.append(
            TimeSpan(
                timespan.start + st,
                timespan.start + ed,
            )
        )

        if ed < curr_span_size:
            original_task_timespans.append(
                TimeSpan(
                    timespan.start + ed,
                    timespan.stop,
                )
            )

        task_dur_sum += curr_span_size

    return original_task_timespans, new_task_timespans


class TasksManager:
    def __init__(self) -> None:
        self._tasks: list[Task] = []
        self._active_task: int | None = None

    def transfer_time(
        self, source_task: int | str, target_task: int | str, start: datetime, duration: timedelta
    ) -> None:
        s_task = self.get(source_task)
        d_task = self.get(target_task)
        if s_task is None or d_task is None:
            raise ValueError("No such tasks")
        original_frames, new_frames = transfer_time_from_task(s_task, start, duration)
        s_task.timespans = list(original_frames)
        target_timeframes = [*new_frames, *d_task.timespans]
        target_timeframes.sort(key=lambda x: x.start)
        d_task.timespans = target_timeframes

    def has_tasks(self) -> bool:
        return bool(self._tasks)

    def get_tasks(self) -> list[Task]:
        return deepcopy(self._tasks)

    def clear(self) -> None:
        self._tasks.clear()
        self._active_task = None

    def has(self, name: str) -> bool:
        return any(name == x.name for x in self._tasks)

    def add(self, task: Task) -> None:
        if self.has(task.name):
            raise TaskAlreadyExists(task.name)

        self._tasks.append(task)

        if task.is_started():
            self._active_task = len(self._tasks) - 1

    def remove(self, index: int) -> None:
        if 0 <= index < len(self._tasks):
            if index == self._active_task:
                self._active_task = None
            self._tasks.remove(self._tasks[index])

    def get(self, index: int | str) -> Task | None:
        if isinstance(index, int):
            if 0 <= index < len(self._tasks):
                return self._tasks[index]
        elif isinstance(index, str):  # pylint: disable=confusing-consecutive-elif
            for task in self._tasks:
                if task.name == index:
                    return task
        return None

    def edit(self, index: int, task: Task) -> None:
        if 0 <= index < len(self._tasks):
            self._tasks[index] = task

    def start(self, index: int) -> None:
        if 0 <= index < len(self._tasks):
            self.stop_active()

            self._active_task = index
            self._tasks[index].timespans.append(TimeSpan(get_current_utc_time(), None))

    def stop(self, index: int) -> None:
        if 0 <= index < len(self._tasks):
            last_timespan = self._tasks[index].timespans[-1]
            last_timespan.stop = get_current_utc_time()
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
