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
import argparse
import ctypes
import hashlib
import importlib.metadata
import importlib.resources
import json
import logging
import os
import platform
import shlex
import shutil
import subprocess
import sys
from collections.abc import Generator
from dataclasses import dataclass
from functools import cache
from importlib.metadata import PackageNotFoundError
from os import PathLike
from pathlib import Path
from tempfile import TemporaryDirectory
from time import sleep
from typing import Final
from urllib.error import HTTPError
from urllib.request import urlopen

import packaging.version
from packaging.utils import InvalidName, canonicalize_name
from packaging.version import InvalidVersion
from PySide6.QtCore import QEvent, QObject, QProcess, QSize, QThread, Signal, Slot
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QDialog, QMainWindow, QMessageBox, QTextEdit, QVBoxLayout, QWidget

from totaltrackie.core import APP_NAME
from totaltrackie.ui._utils import start_gui_app
from totaltrackie.ui.icons import IconResource

_logger = logging.getLogger(__name__)

USER_FACED_ERROR_FILE_ENV: Final[str] = f"{APP_NAME.upper()}_USER_FACED_UPDATE_ERROR"


class GenericUpdateError(Exception):
    pass


def is_valid_python_package_name(name: str) -> bool:
    try:
        canonicalize_name(name, validate=True)
    except InvalidName:
        return False
    return True


@dataclass(kw_only=True, frozen=True, eq=True)
class PackageReference:
    ref: str
    updatable: bool


@dataclass(kw_only=True, frozen=True)
class UpdateData:
    update_url: str
    known_plugins: dict[str, PackageReference]


@cache
def get_update_data() -> UpdateData | None:
    path = importlib.resources.files(APP_NAME).joinpath("update_data/update.json")
    if not path.is_file():
        return None

    with path.open("rb") as handle:
        data = json.load(handle)

    try:
        return UpdateData(
            update_url=data["update_url"],
            known_plugins={
                k: PackageReference(ref=str(v["url"]), updatable=bool(v["updatable"]))
                for k, v in data["known_plugins"].items()
            },
        )
    except Exception as error:  # pylint: disable=broad-exception-caught
        _logger.warning("Unable to load update data: %s", error, exc_info=error)
        return None


def is_update_functionality_enabled() -> bool:
    is_venv = sys.prefix != sys.base_prefix
    has_update_data = get_update_data() is not None

    return is_venv and has_update_data


def venv_unique_id(base_storage_dir: Path) -> Path:
    venv_id = hashlib.sha256(sys.prefix.encode("utf-8")).hexdigest()
    return base_storage_dir / "instances" / venv_id


