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

import dataclasses
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from totaltrackie.core import Task, TasksManager, TimeSpan


@dataclass
class Settings:
    work_time_hours: int = 8
    work_time_minutes: int = 0
    templates: dict[str, bool] = dataclasses.field(default_factory=dict)

    @property
    def work_time_as_timedelta(self) -> timedelta:
        return timedelta(hours=self.work_time_hours, minutes=self.work_time_minutes)


class PersistenceManager:
    def __init__(self, store_dir: Path):
        self._store_dir = store_dir
        self._settings_file = store_dir / "settings.json"

    @property
    def store_dir(self) -> Path:
        return self._store_dir

    def save_settings(self, settings: Settings) -> None:
        self._settings_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._settings_file, "wt", encoding="utf-8") as file_handle:
            file_handle.write(
                json.dumps(
                    {
                        "workTimeHours": settings.work_time_hours,
                        "workTimeMinutes": settings.work_time_minutes,
                        "templatedTasks": settings.templates,
                    },
                    indent=4,
                )
            )

    def load_settings(self) -> Settings:
        settings = Settings()
        try:
            with open(self._settings_file, "rt", encoding="utf-8") as file_handle:
                data = file_handle.read()
                parsed_data = json.loads(data)
                settings.work_time_minutes = parsed_data["workTimeMinutes"]
                settings.work_time_hours = parsed_data["workTimeHours"]

                settings.templates = {}

                templated_tasks = parsed_data.get("templatedTasks")
                if isinstance(templated_tasks, list):
                    settings.templates = {item: False for item in templated_tasks}
                elif isinstance(templated_tasks, dict):
                    settings.templates = templated_tasks
        except (FileNotFoundError, json.JSONDecodeError):
            self.save_settings(settings)
        return settings

    def _get_save_file_name(self, day: date) -> Path:
        return self._store_dir / "tasks" / str(day.year) / str(day.month) / f"{day.day}.json"

    def save_tasks(self, day: date, tasks: TasksManager) -> None:
        save_file = self._get_save_file_name(day)
        save_file.parent.mkdir(exist_ok=True, parents=True)

        data = [
            {
                "name": task.name,
                "comments": task.comments,
                "timespans": [
                    {
                        "start": timespan.start.isoformat(),
                        "stop": (timespan.stop.isoformat() if timespan.stop is not None else None),
                    }
                    for timespan in task.timespans
                ],
            }
            for task in tasks.get_tasks()
        ]

        save_file.write_text(json.dumps(data, indent=4), encoding="utf-8")

    def load_tasks(self, day: date, manager: TasksManager) -> None:
        save_file = self._get_save_file_name(day)
        manager.clear()
        if save_file.is_file():
            data = json.loads(save_file.read_text(encoding="utf-8"))
            for item in data:
                task = Task(
                    item["name"],
                    comments=item["comments"],
                    timespans=[
                        TimeSpan(
                            start=datetime.fromisoformat(timespan["start"]),
                            stop=(datetime.fromisoformat(timespan["stop"]) if timespan["stop"] is not None else None),
                        )
                        for timespan in item["timespans"]
                    ],
                )
                manager.add(task)

    @property
    def logs_folder(self) -> Path:
        return self._store_dir / "logs"