class EnvironmentDescriptor:
    def __init__(self, root: Path) -> None:
        self.registry: Final[Path] = root / "env.json"
        self.whl_house: Final[Path] = root / "whl-house"

        self._packages: dict[str, PackageReference] | None = None

    def list(self) -> dict[str, PackageReference]:
        if self._packages is None:
            packages: dict[str, PackageReference] = {}
            try:
                data = json.loads(self.registry.read_text(encoding="utf-8"))
                for item, rref in data.items():
                    packages[item] = PackageReference(ref=rref["ref"], updatable=rref["updatable"])
            except (json.JSONDecodeError, FileNotFoundError, ValueError, KeyError, IndexError):
                pass
            self._packages = packages
        return self._packages

    def save(self) -> None:
        if self._packages is None:
            return
        self.registry.parent.mkdir(exist_ok=True, parents=True)
        self.registry.write_text(
            json.dumps({k: {"ref": v.ref, "updatable": v.updatable} for k, v in self._packages.items()})
        )
        self._packages = None

    def add(self, name: str, ref: PackageReference) -> None:
        if self._packages is None:
            self.list()
        self._packages[name] = ref

    def remove(self, name: str) -> None:
        if self._packages is None:
            self.list()
        self._packages.pop(name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented

        return tuple(sorted(self.list().items())) == tuple(sorted(other.list().items()))


class NoWhlDefinitionError(Exception):
    pass


class WhlCache:
    def __init__(self, root: Path) -> None:
        self.root: Final[Path] = root

    def _get_whl_dir(self, name: str) -> Path:
        return self.root / name

    def list(self) -> set[str]:
        return set(item.name for item in self.root.iterdir() if item.is_dir())

    def remove(self, name: str) -> None:
        shutil.rmtree(self._get_whl_dir(name))

    def get_versions_for(self, name: str) -> set[str]:
        whl_dir = self._get_whl_dir(name)
        result = set()
        if not whl_dir.is_dir():
            return result
        for item in whl_dir.iterdir():
            if item.is_dir():
                result.add(item.name)
        return result

    def get_last_version_for(self, name: str) -> str | None:
        versions = self.get_versions_for(name)
        if not versions:
            return None
        parsed_versions = []
        for version in versions:
            try:
                parsed_versions.append(packaging.version.Version(version))
            except InvalidVersion:
                pass
        if not parsed_versions:
            return None

        return str(max(parsed_versions))

    def get_version_folder_for(self, name: str, version: str) -> Path:
        return self._get_whl_dir(name) / version

    def set_whl_path(self, name: str, version: str, path: str) -> None:
        whl_dir = self.get_version_folder_for(name, version)
        metadata_file = whl_dir / "pkg-whl.prop"
        metadata_file.parent.mkdir(exist_ok=True, parents=True)
        (whl_dir / metadata_file).write_text(path, encoding="utf-8")

    def get_whl_path(self, name: str, version: str) -> Path:
        whl_dir = self.get_version_folder_for(name, version)
        metadata_file = whl_dir / "pkg-whl.prop"
        try:
            return whl_dir / metadata_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError as error:
            raise NoWhlDefinitionError() from error


class UpdateWorkspace:
    def __init__(self, root: Path) -> None:
        self.root: Final[Path] = root

        self.current_env: Final[EnvironmentDescriptor] = EnvironmentDescriptor(root / "current")
        self.update_env: Final[EnvironmentDescriptor] = EnvironmentDescriptor(root / "update")

        self.whl_cache: Final[WhlCache] = WhlCache(root / "whl-cache")
        self.pip_cache: Final[Path] = root / "pip-cache"

        self.side_venv: Final[Path] = root / "side-venv"

        if not self.current_env.registry.is_file():
            self.current_env.add(
                APP_NAME,
                PackageReference(ref=get_update_data().update_url, updatable=True),
            )
            self.current_env.save()

        if not self.update_env.registry.is_file():
            for name, ref in self.current_env.list().items():
                self.update_env.add(name, ref)
            self.update_env.save()

    def has_env_changes(self) -> bool:
        return self.current_env != self.update_env

    def cleanup_whl_cache(self) -> None:
        pkgs = set()
        pkgs.update(set(self.current_env.list().keys()))
        pkgs.update(set(self.update_env.list().keys()))
        _logger.debug("The requested packages in envs: %s", pkgs)
        items_to_remove = set(pkg for pkg in self.whl_cache.list() if pkg not in pkgs)
        _logger.debug("Will remove next packages as no longer needed: %s", items_to_remove)
        for item in items_to_remove:
            self.whl_cache.remove(item)

    def run_pip(
        self, *args: PathLike[str] | str, interpreter: PathLike[str] | str = sys.executable, output: bool = False
    ) -> str:
        args = [
            interpreter,
            "-m",
            "pip",
            "--cache-dir",
            self.pip_cache,
            "--isolated",
            "--require-virtualenv",
            "--no-input",
            "--disable-pip-version-check",
            "--no-color",
            *args,
        ]

        if output:
            return subprocess.check_output(args, encoding="utf-8", text=True)
        subprocess.check_call(args, stderr=subprocess.STDOUT)
        return ""


def _determine_install_ref(workspace: UpdateWorkspace, pkg: str) -> None | str:
    ref = workspace.update_env.list()[pkg]

    current_version: str | None = None
    try:
        current_version = importlib.metadata.version(pkg)
    except (NoWhlDefinitionError, PackageNotFoundError):
        pass

    install_ref = ref.ref
    if ref.updatable:
        try:
            with urlopen(ref.ref) as response:
                try:
                    data = json.load(response)
                    name = data["name"]
                    ziball_url = data["zipball_url"]
                except (json.JSONDecodeError, KeyError) as error:
                    raise GenericUpdateError(
                        f"Unable to check updates for {pkg}: unexpected response from update site"
                    ) from error

        except HTTPError as error:
            raise GenericUpdateError(
                f"Unable to check updates for pkg {pkg}: incorrect response from update server"
            ) from error

        if name == current_version:
            return None

        install_ref = ziball_url
    elif workspace.whl_cache.get_versions_for(pkg):
        return None

    return install_ref


def _perform_whl_caching(workspace: UpdateWorkspace, pkg: str) -> None:
    install_ref: str | None = _determine_install_ref(workspace, pkg)
    if install_ref is None:
        return

    _logger.info("Running installation of %s...", pkg)
    with TemporaryDirectory() as tmp_dir_str:
        workspace.run_pip(
            "wheel",
            "-w",
            tmp_dir_str,
            "--no-cache",
            install_ref,
        )

        whl_files = list(Path(tmp_dir_str).glob("*.whl"))
        if not whl_files:
            raise GenericUpdateError(f"No wheel files found after install of {install_ref}")
        whl_file = whl_files[0]

        _logger.info("Target wheel file is %s", whl_file)

        report_file = Path(tmp_dir_str, "report.json")
        workspace.run_pip(
            "install",
            "--report",
            report_file,
            "--dry-run",
            "--no-deps",
            "--ignore-installed",
            whl_file,
        )
        try:
            data = json.loads(report_file.read_text(encoding="utf-8"))

            install_data = data["install"]
            if not isinstance(install_data, list) or len(install_data) != 1:
                raise TypeError("Incorrect format of install report")

            python_package_name = install_data[0]["metadata"]["name"]
            version = install_data[0]["metadata"]["version"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise GenericUpdateError(f"Unable to perform dry-run install: {error}") from error

        if python_package_name != pkg:
            raise GenericUpdateError(
                f"The plugin name '{pkg}' and package name '{python_package_name}' do not match, "
                f"did you specify name right?"
            )

        workspace.whl_cache.set_whl_path(pkg, version, whl_file.name)
        shutil.copy(whl_file, workspace.whl_cache.get_whl_path(pkg, version))


def _check_updates_process(workspace: UpdateWorkspace) -> dict[str, str]:
    result: dict[str, str] = {}
    _logger.info("Update env packages: %s", workspace.update_env.list())
    for pkg in workspace.update_env.list():
        _logger.info("Processing package %s", pkg)
        _perform_whl_caching(workspace, pkg)
    return result


def _check_updates(args: argparse.Namespace) -> None:
    pkgs_workspace = args.pkgs_workspace
    workspace = UpdateWorkspace(Path(pkgs_workspace))
    _check_updates_process(workspace)


def get_interpreter_path_for_venv(venv_path: Path) -> Path:
    if os.name == "nt":
        interpreter = venv_path / "Scripts" / "python.exe"
    else:
        interpreter = venv_path / "bin" / "python"

    if not interpreter.exists():
        raise FileNotFoundError(f"No Python interpreter found in venv: {interpreter}")
    return interpreter


def _collect_wheels_for_install(workspace: UpdateWorkspace, interpreter: Path) -> None:
    whl_house = workspace.update_env.whl_house
    if whl_house.is_dir():
        shutil.rmtree(whl_house)
    whl_house.mkdir(parents=True)

    whl_to_install: set[Path] = _get_wheels_for_install(workspace)
    workspace.run_pip("wheel", "-w", whl_house, *whl_to_install, interpreter=interpreter)


def _get_wheels_for_install(workspace: UpdateWorkspace) -> set[Path]:
    whl_to_install: set[Path] = set()
    for pkg in workspace.update_env.list().keys():
        last_version = workspace.whl_cache.get_last_version_for(pkg)
        if not last_version:
            raise GenericUpdateError(f"Critical error, where is no prebuilt wheel for pkg '{pkg}'!")
        whl_path = workspace.whl_cache.get_whl_path(pkg, last_version)
        whl_to_install.add(whl_path)
    return whl_to_install


def _perform_install_into_venv(workspace: UpdateWorkspace, interpreter: Path, clean_pkgs: bool = False) -> None:
    if clean_pkgs:
        _logger.info("Cleaning virtual environment...")
        output = workspace.run_pip("freeze", interpreter=interpreter, output=True)
        with TemporaryDirectory() as tmp_dir_str:
            file = Path(tmp_dir_str, "env.txt")
            file.write_text(output, encoding="utf-8")
            workspace.run_pip("uninstall", "-y", "-r", file, interpreter=interpreter)

    workspace.run_pip(
        "install",
        "--no-index",
        "--find-links",
        workspace.update_env.whl_house,
        *_get_wheels_for_install(workspace),
        interpreter=interpreter,
    )


def _side_update(args: argparse.Namespace) -> None:
    pkgs_workspace = args.pkgs_workspace
    workspace = UpdateWorkspace(Path(pkgs_workspace))
    venv_path = workspace.side_venv
    if venv_path.is_dir():
        _logger.info("Performing cleaning of virtual environment...")
        shutil.rmtree(venv_path)

    _logger.info("Creating virtual environment at %s...", venv_path)
    subprocess.check_call([sys.executable, "-m", "venv", "--clear", "--upgrade-deps", venv_path])
    interpreter = get_interpreter_path_for_venv(venv_path)
    _logger.info("Collecting wheels for installation...")
    _collect_wheels_for_install(workspace, interpreter)
    _logger.info("Performing a test of update installation...")
    _perform_install_into_venv(workspace, interpreter)


# pylint: disable-next=too-few-public-methods
class _SubProcessBackgroundItemWorker(QObject):
    progress = Signal(str)
    finished = Signal(int)
    cancelled = Signal(str)

    def __init__(self, cmd: list[str]) -> None:
        self.cmd: Final[tuple[str, ...]] = tuple(cmd)
        self.display_cmd: Final[str] = shlex.join(str(item) for item in self.cmd)
        super().__init__()

    @Slot()
    def run(self) -> None:
        _logger.debug("Process [%s] starting...", self.display_cmd)
        env = dict(os.environ)
        with TemporaryDirectory() as tmp_dir_str:
            user_faced_error_file = Path(tmp_dir_str, "user-faced-error.txt")
            user_faced_error_file.touch()
            env[USER_FACED_ERROR_FILE_ENV] = str(user_faced_error_file)
            with subprocess.Popen(
                self.cmd,
                stderr=subprocess.STDOUT,
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            ) as process:
                for line in process.stdout:
                    stripped_line = line.rstrip()
                    if QThread.currentThread().isInterruptionRequested():
                        _logger.debug("Determined interruption request")
                        self.cancelled.emit("")
                        raise InterruptedError("Interruption requested!")
                    _logger.debug("Process [%s]: %s", self.display_cmd, stripped_line)
                    self.progress.emit(stripped_line)
                if (result := process.wait()) != 0:
                    error = user_faced_error_file.read_text(encoding="utf-8", errors="replace")
                    if not error:
                        error = f"Non-zero exit code from sub process [{self.display_cmd}] = {result}"
                    self.cancelled.emit(error)
                    return

                _logger.debug("Process [%s]: completed", self.display_cmd)
                self.finished.emit(result)


class SubProcessDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str, cmd: list[str], closeable: bool = True) -> None:
        super().__init__(parent)
        self.setWindowIcon(IconResource.APP.get_icon())
        self.setModal(True)
        self.setWindowTitle(title)
        self.resize(QSize(2**9, 2**9))
        self._result: int = -1
        self._closeable: bool = closeable

        layout = QVBoxLayout()
        self.setLayout(layout)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setWordWrapMode(QTextOption.WrapMode.WordWrap)
        layout.addWidget(self._text_edit)

        self._thread = QThread()
        self._worker = _SubProcessBackgroundItemWorker(cmd)
        self._worker.moveToThread(self._thread)

        self._worker.progress.connect(self._on_progress)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.cancelled.connect(self._on_cancelled)

        self._thread.start()

    def get_result(self) -> int:
        return self._result

    def _close_dialog(self, state: bool) -> None:
        if state:
            self._thread.finished.connect(self.accept)
        else:
            self._thread.finished.connect(self.reject)

        self._worker.deleteLater()
        self._thread.requestInterruption()
        self._thread.quit()

    @Slot(str)
    def _on_progress(self, val: str) -> None:
        self._text_edit.append(val)

    @Slot(int)
    def _on_finished(self, val: int) -> None:
        self._result = val
        self._close_dialog(True)

    @Slot(str)
    def _on_cancelled(self, reason: str) -> None:
        if reason:
            box = QMessageBox(
                QMessageBox.Icon.Critical,
                self.windowTitle(),
                f"Error happened: '{reason}'. No changes applied. Please check logs",
            )
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.setDefaultButton(QMessageBox.StandardButton.Ok)
            box.setWindowIcon(self.windowIcon())
            box.setDetailedText(self._text_edit.toPlainText())
            box.exec()
        self._close_dialog(False)

    def closeEvent(self, event: QEvent, /) -> None:
        if self._thread.isRunning():
            if self._closeable:
                self._thread.requestInterruption()
            event.ignore()
            return

        event.accept()


def _wait_for_pid(pid: int) -> None:
    _logger.info("Waiting for PID %s for completion...", pid)
    if platform.system() == "Windows":
        while True:
            try:
                handle = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
                if handle == 0:
                    break
                ctypes.windll.kernel32.CloseHandle(handle)
                sleep(1)
            except Exception:  # pylint: disable=broad-exception-caught
                break
    else:
        while True:
            try:
                os.kill(pid, 0)
            except OSError:
                break


class UpdateMainWindow(QMainWindow):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__()
        self.setWindowIcon(IconResource.APP.get_icon())
        self._namespace = args


def _run_main_update_generator(
    workspace: UpdateWorkspace, pid: int, main_interpreter: Path
) -> Generator[str, None, int]:
    with subprocess.Popen(
        [
            sys.executable,
            "-us",
            "-m",
            f"{APP_NAME}.update_helper",
            "main-update-progress",
            workspace.root,
            main_interpreter,
            str(pid),
        ],
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    ) as process:
        for line in process.stdout:
            yield line.rstrip()
        if process.wait() != 0:
            raise ValueError("Error while performing update")
        return process.wait()


def _main_update(args: argparse.Namespace) -> None:
    _application, _ = start_gui_app(args=args.args, logger=_logger, log_name="update", log_stderr=True)

    _logger.debug("The args namespace: %s", args)
    d = SubProcessDialog(
        None,
        "Finalizing update",
        [
            sys.executable,
            "-us",
            "-m",
            f"{APP_NAME}.update_helper",
            "main-update-progress",
            UpdateWorkspace(args.pkgs_workspace).root,
            args.main_interpreter,
            str(args.pid),
        ],
        closeable=False,
    )

    @Slot()
    def _on_exit():
        process_args = list(args.args)
        _logger.info("Start detached process %s", process_args)
        started, pid = QProcess.startDetached(
            str(args.main_interpreter),
            process_args,
        )
        _logger.info("Main window started (%s) as %s", started, pid)
        if not started:
            raise GenericUpdateError("Sub process is not started!")

        _application.quit()

    d.accepted.connect(_on_exit)
    d.show()
    _application.exec()

    if d.result() != QDialog.DialogCode.Accepted:
        raise GenericUpdateError("Update cancelled midway!")



def _main_update_window(args: argparse.Namespace) -> None:
    pid = int(args.pid)
    _wait_for_pid(pid)

    pkgs_workspace = args.pkgs_workspace
    workspace = UpdateWorkspace(Path(pkgs_workspace))
    main_interpreter = Path(args.main_interpreter)

    _perform_install_into_venv(workspace, main_interpreter, clean_pkgs=True)

    shutil.copy(workspace.update_env.registry, workspace.current_env.registry)
    if workspace.current_env.whl_house.is_dir():
        shutil.rmtree(workspace.current_env.whl_house)
    shutil.copytree(workspace.update_env.whl_house, workspace.current_env.whl_house)
    workspace = UpdateWorkspace(Path(pkgs_workspace))  # reset caches after update
    workspace.cleanup_whl_cache()


def _main_update_handle() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True)

    check_updates_parser = subparsers.add_parser("check-updates")
    check_updates_parser.add_argument("pkgs_workspace", type=Path, help="Path to packages workspace")
    check_updates_parser.set_defaults(func=_check_updates)

    side_update_parser = subparsers.add_parser("side-update")
    side_update_parser.add_argument("pkgs_workspace", type=Path, help="Path to packages workspace")
    side_update_parser.set_defaults(func=_side_update)

    main_update_parser = subparsers.add_parser("main-update")
    main_update_parser.add_argument("pkgs_workspace", type=Path, help="Path to packages workspace")
    main_update_parser.add_argument("pid", type=int, help="The PID of the parent process")
    main_update_parser.add_argument("main_interpreter", type=Path, help="The path to the main venv interpreter")
    main_update_parser.add_argument("args", type=str, nargs="+", help="Args to restart main instance")
    main_update_parser.set_defaults(func=_main_update)

    main_update_progress_parser = subparsers.add_parser("main-update-progress")
    main_update_progress_parser.add_argument("pkgs_workspace", type=Path, help="Path to packages workspace")
    main_update_progress_parser.add_argument(
        "main_interpreter", type=Path, help="The path to the main venv interpreter"
    )
    main_update_progress_parser.add_argument("pid", type=int, help="The PID of the parent process")
    main_update_progress_parser.set_defaults(func=_main_update_window)

    args = parser.parse_args()

    try:
        args.func(args)
    except Exception as error:  # pylint: disable=broad-exception-caught
        if USER_FACED_ERROR_FILE_ENV in os.environ:
            path = Path(os.environ[USER_FACED_ERROR_FILE_ENV])
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_text(str(error), encoding="utf-8")
        raise


if __name__ == "__main__":
    sys.exit(_main_update_handle())
